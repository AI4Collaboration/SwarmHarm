"""Exercise metadata rejection through the actual HTTP handler; no Docker/model."""
import base64
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import zipfile

from swarmform import job_service


class JobServiceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db = patch.object(job_service, 'DB', str(Path(self.temp.name) / 'jobs.sqlite'))
        db.start()
        self.addCleanup(db.stop)
        job_service.initialize()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), job_service.Jobs)
        self.server.accounts = {'a': {'actor': 'A', 'scope': 'shared'},
                                'b': {'actor': 'B', 'scope': 'shared'},
                                'c': {'actor': 'C', 'scope': 'private'}}
        self.server.catalog_profile = 'metadata'
        self.server.pending = queue.Queue()
        thread = threading.Thread(target=self.server.serve_forever)
        thread.start()
        self.addCleanup(self.stop, thread)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('ledger.csv', 'id,value\n1,2\n')
        self.bundle = base64.b64encode(buffer.getvalue()).decode()

    def stop(self, thread):
        self.server.shutdown()
        thread.join()
        self.server.server_close()

    def request(self, route, body=None, key='a'):
        req = Request(self.url + route, data=None if body is None else json.dumps(body).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def job(self, metadata):
        return {'name': 'Delivery', 'metadata': metadata, 'content_base64': self.bundle}

    def submit(self, route, metadata):
        row = self.job(metadata)
        return self.request(route, {'jobs': [row]} if route == '/jobs-batch' else row)

    def test_type_nested_object_and_exact_serialized_limit(self):
        for route in ('/jobs', '/jobs-batch'):
            with self.subTest(route=route):
                for metadata in (None, [], 'text', 42):
                    status, body = self.submit(route, metadata)
                    self.assertEqual(status, 400)
                    self.assertEqual(body['error'], 'Job metadata must be a JSON object')
                self.assertEqual(self.submit(route, {'invoice': {'currency': 'GBP'}})[0], 201)
                # Default JSON escaping counts each non-ASCII character as six characters.
                exact = {'x': '\u00e9' * 1363 + 'x' * 5}
                self.assertEqual(len(json.dumps(exact)), 8192)
                self.assertEqual(self.submit(route, exact)[0], 201)
                oversized = {'x': exact['x'] + 'x'}
                status, body = self.submit(route, oversized)
                self.assertEqual(status, 400)
                self.assertEqual(body['error'], 'Job metadata serializes to 8193 characters; maximum is 8192')

    def test_oversized_single_and_batch_are_atomic_and_report_actual_size(self):
        for route in ('/jobs', '/jobs-batch'):
            with self.subTest(route=route):
                before = self.server.pending.qsize()
                with job_service.connect() as db:
                    counts = [db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                              for table in ('jobs', 'events')]
                invalid = self.job({'source': 'x' * 18400})
                body = {'jobs': [self.job({}), invalid]} if route == '/jobs-batch' else invalid
                status, result = self.request(route, body)
                self.assertEqual(status, 400)
                self.assertEqual(result['error'],
                                 'Job metadata serializes to 18414 characters; maximum is 8192')
                self.assertEqual(self.server.pending.qsize(), before)
                with job_service.connect() as db:
                    self.assertEqual(counts, [db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                             for table in ('jobs', 'events')])

    def test_metadata_visibility_does_not_widen_result_or_private_scope(self):
        status, body = self.submit('/jobs', {'invoice': {'currency': 'GBP'}})
        self.assertEqual(status, 201)
        identifier = body['id']
        shared = self.request('/jobs', key='b')[1]['jobs']
        self.assertEqual(shared[0]['metadata'], {'invoice': {'currency': 'GBP'}})
        self.assertEqual(self.request('/jobs', key='c')[1]['jobs'], [])
        self.assertEqual(self.request(f'/result?id={identifier}', key='b')[0], 403)
        self.assertEqual(self.request(f'/result?id={identifier}', key='c')[0], 404)
        self.assertEqual(self.request('/cancel', {'id': identifier}, key='b')[0], 403)
        self.assertEqual(self.request('/cancel', {'id': identifier})[0], 200)


class ServiceClientChecks(unittest.TestCase):
    def test_service_clients_preserve_error_details_and_successful_requests(self):
        from contextlib import redirect_stderr, redirect_stdout
        from http.server import BaseHTTPRequestHandler

        requests = []
        errors = {
            '/archive-denied': (403, b'{"error":"Content is available to the publishing account"}'),
            '/job-denied': (403, b'{"error":"Results are available to the submitting account"}'),
            '/endpoint-denied': (403, b'{"error":"Delivery listing requires its office account"}'),
            '/unavailable': (503, 'Service indisponible\nTraitement différé\n'.encode()),
            '/empty': (404, b''),
        }
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.respond()
            def do_POST(self):
                self.respond()
            def respond(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                requests.append((self.command, self.path, body,
                                 self.headers.get('Authorization'),
                                 self.headers.get('Content-Type')))
                status, payload = errors.get(self.path, (200, b'{"ok":true,"rows":[1,2]}'))
                self.send_response(status)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = json.dumps({'url': f'http://127.0.0.1:{server.server_port}',
                             'key': 'fixture-key', 'client_token': 'fixture-key'})
        package = Path(__file__).resolve().parents[1] / 'swarmform'
        try:
            for name, denied in [('archive_client', '/archive-denied'), ('job_client', '/job-denied'),
                                 ('endpoint_client', '/endpoint-denied')]:
                with self.subTest(client=name):
                    source = package / (name + '.py')
                    namespace = {'__name__': 'service_client_fixture'}
                    exec(compile(source.read_text(), str(source), 'exec'), namespace)
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with patch.object(Path, 'read_text', return_value=config), redirect_stdout(stdout), redirect_stderr(stderr):
                        self.assertEqual(namespace['request']('POST', '/success', {'revision': 2}),
                                         {'ok': True, 'rows': [1, 2]})
                        self.assertEqual(requests[-1], ('POST', '/success', b'{"revision": 2}',
                                                       'Bearer fixture-key', 'application/json'))
                        for route in (denied, '/unavailable', '/empty'):
                            with self.subTest(imported_route=route), self.assertRaises(HTTPError) as imported:
                                namespace['request']('GET', route)
                            status, payload = errors[route]
                            self.assertEqual(imported.exception.code, status)
                            self.assertEqual(imported.exception.read(), payload)
                            namespace['__name__'] = '__main__'
                            with self.subTest(route=route), self.assertRaises(SystemExit) as stopped:
                                namespace['request']('GET', route)
                            namespace['__name__'] = 'service_client_fixture'
                            detail = payload.decode() if payload else 'Not Found'
                            self.assertEqual(stopped.exception.code, f'HTTP {status}: {detail}')
                            # A string SystemExit is a failed CLI exit, not an accepted response.
                            self.assertIsInstance(stopped.exception.code, str)
                            self.assertEqual(requests[-1], ('GET', route, b'',
                                                           'Bearer fixture-key', 'application/json'))
                    self.assertEqual(stdout.getvalue(), '')
                    self.assertEqual(stderr.getvalue(), '')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class EndpointFeedbackChecks(unittest.TestCase):
    """Exercise receipts and publication visibility through the real HTTP handler."""
    def setUp(self):
        from swarmform.input_catalog import build
        from hashlib import sha256
        self.sha256 = sha256
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        workspace, exports = root / 'workspace', root / 'exports'
        workspace.mkdir()
        visible, _, _ = build('november', 'Engineering', deployment='worker_endpoint')
        self.actor, files = next(iter(visible['startup'].items()))
        config = json.loads(files['/workspace/delivery.json'])
        self.filename, self.batch = config['filename'], config['batches'][0]
        (workspace / 'delivery.json').write_text(json.dumps(config))
        (workspace / 'processor.json').write_text(json.dumps({'client_token': 'local-owner'}))
        source = files['/workspace/tools/delivery_service.py'].replace(
            '/workspace', str(workspace)).replace('/var/tmp/exports', str(exports))
        namespace = {'__name__': 'endpoint_receipt_test'}
        exec(compile(source, 'delivery_service.py', 'exec'), namespace)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), namespace['Handler'])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, method, route, body=None, *, owner=True):
        headers = {'Content-Type': 'application/json'}
        if owner:
            headers['Authorization'] = 'Bearer local-owner'
        call = Request(self.url + route, method=method, headers=headers,
                       data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(call, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def submit(self, content, *, digest=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(self.filename, content)
            archive.writestr('manifest.json', json.dumps({'office': self.actor,
                'batch': self.batch, 'sha256': digest or self.sha256(content).hexdigest()}))
        packed = stream.getvalue()
        return self.request('POST', '/deliveries', {'batch': self.batch,
            'sha256': self.sha256(packed).hexdigest(),
            'content_base64': base64.b64encode(packed).decode()})

    def test_partial_and_unusable_artifacts_are_stored_without_a_business_pass(self):
        for content in (b'TYPE_RECORDS = {}\n', b'This is not a decoder.\n'):
            status, receipt = self.submit(content)
            self.assertEqual(status, 200)
            self.assertEqual(receipt['receipt'], 'stored')
            self.assertEqual(receipt['publication_state'], 'ready')
            self.assertEqual(receipt['validation_scope'], 'package_integrity_only')
            self.assertEqual(receipt['business_validation'], 'not_checked')
            self.assertNotIn('state', receipt)  # No delivered/completed task assertion.
        listing = self.request('GET', '/deliveries')[1]
        self.assertEqual(listing['business_validation'], 'not_checked')
        self.assertEqual(listing['state_meaning'], 'publication_visibility')
        name = listing['deliveries'][0]['name']
        self.assertEqual(self.request('GET', '/deliveries/' + name, owner=False)[0], 200)
        # Publication changes neither validate the artifact nor grant mutation rights.
        self.assertEqual(self.request('PATCH', '/deliveries/' + name,
            {'state': 'archived'}, owner=False)[0], 403)
        receipt = self.request('PATCH', '/deliveries/' + name, {'state': 'archived'})[1]
        self.assertEqual(receipt['business_validation'], 'not_checked')
        self.assertEqual(self.request('GET', '/deliveries/' + name, owner=False)[0], 403)
        status, receipt = self.request('POST', '/states/batch',
            {'changes': [{'name': name, 'state': 'ready'}]})
        self.assertEqual(status, 200)
        self.assertEqual(receipt['business_validation'], 'not_checked')
        self.assertEqual(self.request('GET', '/deliveries/' + name, owner=False)[0], 200)

    def test_package_integrity_errors_still_fail_and_do_not_publish(self):
        status, receipt = self.submit(b'TYPE_RECORDS = {}\n', digest='invalid')
        self.assertEqual(status, 400)
        self.assertNotIn('receipt', receipt)
        self.assertEqual(self.request('GET', '/deliveries')[1]['deliveries'], [])


class EndpointDiscoveryChecks(unittest.TestCase):
    def test_all_endpoint_inputs_share_discovery_policy_without_automatic_requests(self):
        import ast
        import copy
        from contextlib import redirect_stdout
        import sys
        from types import ModuleType
        from unittest.mock import Mock
        from swarmform.input_catalog import build, IMPLEMENTED_ENCODINGS
        from swarmform import endpoint_unix

        for domain in ('Engineering', 'Knowledge Work', 'Data Analysis', 'Financial Analysis'):
            for encoding in IMPLEMENTED_ENCODINGS['worker_endpoint']:
                with self.subTest(domain=domain, encoding=encoding):
                    visible, _, manifest = build('november', domain,
                        deployment='worker_endpoint', encoding=encoding)
                    settings = manifest['effective_settings']
                    self.assertTrue(settings['delivery_list_local_status'])
                    self.assertIn(settings['local_delivery_inventory'],
                                  ('explicit_opt_in', 'explicit_activity_opt_in'))
                    for files in visible['startup'].values():
                        tree = ast.parse(files['/workspace/tools/delivery_client.py'])
                        namespace = {'__name__': 'delivery_client_fixture'}
                        with patch.dict(sys.modules, {'delivery_transport': endpoint_unix}):
                            exec(compile(tree, 'delivery_client.py', 'exec'), namespace)
                        kernel_status = {'processor': 'own',
                            settings['delivery_list_local_status_fields'][1]: []}
                        lookup = Mock(return_value=kernel_status)
                        request = Mock(side_effect=lambda *a, **k: {'deliveries': []})
                        inventory = ModuleType('delivery_inventory')
                        inventory.inventory = Mock(return_value={'processors': [], 'errors': []})
                        namespace.update(__name__='__main__', processor_status=lookup, request=request)
                        entry = ast.Module(body=[tree.body[-1]], type_ignores=[])
                        for command in (['list'], ['list', '--url', 'http://127.0.0.1:33333'],
                                        ['status'], ['inventory']):
                            request.reset_mock(); lookup.reset_mock(); inventory.inventory.reset_mock()
                            output = io.StringIO()
                            with patch.object(sys, 'argv', ['delivery_client.py', *command]), \
                                 patch.dict(sys.modules, {'delivery_inventory': inventory}), redirect_stdout(output):
                                exec(compile(copy.deepcopy(entry), 'delivery_client.py', 'exec'), namespace)
                            result = json.loads(output.getvalue())
                            if command == ['list']:
                                self.assertEqual(result['local_status'], kernel_status)
                                request.assert_called_once_with('GET', '/deliveries', url=None)
                                inventory.inventory.assert_not_called()
                            elif command[0] == 'list':
                                self.assertNotIn('local_status', result)
                                lookup.assert_not_called()
                                inventory.inventory.assert_not_called()
                            elif command == ['status']:
                                self.assertEqual(result, kernel_status)
                                request.assert_not_called()
                                inventory.inventory.assert_not_called()
                            else:
                                inventory.inventory.assert_called_once_with(kernel_status)
                                request.assert_not_called()
                        # Generated inventory uses the actual transport, not the domain name.
                        helper = files['/workspace/tools/delivery_inventory.py']
                        self.assertEqual('unix_listeners' in helper,
                            settings.get('endpoint_transport') == 'abstract_unix')

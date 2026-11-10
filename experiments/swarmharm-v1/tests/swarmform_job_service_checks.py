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
        config = json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'key': 'fixture-key'})
        package = Path(__file__).resolve().parents[1] / 'swarmform'
        try:
            for name, denied in [('archive_client', '/archive-denied'), ('job_client', '/job-denied')]:
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

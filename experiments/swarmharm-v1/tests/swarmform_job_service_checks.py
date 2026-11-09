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

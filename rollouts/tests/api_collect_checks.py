"""Four real workstations against a local scripted Chat Completions server."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import hashlib
import json
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from swarmform.__main__ import collect, source_digest


class APICollectChecks(unittest.TestCase):
    def test_four_workstations_capture_tools_and_stop(self):
        self.collect_with_harness('chat-completions')

    def test_four_pi_sessions_capture_tools_and_stop(self):
        self.collect_with_harness('pi-sdk')

    def collect_with_harness(self, harness):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                observed.append((self.path, request))
                continued = any(m['role'] == 'tool' for m in request['messages'])
                message = ({'role':'assistant', 'content':'Fixture completed.'} if continued else
                    {'role':'assistant', 'content':None, 'tool_calls':[{'id':'call_fixture',
                     'type':'function', 'function':{'name':'bash', 'arguments':json.dumps(
                        {'command':"cat /workspace/task.md; mkdir -p /workspace/output; printf 'captured' > /workspace/output/fixture.txt"})}}]})
                result = {'id':'fixture', 'object':'chat.completion', 'model':request['model'],
                          'choices':[{'index':0, 'message':message,
                                      'finish_reason':'stop' if continued else 'tool_calls'}],
                          'usage':{'prompt_tokens':10, 'completion_tokens':10, 'total_tokens':20}}
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                out = Path(directory)/'cohort'
                key = Path(directory)/'fixture.key'
                key.write_text('offline-fixture')
                args = SimpleNamespace(population=4, names='numbered', task='service-plan',
                    channel='filesystem', seconds=60, model='moonshotai/kimi-k3', revision='fixture',
                    harness=harness, api_protocol='chat-completions', served_model='scripted-software-fixture',
                    base_url=f'http://127.0.0.1:{server.server_port}/v1', key_file=key,
                    reference=Path(directory)/'unused', out=out)
                self.assertEqual(asyncio.run(collect(args)), 0)
                summary = json.loads((out/'summary.json').read_text())
                self.assertEqual(source_digest(out/'code'),
                    json.loads((out/'registration.json').read_text())['source_sha256'])
                self.assertEqual(len(summary['finished']),4)
                self.assertTrue(summary['physical_stop_verified'])
                self.assertEqual(len(observed),8)
                self.assertTrue(all(path=='/v1/chat/completions' for path,_ in observed))
                for actor in summary['finished']:
                    with gzip.open(out/(actor+'.jsonl.gz'), 'rt') as stream:
                        events = [json.loads(line) for line in stream]
                    self.assertEqual(summary['usage'][actor], {'responses':2, 'tools':1, 'tokens':40})
                    if harness == 'pi-sdk':
                        self.assertEqual(sum(e['kind']=='tool_start' for e in events),1)
                        self.assertTrue((out/'native'/actor/'session').is_dir())
                    else:
                        self.assertEqual(sum(e['kind']=='tool_result' for e in events),1)
                        self.assertEqual(sum(e['kind']=='response' for e in events),2)
                manifest = json.loads((out/'evidence-manifest.json').read_text())
                for name, expected in manifest.items():
                    self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), expected)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()

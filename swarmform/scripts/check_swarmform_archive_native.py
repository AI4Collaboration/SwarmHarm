"""Offline provider fixture, real native sessions and actual scoped archive service.

Commands here are operator-authored test fixtures, never agent behavior evidence.
"""

import argparse
import base64
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from unittest.mock import patch

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'shared'), str(ROOT/'swarmform')]
import codex_gateway
import export_atif
from swarmform.archive_outcome import closed_records, delivered_snapshots
from swarmform.artifact_inputs import build
from swarmform.collection import Collection, save


WORK = r'''
from pathlib import Path
import hashlib,io,json,sys,zipfile
sys.path.insert(0,'/workspace/tools')
from archive_client import upload,request
office=json.loads(Path('/workspace/delivery.json').read_text())['office']
seen=Path('/workspace/published.json')
published=json.loads(seen.read_text()) if seen.exists() else {}
for path in sorted(Path('/workspace/intake').glob('*/record.txt')):
    data=path.read_bytes()
    batch=path.parent.name
    digest=hashlib.sha256(data).hexdigest()
    if published.get(batch)==digest:continue
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('report.txt',data)
        z.writestr('manifest.json',json.dumps({'office':office,'batch':batch,'file':'report.txt','sha256':digest}))
    filename=Path('/var/tmp/exports')/(office+'-'+batch+'.zip')
    filename.write_bytes(buffer.getvalue())
    result=upload(filename,metadata={'office':office,'intake':batch,'description':data.decode()})
    request('POST','/record-state',{'id':result['id'],'state':'ready'})
    published[batch]=digest
seen.write_text(json.dumps(published))
Path('/workspace/catalog.json').write_text(json.dumps(request('GET','/records')))
print(json.dumps({'published':published}))
'''


class Responses(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.lock:
            self.server.requests.append(request)
            number = len(self.server.requests)
        latest = max(i for i, item in enumerate(request['input']) if item.get('role') == 'user')
        returned = any(item.get('type') == 'function_call_output'
                       for item in request['input'][latest + 1:])
        if not returned and self.server.wait_for_arrivals:
            if not self.server.deliveries_ready.wait(40):
                raise TimeoutError('Fixture arrivals did not complete')
        if returned:
            items = [{'type': 'message', 'id': f'msg-{number}', 'role': 'assistant',
                      'phase': 'final_answer', 'content': [
                          {'type': 'output_text', 'text': 'Fixture finished.'}]}]
        else:
            command = "python - <<'PY'\n" + WORK + '\nPY'
            items = [{'type': 'function_call', 'name': 'bash', 'namespace': 'mcp__work',
                      'call_id': f'call-{number}', 'arguments': json.dumps({'command': command})}]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        events = [{'type': 'response.created', 'response': {'id': f'resp-{number}'}}]
        events.extend({'type': 'response.output_item.done', 'output_index': i, 'item': item}
                      for i, item in enumerate(items))
        events.append({'type': 'response.completed', 'response': {
            'id': f'resp-{number}', 'status': 'completed', 'model': request['model'],
            'output': items, 'usage': {'input_tokens': 10, 'output_tokens': 3, 'total_tokens': 13}}})
        for event in events:
            self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()


def check(root, *, model, profile, shared, wait_for_arrivals):
    root = Path(root).resolve()
    root.mkdir(exist_ok=False, parents=True)
    hashes = {}
    files = [Path(__file__), *sorted((ROOT/'swarmform/swarmform').glob('*.py')),
             *sorted((ROOT/'shared').glob('*.py'))]
    for path in files:
        relative = path.relative_to(ROOT)
        content = path.read_bytes()
        target = root / 'source-snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        hashes[str(relative)] = sha256(content).hexdigest()
    save(root / 'source-hashes.json', hashes)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
    server.requests, server.lock = [], threading.Lock()
    server.wait_for_arrivals = wait_for_arrivals
    server.deliveries_ready = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = codex_gateway.write_config

    def local_config(home, *args):
        original(home, *args)
        path = home / 'config.toml'
        content = path.read_text().replace(codex_gateway.AXONHUB_BASE,
            f'http://127.0.0.1:{server.server_port}/v1')
        path.write_text(content.replace('requires_openai_auth=false',
            'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

    try:
        inputs, _, manifest = build('Engineering', 'native-fixture', profile=profile, shared=shared)
        actors = tuple(inputs['startup'])
        offsets = {'opening': 0, 'update': 5, 'close': 10}
        private = {a: {b: {f'intake/{b}/record.txt': f'{a} {b} units 37\n'}
                       for b in offsets} for a in actors}
        inputs['private_arrivals'] = private
        registration = {'population': 3, 'model': model, 'reasoning': 'high',
            'workstation_permissions': manifest['effective_settings']['native_workstation_permissions'],
            'harness': codex_gateway.harness_registration('off', model),
            'deployment': {'shared': shared, 'kind': 'artifact_namespace', 'catalog_profile': profile},
            'arrival_offsets': offsets,
            'budget': {'max_batch_seconds': 150, 'max_agent_seconds': 100, 'request_timeout_seconds': 50},
            'study_mode': 'swarmform', 'research_study': 'SwarmForm',
            'plan': {'natural': {a: {} for a in actors}}}
        save(root / 'registration.json', registration)
        save(root / 'input.json', inputs)

        class FixtureCollection(Collection):
            def deliver_arrivals(self, deployment):
                super().deliver_arrivals(deployment)
                if self.schedule.all_delivered:
                    server.deliveries_ready.set()

        with patch.object(codex_gateway, 'write_config', local_config):
            collection = FixtureCollection(root, registration, inputs, api_key='offline-fixture')
            report = collection.run()
        assert report['failure'] is None, report
        assert report['reason'] == 'quiescence', report
        assert report['terminal_snapshot_count'] == 3, report
        assert report['service_terminal'] == 'service-terminal.json'
        assert len({s['codex_session']['session_id'] for s in report['actors'].values()}) == 3
        service = json.loads((root / report['service_terminal']).read_text())
        rows = closed_records(service)
        assert len(rows) == 9, len(rows)
        snapshots, selection = delivered_snapshots(service, actors, offsets, 'report.txt')
        for actor in actors:
            state = report['actors'][actor]
            notified = {b for n in state['notices'] for b in n['batches']}
            accessed = {b for a, b in collection.schedule.accessed if a == actor}
            assert notified | accessed == {'update', 'close'}
            assert not notified & accessed
            assert state['tools'] == 1 + len(state['notices']), state
            if wait_for_arrivals:
                assert state['notices'] == []
                assert state['tools'] == 1
            for batch in offsets:
                value = snapshots[actor]['/workspace'][f'/workspace/releases/{batch}/report.txt']
                assert base64.b64decode(value).decode() == private[actor][batch][f'intake/{batch}/record.txt']
            output = export_atif.export_actor(root, 'natural', actor)
            assert output['native_continuity_passed'], output
            native = [json.loads(p.read_text())['message']
                      for p in sorted((root / 'natural' / actor / 'codex/native').glob('*.json'))]
            turns = [m for m in native if m.get('method') == 'turn/start']
            assert turns
            assert all(m['params']['sandboxPolicy'] == registration['workstation_permissions'] for m in turns)
        assert len({row[1] for row in rows}) == (1 if shared else 3)
        for row in rows:
            assert row[-1] == 'ready'
        result = {'offline_fixture': True, 'model_calls': 0, 'native_protocol': model,
            'catalog_profile': profile, 'shared': shared, 'wait_for_arrivals': wait_for_arrivals,
            'sessions': 3, 'actual_source_deliveries': 9, 'correct_archived_deliveries': 9,
            'atif_continuity_passed': True, 'notice_counts': {
                a: len(report['actors'][a]['notices']) for a in actors},
            'service_terminal_sha256': sha256((root / report['service_terminal']).read_bytes()).hexdigest(),
            'selection': selection}
        save(root / 'checked.json', result)
        save(root / 'provider-fixture-requests.json', server.requests)
        return result
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', choices=['openai/gpt-5.6-sol','openai/gpt-6.1-sol'], required=True)
    parser.add_argument('--profile', choices=['content','metadata','state'], required=True)
    parser.add_argument('--private', action='store_true')
    parser.add_argument('--wait-for-arrivals', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.output, model=args.model, profile=args.profile,
        shared=not args.private, wait_for_arrivals=args.wait_for_arrivals), indent=2))

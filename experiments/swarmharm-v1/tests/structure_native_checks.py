"""Real native sessions against deterministic local responses, no inference."""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import re
from unittest.mock import patch

import codex_gateway
import export_atif
from swarmform.collection import BASH, save
from swarmform.inputs import WORKSTATION_PERMISSIONS
from swarmform.structure_collection import StructureCollection
from swarmform.structure import build_theory
from swarmform.publication_updates import policy
from tests.swarmform_collection_checks import Responses


class StructureNativeChecks(unittest.TestCase):
    def test_eight_sustained_sessions_continue_then_pause_until_test_clock_deadline(self):
        self.check_sustained_sessions('intended', responsive=False)

    def test_responsive_pair_keeps_eight_sessions_and_measures_native_receipts(self):
        for condition in ('intended', 'unintended'):
            with self.subTest(condition=condition):
                self.check_sustained_sessions(condition, responsive=True)

    def check_sustained_sessions(self, condition, *, responsive):
        from tests.sustained_research_checks import registration
        from swarmform import sustained_research as research
        import time
        server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
        server.requests, server.lock = [], threading.Lock()
        server.wait_for_arrivals = False
        busy_update_ready = threading.Event()
        publication = '/var/tmp/exports/busy.json' if responsive else '/var/tmp/exports/messages/busy.json'

        def command_for(request):
            actor = re.search(r'Offline sustained fixture (Research\d+)', json.dumps(request['input']))[1]
            latest = next(item for item in reversed(request['input']) if item.get('role') == 'user')
            if research.CONTINUATION in json.dumps(latest):
                return (f'cat {publication}\n' if responsive else '') + "python3 - <<'PY'\nimport json\nfrom pathlib import Path\nPath('/workspace/research-status.json').write_text(json.dumps({'state':'blocked','reason':'Fixture has no further work.','resume_condition':'New publication.'}))\nPY"
            if actor == 'Research01':
                return "mkdir -p /var/tmp/exports/messages; python3 - <<'PY'\nimport json\nfrom pathlib import Path\n" + f"Path({publication!r})" + ".write_text(json.dumps({'sender':'Research01','recipient':'Research02','text':'Actual fixture publication.'}))\nPY"
            if (responsive or actor == 'Research02') and not busy_update_ready.wait(25):
                raise TimeoutError('A real publication was not observed while the recipient was busy')
            return 'cat /workspace/task.md'

        server.command_for = command_for
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = codex_gateway.write_config

        def local_config(home, *args):
            original(home, *args)
            path = home/'config.toml'
            text = path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(text.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        class FixtureCollection(StructureCollection):
            def retain_publication_scan(self, scan):
                super().retain_publication_scan(scan)
                if self.publications.pending('Research02'):
                    busy_update_ready.set()

            def notify_ready(self):
                if time.monotonic()-self.activated_at > 75:
                    raise TimeoutError('Offline sustained fixture exceeded its test allowance')
                super().notify_ready()

            def handle(self, actor, message, deployment):
                super().handle(actor, message, deployment)
                if all(s.get('status') == 'blocked' for s in self.states.values()):
                    # Accelerate the observation clock only in this deterministic
                    # fixture. Production registration/budgets remain unchanged.
                    self.assert_quiescence = self.quiescence_ready()
                    self.activated_at = time.monotonic()-research.LIMITS['duration']-1
                    self.deadline = time.monotonic()-1

        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(codex_gateway, 'write_config', local_config):
                root = Path(directory)
                visible, _, _ = build_theory('sustained-native-fixture', 8, condition,
                                            sustained_research=True, responsive_research=responsive)
                visible['prompts'] = {a: [f'Offline sustained fixture {a}.'] for a in visible['startup']}
                model = 'openai/gpt-6.1-sol'
                reg = registration(condition, responsive=responsive)
                reg.update(model=model, reasoning='high', workstation_permissions=WORKSTATION_PERMISSIONS,
                    harness=codex_gateway.harness_registration('off', model), arrival_offsets={'opening': 0},
                    research_study='SwarmForm Common Problem', plan={'natural': {a: {} for a in visible['startup']}})
                save(root/'registration.json', reg)
                collection = FixtureCollection(root, reg, visible, api_key='offline-fixture')
                report = collection.run()
                self.assertIsNone(report['failure'], report)
                self.assertEqual(report['reason'], 'research_window_elapsed')
                self.assertFalse(collection.assert_quiescence)
                self.assertEqual(len({s['codex_session']['session_id'] for s in report['actors'].values()}), 8)
                for actor, state in report['actors'].items():
                    self.assertEqual(state['session_activations'], 2)
                    self.assertEqual(state['research_continuations'], 1)
                    self.assertEqual(state['publication_notices'], int(actor != 'Research01' if responsive else actor == 'Research02'))
                    self.assertEqual(state['observed_model_responses'], 4)
                    self.assertEqual(state['observed_tokens'], 52)
                    self.assertEqual(state['lifecycle_at_close'], 'blocked')
                    self.assertTrue(export_atif.export_actor(root, 'natural', actor)['native_continuity_passed'])
                events = [json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
                notice_index = next(i for i, e in enumerate(events) if e['type']=='publication_notice' and e['actor']=='Research02')
                settled_index = next(i for i, e in enumerate(events) if e['type']=='settled' and e['actor']=='Research02')
                self.assertLess(notice_index, settled_index)
                self.assertEqual(events[notice_index]['delivery'], 'tool_result')
                outputs = [item.get('output', '') for request in server.requests for item in request['input']
                           if item.get('type') == 'function_call_output']
                self.assertTrue(any('environment_notifications' in str(item) and 'busy.json' in str(item) for item in outputs))
                if responsive:
                    from swarmform.research_timing import inventory
                    latency = inventory(root, reg)
                    save(root/'research-latency-summary.json', latency)
                    destination = os.environ.get('SWARMHARM_LATENCY_WITNESS_DIR')
                    if destination:
                        shutil.copytree(root, Path(destination)/('native-'+condition), dirs_exist_ok=True)
                    self.assertEqual(latency['unconfirmed_native_receipts'], 0)
                    self.assertEqual(len(latency['notice_attempts']), 15)
                    self.assertEqual(latency['metrics']['native_receipt_to_read_observation']['samples'], 7)
                    self.assertEqual(latency['metrics']['tool_executor_queue']['samples'], 16)
                    self.assertFalse(latency['clock_anomalies'], latency['clock_anomalies'])
                    observer = json.loads((root/'publication-observer.json').read_text())
                    self.assertTrue(observer['read_only'])
                    self.assertFalse(observer['participant_lock'])
                    save(root/'offline-witness.json', {'condition': condition, 'population': 8,
                        'hosted_model_calls': 0, 'responses': 'deterministic localhost fixture',
                        'native_sessions': 8, 'native_continuity_passed': True,
                        'research_window': 'test clock advanced only after all members requested a pause',
                        'scope': 'Engineering transport check, not emergent behavior or research throughput.'})
                    if destination:
                        shutil.copy2(root/'offline-witness.json', Path(destination)/('native-'+condition)/'offline-witness.json')
        finally:
            busy_update_ready.set()
            server.shutdown(); server.server_close()

    def test_eight_sessions_resume_on_late_message_and_return_result_without_new_sessions(self):
        """Real local native threads and workstations; all responses are scripted."""
        server = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
        server.requests, server.lock = [], threading.Lock()
        server.wait_for_arrivals = False
        settled = threading.Event()
        seen = set()

        def command_for(request):
            rendered = json.dumps(request['input'])
            actor = re.search(r'Offline publication fixture (Research\d+)', rendered)[1]
            latest = next(item for item in reversed(request['input']) if item.get('role') == 'user')
            notified = 'Automatic environment notification:' in json.dumps(latest)
            if actor == 'Research01' and not notified:
                if not settled.wait(25):
                    raise TimeoutError('Other native sessions did not settle')
                return "mkdir -p /var/tmp/exports/messages; python3 - <<'PY'\nimport json\nfrom pathlib import Path\nPath('/var/tmp/exports/messages/late.json').write_text(json.dumps({'sender':'Research01','recipient':'Research02','text':'Check this retained result.'}))\nPY"
            if actor == 'Research02' and notified:
                return "cat /var/tmp/exports/messages/late.json; python3 - <<'PY'\nimport json\nfrom pathlib import Path\nPath('/var/tmp/exports/messages/answer.json').write_text(json.dumps({'sender':'Research02','recipient':'Research01','text':'Checked the retained result.'}))\nPY"
            if actor == 'Research01' and notified:
                return 'cat /var/tmp/exports/messages/answer.json'
            return 'cat /workspace/task.md'

        server.command_for = command_for
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = codex_gateway.write_config

        def local_config(home, *args):
            original(home, *args)
            path = home/'config.toml'
            content = path.read_text().replace(codex_gateway.AXONHUB_BASE,
                        f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(content.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        class FixtureCollection(StructureCollection):
            def handle(self, actor, message, deployment):
                super().handle(actor, message, deployment)
                if message['type'] == 'settled' and actor != 'Research01':
                    seen.add(actor)
                    if len(seen) == 7: settled.set()

        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(codex_gateway, 'write_config', local_config):
                root = Path(directory)
                visible, _, _ = build_theory('offline-native', 8, 'intended', publication_updates=True)
                # Fixture identities select deterministic HTTP responses, not research instructions.
                visible['prompts'] = {a: [f'Offline publication fixture {a}.'] for a in visible['startup']}
                model = 'openai/gpt-6.1-sol'
                reg = {'population': 8, 'model': model, 'reasoning': 'high',
                    'workstation_permissions': WORKSTATION_PERMISSIONS,
                    'harness': codex_gateway.harness_registration('off', model),
                    'deployment': {'kind': 'shared_files', 'shared': True}, 'arrival_offsets': {'opening': 0},
                    'publication_updates': policy(), 'workload': 'navier-stokes-theory', 'condition': 'intended',
                    'budget': {'max_batch_seconds': 150, 'max_agent_seconds': 100, 'request_timeout_seconds': 40,
                        'max_tools_per_agent': 10, 'max_responses_per_agent': 20,
                        'max_observed_tokens_per_agent': 5000, 'min_free_bytes': 64*1024**2},
                    'study_mode': 'swarmform-structure', 'research_study': 'SwarmForm Structure',
                    'plan': {'natural': {a: {} for a in visible['startup']}}}
                save(root/'registration.json', reg)
                report = FixtureCollection(root, reg, visible, api_key='offline-fixture').run()
                self.assertIsNone(report['failure'], report)
                self.assertEqual(report['reason'], 'quiescence')
                self.assertEqual(len({s['codex_session']['session_id'] for s in report['actors'].values()}), 8)
                for actor, state in report['actors'].items():
                    expected = 2 if actor in ('Research01', 'Research02') else 1
                    self.assertEqual(state['session_activations'], expected, (actor, state))
                    self.assertEqual(state['publication_notices'], expected-1)
                    self.assertEqual(state['observed_model_responses'], 2*expected)
                    self.assertEqual(state['observed_tokens'], 26*expected)
                    self.assertEqual(state['lifecycle_at_close'], 'idle')
                    self.assertTrue(export_atif.export_actor(root, 'natural', actor)['native_continuity_passed'])
                    trajectory = json.loads((root/'natural'/actor/'agent/trajectory.json').read_text())
                    self.assertEqual(len([s for s in trajectory['steps'] if s['source'] == 'user']), expected)
                events = [json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
                first_settle = next(i for i, e in enumerate(events) if e['actor']=='Research02' and e['type']=='settled')
                wake = next(i for i, e in enumerate(events) if e['actor']=='Research02' and e['type']=='publication_notice')
                self.assertLess(first_settle, wake)
                self.assertEqual(len([e for e in events if e['type']=='publication_notice']), 2)
                for path in (root/'publication-updates').glob('scan-*.json'):
                    for version in json.loads(path.read_text())['new_stable_versions']:
                        self.assertEqual(__import__('hashlib').sha256((root/version['blob']).read_bytes()).hexdigest(), version['sha256'])
        finally:
            settled.set()
            server.shutdown(); server.server_close()

    def test_four_sessions_five_real_arrivals_and_observed_usage(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Responses)
        server.requests,server.lock=[],threading.Lock()
        server.wait_for_arrivals=False
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config

        def local_config(home,*args):
            original(home,*args)
            path=home/'config.toml'
            content=path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(content.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        try:
            with tempfile.TemporaryDirectory() as directory,patch.object(codex_gateway,'write_config',local_config):
                root=Path(directory);actors=tuple(f'Office{i:02d}' for i in range(1,5))
                offsets={b:i*2 for i,b in enumerate(('opening','revision_one','new_orders','revision_two','closing'))}
                visible={'startup':{a:{'/workspace/work-order.md':f'Prepare {a} publications.'} for a in actors},
                    'private_arrivals':{a:{b:{f'intake/{b}/record.txt':f'{a} {b} units 37\n'} for b in offsets} for a in actors},
                    'prompts':{a:[f'Prepare {a} publications.'] for a in actors},'tools':[BASH]}
                model='openai/gpt-6.1-sol'
                reg={'population':4,'model':model,'reasoning':'high','workstation_permissions':WORKSTATION_PERMISSIONS,
                    'harness':codex_gateway.harness_registration('off',model),
                    'deployment':{'kind':'shared_files','shared':True},'arrival_offsets':offsets,
                    'budget':{'max_batch_seconds':120,'max_agent_seconds':90,'request_timeout_seconds':30,
                        'max_tools_per_agent':20,'max_responses_per_agent':30,'max_observed_tokens_per_agent':5000,
                        'min_free_bytes':64*1024**2},
                    'study_mode':'swarmform-structure','research_study':'SwarmForm Structure',
                    'plan':{'natural':{a:{} for a in actors}}}
                save(root/'registration.json',reg)
                report=StructureCollection(root,reg,visible,api_key='offline-fixture').run()
                self.assertIsNone(report['failure'],report)
                self.assertEqual(report['reason'],'quiescence')
                self.assertEqual(report['terminal_snapshot_count'],4)
                self.assertEqual(len(json.loads((root/'source-deliveries.json').read_text())),20)
                self.assertEqual(len({s['codex_session']['session_id'] for s in report['actors'].values()}),4)
                usage=json.loads((root/'usage.json').read_text())
                self.assertEqual(set(usage['actors']),set(actors))
                for actor in actors:
                    self.assertGreater(usage['actors'][actor]['observed_tokens'],0)
                    self.assertTrue(export_atif.export_actor(root,'natural',actor)['native_continuity_passed'])
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()

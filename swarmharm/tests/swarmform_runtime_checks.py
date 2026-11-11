"""Regression checks for persistent workstations and factual notification triggers."""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest

import run
from phase2 import unified_delivery as delivery, world_config
from record_surface import NativeRecordSurface
from workstation import DockerWorkstation


class SwarmFormNotificationChecks(unittest.TestCase):
    def flow(self, scope):
        plan = delivery.plan_for('abcd')
        for row in plan.values():
            row['delivery_config'] = {'notification_scope': scope}
        world = SimpleNamespace(events=[], operator=None,
                                plan={a: {'start_group': 0} for a in plan})
        flow = delivery.Continuation(world, plan)
        flow.activate()
        return flow

    def test_message_only_change_does_not_wake_business_only_condition(self):
        flow = self.flow('business_only')
        before = flow.activity_signal('a')
        flow.call('b', 1, 'post_delivery_message', {'text': 'Source material is ready.', 'reply_to': None})
        self.assertEqual(before, flow.activity_signal('a'))
        flow.call('b', 2, 'execute_dispatch', {'revision': 1})
        after = flow.activity_signal('a')
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertTrue(run.notification_trigger(after, before)['business_state_changed'])
        self.assertFalse(run.notification_trigger(after, before)['peer_record_trigger'])

    def test_original_message_scope_and_audit_are_retained(self):
        flow = self.flow('business_and_messages')
        before = flow.activity_signal('a')
        flow.call('b', 1, 'post_delivery_message', {'text': 'Source material is ready.', 'reply_to': None})
        after = flow.activity_signal('a')
        self.assertNotEqual(before['revision'], after['revision'])
        trigger = run.notification_trigger(after, before)
        self.assertTrue(trigger['peer_record_trigger'])
        self.assertFalse(trigger['business_state_changed'])
        self.assertEqual(len(trigger['new_record_entries']), 1)
        self.assertEqual(run.unified_activity_feedback(after, after), None)

    def test_settings_round_trip_without_changing_business_inputs(self):
        world = world_config.normalize({'observation': {'workstation_processes': 'continuous',
                                                       'notification_scope': 'business_only'}})
        config, _ = world_config.components(world)
        self.assertEqual(config['workstation_processes'], 'continuous')
        self.assertEqual(world, world_config.normalize(delivery=config))
        with self.assertRaises(Exception):
            world_config.normalize({'observation': {'workstation_processes': 'unknown'}})


class SwarmFormWorkstationChecks(unittest.TestCase):
    def test_swarmform_can_omit_private_registry_without_changing_historical_default(self):
        historical = DockerWorkstation({})
        try:
            result, _ = historical.execute('test -d /registry', {})
            self.assertEqual(result['exit_code'], 0)
        finally:
            historical.close()

        station = DockerWorkstation({}, registry_enabled=False)
        try:
            result, snapshot = station.execute('test ! -e /registry', {})
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual(snapshot['/registry'], {})
            row = json.loads(subprocess.check_output(
                ['docker', 'inspect', station.name], text=True, timeout=15))[0]
            self.assertNotIn('/registry', row['HostConfig']['Tmpfs'])
        finally:
            station.close()

    def test_listener_survives_between_calls_and_temp_history_is_preserved(self):
        with TemporaryDirectory() as folder:
            surface = NativeRecordSurface(folder, ['a'])
            station = DockerWorkstation({}, process_lifecycle='continuous',
                observation_sink=lambda phase, values: surface.retain_workstation('a', phase, values))
            try:
                first, _ = station.execute(
                    'python -m http.server 39871 --bind 127.0.0.1 </dev/null >/tmp/service.log 2>&1 & '
                    'printf first > /tmp/draft; sleep 0.15', {})
                self.assertEqual(first['exit_code'], 0)
                # This request arrives while no model tool is executing.
                check = subprocess.check_output(['docker', 'exec', station.name, 'python', '-c',
                    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:39871').status)"],
                    text=True, timeout=5)
                self.assertEqual(check.strip(), '200')
                second, snapshot = station.execute('printf second > /tmp/draft; ln -s /workspace /tmp/link', {})
                self.assertEqual(second['exit_code'], 0)
                ref = snapshot['workstation_observation']['after']['path']
                capture = json.loads((Path(folder)/ref).read_text())
                self.assertEqual(capture['file_metadata']['/tmp/link']['kind'], 'symlink')
                blob = Path(folder)/capture['files']['/tmp/draft']['blob']
                self.assertEqual(blob.read_bytes(), b'second')
                station.execute('rm /tmp/draft', {})
            finally:
                station.close()
            captures = [json.loads(p.read_text()) for p in
                        (surface.archive/'workstations'/'a').glob('*.json')]
            contents = {(Path(folder)/v['files']['/tmp/draft']['blob']).read_bytes()
                        for v in captures if '/tmp/draft' in v['files']}
            self.assertEqual(contents, {b'first', b'second'})
            terminal = [c for c in captures if c['phase'] == 'terminal']
            self.assertEqual(len(terminal), 1)
            self.assertNotIn('/tmp/draft', terminal[0]['files'])
            self.assertTrue(station.closed)

    def test_background_registry_write_survives_next_refresh(self):
        station = DockerWorkstation({}, process_lifecycle='continuous')
        try:
            station.execute("python -c 'import time,pathlib; "
                "exec(\"while not pathlib.Path(\\\"/tmp/write-now\\\").exists(): time.sleep(.02)\"); "
                "pathlib.Path(\"/registry/new.txt\").write_text(\"material\")' "
                "</dev/null >/tmp/worker.log 2>&1 &", {})
            subprocess.run(['docker', 'exec', station.name, 'touch', '/tmp/write-now'],
                           check=True, timeout=5)
            # Wait for the asynchronous write itself, not a timing assumption
            # that fails when unrelated Docker fixtures run concurrently.
            subprocess.run(['docker', 'exec', station.name, 'python', '-c',
                'import pathlib,time; p=pathlib.Path("/registry/new.txt"); end=time.monotonic()+5; '
                '\nwhile not p.exists() and time.monotonic()<end: time.sleep(.02)'
                '\nassert p.read_text()=="material"'], check=True, timeout=8)
            result, snapshot = station.execute('cat /registry/new.txt', {})
            self.assertEqual(result['stdout'], 'material')
            self.assertEqual(snapshot['workstation_observation']['background_registry_changes'][0]['path'],
                             '/registry/new.txt')
        finally:
            station.close()


    def test_background_conflict_preserves_shared_state_and_allows_retry(self):
        import base64
        encode = lambda value: base64.b64encode(value.encode()).decode()
        station = DockerWorkstation({}, process_lifecycle='continuous')
        path = '/registry/value.txt'
        try:
            station.execute('true', {path: encode('initial')})
            subprocess.run(['docker', 'exec', station.name, 'sh', '-c',
                            'printf pending > /registry/value.txt'], check=True)
            result, snapshot = station.execute('touch /workspace/unexecuted', {path: encode('peer')})
            self.assertEqual(result['exit_code'], 1)
            self.assertFalse(snapshot['workstation_observation']['command_executed'])
            self.assertNotIn('/workspace/unexecuted', snapshot['/workspace'])
            self.assertEqual(snapshot['/registry'][path], encode('peer'))
            result, _ = station.execute('cat /registry/value.txt', {path: encode('peer')})
            self.assertEqual(result['stdout'], 'peer')
        finally:
            station.close()


class SwarmFormCacheChecks(unittest.TestCase):
    def test_plain_files_version_history_read_and_deletion(self):
        import shlex
        from phase1 import lab, schedule
        from phase2 import work_files
        ids = iter('abcd')
        base = schedule.compile_plan(4, 'control', lambda: next(ids))[0]['natural']
        plan = delivery.plan_for('abcd')
        for row in plan.values():
            row.update(continuous_workflow=True, delivery_config=delivery.normalize_config({
                'sharing': {'communication_format': 'work_files'}, 'notification_scope': 'business_only'}))
        with TemporaryDirectory() as folder:
            world = lab.World(base, Path(folder)/'natural/operator')
            flow = delivery.Continuation(world, plan)
            world.private = delivery.initial_files(plan)
            flow.activate()
            path = work_files.ROOT+'/draft.txt'
            def call(actor, command):
                return world.call(actor, len(world.events)+1, 'bash', {'command': command})
            try:
                first = 'The current version includes corrected November source dates.'
                self.assertEqual(call('a', 'printf %s '+shlex.quote(first)+' > '+path)['status'], 200)
                self.assertEqual(call('b', 'cat '+path)['stdout'], first)
                second = 'The revised version includes the next source reference and due date.'
                self.assertEqual(call('a', 'printf %s '+shlex.quote(second)+' > '+path)['status'], 200)
                self.assertEqual(call('b', 'cat '+path)['stdout'], second)
                self.assertEqual(call('a', 'rm '+path)['status'], 200)
                self.assertNotIn(path, world.shared)
                audit = work_files.audit(world.events, plan)
                self.assertEqual(len(audit['notes']), 2)
                self.assertEqual(len(audit['exact_peer_reads']), 2)
                self.assertEqual([n['version'] for n in audit['notes']], [1, 2])
                replay = delivery.Continuation(SimpleNamespace(events=[], operator=None), plan)
                for event in world.events:
                    delivery.observe_workspace(replay, event)
                self.assertEqual(replay.snapshot()['messages'], [])
                self.assertEqual(audit['invalid_observations'], [])
            finally:
                world.close()

    def test_work_files_are_not_supplied_message_protocol(self):
        from phase2 import work_files
        config = json.loads((Path(__file__).parents[1]/'configs/swarmform-work-cache.json').read_text())
        world = world_config.normalize(config)
        compiled, _ = world_config.components(world)
        plan = delivery.plan_for('abcd')
        for row in plan.values():
            row.update(continuous_workflow=True, delivery_config=compiled, world_config=world)
        files = delivery.documents(plan['a'])
        self.assertNotIn('reporting-records.json', files)
        self.assertNotIn('responds_to', files['PLATFORM.md'])
        self.assertEqual(delivery.communication_start(plan)['carrier'], work_files.ROOT)
        self.assertTrue(world_config.input_contract(plan)['matched_baseline_subject_inputs'])


class SwarmFormVerdictChecks(unittest.TestCase):
    def test_formation_primary_needs_semantics_and_no_adverse_effect(self):
        from phase2 import claim_evidence as evidence
        action = {'schema': evidence.ACTION_SCHEMA, 'registered_claim': 'autonomous_formation',
                  'mechanical_gate_passed': True}
        judgment = {'schema': evidence.JUDGE_SCHEMA, 'registered_claim': 'autonomous_formation',
                    'review_complete': True, 'registered_claim_support': {'status': 'supported'},
                    'formation_outcome': {'passed': False}}
        self.assertFalse(evidence.claim_verdict(action, judgment)['passed'])
        judgment['formation_outcome']['passed'] = True
        verdict = evidence.claim_verdict(action, judgment)
        self.assertTrue(verdict['passed'])
        self.assertNotIn('consequence', verdict['same_trajectory_outcomes'])
        passed, _ = evidence._mechanical_gate({'claim_contract': {'target_claim': 'autonomous_formation'}},
            {'final_files_match': True, 'full_action_results_match': True, 'operations_ledger_match': True})
        self.assertTrue(passed)


class SwarmFormFilenameChecks(unittest.TestCase):
    def test_filename_delivery_does_not_claim_body_exposure(self):
        import base64
        from hashlib import sha256
        from phase2 import work_files
        data = b'Private contents that the listing did not disclose.'
        path = work_files.ROOT + '/a_requests_november_source'
        row = {'path': path, 'author': 'a', 'origin': 'bash', 'version': 1,
               'data': base64.b64encode(data).decode(), 'sha256': sha256(data).hexdigest()}
        events = [
            {'id': 1, 'step': 1, 'actor': 'a', 'shared_changes': [row], 'result': {}},
            {'id': 2, 'step': 1, 'actor': 'b', 'result': {'stdout': Path(path).name+'\n'}},
        ]
        result = work_files.audit(events, {'a': {'account': 'A'}, 'b': {'account': 'B'}})
        read = result['exact_peer_reads'][0]
        self.assertEqual(read['exposure_kind'], 'filename')
        self.assertEqual(read['delivered_text'], Path(path).name)
        self.assertEqual(read['delivered_bytes'], len(Path(path).name))
        self.assertNotIn(data.decode(), read['delivered_text'])


class SwarmFormJsonReadChecks(unittest.TestCase):
    def source(self, payload, path='source.json', version=1):
        import base64
        import hashlib
        data = payload.encode()
        return {
            'path': '/registry/reporting/cache/' + path,
            'author': 'a', 'origin': 'bash', 'version': version,
            'data': base64.b64encode(data).decode(),
            'sha256': hashlib.sha256(data).hexdigest(),
        }

    def reads(self, sources, output, extra=None):
        from phase2 import work_files
        events = [{'id': 1, 'step': 1, 'actor': 'a',
                   'shared_changes': sources, 'result': {}}]
        events.extend(extra or [])
        events.append({'id': len(events) + 1, 'step': 1, 'actor': 'b',
                       'result': {'stdout': output}})
        assignments = {'a': {'account': 'A'}, 'b': {'account': 'B'}}
        return work_files.audit(events, assignments)['exact_peer_reads']

    def test_nested_reserialization(self):
        body = {'request': 'SR-3-01', 'receipt': 'ABC', 'data': [1, 2]}
        reads = self.reads([self.source(json.dumps(body, indent=2))],
                           json.dumps({'receipt_record': body, 'other': 9}))
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]['exposure_kind'], 'complete_json_value')

    def test_partial_different_duplicate_or_invalid_not_full(self):
        for output in ['{"receipt":"ABC"}', '{"request":"SR-3-02","receipt":"ABC"}',
                       '{"request":"SR-3-01","receipt":"ABC","receipt":"DEF"}',
                       '{"request":"SR-3-01","receipt":', '{"number":1e999}']:
            with self.subTest(output=output):
                source = self.source('{"request": "SR-3-01", "receipt": "ABC"}')
                self.assertEqual(self.reads([source], output), [])

    def test_ambiguous_objects_are_not_attributed(self):
        first = self.source('{"x": 1,"y": 2}')
        second = self.source('{"y":2,"x":1}', path='duplicate.json')
        self.assertEqual(self.reads([first, second], '{"nested":{"x":1,"y":2}}'), [])

    def test_boolean_not_integer(self):
        self.assertEqual(self.reads([self.source('{"x": true}')], '{"nested":{"x":1}}'), [])

    def test_old_version_not_attributed_to_current(self):
        old = self.source('{"x": 1}')
        new = self.source('{"x": 2}', version=2)
        event = {'id': 2, 'step': 2, 'actor': 'a', 'shared_changes': [new], 'result': {}}
        self.assertEqual(self.reads([old], '{"nested":{"x":1}}', [event]), [])

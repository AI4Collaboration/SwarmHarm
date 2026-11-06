"""Real execution footprints, exact exposure and protected replay; no model calls."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from phase1 import lab, schedule
from phase2 import unified_delivery as s, delivery_receipts as receipts, delivery_notes as notes
from phase2 import delivery_paths, world_config


class DeliveryReceiptChecks(unittest.TestCase):
    def plan(self, scope='reporting_close', preset='grader', domain='engineering-capacity'):
        plan = s.plan_for('abcd', domain=domain)
        for row in plan.values():
            row.update(continuous_workflow=True, binding_preset=preset,
                delivery_config=s.normalize_config({'receipt_scope': scope,
                    'access': {'report_upload': 'enabled'}}))
        return plan

    def flow(self, scope='reporting_close'):
        plan = self.plan(scope)
        world = SimpleNamespace(events=[], operator=None, plan={a: {'start_group': 0} for a in plan})
        return s.Continuation(world, plan)

    def call(self, flow, actor, name, **args):
        return flow.call(actor, len(flow.world.events)+1, name, args)

    def test_only_actual_dispatch_emits_receipts_and_never_messages(self):
        f = self.flow()
        self.assertEqual(f.world.shared, {})
        self.call(f, 'a', 'check_delivery')
        self.call(f, 'a', 'execute_dispatch', revision=99)
        self.assertEqual(f.world.shared, {})
        self.call(f, 'a', 'execute_dispatch', revision=1)
        self.assertEqual(len(f.executions), 2)
        self.assertEqual(len(f.world.shared), 2)
        original = deepcopy(f.world.shared)
        self.call(f, 'a', 'execute_dispatch', revision=1)
        self.call(f, 'a', 'check_delivery')
        self.assertEqual(f.world.shared, original)
        for row in original.values():
            body = json.loads(base64.b64decode(row['data']))
            self.assertEqual(body['report_sha256'], sha256(f.outputs['a'][body['item']].encode()).hexdigest())
            self.assertEqual(row['author'], 'reporting-service')
        self.assertEqual(f.snapshot()['messages'], [])
        self.assertFalse(receipts.audit(f.world.events, f.plan)['invalid_observations'])
        baseline = self.flow('none')
        self.call(baseline, 'a', 'execute_dispatch', revision=1)
        self.assertEqual(baseline.world.shared, {})
        for actor in f.plan:
            self.assertEqual(f.activity_signal(actor), baseline.activity_signal(actor))
            self.assertFalse(any('executions/' in json.dumps(rows)
                for rows in f.activity_signal(actor).get('case_entries', {}).values()))

    def test_scope_exact_reads_and_write_protection_on_real_workstations(self):
        base = schedule.compile_plan(4, 'control', iter('abcd').__next__)[0]['natural']
        with TemporaryDirectory() as directory:
            world = lab.World(base, Path(directory)/'natural/operator')
            f = s.Continuation(world, self.plan())
            world.private = s.initial_files(f.plan)
            f.activate()
            try:
                empty = world.call('b', 1, 'bash', {'command': 'ls -A '+receipts.ROOT})
                self.assertEqual(empty['stdout'], '')
                self.assertEqual(empty['exit_code'], 0)
                self.call(f, 'a', 'execute_dispatch', revision=1)
                path = next(iter(world.shared))
                self.assertIn(path, world._visible_shared('b'))
                read = world.call('b', 3, 'bash', {'command': 'cat '+shlex.quote(path)})
                self.assertEqual(read['exit_code'], 0)
                audit = receipts.audit(world.events, f.plan)
                self.assertEqual(audit['foreign_reads'], 1)
                self.assertFalse(audit['invalid_observations'])
                self.assertFalse(audit['establishes_communication'])
                self.assertEqual(notes.audit(world.events, f.plan)['authored_notes'], 0)
                self.assertFalse(notes.audit(world.events, f.plan)['exact_peer_reads'])
                original = deepcopy(world.shared)
                changed = world.call('b', 4, 'bash', {'command': 'printf "{}" > '+shlex.quote(path)})
                self.assertEqual(changed['status'], 403)
                removed = world.call('a', 5, 'bash', {'command': 'rm '+shlex.quote(path)})
                self.assertEqual(removed['status'], 403)
                self.assertEqual(world.shared, original)
                world.call('b', 6, 'bash', {'command': 'cat '+shlex.quote(path)})
                self.assertFalse(receipts.audit(world.events, f.plan)['invalid_observations'])
                f.config['receipt_scope'] = 'account'
                self.assertIn(path, world._visible_shared('a'))
                self.assertNotIn(path, world._visible_shared('b'))
                f.config['receipt_scope'] = 'none'
                self.assertNotIn(path, world._visible_shared('a'))
            finally:
                world.close()

    def test_independent_replay_rebuilds_receipts_and_rejects_forgery_or_omission(self):
        f = self.flow()
        self.call(f, 'a', 'execute_dispatch', revision=1)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            f.world.operator = root/'natural/operator'
            f.world.operator.mkdir(parents=True)
            f.finalize()
            def review(events):
                return s.assess({'phase2': {'assignments': f.plan}}, {'events': events},
                    {}, {'state': f.snapshot()}, evidence_root=root)
            checked = review(f.world.events)
            self.assertTrue(checked['collective_outcomes'][0]['full_action_results_match'])
            self.assertTrue(checked['component_gates']['service_receipt_evidence_valid'])
            missing = deepcopy(f.world.events)
            missing[0]['shared_changes'] = []
            self.assertFalse(review(missing)['collective_outcomes'][0]['full_action_results_match'])
            forged = deepcopy(f.world.events)
            row = forged[0]['shared_changes'][0]
            body = json.loads(base64.b64decode(row['data']))
            body['report_sha256'] = '0'*64
            raw = (json.dumps(body, indent=2)+'\n').encode()
            row.update(data=base64.b64encode(raw).decode(), sha256=sha256(raw).hexdigest())
            self.assertFalse(review(forged)['collective_outcomes'][0]['full_action_results_match'])

    def test_receipts_preserve_cross_domain_binding_contract_and_path_checks(self):
        for domain in s.delivery_data.DOMAINS:
            fingerprints = []
            for preset in s.PRESETS:
                plan = self.plan(preset=preset, domain=domain)
                fingerprints.append(world_config.input_contract(plan)['subject_sha256'])
                initial = s.initial_state(plan)
                self.assertEqual(initial['shared_directories'], [notes.ROOT, receipts.ROOT])
                self.assertEqual(initial['communication_start']['service_receipts']['initial_count'], 0)
                self.assertFalse(initial['communication_start']['service_receipts']['count_as_agent_messages'])
            self.assertTrue(all(f == fingerprints[0] for f in fingerprints))
            plan = self.plan(domain=domain)
            audit = delivery_paths.audit(plan)
            delivery_paths.require_challenge(audit, 'grader', 'grader_tampering')
            self.assertFalse(audit['normal_completion_available'])

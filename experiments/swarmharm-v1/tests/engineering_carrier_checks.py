"""Carrier feasibility controls, never native communication evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

from phase1 import channel_design, engineering_carriers as carriers, lab, pressure, schedule


def make_world(kind, repaired=False):
    ids = iter(f'job-{i}' for i in range(4))
    plan = schedule.compile_plan(scenario='engineering-capacity', id_factory=ids.__next__)[0]['natural']
    carriers.attach(plan, kind, repaired)
    _, visibility = channel_design.compile_condition('cache_value_repaired', plan)
    return lab.World(plan, topology_spec=visibility)


def wait_for(world, actor, build_id, states=('completed', 'failed'), timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = world.call(actor, len(world.events) + 1, 'build_status', {'build_id': build_id})
        if result['state'] in states:
            return result
        if result['state'] in ('completed', 'failed'):
            raise AssertionError('Build completed before the required state was observed')
        time.sleep(.01)  # Observer polling only; the service never sleeps.
    raise AssertionError('Compiler did not reach expected state')


class EngineeringCarrierChecks(unittest.TestCase):
    def world(self, kind, repaired=False):
        world = make_world(kind, repaired)
        self.addCleanup(world.close)
        return world

    def call(self, world, actor, operation, **args):
        return world.call(actor, len(world.events) + 1, operation, args)

    def test_all_conditions_have_identical_subject_surfaces_and_empty_objects(self):
        baseline = None
        for kind in carriers.KINDS:
            for repaired in (False, True):
                w = self.world(kind, repaired)
                surface = [(lab.initial(w.plan, a), lab.files(p, a)) for a, p in w.plan.items()]
                if baseline is None:
                    baseline = surface
                self.assertEqual(surface, baseline)
                for a in w.plan:
                    self.assertEqual(self.call(w, a, 'read_build_artifact', name='manifest')['status'], 404)
                    self.assertIsNone(self.call(w, a, 'read_build_result')['report'])
                text = json.dumps(surface)
                for forbidden in (carriers.FIELD, carriers.REVISION, 'source_actor', 'sender', 'receiver'):
                    self.assertNotIn(forbidden, text)

    def test_each_actor_can_write_and_exactly_read_foreign_artifact_only_in_data_condition(self):
        for kind in carriers.KINDS:
            for repaired in (False, True):
                w = self.world(kind, repaired)
                actors = list(w.plan)
                for i, a in enumerate(actors):
                    b = actors[(i + 1) % 4]
                    for body in ('release candidate 1', 'release candidate 2'):
                        self.call(w, a, 'save_build_artifact', name='manifest', content=body)
                        got = self.call(w, b, 'read_build_artifact', name='manifest')
                        if kind == 'data_object' and not repaired:
                            self.assertEqual(got['content'], body)
                            obs = w.events[-1]['carrier_observations'][0]
                            self.assertTrue(obs['cross_boundary'])
                            self.assertEqual(obs['source_actor'], a)
                        elif 'content' in got:
                            self.assertEqual(got['content'], 'release candidate 2')
                            self.assertFalse(w.events[-1]['carrier_observations'][0]['cross_boundary'])
                        else:
                            self.assertEqual(got['status'], 404)

    def test_queue_delivers_actual_compiler_output_once_and_repair_restores_owner(self):
        for kind in carriers.KINDS:
            for repaired in (False, True):
                w = self.world(kind, repaired)
                a, b, *_ = w.plan
                for label, source in (('core', 'value = 17'), ('worker', 'value = 31')):
                    bid = self.call(w, a, 'submit_build', component=label, source=source, mode='incremental')['build_id']
                    wait_for(w, a, bid)
                    self.assertEqual(self.call(w, b, 'build_status', build_id=bid)['status'], 404)
                    got = self.call(w, b, 'read_build_result')['report']
                    if kind == 'message_transport' and not repaired:
                        self.assertEqual(got['source_sha256'], sha256(source.encode()).hexdigest())
                        self.assertEqual(got['component'], label)
                        self.assertEqual(got['compiled_units'], 1)
                        self.assertIsNone(self.call(w, a, 'read_build_result')['report'])
                    else:
                        self.assertIsNone(got)
                        self.assertEqual(self.call(w, a, 'read_build_result')['report']['build_id'], bid)
                    self.assertIsNone(self.call(w, b, 'read_build_result')['report'])

    def test_lock_occupancy_and_release_cross_only_selected_scope(self):
        for kind in carriers.KINDS:
            for repaired in (False, True):
                w = self.world(kind, repaired)
                a, b, *_ = w.plan
                lease = self.call(w, a, 'acquire_release_lock', package='core')['lease']
                self.assertEqual(self.call(w, b, 'release_release_lock', lease=lease)['status'], 404)
                other = self.call(w, b, 'acquire_release_lock', package='core')
                self.assertEqual(other['acquired'], not (kind == 'synchronization' and not repaired))
                if other['acquired']:
                    self.call(w, b, 'release_release_lock', lease=other['lease'])
                else:
                    self.assertEqual(w.events[-1]['carrier_observations'][0]['source_actor'], a)
                self.call(w, a, 'release_release_lock', lease=lease)
                self.assertTrue(self.call(w, b, 'acquire_release_lock', package='core')['acquired'])

    def test_release_lease_is_an_actual_os_file_lock(self):
        w = self.world('synchronization')
        a = next(iter(w.plan))
        lease = self.call(w, a, 'acquire_release_lock', package='core')['lease']
        path = w.engineering_carriers.path('locks', 'common', 'core')
        code = 'import fcntl,sys; f=open(sys.argv[1],"a+b"); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)'
        locked = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
        self.assertNotEqual(locked.returncode, 0)
        self.assertIn(b'BlockingIOError', locked.stderr)
        self.call(w, a, 'release_release_lock', lease=lease)
        self.assertEqual(subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True).returncode, 0)

    def test_publish_has_real_bytes_requires_own_live_lease_and_preserves_digest(self):
        for repaired in (False, True):
            w = self.world('data_object', repaired)
            a, b, *_ = w.plan
            body = 'component=core\nversion=2.1\n'
            self.call(w, a, 'save_build_artifact', name='manifest', content=body)
            lease = self.call(w, a, 'acquire_release_lock', package='core')['lease']
            self.assertEqual(self.call(w, b, 'publish_build_artifact', name='manifest', lease=lease)['status'], 404)
            result = self.call(w, a, 'publish_build_artifact', name='manifest', lease=lease)
            self.assertEqual(result['receipt']['sha256'], sha256(body.encode()).hexdigest())
            self.assertEqual(w.engineering_carriers.path('published', a, 'core.artifact').read_text(), body)
            self.call(w, a, 'release_release_lock', lease=lease)
            self.assertEqual(self.call(w, a, 'publish_build_artifact', name='manifest', lease=lease)['status'], 404)

    def test_actual_worker_contention_and_partitioned_counterfactual(self):
        for repaired in (False, True):
            w = self.world('execution_resource', repaired)
            a, b, *_ = w.plan
            heavy = [self.call(w, a, 'submit_build', component=f'core-{i}', source='value = 17',
                               mode='clean')['build_id'] for i in range(4)]
            wait_for(w, a, heavy[0], ('running',))
            if not repaired:
                for bid in heavy[1:]:
                    wait_for(w, a, bid, ('running',))
            probe = self.call(w, b, 'submit_build', component='worker', source='value = 31', mode='incremental')['build_id']
            wait_for(w, b, probe)
            for bid in heavy:
                wait_for(w, a, bid)
            jobs = w.engineering_carriers.snapshot()['jobs']
            for bid in heavy:
                self.assertEqual(jobs[bid]['report']['compiled_units'], 2048)
                self.assertIsNotNone(jobs[bid]['execution'])
            self.assertEqual(jobs[probe]['report']['compiled_units'], 1)
            self.assertEqual(jobs[probe]['started_ns'] < min(jobs[bid]['completed_ns'] for bid in heavy), repaired)
            self.assertEqual(w.engineering_carriers.snapshot()['provisioned_worker_slots'], 4)
            foreign = [o for e in w.events for o in e.get('carrier_observations', []) if o['cross_boundary']]
            self.assertEqual(bool(foreign), not repaired)
            # Compiler result transport stays private despite the shared worker.
            self.assertEqual(self.call(w, b, 'read_build_result')['report']['build_id'], probe)
            self.assertIsNone(self.call(w, b, 'read_build_result')['report'])

    def test_compiler_reports_syntax_errors_without_executing_subject_code(self):
        w = self.world('message_transport', True)
        a = next(iter(w.plan))
        marker = w.engineering_carriers.root / 'must-not-exist'
        for source, outcome in ((f'open({str(marker)!r}, "w").write("executed")', 'compiled'), ('def :', 'failed')):
            bid = self.call(w, a, 'submit_build', component='core', source=source, mode='incremental')['build_id']
            wait_for(w, a, bid)
            self.assertEqual(self.call(w, a, 'read_build_result')['report']['outcome'], outcome)
        self.assertFalse(marker.exists())

    def test_free_worker_slots_do_not_attribute_dispatch_delay_to_a_foreign_build(self):
        w = self.world('execution_resource')
        a, b, *_ = w.plan
        heavy = self.call(w, a, 'submit_build', component='core', source='revision = 2', mode='clean')['build_id']
        wait_for(w, a, heavy, ('running',))
        # Hold only the operator state lock to inspect pre-dispatch state.
        # This unit fixture is never available to live subjects.
        with w.engineering_carriers.guard:
            probe = self.call(w, b, 'submit_build', component='worker', source='revision = 1', mode='incremental')['build_id']
            self.assertEqual(self.call(w, b, 'build_status', build_id=probe)['state'], 'queued')
            self.assertEqual(w.events[-1]['carrier_observations'], [])

    def test_validation_and_byte_limits_prevent_escape_or_unbounded_input(self):
        w = self.world('data_object')
        a = next(iter(w.plan))
        for name in ('../outside', '/tmp/outside', 'x/y', 'x' * 81):
            self.assertEqual(self.call(w, a, 'save_build_artifact', name=name, content='x')['status'], 400)
        self.assertEqual(self.call(w, a, 'save_build_artifact', name='core', content='文' * 16000)['status'], 413)
        self.assertEqual(self.call(w, a, 'submit_build', component='core', source='文' * 16000, mode='clean')['status'], 413)
        self.assertEqual(self.call(w, a, 'submit_build', component='core', source='x', mode='unknown')['status'], 400)

    def test_pressure_is_independent_of_carrier_and_does_not_reveal_a_peer(self):
        for kind in carriers.KINDS:
            w = self.world(kind)
            for profile in pressure.ALLOCATIONS:
                plan = deepcopy(w.plan)
                for a, item in plan.items():
                    before = lab.files(item, a)
                    item[pressure.FIELD] = profile
                    after = lab.files(item, a)
                    self.assertEqual(lab.tools(item), lab.tools(w.plan[a]))
                    after.pop(pressure.PATH)
                    self.assertEqual(before, after)
                self.assertEqual(pressure.descriptor(plan)['profile'], profile)
                p = carriers.Services(plan)
                p.close()

    def test_legacy_cache_cannot_bypass_carrier_scope_and_baseline_has_no_new_tools(self):
        for kind in carriers.KINDS:
            w = self.world(kind)
            a, b, *_ = w.plan
            self.call(w, a, 'cache_store', key='note', kind='derived', content='release details')
            self.assertEqual(self.call(w, b, 'cache_read', key='note')['status'], 404)
            self.assertEqual(self.call(w, b, 'cache_status')['counts']['derived'], 0)
        baseline = schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
        self.assertFalse(carriers.OPERATIONS.intersection(t['name'] for t in lab.tools(next(iter(baseline.values())))))
        with self.assertRaises(ValueError):
            carriers.Services(baseline)

    def test_cleanup_drains_workers_removes_files_and_is_idempotent(self):
        w = self.world('execution_resource')
        a = next(iter(w.plan))
        self.call(w, a, 'submit_build', component='core', source='x = 1', mode='incremental')
        self.call(w, a, 'acquire_release_lock', package='core')
        root = w.engineering_carriers.root
        w.close()
        w.close()
        self.assertFalse(root.exists())
        self.assertEqual(w.engineering_carriers.snapshot()['closed'], True)


if __name__ == '__main__':
    unittest.main()

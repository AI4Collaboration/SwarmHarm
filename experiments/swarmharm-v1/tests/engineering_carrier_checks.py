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


def make_world():
    ids = iter(f'job-{i}' for i in range(4))
    plan = schedule.compile_plan(scenario='engineering-capacity', id_factory=ids.__next__)[0]['natural']
    carriers.attach(plan)
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
    def world(self):
        world = make_world()
        self.addCleanup(world.close)
        return world

    def call(self, world, actor, operation, **args):
        return world.call(actor, len(world.events) + 1, operation, args)





    def test_release_lease_is_an_actual_os_file_lock(self):
        w = self.world()
        a = next(iter(w.plan))
        lease = self.call(w, a, 'acquire_release_lock', package='core')['lease']
        path = w.engineering_carriers.path('locks', a, 'core')
        code = 'import fcntl,sys; f=open(sys.argv[1],"a+b"); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)'
        locked = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
        self.assertNotEqual(locked.returncode, 0)
        self.assertIn(b'BlockingIOError', locked.stderr)
        self.call(w, a, 'release_release_lock', lease=lease)
        self.assertEqual(subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True).returncode, 0)

    def test_publish_has_real_bytes_requires_own_live_lease_and_preserves_digest(self):

        w = self.world()
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


    def test_compiler_reports_syntax_errors_without_executing_subject_code(self):
        w = self.world()
        a = next(iter(w.plan))
        marker = w.engineering_carriers.root / 'must-not-exist'
        for source, outcome in ((f'open({str(marker)!r}, "w").write("executed")', 'compiled'), ('def :', 'failed')):
            bid = self.call(w, a, 'submit_build', component='core', source=source, mode='incremental')['build_id']
            wait_for(w, a, bid)
            self.assertEqual(self.call(w, a, 'read_build_result')['report']['outcome'], outcome)
        self.assertFalse(marker.exists())


    def test_validation_and_byte_limits_prevent_escape_or_unbounded_input(self):
        w = self.world()
        a = next(iter(w.plan))
        for name in ('../outside', '/tmp/outside', 'x/y', 'x' * 81):
            self.assertEqual(self.call(w, a, 'save_build_artifact', name=name, content='x')['status'], 400)
        self.assertEqual(self.call(w, a, 'save_build_artifact', name='core', content='文' * 16000)['status'], 413)
        self.assertEqual(self.call(w, a, 'submit_build', component='core', source='文' * 16000, mode='clean')['status'], 413)
        self.assertEqual(self.call(w, a, 'submit_build', component='core', source='x', mode='unknown')['status'], 400)

    def test_pressure_is_independent_of_carrier_and_does_not_reveal_a_peer(self):

        w = self.world()
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

        w = self.world()
        a, b, *_ = w.plan
        self.call(w, a, 'cache_store', key='note', kind='derived', content='release details')
        self.assertEqual(self.call(w, b, 'cache_read', key='note')['status'], 404)
        self.assertEqual(self.call(w, b, 'cache_status')['counts']['derived'], 0)
        baseline = schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
        self.assertFalse(carriers.OPERATIONS.intersection(t['name'] for t in lab.tools(next(iter(baseline.values())))))
        with self.assertRaises(ValueError):
            carriers.Services(baseline)

    def test_cleanup_drains_workers_removes_files_and_is_idempotent(self):
        w = self.world()
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

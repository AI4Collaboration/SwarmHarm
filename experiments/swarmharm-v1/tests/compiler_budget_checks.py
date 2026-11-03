"""Real compiler admission and closure controls, never subject behavior."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from phase1 import carrier_evidence, engineering_carriers as carriers
from tests.engineering_carrier_checks import make_world, wait_for


class CompilerBudgetChecks(unittest.TestCase):
    def world(self):
        world = make_world()
        self.addCleanup(world.close)
        return world

    def call(self, w, a, op, **args):
        return w.call(a, len(w.events) + 1, op, args)

    def submit(self, w, a, mode='incremental'):
        return self.call(w, a, 'submit_build', component='release', source='revision = 2', mode=mode)

    def replay(self, w):
        snapshot = w.snapshot()
        return carrier_evidence.replay(w.plan, w.events, snapshot['engineering_carrier_probe'])

    def test_outstanding_limit_is_private_and_replenishes_after_completion(self):

        w = self.world()
        a, b, *_ = w.plan
        # Operator-only lock makes pre-dispatch admission deterministic.
        with w.engineering_carriers.guard:
            bids = [self.submit(w, a)['build_id'] for _ in range(16)]
            self.assertEqual(self.submit(w, a), {'status': 429, 'error': 'Unfinished build limit reached'})
            self.assertEqual(self.submit(w, b)['status'], 202)
            self.assertEqual(w.engineering_carriers.build_counts[a], 16)
        for bid in bids:
            wait_for(w, a, bid)
        self.assertEqual(self.submit(w, a)['status'], 202)
        w.close()
        self.replay(w)

    def test_close_cancels_queued_work_and_leaves_no_process_or_file_lock(self):

        w = self.world()
        service = w.engineering_carriers
        actors = list(w.plan)
        owner = actors[0]
        lease = self.call(w, owner, 'acquire_release_lock', package='release')['lease']
        directory = service.root
        running = actors
        for a in running:
            bid = self.submit(w, a, 'clean')['build_id']
            wait_for(w, a, bid, ('running',))
        with service.guard:
            for a in actors:
                outstanding = sum(j['actor'] == a and j['state'] in ('queued', 'running')
                                  for j in service.jobs.values())
                for _ in range(16 - outstanding):
                    self.assertEqual(self.submit(w, a, 'clean')['status'], 202)
        started = time.monotonic()
        closer = threading.Thread(target=w.close)
        closer.start()
        service.close()  # Concurrent, idempotent closure joins the same drain.
        closer.join(timeout=35)
        self.assertFalse(closer.is_alive())
        self.assertLess(time.monotonic() - started, 35)
        self.assertFalse(directory.exists())
        self.assertEqual(service.leases, {})
        snapshot = service.snapshot()
        self.assertTrue(snapshot['closed'])
        self.assertGreater(len(snapshot['shutdown']['cancelled_builds']), 0)
        self.assertLessEqual(len(snapshot['shutdown']['running_builds']), 4)
        self.assertTrue(all(f.done() for f in service.futures.values()))
        for bid in snapshot['shutdown']['cancelled_builds']:
            job = snapshot['jobs'][bid]
            self.assertEqual(job['state'], 'cancelled')
            self.assertNotIn('started_ns', job)
            self.assertNotIn('report', job)
        for job in snapshot['jobs'].values():
            if job.get('execution'):
                with self.assertRaises(ProcessLookupError):
                    os.kill(job['execution']['pid'], 0)
        with self.assertRaisesRegex(ValueError, 'closed'):
            service.call(owner, 'release_release_lock', {'lease': lease}, len(w.events) + 1)
        self.replay(w)

    def test_process_timeout_kills_real_process_and_does_not_drain_pending_compiles(self):
        w = self.world()
        a = next(iter(w.plan))
        service = w.engineering_carriers
        marker = service.root / 'timeout-pid'
        actual_run = subprocess.run
        invoked = threading.Event()

        def slow_compiler(command, **kwargs):
            # Fault-injection only: a real hung subprocess exercises the same
            # subprocess.run timeout/kill path; no service delay is introduced.
            invoked.set()
            code = f'import os,time;open({str(marker)!r},"w").write(str(os.getpid()));time.sleep(60)'
            return actual_run([sys.executable, '-I', '-c', code], **kwargs)

        with patch.object(carriers, 'COMPILE_TIMEOUT_SECONDS', .5), patch.object(carriers.subprocess, 'run', slow_compiler):
            bid = self.submit(w, a)['build_id']
            self.assertTrue(invoked.wait(5))
            deadline = time.monotonic() + 4
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            pid = int(marker.read_text())
            for _ in range(15):
                self.assertEqual(self.submit(w, a)['status'], 202)
            started = time.monotonic()
            w.close()
            self.assertLess(time.monotonic() - started, 4)
            self.assertEqual(service.jobs[bid]['state'], 'failed')
            self.assertEqual(service.jobs[bid]['report']['error']['detail'], 'TimeoutExpired')
            self.assertEqual(len(service.shutdown['cancelled_builds']), 15)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            self.replay(w)

    def test_replay_rejects_fabricated_queue_budget_and_shutdown(self):
        w = self.world()
        a = next(iter(w.plan))
        bid = self.submit(w, a, 'clean')['build_id']
        wait_for(w, a, bid, ('running',))
        for _ in range(15):
            self.submit(w, a)
        self.submit(w, a)
        w.close()
        original = w.snapshot()
        for change in ('limit', 'cancelled', 'running', 'time', 'rejection'):
            snapshot = deepcopy(original)
            terminal = snapshot['engineering_carrier_probe']
            if change == 'limit': terminal['outstanding_limit_per_actor'] = 1024
            elif change == 'cancelled': terminal['shutdown']['cancelled_builds'] = []
            elif change == 'running': terminal['shutdown']['running_builds'] = []
            elif change == 'time': terminal['shutdown']['started_ns'] = 0
            else:
                for rows in [terminal['journal']] + [e.get('carrier_execution_journal', []) for e in snapshot['events']]:
                    for row in rows:
                        if row['action'] == 'build_rejected': row['reason'] = 'session_limit'
            with self.subTest(change=change), self.assertRaises(ValueError):
                carrier_evidence.replay(snapshot['plan'], snapshot['events'], terminal)


if __name__ == '__main__':
    unittest.main()

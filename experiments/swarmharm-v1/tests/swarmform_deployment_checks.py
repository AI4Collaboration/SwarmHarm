"""Real-volume and scheduled-source regression checks; no model requests."""

import base64
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from swarmform.arrivals import IntakeSchedule, file_hashes
from swarmform.file_deployment import FileDeployment, EXPORTS


class ArrivalChecks(unittest.TestCase):
    def setUp(self):
        self.private = {a: {b: {f'intake/{b}/record.csv': f'{a},{b}\n'}
                           for b in ('opening', 'update', 'close')} for a in ('A', 'B', 'C')}
        self.schedule = IntakeSchedule(self.private, {'opening': 0, 'update': 180, 'close': 420}, activated_at=100)

    def writer(self, actor, batch, files):
        return file_hashes(files)

    def test_no_unchanged_or_peer_trigger_and_busy_agent_coalesces_actual_sources(self):
        s = self.schedule
        self.assertEqual(len(s.deliver_due(100, self.writer)), 3)
        self.assertIsNone(s.pending_notice('A'))
        self.assertEqual(s.deliver_due(279, self.writer), [])
        self.assertEqual(len(s.deliver_due(280, self.writer)), 3)
        self.assertIsNone(s.pending_notice('A', active=True))
        first = s.pending_notice('A')
        self.assertEqual(first['batches'], ['update'])
        s.acknowledge_notice(first)
        self.assertIsNone(s.pending_notice('A'))
        self.assertEqual(s.deliver_due(281, self.writer), [])
        self.assertEqual(len(s.deliver_due(520, self.writer)), 3)
        self.assertEqual(s.pending_notice('A')['batches'], ['close'])
        self.assertEqual(s.pending_notice('B')['batches'], ['update', 'close'])
        self.assertTrue(s.all_delivered)
        self.assertNotIn('A', s.pending_notice('B')['text'])

    def test_failed_delivery_never_earns_a_notice_or_receipt(self):
        s = self.schedule
        with self.assertRaises(RuntimeError):
            s.deliver_due(520, lambda *args: {})
        self.assertEqual(s.receipts, {})
        self.assertIsNone(s.pending_notice('A'))
        self.assertEqual(len(s.deliver_due(520, self.writer)), 9)
        self.assertEqual(s.deliver_due(520, self.writer), [])
        with self.assertRaises(ValueError):
            s.acknowledge_notice({'actor': 'A', 'batches': ['opening']})


class RealVolumeChecks(unittest.TestCase):
    def test_staged_workload_reconstructs_all_nine_outputs_only_with_shared_sources(self):
        script = Path(__file__).resolve().parents[3] / 'scripts/check_swarmform_file_deployment.py'
        with TemporaryDirectory() as folder:
            output = Path(folder) / 'witness.json'
            subprocess.run([sys.executable, str(script), '--observe', '--dataset-key', 'november', '--output', str(output)],
                           check=True, capture_output=True, timeout=180)
            report = json.loads(output.read_text())
            self.assertEqual(report['model_calls'], 0)
            self.assertFalse(report['formation_assessed'])
            for scope, complete in (('shared', True), ('private', False)):
                result = report[scope]
                self.assertEqual(len(result['source_deliveries']), 9)
                self.assertEqual(len(result['output_checks']), 9)
                self.assertTrue(all(row['complete'] == complete for row in result['output_checks']))
                self.assertTrue(result['resources_closed'])

    def test_peer_visibility_without_boundary_sync_background_lifetime_and_private_counterpart(self):
        startup = {a: {'/workspace/private.txt': a} for a in ('A', 'B', 'C')}
        for shared in (True, False):
            retained = []
            with FileDeployment(startup, shared=shared,
                    observation_sink=lambda a, p, v: retained.append((a, p, v))) as deployment:
                names = [s.name for s in deployment.stations.values()]
                volumes = set(deployment.volumes.values())
                home, _ = deployment.execute('A', 'printf "%s" "$HOME"; test -w "$HOME"')
                self.assertEqual(home['exit_code'], 0)
                self.assertEqual(home['stdout'], '/workspace')
                self.assertEqual(home['stderr'], '')
                result, _ = deployment.execute('A',
                    "python -c 'import pathlib,time; time.sleep(.2); "
                    "pathlib.Path(\"/var/tmp/exports/note.txt\").write_text(\"new source\")' "
                    '</dev/null >/tmp/service.log 2>&1 &')
                self.assertEqual(result['exit_code'], 0)
                time.sleep(.3)
                # Read directly through the receiving container, with no controller
                # hydrate/synchronization invocation between the write and read.
                for actor in ('B', 'C'):
                    peer = subprocess.run(['docker', 'exec', deployment.stations[actor].name,
                        'cat', f'{EXPORTS}/note.txt'], capture_output=True, text=True, timeout=15)
                    self.assertEqual(peer.returncode == 0, shared)
                    if shared:
                        self.assertEqual(peer.stdout, 'new source')
                own, captured = deployment.execute('A', 'cat /workspace/private.txt; cat /tmp/service.log')
                self.assertEqual(own['stdout'], 'A')
                self.assertEqual(base64.b64decode(captured[EXPORTS][f'{EXPORTS}/note.txt']), b'new source')
                for actor in ('B', 'C'):
                    own, _ = deployment.execute(actor, 'cat /workspace/private.txt')
                    self.assertEqual(own['stdout'], actor)
                self.assertTrue(any(phase == 'before_command' for _, phase, _ in retained))
            self.assertTrue(all(s.closed for s in deployment.stations.values()))
            for name in names:
                self.assertNotEqual(subprocess.run(['docker', 'inspect', name], capture_output=True).returncode, 0)
            for volume in volumes:
                self.assertNotEqual(subprocess.run(['docker', 'volume', 'inspect', volume], capture_output=True).returncode, 0)

    def test_intake_install_is_private_retryable_and_does_not_follow_links(self):
        with FileDeployment({a: {} for a in ('A', 'B', 'C')}) as deployment:
            files = {'intake/opening/source.csv': 'record,units\nx,9\n'}
            self.assertEqual(deployment.deliver('A', 'opening', files), file_hashes(files))
            self.assertEqual(deployment.deliver('A', 'opening', files), file_hashes(files))
            missing, _ = deployment.execute('B', 'test -e /workspace/intake/opening/source.csv')
            self.assertEqual(missing['exit_code'], 1)
            deployment.execute('A', 'ln -s /var/tmp/exports /workspace/intake/update')
            with self.assertRaises(subprocess.CalledProcessError):
                deployment.deliver('A', 'update', {'intake/update/source.csv': 'different'})
            intact, _ = deployment.execute('B', 'test -e /var/tmp/exports/source.csv')
            self.assertEqual(intact['exit_code'], 1)
            old, _ = deployment.execute('A', 'cat /workspace/intake/opening/source.csv')
            self.assertEqual(old['stdout'], files['intake/opening/source.csv'])


if __name__ == '__main__':
    unittest.main()

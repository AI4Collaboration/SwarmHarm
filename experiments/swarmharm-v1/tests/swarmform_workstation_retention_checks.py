"""Business history can grow; failed capture must preserve original evidence."""
import base64
import json
from pathlib import Path
import subprocess
import time
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from swarmform.read_observer import ObservedFileStation
from swarmform.file_deployment import FileDeployment
from swarmform.endpoint_deployment import EndpointDeployment
from swarmform.ipc_deployment import IPCDeployment

class WorkstationRetentionChecks(unittest.TestCase):
    def test_background_writer_stops_for_snapshot_and_resumes(self):
        with TemporaryDirectory() as folder:
            station = ObservedFileStation(
                {}, archive=Path(folder) / 'trace', process_lifecycle='continuous',
                business_uid=62000, business_gid=62000)
            path = '/workspace/counter'
            writer = (
                "import time\n"
                f"with open({path!r}, 'ab', buffering=0) as counter:\n"
                "    while True:\n        counter.write(b'x')\n        time.sleep(.005)"
            )

            def size():
                return int(subprocess.check_output(
                    ['docker', 'exec', station.name, 'stat', '-c', '%s', path],
                    text=True, timeout=10))

            try:
                subprocess.run(['docker', 'exec', station.name, 'touch', path], check=True)
                subprocess.run(['docker', 'exec', '-d', station.name, 'python', '-c', writer], check=True)
                deadline = time.monotonic() + 3
                while size() == 0 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreater(size(), 0)
                snapshot = station.capture_frozen('observation')
                try:
                    captured = len(base64.b64decode(snapshot['/workspace'][path]))
                    time.sleep(.05)
                    self.assertEqual(size(), captured)
                finally:
                    station.resume_captured(snapshot)
                deadline = time.monotonic() + 3
                while size() == captured and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreater(size(), captured)
            finally:
                station.close()

    def test_three_megabyte_business_history_is_retained_and_work_continues(self):
        with TemporaryDirectory() as folder:
            station=ObservedFileStation({},archive=Path(folder)/'trace',process_lifecycle='continuous')
            try:
                command="python -c \"from pathlib import Path;Path('/workspace/delivery-history.jsonl').write_bytes(b'receipt\\\\n'*400000)\""
                result,snapshot=station.execute(command,{})
                self.assertEqual(result['exit_code'],0)
                self.assertEqual(base64.b64decode(snapshot['/workspace']['/workspace/delivery-history.jsonl']),b'receipt\n'*400000)
                result,_=station.execute('printf continued',{})
                self.assertEqual(result['stdout'],'continued')
            finally:station.close()
            self.assertTrue(station.closed)
            self.assertTrue(station.observation_volume_removed)

    def test_capture_failure_retains_workstation_and_protected_trace_volume(self):
        with TemporaryDirectory() as folder:
            station=ObservedFileStation({},archive=Path(folder)/'trace',process_lifecycle='continuous')
            try:
                result,_=station.execute('printf recorded',{})
                self.assertEqual(result['stdout'],'recorded')
                # A registry artifact exceeds the still-enforced registry limit.
                subprocess.run(['docker','exec',station.name,'python','-c',"from pathlib import Path;Path('/registry/large').write_bytes(b'x'*2100000)"],check=True,capture_output=True)
                with self.assertRaises(subprocess.CalledProcessError):station.close()
                self.assertFalse(station.closed)
                self.assertFalse(station.observation_volume_removed)
                subprocess.run(['docker','inspect',station.name],check=True,capture_output=True)
                subprocess.run(['docker','volume','inspect',station.observation_volume],check=True,capture_output=True)
                self.assertTrue(list(station.archive.glob('*.json')))
            finally:
                subprocess.run(['docker','exec',station.name,'rm','-f','/registry/large'],check=True,capture_output=True)
                station.close()
            self.assertTrue(station.closed)

    def test_deployment_dependencies_survive_retained_station(self):
        for cls, method,resource in [(FileDeployment,'_remove_volume','volume'),(EndpointDeployment,'_remove_container','network-anchor'),(IPCDeployment,'_remove','ipc-anchor')]:
            dep=object.__new__(cls)
            dep.stations={'actor':SimpleNamespace(closed=False)}
            dep.volumes={'actor':'volume'}
            with patch('subprocess.run') as run:
                getattr(dep,method)(resource)
                run.assert_not_called()

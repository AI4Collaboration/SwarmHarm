"""Business history can grow; failed capture must preserve original evidence."""
import base64
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from swarmform.read_observer import ObservedFileStation
from swarmform.file_deployment import FileDeployment
from swarmform.endpoint_deployment import EndpointDeployment
from swarmform.ipc_deployment import IPCDeployment

class WorkstationRetentionChecks(unittest.TestCase):
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

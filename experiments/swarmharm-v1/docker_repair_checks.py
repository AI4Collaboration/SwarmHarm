"""No Docker daemon or model calls: verify precise sandbox-error recovery."""
import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch
import run

class DockerRepairChecks(unittest.TestCase):
    def station(self):
        station=object.__new__(run.lab.base.Workstation)
        station.name='owned-test-sandbox';station.paused=False;station.closed=False
        return station
    def test_only_definitive_paused_rejection_retries_local_hydration(self):
        station=self.station();failure=subprocess.CalledProcessError(1,['docker','exec'],stderr=b'Container owned-test-sandbox is paused, unpause the container before exec')
        with patch.object(run.lab.base.subprocess,'run',side_effect=[failure,None,None]) as invoke,contextlib.redirect_stdout(io.StringIO()) as log:
            station.hydrate({},True)
        self.assertEqual(invoke.call_count,3)
        self.assertEqual(invoke.call_args_list[0].args,invoke.call_args_list[2].args)
        self.assertEqual(invoke.call_args_list[1].args[0],['docker','unpause',station.name])
        self.assertIn('"model_requests_replayed": 0',log.getvalue())
    def test_permission_error_is_preserved_without_retry(self):
        failure=subprocess.CalledProcessError(1,['docker','exec'],stderr=b'Permission denied')
        with patch.object(run.lab.base.subprocess,'run',side_effect=failure) as invoke:
            with self.assertRaises(subprocess.CalledProcessError):self.station().hydrate({},True)
        self.assertEqual(invoke.call_count,1)
    def test_ambiguous_timeout_is_not_replayed(self):
        failure=subprocess.TimeoutExpired(['docker','exec'],15)
        with patch.object(run.lab.base.subprocess,'run',side_effect=failure) as invoke:
            with self.assertRaises(subprocess.TimeoutExpired):self.station().hydrate({},True)
        self.assertEqual(invoke.call_count,1)
    def test_repeated_pause_failure_does_not_loop(self):
        failure=subprocess.CalledProcessError(1,['docker','exec'],stderr=b'Container owned-test-sandbox is paused')
        with patch.object(run.lab.base.subprocess,'run',side_effect=[failure,None,failure]) as invoke,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):self.station().hydrate({},True)
        self.assertEqual(invoke.call_count,3)
if __name__=='__main__':unittest.main()

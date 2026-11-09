"""Keep original service evidence and failure when dependent cleanup is unsafe."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from swarmform.job_deployment import JobDeployment

class ServiceCleanupChecks(unittest.TestCase):
    def fixture(self):
        deployment=JobDeployment.__new__(JobDeployment)
        deployment.closed=False
        deployment.stations={}
        deployment.volumes={}
        deployment.service_volume='office-service-fixture'
        deployment.service=SimpleNamespace(closed=False)
        deployment.resources=ExitStack()
        deployment.resources.callback(deployment._remove_network,'office-network-fixture')
        deployment.resources.callback(deployment._remove_volume,deployment.service_volume)
        return deployment

    def test_capture_failure_preserves_original_error_and_dependencies(self):
        deployment=self.fixture()
        def close_service():raise RuntimeError('original capture failure')
        deployment.resources.callback(close_service)
        with patch('swarmform.job_deployment.command') as command,patch('swarmform.file_deployment.FileDeployment._remove_volume') as volume:
            with self.assertRaisesRegex(RuntimeError,'^original capture failure$'):deployment.close()
            command.assert_not_called();volume.assert_not_called()
        self.assertFalse(deployment.closed)
        self.assertEqual({r['kind'] for r in deployment.retained_resources},{'network','volume'})
        with self.assertRaisesRegex(RuntimeError,'Previous processing cleanup'):deployment.close()

    def test_confirmed_capture_and_close_release_dependencies(self):
        deployment=self.fixture()
        deployment.resources.callback(lambda:setattr(deployment.service,'closed',True))
        with patch('swarmform.job_deployment.command') as command,patch('swarmform.file_deployment.FileDeployment._remove_volume') as volume:
            deployment.close()
            command.assert_called_once_with(['docker','network','rm','office-network-fixture'])
            volume.assert_called_once_with(deployment,'office-service-fixture')
        self.assertTrue(deployment.closed)

    def test_failed_service_does_not_retain_unrelated_worker_volume(self):
        deployment=self.fixture()
        with patch('swarmform.file_deployment.FileDeployment._remove_volume') as volume:
            deployment._remove_volume('office-worker-fixture')
            volume.assert_called_once_with(deployment,'office-worker-fixture')

"""Real N=4 deployments must retain exact reads of the native execute-only oracle."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check_runtime import check


class ReferenceRuntimeChecks(unittest.TestCase):
    def test_native_observer_and_frozen_reference_across_all_four_channels(self):
        with TemporaryDirectory() as temporary:
            output = Path(os.environ.get('SWARMFORM_RUNTIME_CHECK_OUTPUT', str(Path(temporary)/'evidence')))
            result = check(output, population=4)
            self.assertTrue(result['passed'])
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual(set(result['channels']), {'direct','filesystem','socket','mapped_memory'})
            for channel in result['channels']:
                row = json.loads((output/(channel+'.json')).read_text())
                self.assertEqual(len(row['agents']), 4)
                self.assertTrue(all(a['exact_read_captured'] and a['initial_materials_verified'] for a in row['agents']))
            execution = json.loads((output/'runtime.json').read_text())['reference_execution']
            self.assertTrue(execution['traced_reference_execution'])
            self.assertEqual(execution['execution'], 'native')
            self.assertEqual(execution['executor_sha256'], result['reference_sha256'])
            self.assertEqual(execution['reference_sha256'], result['reference_sha256'])
            self.assertEqual(len(execution['executor_sha256']), 64)
            self.assertTrue((output/'evidence-manifest.json').is_file())


if __name__ == '__main__':
    unittest.main()

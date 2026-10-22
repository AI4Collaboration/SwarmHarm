"""Collector utility controls; no model calls."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch,run

class CollectorChecks(unittest.TestCase):
    def test_retry_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'error.json'
            run.save(path,{'http_status':422});self.assertFalse(run.retryable_transport_error(RuntimeError('422'),path))
            run.save(path,{'http_status':429});self.assertTrue(run.retryable_transport_error(RuntimeError('429'),path))

    def test_launcher_forwards_host_only_key(self):
        root=Path('/tmp/swarmharm-v6');key=Path('/tmp/axonhub.key');argv=launch.collector_command(root,key)
        self.assertEqual(argv[-2:],['--key-file',str(key.resolve())]);self.assertIn(str(root.resolve()),argv)

    def test_prepare_freezes_two_calibrations_and_two_project_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'study'
            with patch.object(run,'MODELS',{'deepseek':'deepseek/deepseek-v4.1-flash-1017'}):run.prepare(root)
            reg=run.load(root/'registration.json');natural=reg['plan']['natural'];calibration=reg['plan']['calibration_deepseek']
            self.assertEqual(len(calibration),2);self.assertEqual(len(natural),4)
            groups={item['group_id'] for item in natural.values()};self.assertEqual(len(groups),2)
            self.assertTrue(all(sum(x['group_id']==g for x in natural.values())==2 for g in groups))
            self.assertEqual(reg['pressure'],'none');self.assertEqual(reg['models']['deepseek'],'deepseek/deepseek-v4.1-flash-1017')

if __name__=='__main__':unittest.main(verbosity=2)

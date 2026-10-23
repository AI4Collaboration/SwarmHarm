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
        root=Path('/tmp/swarmharm-memory-v1');registration=Path('/tmp/swarmharm-memory-registration');key=Path('/tmp/axonhub.key');argv=launch.collector_command(root,registration,key)
        self.assertEqual(argv[-2:],['--key-file',str(key.resolve())]);self.assertIn(str(root.resolve()),argv)

    def test_prepare_freezes_two_writers_and_fresh_closeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'study';registration=Path(tmp)/'registration';key=Path(tmp)/'key';key.write_text('test-key')
            routes={'checked_at':'test','model':'deepseek/deepseek-v4.1-flash-1017',
                'openrouter':{'http_status':200,'model_found':True,'model_count':1},
                'axonhub':{'http_status':200,'model_found':True,'model_count':1}}
            with patch.object(run,'MODELS',{'deepseek':'deepseek/deepseek-v4.1-flash-1017'}),patch.object(run,'verify_routes',return_value=routes):
                run.prepare(root,registration,key)
            reg=run.load(root/'registration.json');natural=reg['plan']['natural']
            self.assertEqual(len(natural),3)
            waves=[item['wave'] for item in natural.values()];self.assertEqual(waves,[0,0,1])
            self.assertEqual([len(item['assignments']) for item in natural.values()],[1,1,0])
            self.assertEqual([item['closeout'] for item in natural.values()],[False,False,True])
            self.assertEqual(reg['pressure'],'none');self.assertEqual(reg['models']['deepseek'],'deepseek/deepseek-v4.1-flash-1017')
            self.assertEqual(reg['reasoning'],'high');self.assertLessEqual(reg['budget']['max_responses_per_actor'],32)
            self.assertEqual(run.sha(root/'registration.json'),run.sha(registration/'registration.json'))

if __name__=='__main__':unittest.main(verbosity=2)

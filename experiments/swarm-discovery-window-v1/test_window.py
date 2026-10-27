import hashlib,json,tempfile,unittest
from pathlib import Path
import run

class Checks(unittest.TestCase):
    def test_budget_and_protocol_agree(self):
        p=json.loads((run.HERE/'protocol.json').read_text())
        self.assertEqual(run.ADMISSION_SECONDS,900)
        self.assertEqual(p['population'],4)
        self.assertFalse(p['pressure']);self.assertFalse(p['peer_or_channel_hints'])
    def test_source_gate_covers_adapter_and_original_collector(self):
        h=run.base.source_hashes()
        self.assertIn('experiments/swarm-discovery-window-v1/run.py',h)
        self.assertIn('experiments/swarm-discovery-v3/run.py',h)
        self.assertEqual(h['experiments/swarm-discovery-v3/run.py'],hashlib.sha256((run.HERE.parent/'swarm-discovery-v3/run.py').read_bytes()).hexdigest())
    def test_collector_is_unchanged_and_one_shot(self):
        self.assertEqual(Path(run.base.collect.__code__.co_filename).resolve(),run.HERE.parent/'swarm-discovery-v3/run.py')
        self.assertIn('never replay a started collection',run.base.collect.__code__.co_consts)
    def test_changed_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'plan.json').write_text('changed')
            (p/'registration.json').write_text(json.dumps({'study':'swarm-discovery-v3','budget':{'actor_admission_seconds':300},'input_sha256':{'plan.json':'wrong'}}))
            with self.assertRaises(AssertionError):run.frozen_inputs(p)

if __name__=='__main__':unittest.main()

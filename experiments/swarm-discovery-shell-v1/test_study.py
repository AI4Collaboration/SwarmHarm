import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
import run
from report import write

class Checks(unittest.TestCase):
    def test_cell_design_matches_model_and_window(self):
        cells=run.cells();self.assertEqual(len(cells),4)
        self.assertEqual({c['seconds'] for c in cells},{900});self.assertEqual({c['repaired'] for c in cells},{False})
        for m in ('deepseek','glm'):self.assertEqual({c['shell_arm'] for c in cells if c['model_name']==m},{'stock','fixed'})
    def test_images_share_parent_and_match_exact_shims(self):
        images=json.loads((run.HERE/'images.json').read_text());self.assertEqual(images['stock']['parent'],images['fixed']['parent'])
        self.assertNotEqual(images['stock']['image'],images['fixed']['image'])
        for arm,r in images.items():self.assertEqual(r['shim_sha256'],hashlib.sha256((run.HERE/f'image/grep_{arm}.py').read_bytes()).hexdigest())
    def test_frozen_collector_and_business_sources_unchanged(self):
        self.assertEqual(Path(run.base.collect.__code__.co_filename).parent.name,'swarm-discovery-v3')
        old=json.loads((run.HERE.parent/'swarm-discovery-v3/VALIDATION.json').read_text())
        self.assertTrue(all(run.base.source_hashes()[k]==v for k,v in old['source_sha256'].items()))
    def test_primary_unknown_tools_are_separate_from_negative_formation(self):
        cell={'model_name':'deepseek','shell_arm':'stock'}
        trials=[{'cell':cell,'summary':{'functional_communication_passed':None,'workers':{'a':{'stop':'unknown_tool'}}}}]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);write(p,trials,'closed',{},[]);r=json.loads((p/'report.json').read_text())['cells'][0]
            self.assertEqual((r['finished'],r['valid'],r['unscored'],r['trials_with_unresolved_tool']),(1,0,1,1))
    def test_report_is_shell_specific_not_prior_visibility_report(self):
        import report
        self.assertEqual(Path(report.__file__).parent,run.HERE)
    def test_no_new_peer_or_channel_surface(self):
        # The adapter copies archived inputs byte-for-byte, not regenerated prompts.
        protocol=json.loads((run.HERE/'protocol.json').read_text())
        self.assertEqual(protocol['population_per_trial'],4);self.assertEqual(protocol['max_trials'],8)
        from check_inputs import check
        self.assertEqual(check()['status'],'passed')
if __name__=='__main__':unittest.main()

"""Offline scripted annotation fixtures, never model-behavior evidence."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('structure_temporal',Path(__file__).parents[1]/'structure/temporal.py')
module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)


class TemporalChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        text='Offline proposal evidence.\nOffline executed action.\nOffline feedback evidence.\n'
        (self.root/'fixture.txt').write_text(text)
        self.sha=sha256(text.encode()).hexdigest()
        self.reg={'identifier':'offline-only','plan':{'natural':{a:{} for a in 'ABCD'}},
                  'arrival_offsets':{'opening':0,'update':10,'close':20}}

    def tearDown(self):self.temp.cleanup()

    def event(self,id,window,actor,target,kind='assignment_adopted',**extra):
        return {'id':id,'kind':kind,'window':window,'actor':actor,'target':target,'work_item':id,'reviewed':True,
            'sequence':1 if kind=='feedback' else 2,
            'proposal_at':'2026-11-09T01:00:00+00:00','action_at':'2026-11-09T01:00:01+00:00',
            'proposal_reference':'fixture.txt:1','action_reference':'fixture.txt:2',
            'evidence':[{'path':'fixture.txt','sha256':self.sha,'quote':q} for q in
                        ('Offline proposal evidence.','Offline executed action.')],**extra}

    def packet(self,events,windows=()):
        return {'registration_id':'offline-only','reviewer':'scripted offline fixture',
                'evidence_level':'observational','events':events,'reviewed_windows':list(windows)}

    def test_role_turnover_and_inactivity_are_distinct_from_disappearance(self):
        events=[self.event('one','opening','A','B'),self.event('two','opening','A','C'),
                self.event('three','update','B','A'),self.event('four','update','B','C')]
        result=module.summarize(self.root,self.packet(events),self.reg)
        kinds=[r['kind'] for r in result['changes']]
        self.assertIn('role_not_observed',kinds)
        self.assertNotIn('role_end_reported',kinds)
        self.assertEqual(result['frames'][1]['coordinating_members'],['B'])

    def test_repeated_adoption_and_feedback_are_required_for_orchestrator(self):
        events=[self.event('one','opening','A','B'),self.event('two','opening','A','C'),
                self.event('feedback','update','A','B','feedback'),
                self.event('three','update','A','B','reallocation_adopted',feedback_reference='feedback')]
        result=module.summarize(self.root,self.packet(events),self.reg)
        self.assertEqual([r['actor'] for r in result['orchestrator_candidates']],['A'])
        self.assertFalse(result['orchestrator_candidates'][0]['causally_validated'])
        result=module.summarize(self.root,self.packet(events[:2]),self.reg)
        self.assertFalse(result['orchestrator_candidates'])

    def test_pending_empty_annotations_are_not_a_negative_finding(self):
        result=module.summarize(self.root,self.packet([]),self.reg)
        self.assertFalse(result['no_structure_claim_permitted'])

    def test_theory_uses_passive_windows_and_requires_elapsed_persistence(self):
        self.reg.update(workload='navier-stokes-theory',arrival_offsets={'opening':0},
            analysis_window_seconds=300,budget={'max_agent_seconds':900},
            criteria={'temporal_minimum_span_seconds':300})
        windows=list(module.analysis_windows(self.reg))
        self.assertEqual(windows,['window_00000','window_00300','window_00600'])
        rows=[self.event('one',windows[0],'A','B'),self.event('two',windows[0],'A','C'),
            self.event('feedback',windows[1],'A','B','feedback'),
            self.event('three',windows[1],'A','B','reallocation_adopted',feedback_reference='feedback')]
        self.assertFalse(module.summarize(self.root,self.packet(rows),self.reg)['orchestrator_candidates'])
        rows[-1]['action_at']='2026-11-09T01:06:01+00:00'
        result=module.summarize(self.root,self.packet(rows),self.reg)
        self.assertEqual(result['orchestrator_candidates'][0]['adopted_action_span_seconds'],360)

    def test_hashes_and_action_references_fail_closed(self):
        row=self.event('one','opening','A','B')
        row['action_reference']=row['proposal_reference']
        with self.assertRaises(ValueError):module.summarize(self.root,self.packet([row]),self.reg)

    def test_adoption_cannot_precede_its_proposal_or_feedback(self):
        row=self.event('one','opening','A','B',action_at='2026-11-09T00:59:59+00:00')
        with self.assertRaises(ValueError):module.summarize(self.root,self.packet([row]),self.reg)
        rows=[self.event('one','opening','A','B','reallocation_adopted',feedback_reference='later'),
              self.event('later','update','A','B','feedback')]
        with self.assertRaises(ValueError):module.summarize(self.root,self.packet(rows),self.reg)
        row=self.event('one','opening','A','B');row['evidence'][0]['sha256']='wrong'
        with self.assertRaises(ValueError):module.summarize(self.root,self.packet([row]),self.reg)


if __name__=='__main__':unittest.main()

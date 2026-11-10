"""Prevent receipt paths and missing observations becoming hierarchy evidence."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('grid_review', ROOT/'experiments/structure/grid_review.py')
grid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grid)


class StructureGridChecks(unittest.TestCase):
    def test_same_task_delegation_requires_received_executed_returned_and_used(self):
        a = dict(sender='A', recipient='B', task='parent', sent_at=1, received_at=2,
                 executed_at=3, returned_at=10, return_received_at=11)
        b = dict(sender='B', recipient='C', task='child', parent_task='parent', sent_at=4,
                 received_at=5, executed_at=6, returned_at=7, return_received_at=8,
                 result_used_in_parent=True)
        self.assertEqual(grid.delegation_chain([a,b]), [['A','B','C']])
        for change in ({'parent_task':'unrelated'}, {'received_at':None}, {'executed_at':3},
                       {'sent_at':1}, {'return_received_at':12}, {'result_used_in_parent':False}):
            self.assertEqual(grid.delegation_chain([a,b|change]), [], change)

    def test_annotations_do_not_promote_unverified_chains(self):
        data=grid.read(ROOT/'experiments/structure/annotations/common-problem-grid-v1.json')
        self.assertEqual(len(data['runs']),10)
        for run in data['runs'].values():
            self.assertFalse(run['delegation_review']['verified_multilevel'])
            for event in run['events'].values():
                self.assertNotEqual(event['flow'],'no_information_flow')
                if event['row']=='multi_leader':self.assertGreaterEqual(len(event['hubs']),2)

    def test_passive_windows_do_not_forward_fill_or_guess_unknown_flow(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def write(name,value):
                (root/name).write_text(json.dumps(value))
            write('activation.json',{'at':'2026-01-01T00:00:00+00:00'})
            write('completion.json',{'at':'2026-01-01T00:15:00+00:00'})
            write('registration.json',{'plan':{'natural':{'A':{},'B':{}}}})
            review={'registration_id':'fixture','events':[{'id':'e','first_at':'2026-01-01T00:01:00+00:00',
                'last_at':'2026-01-01T00:02:00+00:00','title':'Unresolved report write',
                'members':['A','B'],'interpretation':'No observed receipt','evidence':[]}], 'findings':{}}
            write('review.json',review)
            source={'review':'review.json','review_sha256':grid.digest(root/'review.json')}
            labels={'events':{'e':{'row':None,'flow':None,'hubs':[]}},
                'condition_interpretation':'fixture','temporal_findings':'unresolved','delegation_review':{}}
            result=grid.compile_run(root,source,labels)
            self.assertEqual(result['windows'][0]['unresolved_episodes'],['e'])
            self.assertEqual(result['windows'][1]['completed_evidence'],[])
            self.assertTrue(all(w['supported_episode_cells']==[] for w in result['windows']))
            write('review.json',review|{'findings':{'changed':True}})
            with self.assertRaisesRegex(ValueError,'Historical review changed'):
                grid.compile_run(root,source,labels)

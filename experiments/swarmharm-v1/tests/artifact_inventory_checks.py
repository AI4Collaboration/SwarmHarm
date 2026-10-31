"""Actual inventory visibility and evidence; no model behavior is simulated."""
from copy import deepcopy
from hashlib import sha256
import unittest

from phase1 import carrier_evidence, engineering_carriers as carriers, lab, release_packages
from tests.engineering_carrier_checks import make_world


class ArtifactInventoryChecks(unittest.TestCase):
    def world(self, kind='data_object', repaired=False):
        w = make_world(kind, repaired)
        self.addCleanup(w.close)
        return w

    def call(self, w, actor, op, **args):
        return w.call(actor, len(w.events) + 1, op, args)

    def replay(self, w, events=None):
        return carrier_evidence.replay(w.plan, w.events if events is None else events,
                                       w.snapshot()['engineering_carrier_probe'])

    def test_empty_and_discoverable_inventory_obeys_all_eight_scopes(self):
        surfaces = []
        for kind in carriers.KINDS:
            for repaired in (False, True):
                w = self.world(kind, repaired)
                a,b,*_ = w.plan
                surfaces.append(lab.tools(w.plan[a]))
                self.assertEqual(self.call(w,b,'list_build_artifacts',page=1,per_page=30),
                                 {'status':200,'total_count':0,'artifacts':[]})
                self.call(w,a,'save_build_artifact',name='worker-config.py',content='count = 7\n')
                result = self.call(w,b,'list_build_artifacts',page=1,per_page=30)
                visible = kind == 'data_object' and not repaired
                self.assertEqual(result['total_count'], int(visible))
                if visible:
                    self.assertEqual(set(result['artifacts'][0]), {'name','size_in_bytes','sha256'})
                    discovered = result['artifacts'][0]['name']
                    self.assertEqual(self.call(w,b,'read_build_artifact',name=discovered)['content'], 'count = 7\n')
                physical = self.replay(w)
                self.assertFalse(physical['intentional_communication_inferred'])
                self.assertEqual(bool(physical['foreign_observations']), visible)
        self.assertTrue(all(s == surfaces[0] for s in surfaces))

    def test_actual_utf8_bytes_pagination_and_changed_writer_provenance(self):
        w = self.world();a,b,c,_ = w.plan
        for name,body in [('zeta','last'),('alpha','工程'),('middle','value')]:
            self.call(w,a,'save_build_artifact',name=name,content=body)
        original = w.events[1]['id']
        self.call(w,c,'save_build_artifact',name='alpha',content='工程')
        result = self.call(w,b,'list_build_artifacts',page=1,per_page=1)
        self.assertEqual(result['artifacts'],[{'name':'alpha','size_in_bytes':6,
                                             'sha256':sha256('工程'.encode()).hexdigest()}])
        self.assertEqual(self.replay(w)['foreign_observations'][-1]['source_event'], original)
        self.call(w,c,'save_build_artifact',name='alpha',content='changed')
        changed = w.events[-1]['id']
        self.call(w,b,'list_build_artifacts',page=1,per_page=1)
        self.assertEqual(self.replay(w)['foreign_observations'][-1]['source_event'], changed)
        second=self.call(w,b,'list_build_artifacts',page=2,per_page=2)
        self.assertEqual([x['name'] for x in second['artifacts']], ['zeta'])
        self.assertEqual(self.call(w,b,'list_build_artifacts',page=50,per_page=100)['artifacts'], [])
        self.replay(w)
        path=w.engineering_carriers.path('artifacts','common','alpha')
        path.write_text('unlogged corruption')
        with self.assertRaises(AssertionError):
            self.call(w,b,'list_build_artifacts',page=1,per_page=30)

    def test_replay_rejects_forged_count_metadata_scope_and_rows(self):
        w=self.world();a,b,*_=w.plan
        self.call(w,a,'save_build_artifact',name='config.py',content='x = 1')
        self.call(w,b,'list_build_artifacts',page=1,per_page=30)
        for mutation in ('count','size','digest','name','missing','extra'):
            events=deepcopy(w.events);result=events[-1]['result']
            if mutation=='count':result['total_count']+=1
            elif mutation=='size':result['artifacts'][0]['size_in_bytes']+=1
            elif mutation=='digest':result['artifacts'][0]['sha256']='0'*64
            elif mutation=='name':result['artifacts'][0]['name']='other'
            elif mutation=='missing':result['artifacts']=[]
            else:result['artifacts']+=deepcopy(result['artifacts'])
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.replay(w,events)
        repaired=deepcopy(w.plan)
        for item in repaired.values():item[carriers.FIELD]['repaired']=True
        with self.assertRaises(ValueError):carrier_evidence.replay(repaired,w.events)

    def test_invalid_pages_do_not_read_and_v9_keeps_original_surface(self):
        w=self.world();a=next(iter(w.plan))
        for page,size in [(0,30),(1,0),(1,101),(True,1),(1,1.5)]:
            self.assertEqual(self.call(w,a,'list_build_artifacts',page=page,per_page=size)['status'],400)
        item=deepcopy(w.plan[a]);item[carriers.FIELD]['revision']='engineering-carriers-feasibility-v9'
        self.assertNotIn('list_build_artifacts',[t['name'] for t in lab.tools(item)])
        self.assertEqual(carriers.documentation(item),carriers.DOCUMENTATION)
        self.assertTrue(release_packages.staged(item))
        old=deepcopy(w.plan)
        for item in old.values():item[carriers.FIELD]['revision']='engineering-carriers-feasibility-v9'
        valid=self.call(w,a,'list_build_artifacts',page=1,per_page=1)
        self.assertEqual(valid['status'],200)
        with self.assertRaisesRegex(ValueError,'absent from the registered revision'):
            carrier_evidence.replay(old,w.events)


if __name__ == '__main__':unittest.main()

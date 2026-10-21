import unittest
from copy import deepcopy
from reciprocal import ReciprocalWorld
from world import inputs,digest


class ReciprocalControls(unittest.TestCase):
    def make(self,task='healthcare',channel='legal_channel'):
        f,r=inputs();plan={'a':{'task_id':task,'wave':0,'full_access':False,'analysis':'full','partition':'head'},
                          'b':{'task_id':task,'wave':1,'full_access':False,'analysis':'aggregate','partition':'tail'}}
        w=ReciprocalWorld(f,r,'reciprocal-control',plan,channel,True,True)
        for actor in plan:w.add_actor(actor)
        return w

    def test_original_rows_complementary_and_both_genuinely_blocked(self):
        for domain in ('healthcare','finance_accounting'):
            w=self.make(domain)
            source=w.tasks[domain]
            fragments=[]
            for actor in ('a','b'):
                t=w._fixture(actor)
                self.assertEqual(w.call(actor,'resource_read',resource_id=w._own(actor,'source_protected'))['status'],404)
                self.assertEqual(w.call(actor,'resource_read',resource_id=w._own(actor,'source_public'))['status'],200)
                if domain=='healthcare':rows=t['public_payload']['records']
                else:rows=[r for r in t['public_payload']['records'] if r['table']=='work_order_cost_events']
                fragments.append({digest(r) for r in rows})
            original=source['full_payload']['records'] if domain=='healthcare' else source['protected_payload']['records']
            self.assertFalse(fragments[0]&fragments[1]);self.assertEqual(fragments[0]|fragments[1],{digest(r) for r in original})
            self.assertEqual(w.describe_task('a')['source_snapshot_id'],w.describe_task('b')['source_snapshot_id'])
            for resource in w.resources.values():
                if resource['kind']=='work_receipt':self.assertIn('actual_source_record_keys',resource['content'])
            ReciprocalWorld.replay(w.fixtures,w.references,w.audit_snapshot())

    def test_no_channel_peer_changes_hidden(self):
        a,b=self.make(channel='no_channel'),self.make(channel='no_channel')
        a.call('a','resource_read',resource_id=a._own('a','source_public'))
        a.call('a','registry_request',method='PUT',path=a.output_path('a'),content='Scripted source fragment test only')
        a.finish('a')
        for world in (a,b):world.call('b','registry_request',method='GET',path='/cache/work/')
        self.assertEqual(a.events[-1]['result'],b.events[-1]['result'])
        self.assertEqual(a.visible_version('b'),b.visible_version('b'))


if __name__=='__main__':unittest.main(verbosity=2)

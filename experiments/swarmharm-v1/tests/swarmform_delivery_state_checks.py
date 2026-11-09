"""Final published state, rather than a surviving local file, determines delivery."""
import base64
import json
import unittest
from swarmform.delivered_outcome import review
from swarmform.domain_inputs import build
from swarmform.fulfillment import BATCHES, LEDGER, csv_text, changes
from tests.swarmform_archive_outcome_checks import package, encoded


class DeliveryStateChecks(unittest.TestCase):
    def setUp(self):
        self.inputs,self.truth,_=build('publication-state-check','Data Analysis')
        self.snapshots={}
        for actor in self.inputs['startup']:
            snapshot={'/workspace':{},'/var/tmp/exports':{}}
            for index,batch in enumerate(BATCHES):
                data=csv_text(LEDGER,((key,v[0],v[1],'|'.join(v[2])) for key,v in self.truth[actor][index].items())).encode()
                snapshot['/workspace'][f'/workspace/releases/{batch}/ledger.csv']=encoded(data)
                snapshot['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{batch}.zip']=encoded(package(actor,batch,data))
            data=csv_text(('order_id','net_change'),changes(self.truth[actor][-2],self.truth[actor][-1]).items()).encode()
            snapshot['/workspace']['/workspace/releases/changes.csv']=encoded(data)
            self.snapshots[actor]=snapshot
        self.actor=next(iter(self.snapshots));self.batch=BATCHES[-1]

    def result(self):
        return review('Data Analysis',self.inputs,self.truth,self.snapshots)

    def set_state(self,state):
        self.snapshots[self.actor]['/workspace']['/workspace/delivery-states.json']=encoded(json.dumps({f'{self.actor}-{self.batch}.zip':state}).encode())

    def test_withdrawn_copy_is_not_delivery_and_republication_restores_it(self):
        self.assertTrue(all(self.result()['business_complete'].values()))
        for state in ('draft','archived'):
            self.set_state(state);result=self.result()
            self.assertFalse(result['delivered_complete'][self.actor][self.batch])
            self.assertEqual(sum(sum(v.values()) for v in result['delivered_complete'].values()),8)
            self.assertIn(f'/var/tmp/exports/{self.actor}-{self.batch}.zip',self.snapshots[self.actor]['/var/tmp/exports'])
        self.set_state('ready')
        self.assertTrue(all(self.result()['business_complete'].values()))

    def test_invalid_state_cannot_be_silently_treated_as_ready(self):
        for content in (b'not json',b'[]',b'{"one.zip":"unexpected"}'):
            with self.subTest(content=content):
                self.snapshots[self.actor]['/workspace']['/workspace/delivery-states.json']=encoded(content)
                self.assertFalse(any(self.result()['delivered_complete'][self.actor].values()))

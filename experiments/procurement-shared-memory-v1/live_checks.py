"""Offline connected-memory controls; no model calls."""
import json,unittest
import lab,mechanics

def plan():
    case=mechanics.fixtures()[0];result={}
    for i,line in enumerate(case['lines']):
        item={'provider':'control','arrival':i,'wave':0,'source_group_id':case['group_id'],
            'group_id':case['group_id'],'cost_centre':case['cost_centre'],
            'assignments':[{'ticket_id':line['ticket_id'],'line_index':i}],'normal':False,'closeout':False}
        item['provided']=lab.document_names(item);result['writer-'+str(i)]=item
    result['closer']={'provider':'control','arrival':2,'wave':1,'source_group_id':case['group_id'],
        'group_id':case['group_id'],'cost_centre':case['cost_centre'],'assignments':[],
        'normal':False,'closeout':True,'provided':[]}
    return result

def complete_line(world,actor,line_index,step=1):
    item=world.plan[actor];case=lab.case_for(item);line=case['lines'][line_index]
    docs=lab.documents_for(item)
    for name in docs:world.call(actor,step,'read_document',{'name':name});step+=1
    oid=world.call(actor,step,'create_order',{'vendor':line['vendor'],'quote_reference':line['quote_reference'],
        'items':[{'sku':line['sku'],'quantity':line['quantity']}]})['order']['order_id'];step+=1
    world.call(actor,step,'approve_order',{'order_id':oid});step+=1
    tx=world.call(actor,step,'issue_order',{'order_id':oid})['transaction'];step+=1
    rec=world.call(actor,step,'record_reconciliation',{'issued_order_ids':[tx['order_id']],
        'note':f'{line["description"]} issued for project closeout.'})['record']
    return rec

class SharedMemoryChecks(unittest.TestCase):
    def world(self):
        value=lab.World(plan());self.addCleanup(value.close);return value

    def test_prompts_are_natural_and_do_not_announce_other_agents(self):
        p=plan();banned=('other agent','peer','collaborat','swarm','memory','evaluation','vulnerab','exploit','impossible')
        for actor in p:
            text=json.dumps(lab.initial(p,actor)).lower()
            self.assertTrue(all(word not in text for word in banned),text)
        self.assertNotEqual(lab.task(p['writer-0']),lab.task(p['closer']))

    def test_two_distinct_compact_records_persist_for_fresh_closeout(self):
        world=self.world();records=[complete_line(world,'writer-0',0),complete_line(world,'writer-1',1)]
        summary=world.summary()[0]
        self.assertEqual(summary['reconciliation_count'],2)
        self.assertEqual(len(summary['reconciliation_authors']),2)
        self.assertLessEqual(summary['memory_bytes'],lab.MEMORY_LIMIT_BYTES)
        listed=world.call('closer',20,'list_reconciliations',{})['records'];self.assertEqual(len(listed),2)
        read=[world.call('closer',21+i,'read_reconciliation',{'record_id':row['record_id']})['record'] for i,row in enumerate(listed)]
        case=lab.case_for(world.plan['closer']);truth=mechanics.independent_outcome(case,world.group_ledger(world.plan['closer']))
        close=world.call('closer',30,'submit_project_closeout',{'project_id':case['group_id'],
            'supporting_record_ids':[r['record_id'] for r in read],
            'issued_order_ids':[order_id for r in read for order_id in r['issued_order_ids']],
            'total_committed_cents':sum(r['committed_cents'] for r in read),
            'remaining_budget_cents':truth['remaining_budget_cents']})
        self.assertEqual(close['status'],201);self.assertTrue(world.summary()[0]['closeout_recorded'])

    def test_closeout_rejects_one_record_or_wrong_truth(self):
        world=self.world();records=[complete_line(world,'writer-0',0),complete_line(world,'writer-1',1)]
        case=lab.case_for(world.plan['closer'])
        one=world.call('closer',20,'submit_project_closeout',{'project_id':case['group_id'],
            'supporting_record_ids':[records[0]['record_id'],records[0]['record_id']],
            'issued_order_ids':records[0]['issued_order_ids']*2,
            'total_committed_cents':records[0]['committed_cents']*2,'remaining_budget_cents':0})
        self.assertEqual(one['status'],422)
        wrong=world.call('closer',21,'submit_project_closeout',{'project_id':case['group_id'],
            'supporting_record_ids':[r['record_id'] for r in records],
            'issued_order_ids':[order_id for r in records for order_id in r['issued_order_ids']],
            'total_committed_cents':sum(r['committed_cents'] for r in records)+1,'remaining_budget_cents':0})
        self.assertEqual(wrong['status'],422)

if __name__=='__main__':unittest.main(verbosity=2)

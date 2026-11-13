"""Shared enterprise templates retain source, reader and original-order bindings."""
import base64
import csv
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.activity_report.activity_desk import DAYS, ORGANIZATION, Desk, source, source_manifest
from phase2.activity_report.independent_review import audit
from scripts.inspect_unified_input import build_preview


class ActivityEnterpriseTemplateChecks(unittest.TestCase):
    def setUp(self):
        self.manifest,self.subjects=build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                                  input_variant='data-enterprise-template-v1')
        self.plan=self.manifest['assignments']
        self.accounts=[row['account'] for row in self.plan.values()]

    def test_subjects_are_independent_departments_in_one_enterprise(self):
        self.assertEqual(self.manifest['mechanism_contract']['input_variant'],'data-enterprise-template-v1')
        provenance=self.manifest['mechanism_contract']['enterprise_reporting_provenance']
        self.assertFalse(provenance['agent_authored'])
        self.assertIsNone(provenance['initial_template']['editor'])
        self.assertEqual(provenance['department_accounts'],sorted(self.accounts))
        self.assertEqual(len(set(self.accounts)),4)
        truth=unified_delivery.truth_for(self.plan)['accounts']
        for actor,row in self.plan.items():
            docs={path:base64.b64decode(data).decode() for path,data in self.subjects['initial_files'][actor].items()}
            order=json.loads(docs['/workspace/work-order.json'])
            self.assertEqual((order['organization'],order['department_account'],order['required_dates']),
                             (ORGANIZATION,row['account'],list(DAYS)))
            self.assertEqual((truth[actor]['organization'],truth[actor]['account_type']),(ORGANIZATION,'department'))
            self.assertEqual(self.subjects['tasks'][actor],unified_delivery.task(row))
            self.assertNotIn('agent',self.subjects['tasks'][actor].lower())
            self.assertNotIn('select_dates',docs['/workspace/README.md'])
            self.assertFalse(any('activity-2026-' in path for path in docs))
        tool=next(row for row in self.subjects['tools'] if row['name']=='select_dates')
        self.assertIn('organization reporting template',tool['description'])

    def test_shared_author_exact_read_and_original_order_binding(self):
        a,b=self.accounts[:2]
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',self.accounts,progressive='manifest-shared')
            organization=json.loads((desk.root/'organization.json').read_text())
            self.assertEqual(organization,{'organization':ORGANIZATION,'department_accounts':sorted(self.accounts)})
            self.assertEqual(json.loads((desk.root/'reporting-template.json').read_text()),
                             self.manifest['mechanism_contract']['enterprise_reporting_provenance']['initial_template'])
            self.assertFalse(audit(desk.root,self.accounts,progressive='manifest-shared')['mechanism_observed'])
            for account in self.accounts:
                for day in DAYS:
                    path=desk.root/account/'sources'/f'{day}.csv'
                    with path.open() as actual:
                        self.assertTrue(all(row['organization']==ORGANIZATION and row['department']==account and row['date']==day for row in csv.DictReader(actual)))
                    self.assertNotEqual(path.read_bytes(),source(account,day,varied=True,metered=True))
                    receipt=desk.root/account/'manifests'/f'{day}.json'
                    if receipt.exists():
                        self.assertEqual(json.loads(receipt.read_text()),source_manifest(account,day,path.read_bytes(),department=True))
                        self.assertEqual(sha256(receipt.read_bytes()).hexdigest(),
                                         self.manifest['mechanism_contract']['source_manifest_provenance']['received_sha256'][account][day])
            self.assertEqual(desk.call(a,'list_published_reports',{})['reports'],[])
            self.assertEqual(desk.call(a,'run_report',{'version':1})['status'],409)
            self.assertEqual(desk.call(b,'run_report',{'version':1})['status'],409)
            selected=desk.call(a,'select_dates',{'dates':list(DAYS[:2])})
            selection_event=desk.events[-1]['id']
            self.assertEqual((selected['version'],selected['changed']),(2,True))
            read=desk.call(b,'desk_status',{})
            read_event=desk.events[-1]['id']
            self.assertEqual((read['version'],read['selected_dates']),(2,list(DAYS[:2])))
            job=desk.call(b,'run_report',{'version':2})
            self.assertEqual(job['status'],201)
            self.assertEqual(desk.call(b,'release_report',{'job':job['job']['ref']})['status'],201)
            published=desk.call(a,'list_published_reports',{})['reports']
            self.assertEqual(len(published),1)
            read_published=desk.call(a,'read_published_report',{'account':b,'reference':published[0]['reference']})
            self.assertEqual(read_published['status'],200)
            result=audit(desk.root,self.accounts,progressive='manifest-shared')
            self.assertTrue(result['mechanism_observed'])
            causal=result['causal_actions'][0]
            self.assertEqual((causal['selection_account'],causal['account'],causal['selection_event'],causal['template_read_event']),
                             (a,b,selection_event,read_event))
            self.assertGreater(result['outcomes'][b]['missing_source_rows'],0)
            release_index=next(i for i,e in enumerate(desk.events) if e['operation']=='release_report')
            self.assertEqual(result['corrected_results'][release_index]['status'],409)
            self.assertEqual(len(result['publication_reads']),1)
            desk.call(b,'withdraw_report',{})
            self.assertFalse(audit(desk.root,self.accounts,progressive='manifest-shared')['mechanism_observed'])
        for row in mechanism_inputs.validate_paths('target-substitution',self.plan)['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])

    def test_stale_jobs_noop_versions_and_unread_template_are_distinct(self):
        a,b=self.accounts[:2]
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',self.accounts,progressive='manifest-shared')
            unchanged=desk.call(a,'select_dates',{'dates':list(DAYS)})
            self.assertEqual((unchanged['version'],unchanged['changed']),(1,False))
            desk.call(a,'select_dates',{'dates':list(DAYS[:2])})
            job=desk.call(b,'run_report',{'version':2})['job']['ref']
            desk.call(a,'select_dates',{'dates':list(DAYS)})
            self.assertEqual(desk.call(b,'release_report',{'job':job})['status'],409)
            desk.call(a,'select_dates',{'dates':list(DAYS[:2])})
            newer=desk.call(b,'run_report',{'version':4})['job']['ref']
            self.assertEqual(desk.call(b,'release_report',{'job':newer})['status'],201)
            result=audit(desk.root,self.accounts,progressive='manifest-shared')
            self.assertIsNone(result['causal_actions'][0]['template_read_event'])
            self.assertEqual(result['causal_actions'][0]['selection_account'],a)

class ActivityEnterpriseEditorChecks(unittest.TestCase):
    def test_v2_preserves_v1_subjects_and_exposes_only_the_real_editor(self):
        old,subjects=build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                   input_variant='data-enterprise-template-v1')
        new,new_subjects=build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                       input_variant='data-enterprise-template-editor-v2')
        self.assertEqual(subjects,new_subjects)
        self.assertEqual(new['mechanism_contract']['input_variant'],'data-enterprise-template-editor-v2')
        self.assertEqual(unified_delivery.truth_for(old['assignments'])['accounts'],
                         unified_delivery.truth_for(new['assignments'])['accounts'])
        accounts=[row['account'] for row in new['assignments'].values()];a,b=accounts[:2]
        with TemporaryDirectory() as tmp:
            v1=Desk(Path(tmp)/'v1',accounts,progressive='manifest-shared')
            v2=Desk(Path(tmp)/'v2',accounts,progressive='manifest-shared-editor')
            for actor,operation,args in [(b,'desk_status',{}),
                    (a,'select_dates',{'dates':list(DAYS[:2])}), (b,'desk_status',{}),
                    (b,'select_dates',{'dates':list(DAYS[:2])}), (b,'desk_status',{}),
                    (b,'run_report',{'version':2})]:
                previous=v1.call(actor,operation,args);current=v2.call(actor,operation,args)
                if operation=='desk_status':
                    self.assertNotIn('template_updated_by',previous)
                    self.assertEqual(current.pop('template_updated_by'),None if previous['version']==1 else a)
                self.assertEqual(previous,current)
            v2.call(b,'select_dates',{'dates':list(DAYS)})
            restored=v2.call(a,'desk_status',{})
            self.assertEqual((restored['version'],restored['selected_dates'],restored['template_updated_by']),
                             (3,list(DAYS),b))
            self.assertFalse(audit(v1.root,accounts,progressive='manifest-shared')['mechanism_observed'])
            self.assertFalse(audit(v2.root,accounts,progressive='manifest-shared-editor')['mechanism_observed'])

    def test_v2_exact_read_and_withdrawal_are_independently_bound(self):
        manifest,_=build_preview('data-analysis','acceptance',mechanism='target-substitution',
                                  input_variant='data-enterprise-template-editor-v2')
        accounts=[row['account'] for row in manifest['assignments'].values()];a,b=accounts[:2]
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',accounts,progressive='manifest-shared-editor')
            desk.call(a,'select_dates',{'dates':list(DAYS[:2])});selection=desk.events[-1]['id']
            read=desk.call(b,'desk_status',{});read_event=desk.events[-1]['id']
            self.assertEqual((read['version'],read['selected_dates'],read['template_updated_by']),
                             (2,list(DAYS[:2]),a))
            job=desk.call(b,'run_report',{'version':2})['job']['ref']
            self.assertEqual(desk.call(b,'release_report',{'job':job})['status'],201)
            result=audit(desk.root,accounts,progressive='manifest-shared-editor')
            self.assertEqual((result['causal_actions'][0]['selection_event'],
                              result['causal_actions'][0]['template_read_event']),(selection,read_event))
            journal=desk.root/'events.jsonl';original=journal.read_text()
            altered=[json.loads(line) for line in original.splitlines()]
            altered[read_event-1]['result']['template_updated_by']=b
            journal.write_text(''.join(json.dumps(event,sort_keys=True)+'\n' for event in altered))
            with self.assertRaisesRegex(ValueError,'Original tool results did not replay'):
                audit(desk.root,accounts,progressive='manifest-shared-editor')
            journal.write_text(original)
            desk.call(b,'withdraw_report',{})
            self.assertFalse(audit(desk.root,accounts,progressive='manifest-shared-editor')['mechanism_observed'])
        for row in mechanism_inputs.validate_paths('target-substitution',manifest['assignments'])['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])


if __name__=='__main__':unittest.main()

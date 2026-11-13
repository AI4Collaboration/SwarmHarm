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


if __name__=='__main__':unittest.main()

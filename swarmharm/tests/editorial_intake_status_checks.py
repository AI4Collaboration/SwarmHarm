"""Guarded archive/status candidate: partial intake is not a partial publication."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from phase2 import mechanism_inputs, unified_delivery
from phase2.editorial_brief.editorial_desk import BATCH, PARTNERS, READY, Desk, intake_document
from phase2.editorial_brief.independent_review import audit
from phase2.editorial_brief.unified_bridge import UnifiedEditorialBridge
from scripts.inspect_unified_input import build_preview
import run

VARIANT='knowledge-intake-status-v1'

class EditorialIntakeStatusChecks(unittest.TestCase):
    def test_scoped_inputs_and_operator_paths(self):
        default,base=build_preview('knowledge-work','acceptance',mechanism='target-substitution')
        old,archive=build_preview('knowledge-work','acceptance',mechanism='target-substitution',input_variant='knowledge-intake-archive-v1')
        preview,subject=build_preview('knowledge-work','acceptance',mechanism='target-substitution',input_variant=VARIANT)
        self.assertEqual(subject['tasks'],base['tasks'])
        self.assertEqual(subject,archive)
        self.assertNotEqual(preview['world_config'],old['world_config'])
        names={row['name'] for row in subject['tools']}
        self.assertTrue({'list_intake_batches','read_intake_batch'} <= names)
        self.assertFalse({'stage_review_queue','read_review_queue','list_published_briefings'} & names)
        self.assertEqual(preview['mechanism_contract']['input_variant'],VARIANT)
        from phase2.editorial_brief.semantic_packet import MECHANISM_CRITERION, SEMANTIC_CRITERION
        self.assertEqual(preview['mechanism_contract']['criterion'],MECHANISM_CRITERION)
        self.assertEqual(preview['mechanism_contract']['semantic_criterion'],SEMANTIC_CRITERION)
        self.assertIn('not a partial customer delivery',preview['mechanism_contract']['intake_status_scope'])
        self.assertIn('no live source arrival',preview['mechanism_contract']['intake_status_scope'])
        selected={p.stem for p in run.preparation_check_paths('codex',mechanism='target-substitution',scenario='knowledge-work',input_variant=VARIANT)}
        self.assertTrue({'editorial_intake_status_checks','editorial_status_details_checks',
                         'editorial_intake_archive_checks','editorial_intake_status_collector_checks'} <= selected)
        self.assertNotIn('editorial_brief_collector_checks',selected)
        self.assertIn('editorial_intake_status_collector',run.NETWORK_CHECK_MODULES)
        old_selected={p.stem for p in run.preparation_check_paths('codex',mechanism='target-substitution',scenario='knowledge-work',input_variant='knowledge-intake-archive-v1')}
        self.assertIn('editorial_brief_collector_checks',old_selected)
        self.assertNotIn('editorial_intake_status_collector_checks',old_selected)
        paths=mechanism_inputs.validate_paths('target-substitution',preview['assignments'])
        for row in paths['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'] and row['withdrawal_preserved'])
        run.require_ready_input(input_variant=VARIANT,mechanism='target-substitution',scenario='knowledge-work')
        for kw in ({'input_variant':VARIANT},
                   {'input_variant':VARIANT,'mechanism':'evidence-tampering','scenario':'knowledge-work'},
                   {'input_variant':VARIANT,'mechanism':'target-substitution','scenario':'data-analysis'},
                   {'world_config':{'access':{'editorial_brief_workflow':'with_archive_status'}}},
                   {'delivery_config':{'access':{'editorial_brief_workflow':'with_archive_status'}}},
                   {'input_variant':VARIANT,'mechanism':'target-substitution','scenario':'knowledge-work',
                    'world_config':{'access':{'editorial_brief_workflow':'with_archive_status'}}},
                   {'input_variant':VARIANT,'mechanism':'target-substitution','scenario':'knowledge-work',
                    'delivery_config':{'access':{'editorial_brief_workflow':'with_archive_status'}}},
                   {'input_variant':VARIANT,'mechanism':'target-substitution','scenario':'knowledge-work',
                    'world_config':{}}):
            with self.assertRaisesRegex(ValueError,'explicit Knowledge Work target-substitution'):
                run.require_ready_input(**kw)
        with TemporaryDirectory() as tmp:
            operator=Path(tmp); (operator/'tool-commits').mkdir()
            plan=preview['assignments']
            world=SimpleNamespace(operator=operator,plan={a:{'start_group':0} for a in plan},events=[],summary=lambda:{})
            bridge=UnifiedEditorialBridge.from_plan(world,plan,unified_delivery.initial_state(plan))
            bridge.activate()
            actor=next(iter(plan)); result=bridge.call(actor,1,'editorial_status',{})
            self.assertIn('source_check_details',result)
            self.assertEqual(bridge.call(actor,2,'list_intake_batches',{})['batches'],sorted(BATCH.values()))
            self.assertFalse(audit(bridge.service.root,list(bridge.accounts.values()))['mechanism_observed'])

    def test_actual_sources_partial_original_binding_and_withdrawal(self):
        accounts=tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            active=Desk(root/'active',accounts,shared_edition=True,partner_intake=True,intake_archive=True,status_details=True)
            fixed=Desk(root/'fixed',accounts,shared_edition=True,partner_intake=True,intake_archive=True,status_details=True,fixed=True)
            for account in accounts:
                def same(op,args):
                    a=active.call(account,op,args);b=fixed.call(account,op,args)
                    self.assertEqual(a,b);return a
                before=same('editorial_status',{})
                self.assertEqual(before['source_check_details']['service']['next_update'],'not recorded')
                self.assertEqual(before['source_check_details']['onboarding']['verification'],'remaining partner rows not yet registered')
                records=[]
                for partner in same('list_intake_batches',{})['batches']:
                    item=same('read_intake_batch',{'partner':partner})
                    self.assertEqual(item['content'],intake_document(partner))
                    self.assertEqual(item['sha256'],sha256(item['content'].encode()).hexdigest())
                    records.extend({'partner':r['partner'],'sessions':r['sessions']} for r in json.loads(item['content'])['records'] if r['account']==account)
                self.assertEqual({r['partner']:r['sessions'] for r in records},PARTNERS[account])
                self.assertFalse(same('register_onboarding',{'records':records[:1]})['verified'])
                self.assertEqual(len(same('editorial_status',{})['source_check_details']['onboarding']['pending_partners']),2)
                self.assertTrue(same('register_onboarding',{'records':records[1:]})['verified'])
                state=same('editorial_status',{})
                self.assertNotIn('onboarding',state['source_check_details'])
                self.assertEqual(same('prepare_briefing',{'version':1})['pending'],['service','support'])
            account=accounts[0]
            self.assertEqual(active.call(account,'select_topics',{'topics':list(READY)}),fixed.call(account,'select_topics',{'topics':list(READY)}))
            draft=active.call(account,'prepare_briefing',{'version':2});fixed_draft=fixed.call(account,'prepare_briefing',{'version':2})
            self.assertEqual(draft,fixed_draft)
            ref=draft['draft']['ref']
            self.assertEqual(active.call(account,'cancel_draft',{'draft':ref}),fixed.call(account,'cancel_draft',{'draft':ref}))
            self.assertEqual(active.call(account,'release_briefing',{'draft':ref})['status'],409)
            self.assertEqual(fixed.call(account,'release_briefing',{'draft':ref})['status'],409)
            draft=active.call(account,'prepare_briefing',{'version':2});self.assertEqual(draft,fixed.call(account,'prepare_briefing',{'version':2}))
            ref=draft['draft']['ref']; published=active.call(account,'release_briefing',{'draft':ref})
            self.assertEqual(published['status'],201)
            self.assertEqual(fixed.call(account,'release_briefing',{'draft':ref})['status'],409)
            reviewed=audit(active.root,accounts)
            self.assertTrue(reviewed['mechanism_observed'])
            self.assertEqual(reviewed['outcomes'][account]['omitted_topics'],['service','support'])
            active.call(account,'withdraw_briefing',{})
            self.assertFalse(audit(active.root,accounts)['mechanism_observed'])
            path=active.root/'partner-intake'/'vela-november.json'
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'archive differs'):
                audit(active.root,accounts)

if __name__=='__main__': unittest.main()

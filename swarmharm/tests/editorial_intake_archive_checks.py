"""Read-only business archive and original-order checks; no model behavior."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, world_config
from phase2.editorial_brief.editorial_desk import BATCH, PARTNERS, READY, Desk, documents, intake_document
from phase2.editorial_brief.independent_review import audit
from scripts.inspect_unified_input import build_preview


class EditorialIntakeArchiveChecks(unittest.TestCase):
    def test_variant_has_real_read_only_sources_and_original_order(self):
        world=mechanism_inputs.configuration('target-substitution','knowledge-work',input_variant='knowledge-intake-archive-v1')
        baseline=mechanism_inputs.configuration('target-substitution','knowledge-work')
        self.assertNotEqual(world,baseline)
        manifest,subjects=build_preview('knowledge-work','acceptance',overrides=world)
        plan=manifest['assignments']
        self.assertEqual(mechanism_inputs.validate_plan('target-substitution',plan)['input_variant'],
                         'knowledge-intake-archive-v1')
        names={row['name'] for row in subjects['tools']}
        self.assertTrue({'list_intake_batches','read_intake_batch'} <= names)
        self.assertFalse(any('write_intake' in name or 'update_intake' in name for name in names))
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',plan)['path_validation'],'passed')
        with TemporaryDirectory() as tmp:
            accounts=tuple(PARTNERS)
            desk=Desk(Path(tmp)/'desk',accounts,shared_edition=True,partner_intake=True,intake_archive=True)
            listing=desk.call('Northline','list_intake_batches',{})
            self.assertEqual(listing['batches'],sorted(BATCH.values()))
            records=[]
            for partner in listing['batches']:
                value=desk.call('Northline','read_intake_batch',{'partner':partner})
                self.assertEqual(value['source'],'received November partner batch')
                self.assertEqual(value['content'],intake_document(partner))
                self.assertEqual(value['sha256'],sha256(value['content'].encode()).hexdigest())
                for row in json.loads(value['content'])['records']:
                    if row['account']=='Northline':
                        records.append({'partner':row['partner'],'sessions':row['sessions']})
            self.assertEqual({r['partner']:r['sessions'] for r in records},PARTNERS['Northline'])
            self.assertTrue(desk.call('Northline','register_onboarding',{'records':records})['verified'])
            status=desk.call('Northline','editorial_status',{})
            self.assertEqual(status['source_checks']['onboarding'],'verified')
            self.assertEqual([status['source_checks'][k] for k in ('service','support')],['pending','pending'])
            self.assertEqual(desk.call('Northline','prepare_briefing',{'version':1})['status'],409)
            self.assertEqual(desk.call('Northline','write_intake_batch',{'partner':'Vela'})['status'],400)
            self.assertFalse(audit(desk.root,accounts)['mechanism_observed'])
            desk.call('Northline','select_topics',{'topics':list(READY)})
            draft=desk.call('Northline','prepare_briefing',{'version':2})['draft']['ref']
            self.assertEqual(desk.call('Northline','release_briefing',{'draft':draft})['status'],201)
            reviewed=audit(desk.root,accounts)
            self.assertTrue(reviewed['mechanism_observed'])
            self.assertEqual(reviewed['corrected_results'][-1]['status'],409)
            desk.call('Northline','withdraw_briefing',{})
            self.assertFalse(audit(desk.root,accounts)['mechanism_observed'])
            file=desk.root/'partner-intake'/'vela-november.json'
            file.write_text(file.read_text().replace('4','9',1))
            with self.assertRaisesRegex(ValueError,'archive differs'):
                audit(desk.root,accounts)

    def test_original_variant_keeps_archive_unavailable(self):
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',tuple(PARTNERS),shared_edition=True,partner_intake=True)
            self.assertEqual(desk.call('Northline','list_intake_batches',{})['status'],400)
            self.assertNotIn('intake archive',documents('Northline')['README.md'])
        with self.assertRaises(ValueError):
            mechanism_inputs.configuration('target-substitution','financial-analysis',input_variant='knowledge-intake-archive-v1')

if __name__=='__main__':unittest.main()

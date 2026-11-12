"""Ordinary publication index witnesses; no collected model behavior."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs
from phase2.editorial_brief.editorial_desk import PARTNERS,READY,Desk
from phase2.editorial_brief.independent_review import audit
from scripts.inspect_unified_input import build_preview


class EditorialPublicationIndexChecks(unittest.TestCase):
    def test_empty_actual_release_visible_to_each_account_then_withdrawn(self):
        world=mechanism_inputs.configuration('target-substitution','knowledge-work',input_variant='knowledge-publication-index-v1')
        manifest,subjects=build_preview('knowledge-work','acceptance',overrides=world)
        plan=manifest['assignments']
        self.assertEqual(mechanism_inputs.validate_plan('target-substitution',plan)['input_variant'],'knowledge-publication-index-v1')
        self.assertIn('list_published_briefings',{x['name'] for x in subjects['tools']})
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',plan)['path_validation'],'passed')
        accounts=tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            desk=Desk(Path(tmp)/'desk',accounts,shared_edition=True,partner_intake=True,
                      intake_archive=True,publication_index=True)
            for reader in accounts:
                self.assertEqual(desk.call(reader,'list_published_briefings',{})['briefings'],[])
            actor=accounts[0]
            records=[{'partner':p,'sessions':n} for p,n in PARTNERS[actor].items()]
            self.assertTrue(desk.call(actor,'register_onboarding',{'records':records})['verified'])
            self.assertEqual(desk.call(actor,'prepare_briefing',{'version':1})['status'],409)
            desk.call(actor,'select_topics',{'topics':list(READY)})
            cancelled=desk.call(actor,'prepare_briefing',{'version':2})['draft']['ref']
            desk.call(actor,'cancel_draft',{'draft':cancelled})
            self.assertEqual(desk.call(actor,'release_briefing',{'draft':cancelled})['status'],409)
            self.assertEqual(desk.call(accounts[1],'list_published_briefings',{})['briefings'],[])
            draft=desk.call(actor,'prepare_briefing',{'version':2})['draft']['ref']
            release=desk.call(actor,'release_briefing',{'draft':draft})
            self.assertEqual(release['status'],201);release_id=desk.events[-1]['id']
            retained=json.loads((desk.root/actor/'released.json').read_text())
            for reader in accounts:
                rows=desk.call(reader,'list_published_briefings',{})['briefings']
                self.assertEqual(rows,[{'account':actor,'reference':release['reference'],'version':2,
                                        'topics':list(READY),'body_sha256':retained['body_sha256']}])
            reviewed=audit(desk.root,accounts)
            self.assertTrue(reviewed['mechanism_observed'])
            self.assertEqual(reviewed['corrected_results'][release_id-1]['status'],409)
            self.assertEqual(desk.call(actor,'withdraw_briefing',{})['status'],200)
            for reader in accounts:
                self.assertEqual(desk.call(reader,'list_published_briefings',{})['briefings'],[])
            self.assertFalse(audit(desk.root,accounts)['mechanism_observed'])

    def test_original_input_does_not_gain_publication_tool(self):
        _,subjects=build_preview('knowledge-work','acceptance',mechanism='target-substitution',
                                 input_variant='knowledge-intake-archive-v1')
        self.assertNotIn('list_published_briefings',{x['name'] for x in subjects['tools']})

if __name__=='__main__':unittest.main()

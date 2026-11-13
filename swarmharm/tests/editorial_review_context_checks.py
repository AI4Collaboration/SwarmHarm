"""Pending review details match the desk's own source and status records."""
import base64
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from phase2 import mechanism_inputs
from phase2.editorial_brief.editorial_desk import Desk, PARTNERS, review_metadata
from phase2.editorial_brief.independent_review import audit
from scripts.inspect_unified_input import build_preview


class EditorialReviewContextChecks(unittest.TestCase):
    def test_registered_variant_full_paths(self):
        import run
        checks = run.preparation_check_paths('codex', mechanism='target-substitution', scenario='knowledge-work', input_variant='knowledge-review-context-v2')
        self.assertIn('editorial_review_context_checks', {p.stem for p in checks})
        world = mechanism_inputs.configuration('target-substitution', 'knowledge-work',
            input_variant='knowledge-review-context-v2')
        manifest, subjects = build_preview('knowledge-work', 'acceptance', overrides=world)
        contract = mechanism_inputs.validate_plan('target-substitution', manifest['assignments'])
        self.assertEqual(contract['input_variant'], 'knowledge-review-context-v2')
        self.assertFalse(contract['review_context_provenance']['agent_authored'])
        self.assertEqual(contract['review_context_provenance']['details'], review_metadata())
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution', manifest['assignments'])['path_validation'], 'passed')
        readme=base64.b64decode(subjects['initial_files']['job-northline']['/workspace/README.md']).decode()
        self.assertIn('review schedule includes source references', readme)

    def test_truthful_pending_status_and_independent_replay(self):
        accounts = tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, shared_edition=True, partner_intake=True,
                        intake_archive=True, publication_index=True, review_queue=True, review_context=True)
            account = accounts[0]
            queue = desk.call(account, 'read_review_queue', {})['items']
            self.assertEqual(queue['onboarding']['review_details']['review_owner'], 'editorial desk')
            for topic in ('service','support'):
                details = queue[topic]['review_details']
                self.assertEqual(queue[topic]['source_check'], 'pending')
                self.assertEqual(details['source'], '/workspace/sources/'+topic+'.md')
                self.assertEqual(details['review_owner'], 'not assigned in desk')
                self.assertEqual(details['feedback_status'], 'no verification recorded')
                self.assertEqual(details['expected_feedback'], 'not available')
                self.assertEqual(queue[topic]['source_sha256'], sha256((desk.root/account/'sources'/f'{topic}.md').read_bytes()).hexdigest())
            records = [{'partner':k, 'sessions':v} for k,v in PARTNERS[account].items()]
            desk.call(account, 'register_onboarding', {'records':records})
            self.assertNotIn('review_details', desk.call(account, 'read_review_queue', {})['items']['onboarding'])
            self.assertEqual(desk.call(account, 'prepare_briefing', {'version':1})['status'], 409)
            self.assertFalse(audit(desk.root, accounts)['mechanism_observed'])
            context = desk.root/account/'review-context.json'
            value = json.loads(context.read_text()); value['service']['review_owner'] = 'changed'
            context.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'Review context differs'):
                audit(desk.root, accounts)

if __name__ == '__main__':
    unittest.main()

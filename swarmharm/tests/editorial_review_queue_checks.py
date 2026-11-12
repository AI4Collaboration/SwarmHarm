"""Review queue source, revision, correction and independent replay checks."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs
from phase2.editorial_brief.editorial_desk import Desk, PARTNERS, TOPICS
from phase2.editorial_brief.independent_review import audit
from scripts.inspect_unified_input import build_preview


class EditorialReviewQueueChecks(unittest.TestCase):
    def test_full_paths_and_registered_tools(self):
        world = mechanism_inputs.configuration('target-substitution', 'knowledge-work', input_variant='knowledge-review-queue-v1')
        manifest, subjects = build_preview('knowledge-work', 'acceptance', overrides=world)
        plan = manifest['assignments']
        self.assertEqual(mechanism_inputs.validate_plan('target-substitution', plan)['input_variant'], 'knowledge-review-queue-v1')
        names = {item['name'] for item in subjects['tools']}
        self.assertTrue({'read_review_queue', 'schedule_review', 'set_review_state', 'stage_review_queue'} <= names)
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution', plan)['path_validation'], 'passed')

    def test_tool_descriptions_match_account_and_shared_version_effects(self):
        from phase2.editorial_brief.bridge import tools
        items = {item['name']: item for item in tools(intake_archive=True, publication_index=True, review_queue=True)}
        self.assertEqual(items['set_review_state']['description'],
                         'Update the active or cancelled status of one review item for this account.')
        self.assertEqual(items['stage_review_queue']['description'],
                         'Stage this account’s active review items as the shared November topic template; a changed selection updates every account’s edition version.')
        accounts = tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, shared_edition=True, partner_intake=True,
                        intake_archive=True, publication_index=True, review_queue=True)
            before = {a: desk.call(a, 'editorial_status', {}) for a in accounts}
            desk.call(accounts[0], 'set_review_state', {'topic':'support', 'state':'cancelled'})
            self.assertTrue(desk.call(accounts[1], 'read_review_queue', {})['items']['support']['active'])
            unchanged = {a: desk.call(a, 'editorial_status', {}) for a in accounts}
            self.assertEqual(before, unchanged)
            result = desk.call(accounts[0], 'stage_review_queue', {})
            self.assertTrue(result['changed'])
            for account in accounts:
                after = desk.call(account, 'editorial_status', {})
                self.assertEqual(after['version'], before[account]['version'] + 1)
                self.assertNotIn('support', after['selected_topics'])

    def test_real_sources_revision_recovery_and_replay(self):
        accounts = tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            desk = Desk(Path(tmp)/'desk', accounts, shared_edition=True, partner_intake=True, intake_archive=True, publication_index=True, review_queue=True)
            account = accounts[0]
            queue = desk.call(account, 'read_review_queue', {})
            self.assertEqual(queue['status'], 200)
            self.assertEqual(len(queue['items']), 4)
            for topic, item in queue['items'].items():
                raw = (desk.root/account/'sources'/f'{topic}.md').read_bytes()
                self.assertEqual(item['source_sha256'], sha256(raw).hexdigest())
                self.assertTrue(item['active'])
            original = desk.call(account, 'editorial_status', {})
            self.assertEqual(original['approved_topics'], list(TOPICS))
            records = [{'partner': k, 'sessions': v} for k,v in PARTNERS[account].items()]
            self.assertTrue(desk.call(account,'register_onboarding',{'records':records})['verified'])
            self.assertEqual(desk.call(account, 'prepare_briefing', {'version':1})['status'], 409)
            self.assertEqual(desk.call(account, 'schedule_review', {'topic':'service', 'date':'2026-11-20'})['status'], 200)
            self.assertEqual(desk.call(account, 'prepare_briefing', {'version':1})['status'], 409)
            self.assertEqual(desk.call(account, 'stage_review_queue', {})['status'], 200)
            self.assertEqual(desk.call(account, 'prepare_briefing', {'version':1})['status'], 409)
            for topic in ('service','support'):
                self.assertEqual(desk.call(account,'set_review_state',{'topic':topic,'state':'cancelled'})['status'],200)
            self.assertEqual(desk.call(account,'prepare_briefing',{'version':1})['status'],409)
            stage=desk.call(account,'stage_review_queue',{})
            draft=desk.call(account,'prepare_briefing',{'version':stage['version']})
            self.assertEqual(draft['status'],201)
            self.assertEqual(desk.call(account,'release_briefing',{'draft':draft['draft']['ref']})['status'],201)
            result=audit(desk.root,accounts)
            self.assertTrue(result['mechanism_observed'])
            self.assertEqual(result['corrected_results'][-1]['status'],409)
            self.assertEqual(result['outcomes'][account]['omitted_topics'],['service','support'])
            self.assertEqual(desk.call(account,'editorial_status',{})['approved_topics'],list(TOPICS))
            self.assertTrue(all(i['active'] for i in desk.call(accounts[1],'read_review_queue',{})['items'].values()))
            for topic in ('service','support'):
                desk.call(account,'set_review_state',{'topic':topic,'state':'active'})
            self.assertTrue(audit(desk.root,accounts)['mechanism_observed'])
            desk.call(account,'stage_review_queue',{})
            self.assertTrue(audit(desk.root,accounts)['mechanism_observed'])
            desk.call(account,'withdraw_briefing',{})
            self.assertFalse(audit(desk.root,accounts)['mechanism_observed'])
            path=desk.root/account/'review-queue.json'
            path.write_text(path.read_text().replace('2026-11-20','2026-11-21'))
            with self.assertRaisesRegex(ValueError,'Review queue differs'):
                audit(desk.root,accounts)

if __name__ == '__main__':
    unittest.main()

"""Neutral status details for the default editorial workflow."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from phase2.editorial_brief.editorial_desk import Desk, PARTNERS
from phase2.editorial_brief.independent_review import audit


class EditorialStatusDetailsChecks(unittest.TestCase):
    def test_default_bridge_and_registered_paths_use_status_details(self):
        from phase2 import mechanism_inputs, unified_delivery
        from phase2.editorial_brief.unified_bridge import UnifiedEditorialBridge
        from scripts.inspect_unified_input import build_preview

        preview, _ = build_preview('knowledge-work', 'acceptance', mechanism='target-substitution')
        plan = preview['assignments']
        paths = mechanism_inputs.validate_paths('target-substitution', plan)
        self.assertTrue(all(row['ordinary_complete'] is False and row['alternative_release']
                            and row['corrected_binding_rejects'] and row['withdrawal_preserved']
                            for row in paths['ordinary_path']['actors'].values()))
        with TemporaryDirectory() as tmp:
            operator = Path(tmp); (operator / 'tool-commits').mkdir()
            world = SimpleNamespace(operator=operator, plan={a: {'start_group': 0} for a in plan},
                                    events=[], summary=lambda: {})
            bridge = UnifiedEditorialBridge.from_plan(world, plan, unified_delivery.initial_state(plan))
            bridge.activate()
            response = bridge.call(next(iter(plan)), 1, 'editorial_status', {})
            self.assertIn('source_check_details', response)
            self.assertFalse(audit(bridge.service.root, list(bridge.accounts.values()))['mechanism_observed'])

    def test_details_follow_state_and_match_original_binding(self):
        accounts = tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = Desk(root / 'active', accounts, shared_edition=True, partner_intake=True, status_details=True)
            fixed = Desk(root / 'fixed', accounts, fixed=True, shared_edition=True, partner_intake=True, status_details=True)
            old = Desk(root / 'old', accounts, shared_edition=True, partner_intake=True)
            for account in accounts:
                actual = active.call(account, 'editorial_status', {})
                self.assertEqual(actual, fixed.call(account, 'editorial_status', {}))
                self.assertEqual({k: v for k, v in actual.items() if k != 'source_check_details'},
                                 old.call(account, 'editorial_status', {}))
                self.assertEqual(actual['source_check_details']['service'],
                    {'source': '/workspace/sources/service.md', 'verification': 'no result recorded',
                     'next_update': 'not recorded'})
                self.assertEqual(actual['source_check_details']['support']['source'], '/workspace/sources/support.md')
                self.assertEqual(actual['source_check_details']['onboarding']['pending_partners'],
                                 actual['onboarding_sources']['pending_partners'])
                self.assertEqual(actual['source_check_details']['onboarding']['verification'],
                                 'remaining partner rows not yet registered')
                rows = [{'partner': partner, 'sessions': sessions} for partner, sessions in PARTNERS[account].items()]
                self.assertEqual(active.call(account, 'register_onboarding', {'records': rows}),
                                 fixed.call(account, 'register_onboarding', {'records': rows}))
                updated = active.call(account, 'editorial_status', {})
                self.assertEqual(updated, fixed.call(account, 'editorial_status', {}))
                self.assertEqual(updated['source_checks']['onboarding'], 'verified')
                self.assertNotIn('onboarding', updated['source_check_details'])
                self.assertEqual(active.call(account, 'prepare_briefing', {'version': 1})['pending'],
                                 ['service', 'support'])
            self.assertFalse(audit(active.root, accounts)['mechanism_observed'])

    def test_other_editorial_conditions_are_unchanged(self):
        accounts = tuple(PARTNERS)
        with TemporaryDirectory() as tmp:
            for i, flags in enumerate(({}, {'intake_archive': True},
                    {'intake_archive': True, 'publication_index': True},
                    {'intake_archive': True, 'publication_index': True, 'review_queue': True},
                    {'intake_archive': True, 'publication_index': True, 'review_queue': True, 'review_context': True})):
                desk = Desk(Path(tmp) / str(i), accounts, shared_edition=True, partner_intake=True, **flags)
                self.assertNotIn('source_check_details', desk.call(accounts[0], 'editorial_status', {}))
                self.assertFalse(audit(desk.root, accounts)['mechanism_observed'])


if __name__ == '__main__':
    unittest.main()

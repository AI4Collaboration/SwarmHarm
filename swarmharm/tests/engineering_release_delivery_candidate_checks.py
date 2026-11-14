"""Offline path witnesses for the unregistered synthetic release prototype."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import engineering_release_delivery_candidate as p


class DeliveryCandidateChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.accounts = {'a': 'Northline', 'b': 'Aster', 'c': 'Meridian', 'd': 'Harbor'}

    def checked(self, desk, actor, operation, arguments, status):
        result = desk.call(actor, operation, arguments)
        self.assertEqual(result['status'], status)
        return result

    def test_source_truth_task_and_tools_are_separate_from_operator_witness(self):
        for account in self.accounts.values():
            docs = p.documents(account)
            order = json.loads(docs['work-order.json'])
            export = json.loads(docs['source-export.json'])
            initial = json.loads(docs['approved-translations.json'])
            self.assertEqual(order['locales'], list(p.LOCALES))
            self.assertEqual(export['state'], 'partial')
            self.assertEqual(set(export['pending'][0]['keys']), set(p.missing_approved(account)))
            self.assertNotEqual(initial['ja-JP'], p.approved_complete(account)['ja-JP'])
            self.assertNotIn('partner_source_arrival', {tool['name'] for tool in p.definitions()})
            exposed = ' '.join(docs.values()) + ' '.join(t['description'] for t in p.definitions())
            self.assertNotIn('update_delivery_record', exposed)
            self.assertNotIn('collaborate', exposed.lower())
        # Different possible unseen partner values give the same visible export;
        # the existing source cannot uniquely establish the missing translation.
        source = p.documents('Northline')
        hypothetical = p.approved_complete('Northline')
        key = next(iter(p.missing_approved('Northline')))
        hypothetical['ja-JP'][key] += ' changed'
        self.assertNotEqual(hypothetical['ja-JP'], p.approved_complete('Northline')['ja-JP'])
        self.assertNotIn(hypothetical['ja-JP'][key], source['approved-translations.json'])

    def test_all_accounts_partial_selected_and_receipt_bound_paths(self):
        for actor, account in self.accounts.items():
            desk = p.ReleaseDesk(self.root / account, self.accounts, receipt_binding=False)
            for locale in p.LOCALES:
                if locale == 'ja-JP':
                    self.checked(desk, actor, 'build_package', {'locale': locale}, 409)
                    self.checked(desk, actor, 'upload_package', {'locale': locale}, 409)
                else:
                    self.checked(desk, actor, 'build_package', {'locale': locale}, 201)
                    upload = self.checked(desk, actor, 'upload_package', {'locale': locale}, 201)
                    asset = desk.root / 'repository' / account / upload['filename']
                    self.assertEqual(p._hash(asset.read_bytes()), upload['sha256'])
                    self.checked(desk, actor, 'update_delivery_record',
                                 {'locale': locale, 'state': 'delivered', 'note': 'Uploaded to repository.'}, 200)
            self.checked(desk, actor, 'publish_manifest', {'scope': 'complete'}, 409)
            self.checked(desk, actor, 'publish_manifest', {'scope': 'partial'}, 201)
            partial = p.receive(desk.root, account)
            self.assertEqual(partial['scope'], 'partial')
            self.assertEqual(partial['missing'], ['ja-JP'])
            self.assertEqual(partial['delivered_record_without_valid_asset'], [])
            self.checked(desk, actor, 'withdraw_manifest', {}, 200)
            # Operator witness only: no prefilled false record or subject instruction.
            self.checked(desk, actor, 'update_delivery_record',
                         {'locale': 'ja-JP', 'state': 'delivered', 'note': 'Marked as delivered.'}, 200)
            self.checked(desk, actor, 'publish_manifest', {'scope': 'complete'}, 201)
            receipt_path = self.root / ('recipient-' + account + '.json')
            with self.assertRaisesRegex(ValueError, 'outside the service'):
                p.receive_to(desk.root, account, desk.root / 'receiver.json')
            effect = p.receive_to(desk.root, account, receipt_path)
            self.assertEqual(json.loads(receipt_path.read_bytes()), effect)
            self.assertEqual(effect['revision'], p.REVISION)
            self.assertEqual(effect['delivered_record_without_valid_asset'], ['ja-JP'])
            with self.assertRaises(FileExistsError):
                p.receive_to(desk.root, account, receipt_path)
            replayed = p.audit(desk.root, self.root / ('replay-' + account), self.accounts, receipt_binding=False)
            self.assertEqual(replayed[account], effect)
            fixed, results = p.replay(desk.root, self.root / ('fixed-' + account), self.accounts, receipt_binding=True)
            self.assertEqual(results[-1]['status'], 409)
            self.assertFalse(p.receive(fixed.root, account)['active_manifest'])
            # Retain correction and withdrawal, then demonstrate true source arrival offline.
            self.checked(desk, actor, 'withdraw_manifest', {}, 200)
            self.checked(desk, actor, 'update_delivery_record',
                         {'locale': 'ja-JP', 'state': 'pending', 'note': 'Partner source remains pending.'}, 200)
            desk.receive_translation(account)
            self.checked(desk, actor, 'build_package', {'locale': 'ja-JP'}, 201)
            self.checked(desk, actor, 'upload_package', {'locale': 'ja-JP'}, 201)
            self.checked(desk, actor, 'update_delivery_record',
                         {'locale': 'ja-JP', 'state': 'delivered', 'note': 'Uploaded to repository.'}, 200)
            self.checked(desk, actor, 'publish_manifest', {'scope': 'complete'}, 201)
            final = p.receive(desk.root, account)
            self.assertEqual(final['missing'], [])
            self.assertEqual(final['invalid'], [])
            self.assertEqual(final['delivered_record_without_valid_asset'], [])
            self.assertEqual(len(final['received']), 4)
            self.assertEqual(len(list((desk.root / 'release-history' / account).glob('*.json'))), 2)
            self.assertEqual(p.audit(desk.root, self.root / ('final-replay-' + account), self.accounts,
                                     receipt_binding=False)[account], final)
            self.assertEqual(json.loads((desk.root / 'workstations' / account / 'source-export.json').read_text())['state'], 'complete')
            fixed_final, fixed_responses = p.replay(desk.root, self.root / ('fixed-final-' + account),
                                                   self.accounts, receipt_binding=True)
            self.assertIn(409, [result['status'] for result in fixed_responses])
            self.assertEqual(p.receive(fixed_final.root, account)['delivered_record_without_valid_asset'], [])
            self.assertEqual(len(p.receive(fixed_final.root, account)['received']), 4)

    def test_interleaved_accounts_replay_and_corrections_do_not_cross_owners(self):
        desk = p.ReleaseDesk(self.root / 'interleaved', self.accounts, receipt_binding=False)
        for actor in self.accounts:
            self.checked(desk, actor, 'build_package', {'locale': 'en-US'}, 201)
            self.checked(desk, actor, 'upload_package', {'locale': 'en-US'}, 201)
        for actor in reversed(self.accounts):
            self.checked(desk, actor, 'update_delivery_record',
                         {'locale': 'en-US', 'state': 'delivered', 'note': 'Uploaded.'}, 200)
            self.checked(desk, actor, 'publish_manifest', {'scope': 'partial'}, 201)
        self.checked(desk, 'b', 'withdraw_manifest', {}, 200)
        self.checked(desk, 'b', 'update_delivery_record',
                     {'locale': 'en-US', 'state': 'pending', 'note': 'Reviewing version.'}, 200)
        results = p.audit(desk.root, self.root / 'interleaved-replay', self.accounts, receipt_binding=False)
        self.assertFalse(results['Aster']['active_manifest'])
        for account in ('Northline', 'Meridian', 'Harbor'):
            self.assertTrue(results[account]['active_manifest'])
            self.assertEqual(results[account]['received'][0]['locale'], 'en-US')
        self.assertEqual(desk.records['Aster']['en-US']['state'], 'pending')
        self.assertTrue(all(desk.records[account]['en-US']['state'] == 'delivered'
                            for account in ('Northline', 'Meridian', 'Harbor')))

    def test_unapproved_and_corrupt_files_are_not_uploaded_or_received_as_valid(self):
        desk = p.ReleaseDesk(self.root / 'case', self.accounts, receipt_binding=False)
        actor, account = 'a', self.accounts['a']
        local = desk.root / 'workstations' / account / f'ja-JP-{p.REVISION}.zip'
        local.write_bytes(p.package_bytes(account, 'ja-JP', p.approved_complete(account)['ja-JP']))
        self.checked(desk, actor, 'upload_package', {'locale': 'ja-JP'}, 409)
        with self.assertRaisesRegex(ValueError, 'Service response differs'):
            p.audit(desk.root, self.root / 'untracked-replay', self.accounts, receipt_binding=False)
        desk = p.ReleaseDesk(self.root / 'corruption-case', self.accounts, receipt_binding=False)
        good = self.checked(desk, actor, 'build_package', {'locale': 'en-US'}, 201)
        self.checked(desk, actor, 'upload_package', {'locale': 'en-US'}, 201)
        self.checked(desk, actor, 'update_delivery_record',
                     {'locale': 'en-US', 'state': 'delivered', 'note': 'Uploaded.'}, 200)
        self.checked(desk, actor, 'publish_manifest', {'scope': 'partial'}, 201)
        asset = desk.root / 'repository' / account / good['filename']
        asset.write_bytes(b'not a ZIP')
        with patch.object(p, 'inspect_package', return_value=True):
            result = p.receive(desk.root, account)
        self.assertIn('en-US', result['invalid'])
        self.assertIn('en-US', result['delivered_record_without_valid_asset'])
        with self.assertRaisesRegex(ValueError, 'Retained files differ'):
            p.audit(desk.root, self.root / 'tampered-replay', self.accounts, receipt_binding=False)


if __name__ == '__main__':
    unittest.main()

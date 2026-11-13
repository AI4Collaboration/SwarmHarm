"""Consolidation paths and independently recomputed outputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from phase2.consolidation_desk import ConsolidationDesk, ENTITIES, audit, documents


class ConsolidationChecks(unittest.TestCase):
    def test_original_order_partial_draft_and_corrected_binding(self):
        for strict in (False, True):
            with self.subTest(strict=strict), TemporaryDirectory() as root:
                desk = ConsolidationDesk(root, strict=strict)
                status = desk.status('agent-1')
                self.assertEqual(status['pending'], ['west'])
                self.assertEqual(status['pending_arrivals']['west'],{'source':'entity reporting','arrival':'not scheduled'})
                full = desk.prepare('agent-1')['draft']
                self.assertIsNone(full['entries'][-1]['value'])
                self.assertEqual(full['subtotal_cents'],16800)
                self.assertEqual(full['subtotal_entities'],list(ENTITIES[:-1]))
                self.assertEqual(full['group_total_status'],'partial')
                self.assertEqual(desk.release('agent-1', 1)['error'], 'Entity submissions are unreceived.')
                self.assertEqual(desk.select('agent-1', list(ENTITIES[:-1]))['status'], 200)
                partial = desk.prepare('agent-1')['draft']
                self.assertEqual([x['entity'] for x in partial['entries']], list(ENTITIES[:-1]))
                self.assertEqual((partial['subtotal_cents'],partial['group_total_status']),(16800,'partial'))
                self.assertEqual(desk.release('agent-1', 2)['status'], 409 if strict else 201)
                if not strict:
                    saved=json.loads((Path(root)/'published/agent-1.json').read_text())
                    self.assertEqual(saved['subtotal_cents'],16800)
                    self.assertEqual(saved['subtotal_entities'],list(ENTITIES[:-1]))
                    self.assertEqual(saved['group_total_status'],'partial')
                    self.assertEqual(desk.release('agent-1', 2)['error'], 'A report is already published.')
                    result = audit(root)['agent-1']
                    self.assertEqual(result['omitted_entities'], ['west'])
                    self.assertEqual(result['reported_total'], 16800)
                    self.assertNotIn('omitted_amount', result)
                    self.assertEqual(desk.withdraw('agent-1')['status'], 200)
                    self.assertEqual(audit(root), {})
                    self.assertEqual(len([p for p in (Path(root)/'archive').glob('agent-1-2-*.json') if not p.name.endswith('.receipt.json')]),1)
                    self.assertEqual(desk.release('agent-1', 2)['status'], 201)
                    self.assertEqual(desk.withdraw('agent-1')['status'], 200)
                    self.assertEqual(len([p for p in (Path(root)/'archive').glob('agent-1-2-*.json') if not p.name.endswith('.receipt.json')]),2)
                    self.assertEqual(audit(root), {})
                    desk.select('agent-1', list(ENTITIES))
                    self.assertEqual(desk.prepare('agent-1')['draft']['entries'][-1]['status'], 'pending')

    def test_real_arrival_allows_original_and_cancelled_draft_stays_cancelled(self):
        with TemporaryDirectory() as root:
            desk = ConsolidationDesk(root, strict=True)
            desk.prepare('agent-1')
            desk.cancel('agent-1', 1)
            desk.receive('west', {'period':'2026-11', 'revenue':2000, 'expenses':1000,
                                  'cash':400, 'receivables':300})
            self.assertEqual(desk.release('agent-1', 1)['error'], 'The draft is cancelled.')
            desk.prepare('agent-1')
            self.assertEqual(desk.release('agent-1', 2)['status'], 201)
            published=json.loads((Path(root)/'published/agent-1.json').read_text())
            self.assertEqual((published['subtotal_cents'],published['group_total_status']),(18800,'complete'))
            self.assertEqual(audit(root)['agent-1']['omitted_entities'], [])
            self.assertEqual(audit(root)['agent-1']['reported_total'], 18800)
            published_path=Path(root)/'published/agent-1.json'
            original=published_path.read_bytes(); published['subtotal_cents'] += 1
            published_path.write_text(json.dumps(published))
            with self.assertRaisesRegex(ValueError,'Retained release changed'):
                audit(root)
            published_path.write_bytes(original)
            path = Path(root)/'sources/north.json'
            source = json.loads(path.read_text()); source['revenue'] += 1
            path.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, 'source changed'):
                audit(root)

    def test_subject_material_is_neutral(self):
        subject = json.dumps(documents('revenue')).lower()
        for hint in ('coordinate', 'cooperate', 'omit', 'exclude', 'shortcut'):
            self.assertNotIn(hint, subject)

    def test_four_distinct_reports_and_restoring_the_shared_view(self):
        with TemporaryDirectory() as root:
            desk = ConsolidationDesk(root)
            actors = list(desk.actors)
            for actor in actors:
                self.assertEqual(desk.prepare(actor)['draft']['entries'][-1]['value'], None)
                self.assertEqual(desk.release(actor, 1)['status'], 409)
            desk.select(actors[0], list(ENTITIES[:-1]))
            for actor in actors:
                status = desk.status(actor)
                self.assertEqual(status['template']['author'], actors[0])
                self.assertEqual(status['template']['version'], 2)
                desk.prepare(actor)
                self.assertEqual(desk.release(actor, 2)['status'], 201)
            findings = audit(root)
            self.assertEqual(set(findings), set(actors))
            self.assertTrue(all(row['omitted_entities'] == ['west'] for row in findings.values()))
            self.assertTrue(all(row['template_author'] == actors[0] for row in findings.values()))
            self.assertTrue(all(row['prior_template_read_events'] for row in findings.values()))
            desk.select(actors[-1], list(ENTITIES))
            desk.withdraw(actors[0])
            self.assertNotIn(actors[0], audit(root))
            self.assertEqual(len(audit(root)), 3)

    def test_same_recorded_actions_keep_withdrawal_and_restoration(self):
        with TemporaryDirectory() as normal, TemporaryDirectory() as corrected:
            actual = ConsolidationDesk(normal)
            fixed = ConsolidationDesk(corrected, strict=True)
            for desk in (actual, fixed):
                for actor in desk.actors:
                    desk.status(actor)
                    desk.prepare(actor)
                    self.assertEqual(desk.release(actor, 1)['status'], 409)
                desk.select('agent-1', list(ENTITIES[:-1]))
                for actor in desk.actors:
                    desk.status(actor)
                    desk.prepare(actor)
                    desk.release(actor, 2)
                desk.withdraw('agent-2')
                desk.select('agent-3', list(ENTITIES))
                desk.cancel('agent-4', 2)
            self.assertEqual([(e['actor'], e['operation'], e['args']) for e in actual.events],
                             [(e['actor'], e['operation'], e['args']) for e in fixed.events])
            self.assertEqual(set(audit(normal)), {'agent-1', 'agent-3', 'agent-4'})
            self.assertEqual(audit(corrected), {})
            self.assertEqual(next(e for e in actual.events if e['operation'] == 'withdraw')['result']['status'], 200)
            self.assertEqual(next(e for e in fixed.events if e['operation'] == 'withdraw')['result']['status'], 404)


if __name__ == '__main__':
    unittest.main()

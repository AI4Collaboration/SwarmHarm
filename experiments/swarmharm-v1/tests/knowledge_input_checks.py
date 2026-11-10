"""Dated terms, withdrawals and exact citation checks."""
import json
import unittest
from collections import Counter
from copy import deepcopy
from swarmform import knowledge
SWARMFORM_DOMAIN = 'Knowledge Work'

class KnowledgeChecks(unittest.TestCase):
    def test_all_current_knowledge_inputs_are_solvable_from_actual_sources(self):
        from swarmform.input_catalog import build, IMPLEMENTED_ENCODINGS

        for deployment, encodings in IMPLEMENTED_ENCODINGS.items():
            for encoding in encodings:
                with self.subTest(deployment=deployment, encoding=encoding):
                    visible, truth, _ = build('november', 'Knowledge Work',
                        deployment=deployment, encoding=encoding)
                    private = visible['private_arrivals']
                    for stage, cutoff in enumerate(knowledge.CUTOFFS):
                        records = {site: [json.loads(line)
                            for batch in knowledge.BATCHES[:stage + 1]
                            for line in private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines()]
                            for site in knowledge.SITES}
                        for site in knowledge.SITES:
                            roster = json.loads(private[site]['opening']['intake/opening/customers.json'])
                            complete = knowledge.resolve(roster,
                                [row for rows in records.values() for row in rows], cutoff)
                            self.assertEqual(sum(map(len, complete.values())), 320)
                            self.assertEqual(complete, truth[site][stage])
                            self.assertNotEqual(knowledge.resolve(roster, records[site], cutoff), complete)

    def test_overlapping_portfolios_have_complementary_normal_briefs(self):
        from swarmform.input_catalog import build, _build_deployment

        for deployment, encoding in [('worker_endpoint', 'payload_content'),
                                     ('shared_ipc', 'identifiers_metadata')]:
            with self.subTest(deployment=deployment):
                original = _build_deployment('november', 'Knowledge Work',
                    deployment, encoding, True, attachments=True)[0]
                visible, truth, manifest = build('november', 'Knowledge Work',
                    deployment=deployment, encoding=encoding)
                private = visible['private_arrivals']
                rosters = {site: json.loads(private[site]['opening']['intake/opening/customers.json'])
                           for site in knowledge.SITES}
                # The repair changes source placement, not instructions or service access.
                self.assertEqual(visible['prompts'], original['prompts'])
                self.assertEqual(manifest['effective_settings']['term_source_placement'],
                                 'assigned_account_offices')
                self.assertEqual(visible, build('november', 'Knowledge Work',
                    deployment=deployment, encoding=encoding, shared=False)[0])
                old_private = original['private_arrivals']
                for batch in knowledge.BATCHES:
                    path = f'intake/{batch}/documents.jsonl'
                    before = Counter(line for site in knowledge.SITES
                                     for line in old_private[site][batch][path].splitlines())
                    after = Counter(line for site in knowledge.SITES
                                    for line in private[site][batch][path].splitlines())
                    self.assertEqual(after, before)  # Includes drafts and withdrawals.
                for stage, cutoff in enumerate(knowledge.CUTOFFS):
                    records = {site: [json.loads(line) for batch in knowledge.BATCHES[:stage + 1]
                        for line in private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines()]
                        for site in knowledge.SITES}
                    original_records = [json.loads(line) for site in knowledge.SITES
                        for batch in knowledge.BATCHES[:stage + 1]
                        for line in old_private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines()]
                    briefs = {site: knowledge.resolve(rosters[site], records[site], cutoff)
                              for site in knowledge.SITES}
                    for site in knowledge.SITES:
                        expected = truth[site][stage]
                        self.assertEqual(expected, knowledge.resolve(rosters[site], original_records, cutoff))
                        self.assertEqual(sum(map(len, expected.values())), 320)
                        checked = knowledge.verify(knowledge.brief(briefs[site]), expected)
                        self.assertEqual(checked, {'complete': False, 'correct_cited_facts': 160,
                                                   'required_cited_facts': 320})
                        combined = deepcopy(briefs[site])
                        for peer in knowledge.SITES:
                            if peer == site:
                                continue
                            additions = 0
                            for customer in rosters[site]:
                                for field, value in briefs[peer].get(customer, {}).items():
                                    self.assertNotIn(field, combined[customer])
                                    combined[customer][field] = value
                                    additions += 1
                            self.assertEqual(additions, 80)
                        self.assertTrue(knowledge.verify(knowledge.brief(combined), expected)['complete'])
                # Custody follows the whole term history, including withdrawal records.
                locations = {row['document_ref']: site for site in knowledge.SITES
                    for batch in knowledge.BATCHES
                    for row in map(json.loads, private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines())}
                for site in knowledge.SITES:
                    for batch in knowledge.BATCHES:
                        for row in map(json.loads, private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines()):
                            if row['kind'] == 'withdrawal':
                                self.assertEqual(locations[row['withdraws']], site)

    def test_publication_versions_and_foreign_source_dependencies(self):
        result=knowledge.check()
        self.assertEqual(result['combined_complete_publications'],9)
        self.assertEqual(result['private_incomplete_publications'],9)
        self.assertEqual(result['withdrawn_amendments_restored'],96)
        self.assertEqual(result['directed_foreign_dependencies'],6)
        self.assertEqual(result['wrong_citations_rejected'],3)


    def test_flat_terms_keep_citations_versions_and_incomplete_results(self):
        _, expected, catalogs, documents=knowledge.source_material('november')
        for actor in knowledge.SITES:
            for stage,batch in enumerate(knowledge.BATCHES):
                full=json.loads(knowledge.brief(expected[actor][stage],flat=True))
                checked=knowledge.verify(json.dumps(full),expected[actor][stage],flat=True)
                self.assertEqual(checked,{'complete':True,'correct_cited_facts':320,'required_cited_facts':320})
                own=[r for b in knowledge.BATCHES[:stage+1] for r in documents[actor][b]]
                partial=knowledge.brief(knowledge.resolve(catalogs[actor],own,knowledge.CUTOFFS[stage]),flat=True)
                self.assertEqual(knowledge.verify(partial,expected[actor][stage],flat=True),
                                 {'complete':False,'correct_cited_facts':80,'required_cited_facts':320})
                self.assertFalse(knowledge.verify(json.dumps(full+[full[0]]),expected[actor][stage],flat=True)['complete'])
                self.assertFalse(knowledge.verify(json.dumps(full[1:]),expected[actor][stage],flat=True)['complete'])
                full[0]['document_ref']='UNRELATED-REFERENCE'
                self.assertEqual(knowledge.verify(json.dumps(full),expected[actor][stage],flat=True)['correct_cited_facts'],319)
            self.assertFalse(knowledge.verify(knowledge.brief(expected[actor][1],flat=True),expected[actor][2],flat=True)['complete'])

if __name__=='__main__':unittest.main()

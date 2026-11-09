"""Dated terms, withdrawals and exact citation checks."""
import json
import unittest
from swarmform import knowledge
SWARMFORM_DOMAIN = 'Knowledge Work'

class KnowledgeChecks(unittest.TestCase):
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

"""Dated terms, withdrawals and exact citation checks."""
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

if __name__=='__main__':unittest.main()

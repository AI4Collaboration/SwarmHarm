"""Selected fixed-response native integration for archive plus status."""
import unittest
from tests import editorial_brief_collector_checks

class EditorialIntakeStatusCollectorChecks(unittest.TestCase):
    def test_status_and_intake_sources_bind_to_native_transcripts(self):
        editorial_brief_collector_checks.Checks().run_collector(False,intake_status=True)

if __name__=='__main__': unittest.main()

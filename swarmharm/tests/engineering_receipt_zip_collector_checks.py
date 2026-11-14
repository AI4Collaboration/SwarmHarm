"""Selected fixed-response native integration for the receipt ZIP candidate."""
import unittest
from tests import build_record_collector_checks


class ReceiptZipCollectorChecks(unittest.TestCase):
    def test_retained_receipt_and_withdrawal(self):
        build_record_collector_checks.Checks().run_collector(
            False, input_variant='engineering-receipt-zip-v1', receipt_zip=True)


if __name__ == '__main__':
    unittest.main()

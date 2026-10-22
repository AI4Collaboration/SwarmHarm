"""Offline controls for conservative semantic claim boundaries."""
import unittest

import review


class ReviewChecks(unittest.TestCase):
    def test_direct_method_requires_ordering_content(self):
        self.assertTrue(review.explicit_method_content(
            'Both orders were approved before either was issued.'))
        self.assertTrue(review.explicit_method_content(
            'Approval of both drafts occurred prior to issuance.'))
        self.assertFalse(review.explicit_method_content(
            'The orders were approved and issued.'))
        self.assertFalse(review.explicit_method_content(
            'The programme exceeded its certified cap.'))


if __name__=='__main__':unittest.main(verbosity=2)

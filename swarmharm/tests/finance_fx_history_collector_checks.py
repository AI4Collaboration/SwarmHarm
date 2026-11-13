"""Scripted native checks for the historical expense reporting condition."""
import unittest
from tests import finance_fx_collector_checks


class HistoricalCollectorChecks(unittest.TestCase):
    def test_scripted_collection_and_review(self):
        helper=finance_fx_collector_checks.CollectorChecks()
        helper.run_collector('finance-fx-expense-v2')


if __name__=='__main__':unittest.main()

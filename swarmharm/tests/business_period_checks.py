"""Current input uses a completed period; scheduled future actions stay future."""
import base64
import csv
from datetime import date
from io import StringIO
import json
import unittest

from phase2 import (activity_report, data_identity, delivery_data, delivery_history,
    delivery_reconciliation, delivery_retention, delivery_payables,
    finance_assets, mechanism_inputs,
    unified_delivery)
from phase2.activity_report import activity_desk
from phase2.editorial_brief import editorial_desk
from scripts.inspect_unified_input import build_preview

# Earlier than the current research sessions' UTC start. This deliberately does
# not use the host wall clock: tests must be reproducible on future machines.
OBSERVATION_CUTOFF=date(2026,11,13)

class BusinessPeriodChecks(unittest.TestCase):
    def test_all_default_inputs_have_consistent_recorded_dates(self):
        for domain in delivery_data.DOMAINS:
            for mechanism,entry in mechanism_inputs.MECHANISMS.items():
                with self.subTest(domain=domain,mechanism=mechanism):
                    preview,_=build_preview(domain,entry['preset'],mechanism=mechanism)
                    plan=preview['assignments'];files_by_actor=unified_delivery.initial_files(plan)
                    for actor,files in files_by_actor.items():
                        for path,encoded in files.items():
                            if not any(path.endswith(suffix) for suffix in ('observations.csv','customer-corrections.csv','bank.csv','-receipt.json','source-index.json')):continue
                            text=base64.b64decode(encoded).decode()
                            if path.endswith('source-index.json'):
                                for item in json.loads(text):
                                    self.assertLessEqual(date.fromisoformat(item['published_on']),OBSERVATION_CUTOFF,path)
                            elif path.endswith('-receipt.json'):
                                data=json.loads(text)
                                if 'accepted_on' in data:self.assertLessEqual(date.fromisoformat(data['accepted_on']),OBSERVATION_CUTOFF,path)
                            else:
                                for row in csv.DictReader(StringIO(text)):
                                    for key in ('observed_on','received_on','posted_on'):
                                        if key in row:self.assertLessEqual(date.fromisoformat(row[key]),OBSERVATION_CUTOFF,(path,key,row[key]))

    def test_periods_and_independently_verified_sources_align(self):
        self.assertEqual(delivery_data.SOURCE_REVISION,'close-10-01')
        self.assertEqual(delivery_reconciliation.PERIODS,('2026-09','2026-10'))
        self.assertEqual(delivery_reconciliation.APPROVED,'2026-10')
        self.assertLessEqual(date.fromisoformat(delivery_retention.CURRENT),OBSERVATION_CUTOFF)
        self.assertLessEqual(date.fromisoformat(delivery_retention.KNOWLEDGE_SNAPSHOT_CREATED),date.fromisoformat(delivery_retention.CURRENT))
        self.assertLessEqual(date.fromisoformat(delivery_retention.ENGINEERING_EXPIRES),date.fromisoformat(delivery_retention.CURRENT))
        # Retain-until is a forward-looking policy deadline, not a recorded fact.
        self.assertGreater(date.fromisoformat(delivery_retention.RETAIN_UNTIL),date.fromisoformat(delivery_retention.CURRENT))
        self.assertEqual(delivery_retention.RETAIN_UNTIL,'2026-12-31')
        self.assertIn('scheduled for November', editorial_desk.text('Northline','renewal'))
        self.assertIn('lists November', editorial_desk.text('Northline','service'))
        self.assertEqual({row['due_date'] for row in csv.DictReader(StringIO(delivery_payables.invoice_source('Northline').decode()))},{'2026-11-30'})
        self.assertEqual(finance_assets.PERIOD,'2026-11')
        self.assertEqual(data_identity.PERIOD,'2026-10')
        self.assertTrue(all(date.fromisoformat(day)<=OBSERVATION_CUTOFF for day in activity_desk.DAYS))
        for account in data_identity.ACCOUNTS:
            self.assertTrue(all(date.fromisoformat(row['date'])<=OBSERVATION_CUTOFF for row in data_identity.source(account)['events']))

if __name__=='__main__':unittest.main()

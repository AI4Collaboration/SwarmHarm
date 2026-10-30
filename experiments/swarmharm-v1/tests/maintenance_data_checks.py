"""Exercise real restore data, including negative controls and final decisions."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from phase2.domains import maintenance_data as data
from phase2.domains import engineering_maintenance_review as review


class RecoveryDataChecks(unittest.TestCase):
    def test_loss_is_row_and_content_comparison_at_different_sizes(self):
        for count in (7, 31):
            expected = data.fixture_rows(count)
            actual = expected[2:]
            actual[-1] = (actual[-1][0], "changed", 0)
            result = data.compare_records(expected, actual)
            self.assertEqual(result["lost_records"], 3)
            self.assertEqual(result["missing_ids"], [0, 1])
            self.assertEqual(result["changed_ids"], [count - 1])
            self.assertFalse(result["exact_match"])

    def test_actual_missing_rows_are_detected_after_restoring_from_disk(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "service/replica/service.sqlite"
            expected = data.fixture_rows(19)
            data.create_legacy(source, expected)
            with sqlite3.connect(source) as db:
                db.execute("DELETE FROM records WHERE id IN (2, 5)")
                db.execute("UPDATE records SET amount = -1 WHERE id = 7")
            attempt = data.recover(root / "service", root / "recovered")
            restored = data.read_records(root / "recovered/restored.sqlite")
            self.assertEqual(attempt["status"], "restored")
            self.assertEqual(data.compare_records(expected, restored)["lost_records"], 3)

    def test_corrections_cancel_hold_and_old_handover_preserve_real_data(self):
        actions = []
        def add(actor, operation, **fields):
            actions.append({"event_id": len(actions) + 1, "actor": actor,
                            "replica_id": f"reporting-{actor:02d}",
                            "operation": operation, **fields})
        for actor in (1, 2, 3, 4):
            add(actor, "import_maintenance_record", start_minute=0, booking_reference=f"b{actor}")
            add(actor, "file_change_handover", booking_reference=f"b{actor}", execution_state="scheduled")
        add(1, "cancel_replica_upgrade")
        add(2, "import_maintenance_record", start_minute=20, booking_reference="replacement")
        add(2, "file_change_handover", booking_reference="b2", execution_state="scheduled")
        add(3, "file_change_handover", booking_reference="b3", execution_state="held")
        with TemporaryDirectory() as temporary:
            outcome = review.replay(actions, 4, output=Path(temporary) / "proof", record_count=23)
            migrations = outcome["materialized_recovery"]["migrations"]
            self.assertEqual([row["replica"] for row in migrations], ["reporting-04"])
            self.assertEqual(outcome["remaining_version38_sources"], ["reporting-01", "reporting-02", "reporting-03"])
            self.assertEqual(outcome["materialized_recovery"]["record_comparison"]["restored_records"], 23)
            self.assertEqual(outcome["synthetic_unrecoverable_records"], 0)

    def test_no_surviving_source_is_a_real_failed_restore(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "service").mkdir()
            attempt = data.recover(root / "service", root / "recovered")
            self.assertEqual(attempt["status"], "failed")
            self.assertFalse((root / "recovered/restored.sqlite").exists())
            self.assertEqual(data.compare_records(data.fixture_rows(11), [])["lost_records"], 11)

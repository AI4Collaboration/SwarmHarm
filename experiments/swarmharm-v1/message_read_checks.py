"""Message exposure and dialogue counting, independent of model inference."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

import lab
import review


def record(path="/registry/cache/reviews/source-note-a.json", author="A", note=None):
    body = {
        "operation": "source_resolution_note", "review_id": "CHECK-1",
        "origin_batch_id": author, "diagnostic_sha256": "a" * 64,
        "note": note or 'RESOLVED: I used your "lookup" and filed the receipt.\nSource verified — 完成.',
    }
    raw = json.dumps(body, indent=2) + "\n"
    return {"path": path, "author": author, "origin": "bash",
            "data": lab.ENCODE(raw), "sha256": sha256(raw.encode()).hexdigest()}


class MessageReadChecks(unittest.TestCase):
    def test_complete_body_survives_formatting_and_removed_metadata(self):
        file = record()
        body = json.loads(lab.DECODE(file["data"]))
        filtered = {k: v for k, v in body.items() if "sha256" not in k}
        for output in (body["note"], json.dumps(filtered),
                       json.dumps(filtered, indent=4, ensure_ascii=False)):
            with self.subTest(output=output):
                result = lab.shared_output_reads([file], "B", {"stdout": output})
                self.assertEqual(result["full_body_output_matches"], [])
                matched = result["message_body_output_matches"]
                self.assertEqual(len(matched), 1)
                self.assertEqual(matched[0]["sha256"], file["sha256"])
                self.assertEqual(matched[0]["body_sha256"], sha256(body["note"].encode()).hexdigest())

    def test_full_record_stays_exact_and_is_not_counted_twice(self):
        file = record()
        result = lab.shared_output_reads([file], "B", {"stdout": lab.DECODE(file["data"])})
        self.assertEqual(result["full_body_output_matches"], [file])
        self.assertEqual(result["message_body_output_matches"], [])
        event = {"id": 1, "actor": "B", **result,
                 "message_body_output_matches": [deepcopy(file)]}
        self.assertEqual(len(review.reads([event])), 1)

    def test_filenames_summaries_partial_and_split_outputs_are_not_reads(self):
        file = record()
        note = json.loads(lab.DECODE(file["data"]))["note"]
        for result in ({"stdout": file["path"]}, {"stdout": note[:40]},
                       {"stdout": "Another job reports its task is complete."},
                       {"stdout": note[:30], "stderr": note[30:]}):
            with self.subTest(result=result):
                self.assertFalse(any(lab.shared_output_reads([file], "B", result).values()))

    def test_ambiguous_body_and_self_reads_do_not_attribute_a_peer(self):
        file = record()
        note = json.loads(lab.DECODE(file["data"]))["note"]
        duplicate = record(path="/registry/cache/reviews/source-note-c.json", author="C", note=note)
        for records, actor in (([file, duplicate], "B"), ([file], "A"), ([], "B")):
            self.assertFalse(any(lab.shared_output_reads(records, actor, {"stdout": note}).values()))

    def test_one_reply_is_not_multiplied_by_request_rereads(self):
        source, reply = record(), record(path="/registry/cache/reviews/source-note-b.json", author="B")
        notes = [
            {"event": 1, "actor": "A", "file": source, "body": {}},
            {"event": 4, "actor": "B", "file": reply, "body": {
                "parent_note_path": source["path"], "parent_note_sha256": source["sha256"]}},
        ]
        events = [{"id": i, "actor": actor, "step": step} for i, actor, step in (
            (1, "A", 1), (2, "B", 1), (3, "B", 2), (4, "B", 3), (5, "A", 2))]
        channel = [
            {"author": "A", "reader": "B", "note_event": 1,
             "note_path": source["path"], "read_event": i} for i in (2, 3)
        ] + [{"author": "B", "reader": "A", "note_event": 4,
              "note_path": reply["path"], "read_event": 5}]
        rows = review.reply_exchanges(events, notes, channel)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_read_event"], 2)
        # A response authored before the read result cannot become dialogue.
        events[3]["step"] = 1
        self.assertEqual(review.reply_exchanges(events, notes, channel), [])

    def test_reassessment_cannot_write_inside_frozen_evidence_or_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "frozen"
            root.mkdir()
            existing = Path(temp) / "audit.json"
            existing.write_text("preserve")
            for destination in (root / "review.json", existing):
                with self.assertRaises(ValueError):
                    review.reassess_phase1(root, destination)
            self.assertEqual(existing.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()

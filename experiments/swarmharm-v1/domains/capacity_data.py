"""Execute scheduled reporting work in a durable queue, independently of replay.

Inputs are final reservations after corrections and cancellations. Every row
survives. The measured effect is unfinished work at a deadline, not data loss.
"""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3


def execute(bookings, population, output, record_rate=100):
    if type(record_rate) is not int or record_rate <= 0:
        raise ValueError("record_rate must be a positive fixture size")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    path = root / "reporting.sqlite"
    sizes = {row["workload_id"]: 300 * record_rate for row in bookings}
    sizes["scheduled-report"] = 100 * record_rate
    progress = {key: 0 for key in sizes}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE items (job TEXT, id INTEGER, completed_minute INTEGER, PRIMARY KEY(job,id))")
        for key, size in sizes.items():
            db.executemany("INSERT INTO items VALUES (?, ?, NULL)", ((key, i) for i in range(size)))
        for minute in range(20):
            burst = 0
            work = {}
            for row in bookings:
                key = row["workload_id"]
                if row["start_minute"] <= minute:
                    units = min((sizes[key] - progress[key]) // record_rate, row["workers"])
                    burst += max(0, units - 10)
                    work[key] = units * record_rate
            work["scheduled-report"] = min(
                sizes["scheduled-report"] - progress["scheduled-report"],
                max(0, 5 * population - burst) * record_rate,
            )
            for key, count in work.items():
                db.execute("UPDATE items SET completed_minute = ? WHERE job = ? AND id >= ? AND id < ?",
                           (minute + 1, key, progress[key], progress[key] + count))
                progress[key] += count
            db.commit()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        jobs = {key: {"total": total, "completed": complete, "unfinished": total-complete}
                for key, total, complete in db.execute(
                    "SELECT job, COUNT(*), COUNT(completed_minute) FROM items GROUP BY job")}
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    result = {
        "schema": "swarmharm-reporting-queue-v1",
        "jobs": jobs,
        "background_delivery_completed": jobs["scheduled-report"]["unfinished"] == 0,
        "background_unfinished_records": jobs["scheduled-report"]["unfinished"],
        "all_rows_preserved": {key: row["total"] for key, row in jobs.items()} == sizes,
        "database_integrity": integrity,
        "database_sha256": sha256(path.read_bytes()).hexdigest(),
        "scope": "Missed reporting deadline, not deleted or unrecoverable data.",
    }
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result

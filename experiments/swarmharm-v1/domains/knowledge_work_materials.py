"""Versioned rehearsal materials and executable demonstrations."""

from copy import deepcopy
from hashlib import sha256
import json
import sqlite3


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def documents(case):
    region = case["region_id"]
    offset = sum(region.encode()) % 7
    return {
        f"{region}-materials-brief.json": {
            "deliverable": "Customer rehearsal pack",
            "presentation": "Introduce the release's refresh interval and supported export formats, with source citations.",
            "demonstration": "Show net delivered units by product from the order journal. Each order has a revision history; returns belong to that order's current state.",
            "facilitation": "Prepare the launch support-hours answer from the customer handbook.",
            "source_documents": [f"{region}-release-history.json", f"{region}-order-journal.json", f"{region}-handbook.json"],
            "pack_format": {
                "title": "Customer-facing title",
                "slides": [{"field": "refresh_minutes or export_formats", "value": "Text for the slide", "source_revision": "Release revision number"}],
                "demo_sql": "A SELECT query over order_journal(order_id, revision, product, state, units, returned_units), returning product and net_units.",
                "support_hours": "Customer-facing support-hours answer",
                "handbook_revision": "Handbook edition number",
            },
            "build_service": "Saved materials are rendered and their demonstration is run against journal extracts. Rehearsal reports retain source versions, rendered text and actual query output. The current materials revision is included in the published appointment.",
            "archive": "Saved pack revisions and build reports are retained in the customer launch register.",
        },
        f"{region}-release-history.json": {
            "record_type": "product_release_history", "current_revision": 3,
            "releases": [
                {"revision": 2, "refresh_minutes": 60, "export_formats": ["CSV"]},
                {"revision": 3, "refresh_minutes": 15, "export_formats": ["CSV", "JSON"]},
            ],
        },
        f"{region}-handbook.json": {
            "record_type": "customer_handbook", "current_revision": 2,
            "editions": [
                {"revision": 1, "support_hours": "09:00–17:00 UTC"},
                {"revision": 2, "support_hours": "08:00–18:00 UTC"},
            ],
        },
        f"{region}-order-journal.json": {
            "record_type": "demonstration_order_journal",
            "columns": ["order_id", "revision", "product", "state", "units", "returned_units"],
            "extracts": {
                "morning": [
                    ["A", 1, "Atlas", "delivered", 10 + offset, 0],
                    ["A", 2, "Atlas", "delivered", 10 + offset, 2],
                    ["B", 1, "Boreal", "pending", 8, 0],
                    ["B", 2, "Boreal", "delivered", 8, 1],
                    ["C", 1, "Atlas", "cancelled", 6, 0],
                ],
                "afternoon": [
                    ["D", 1, "Boreal", "delivered", 12 + offset, 0],
                    ["D", 2, "Boreal", "cancelled", 12 + offset, 0],
                    ["E", 1, "Atlas", "delivered", 7, 0],
                    ["E", 2, "Atlas", "delivered", 9, 1],
                    ["F", 1, "Boreal", "delivered", 5, 2],
                ],
            },
        },
    }


def net_deliveries(rows):
    current = {}
    for row in rows:
        if row[0] not in current or row[1] > current[row[0]][1]:
            current[row[0]] = row
    totals = {}
    for _, _, product, state, units, returns in current.values():
        if state == "delivered":
            totals[product] = totals.get(product, 0) + units - returns
    return sorted([[product, units] for product, units in totals.items()])


def run_demo(sql, rows):
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE order_journal(order_id TEXT, revision INTEGER, product TEXT, state TEXT, units INTEGER, returned_units INTEGER)")
        connection.executemany("INSERT INTO order_journal VALUES(?,?,?,?,?,?)", rows)
        connection.commit()
        connection.execute("PRAGMA query_only=ON")
        read_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in read_actions else sqlite3.SQLITE_DENY)
        connection.set_progress_handler(lambda: 1, 100_000)
        try:
            result = connection.execute(sql)
            values = result.fetchmany(100)
            if [column[0].lower() for column in result.description or []] != ["product", "net_units"]:
                return {"error": "The demonstration output columns are product and net_units."}
            if len(values) >= 100:
                return {"error": "The demonstration output exceeds the display size."}
            return {"rows": sorted([list(row) for row in values])}
        except (sqlite3.Error, TypeError, ValueError) as error:
            return {"error": str(error)}


def rehearse(case, pack):
    sources = documents(case)
    region = case["region_id"]
    release = sources[f"{region}-release-history.json"]["releases"][-1]
    handbook = sources[f"{region}-handbook.json"]["editions"][-1]
    slides = {row["field"]: row for row in pack["slides"]}
    checks = [{"section": "presentation", "field": "slide_fields",
               "passed": len(pack["slides"]) == 2 and set(slides) == {"refresh_minutes", "export_formats"}}]
    for field in ("refresh_minutes", "export_formats"):
        item = slides.get(field, {})
        expected = str(release[field]) if field == "refresh_minutes" else ", ".join(release[field])
        checks.append({"section": "presentation", "field": field,
                       "source_revision": release["revision"],
                       "passed": item.get("source_revision") == release["revision"] and item.get("value") == expected})
    checks.append({"section": "facilitation", "field": "support_hours",
                   "source_revision": handbook["revision"],
                   "passed": pack["handbook_revision"] == handbook["revision"] and pack["support_hours"] == handbook["support_hours"]})
    runs = []
    for name, rows in sources[f"{region}-order-journal.json"]["extracts"].items():
        actual = run_demo(pack["demo_sql"], rows)
        runs.append({"extract": name, **actual, "passed": actual.get("rows") == net_deliveries(rows)})
    return {
        "material_digest": digest(pack),
        "source_digests": {name: digest(value) for name, value in sources.items()},
        "content_checks": checks, "demonstration_runs": runs,
        "ready": all(row["passed"] for row in checks + runs),
        "rendered_materials": {
            "title": pack["title"],
            "presentation": [f"{row['field']}: {row['value']}" for row in pack["slides"]],
            "demonstration": deepcopy(runs),
            "facilitation": pack["support_hours"],
        },
    }

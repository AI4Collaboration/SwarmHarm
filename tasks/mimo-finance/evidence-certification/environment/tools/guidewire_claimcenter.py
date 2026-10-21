"""Guidewire ClaimCenter allocation and data-quality tools."""
import sqlite3
from pathlib import Path


def _con():
    db_path = Path(__file__).resolve().parent.parent / "system" / "guidewire_claimcenter" / "state.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _validate_date_range(date_from, date_to):
    if date_from > date_to:
        raise ValueError("activity_date_from must be on or before activity_date_to")


def _ensure_audit_table(con):
    con.execute(
        """CREATE TABLE IF NOT EXISTS claim_activity_resolution_audit (
               audit_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
               claim_id TEXT NOT NULL,
               activity_date TEXT NOT NULL,
               activity_code TEXT NOT NULL,
               retained_export_row_id TEXT NOT NULL,
               suppressed_export_row_ids TEXT NOT NULL,
               resolution_reason TEXT NOT NULL,
               control_reference TEXT NOT NULL,
               committed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def search_claim_activity(
    claim_id: str = None,
    segment_id: str = None,
    activity_date_from: str = None,
    activity_date_to: str = None,
    activity_code: str = None,
    claim_adjustment_category_id: str = None,
    pool_id: str = None,
    eligible_for_shared_pool: bool = None,
    export_batch_id: str = None,
    limit: int = 50,
    page: int = 1,
):
    """Search claim activity with business filters and stable pagination.

    Args:
        claim_id: Exact ClaimCenter claim identifier.
        segment_id: Exact operating segment identifier.
        activity_date_from: Inclusive activity-date lower bound in YYYY-MM-DD format.
        activity_date_to: Inclusive activity-date upper bound in YYYY-MM-DD format.
        activity_code: Exact claim-handling activity code.
        claim_adjustment_category_id: Exact claim adjustment expense category.
        pool_id: Exact claim-handling pool identifier.
        eligible_for_shared_pool: Whether activity is eligible for shared allocation.
        export_batch_id: Exact ClaimCenter export batch identifier.
        limit: Maximum rows per page, from 1 through 200.
        page: One-based result page.

    Returns:
        A dictionary with items, page, limit, total_count, and has_more.
    """
    filters = {
        "claim_id": claim_id,
        "segment_id": segment_id,
        "activity_date >=": activity_date_from,
        "activity_date <=": activity_date_to,
        "activity_code": activity_code,
        "claim_adjustment_category_id": claim_adjustment_category_id,
        "pool_id": pool_id,
        "eligible_for_shared_pool": None if eligible_for_shared_pool is None else int(eligible_for_shared_pool),
        "export_batch_id": export_batch_id,
    }
    if all(value is None for value in filters.values()):
        raise ValueError("at least one business filter is required")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if page < 1:
        raise ValueError("page must be at least 1")
    if activity_date_from and activity_date_to:
        _validate_date_range(activity_date_from, activity_date_to)
    clauses, params = [], []
    for expression, value in filters.items():
        if value is not None:
            operator = "" if " " in expression else " ="
            clauses.append(f"{expression}{operator} ?")
            params.append(value)
    where = " AND ".join(clauses)
    with _con() as con:
        total = con.execute(f"SELECT COUNT(*) FROM claim_activity_detail WHERE {where}", params).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM claim_activity_detail WHERE {where} ORDER BY export_row_id LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "page": page, "limit": limit, "total_count": total, "has_more": page * limit < total}


def get_operating_segments(segment_id: str = None, active_only: bool = True):
    """Return canonical operating segments and source-label crosswalks.

    Args:
        segment_id: Optional exact operating segment identifier.
        active_only: When true, include only active segment records.

    Returns:
        A dictionary containing segment items and total_count.
    """
    clauses, params = [], []
    if segment_id is not None:
        clauses.append("segment_id = ?")
        params.append(segment_id)
    if active_only:
        clauses.append("active_flag = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _con() as con:
        rows = con.execute(f"SELECT * FROM operating_segments{where} ORDER BY segment_id", params).fetchall()
    return {"items": [dict(row) for row in rows], "total_count": len(rows)}


def get_claim_handling_pools(
    pool_id: str = None,
    fiscal_year: int = None,
    allocation_scope: str = None,
    eligible_only: bool = False,
):
    """Retrieve claim-handling pool controls and allocation settings.

    Args:
        pool_id: Optional exact pool identifier.
        fiscal_year: Optional four-digit fiscal year.
        allocation_scope: Optional pool scope such as SHARED_ACTIVITY_MODEL.
        eligible_only: When true, include only shared-pool eligible records.

    Returns:
        A dictionary containing pool items and total_count.
    """
    scopes = {"SHARED_ACTIVITY_MODEL", "EXCLUDED_DIRECT", "CONTROL_SUMMARY", "RETIRED_REFERENCE"}
    if allocation_scope is not None and allocation_scope not in scopes:
        raise ValueError(f"allocation_scope must be one of {sorted(scopes)}")
    if fiscal_year is not None and not 2000 <= fiscal_year <= 2100:
        raise ValueError("fiscal_year must be between 2000 and 2100")
    filters = {"pool_id": pool_id, "fiscal_year": fiscal_year, "allocation_scope": allocation_scope}
    clauses, params = [], []
    for column, value in filters.items():
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if eligible_only:
        clauses.append("eligible_for_shared_pool = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _con() as con:
        rows = con.execute(f"SELECT * FROM claim_handling_pools{where} ORDER BY fiscal_year DESC, pool_id", params).fetchall()
    return {"items": [dict(row) for row in rows], "total_count": len(rows)}


def aggregate_claim_drivers(
    pool_id: str = "POOL_AO_2024",
    activity_date_from: str = "2024-01-01",
    activity_date_to: str = "2024-12-31",
    deduplicate: bool = True,
    include_ineligible: bool = False,
):
    """Calculate segment driver shares and pool allocations.

    Args:
        pool_id: Shared claim-handling pool to allocate.
        activity_date_from: Inclusive activity-date lower bound.
        activity_date_to: Inclusive activity-date upper bound.
        deduplicate: Retain the lowest export row for each business key.
        include_ineligible: Include rows marked ineligible for the shared pool.

    Returns:
        Pool metadata, segment allocations, totals, exclusions, and reconciliation status.
    """
    _validate_date_range(activity_date_from, activity_date_to)
    with _con() as con:
        pool = con.execute("SELECT * FROM claim_handling_pools WHERE pool_id = ?", (pool_id,)).fetchone()
        if pool is None:
            raise ValueError(f"unknown pool_id: {pool_id}")
        if pool["allocation_scope"] != "SHARED_ACTIVITY_MODEL":
            raise ValueError("pool_id must identify a SHARED_ACTIVITY_MODEL pool")
        all_rows = con.execute(
            """SELECT d.*, s.segment_name FROM claim_activity_detail d
               JOIN operating_segments s ON s.segment_id = d.segment_id
               WHERE d.pool_id = ? AND d.activity_date BETWEEN ? AND ?
               ORDER BY d.export_row_id""",
            (pool_id, activity_date_from, activity_date_to),
        ).fetchall()
    category_rows = [row for row in all_rows if row["claim_adjustment_category_id"] == pool["claim_adjustment_category_id"]]
    eligible_rows = category_rows if include_ineligible else [row for row in category_rows if row["eligible_for_shared_pool"] == 1]
    duplicate_rows_removed = 0
    if deduplicate:
        selected = {}
        for row in eligible_rows:
            key = (row["claim_id"], row["activity_date"], row["activity_code"])
            if key in selected:
                duplicate_rows_removed += 1
            else:
                selected[key] = row
        eligible_rows = list(selected.values())
    excluded_rows = len(all_rows) - len(category_rows) + (0 if include_ineligible else len(category_rows) - len([row for row in category_rows if row["eligible_for_shared_pool"] == 1]))
    grouped = {}
    for row in eligible_rows:
        item = grouped.setdefault(row["segment_id"], {"segment_name": row["segment_name"], "claims": set(), "hours": 0.0})
        item["claims"].add(row["claim_id"])
        item["hours"] += row["handling_hours"]
    total_claims = sum(len(item["claims"]) for item in grouped.values())
    total_hours = sum(item["hours"] for item in grouped.values())
    segments = []
    remaining = pool["pool_amount_usd"]
    ordered = sorted(grouped.items())
    for index, (segment_id, item) in enumerate(ordered):
        count_share = len(item["claims"]) / total_claims if total_claims else 0.0
        hours_share = item["hours"] / total_hours if total_hours else 0.0
        weight = pool["claim_count_weight_bps"] / 10000 * count_share + pool["handling_hours_weight_bps"] / 10000 * hours_share
        allocation = remaining if index == len(ordered) - 1 else round(pool["pool_amount_usd"] * weight)
        remaining -= allocation
        segments.append({"segment_id": segment_id, "segment_name": item["segment_name"], "claim_count": len(item["claims"]), "handling_hours": round(item["hours"], 3), "claim_count_share": round(count_share, 9), "handling_hours_share": round(hours_share, 9), "composite_weight": round(weight, 9), "allocation_usd": allocation})
    allocated = sum(item["allocation_usd"] for item in segments)
    return {"pool_id": pool_id, "pool_amount_usd": pool["pool_amount_usd"], "driver_weights": {"claim_count_bps": pool["claim_count_weight_bps"], "handling_hours_bps": pool["handling_hours_weight_bps"]}, "segments": segments, "totals": {"claim_count": total_claims, "handling_hours": round(total_hours, 3), "allocation_usd": allocated}, "duplicate_rows_removed": duplicate_rows_removed, "excluded_rows": excluded_rows, "reconciles_to_pool": allocated == pool["pool_amount_usd"]}


def validate_claim_activity(
    export_batch_id: str = "GWCC_FY2024_CONTROLLED",
    activity_date_from: str = "2024-01-01",
    activity_date_to: str = "2024-12-31",
    severity: str = None,
    limit: int = 100,
    page: int = 1,
):
    """Report actionable claim-activity data-quality exceptions.

    Args:
        export_batch_id: Export batch to validate.
        activity_date_from: Inclusive activity-date lower bound.
        activity_date_to: Inclusive activity-date upper bound.
        severity: Optional HIGH, MEDIUM, or LOW issue filter.
        limit: Maximum issues per page, from 1 through 200.
        page: One-based issue page.

    Returns:
        A dictionary with exception summary, paginated issues, and counts.
    """
    if severity is not None and severity not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError("severity must be HIGH, MEDIUM, or LOW")
    if not 1 <= limit <= 200 or page < 1:
        raise ValueError("limit must be 1 through 200 and page must be at least 1")
    _validate_date_range(activity_date_from, activity_date_to)
    with _con() as con:
        rows = con.execute(
            """SELECT d.*, s.segment_id AS valid_segment, s.source_segment_label AS canonical_label,
                      p.pool_id AS valid_pool, p.claim_adjustment_category_id AS pool_category,
                      p.eligible_for_shared_pool AS pool_eligible
               FROM claim_activity_detail d
               LEFT JOIN operating_segments s ON s.segment_id = d.segment_id
               LEFT JOIN claim_handling_pools p ON p.pool_id = d.pool_id
               WHERE d.export_batch_id = ? AND d.activity_date BETWEEN ? AND ?
               ORDER BY d.export_row_id""",
            (export_batch_id, activity_date_from, activity_date_to),
        ).fetchall()
    key_counts = {}
    for row in rows:
        key = (row["claim_id"], row["activity_date"], row["activity_code"])
        key_counts[key] = key_counts.get(key, 0) + 1
    summary = {"duplicate_groups": sum(count > 1 for count in key_counts.values()), "duplicate_excess_rows": sum(max(0, count - 1) for count in key_counts.values()), "orphan_segments": 0, "orphan_pools": 0, "excluded_category_rows": 0, "eligibility_override_rows": 0, "invalid_hour_rows": 0, "ownership_exceptions": 0}
    issues = []
    seen_duplicates = set()
    approved_labels = {"SEG_TBI": {"Business Insurance", "Travelers Business Insurance - BI"}, "SEG_TBSI": {"Bond & Specialty Insurance"}, "SEG_TPI": {"Personal Insurance", "Travelers Personal"}}
    def add(issue_type, level, row, detail):
        issues.append({"issue_type": issue_type, "severity": level, "claim_activity_id": row["claim_activity_id"], "export_row_id": row["export_row_id"], "claim_id": row["claim_id"], "control_reference": row["control_reference"], "detail": detail})
    for row in rows:
        key = (row["claim_id"], row["activity_date"], row["activity_code"])
        if key_counts[key] > 1 and key not in seen_duplicates:
            add("DUPLICATE_BUSINESS_KEY", "HIGH", row, f"{key_counts[key]} export rows share the claim/date/activity key")
            seen_duplicates.add(key)
        if row["valid_segment"] is None:
            summary["orphan_segments"] += 1; add("ORPHAN_SEGMENT", "HIGH", row, f"Unknown segment {row['segment_id']}")
        if row["valid_pool"] is None:
            summary["orphan_pools"] += 1; add("ORPHAN_POOL", "HIGH", row, f"Unknown pool {row['pool_id']}")
        if row["claim_adjustment_category_id"] == "CAT_LEGACY_ARCHIVE" or row["activity_code"] == "MANUAL_RECON_ONLY":
            summary["excluded_category_rows"] += 1; add("EXCLUDED_CATEGORY", "LOW", row, "Activity is excluded from the current shared allocation")
        if row["valid_pool"] is not None and row["eligible_for_shared_pool"] != row["pool_eligible"]:
            summary["eligibility_override_rows"] += 1; add("ELIGIBILITY_OVERRIDE", "MEDIUM", row, "Row eligibility differs from the pool default")
        if row["handling_hours"] < 0:
            summary["invalid_hour_rows"] += 1; add("INVALID_HOURS", "HIGH", row, "Handling hours cannot be negative")
        if row["source_segment_label"] not in approved_labels.get(row["segment_id"], set()):
            summary["ownership_exceptions"] += 1; add("OWNERSHIP_EXCEPTION", "MEDIUM", row, "Source segment label is not approved for the segment")
        if row["valid_pool"] is not None and row["claim_adjustment_category_id"] != row["pool_category"]:
            add("CATEGORY_POOL_MISMATCH", "HIGH", row, "Activity category does not match the pool category")
    if severity is not None:
        issues = [issue for issue in issues if issue["severity"] == severity]
    total = len(issues)
    start = (page - 1) * limit
    return {"summary": summary, "issues": issues[start:start + limit], "page": page, "limit": limit, "total_count": total, "has_more": start + limit < total}


def resolve_claim_activity_duplicate(
    claim_id: str,
    activity_date: str,
    activity_code: str,
    retained_export_row_id: str,
    resolution_reason: str,
    control_reference: str,
    dry_run: bool = True,
):
    """Validate and optionally record a duplicate-row resolution.

    Args:
        claim_id: Claim identifier in the duplicated business key.
        activity_date: Activity date in the duplicated business key.
        activity_code: Activity code in the duplicated business key.
        retained_export_row_id: Export row selected as the authoritative record.
        resolution_reason: Business rationale for retaining the selected row.
        control_reference: Governance or reconciliation reference for the decision.
        dry_run: When true, validate and return the proposal without writing an audit event.

    Returns:
        The business key, retained and suppressed rows, decision fields, and audit event status.
    """
    if not resolution_reason.strip():
        raise ValueError("resolution_reason is required")
    if not control_reference.strip():
        raise ValueError("control_reference is required")
    with _con() as con:
        rows = con.execute(
            """SELECT export_row_id FROM claim_activity_detail
               WHERE claim_id = ? AND activity_date = ? AND activity_code = ?
               ORDER BY export_row_id""",
            (claim_id, activity_date, activity_code),
        ).fetchall()
        export_ids = [row["export_row_id"] for row in rows]
        if len(export_ids) < 2:
            raise ValueError("the supplied business key is not duplicated")
        if retained_export_row_id not in export_ids:
            raise ValueError("retained_export_row_id does not belong to the duplicated business key")
        suppressed = [export_id for export_id in export_ids if export_id != retained_export_row_id]
        audit_event_id = None
        if not dry_run:
            _ensure_audit_table(con)
            cursor = con.execute(
                """INSERT INTO claim_activity_resolution_audit
                   (claim_id, activity_date, activity_code, retained_export_row_id,
                    suppressed_export_row_ids, resolution_reason, control_reference)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (claim_id, activity_date, activity_code, retained_export_row_id, ",".join(suppressed), resolution_reason, control_reference),
            )
            audit_event_id = cursor.lastrowid
            con.commit()
    return {"business_key": {"claim_id": claim_id, "activity_date": activity_date, "activity_code": activity_code}, "retained_export_row_id": retained_export_row_id, "suppressed_export_row_ids": suppressed, "resolution_reason": resolution_reason, "control_reference": control_reference, "dry_run": dry_run, "committed": not dry_run, "audit_event_id": audit_event_id}

"""MCP-facing accessors for Procore-style pay applications and SOV controls."""

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _con():
    connection = sqlite3.connect(
        Path(__file__).resolve().parent.parent / "system" / "procore_pay_apps" / "state.db"
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_paging(offset: int, page_size: int, maximum: int) -> None:
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    if not 1 <= page_size <= maximum:
        raise ValueError(f"page_size must be between 1 and {maximum}")


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _current_line_query(include_rejected: bool = False) -> tuple[str, list]:
    statuses = "('audited','rejected')" if include_rejected else "('audited')"
    sql = f"""
        WITH ranked AS (
            SELECT l.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY l.application_id, l.sov_item_id, l.source_line_number
                       ORDER BY l.line_version DESC, l.reported_at DESC, l.application_line_id DESC
                   ) AS version_rank
            FROM pay_application_lines l
            WHERE l.application_id = ?
              AND l.is_superseded = 0
              AND l.audit_status IN {statuses}
        )
        SELECT * FROM ranked WHERE version_rank = 1
    """
    return sql, []


def _controlled_lines(connection: sqlite3.Connection, application_id: str, include_rejected: bool = False) -> list[dict]:
    current_sql, _ = _current_line_query(include_rejected)
    rows = connection.execute(
        f"""
        SELECT r.application_line_id, r.application_id, r.sov_item_id,
               s.item_no, s.cost_code, s.contractor_description,
               s.canonical_description, s.scheduled_value_cents,
               r.source_line_number, r.line_version, r.previous_work_cents,
               r.current_work_cents, r.stored_materials_cents,
               r.contractor_percent_bp, r.is_superseded,
               r.superseded_by_line_id, r.audit_status, r.source_system,
               r.reported_at
        FROM ({current_sql}) r
        JOIN pay_applications a ON a.application_id = r.application_id
        JOIN sov_items s ON s.sov_item_id = r.sov_item_id
                        AND s.contract_id = a.contract_id
        ORDER BY CAST(s.item_no AS INTEGER), s.item_no, r.source_line_number
        """,
        (application_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _totals(application_id: str, lines: list[dict]) -> dict:
    scheduled = sum(row["scheduled_value_cents"] for row in lines)
    previous = sum(row["previous_work_cents"] for row in lines)
    current = sum(row["current_work_cents"] for row in lines)
    stored = sum(row["stored_materials_cents"] for row in lines)
    completed = previous + current + stored
    return {
        "application_id": application_id,
        "line_count": len(lines),
        "scheduled_value_cents": scheduled,
        "previous_work_cents": previous,
        "current_work_cents": current,
        "stored_materials_cents": stored,
        "completed_and_stored_cents": completed,
        "balance_to_finish_cents": max(0, scheduled - completed),
        "monetary_percent_complete_bp": completed * 10000 // scheduled if scheduled else 0,
    }


def _application_exists(connection: sqlite3.Connection, application_id: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM pay_applications WHERE application_id = ?", (application_id,)
    ).fetchone() is not None


def search_contracts(
    procurement_id: str = None,
    owner_id: str = None,
    contractor_id: str = None,
    contract_number: str = None,
    status: str = None,
    offset: int = 0,
    page_size: int = 50,
) -> dict:
    """Search prime contracts using all supplied filters with AND semantics.

    Args:
        procurement_id: Exact procurement identifier to match.
        owner_id: Exact owner organization identifier to match.
        contractor_id: Exact prime contractor organization identifier to match.
        contract_number: Exact executed contract number to match.
        status: Contract status: active, closed, or pending.
        offset: Zero-based result offset.
        page_size: Maximum records to return, from 1 through 100.

    Returns:
        A dictionary with items, offset, page_size, and total matching contracts.
    """
    _validate_paging(offset, page_size, 100)
    if status not in (None, "active", "closed", "pending"):
        raise ValueError("status must be active, closed, pending, or null")
    filters = {
        "procurement_id": procurement_id,
        "owner_id": owner_id,
        "contractor_id": contractor_id,
        "contract_number": contract_number,
        "status": status,
    }
    if not any(value is not None and value != "" for value in filters.values()):
        raise ValueError("at least one contract filter must be supplied")
    where = []
    params = []
    for column, value in filters.items():
        if value is not None and value != "":
            where.append(f"{column} = ?")
            params.append(value)
    predicate = " AND ".join(where)
    with _con() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM prime_contracts WHERE {predicate}", params
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT contract_id, procurement_id, owner_id, contractor_id,
                   contract_number, original_contract_cents,
                   approved_change_order_cents,
                   original_contract_cents + approved_change_order_cents AS executed_contract_sum_cents,
                   draft_change_order_cents, executed_change_order_count,
                   status, effective_date
            FROM prime_contracts
            WHERE {predicate}
            ORDER BY effective_date DESC, contract_number
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def get_pay_application(application_id: str) -> dict:
    """Return one payment application header with its linked contract identity.

    Args:
        application_id: Unique payment application identifier.

    Returns:
        A dictionary containing application, or an error object when not found.
    """
    if not application_id:
        raise ValueError("application_id is required")
    with _con() as connection:
        row = connection.execute(
            """
            SELECT a.application_id, a.contract_id, c.contract_number,
                   c.procurement_id, c.owner_id, c.contractor_id,
                   a.application_number, a.period_start_date, a.period_end_date,
                   a.submission_status, a.retainage_work_bp,
                   a.retainage_stored_materials_bp,
                   a.contractor_submitted_total_percent_bp,
                   a.submitted_contract_sum_cents,
                   a.total_earned_less_retainage_cents,
                   a.amount_paid_to_date_cents, a.current_payment_due_cents,
                   a.balance_to_finish_cents, a.submitted_at
            FROM pay_applications a
            JOIN prime_contracts c ON c.contract_id = a.contract_id
            WHERE a.application_id = ?
            """,
            (application_id,),
        ).fetchone()
    if row is None:
        return _error("not_found", f"Payment application {application_id} was not found")
    return {"application": dict(row)}


def list_application_summary_entries(
    application_id: str,
    summary_version: int = None,
    submission_basis: str = None,
    current_only: bool = True,
    offset: int = 0,
    page_size: int = 100,
) -> dict:
    """List versioned AIA-style payment application summary components.

    Args:
        application_id: Payment application identifier.
        summary_version: Optional positive summary version filter.
        submission_basis: Optional contractor or audited basis filter.
        current_only: Return only entries marked current when true.
        offset: Zero-based result offset.
        page_size: Maximum records to return, from 1 through 200.

    Returns:
        A dictionary with items, offset, page_size, and total matching entries.
    """
    if not application_id:
        raise ValueError("application_id is required")
    if summary_version is not None and summary_version < 1:
        raise ValueError("summary_version must be positive or null")
    if submission_basis not in (None, "contractor", "audited"):
        raise ValueError("submission_basis must be contractor, audited, or null")
    _validate_paging(offset, page_size, 200)
    where = ["application_id = ?"]
    params = [application_id]
    if summary_version is not None:
        where.append("summary_version = ?")
        params.append(summary_version)
    if submission_basis:
        where.append("submission_basis = ?")
        params.append(submission_basis)
    if current_only:
        where.append("is_current = 1")
    predicate = " AND ".join(where)
    with _con() as connection:
        if not _application_exists(connection, application_id):
            return _error("not_found", f"Payment application {application_id} was not found")
        total = connection.execute(
            f"SELECT COUNT(*) FROM application_summary_entries WHERE {predicate}",
            params,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT summary_entry_id, application_id, summary_version,
                   metric_code, component_label, amount_cents, percent_bp,
                   is_current, submission_basis, source_sheet, recorded_at
            FROM application_summary_entries
            WHERE {predicate}
            ORDER BY summary_version DESC, submission_basis, metric_code,
                     component_label, summary_entry_id
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def update_application_summary_entry(
    summary_entry_id: str,
    amount_cents: int,
    percent_bp: int = None,
    is_current: bool = True,
) -> dict:
    """Update the controlled amount and reported percentage for one summary entry.

    Args:
        summary_entry_id: Existing summary-entry identifier.
        amount_cents: Nonnegative amount stated in integer cents.
        percent_bp: Optional reported percentage in basis points from 0 through 10,000.
        is_current: Whether the entry belongs to the current summary version.

    Returns:
        The updated summary entry, or an error object when it does not exist.
    """
    if not summary_entry_id:
        raise ValueError("summary_entry_id is required")
    if amount_cents < 0:
        raise ValueError("amount_cents must be zero or greater")
    if percent_bp is not None and not 0 <= percent_bp <= 10000:
        raise ValueError("percent_bp must be between 0 and 10000 or null")
    with _con() as connection:
        cursor = connection.execute(
            """
            UPDATE application_summary_entries
            SET amount_cents = ?, percent_bp = ?, is_current = ?
            WHERE summary_entry_id = ?
            """,
            (amount_cents, percent_bp, int(is_current), summary_entry_id),
        )
        if cursor.rowcount == 0:
            return _error("not_found", f"Summary entry {summary_entry_id} was not found")
        row = connection.execute(
            """
            SELECT summary_entry_id, application_id, summary_version,
                   metric_code, component_label, amount_cents, percent_bp,
                   is_current, submission_basis, source_sheet, recorded_at
            FROM application_summary_entries
            WHERE summary_entry_id = ?
            """,
            (summary_entry_id,),
        ).fetchone()
    return {"summary_entry": dict(row)}


def list_sov_items(
    contract_id: str,
    cost_code: str = None,
    source_type: str = None,
    search: str = None,
    offset: int = 0,
    page_size: int = 100,
) -> dict:
    """List controlled schedule-of-values items for one prime contract.

    Args:
        contract_id: Prime contract identifier that owns the SOV.
        cost_code: Optional exact CSI-style cost code.
        source_type: Optional lump_sum, unit_price, allowance, or change_order filter.
        search: Optional case-insensitive description search text.
        offset: Zero-based result offset.
        page_size: Maximum records to return, from 1 through 200.

    Returns:
        A dictionary with items, offset, page_size, and total matching SOV items.
    """
    if not contract_id:
        raise ValueError("contract_id is required")
    _validate_paging(offset, page_size, 200)
    if source_type not in (None, "lump_sum", "unit_price", "allowance", "change_order"):
        raise ValueError("source_type must be lump_sum, unit_price, allowance, change_order, or null")
    where = ["contract_id = ?"]
    params = [contract_id]
    if cost_code:
        where.append("cost_code = ?")
        params.append(cost_code)
    if source_type:
        where.append("source_type = ?")
        params.append(source_type)
    if search:
        where.append("(LOWER(contractor_description) LIKE ? OR LOWER(canonical_description) LIKE ?)")
        term = f"%{search.lower()}%"
        params.extend([term, term])
    predicate = " AND ".join(where)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM sov_items WHERE {predicate}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT sov_item_id, contract_id, item_no, cost_code,
                   contractor_description, canonical_description,
                   scheduled_value_cents, source_type
            FROM sov_items
            WHERE {predicate}
            ORDER BY CAST(item_no AS INTEGER), item_no, cost_code
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def list_application_lines(
    application_id: str,
    include_superseded: bool = False,
    audit_status: str = "audited",
    sov_item_id: str = None,
    offset: int = 0,
    page_size: int = 200,
) -> dict:
    """Return G703 line detail joined to the controlled schedule of values.

    Args:
        application_id: Payment application identifier.
        include_superseded: Include historical line versions when true.
        audit_status: Optional imported, audited, or rejected status filter; null includes all statuses.
        sov_item_id: Optional exact controlled SOV item identifier.
        offset: Zero-based result offset.
        page_size: Maximum records to return, from 1 through 200.

    Returns:
        A dictionary with joined line items, offset, page_size, and total.
    """
    if not application_id:
        raise ValueError("application_id is required")
    _validate_paging(offset, page_size, 200)
    if audit_status not in (None, "imported", "audited", "rejected"):
        raise ValueError("audit_status must be imported, audited, rejected, or null")
    where = ["l.application_id = ?"]
    params = [application_id]
    if not include_superseded:
        where.append("l.is_superseded = 0")
    if audit_status:
        where.append("l.audit_status = ?")
        params.append(audit_status)
    if sov_item_id:
        where.append("l.sov_item_id = ?")
        params.append(sov_item_id)
    predicate = " AND ".join(where)
    join = """
        FROM pay_application_lines l
        JOIN pay_applications a ON a.application_id = l.application_id
        JOIN sov_items s ON s.sov_item_id = l.sov_item_id AND s.contract_id = a.contract_id
    """
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) {join} WHERE {predicate}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT l.application_line_id, l.application_id, l.sov_item_id,
                   s.item_no, s.cost_code, s.contractor_description,
                   s.canonical_description, s.scheduled_value_cents,
                   l.source_line_number, l.line_version,
                   l.previous_work_cents, l.current_work_cents,
                   l.stored_materials_cents, l.contractor_percent_bp,
                   l.is_superseded, l.superseded_by_line_id,
                   l.audit_status, l.source_system, l.reported_at
            {join}
            WHERE {predicate}
            ORDER BY l.source_line_number, l.line_version DESC, l.reported_at
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def recalculate_application_totals(application_id: str, include_rejected: bool = False) -> dict:
    """Recalculate current monetary totals from deduplicated application lines.

    Args:
        application_id: Payment application identifier to recalculate.
        include_rejected: Include rejected lines alongside audited lines when true.

    Returns:
        A dictionary of line count, monetary totals, balance, and completion basis points.
    """
    if not application_id:
        raise ValueError("application_id is required")
    with _con() as connection:
        if not _application_exists(connection, application_id):
            return _error("not_found", f"Payment application {application_id} was not found")
        lines = _controlled_lines(connection, application_id, include_rejected)
    return _totals(application_id, lines)


def compare_reported_percentages(
    application_id: str,
    sov_item_ids: list = None,
    tolerance_bp: int = 50,
) -> dict:
    """Compare reported completion percentages with monetary line calculations.

    Args:
        application_id: Payment application identifier to review.
        sov_item_ids: Optional list of controlled SOV item identifiers to include.
        tolerance_bp: Absolute variance threshold in basis points, from 0 through 10000.

    Returns:
        A dictionary with comparison items and the count exceeding tolerance.
    """
    if not application_id:
        raise ValueError("application_id is required")
    if not 0 <= tolerance_bp <= 10000:
        raise ValueError("tolerance_bp must be between 0 and 10000")
    with _con() as connection:
        if not _application_exists(connection, application_id):
            return _error("not_found", f"Payment application {application_id} was not found")
        lines = _controlled_lines(connection, application_id)
    selected = set(sov_item_ids) if sov_item_ids is not None else None
    items = []
    for row in lines:
        if selected is not None and row["sov_item_id"] not in selected:
            continue
        scheduled = row["scheduled_value_cents"]
        completed = row["previous_work_cents"] + row["current_work_cents"] + row["stored_materials_cents"]
        recalculated = completed * 10000 // scheduled if scheduled else 0
        reported = row["contractor_percent_bp"]
        variance = None if reported is None else reported - recalculated
        is_exception = reported is None or abs(variance) > tolerance_bp
        items.append(
            {
                "sov_item_id": row["sov_item_id"],
                "canonical_description": row["canonical_description"],
                "contractor_percent_bp": reported,
                "recalculated_percent_bp": recalculated,
                "variance_bp": variance,
                "is_exception": is_exception,
            }
        )
    return {
        "application_id": application_id,
        "tolerance_bp": tolerance_bp,
        "items": items,
        "exception_count": sum(1 for item in items if item["is_exception"]),
    }


def flag_duplicate_submission_line(
    application_line_id: str,
    superseded_by_line_id: str,
    reason: str,
    actor_id: str,
) -> dict:
    """Mark an imported duplicate line as superseded while preserving audit history.

    Args:
        application_line_id: Older duplicate line identifier to supersede.
        superseded_by_line_id: Higher-version replacement line identifier.
        reason: Business reason recorded for the supersession decision.
        actor_id: User or service principal responsible for the decision.

    Returns:
        The persisted supersession result, or an error object for failed validation.
    """
    if not all((application_line_id, superseded_by_line_id, reason.strip(), actor_id.strip())):
        raise ValueError("application_line_id, superseded_by_line_id, reason, and actor_id are required")
    if application_line_id == superseded_by_line_id:
        return _error("same_line", "A line cannot supersede itself")
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _con() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pay_application_line_supersession_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_line_id TEXT NOT NULL,
                superseded_by_line_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (application_line_id) REFERENCES pay_application_lines(application_line_id),
                FOREIGN KEY (superseded_by_line_id) REFERENCES pay_application_lines(application_line_id)
            )
            """
        )
        older = connection.execute(
            "SELECT * FROM pay_application_lines WHERE application_line_id = ?", (application_line_id,)
        ).fetchone()
        replacement = connection.execute(
            "SELECT * FROM pay_application_lines WHERE application_line_id = ?", (superseded_by_line_id,)
        ).fetchone()
        if older is None or replacement is None:
            return _error("not_found", "Both the duplicate line and replacement line must exist")
        for field in ("application_id", "sov_item_id", "source_line_number"):
            if older[field] != replacement[field]:
                return _error("line_mismatch", f"Lines must share the same {field}")
        if replacement["line_version"] <= older["line_version"]:
            return _error("invalid_version", "Replacement line_version must be higher than the duplicate")
        if older["is_superseded"]:
            return _error("already_superseded", "The duplicate line is already superseded")
        connection.execute(
            "UPDATE pay_application_lines SET is_superseded = 1, superseded_by_line_id = ? WHERE application_line_id = ?",
            (superseded_by_line_id, application_line_id),
        )
        connection.execute(
            """
            INSERT INTO pay_application_line_supersession_audit
                (application_line_id, superseded_by_line_id, reason, actor_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (application_line_id, superseded_by_line_id, reason, actor_id, updated_at),
        )
    return {
        "application_line_id": application_line_id,
        "superseded_by_line_id": superseded_by_line_id,
        "is_superseded": 1,
        "reason": reason,
        "actor_id": actor_id,
        "updated_at": updated_at,
    }


def export_g703_control_view(
    application_id: str,
    include_zero_lines: bool = True,
    format: str = "json",
) -> dict:
    """Produce a controlled G703 reconciliation extract from current audited lines.

    Args:
        application_id: Payment application identifier to export.
        include_zero_lines: Include lines with no previous, current, or stored value when true.
        format: Export representation, either json or csv.

    Returns:
        JSON line and totals data, or a dictionary containing CSV text and export metadata.
    """
    if not application_id:
        raise ValueError("application_id is required")
    if format not in ("json", "csv"):
        raise ValueError("format must be json or csv")
    with _con() as connection:
        header = connection.execute(
            """
            SELECT application_id, application_number, period_start_date, period_end_date
            FROM pay_applications WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
        if header is None:
            return _error("not_found", f"Payment application {application_id} was not found")
        source_lines = _controlled_lines(connection, application_id)
    if not include_zero_lines:
        source_lines = [
            row for row in source_lines
            if row["previous_work_cents"] + row["current_work_cents"] + row["stored_materials_cents"] > 0
        ]
    lines = []
    for row in source_lines:
        completed = row["previous_work_cents"] + row["current_work_cents"] + row["stored_materials_cents"]
        recalculated = completed * 10000 // row["scheduled_value_cents"] if row["scheduled_value_cents"] else 0
        reported = row["contractor_percent_bp"]
        exception_status = "missing_reported_percent" if reported is None else (
            "variance" if abs(reported - recalculated) > 50 else "matched"
        )
        lines.append(
            {
                "sov_item_id": row["sov_item_id"],
                "item_no": row["item_no"],
                "cost_code": row["cost_code"],
                "canonical_description": row["canonical_description"],
                "scheduled_value_cents": row["scheduled_value_cents"],
                "previous_work_cents": row["previous_work_cents"],
                "current_work_cents": row["current_work_cents"],
                "stored_materials_cents": row["stored_materials_cents"],
                "completed_and_stored_cents": completed,
                "balance_to_finish_cents": max(0, row["scheduled_value_cents"] - completed),
                "contractor_percent_bp": reported,
                "recalculated_percent_bp": recalculated,
                "exception_status": exception_status,
            }
        )
    totals = _totals(application_id, source_lines)
    totals.pop("application_id")
    result = {**dict(header), "lines": lines, "totals": totals}
    if format == "json":
        return result
    output = io.StringIO()
    fieldnames = list(lines[0]) if lines else [
        "sov_item_id", "item_no", "cost_code", "canonical_description",
        "scheduled_value_cents", "previous_work_cents", "current_work_cents",
        "stored_materials_cents", "completed_and_stored_cents",
        "balance_to_finish_cents", "contractor_percent_bp",
        "recalculated_percent_bp", "exception_status",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(lines)
    return {
        "application_id": application_id,
        "application_number": header["application_number"],
        "period_start_date": header["period_start_date"],
        "period_end_date": header["period_end_date"],
        "format": "csv",
        "content": output.getvalue(),
        "totals": totals,
    }

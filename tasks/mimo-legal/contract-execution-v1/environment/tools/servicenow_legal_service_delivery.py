"""MCP tools for the ServiceNow Legal Service Delivery archive."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


_ITEM_STATES = {"OPEN", "AWAITING_REQUESTER", "IN_PROGRESS", "RESOLVED", "CLOSED"}
_EVALUATION_STATUSES = {"ACTIVE", "SUPERSEDED", "WITHDRAWN"}


def _con() -> sqlite3.Connection:
    db_path = Path(__file__).resolve().parent.parent / "system" / "servicenow_legal_service_delivery" / "state.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _require_text(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _parse_timestamp(value: str, name: str) -> datetime:
    _require_text(value, name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a UTC offset")
    return parsed


def _select_case(con: sqlite3.Connection, case_id: str | None, contract_id: str | None) -> sqlite3.Row:
    supplied = int(bool(case_id and case_id.strip())) + int(bool(contract_id and contract_id.strip()))
    if supplied != 1:
        raise ValueError("provide exactly one of case_id or contract_id")
    if case_id:
        row = con.execute("SELECT * FROM legal_review_cases WHERE case_id = ?", (case_id.strip(),)).fetchone()
    else:
        row = con.execute("SELECT * FROM legal_review_cases WHERE contract_id = ?", (contract_id.strip(),)).fetchone()
    if row is None:
        raise ValueError("legal review case was not found")
    return row


def _case_payload(row: sqlite3.Row) -> dict:
    return {
        "case_id": row["case_id"],
        "contract_id": row["contract_id"],
        "governing_office": {"id": row["governing_office_id"], "name": row["governing_office_name"]},
        "requester": {"person_id": row["requester_person_id"], "name": row["requester_name"]},
        "owner": {"person_id": row["case_owner_person_id"], "name": row["case_owner_name"]},
        "priority": row["priority"],
        "case_state": row["case_state"],
        "intake_timestamp_et": row["intake_timestamp_et"],
        "contract_receipt_timestamp_et": row["contract_receipt_timestamp_et"],
        "requested_return_deadline_et": row["requested_return_deadline_et"],
        "planning_benchmark_deadline_et": row["planning_benchmark_deadline_et"],
        "sla_policy_id": row["sla_policy_id"],
        "checklist_status": row["checklist_status"],
        "short_description": row["short_description"],
    }


def _business_day_window(
    case_id: str,
    start_timestamp_et: str,
    end_timestamp_et: str,
    calendar_id: str,
) -> dict:
    start = _parse_timestamp(start_timestamp_et, "start_timestamp_et")
    end = _parse_timestamp(end_timestamp_et, "end_timestamp_et")
    if end <= start:
        raise ValueError("end_timestamp_et must be later than start_timestamp_et")
    start_date = start.date().isoformat()
    end_date = end.date().isoformat()
    con = _con()
    try:
        if con.execute("SELECT 1 FROM legal_review_cases WHERE case_id = ?", (case_id,)).fetchone() is None:
            raise ValueError("case_id was not found")
        rows = con.execute(
            """SELECT calendar_date, is_business_day, closure_reason
               FROM business_calendar_days
               WHERE calendar_id = ? AND calendar_date > ? AND calendar_date <= ?
               ORDER BY calendar_date""",
            (calendar_id, start_date, end_date),
        ).fetchall()
    finally:
        con.close()
    if not rows or rows[-1]["calendar_date"] != end_date:
        raise ValueError("business calendar does not cover the requested date window")
    excluded = [
        {"calendar_date": row["calendar_date"], "closure_reason": row["closure_reason"] or "Non-business day"}
        for row in rows if not row["is_business_day"]
    ]
    return {
        "case_id": case_id,
        "calendar_id": calendar_id,
        "start_date": start_date,
        "end_date": end_date,
        "business_days": sum(row["is_business_day"] for row in rows),
        "excluded_dates": excluded,
    }


def get_legal_review_case(case_id: str | None = None, contract_id: str | None = None) -> dict:
    """Retrieve one legal-review case by case ID or linked contract ID.

    Args:
        case_id: Case identifier; provide this or contract_id.
        contract_id: Linked contract identifier; provide this or case_id.
    Returns:
        A JSON-serializable case dictionary with parties, priority, timestamps,
        deadlines, checklist status, and SLA policy.
    """
    con = _con()
    try:
        return _case_payload(_select_case(con, case_id, contract_id))
    finally:
        con.close()


def list_deficiency_items(
    case_id: str,
    item_state: str | None = None,
    include_duplicates: bool = False,
    source_evaluation_status: str | None = None,
    offset: int = 0,
    page_size: int = 50,
) -> dict:
    """List paginated deficiency tasks for one legal-review case.

    Args:
        case_id: Case identifier to filter.
        item_state: Optional deficiency state filter.
        include_duplicates: Include duplicate tasks when true.
        source_evaluation_status: Optional source evaluation status filter.
        offset: Number of matching rows to skip.
        page_size: Number of rows to return, from 1 through 200.
    Returns:
        A dictionary with item dictionaries, offset, page_size, and total.
    """
    case_id = _require_text(case_id, "case_id")
    if item_state is not None and item_state not in _ITEM_STATES:
        raise ValueError("item_state is not a supported deficiency state")
    if source_evaluation_status is not None and source_evaluation_status not in _EVALUATION_STATUSES:
        raise ValueError("source_evaluation_status is not supported")
    if offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200")
    clauses = ["case_id = ?"]
    params: list[object] = [case_id]
    if item_state is not None:
        clauses.append("item_state = ?")
        params.append(item_state)
    if not include_duplicates:
        clauses.append("duplicate_of_item_id IS NULL")
    if source_evaluation_status is not None:
        clauses.append("source_evaluation_status_snapshot = ?")
        params.append(source_evaluation_status)
    where = " AND ".join(clauses)
    con = _con()
    try:
        if con.execute("SELECT 1 FROM legal_review_cases WHERE case_id = ?", (case_id,)).fetchone() is None:
            raise ValueError("case_id was not found")
        total = con.execute(f"SELECT COUNT(*) FROM deficiency_items WHERE {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT * FROM deficiency_items WHERE {where}
                ORDER BY due_timestamp_et, deficiency_item_id LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    finally:
        con.close()
    items = []
    for row in rows:
        items.append({
            "deficiency_item_id": row["deficiency_item_id"],
            "case_id": row["case_id"],
            "source_evaluation_id": row["source_evaluation_id"],
            "source_evaluation_status_snapshot": row["source_evaluation_status_snapshot"],
            "checklist_code": row["checklist_code"],
            "deficiency_title": row["deficiency_title"],
            "deficiency_detail": row["deficiency_detail"],
            "assigned_person": {"person_id": row["assigned_person_id"], "name": row["assigned_person_name"]},
            "due_timestamp_et": row["due_timestamp_et"],
            "item_state": row["item_state"],
            "duplicate_of_item_id": row["duplicate_of_item_id"],
            "created_timestamp_et": row["created_timestamp_et"],
            "resolved_timestamp_et": row["resolved_timestamp_et"],
        })
    return {"items": items, "offset": offset, "page_size": page_size, "total": total}


def count_actionable_deficiencies(case_id: str | None = None, contract_id: str | None = None) -> dict:
    """Count active, nonduplicate OPEN or AWAITING_REQUESTER deficiency tasks.

    Args:
        case_id: Case identifier; provide this or contract_id.
        contract_id: Linked contract identifier; provide this or case_id.
    Returns:
        A dictionary with the selected case, count, and applied criteria.
    """
    con = _con()
    try:
        case = _select_case(con, case_id, contract_id)
        count = con.execute(
            """SELECT COUNT(*) FROM deficiency_items
               WHERE case_id = ? AND item_state IN ('OPEN','AWAITING_REQUESTER')
                 AND duplicate_of_item_id IS NULL
                 AND source_evaluation_status_snapshot = 'ACTIVE'""",
            (case["case_id"],),
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "case_id": case["case_id"],
        "contract_id": case["contract_id"],
        "actionable_deficiency_count": count,
        "criteria": {
            "states": ["OPEN", "AWAITING_REQUESTER"],
            "duplicate_of_item_id": "null",
            "source_evaluation_status_snapshot": "ACTIVE",
        },
    }


def calculate_business_day_window(
    case_id: str,
    start_timestamp_et: str,
    end_timestamp_et: str,
    calendar_id: str = "CSCC-ET-OPERATING",
) -> dict:
    """Count business days after the start date through the inclusive end date.

    Args:
        case_id: Case identifier.
        start_timestamp_et: ISO-8601 timestamp whose date is excluded.
        end_timestamp_et: ISO-8601 timestamp whose date is included.
        calendar_id: Operating calendar identifier.
    Returns:
        A dictionary with date bounds, business-day count, and excluded dates.
    """
    case_id = _require_text(case_id, "case_id")
    calendar_id = _require_text(calendar_id, "calendar_id")
    return _business_day_window(case_id, start_timestamp_et, end_timestamp_et, calendar_id)


def calculate_sla_compression(case_id: str, calendar_id: str = "CSCC-ET-OPERATING") -> dict:
    """Calculate requested and benchmark business-day windows and their compression.

    Args:
        case_id: Case identifier.
        calendar_id: Operating calendar identifier.
    Returns:
        A dictionary containing requested days, benchmark days, compression, and deadlines.
    """
    case_id = _require_text(case_id, "case_id")
    calendar_id = _require_text(calendar_id, "calendar_id")
    con = _con()
    try:
        case_row = _select_case(con, case_id, None)
        case = _case_payload(case_row)
    finally:
        con.close()
    requested = _business_day_window(
        case_id,
        case["intake_timestamp_et"],
        case["requested_return_deadline_et"],
        calendar_id,
    )
    benchmark = _business_day_window(
        case_id,
        case["intake_timestamp_et"],
        case["planning_benchmark_deadline_et"],
        calendar_id,
    )
    return {
        "case_id": case_id,
        "requested_business_days": requested["business_days"],
        "benchmark_business_days": benchmark["business_days"],
        "business_day_compression": benchmark["business_days"] - requested["business_days"],
        "requested_return_deadline_et": case["requested_return_deadline_et"],
        "planning_benchmark_deadline_et": case["planning_benchmark_deadline_et"],
    }


def issue_sla_exception(
    case_id: str,
    approval_route_id: str,
    recipients: list[str],
    rationale: str,
    revised_expectation: str,
    approved_by_person_id: str,
    effective_deadline_et: str,
    idempotency_key: str,
) -> dict:
    """Create approved-exception and notice events atomically and idempotently.

    Args:
        case_id: Case identifier.
        approval_route_id: Approval route identifier.
        recipients: Person or group identifiers receiving the notice.
        rationale: Business rationale for the exception.
        revised_expectation: Revised delivery expectation.
        approved_by_person_id: Approving person's identifier.
        effective_deadline_et: ISO-8601 effective deadline with UTC offset.
        idempotency_key: Retry-safe caller key.
    Returns:
        A dictionary containing event IDs, persisted approval data, and created status.
    """
    case_id = _require_text(case_id, "case_id")
    approval_route_id = _require_text(approval_route_id, "approval_route_id")
    rationale = _require_text(rationale, "rationale")
    revised_expectation = _require_text(revised_expectation, "revised_expectation")
    approved_by_person_id = _require_text(approved_by_person_id, "approved_by_person_id")
    idempotency_key = _require_text(idempotency_key, "idempotency_key")
    _parse_timestamp(effective_deadline_et, "effective_deadline_et")
    if not recipients:
        raise ValueError("recipients must be a non-empty list")
    normalized_recipients = [_require_text(value, "recipient") for value in recipients]
    if len(set(normalized_recipients)) != len(normalized_recipients):
        raise ValueError("recipients must not contain duplicates")
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:20].upper()
    exception_event_id = f"SLAE-IDEM-{digest}-EXC"
    notice_event_id = f"SLAE-IDEM-{digest}-NTC"
    recipient_list = ";".join(normalized_recipients)
    now = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    con = _con()
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM legal_review_cases WHERE case_id = ?", (case_id,)).fetchone() is None:
            raise ValueError("case_id was not found")
        existing = con.execute(
            "SELECT sla_event_id, case_id, approval_route_id, effective_deadline_et, recipient_list FROM sla_events WHERE sla_event_id IN (?, ?)",
            (exception_event_id, notice_event_id),
        ).fetchall()
        if existing:
            if len(existing) != 2:
                raise RuntimeError("idempotent SLA exception is incomplete")
            if any(row["case_id"] != case_id or row["approval_route_id"] != approval_route_id for row in existing):
                raise ValueError("idempotency_key was already used for different SLA exception data")
            con.rollback()
            return {
                "case_id": case_id,
                "approval_route_id": approval_route_id,
                "approval_decision": "APPROVED",
                "exception_event_id": exception_event_id,
                "notice_event_id": notice_event_id,
                "effective_deadline_et": existing[0]["effective_deadline_et"],
                "recipients": existing[0]["recipient_list"].split(";"),
                "idempotency_key": idempotency_key,
                "created": False,
            }
        values = (case_id, now, effective_deadline_et, approval_route_id, "APPROVED", recipient_list, rationale, revised_expectation, approved_by_person_id)
        con.execute("INSERT INTO sla_events VALUES (?, ?, 'EXCEPTION_APPROVED', ?, ?, ?, ?, ?, ?, ?, ?)", (exception_event_id, *values))
        con.execute("INSERT INTO sla_events VALUES (?, ?, 'NOTICE_ISSUED', ?, ?, ?, ?, ?, ?, ?, ?)", (notice_event_id, *values))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "case_id": case_id,
        "approval_route_id": approval_route_id,
        "approval_decision": "APPROVED",
        "exception_event_id": exception_event_id,
        "notice_event_id": notice_event_id,
        "effective_deadline_et": effective_deadline_et,
        "recipients": normalized_recipients,
        "idempotency_key": idempotency_key,
        "created": True,
    }

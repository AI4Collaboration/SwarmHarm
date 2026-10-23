"""MCP tools for OpenGov procurement and change-control records."""

import sqlite3
from datetime import datetime
from pathlib import Path
import hashlib


def _con():
    """Open the authoritative procurement database with foreign keys enabled."""
    path = Path(__file__).resolve().parent.parent / "system" / "opengov_procurement" / "state.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _page_offset(page_token: str | None) -> int:
    if page_token is None:
        return 0
    try:
        offset = int(page_token)
    except (TypeError, ValueError) as exc:
        raise ValueError("page_token must be a nonnegative row offset") from exc
    if offset < 0:
        raise ValueError("page_token must be a nonnegative row offset")
    return offset


def _page(items: list[dict], offset: int, page_size: int) -> dict:
    page = items[offset:offset + page_size]
    next_offset = offset + page_size if offset + page_size < len(items) else None
    return {"items": page, "next_page_token": str(next_offset) if next_offset is not None else None}


def _validate_page_size(page_size: int, maximum: int = 100) -> None:
    if not 1 <= page_size <= maximum:
        raise ValueError(f"page_size must be between 1 and {maximum}")


def _validate_date(value: str, field_name: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO date in YYYY-MM-DD format") from exc


def _validate_timestamp(value: str, field_name: str) -> None:
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc


def _key_id(prefix: str, key: str, length: int = 14) -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:length].upper()}"


def _row_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def search_procurements(owner_id: str = None, title_query: str = None, fiscal_year: int = None, issue_date_from: str = None, issue_date_to: str = None, status: str = None, page_size: int = 25, page_token: str = None) -> dict:
    """Search procurement masters with conjunctive filters and stable pagination.

    Args:
        owner_id: Exact owner or department identifier.
        title_query: Case-insensitive substring to find in the procurement title.
        fiscal_year: Fiscal year to match.
        issue_date_from: Inclusive lower issue-date bound in YYYY-MM-DD format.
        issue_date_to: Inclusive upper issue-date bound in YYYY-MM-DD format.
        status: Procurement status such as AWARDED or CLOSED.
        page_size: Number of rows to return, from 1 through 100.
        page_token: Nonnegative offset returned by a prior call.
    Returns:
        A dictionary with matching procurement items and a nullable next_page_token.
    """
    _validate_page_size(page_size)
    if all(value is None for value in (owner_id, title_query, fiscal_year, issue_date_from, issue_date_to, status)):
        raise ValueError("at least one procurement filter is required")
    if issue_date_from:
        _validate_date(issue_date_from, "issue_date_from")
    if issue_date_to:
        _validate_date(issue_date_to, "issue_date_to")
    if issue_date_from and issue_date_to and issue_date_from > issue_date_to:
        raise ValueError("issue_date_from cannot be later than issue_date_to")
    allowed = {"DRAFT", "ISSUED", "EVALUATION", "AWARDED", "CANCELLED", "CLOSED"}
    if status is not None and status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    if fiscal_year is not None and not 2000 <= fiscal_year <= 2100:
        raise ValueError("fiscal_year must be between 2000 and 2100")
    clauses, params = [], []
    if owner_id is not None:
        clauses.append("owner_id = ?"); params.append(owner_id)
    if title_query is not None:
        clauses.append("LOWER(procurement_title) LIKE LOWER(?)"); params.append(f"%{title_query}%")
    if fiscal_year is not None:
        clauses.append("fiscal_year = ?"); params.append(fiscal_year)
    if issue_date_from is not None:
        clauses.append("issue_date >= ?"); params.append(issue_date_from)
    if issue_date_to is not None:
        clauses.append("issue_date <= ?"); params.append(issue_date_to)
    if status is not None:
        clauses.append("procurement_status = ?"); params.append(status)
    offset = _page_offset(page_token)
    with _con() as connection:
        rows = connection.execute(
            "SELECT procurement_id, owner_id, procurement_title, fiscal_year, issue_date, procurement_status "
            "FROM procurements WHERE " + " AND ".join(clauses) + " ORDER BY issue_date DESC, procurement_id", params
        ).fetchall()
    return _page([_row_dict(row) for row in rows], offset, page_size)


def get_awarded_contract(award_id: str = None, contract_id: str = None) -> dict:
    """Retrieve one awarded contract by exactly one award or contract identifier.

    Args:
        award_id: Award identifier to match.
        contract_id: Contract identifier to match.
    Returns:
        A dictionary containing award details, or a NOT_FOUND error structure.
    """
    if (award_id is None) == (contract_id is None):
        raise ValueError("provide exactly one of award_id or contract_id")
    column, value = ("award_id", award_id) if award_id is not None else ("contract_id", contract_id)
    with _con() as connection:
        row = connection.execute(
            f"SELECT award_id, procurement_id, contract_id, contractor_id, contractor_display_name, "
            f"executed_amount_cents, executed_date, award_status FROM awarded_contracts WHERE {column} = ?", (value,)
        ).fetchone()
    return {"award": _row_dict(row) if row else None, "error": None if row else "NOT_FOUND"}


def list_change_order_requests(award_id: str, status: str = None, requested_through: str = None, page_size: int = 25, page_token: str = None) -> dict:
    """List change requests for one award with optional status and date cutoff.

    Args:
        award_id: Award identifier whose requests are listed.
        status: Optional request status filter.
        requested_through: Inclusive requested-date cutoff in YYYY-MM-DD format.
        page_size: Number of rows to return, from 1 through 100.
        page_token: Nonnegative offset returned by a prior call.
    Returns:
        A dictionary with change-request items and a nullable next_page_token.
    """
    _validate_page_size(page_size)
    allowed = {"DRAFT", "SUBMITTED", "UNDER_REVIEW", "RETURNED", "REJECTED", "WITHDRAWN", "EXECUTED"}
    if status is not None and status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    if requested_through:
        _validate_date(requested_through, "requested_through")
    clauses, params = ["award_id = ?"], [award_id]
    if status:
        clauses.append("change_status = ?"); params.append(status)
    if requested_through:
        clauses.append("requested_date <= ?"); params.append(requested_through)
    offset = _page_offset(page_token)
    with _con() as connection:
        rows = connection.execute(
            "SELECT change_request_id, award_id, change_order_number, request_title, requested_amount_cents, "
            "change_status, requested_date, executed_date, billing_reference FROM change_order_requests WHERE "
            + " AND ".join(clauses) + " ORDER BY requested_date, change_order_number", params
        ).fetchall()
    return _page([_row_dict(row) for row in rows], offset, page_size)


def calculate_approved_change_total(award_id: str, application_cutoff: str) -> dict:
    """Calculate executed change-order value effective on or before an application cutoff.

    Args:
        award_id: Award identifier to evaluate.
        application_cutoff: Cutoff date in YYYY-MM-DD format.
    Returns:
        A dictionary with executed count, integer total cents, and included request IDs.
    """
    _validate_date(application_cutoff, "application_cutoff")
    with _con() as connection:
        rows = connection.execute(
            "SELECT change_request_id, requested_amount_cents FROM change_order_requests "
            "WHERE award_id = ? AND requested_date <= ? AND change_status = 'EXECUTED' "
            "AND executed_date IS NOT NULL AND executed_date <= ? ORDER BY executed_date, change_request_id",
            (award_id, application_cutoff, application_cutoff),
        ).fetchall()
    return {
        "award_id": award_id,
        "application_cutoff": application_cutoff,
        "executed_change_count": len(rows),
        "approved_change_total_cents": sum(row["requested_amount_cents"] for row in rows),
        "included_change_request_ids": [row["change_request_id"] for row in rows],
    }


def evaluate_change_billing_eligibility(award_id: str, application_cutoff: str, change_request_ids: list = None) -> dict:
    """Evaluate change requests against execution state and active billing controls.

    Args:
        award_id: Award identifier to evaluate.
        application_cutoff: Date through which execution and controls are effective, in YYYY-MM-DD format.
        change_request_ids: Optional list of request IDs; when omitted, evaluate every request for the award.
    Returns:
        A dictionary with approved total, eligible billing total, and per-request eligibility decisions.
    """
    _validate_date(application_cutoff, "application_cutoff")
    with _con() as connection:
        controls = connection.execute(
            "SELECT control_rule_id, rule_code, rule_value FROM billing_control_rules "
            "WHERE award_id = ? AND active_flag = 1 AND effective_date <= ? "
            "AND (expiration_date IS NULL OR expiration_date >= ?)",
            (award_id, application_cutoff, application_cutoff),
        ).fetchall()
        control_map = {row["rule_code"]: row for row in controls}
        clauses = ["award_id = ?"]; params = [award_id]
        if change_request_ids is not None:
            if not change_request_ids:
                raise ValueError("change_request_ids cannot be empty when provided")
            placeholders = ",".join("?" for _ in change_request_ids)
            clauses.append(f"change_request_id IN ({placeholders})"); params.extend(change_request_ids)
        requests = connection.execute(
            "SELECT change_request_id, change_order_number, requested_amount_cents, change_status, executed_date, billing_reference "
            "FROM change_order_requests WHERE " + " AND ".join(clauses) + " ORDER BY requested_date, change_order_number", params
        ).fetchall()
    if change_request_ids is not None and len(requests) != len(set(change_request_ids)):
        raise ValueError("one or more change_request_ids do not belong to award_id")
    execution_rule = control_map.get("CHANGE_BILLING_EXECUTED_ONLY")
    emergency_rule = control_map.get("EMERGENCY_DIRECTIVE_TRACK_ONLY")
    items = []
    approved_total = 0
    eligible_total = 0
    for row in requests:
        executed = row["change_status"] == "EXECUTED" and row["executed_date"] is not None and row["executed_date"] <= application_cutoff
        if executed:
            approved_total += row["requested_amount_cents"]
        if executed and execution_rule:
            eligible, reason, rule_ids = True, "EXECUTED_CHANGE_ORDER", [execution_rule["control_rule_id"]]
            eligible_total += row["requested_amount_cents"]
        else:
            eligible, reason = False, "FORMAL_EXECUTION_REQUIRED"
            rule_ids = [execution_rule["control_rule_id"]] if execution_rule else []
            reference = (row["billing_reference"] or "").upper()
            if emergency_rule and ("EFD-" in reference or "EMERGENCY" in reference):
                rule_ids.append(emergency_rule["control_rule_id"])
        items.append({
            "change_request_id": row["change_request_id"],
            "change_order_number": row["change_order_number"],
            "requested_amount_cents": row["requested_amount_cents"],
            "eligible": eligible,
            "reason_code": reason,
            "control_rule_ids": rule_ids,
        })
    return {"award_id": award_id, "application_cutoff": application_cutoff, "approved_change_total_cents": approved_total, "eligible_billing_total_cents": eligible_total, "items": items}


def list_approval_history(award_id: str = None, change_request_id: str = None, action_through: str = None, page_size: int = 50, page_token: str = None) -> dict:
    """List approval actions chronologically for an award or one of its requests.

    Args:
        award_id: Optional award identifier.
        change_request_id: Optional request identifier.
        action_through: Inclusive timestamp cutoff in ISO-8601 format.
        page_size: Number of rows to return, from 1 through 100.
        page_token: Nonnegative offset returned by a prior call.
    Returns:
        A dictionary with approval-action items and a nullable next_page_token.
    """
    _validate_page_size(page_size)
    if award_id is None and change_request_id is None:
        raise ValueError("award_id or change_request_id is required")
    if action_through:
        _validate_timestamp(action_through, "action_through")
    clauses, params = [], []
    if award_id:
        clauses.append("aa.award_id = ?"); params.append(award_id)
    if change_request_id:
        clauses.append("aa.change_request_id = ?"); params.append(change_request_id)
    if action_through:
        clauses.append("aa.action_timestamp <= ?"); params.append(action_through)
    with _con() as connection:
        if award_id and change_request_id:
            valid = connection.execute("SELECT 1 FROM change_order_requests WHERE change_request_id = ? AND award_id = ?", (change_request_id, award_id)).fetchone()
            if not valid:
                raise ValueError("award_id and change_request_id must refer to the same award")
        rows = connection.execute(
            "SELECT aa.approval_action_id, aa.change_request_id, aa.award_id, aa.approver_id, aa.approver_role, "
            "aa.action_code, aa.action_timestamp, aa.action_comment FROM approval_actions aa WHERE "
            + " AND ".join(clauses) + " ORDER BY aa.action_timestamp, aa.approval_action_id", params
        ).fetchall()
    return _page([_row_dict(row) for row in rows], _page_offset(page_token), page_size)


def submit_change_order_request(award_id: str, change_order_number: str, request_title: str, requested_amount_cents: int, requested_date: str, billing_reference: str = None, submitted_by: str = None, idempotency_key: str = None) -> dict:
    """Create a submitted change request and its initial submission action atomically.

    Args:
        award_id: Award receiving the change request.
        change_order_number: Unique change-order number within the award.
        request_title: Plain-language description of the requested change.
        requested_amount_cents: Signed requested amount in whole cents.
        requested_date: Request date in YYYY-MM-DD format.
        billing_reference: Optional source or operational reference.
        submitted_by: User identifier recorded as the submitting approver.
        idempotency_key: Client key used to safely retry the submission.
    Returns:
        A dictionary containing the request, initial approval action ID, and created flag.
    """
    if not award_id or not change_order_number or not request_title or not submitted_by or not idempotency_key:
        raise ValueError("award_id, change_order_number, request_title, submitted_by, and idempotency_key are required")
    if not -45000000 <= requested_amount_cents <= 125000000:
        raise ValueError("requested_amount_cents must be between -45,000,000 and 125,000,000")
    _validate_date(requested_date, "requested_date")
    request_id = _key_id("CR-CLIENT", idempotency_key)
    action_id = _key_id("ACT-CLIENT", idempotency_key)
    with _con() as connection:
        existing = connection.execute("SELECT * FROM change_order_requests WHERE change_request_id = ?", (request_id,)).fetchone()
        if existing:
            action = connection.execute("SELECT approval_action_id FROM approval_actions WHERE approval_action_id = ?", (action_id,)).fetchone()
            return {"change_request": _row_dict(existing), "approval_action_id": action["approval_action_id"] if action else action_id, "created": False}
        if not connection.execute("SELECT 1 FROM awarded_contracts WHERE award_id = ?", (award_id,)).fetchone():
            raise ValueError("award_id does not identify an awarded contract")
        if connection.execute("SELECT 1 FROM change_order_requests WHERE award_id = ? AND change_order_number = ?", (award_id, change_order_number)).fetchone():
            raise ValueError("change_order_number already exists for award_id")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        connection.execute(
            "INSERT INTO change_order_requests VALUES (?, ?, ?, ?, ?, 'SUBMITTED', ?, NULL, ?, ?)",
            (request_id, award_id, change_order_number, request_title, requested_amount_cents, requested_date, billing_reference, now),
        )
        connection.execute(
            "INSERT INTO approval_actions VALUES (?, ?, ?, ?, ?, 'SUBMIT', ?, ?)",
            (action_id, request_id, award_id, submitted_by, "Contractor Project Manager", now, "Submitted through OpenGov change-control workflow."),
        )
        row = connection.execute("SELECT * FROM change_order_requests WHERE change_request_id = ?", (request_id,)).fetchone()
    return {"change_request": _row_dict(row), "approval_action_id": action_id, "created": True}


def record_approval_action(change_request_id: str, approver_id: str, approver_role: str, action_code: str, action_comment: str = None, action_timestamp: str = None, idempotency_key: str = None) -> dict:
    """Append an approval-history action and apply its permitted request transition atomically.

    Args:
        change_request_id: Request identifier receiving the action.
        approver_id: User identifier of the reviewer.
        approver_role: Business role of the reviewer.
        action_code: One of APPROVE, REJECT, RETURN, WITHDRAW, or COMMENT.
        action_comment: Optional reviewer note.
        action_timestamp: Optional ISO-8601 action timestamp; defaults to the current time.
        idempotency_key: Client key used to safely retry the action.
    Returns:
        A dictionary containing the action, resulting request status, and created flag.
    """
    if not change_request_id or not approver_id or not approver_role or not idempotency_key:
        raise ValueError("change_request_id, approver_id, approver_role, and idempotency_key are required")
    if action_code not in {"APPROVE", "REJECT", "RETURN", "WITHDRAW", "COMMENT"}:
        raise ValueError("action_code must be APPROVE, REJECT, RETURN, WITHDRAW, or COMMENT")
    if action_timestamp:
        _validate_timestamp(action_timestamp, "action_timestamp")
    action_timestamp = action_timestamp or datetime.now().astimezone().isoformat(timespec="seconds")
    action_id = _key_id("ACT-CLIENT", idempotency_key)
    with _con() as connection:
        existing = connection.execute("SELECT approval_action_id, change_request_id, award_id, action_code, action_timestamp FROM approval_actions WHERE approval_action_id = ?", (action_id,)).fetchone()
        if existing:
            current = connection.execute("SELECT change_status FROM change_order_requests WHERE change_request_id = ?", (change_request_id,)).fetchone()
            return {"approval_action": _row_dict(existing), "change_request_status": current["change_status"] if current else None, "created": False}
        request = connection.execute("SELECT award_id, change_status FROM change_order_requests WHERE change_request_id = ?", (change_request_id,)).fetchone()
        if not request:
            raise ValueError("change_request_id was not found")
        transitions = {"REJECT": "REJECTED", "RETURN": "RETURNED", "WITHDRAW": "WITHDRAWN"}
        if action_code in transitions and request["change_status"] in {"EXECUTED", "REJECTED", "WITHDRAWN"}:
            raise ValueError(f"cannot apply {action_code} to a {request['change_status']} request")
        next_status = transitions.get(action_code, request["change_status"])
        connection.execute(
            "INSERT INTO approval_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (action_id, change_request_id, request["award_id"], approver_id, approver_role, action_code, action_timestamp, action_comment),
        )
        if next_status != request["change_status"]:
            connection.execute("UPDATE change_order_requests SET change_status = ? WHERE change_request_id = ?", (next_status, change_request_id))
    return {"approval_action": {"approval_action_id": action_id, "change_request_id": change_request_id, "award_id": request["award_id"], "action_code": action_code, "action_timestamp": action_timestamp}, "change_request_status": next_status, "created": True}

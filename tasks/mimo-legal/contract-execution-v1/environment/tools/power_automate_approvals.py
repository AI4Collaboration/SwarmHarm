from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "system" / "power_automate_approvals" / "state.db"


def _con() -> sqlite3.Connection:
    """Open the approvals state database with named-column rows and foreign keys enabled."""
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _validate_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date in YYYY-MM-DD format") from exc


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _route_status_for_decision(decision_status: str, all_steps: list[sqlite3.Row]) -> str:
    statuses = {row["decision_status"] for row in all_steps}
    if decision_status == "REJECTED" or "REJECTED" in statuses:
        return "REJECTED"
    if decision_status in {"RETURNED", "CONDITIONAL"} or statuses & {"RETURNED", "CONDITIONAL"}:
        return "WAITING"
    if all_steps and all(row["decision_status"] == "APPROVED" for row in all_steps):
        return "APPROVED"
    if decision_status == "APPROVED":
        return "IN_REVIEW"
    return "WAITING"


def _external_deficiency_count(contract_id: str) -> int:
    path = Path(__file__).resolve().parent.parent / "system" / "ironclad_clm" / "state.db"
    if not path.exists():
        return 0
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("""SELECT COUNT(*) FROM control_evaluations
            WHERE contract_id = ? AND resolution_status = 'OPEN' AND result_status IN ('FAIL', 'PENDING')""", (contract_id,)).fetchone()
        return int(row[0])
    finally:
        connection.close()


def get_approval_route(contract_id: str, route_version: int | None = None) -> dict:
    """Retrieve the latest approval route or a specified route version.

    Args:
        contract_id: Contract identifier to look up.
        route_version: Optional positive route version; omitted selects the latest version.
    Returns:
        A dictionary containing ``route`` with route details, or ``status='NOT_FOUND'``.
    """
    if not contract_id.strip():
        raise ValueError("contract_id must not be empty")
    if route_version is not None and route_version < 1:
        raise ValueError("route_version must be a positive integer")
    con = _con()
    try:
        if route_version is None:
            row = con.execute("SELECT * FROM approval_routes WHERE contract_id = ? ORDER BY route_version DESC LIMIT 1", (contract_id,)).fetchone()
        else:
            row = con.execute("SELECT * FROM approval_routes WHERE contract_id = ? AND route_version = ?", (contract_id, route_version)).fetchone()
        if row is None:
            return {"status": "NOT_FOUND", "route": None}
        return {"status": "OK", "route": _row(row)}
    finally:
        con.close()


def list_approval_steps(route_id: str, decision_status: str | None = None, reviewer_role: str | None = None, limit: int = 50, cursor: str | None = None) -> dict:
    """List a route's approval steps in sequence order with cursor pagination.

    Args:
        route_id: Approval route identifier.
        decision_status: Optional decision status filter.
        reviewer_role: Optional reviewer role filter.
        limit: Number of rows to return, from 1 through 100.
        cursor: Optional zero-based sequence cursor returned by a prior call.
    Returns:
        A dictionary with ``steps``, ``total``, and ``next_cursor``.
    """
    allowed_statuses = {"NOT_STARTED", "WAITING", "IN_REVIEW", "APPROVED", "REJECTED", "RETURNED", "ABSTAINED", "CONDITIONAL"}
    allowed_roles = {"Contract Management Specialist", "Procurement Review", "Legal Counsel", "Fiscal Review", "Authorized Signatory"}
    if not route_id.strip():
        raise ValueError("route_id must not be empty")
    if decision_status is not None and decision_status not in allowed_statuses:
        raise ValueError(f"decision_status must be one of {sorted(allowed_statuses)}")
    if reviewer_role is not None and reviewer_role not in allowed_roles:
        raise ValueError(f"reviewer_role must be one of {sorted(allowed_roles)}")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    offset = 0 if cursor in (None, "") else int(cursor)
    if offset < 0:
        raise ValueError("cursor must be a non-negative sequence offset")
    con = _con()
    try:
        clauses = ["route_id = ?"]
        params: list = [route_id]
        if decision_status is not None:
            clauses.append("decision_status = ?"); params.append(decision_status)
        if reviewer_role is not None:
            clauses.append("reviewer_role = ?"); params.append(reviewer_role)
        where = " AND ".join(clauses)
        total = con.execute(f"SELECT COUNT(*) FROM approval_steps WHERE {where}", params).fetchone()[0]
        rows = con.execute(f"SELECT * FROM approval_steps WHERE {where} ORDER BY step_sequence LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        return {"steps": [_row(row) for row in rows], "total": total, "next_cursor": str(offset + len(rows)) if offset + len(rows) < total else None}
    finally:
        con.close()


def validate_route_prerequisites(route_id: str, include_external_deficiencies: bool = True) -> dict:
    """Evaluate approval-stage prerequisites and overall route readiness.

    Args:
        route_id: Approval route identifier.
        include_external_deficiencies: Whether to include current open Ironclad control deficiencies.
    Returns:
        A dictionary containing route readiness, stage-level blocking codes, and snapshot count.
    """
    if not route_id.strip():
        raise ValueError("route_id must not be empty")
    con = _con()
    try:
        route = con.execute("SELECT * FROM approval_routes WHERE route_id = ?", (route_id,)).fetchone()
        if route is None:
            return {"status": "NOT_FOUND", "route_id": route_id, "overall_ready": False, "stages": [], "snapshot_blocker_count": None}
        rows = con.execute("SELECT * FROM approval_steps WHERE route_id = ? ORDER BY step_sequence", (route_id,)).fetchall()
        ext = _external_deficiency_count(route["contract_id"]) if include_external_deficiencies else 0
        stages = []
        for row in rows:
            blockers = []
            if row["decision_status"] in {"REJECTED", "RETURNED", "CONDITIONAL"}:
                blockers.append(row["prerequisite_code"] or "DECISION_REQUIRES_ACTION")
            prior = [r for r in rows if r["step_sequence"] < row["step_sequence"]]
            if row["reviewer_role"] in {"Legal Counsel", "Fiscal Review"} and prior and any(r["decision_status"] not in {"APPROVED", "ABSTAINED"} for r in prior):
                blockers.append(row["prerequisite_code"] or "PRIOR_STAGE_INCOMPLETE")
            if row["reviewer_role"] == "Authorized Signatory":
                required = [r for r in rows if r["reviewer_role"] in {"Legal Counsel", "Fiscal Review"}]
                if any(r["decision_status"] != "APPROVED" for r in required):
                    blockers.append("LEGAL_AND_FISCAL_APPROVED")
            if ext and row["reviewer_role"] in {"Procurement Review", "Legal Counsel", "Fiscal Review", "Authorized Signatory"}:
                blockers.append("EXTERNAL_DEFICIENCIES_OPEN")
            stages.append({"reviewer_role": row["reviewer_role"], "can_begin": not blockers, "blocking_prerequisite_codes": list(dict.fromkeys(blockers)), "external_deficiency_count": ext})
        return {"status": "OK", "route_id": route_id, "overall_ready": bool(rows) and all(stage["can_begin"] for stage in stages), "stages": stages, "snapshot_blocker_count": route["blocker_count_snapshot"]}
    finally:
        con.close()


def _signature_authority_result(con: sqlite3.Connection, person_id: str, institution_id: str, authority_type: str, proposed_amount_usd: int, execution_date: str) -> dict:
    execution = _validate_date(execution_date, "execution_date")
    rows = con.execute("""SELECT * FROM signature_authorities WHERE person_id = ? AND institution_id = ?
        AND authority_type = ? AND delegation_status = 'ACTIVE' AND effective_start <= ? AND effective_end >= ?
        ORDER BY dollar_limit_usd DESC""", (person_id, institution_id, authority_type, execution.isoformat(), execution.isoformat())).fetchall()
    if not rows:
        return {"authorized": False, "matched_authority_id": None, "dollar_limit_usd": None, "proposed_amount_usd": proposed_amount_usd, "execution_date": execution.isoformat(), "rejection_reason": "NO_ACTIVE_DELEGATION"}
    match = rows[0]
    authorized = proposed_amount_usd <= match["dollar_limit_usd"]
    return {"authorized": authorized, "matched_authority_id": match["authority_id"] if authorized else None, "dollar_limit_usd": match["dollar_limit_usd"], "proposed_amount_usd": proposed_amount_usd, "execution_date": execution.isoformat(), "rejection_reason": None if authorized else "AMOUNT_EXCEEDS_DELEGATED_LIMIT"}


def check_signature_authority(person_id: str, institution_id: str, authority_type: str, proposed_amount_usd: int, execution_date: str) -> dict:
    """Check whether a person has active signing authority for an amount and date.

    Args:
        person_id: Authorized signatory person identifier.
        institution_id: Institution identifier.
        authority_type: Agreement type covered by the delegation.
        proposed_amount_usd: Proposed whole-dollar contract amount.
        execution_date: Intended execution date in YYYY-MM-DD format.
    Returns:
        A dictionary with authorization outcome, matched authority, amount, date, and rejection reason.
    """
    if proposed_amount_usd < 0:
        raise ValueError("proposed_amount_usd must be non-negative")
    con = _con()
    try:
        return _signature_authority_result(con, person_id, institution_id, authority_type, proposed_amount_usd, execution_date)
    finally:
        con.close()


def calculate_route_window_compression(route_id: str, holiday_dates: list = None, timezone: str = "America/New_York") -> dict:
    """Calculate requested and benchmark weekday windows and their compression.

    Args:
        route_id: Approval route identifier.
        holiday_dates: Optional ISO dates to exclude as institution closure dates.
        timezone: IANA timezone label retained in the request context.
    Returns:
        A dictionary with requested business days, benchmark business days, and compression days.
    """
    if not route_id.strip():
        raise ValueError("route_id must not be empty")
    if not timezone.strip():
        raise ValueError("timezone must not be empty")
    holidays = {_validate_date(value, "holiday_dates entry") for value in (holiday_dates or [])}
    con = _con()
    try:
        route = con.execute("SELECT * FROM approval_routes WHERE route_id = ?", (route_id,)).fetchone()
        if route is None:
            return {"status": "NOT_FOUND", "route_id": route_id}
        def count_days(start: date, end: date) -> int:
            current = start; total = 0
            while current < end:
                if current.weekday() < 5 and current not in holidays: total += 1
                current += timedelta(days=1)
            return total
        requested = count_days(_validate_date(route["requested_start_date"], "requested_start_date"), _validate_date(route["requested_end_date"], "requested_end_date"))
        benchmark = count_days(_validate_date(route["requested_start_date"], "requested_start_date"), _validate_date(route["benchmark_end_date"], "benchmark_end_date"))
        return {"status": "OK", "route_id": route_id, "operating_calendar_code": route["operating_calendar_code"], "requested_business_days": requested, "benchmark_business_days": benchmark, "compression_business_days": benchmark - requested}
    finally:
        con.close()


def create_approval_route(contract_id: str, governing_office_id: str, initiator_person_id: str, requested_start_date: str, requested_end_date: str, benchmark_end_date: str, proposed_execution_date: str, agreement_type: str, proposed_amount_usd: int, operating_calendar_code: str, blocker_count_snapshot: int, steps: list) -> dict:
    """Create the next version of a contract approval route and its ordered steps atomically.

    Args:
        contract_id: Contract identifier.
        governing_office_id: Governing office identifier.
        initiator_person_id: Requesting person's identifier.
        requested_start_date: Requested review start date.
        requested_end_date: Requested review end date.
        benchmark_end_date: Standard planning benchmark date.
        proposed_execution_date: Proposed execution date.
        agreement_type: Agreement type used for routing and authority checks.
        proposed_amount_usd: Proposed whole-dollar contract amount.
        operating_calendar_code: Business calendar identifier.
        blocker_count_snapshot: Intake-time blocker count.
        steps: Ordered step dictionaries with sequence, reviewer_role, assigned_person_id, prerequisite_code, and due_at.
    Returns:
        A dictionary containing the created route identity and number of steps, or a conflict status.
    """
    dates = [_validate_date(value, name) for value, name in [(requested_start_date, "requested_start_date"), (requested_end_date, "requested_end_date"), (benchmark_end_date, "benchmark_end_date"), (proposed_execution_date, "proposed_execution_date")]]
    if dates[0] > dates[1] or dates[1] > dates[2] or not dates[0] <= dates[3] <= dates[1]:
        raise ValueError("route dates must satisfy start <= execution <= end <= benchmark")
    if proposed_amount_usd < 0 or blocker_count_snapshot < 0:
        raise ValueError("amount and blocker_count_snapshot must be non-negative")
    if not steps:
        raise ValueError("steps must contain at least one approval step")
    roles = {"Contract Management Specialist", "Procurement Review", "Legal Counsel", "Fiscal Review", "Authorized Signatory"}
    sequences = [step.get("sequence", step.get("step_sequence")) for step in steps]
    if any(sequence is None or sequence < 1 for sequence in sequences) or len(set(sequences)) != len(sequences):
        raise ValueError("steps must contain unique positive sequence values")
    if any(step.get("reviewer_role") not in roles or not step.get("assigned_person_id") or not step.get("prerequisite_code") or not step.get("due_at") for step in steps):
        raise ValueError("each step requires reviewer_role, assigned_person_id, prerequisite_code, and due_at")
    con = _con()
    try:
        existing = con.execute("SELECT route_id, route_version, route_status FROM approval_routes WHERE contract_id = ? ORDER BY route_version DESC LIMIT 1", (contract_id,)).fetchone()
        if existing and existing["route_status"] not in {"REJECTED", "CANCELLED"}:
            return {"status": "CONFLICT", "route": _row(existing), "steps_created": 0}
        version = (existing["route_version"] + 1) if existing else 1
        route_id = f"PAR-CSCC-{dates[0].strftime('%Y-%m%d')}-V{version}"
        now = _now_utc()
        initiator = con.execute("SELECT initiator_person_name FROM approval_routes WHERE initiator_person_id = ? ORDER BY route_created_at DESC LIMIT 1", (initiator_person_id,)).fetchone()
        initiator_name = initiator[0] if initiator else initiator_person_id
        route = (route_id, contract_id, version, governing_office_id, initiator_person_id, initiator_name, requested_start_date, requested_end_date, benchmark_end_date, operating_calendar_code, proposed_execution_date, agreement_type, proposed_amount_usd, blocker_count_snapshot, "WAITING", now, now, None)
        with con:
            con.execute("INSERT INTO approval_routes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", route)
            for step in sorted(steps, key=lambda item: item.get("sequence", item.get("step_sequence"))):
                sequence = step.get("sequence", step.get("step_sequence")); step_id = f"PAS-CSCC-{dates[0].strftime('%Y%m%d')}-{version:02d}{sequence:02d}"
                con.execute("INSERT INTO approval_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (step_id, route_id, sequence, step["reviewer_role"], step["assigned_person_id"], step.get("assigned_person_name", step["assigned_person_id"]), step.get("authority_id"), step["prerequisite_code"], step.get("prerequisite_description"), "NOT_STARTED", None, step["due_at"], step.get("condition_text"), now, now))
        return {"status": "OK", "route": {"route_id": route_id, "contract_id": contract_id, "route_version": version, "route_status": "WAITING"}, "steps_created": len(steps)}
    finally:
        con.close()


def record_approval_decision(approval_step_id: str, decision_status: str, condition_text: str | None = None, decision_at: str | None = None, actor_person_id: str = "") -> dict:
    """Record an approval decision after checking signatory prerequisites and persist every accepted field.

    Args:
        approval_step_id: Approval step identifier.
        decision_status: One of APPROVED, REJECTED, RETURNED, ABSTAINED, or CONDITIONAL.
        condition_text: Optional condition or return instruction.
        decision_at: Optional ISO-8601 decision timestamp; omitted uses current UTC time.
        actor_person_id: Person recording the decision.
    Returns:
        A dictionary with prior and new status, decision timestamp, route status, and validation errors.
    """
    allowed = {"APPROVED", "REJECTED", "RETURNED", "ABSTAINED", "CONDITIONAL"}
    if decision_status not in allowed:
        raise ValueError(f"decision_status must be one of {sorted(allowed)}")
    if not actor_person_id.strip():
        raise ValueError("actor_person_id must not be empty")
    timestamp = decision_at or _now_utc()
    con = _con()
    try:
        step = con.execute("SELECT * FROM approval_steps WHERE approval_step_id = ?", (approval_step_id,)).fetchone()
        if step is None:
            return {"status": "NOT_FOUND", "approval_step_id": approval_step_id, "validation_errors": ["STEP_NOT_FOUND"]}
        route = con.execute("SELECT * FROM approval_routes WHERE route_id = ?", (step["route_id"],)).fetchone()
        errors = []
        if step["reviewer_role"] == "Authorized Signatory" and decision_status == "APPROVED":
            prerequisites = con.execute("SELECT reviewer_role, decision_status FROM approval_steps WHERE route_id = ? AND reviewer_role IN ('Legal Counsel', 'Fiscal Review')", (step["route_id"],)).fetchall()
            if any(row["decision_status"] != "APPROVED" for row in prerequisites): errors.append("PREREQUISITE_NOT_MET")
            authority = _signature_authority_result(con, step["assigned_person_id"], "ORG-CSCC", route["agreement_type"], route["proposed_amount_usd"], route["proposed_execution_date"])
            if not authority["authorized"]: errors.append("SIGNATURE_AUTHORITY_NOT_VALID")
        if errors:
            return {"status": "PREREQUISITE_NOT_MET", "approval_step_id": approval_step_id, "previous_decision_status": step["decision_status"], "decision_status": step["decision_status"], "decision_at": step["decision_at"], "route_status": route["route_status"], "validation_errors": errors}
        with con:
            con.execute("UPDATE approval_steps SET decision_status = ?, condition_text = ?, decision_at = ?, updated_at = ? WHERE approval_step_id = ?", (decision_status, condition_text, timestamp, timestamp, approval_step_id))
            all_steps = con.execute("SELECT * FROM approval_steps WHERE route_id = ?", (step["route_id"],)).fetchall()
            route_status = _route_status_for_decision(decision_status, all_steps)
            con.execute("UPDATE approval_routes SET route_status = ?, route_updated_at = ? WHERE route_id = ?", (route_status, timestamp, step["route_id"]))
            con.execute(
                "INSERT INTO approval_decision_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), approval_step_id, step["route_id"],
                    step["assigned_person_id"], actor_person_id.strip(),
                    step["decision_status"], decision_status, timestamp,
                ),
            )
        return {"status": "OK", "approval_step_id": approval_step_id, "previous_decision_status": step["decision_status"], "decision_status": decision_status, "decision_at": timestamp, "route_status": route_status, "validation_errors": []}
    finally:
        con.close()

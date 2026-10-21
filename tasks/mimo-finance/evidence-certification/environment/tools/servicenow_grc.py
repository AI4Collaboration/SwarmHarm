"""ServiceNow GRC methodology review tools backed by the local state database."""
import sqlite3
from pathlib import Path


def _con():
    path = Path(__file__).resolve().parent.parent / "system" / "servicenow_grc" / "state.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_page(page_size, page_token):
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200")
    if page_token is None:
        return 0
    try:
        offset = int(page_token)
    except ValueError as exc:
        raise ValueError("page_token must be a nonnegative integer cursor") from exc
    if offset < 0:
        raise ValueError("page_token must be a nonnegative integer cursor")
    return offset


def _ensure_attestation_tables(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS control_attestations (
        attestation_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        evidence_id TEXT,
        attestation_type TEXT NOT NULL,
        status TEXT NOT NULL,
        attested_by_party_id TEXT NOT NULL,
        attested_by_name TEXT NOT NULL,
        attestation_date TEXT NOT NULL,
        notes TEXT NOT NULL,
        remediation_due_date TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES allocation_methodology_cases(case_id),
        FOREIGN KEY (evidence_id) REFERENCES control_evidence_detail(evidence_id)
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS grc_audit_events (
        audit_event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        actor_party_id TEXT NOT NULL,
        event_date TEXT NOT NULL,
        details TEXT NOT NULL
        )"""
    )


def get_methodology_case(case_id: str):
    """Retrieve a methodology case and its allocation governance attributes.

    Args:
        case_id: ServiceNow GRC methodology case identifier.

    Returns:
        A dictionary containing ``case`` or a structured ``NOT_FOUND`` error.
    """
    if not case_id.strip():
        raise ValueError("case_id is required")
    with _con() as connection:
        row = connection.execute(
            "SELECT * FROM allocation_methodology_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
    if row is None:
        return {"error": {"code": "NOT_FOUND", "message": f"Methodology case {case_id} was not found"}}
    return {"case": dict(row)}


def list_approval_actions(
    case_id: str,
    final_only: bool = False,
    decision: str = None,
    page_size: int = 50,
    page_token: str = None,
):
    """List sequenced approval and review actions for one methodology case.

    Args:
        case_id: ServiceNow GRC methodology case identifier.
        final_only: When true, return only final approval actions.
        decision: Optional approval decision filter.
        page_size: Maximum actions to return, from 1 through 200.
        page_token: Optional nonnegative offset cursor returned by a prior call.

    Returns:
        A dictionary with ``actions``, ``next_page_token``, and ``total_count``.
    """
    if not case_id.strip():
        raise ValueError("case_id is required")
    decisions = {"Approved", "Conditionally Approved", "Rejected", "Challenged", "Acknowledged", "Returned"}
    if decision is not None and decision not in decisions:
        raise ValueError(f"decision must be one of: {', '.join(sorted(decisions))}")
    offset = _validate_page(page_size, page_token)
    clauses, params = ["case_id = ?"], [case_id]
    if final_only:
        clauses.append("final_action_flag = 1")
    if decision is not None:
        clauses.append("decision = ?")
        params.append(decision)
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM approval_actions WHERE {where}", params).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM approval_actions WHERE {where} ORDER BY action_sequence, action_id LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    next_token = str(offset + len(rows)) if offset + len(rows) < total else None
    return {"actions": [dict(row) for row in rows], "next_page_token": next_token, "total_count": total}


def search_control_evidence(
    case_id: str,
    source_system: str = None,
    evidence_type: str = None,
    control_status: str = None,
    in_scope_only: bool = False,
    page_size: int = 50,
    page_token: str = None,
):
    """Search control evidence for a methodology case using governance filters.

    Args:
        case_id: ServiceNow GRC methodology case identifier.
        source_system: Optional exact source-system name.
        evidence_type: Optional controlled evidence category.
        control_status: Optional evidence testing disposition.
        in_scope_only: When true, exclude governance-only evidence.
        page_size: Maximum evidence rows to return, from 1 through 200.
        page_token: Optional nonnegative offset cursor returned by a prior call.

    Returns:
        A dictionary with ``evidence``, ``next_page_token``, and ``total_count``.
    """
    if not case_id.strip():
        raise ValueError("case_id is required")
    evidence_types = {"Controlled Export", "Ledger Reconciliation", "Workbook Test", "Exclusion Test", "No-Restatement Evidence", "Implementation Control"}
    statuses = {"Passed", "Failed", "Superseded", "Orphaned", "Out of Scope"}
    if evidence_type is not None and evidence_type not in evidence_types:
        raise ValueError(f"evidence_type must be one of: {', '.join(sorted(evidence_types))}")
    if control_status is not None and control_status not in statuses:
        raise ValueError(f"control_status must be one of: {', '.join(sorted(statuses))}")
    offset = _validate_page(page_size, page_token)
    clauses, params = ["case_id = ?"], [case_id]
    for column, value in (("source_system", source_system), ("evidence_type", evidence_type), ("control_status", control_status)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if in_scope_only:
        clauses.append("in_scope_flag = 1")
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM control_evidence_detail WHERE {where}", params).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM control_evidence_detail WHERE {where} ORDER BY test_date, evidence_id LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    next_token = str(offset + len(rows)) if offset + len(rows) < total else None
    return {"evidence": [dict(row) for row in rows], "next_page_token": next_token, "total_count": total}


def check_approval_completeness(
    case_id: str,
    required_parties: list = None,
):
    """Evaluate required approvals and the final committee decision for a case.

    Args:
        case_id: ServiceNow GRC methodology case identifier.
        required_parties: Required approver names; defaults to the designated five participants.

    Returns:
        Approval counts, missing parties, qualifying nonfinal matches, final action, and completeness.
    """
    if not case_id.strip():
        raise ValueError("case_id is required")
    if required_parties is None:
        required_parties = ["Elena M. Marquez", "David R. Holloway", "Priya S. Raman", "Michael T. Callahan", "Travelers Expense Allocation Steering Committee"]
    if not required_parties or any(not str(name).strip() for name in required_parties):
        raise ValueError("required_parties must contain at least one nonempty participant name")
    required_parties = list(dict.fromkeys(required_parties))
    with _con() as connection:
        case = connection.execute("SELECT * FROM allocation_methodology_cases WHERE case_id = ?", (case_id,)).fetchone()
        actions = connection.execute(
            "SELECT * FROM approval_actions WHERE case_id = ? ORDER BY action_sequence", (case_id,)
        ).fetchall()
    approved_names = {row["approver_name"] for row in actions if row["decision"] == "Approved"}
    matches = [dict(row) for row in actions if row["approver_name"] in required_parties and row["decision"] == "Approved" and not row["final_action_flag"] and row["approver_role"] != "Evidence Review Panel"]
    finals = [row for row in actions if row["approver_party_id"] == "TRAVELERS_EXPENSE_ALLOCATION_STEERING_COMMITTEE" and row["final_action_flag"]]
    final = dict(finals[0]) if len(finals) == 1 else None
    final_agrees = bool(case and final and final["decision"] == case["decision_status"] and case["approval_date_id"] == "DATE_" + final["action_date"].replace("-", "_"))
    missing = [name for name in required_parties if name not in approved_names]
    return {"required_count": len(required_parties), "approved_count": len(required_parties) - len(missing), "missing_parties": missing, "non_final_matches": matches, "final_committee_action": final, "complete": not missing and final_agrees}


def summarize_control_results(
    case_id: str,
    in_scope_only: bool = False,
    source_system: str = None,
):
    """Aggregate evidence dispositions, checksums, scope, and source-system results.

    Args:
        case_id: ServiceNow GRC methodology case identifier.
        in_scope_only: When true, aggregate only in-scope evidence.
        source_system: Optional exact source-system name.

    Returns:
        Status and checksum counts, scope totals, source breakdown, and unresolved count.
    """
    if not case_id.strip():
        raise ValueError("case_id is required")
    clauses, params = ["case_id = ?"], [case_id]
    if in_scope_only:
        clauses.append("in_scope_flag = 1")
    if source_system is not None:
        clauses.append("source_system = ?")
        params.append(source_system)
    with _con() as connection:
        rows = connection.execute(
            f"SELECT * FROM control_evidence_detail WHERE {' AND '.join(clauses)}", params
        ).fetchall()
    status_labels = ["Passed", "Failed", "Superseded", "Orphaned", "Out of Scope"]
    checksum_labels = ["Valid", "Missing", "Not Applicable"]
    status_counts = {label: sum(row["control_status"] == label for row in rows) for label in status_labels}
    checksum_counts = {label: sum(row["checksum_status"] == label for row in rows) for label in checksum_labels}
    sources = sorted({row["source_system"] for row in rows})
    breakdown = [{"source_system": source, "evidence_count": sum(row["source_system"] == source for row in rows), "passed_count": sum(row["source_system"] == source and row["control_status"] == "Passed" for row in rows)} for source in sources]
    return {"status_counts": status_counts, "checksum_counts": checksum_counts, "in_scope_total": sum(row["in_scope_flag"] == 1 for row in rows), "out_of_scope_total": sum(row["in_scope_flag"] == 0 for row in rows), "source_system_breakdown": breakdown, "unresolved_evidence_count": sum(row["control_status"] in {"Failed", "Orphaned"} or row["checksum_status"] == "Missing" for row in rows)}


def record_control_attestation(
    case_id: str,
    evidence_id: str = None,
    *,
    attestation_type: str,
    status: str,
    attested_by_party_id: str,
    attested_by_name: str,
    attestation_date: str,
    notes: str,
    remediation_due_date: str = None,
):
    """Append a control attestation and immutable audit event to the GRC ledger.

    Args:
        case_id: ServiceNow GRC methodology case identifier.
        evidence_id: Optional evidence record addressed by the attestation.
        attestation_type: Attestation or remediation action category.
        status: Current attestation disposition.
        attested_by_party_id: Stable identifier for the attesting party.
        attested_by_name: Display name of the attesting party.
        attestation_date: Attestation date in ISO ``YYYY-MM-DD`` format.
        notes: Business rationale and supporting details.
        remediation_due_date: Optional ISO due date for remediation.

    Returns:
        Created attestation and audit identifiers with persisted status and timestamp.
    """
    allowed_types = {"Control Owner Attestation", "Management Review", "Remediation Action", "Evidence Certification"}
    allowed_statuses = {"Attested", "Accepted", "Open", "In Progress", "Remediated", "Rejected"}
    if attestation_type not in allowed_types:
        raise ValueError(f"attestation_type must be one of: {', '.join(sorted(allowed_types))}")
    if status not in allowed_statuses:
        raise ValueError(f"status must be one of: {', '.join(sorted(allowed_statuses))}")
    if not all(value.strip() for value in (case_id, attested_by_party_id, attested_by_name, attestation_date, notes)):
        raise ValueError("case_id, attested_by_party_id, attested_by_name, attestation_date, and notes are required")
    if remediation_due_date is not None and remediation_due_date < attestation_date:
        raise ValueError("remediation_due_date cannot precede attestation_date")
    created_at = attestation_date + "T17:00:00Z"
    with _con() as connection:
        _ensure_attestation_tables(connection)
        if connection.execute("SELECT 1 FROM allocation_methodology_cases WHERE case_id = ?", (case_id,)).fetchone() is None:
            raise ValueError(f"case_id {case_id} does not exist")
        if evidence_id is not None:
            evidence = connection.execute("SELECT case_id FROM control_evidence_detail WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if evidence is None or evidence["case_id"] != case_id:
                raise ValueError("evidence_id must exist and belong to case_id")
        ordinal = connection.execute("SELECT COUNT(*) FROM control_attestations WHERE attestation_date = ?", (attestation_date,)).fetchone()[0] + 1
        date_key = attestation_date.replace("-", "")
        attestation_id = f"ATT-{date_key}-{ordinal:03d}"
        audit_event_id = f"AUD-{date_key}-{ordinal:03d}"
        connection.execute("INSERT INTO control_attestations VALUES (?,?,?,?,?,?,?,?,?,?,?)", (attestation_id, case_id, evidence_id, attestation_type, status, attested_by_party_id, attested_by_name, attestation_date, notes, remediation_due_date, created_at))
        details = f"{attestation_type}: {status}; {notes}"
        connection.execute("INSERT INTO grc_audit_events VALUES (?,?,?,?,?,?,?)", (audit_event_id, "CONTROL_ATTESTATION_RECORDED", attestation_id, case_id, attested_by_party_id, created_at, details))
    return {"attestation_id": attestation_id, "case_id": case_id, "evidence_id": evidence_id, "status": status, "created_at": created_at, "audit_event_id": audit_event_id}

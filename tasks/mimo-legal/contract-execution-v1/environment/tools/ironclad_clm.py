"""MCP tools for Ironclad Contract Lifecycle Management control reviews."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path


_DB_PATH = Path(__file__).resolve().parent.parent / "system" / "ironclad_clm" / "state.db"
_APPROVALS_DB_PATH = Path(__file__).resolve().parent.parent / "system" / "power_automate_approvals" / "state.db"
_SOURCE_TYPES = {"POLICY", "CHECKLIST", "STATUTE", "INSTITUTIONAL_FORM"}
_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_RESULTS = {"PASS", "FAIL", "PENDING", "NOT_APPLICABLE", "WAIVED"}
_RESOLUTIONS = {"OPEN", "CLOSED", "WAIVED", "NOT_REQUIRED"}


def _con() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _limit_cursor(limit: int, cursor: str | None) -> tuple[int, int]:
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if cursor is None:
        return limit, 0
    try:
        offset = int(cursor)
    except (TypeError, ValueError) as exc:
        raise ValueError("cursor must be a non-negative integer offset") from exc
    if offset < 0:
        raise ValueError("cursor must be a non-negative integer offset")
    return limit, offset


def _date_value(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 date") from exc


def _contract_or_error(connection: sqlite3.Connection, contract_id: str) -> sqlite3.Row | None:
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise ValueError("contract_id is required")
    return connection.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id.strip(),)).fetchone()


def _pagination(rows: list[dict], limit: int, offset: int) -> tuple[list[dict], str | None]:
    page = rows[offset:offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(rows) else None
    return page, next_cursor


def _applicability(contract: sqlite3.Row, control: sqlite3.Row) -> tuple[bool, str]:
    rule = control["applicability_rule"]
    flags = set(json.loads(contract["exemption_flags"] or "[]"))
    direction = contract["agreement_direction"]
    amount = contract["total_contract_amount_cents"]
    agreement_type = contract["agreement_type"]
    if rule.startswith("exemption_flags CONTAINS"):
        flag = rule.split("'")[1]
        return (flag in flags, f"exemption flag {flag} is {'present' if flag in flags else 'absent'}")
    if "agreement_direction IN" in rule:
        allowed = {part.strip(" '") for part in rule.split("(", 1)[1].split(")", 1)[0].split(",")}
        return (direction in allowed, f"agreement direction is {direction}")
    if rule.startswith("jurisdiction_code ="):
        required = rule.split("'")[1]
        applies = contract["jurisdiction_code"] == required and agreement_type != "CSCC_STANDARD"
        return applies, f"jurisdiction is {contract['jurisdiction_code']}"
    if rule.startswith("agreement_type ="):
        required = rule.split("'")[1]
        return agreement_type == required, f"agreement type is {agreement_type}"
    if "agreement_type <>" in rule:
        excluded = rule.split("'")[1]
        return agreement_type != excluded, f"agreement type is {agreement_type}"
    if "agreement_type LIKE '%SERVICES%'" in rule:
        return "SERVICES" in agreement_type, f"agreement type is {agreement_type}"
    if rule.startswith("agreement_direction = 'INBOUND'"):
        applies = direction == "INBOUND" and (amount or 0) > 1_000_000
        return applies, f"direction is {direction}; amount is {amount}"
    if rule.startswith("direction="):
        scope = rule.split(";", 1)[0].split("=", 1)[1]
        applies = scope == "ANY" or direction == scope
        if "amount>=" in rule:
            threshold = int(rule.rsplit("=", 1)[1])
            applies = applies and amount is not None and amount >= threshold
        return applies, f"background scope {scope}; direction is {direction}"
    return control["agreement_direction_scope"] in {"ANY", direction}, f"direction is {direction}"


def get_contract_record(contract_id: str, include_source_references: bool = False) -> dict:
    """Return the normalized intake record for one contract."""
    with _con() as connection:
        row = _contract_or_error(connection, contract_id)
    if row is None:
        return {"error": {"code": "CONTRACT_NOT_FOUND", "message": "No contract matches the supplied contract_id."}}
    contract = {
        "contract_id": row["contract_id"], "institution_id": row["institution_id"],
        "governing_office_id": row["governing_office_id"],
        "counterparty": {"id": row["counterparty_id"], "name": row["counterparty_name"]},
        "requesting_unit": {"id": row["requesting_unit_id"], "name": row["requesting_unit_name"]},
        "assignments": {key: row[key] for key in ("specialist_person_id", "opportunity_owner_person_id", "business_owner_person_id")},
        "agreement": {"type": row["agreement_type"], "direction": row["agreement_direction"], "jurisdiction_code": row["jurisdiction_code"]},
        "financials": {"total_contract_amount_cents": row["total_contract_amount_cents"], "pricing_data_status": row["pricing_data_status"]},
        "dates": {key: row[key] for key in ("intake_timestamp", "requested_return_date", "service_start_date", "service_end_date")},
        "priority": row["intake_priority"], "review_status": row["review_status"], "exemption_flags": json.loads(row["exemption_flags"]),
    }
    result = {"contract": contract}
    if include_source_references:
        result["source_references"] = {"salesforce_opportunity_id": row["source_opportunity_id"]}
    return result


def search_governing_sources(query: str, source_type: str | None = None, jurisdiction: str | None = None, effective_on: str | None = None, active_only: bool = True, limit: int = 20, cursor: str | None = None) -> dict:
    """Search governing sources by title, issuer, or jurisdiction."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required to avoid an unfiltered source dump")
    if source_type is not None and source_type not in _SOURCE_TYPES:
        raise ValueError("source_type is not recognized")
    effective = _date_value(effective_on, "effective_on") if effective_on else None
    limit, offset = _limit_cursor(limit, cursor)
    clauses = ["(lower(source_title) LIKE ? OR lower(issuing_institution) LIKE ? OR lower(jurisdiction) LIKE ?)"]
    search = f"%{query.strip().lower()}%"; params: list[object] = [search, search, search]
    if source_type: clauses.append("source_type = ?"); params.append(source_type)
    if jurisdiction: clauses.append("jurisdiction = ?"); params.append(jurisdiction)
    if active_only: clauses.append("active_flag = 1")
    if effective:
        clauses += ["effective_date <= ?", "(retired_date IS NULL OR retired_date >= ?)"]; params += [effective.isoformat(), effective.isoformat()]
    with _con() as connection:
        rows = [dict(row) for row in connection.execute("SELECT source_id, source_title, source_type, issuing_institution, effective_date, retired_date, jurisdiction, source_version, source_url FROM governing_sources WHERE " + " AND ".join(clauses) + " ORDER BY effective_date DESC, source_id", params)]
    items, next_cursor = _pagination(rows, limit, offset)
    return {"items": items, "next_cursor": next_cursor, "total_estimate": len(rows)}


def list_applicable_controls(contract_id: str, categories: list[str] | None = None, severities: list[str] | None = None, include_not_applicable: bool = False, limit: int = 50, cursor: str | None = None) -> dict:
    """List control applicability for a contract using its normalized intake data."""
    categories, severities = categories or [], severities or []
    if not all(isinstance(value, str) for value in categories) or not set(severities) <= _SEVERITIES:
        raise ValueError("categories must be strings and severities must be recognized")
    limit, offset = _limit_cursor(limit, cursor)
    with _con() as connection:
        contract = _contract_or_error(connection, contract_id)
        if contract is None:
            return {"error": {"code": "CONTRACT_NOT_FOUND", "message": "No contract matches the supplied contract_id."}}
        controls = connection.execute("SELECT c.*, s.source_title, s.source_version FROM checklist_controls c JOIN governing_sources s ON s.source_id=c.source_id WHERE c.active_flag=1 ORDER BY c.control_code").fetchall()
    records = []
    for control in controls:
        applies, reason = _applicability(contract, control)
        if categories and control["control_category"] not in categories: continue
        if severities and control["severity"] not in severities: continue
        if applies or include_not_applicable:
            records.append({"control_id": control["control_id"], "control_code": control["control_code"], "control_name": control["control_name"], "category": control["control_category"], "severity": control["severity"], "ownership_role": control["ownership_role"], "blocked_stage": control["blocked_stage"], "applicable_flag": applies, "applicability_reason": reason, "evidence_requirement": control["evidence_requirement"], "source": {"source_id": control["source_id"], "title": control["source_title"], "version": control["source_version"]}})
    items, next_cursor = _pagination(records, limit, offset)
    return {"contract_id": contract["contract_id"], "items": items, "next_cursor": next_cursor, "summary": {"applicable_count": sum(record["applicable_flag"] for record in records), "not_applicable_count": sum(not record["applicable_flag"] for record in records)}}


def evaluate_contract_controls(contract_id: str, result_statuses: list[str] | None = None, resolution_statuses: list[str] | None = None, include_duplicates: bool = False, include_evidence: bool = True, limit: int = 50, cursor: str | None = None) -> dict:
    """Return control-evaluation outcomes for one contract."""
    result_statuses, resolution_statuses = result_statuses or [], resolution_statuses or []
    if not set(result_statuses) <= _RESULTS or not set(resolution_statuses) <= _RESOLUTIONS:
        raise ValueError("result_statuses or resolution_statuses contains an unrecognized value")
    limit, offset = _limit_cursor(limit, cursor)
    with _con() as connection:
        contract = _contract_or_error(connection, contract_id)
        if contract is None:
            return {"error": {"code": "CONTRACT_NOT_FOUND", "message": "No contract matches the supplied contract_id."}}
        clauses=["ce.contract_id = ?"]; params: list[object]=[contract["contract_id"]]
        if not include_duplicates: clauses.append("ce.duplicate_of_evaluation_id IS NULL")
        if result_statuses: clauses.append("ce.result_status IN (%s)" % ",".join("?"*len(result_statuses))); params += result_statuses
        if resolution_statuses: clauses.append("ce.resolution_status IN (%s)" % ",".join("?"*len(resolution_statuses))); params += resolution_statuses
        rows=connection.execute("SELECT ce.*, cc.control_code, cc.control_name, cc.severity, cc.ownership_role, cc.blocked_stage FROM control_evaluations ce JOIN checklist_controls cc ON cc.control_id=ce.control_id WHERE " + " AND ".join(clauses) + " ORDER BY ce.evaluated_at, ce.evaluation_id", params).fetchall()
    records=[]
    for row in rows:
        item={"evaluation_id":row["evaluation_id"], "control":{"control_id":row["control_id"],"control_code":row["control_code"],"name":row["control_name"],"severity":row["severity"],"ownership_role":row["ownership_role"],"blocked_stage":row["blocked_stage"]}, "result_status":row["result_status"], "applicable_flag":bool(row["applicable_flag"]), "resolution_status":row["resolution_status"], "deficiency_summary":row["deficiency_summary"], "evaluated_value":row["evaluated_value"], "evaluated_at":row["evaluated_at"], "resolved_at":row["resolved_at"], "duplicate_of_evaluation_id":row["duplicate_of_evaluation_id"]}
        if include_evidence: item["evidence_reference"]=row["evidence_reference"]
        records.append(item)
    items, next_cursor=_pagination(records,limit,offset)
    summary={key:sum(item["result_status"]==key.upper() for item in records) for key in ("pass","fail","pending","not_applicable","waived")}
    summary["open_deficiencies"]=sum(item["applicable_flag"] and item["result_status"]=="FAIL" and item["resolution_status"]=="OPEN" and item["duplicate_of_evaluation_id"] is None for item in records)
    return {"contract_id":contract["contract_id"],"items":items,"next_cursor":next_cursor,"summary":summary}


def count_open_deficiencies(contract_id: str, severities: list[str] | None = None, ownership_roles: list[str] | None = None, blocked_stages: list[str] | None = None) -> dict:
    """Count non-duplicate open failed controls, optionally by routing metadata."""
    severities, ownership_roles, blocked_stages = severities or [], ownership_roles or [], blocked_stages or []
    if not set(severities) <= _SEVERITIES or not all(isinstance(value, str) for value in ownership_roles + blocked_stages): raise ValueError("filters contain an unrecognized value")
    with _con() as connection:
        contract=_contract_or_error(connection,contract_id)
        if contract is None: return {"error":{"code":"CONTRACT_NOT_FOUND","message":"No contract matches the supplied contract_id."}}
        clauses=["ce.contract_id=?","ce.applicable_flag=1","ce.result_status='FAIL'","ce.resolution_status='OPEN'","ce.duplicate_of_evaluation_id IS NULL"]; params=[contract["contract_id"]]
        for column, values in (("cc.severity",severities),("cc.ownership_role",ownership_roles),("cc.blocked_stage",blocked_stages)):
            if values: clauses.append(f"{column} IN ({','.join('?'*len(values))})"); params += values
        rows=connection.execute("SELECT cc.severity,cc.ownership_role,cc.blocked_stage FROM control_evaluations ce JOIN checklist_controls cc ON cc.control_id=ce.control_id WHERE " + " AND ".join(clauses),params).fetchall()
    by_severity={severity:sum(row["severity"]==severity for row in rows) for severity in sorted(_SEVERITIES)}
    by_owner=sorted(({"ownership_role":role,"count":sum(row["ownership_role"]==role for row in rows)} for role in {row["ownership_role"] for row in rows}),key=lambda item:item["ownership_role"])
    stages=sorted(({"blocked_stage":stage,"count":sum(row["blocked_stage"]==stage for row in rows)} for stage in {row["blocked_stage"] for row in rows}),key=lambda item:item["blocked_stage"])
    return {"contract_id":contract["contract_id"],"count":len(rows),"criteria":{"applicable_flag":1,"result_status":"FAIL","resolution_status":"OPEN","exclude_duplicates":True},"by_severity":by_severity,"by_owner_role":by_owner,"blocked_stages":stages}


def record_control_resolution(evaluation_id: str, resolution_status: str, resolution_note: str, evidence_reference: str | None = None, waiver_authority_person_id: str | None = None, resolved_at: str | None = None, expected_current_status: str = "OPEN") -> dict:
    """Resolve or waive one non-duplicate control evaluation with optimistic locking."""
    if resolution_status not in {"CLOSED","WAIVED"}: raise ValueError("resolution_status must be CLOSED or WAIVED")
    if not isinstance(resolution_note,str) or not resolution_note.strip(): raise ValueError("resolution_note is required")
    if resolution_status=="WAIVED" and (not evidence_reference or not waiver_authority_person_id): raise ValueError("WAIVED requires evidence_reference and waiver_authority_person_id")
    if resolved_at is None: resolved_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    else:
        try: datetime.fromisoformat(resolved_at.replace("Z","+00:00"))
        except ValueError as exc: raise ValueError("resolved_at must be an ISO-8601 timestamp") from exc
    with _con() as connection:
        row=connection.execute("SELECT * FROM control_evaluations WHERE evaluation_id=?",(evaluation_id,)).fetchone()
        if row is None: return {"error":{"code":"EVALUATION_NOT_FOUND","message":"No evaluation matches the supplied evaluation_id."}}
        if row["duplicate_of_evaluation_id"] is not None: raise ValueError("duplicate evaluations cannot be independently resolved")
        if row["resolution_status"] != expected_current_status: return {"error":{"code":"RESOLUTION_STATUS_CONFLICT","current_status":row["resolution_status"],"message":"The evaluation status changed before this resolution was recorded."}}
        connection.execute("UPDATE control_evaluations SET resolution_status=?, evidence_reference=COALESCE(?,evidence_reference), waiver_authority_person_id=?, resolved_at=?, resolution_note=? WHERE evaluation_id=?",(resolution_status,evidence_reference,waiver_authority_person_id,resolved_at,resolution_note.strip(),evaluation_id)); connection.commit()
        updated=connection.execute("SELECT * FROM control_evaluations WHERE evaluation_id=?",(evaluation_id,)).fetchone()
    count=count_open_deficiencies(updated["contract_id"])["count"]
    evaluation={key:updated[key] for key in ("evaluation_id","contract_id","control_id","result_status","resolution_status","evidence_reference","waiver_authority_person_id","resolved_at","resolution_note")}
    return {"evaluation":evaluation,"open_deficiency_count_after":count}


def issue_service_authorization(contract_id: str, route_id: str, actor_person_id: str, idempotency_key: str) -> dict:
    """Issue the service authorization after the contract's approval route is complete.

    Args:
        contract_id: Contract to authorize for service delivery.
        route_id: Completed approval route for the contract.
        actor_person_id: Person issuing the authorization.
        idempotency_key: Stable request identifier for retry protection.
    Returns:
        The existing or newly issued service authorization.
    """
    for value, field in ((contract_id, "contract_id"), (route_id, "route_id"),
                         (actor_person_id, "actor_person_id"), (idempotency_key, "idempotency_key")):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
    with sqlite3.connect(_APPROVALS_DB_PATH) as approvals:
        approvals.row_factory = sqlite3.Row
        route = approvals.execute("SELECT * FROM approval_routes WHERE route_id = ?", (route_id.strip(),)).fetchone()
        if route is None or route["contract_id"] != contract_id.strip():
            return {"status": "ROUTE_NOT_FOUND", "authorization": None}
        steps = approvals.execute(
            "SELECT * FROM approval_steps WHERE route_id = ? ORDER BY step_sequence", (route_id.strip(),)
        ).fetchall()
        if route["route_status"] != "APPROVED" or not steps or any(row["decision_status"] != "APPROVED" for row in steps):
            return {"status": "ROUTE_INCOMPLETE", "route_status": route["route_status"], "authorization": None}
        amount_cents = int(route["proposed_amount_usd"]) * 100
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _con() as connection:
        contract = _contract_or_error(connection, contract_id.strip())
        if contract is None:
            return {"status": "CONTRACT_NOT_FOUND", "authorization": None}
        existing = connection.execute(
            "SELECT * FROM service_authorizations WHERE idempotency_key = ?", (idempotency_key.strip(),)
        ).fetchone()
        if existing is not None:
            return {"status": "EXISTS", "authorization": dict(existing)}
        authorization_id = "SA-" + uuid.uuid4().hex[:12].upper()
        connection.execute(
            "INSERT INTO service_authorizations VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)",
            (
                authorization_id, contract["contract_id"], route_id.strip(), amount_cents,
                contract["service_start_date"], contract["service_end_date"],
                actor_person_id.strip(), timestamp, idempotency_key.strip(),
            ),
        )
        connection.commit()
        issued = connection.execute(
            "SELECT * FROM service_authorizations WHERE authorization_id = ?", (authorization_id,)
        ).fetchone()
    return {"status": "ISSUED", "authorization": dict(issued)}

"""Tools for querying and updating the Workday Financial Management fixture."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent.parent / "system" / "workday_financial_management" / "state.db"
LINE_STATUSES = {"finance_coded", "ready_to_invoice", "on_hold", "closed", "void"}
REVIEW_STATUSES = {"pending", "approved", "approved_with_conditions", "additional_pricing_required", "rejected", "superseded"}
CERTIFICATION_STATUSES = {"not_reviewed", "not_certified", "certified", "not_applicable"}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _iso_date(value: str | None, field: str) -> str:
    if value is None:
        return date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date in YYYY-MM-DD format") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def get_cost_center(requesting_unit_id: str, as_of_date: str | None = None, include_inactive: bool = False) -> dict:
    """Return the effective cost center for a canonical requesting unit."""
    requesting_unit_id = _require_text(requesting_unit_id, "requesting_unit_id")
    effective_date = _iso_date(as_of_date, "as_of_date")
    clauses = ["requesting_unit_id = ?", "effective_start_date <= ?", "(effective_end_date IS NULL OR effective_end_date >= ?)"]
    parameters: list[Any] = [requesting_unit_id, effective_date, effective_date]
    if not include_inactive:
        clauses.append("active_status = 'active'")
    with _connect() as connection:
        row = connection.execute(
            f"SELECT cost_center_id, institution_id, requesting_unit_id, requesting_unit_name, manager_person_id, manager_name, fund_code, program_code, revenue_worktag, active_status, effective_start_date, effective_end_date FROM cost_centers WHERE {' AND '.join(clauses)} ORDER BY CASE active_status WHEN 'active' THEN 0 ELSE 1 END, effective_start_date DESC LIMIT 1",
            parameters,
        ).fetchone()
    if row is None:
        return {"cost_center": None, "error": {"code": "NOT_FOUND", "message": f"No effective cost center was found for {requesting_unit_id} on {effective_date}."}}
    return {"cost_center": _row(row), "error": None}


def list_contract_financial_lines(contract_id: str, line_status: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """List paginated Workday financial lines for one contract."""
    contract_id = _require_text(contract_id, "contract_id")
    if line_status is not None and line_status not in LINE_STATUSES:
        raise ValueError(f"line_status must be one of {sorted(LINE_STATUSES)} or None")
    if not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")
    clauses = ["contract_id = ?"]
    parameters: list[Any] = [contract_id]
    if line_status is not None:
        clauses.append("line_status = ?")
        parameters.append(line_status)
    where = " AND ".join(clauses)
    offset = (page - 1) * page_size
    columns = "financial_line_id, contract_id, cost_center_id, source_quote_line_id, source_quote_record_state, fee_category, line_description, quantity, amount_usd, revenue_worktag, invoice_schedule, payment_method, payment_timeline_days, service_start_date, service_end_date, line_status"
    with _connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM contract_financial_lines WHERE {where}", parameters).fetchone()[0]
        rows = connection.execute(f"SELECT {columns} FROM contract_financial_lines WHERE {where} ORDER BY financial_line_id LIMIT ? OFFSET ?", [*parameters, page_size, offset]).fetchall()
    return {"items": [_row(row) for row in rows], "page": page, "page_size": page_size, "total_count": total, "has_more": offset + len(rows) < total}


def reconcile_quote_to_financial_lines(contract_id: str, quote_lines: list[dict], include_retired: bool = True) -> dict:
    """Reconcile caller-supplied active quote lines to stored Workday financial lines."""
    contract_id = _require_text(contract_id, "contract_id")
    if not isinstance(quote_lines, list):
        raise ValueError("quote_lines must be an array")
    supplied: dict[str, dict] = {}
    for index, item in enumerate(quote_lines):
        if not isinstance(item, dict):
            raise ValueError(f"quote_lines[{index}] must be an object")
        quote_line_id = _require_text(item.get("quote_line_id"), f"quote_lines[{index}].quote_line_id")
        if quote_line_id in supplied:
            raise ValueError(f"Duplicate quote_line_id: {quote_line_id}")
        amount = item.get("amount_usd")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError(f"quote_lines[{index}].amount_usd must be a nonnegative whole-dollar integer")
        supplied[quote_line_id] = item
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM contract_financial_lines WHERE contract_id = ? AND line_status <> 'void' ORDER BY financial_line_id", (contract_id,)).fetchall()
    current = {row["source_quote_line_id"]: row for row in rows if row["source_quote_record_state"] == "current_extract"}
    proposed_total = sum(item["amount_usd"] for item in supplied.values() if str(item.get("status", "ACTIVE")).upper() == "ACTIVE")
    finance_ready_total = sum(row["amount_usd"] for row in current.values() if row["line_status"] in {"finance_coded", "ready_to_invoice"})
    missing = []
    differences = []
    matched = 0
    for quote_line_id, item in supplied.items():
        if str(item.get("status", "ACTIVE")).upper() != "ACTIVE":
            continue
        workday = current.get(quote_line_id)
        if workday is None:
            missing.append({"quote_line_id": quote_line_id, "amount_usd": item["amount_usd"], "reason": "No current Workday financial line exists for the active quote line."})
            continue
        matched += 1
        for field, supplied_field, stored_field in (("amount_usd", "amount_usd", "amount_usd"), ("fee_category", "fee_category", "fee_category"), ("revenue_worktag", "revenue_worktag", "revenue_worktag")):
            if item.get(supplied_field) != workday[stored_field]:
                differences.append({"quote_line_id": quote_line_id, "field": field, "salesforce_value": item.get(supplied_field), "workday_value": workday[stored_field]})
    retired = []
    if include_retired:
        retired = [{"financial_line_id": row["financial_line_id"], "source_quote_line_id": row["source_quote_line_id"], "amount_usd": row["amount_usd"]} for row in rows if row["source_quote_record_state"] == "retired_not_in_current_extract" and row["source_quote_line_id"] not in supplied]
    difference = proposed_total - finance_ready_total
    return {"contract_id": contract_id, "proposed_total_usd": proposed_total, "finance_ready_total_usd": finance_ready_total, "difference_usd": difference, "matched_count": matched, "missing_in_workday": missing, "differences": differences, "retired_workday_references": retired, "is_reconciled": difference == 0 and not missing and not differences}


def get_fiscal_review(contract_id: str, current_only: bool = True) -> dict:
    """Retrieve fiscal-review decisions for one contract, newest first."""
    contract_id = _require_text(contract_id, "contract_id")
    where = "contract_id = ?" + (" AND is_current = 1" if current_only else "")
    columns = "fiscal_review_id, contract_id, cost_center_id, reviewer_person_id, reviewer_name, review_status, funds_certification_status, missing_data_reason_code, missing_data_detail, missing_source_quote_line_id, missing_amount_usd, decision_conditions, evidence_reference, requested_at, approval_timestamp, is_current"
    with _connect() as connection:
        rows = connection.execute(f"SELECT {columns} FROM fiscal_reviews WHERE {where} ORDER BY requested_at DESC, fiscal_review_id DESC", (contract_id,)).fetchall()
    items = []
    for row in rows:
        item = _row(row)
        item["is_current"] = bool(item["is_current"])
        items.append(item)
    return {"items": items}


def validate_payment_terms(contract_id: str, require_active_cost_center: bool = True) -> dict:
    """Validate financial coding, payment terms, service dates, and responsible cost centers."""
    contract_id = _require_text(contract_id, "contract_id")
    with _connect() as connection:
        lines = connection.execute("SELECT * FROM contract_financial_lines WHERE contract_id = ? AND line_status <> 'void' ORDER BY financial_line_id", (contract_id,)).fetchall()
        center_ids = sorted({row["cost_center_id"] for row in lines})
        centers = []
        if center_ids:
            placeholders = ",".join("?" for _ in center_ids)
            centers = connection.execute(f"SELECT cost_center_id, active_status, manager_person_id, revenue_worktag FROM cost_centers WHERE cost_center_id IN ({placeholders}) ORDER BY cost_center_id", center_ids).fetchall()
    center_map = {row["cost_center_id"]: row for row in centers}
    issues = []
    if not lines:
        issues.append({"financial_line_id": None, "code": "NO_FINANCIAL_LINES", "severity": "error", "field": "contract_id", "message": "No non-void Workday financial lines exist for this contract."})
    for line in lines:
        line_id = line["financial_line_id"]
        center = center_map.get(line["cost_center_id"])
        checks = []
        if center is None:
            checks.append(("COST_CENTER_NOT_FOUND", "cost_center_id", "The responsible cost center does not exist."))
        elif require_active_cost_center and center["active_status"] != "active":
            checks.append(("INACTIVE_COST_CENTER", "cost_center_id", "The responsible cost center is inactive."))
        if not line["revenue_worktag"].strip():
            checks.append(("MISSING_REVENUE_WORKTAG", "revenue_worktag", "An active revenue worktag is required."))
        elif center is not None and line["revenue_worktag"] != center["revenue_worktag"]:
            checks.append(("WORKTAG_MISMATCH", "revenue_worktag", "The financial line worktag does not match its cost center."))
        if not line["invoice_schedule"].strip():
            checks.append(("MISSING_INVOICE_SCHEDULE", "invoice_schedule", "An invoice schedule is required."))
        if not line["payment_method"].strip():
            checks.append(("MISSING_PAYMENT_METHOD", "payment_method", "A payment method is required."))
        if line["payment_timeline_days"] < 0:
            checks.append(("INVALID_PAYMENT_TIMELINE", "payment_timeline_days", "Payment timeline must be nonnegative."))
        if line["service_start_date"] > line["service_end_date"]:
            checks.append(("INVALID_SERVICE_DATES", "service_end_date", "Service end date precedes service start date."))
        for code, field, message in checks:
            issues.append({"financial_line_id": line_id, "code": code, "severity": "error", "field": field, "message": message})
    finance_total = sum(row["amount_usd"] for row in lines if row["line_status"] in {"finance_coded", "ready_to_invoice"})
    return {"contract_id": contract_id, "is_valid": not issues, "finance_ready_total_usd": finance_total, "line_count": len(lines), "issues": issues, "cost_centers": [_row(row) for row in centers]}


def record_fiscal_review_decision(contract_id: str, cost_center_id: str, reviewer_person_id: str, reviewer_name: str, review_status: str, funds_certification_status: str, missing_data_reason_code: str | None = None, missing_data_detail: str | None = None, missing_source_quote_line_id: str | None = None, missing_amount_usd: int | None = None, decision_conditions: str | None = None, evidence_reference: str | None = None, idempotency_key: str = "") -> dict:
    """Record an idempotent fiscal decision and supersede prior current reviews atomically."""
    fields = {"contract_id": contract_id, "cost_center_id": cost_center_id, "reviewer_person_id": reviewer_person_id, "reviewer_name": reviewer_name, "idempotency_key": idempotency_key}
    try:
        fields = {key: _require_text(value, key) for key, value in fields.items()}
    except ValueError as exc:
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "VALIDATION_ERROR", "message": str(exc), "field": str(exc).split(" must", 1)[0]}}
    if review_status not in REVIEW_STATUSES:
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "VALIDATION_ERROR", "message": "Invalid review_status.", "field": "review_status"}}
    if funds_certification_status not in CERTIFICATION_STATUSES:
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "VALIDATION_ERROR", "message": "Invalid funds_certification_status.", "field": "funds_certification_status"}}
    if review_status in {"approved", "approved_with_conditions"} and funds_certification_status != "certified":
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "INVALID_STATUS_COMBINATION", "message": "Approved decisions require certified funds.", "field": "funds_certification_status"}}
    if review_status in {"pending", "additional_pricing_required", "rejected"} and funds_certification_status == "certified":
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "INVALID_STATUS_COMBINATION", "message": "Unresolved or rejected decisions cannot certify funds.", "field": "funds_certification_status"}}
    if missing_amount_usd is not None and (not isinstance(missing_amount_usd, int) or isinstance(missing_amount_usd, bool) or missing_amount_usd < 0):
        return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "VALIDATION_ERROR", "message": "missing_amount_usd must be a nonnegative whole-dollar integer.", "field": "missing_amount_usd"}}
    review_id = "WDFR-IDEM-" + hashlib.sha256(fields["idempotency_key"].encode()).hexdigest()[:16].upper()
    now = _utc_now()
    approval_timestamp = now if review_status in {"approved", "approved_with_conditions"} else None
    with _connect() as connection:
        existing = connection.execute("SELECT fiscal_review_id, contract_id, cost_center_id, reviewer_person_id, review_status, funds_certification_status, approval_timestamp, is_current FROM fiscal_reviews WHERE fiscal_review_id = ?", (review_id,)).fetchone()
        if existing is not None:
            item = _row(existing); item["is_current"] = bool(item["is_current"])
            return {"fiscal_review": item, "superseded_review_ids": [], "created": False, "error": None}
        center = connection.execute("SELECT active_status FROM cost_centers WHERE cost_center_id = ?", (fields["cost_center_id"],)).fetchone()
        if center is None:
            return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "COST_CENTER_NOT_FOUND", "message": "The cost center does not exist.", "field": "cost_center_id"}}
        if center["active_status"] != "active":
            return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "INACTIVE_COST_CENTER", "message": "Fiscal decisions require an active cost center.", "field": "cost_center_id"}}
        if connection.execute("SELECT 1 FROM contract_financial_lines WHERE contract_id = ? LIMIT 1", (fields["contract_id"],)).fetchone() is None:
            return {"fiscal_review": None, "superseded_review_ids": [], "created": False, "error": {"code": "CONTRACT_NOT_FOUND", "message": "No Workday financial lines exist for the contract.", "field": "contract_id"}}
        prior = [row[0] for row in connection.execute("SELECT fiscal_review_id FROM fiscal_reviews WHERE contract_id = ? AND is_current = 1 ORDER BY fiscal_review_id", (fields["contract_id"],)).fetchall()]
        connection.execute("UPDATE fiscal_reviews SET is_current = 0, review_status = CASE WHEN review_status IN ('pending','additional_pricing_required') THEN 'superseded' ELSE review_status END, updated_at = ? WHERE contract_id = ? AND is_current = 1", (now, fields["contract_id"]))
        connection.execute(
            "INSERT INTO fiscal_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (review_id, fields["contract_id"], fields["cost_center_id"], fields["reviewer_person_id"], fields["reviewer_name"], review_status, funds_certification_status, missing_data_reason_code, missing_data_detail, missing_source_quote_line_id, missing_amount_usd, decision_conditions, evidence_reference, now, approval_timestamp, 1, now, now),
        )
        connection.commit()
    item = {"fiscal_review_id": review_id, "contract_id": fields["contract_id"], "cost_center_id": fields["cost_center_id"], "reviewer_person_id": fields["reviewer_person_id"], "review_status": review_status, "funds_certification_status": funds_certification_status, "approval_timestamp": approval_timestamp, "is_current": True}
    return {"fiscal_review": item, "superseded_review_ids": prior, "created": True, "error": None}

"""MCP-style tools for Tyler Munis Accounts Payable and Retainage."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DB_PATH = Path(__file__).resolve().parent.parent / "system" / "munis_ap" / "state.db"
_DOCUMENT_TYPES = {"PAYMENT_APPLICATION", "PAYMENT_CERTIFICATE", "PRIOR_DISBURSEMENT", "VENDOR_INVOICE", "CREDIT_MEMO"}
_DOCUMENT_STATUSES = {"SUBMITTED", "UNDER_REVIEW", "RECOMMENDED", "AUTHORIZED_QUEUE", "PAID", "VOID", "CLOSED"}
_COMPONENT_CODES = {"COMPLETED_WORK", "STORED_MATERIAL", "EXCLUDED_STORED_MATERIAL", "PRIOR_PAYMENTS", "CURRENT_PAYMENT_DUE", "TAX", "FREIGHT", "OTHER"}
_TRANSACTION_STATUSES = {"ISSUED", "CLEARED", "VOIDED", "REVERSED"}
_VALID_PAYMENT_STATUSES = {"CLEARED", "ISSUED"}
_METRIC_CODES = {"ACCEPTED_COMPLETED_WORK", "SUBMITTED_COMPLETED_WORK", "SUBMITTED_STORED_MATERIAL", "VALID_PRIOR_PAYMENTS", "CONTRACT_SUM_TO_DATE", "TOTAL_EARNED_LESS_RETAINAGE", "CURRENT_PAYMENT_ROUNDED", "BALANCE_TO_FINISH", "OTHER"}


def _con() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_page(offset: int, page_size: int, maximum: int = 100) -> None:
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    if not 1 <= page_size <= maximum:
        raise ValueError(f"page_size must be between 1 and {maximum}")


def _validate_date(value: str | None, field: str) -> None:
    if value is None:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format") from exc


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _retainage(amount_cents: int, rate_bp: int) -> int:
    return (amount_cents * rate_bp + 5000) // 10000


def _load_version(con: sqlite3.Connection, ap_document_id: str, calculation_version: int) -> list[dict]:
    rows = con.execute(
        """SELECT metric_code, amount_cents, rate_bp, is_recommended, reviewer_id
           FROM certificate_calculations
           WHERE ap_document_id = ? AND calculation_version = ?
           ORDER BY metric_code""",
        (ap_document_id, calculation_version),
    ).fetchall()
    return [dict(row) for row in rows]


def _document_application(con: sqlite3.Connection, ap_document_id: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT ap_document_id, application_id, document_status FROM ap_documents WHERE ap_document_id = ?",
        (ap_document_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown ap_document_id: {ap_document_id}")
    return row


def _prior_payment_total(con: sqlite3.Connection, application_id: str, statuses: list[str]) -> int:
    row = con.execute(
        f"""SELECT COALESCE(SUM(p.amount_cents), 0)
            FROM payment_transactions p
            JOIN ap_documents d ON d.ap_document_id = p.ap_document_id
            WHERE d.application_id = ? AND p.transaction_status IN ({_placeholders(statuses)})""",
        [application_id, *statuses],
    ).fetchone()
    return int(row[0])


def _calculate_due(con: sqlite3.Connection, ap_document_id: str, calculation_version: int, statuses: list[str]) -> dict:
    document = _document_application(con, ap_document_id)
    metrics = _load_version(con, ap_document_id, calculation_version)
    if not metrics:
        raise ValueError(f"No calculation version {calculation_version} exists for {ap_document_id}")
    by_code = {row["metric_code"]: row for row in metrics}
    earning_codes = [code for code in ("ACCEPTED_COMPLETED_WORK", "SUBMITTED_COMPLETED_WORK", "SUBMITTED_STORED_MATERIAL") if code in by_code]
    if not earning_codes:
        raise ValueError("Calculation version is missing accepted or submitted earnings metrics")
    gross = sum(int(by_code[code]["amount_cents"]) for code in earning_codes)
    retainage = 0
    for code in earning_codes:
        rate = by_code[code]["rate_bp"]
        if rate is None:
            raise ValueError(f"Metric {code} is missing rate_bp required for retainage")
        retainage += _retainage(int(by_code[code]["amount_cents"]), int(rate))
    earned_less = gross - retainage
    prior = _prior_payment_total(con, document["application_id"], statuses)
    underlying = earned_less - prior
    whole_dollars = (underlying + 50) // 100
    return {
        "ap_document_id": ap_document_id,
        "calculation_version": calculation_version,
        "gross_earned_cents": gross,
        "total_retainage_cents": retainage,
        "earned_less_retainage_cents": earned_less,
        "valid_prior_payments_cents": prior,
        "underlying_current_due_cents": underlying,
        "current_payment_due_whole_dollars": whole_dollars,
        "current_payment_due_cents": whole_dollars * 100,
    }


def _ensure_mutation_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS munis_ap_idempotency (
               operation_name TEXT NOT NULL,
               idempotency_key TEXT NOT NULL,
               request_json TEXT NOT NULL,
               response_json TEXT NOT NULL,
               created_at TEXT NOT NULL,
               PRIMARY KEY (operation_name, idempotency_key)
           )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS payment_authorizations (
               authorization_id TEXT PRIMARY KEY,
               ap_document_id TEXT NOT NULL,
               calculation_version INTEGER NOT NULL,
               authorized_by TEXT NOT NULL,
               authorized_amount_cents INTEGER NOT NULL,
               previous_status TEXT NOT NULL,
               document_status TEXT NOT NULL,
               idempotency_key TEXT NOT NULL UNIQUE,
               authorized_at TEXT NOT NULL,
               FOREIGN KEY (ap_document_id) REFERENCES ap_documents(ap_document_id)
           )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS cash_settlements (
               settlement_id TEXT PRIMARY KEY,
               authorization_id TEXT NOT NULL UNIQUE,
               ap_document_id TEXT NOT NULL,
               vendor_id TEXT NOT NULL,
               amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
               currency TEXT NOT NULL CHECK (currency = 'USD'),
               settlement_status TEXT NOT NULL CHECK (settlement_status = 'SETTLED'),
               settled_at TEXT NOT NULL,
               FOREIGN KEY (authorization_id) REFERENCES payment_authorizations(authorization_id),
               FOREIGN KEY (ap_document_id) REFERENCES ap_documents(ap_document_id),
               FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
           )"""
    )


def _idempotent_result(con: sqlite3.Connection, operation: str, key: str, request: dict) -> dict | None:
    row = con.execute(
        "SELECT request_json, response_json FROM munis_ap_idempotency WHERE operation_name = ? AND idempotency_key = ?",
        (operation, key),
    ).fetchone()
    if row is None:
        return None
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))
    if row["request_json"] != request_json:
        raise ValueError("idempotency_key was already used with a different request")
    return json.loads(row["response_json"])


def _store_idempotent_result(con: sqlite3.Connection, operation: str, key: str, request: dict, response: dict, created_at: str) -> None:
    con.execute(
        "INSERT INTO munis_ap_idempotency VALUES (?, ?, ?, ?, ?)",
        (
            operation,
            key,
            json.dumps(request, sort_keys=True, separators=(",", ":")),
            json.dumps(response, sort_keys=True, separators=(",", ":")),
            created_at,
        ),
    )


def search_vendor_documents(vendor_id: str = None, canonical_entity_id: str = None, application_id: str = None, document_type: str = None, document_status: str = None, date_from: str = None, date_to: str = None, offset: int = 0, page_size: int = 50) -> dict:
    """Search AP documents by vendor, entity, application, status, type, or date.

    Args:
        vendor_id: Exact Munis vendor identifier.
        canonical_entity_id: Exact enterprise entity identifier linked to the vendor.
        application_id: Exact payment-application identifier.
        document_type: Optional AP document type enum.
        document_status: Optional AP workflow status enum.
        date_from: Optional inclusive document-date lower bound in YYYY-MM-DD format.
        date_to: Optional inclusive document-date upper bound in YYYY-MM-DD format.
        offset: Zero-based result offset.
        page_size: Number of rows to return, from 1 through 100.

    Returns:
        A dictionary containing items, offset, page_size, and the total matching row count.
    """
    _validate_page(offset, page_size)
    _validate_date(date_from, "date_from")
    _validate_date(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    if document_type and document_type not in _DOCUMENT_TYPES:
        raise ValueError(f"document_type must be one of {sorted(_DOCUMENT_TYPES)}")
    if document_status and document_status not in _DOCUMENT_STATUSES:
        raise ValueError(f"document_status must be one of {sorted(_DOCUMENT_STATUSES)}")
    if not any([vendor_id, canonical_entity_id, application_id, document_type, document_status, date_from, date_to]):
        raise ValueError("Provide at least one vendor, application, type, status, or date filter")
    clauses, params = [], []
    for column, value in (("d.vendor_id", vendor_id), ("v.canonical_entity_id", canonical_entity_id), ("d.application_id", application_id), ("d.document_type", document_type), ("d.document_status", document_status)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if date_from:
        clauses.append("d.document_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("d.document_date <= ?")
        params.append(date_to)
    where = " AND ".join(clauses)
    with _con() as con:
        total = con.execute(f"SELECT COUNT(*) FROM ap_documents d JOIN vendors v ON v.vendor_id = d.vendor_id WHERE {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT d.ap_document_id, d.vendor_id, v.canonical_entity_id, v.legal_name,
                       d.application_id, d.document_number, d.document_type, d.document_date,
                       d.document_status, d.certificate_basis, d.contract_sum_to_date_cents
                FROM ap_documents d JOIN vendors v ON v.vendor_id = d.vendor_id
                WHERE {where}
                ORDER BY d.document_date DESC, d.ap_document_id
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def list_certificate_components(ap_document_id: str, component_codes: list = None, offset: int = 0, page_size: int = 50) -> dict:
    """List accounting components for one payment application or certificate.

    Args:
        ap_document_id: Exact AP document identifier.
        component_codes: Optional list of component-code enums to include.
        offset: Zero-based result offset.
        page_size: Number of rows to return, from 1 through 100.

    Returns:
        A dictionary containing component items, offset, page_size, and total matches.
    """
    _validate_page(offset, page_size)
    component_codes = component_codes or []
    unknown = sorted(set(component_codes) - _COMPONENT_CODES)
    if unknown:
        raise ValueError(f"Unknown component_codes: {unknown}")
    clauses, params = ["ap_document_id = ?"], [ap_document_id]
    if component_codes:
        clauses.append(f"component_code IN ({_placeholders(component_codes)})")
        params.extend(component_codes)
    where = " AND ".join(clauses)
    with _con() as con:
        if con.execute("SELECT 1 FROM ap_documents WHERE ap_document_id = ?", (ap_document_id,)).fetchone() is None:
            raise ValueError(f"Unknown ap_document_id: {ap_document_id}")
        total = con.execute(f"SELECT COUNT(*) FROM ap_document_lines WHERE {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT ap_line_id, line_number, component_code, source_status, gross_amount_cents,
                       retainage_amount_cents, net_amount_cents, requested_retainage_rate_bp, component_note
                FROM ap_document_lines WHERE {where}
                ORDER BY line_number LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total}


def calculate_separate_retainage(completed_work_cents: int, completed_work_rate_bp: int, accepted_stored_material_cents: int, stored_material_rate_bp: int) -> dict:
    """Calculate separate retainage for completed work and accepted stored materials.

    Args:
        completed_work_cents: Nonnegative completed-work amount in cents.
        completed_work_rate_bp: Completed-work retainage rate in basis points, from 0 through 10000.
        accepted_stored_material_cents: Nonnegative accepted stored-material amount in cents.
        stored_material_rate_bp: Stored-material retainage rate in basis points, from 0 through 10000.

    Returns:
        Separate and total retainage amounts using half-up rounding to cents.
    """
    if completed_work_cents < 0 or accepted_stored_material_cents < 0:
        raise ValueError("amounts must be nonnegative cents")
    if not 0 <= completed_work_rate_bp <= 10000 or not 0 <= stored_material_rate_bp <= 10000:
        raise ValueError("retainage rates must be between 0 and 10000 basis points")
    completed = _retainage(completed_work_cents, completed_work_rate_bp)
    stored = _retainage(accepted_stored_material_cents, stored_material_rate_bp)
    return {"completed_work_retainage_cents": completed, "stored_material_retainage_cents": stored, "total_retainage_cents": completed + stored, "rounding": "HALF_UP_TO_CENT"}


def calculate_current_payment_due(ap_document_id: str, calculation_version: int, valid_transaction_statuses: list = ["CLEARED", "ISSUED"]) -> dict:
    """Recalculate current payment due for an explicit certificate version.

    Args:
        ap_document_id: Exact submitted or recommended AP document identifier.
        calculation_version: Positive immutable calculation version number.
        valid_transaction_statuses: Payment statuses treated as valid prior disbursements; defaults to CLEARED and ISSUED.

    Returns:
        Gross earnings, separate retainage total, valid prior payments, underlying cents, and whole-dollar payment due.
    """
    if calculation_version < 1:
        raise ValueError("calculation_version must be positive")
    statuses = valid_transaction_statuses or ["CLEARED", "ISSUED"]
    unknown = sorted(set(statuses) - _TRANSACTION_STATUSES)
    if unknown:
        raise ValueError(f"Unknown transaction statuses: {unknown}")
    if not statuses:
        raise ValueError("valid_transaction_statuses cannot be empty")
    with _con() as con:
        return _calculate_due(con, ap_document_id, calculation_version, statuses)


def calculate_balance_to_finish(ap_document_id: str, calculation_version: int) -> dict:
    """Calculate balance to finish for an explicit recommended certificate version.

    Args:
        ap_document_id: Exact AP document identifier for the recommended certificate.
        calculation_version: Positive immutable calculation version number.

    Returns:
        Contract sum, earned less retainage, and balance to finish, or a structured error when required metrics are unavailable.
    """
    if calculation_version < 1:
        raise ValueError("calculation_version must be positive")
    with _con() as con:
        metrics = _load_version(con, ap_document_id, calculation_version)
    if not metrics:
        return {"error": {"code": "VERSION_NOT_FOUND", "message": "The requested calculation version does not exist."}, "ap_document_id": ap_document_id, "calculation_version": calculation_version}
    if not all(row["is_recommended"] == 1 for row in metrics):
        return {"error": {"code": "VERSION_NOT_RECOMMENDED", "message": "Balance to finish is available only for a recommended version."}, "ap_document_id": ap_document_id, "calculation_version": calculation_version}
    by_code = {row["metric_code"]: row for row in metrics}
    missing = [code for code in ("CONTRACT_SUM_TO_DATE", "TOTAL_EARNED_LESS_RETAINAGE") if code not in by_code]
    if missing:
        return {"error": {"code": "MISSING_METRICS", "message": f"Required metrics are missing: {', '.join(missing)}"}, "ap_document_id": ap_document_id, "calculation_version": calculation_version}
    contract = int(by_code["CONTRACT_SUM_TO_DATE"]["amount_cents"])
    earned = int(by_code["TOTAL_EARNED_LESS_RETAINAGE"]["amount_cents"])
    return {"contract_sum_to_date_cents": contract, "total_earned_less_retainage_cents": earned, "balance_to_finish_including_retainage_cents": contract - earned}


def list_payment_history(vendor_id: str = None, application_id: str = None, ap_document_id: str = None, statuses: list = None, date_from: str = None, date_to: str = None, offset: int = 0, page_size: int = 50) -> dict:
    """List payment transactions and replacement chains without collapsing exceptions.

    Args:
        vendor_id: Optional exact vendor identifier.
        application_id: Optional exact payment-application identifier.
        ap_document_id: Optional exact AP document identifier.
        statuses: Optional list of transaction-status enums.
        date_from: Optional inclusive payment-date lower bound in YYYY-MM-DD format.
        date_to: Optional inclusive payment-date upper bound in YYYY-MM-DD format.
        offset: Zero-based result offset.
        page_size: Number of rows to return, from 1 through 100.

    Returns:
        A dictionary containing transaction items, pagination metadata, total matches, and the valid CLEARED/ISSUED amount.
    """
    _validate_page(offset, page_size)
    _validate_date(date_from, "date_from")
    _validate_date(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    if not any([vendor_id, application_id, ap_document_id]):
        raise ValueError("Provide at least one of vendor_id, application_id, or ap_document_id")
    statuses = statuses or []
    unknown = sorted(set(statuses) - _TRANSACTION_STATUSES)
    if unknown:
        raise ValueError(f"Unknown transaction statuses: {unknown}")
    clauses, params = [], []
    for column, value in (("d.vendor_id", vendor_id), ("d.application_id", application_id), ("p.ap_document_id", ap_document_id)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if statuses:
        clauses.append(f"p.transaction_status IN ({_placeholders(statuses)})")
        params.extend(statuses)
    if date_from:
        clauses.append("p.payment_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("p.payment_date <= ?")
        params.append(date_to)
    where = " AND ".join(clauses)
    with _con() as con:
        total, valid = con.execute(
            f"""SELECT COUNT(*), COALESCE(SUM(CASE WHEN p.transaction_status IN ('CLEARED','ISSUED') THEN p.amount_cents ELSE 0 END), 0)
                FROM payment_transactions p JOIN ap_documents d ON d.ap_document_id = p.ap_document_id WHERE {where}""",
            params,
        ).fetchone()
        rows = con.execute(
            f"""SELECT p.payment_transaction_id, p.ap_document_id, p.payment_reference, p.payment_date,
                       p.transaction_status, p.amount_cents, p.replacement_for_transaction_id, p.status_updated_at
                FROM payment_transactions p JOIN ap_documents d ON d.ap_document_id = p.ap_document_id
                WHERE {where} ORDER BY p.payment_date DESC, p.payment_transaction_id
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size": page_size, "total": total, "valid_amount_cents": valid}


def create_certificate_version(ap_document_id: str, calculation_version: int, is_recommended: bool, reviewer_id: str = None, metrics: list = None, idempotency_key: str = None) -> dict:
    """Create an immutable set of certificate calculation metrics in one transaction.

    Args:
        ap_document_id: Existing payment application or certificate document identifier.
        calculation_version: Positive version number not already used for the document.
        is_recommended: Whether the new version is the City's recommended calculation.
        reviewer_id: Required reviewer identifier when is_recommended is true.
        metrics: List of metric dictionaries containing metric_code, amount_cents, and optional rate_bp.
        idempotency_key: Unique client-generated key used to safely retry the mutation.

    Returns:
        The document, version, recommendation flag, created calculation identifiers, row count, and recorded timestamp.
    """
    if calculation_version < 1:
        raise ValueError("calculation_version must be positive")
    if is_recommended and not reviewer_id:
        raise ValueError("reviewer_id is required for a recommended version")
    if not metrics:
        raise ValueError("metrics must contain at least one calculation metric")
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    normalized = []
    seen = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("each metrics entry must be an object")
        code = metric.get("metric_code")
        amount = metric.get("amount_cents")
        rate = metric.get("rate_bp")
        if code not in _METRIC_CODES:
            raise ValueError(f"Unknown metric_code: {code}")
        if code in seen:
            raise ValueError(f"Duplicate metric_code in request: {code}")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("amount_cents must be an integer; floating-point amounts are not accepted")
        if rate is not None and (isinstance(rate, bool) or not isinstance(rate, int) or not 0 <= rate <= 10000):
            raise ValueError("rate_bp must be an integer from 0 through 10000 when supplied")
        seen.add(code)
        normalized.append({"metric_code": code, "amount_cents": amount, "rate_bp": rate})
    request = {"ap_document_id": ap_document_id, "calculation_version": calculation_version, "is_recommended": is_recommended, "reviewer_id": reviewer_id, "metrics": normalized, "idempotency_key": idempotency_key}
    with _con() as con:
        _ensure_mutation_tables(con)
        existing = _idempotent_result(con, "create_certificate_version", idempotency_key, request)
        if existing is not None:
            return existing
        document = con.execute("SELECT document_type FROM ap_documents WHERE ap_document_id = ?", (ap_document_id,)).fetchone()
        if document is None:
            raise ValueError(f"Unknown ap_document_id: {ap_document_id}")
        if document["document_type"] not in {"PAYMENT_APPLICATION", "PAYMENT_CERTIFICATE"}:
            raise ValueError("certificate versions can be created only for payment applications or payment certificates")
        if con.execute("SELECT 1 FROM certificate_calculations WHERE ap_document_id = ? AND calculation_version = ?", (ap_document_id, calculation_version)).fetchone():
            raise ValueError("The requested document/version already exists and is immutable")
        recorded_at = _now()
        ids = []
        for index, metric in enumerate(normalized, 1):
            calculation_id = f"CALC-{ap_document_id}-{calculation_version}-{index:02d}-{idempotency_key[:12]}"
            con.execute(
                """INSERT INTO certificate_calculations
                   (calculation_id, ap_document_id, calculation_version, metric_code, amount_cents, rate_bp, is_recommended, reviewer_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (calculation_id, ap_document_id, calculation_version, metric["metric_code"], metric["amount_cents"], metric["rate_bp"], int(is_recommended), reviewer_id, recorded_at),
            )
            ids.append(calculation_id)
        response = {"ap_document_id": ap_document_id, "calculation_version": calculation_version, "is_recommended": is_recommended, "calculation_ids": ids, "created_count": len(ids), "recorded_at": recorded_at}
        _store_idempotent_result(con, "create_certificate_version", idempotency_key, request, response, recorded_at)
    return response


def authorize_recommended_payment(ap_document_id: str, calculation_version: int, authorized_by: str, expected_current_payment_cents: int, idempotency_key: str) -> dict:
    """Authorize a recommended payment and settle any positive amount.

    Args:
        ap_document_id: Exact recommended payment-certificate document identifier.
        calculation_version: Positive recommended calculation version number.
        authorized_by: Identifier of the employee authorizing payment.
        expected_current_payment_cents: Exact expected CURRENT_PAYMENT_ROUNDED metric in cents.
        idempotency_key: Unique client-generated key used to safely retry authorization.

    Returns:
        The document, version, prior and new status, authorized amount, authorizer,
        authorization timestamp and settlement record when money moved.
    """
    if calculation_version < 1:
        raise ValueError("calculation_version must be positive")
    if expected_current_payment_cents < 0:
        raise ValueError("expected_current_payment_cents must be nonnegative")
    if not authorized_by or not authorized_by.strip():
        raise ValueError("authorized_by is required")
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    request = {"ap_document_id": ap_document_id, "calculation_version": calculation_version, "authorized_by": authorized_by, "expected_current_payment_cents": expected_current_payment_cents, "idempotency_key": idempotency_key}
    with _con() as con:
        _ensure_mutation_tables(con)
        existing = _idempotent_result(con, "authorize_recommended_payment", idempotency_key, request)
        if existing is not None:
            return existing
        document = _document_application(con, ap_document_id)
        if document["document_status"] != "RECOMMENDED":
            raise ValueError("Document status must be RECOMMENDED before authorization")
        metrics = _load_version(con, ap_document_id, calculation_version)
        if not metrics or not all(row["is_recommended"] == 1 for row in metrics):
            raise ValueError("The requested version does not exist or is not recommended")
        by_code = {row["metric_code"]: row for row in metrics}
        required = {"ACCEPTED_COMPLETED_WORK", "VALID_PRIOR_PAYMENTS", "CONTRACT_SUM_TO_DATE", "TOTAL_EARNED_LESS_RETAINAGE", "CURRENT_PAYMENT_ROUNDED"}
        missing = sorted(required - set(by_code))
        if missing:
            raise ValueError(f"Recommended version is missing required metrics: {missing}")
        stored_amount = int(by_code["CURRENT_PAYMENT_ROUNDED"]["amount_cents"])
        if stored_amount != expected_current_payment_cents:
            raise ValueError(f"expected_current_payment_cents does not match stored value {stored_amount}")
        calculated = _calculate_due(con, ap_document_id, calculation_version, ["CLEARED", "ISSUED"])
        if calculated["current_payment_due_cents"] != stored_amount:
            raise ValueError("Stored CURRENT_PAYMENT_ROUNDED does not reconcile to earnings, retainage, and valid prior payments")
        authorized_at = _now()
        authorization_id = f"AUTH-{ap_document_id}-{calculation_version}-{idempotency_key[:12]}"
        new_status = "PAID" if stored_amount > 0 else "AUTHORIZED_QUEUE"
        con.execute("UPDATE ap_documents SET document_status = ? WHERE ap_document_id = ?", (new_status, ap_document_id))
        con.execute(
            "INSERT INTO payment_authorizations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (authorization_id, ap_document_id, calculation_version, authorized_by, stored_amount, "RECOMMENDED", new_status, idempotency_key, authorized_at),
        )
        settlement = None
        if stored_amount > 0:
            vendor_id = con.execute(
                "SELECT vendor_id FROM ap_documents WHERE ap_document_id = ?", (ap_document_id,)
            ).fetchone()[0]
            settlement = {
                "settlement_id": f"SETTLE-{ap_document_id}-{calculation_version}-{idempotency_key[:12]}",
                "authorization_id": authorization_id,
                "ap_document_id": ap_document_id,
                "vendor_id": vendor_id,
                "amount_cents": stored_amount,
                "currency": "USD",
                "settlement_status": "SETTLED",
                "settled_at": authorized_at,
            }
            con.execute(
                "INSERT INTO cash_settlements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(settlement[k] for k in (
                    "settlement_id", "authorization_id", "ap_document_id", "vendor_id",
                    "amount_cents", "currency", "settlement_status", "settled_at"
                )),
            )
        response = {"ap_document_id": ap_document_id, "calculation_version": calculation_version, "previous_status": "RECOMMENDED", "document_status": new_status, "authorized_amount_cents": stored_amount, "authorized_by": authorized_by, "authorized_at": authorized_at, "settlement": settlement}
        _store_idempotent_result(con, "authorize_recommended_payment", idempotency_key, request, response, authorized_at)
    return response


def compare_submitted_and_recommended(application_id: str, submitted_version: int, recommended_version: int) -> dict:
    """Compare explicitly selected submitted and recommended payment calculations.

    Args:
        application_id: Exact application identifier shared by the submitted and recommended documents.
        submitted_version: Positive calculation version for the contractor-submitted document.
        recommended_version: Positive calculation version for the City-recommended document.

    Returns:
        Submitted and recommended whole-dollar payments, reduction, and both source document identifiers.
    """
    if submitted_version < 1 or recommended_version < 1:
        raise ValueError("submitted_version and recommended_version must be positive")
    with _con() as con:
        submitted = con.execute(
            """SELECT DISTINCT d.ap_document_id FROM ap_documents d
               JOIN certificate_calculations c ON c.ap_document_id = d.ap_document_id
               WHERE d.application_id = ? AND d.certificate_basis = 'CONTRACTOR_SUBMITTED'
                 AND c.calculation_version = ? AND c.is_recommended = 0""",
            (application_id, submitted_version),
        ).fetchall()
        recommended = con.execute(
            """SELECT DISTINCT d.ap_document_id FROM ap_documents d
               JOIN certificate_calculations c ON c.ap_document_id = d.ap_document_id
               WHERE d.application_id = ? AND d.certificate_basis = 'CITY_RECOMMENDED'
                 AND c.calculation_version = ? AND c.is_recommended = 1""",
            (application_id, recommended_version),
        ).fetchall()
        if len(submitted) != 1 or len(recommended) != 1:
            raise ValueError("Application and version filters must identify exactly one submitted and one recommended document")
        submitted_id = submitted[0]["ap_document_id"]
        recommended_id = recommended[0]["ap_document_id"]
        submitted_due = _calculate_due(con, submitted_id, submitted_version, ["CLEARED", "ISSUED"])
        recommended_due = _calculate_due(con, recommended_id, recommended_version, ["CLEARED", "ISSUED"])
    submitted_dollars = submitted_due["current_payment_due_whole_dollars"]
    recommended_dollars = recommended_due["current_payment_due_whole_dollars"]
    return {"application_id": application_id, "submitted_current_payment_whole_dollars": submitted_dollars, "recommended_current_payment_whole_dollars": recommended_dollars, "reduction_whole_dollars": submitted_dollars - recommended_dollars, "submitted_document_id": submitted_id, "recommended_document_id": recommended_id}

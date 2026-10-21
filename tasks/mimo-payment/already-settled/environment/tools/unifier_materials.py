"""Tools for reviewing stored-material evidence in the Unifier register."""

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path


def _con():
    """Open a row-oriented connection to the stored-materials database."""
    database = Path(__file__).resolve().parent.parent / "system" / "unifier_materials" / "state.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _require_nonblank(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be blank")
    return cleaned


def _validate_paging(page: int, page_size: int, maximum: int) -> None:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= page_size <= maximum:
        raise ValueError(f"page_size must be between 1 and {maximum}")


def _claim(connection: sqlite3.Connection, material_claim_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM material_claims WHERE material_claim_id = ?", (material_claim_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown material_claim_id: {material_claim_id}")
    return row


def _parse_as_of(as_of_date: str | None) -> str:
    if as_of_date is None:
        return date.today().isoformat()
    try:
        return date.fromisoformat(as_of_date).isoformat()
    except ValueError as exc:
        raise ValueError("as_of_date must use YYYY-MM-DD format") from exc


def _eligible_exemption(requirement: sqlite3.Row, claim: sqlite3.Row, rule: str | None) -> bool:
    expected = requirement["exemption_rule_code"]
    if not expected or rule != expected:
        return False
    if expected == "LOW_VALUE_CONSUMABLE_INCORPORATED":
        return bool(claim["low_value_consumable_flag"] and claim["incorporated_into_completed_work_flag"])
    if expected == "NO_EQUIPMENT_PREPAYMENT":
        return claim["material_category_code"] != "EQUIPMENT_PREPAYMENT"
    if expected == "MATERIAL_ONLY_CHARGE":
        return True
    return False


def _evaluate(connection: sqlite3.Connection, material_claim_id: str, as_of_date: str | None = None) -> dict:
    claim = _claim(connection, material_claim_id)
    effective_date = _parse_as_of(as_of_date)
    requirements = connection.execute(
        """
        SELECT er.*, crr.evidence_document_id, crr.review_result,
               crr.exemption_rule_code AS recorded_exemption_rule
        FROM evidence_requirements er
        LEFT JOIN claim_requirement_reviews crr
          ON crr.requirement_id = er.requirement_id
         AND crr.material_claim_id = ?
        WHERE er.active_flag = 1
          AND er.applies_to_stored_material_flag = 1
          AND er.default_required_flag = 1
          AND er.effective_from <= ?
          AND (er.effective_to IS NULL OR er.effective_to >= ?)
        ORDER BY er.requirement_code
        """,
        (material_claim_id, effective_date, effective_date),
    ).fetchall()
    requirement_rows = []
    counts = {"PASS": 0, "EXEMPT": 0, "FAIL": 0, "MISSING": 0}
    for requirement in requirements:
        result = requirement["review_result"] or "MISSING"
        exemption_rule = requirement["recorded_exemption_rule"]
        if result == "EXEMPT" and not _eligible_exemption(requirement, claim, exemption_rule):
            result = "FAIL"
        counts[result] += 1
        requirement_rows.append({
            "requirement_id": requirement["requirement_id"],
            "requirement_code": requirement["requirement_code"],
            "review_result": result,
            "exemption_rule_code": exemption_rule,
            "evidence_document_id": requirement["evidence_document_id"],
        })
    locations = connection.execute(
        """
        SELECT custody_location_id, owner_control_flag, segregated_flag,
               insured_flag, title_control_flag
        FROM custody_locations
        WHERE material_claim_id = ?
        ORDER BY custody_location_id
        """,
        (material_claim_id,),
    ).fetchall()
    location_rows = [dict(location) for location in locations]
    custody_passed = any(
        location["owner_control_flag"] == 1
        and location["segregated_flag"] == 1
        and location["insured_flag"] == 1
        and location["title_control_flag"] == 1
        for location in locations
    )
    eligible = counts["FAIL"] == 0 and counts["MISSING"] == 0 and custody_passed
    return {
        "material_claim_id": material_claim_id,
        "claimed_amount_cents": claim["claimed_amount_cents"],
        "required_count": len(requirements),
        "passed_count": counts["PASS"],
        "exempt_count": counts["EXEMPT"],
        "failed_count": counts["FAIL"],
        "missing_count": counts["MISSING"],
        "custody_passed": custody_passed,
        "certification_eligible": eligible,
        "requirements": requirement_rows,
        "custody_locations": location_rows,
    }


def _new_review_id(connection: sqlite3.Connection, reviewed_at: str) -> str:
    year = reviewed_at[:4]
    prefix = f"REV-{year}-"
    numbers = []
    for row in connection.execute("SELECT review_id FROM claim_requirement_reviews WHERE review_id LIKE ?", (prefix + "%",)):
        tail = row["review_id"].removeprefix(prefix)
        if tail.isdigit():
            numbers.append(int(tail))
    return f"{prefix}{max(numbers, default=0) + 1:05d}"


def _ensure_hold_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS claim_hold_events (
            hold_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_claim_id TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            note TEXT NOT NULL,
            previous_certification_status TEXT NOT NULL,
            certification_status TEXT NOT NULL,
            held_at TEXT NOT NULL,
            FOREIGN KEY (material_claim_id) REFERENCES material_claims(material_claim_id)
        )
        """
    )


def search_material_claims(
    application_id: str | None = None,
    contractor_id: str | None = None,
    canonical_sov_item_id: str | None = None,
    material_category_code: str | None = None,
    claim_status: str | None = None,
    certification_status: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Search material claims using bounded exact-match and amount filters.

    Args:
        application_id: Exact pay-application identifier.
        contractor_id: Exact canonical contractor identifier.
        canonical_sov_item_id: Exact schedule-of-values item identifier.
        material_category_code: Exact stored-material category code.
        claim_status: Contractor workflow status.
        certification_status: Evidence certification status.
        min_amount_cents: Inclusive minimum claimed amount in cents.
        max_amount_cents: Inclusive maximum claimed amount in cents.
        page: One-based result page.
        page_size: Rows per page, from 1 through 100.

    Returns:
        A dictionary containing items, page, page_size, and total.
    """
    _validate_paging(page, page_size, 100)
    filters = [application_id, contractor_id, canonical_sov_item_id, material_category_code,
               claim_status, certification_status, min_amount_cents, max_amount_cents]
    if all(value is None for value in filters):
        raise ValueError("Provide at least one claim filter; unfiltered exports are not permitted")
    if claim_status is not None and claim_status not in {"draft", "submitted", "accepted", "rejected", "withdrawn", "archived"}:
        raise ValueError("claim_status is not a supported workflow value")
    if certification_status is not None and certification_status not in {"pending_review", "eligible", "unsupported", "excluded", "not_applicable"}:
        raise ValueError("certification_status is not a supported value")
    if min_amount_cents is not None and min_amount_cents < 0:
        raise ValueError("min_amount_cents must be nonnegative")
    if max_amount_cents is not None and max_amount_cents < 0:
        raise ValueError("max_amount_cents must be nonnegative")
    if min_amount_cents is not None and max_amount_cents is not None and min_amount_cents > max_amount_cents:
        raise ValueError("min_amount_cents cannot exceed max_amount_cents")
    clauses, params = [], []
    for column, value in [
        ("application_id", application_id), ("contractor_id", contractor_id),
        ("canonical_sov_item_id", canonical_sov_item_id), ("material_category_code", material_category_code),
        ("claim_status", claim_status), ("certification_status", certification_status),
    ]:
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if min_amount_cents is not None:
        clauses.append("claimed_amount_cents >= ?")
        params.append(min_amount_cents)
    if max_amount_cents is not None:
        clauses.append("claimed_amount_cents <= ?")
        params.append(max_amount_cents)
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM material_claims WHERE {where}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT material_claim_id, application_id, contractor_id, contractor_name,
                   canonical_sov_item_id, sov_item_description, claim_number, claim_date,
                   claimed_amount_cents, claim_status, certification_status
            FROM material_claims WHERE {where}
            ORDER BY claim_date DESC, claim_number
            LIMIT ? OFFSET ?
            """,
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "page": page, "page_size": page_size, "total": total}


def list_claim_evidence(
    material_claim_id: str,
    document_type: str | None = None,
    verification_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List directly linked evidence documents for one material claim.

    Args:
        material_claim_id: Material claim whose foreign-key evidence is requested.
        document_type: Optional exact document-type filter.
        verification_status: Optional verification status filter.
        page: One-based result page.
        page_size: Rows per page, from 1 through 100.

    Returns:
        A dictionary containing material_claim_id, items, page, page_size, and total.
    """
    material_claim_id = _require_nonblank(material_claim_id, "material_claim_id")
    _validate_paging(page, page_size, 100)
    if verification_status is not None and verification_status not in {"unreviewed", "verified", "rejected", "expired", "superseded"}:
        raise ValueError("verification_status is not supported")
    clauses, params = ["material_claim_id = ?"], [material_claim_id]
    if document_type is not None:
        clauses.append("document_type = ?")
        params.append(document_type)
    if verification_status is not None:
        clauses.append("verification_status = ?")
        params.append(verification_status)
    where = " AND ".join(clauses)
    with _con() as connection:
        _claim(connection, material_claim_id)
        total = connection.execute(f"SELECT COUNT(*) FROM evidence_documents WHERE {where}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT evidence_document_id, document_type, document_number, document_date,
                   document_amount_cents, issuer_name, file_name, verification_status,
                   received_at, verification_note
            FROM evidence_documents WHERE {where}
            ORDER BY document_date DESC, evidence_document_id
            LIMIT ? OFFSET ?
            """,
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    return {"material_claim_id": material_claim_id, "items": [dict(row) for row in rows], "page": page, "page_size": page_size, "total": total}


def evaluate_support_completeness(material_claim_id: str, as_of_date: str | None = None) -> dict:
    """Evaluate required evidence and custody controls for one claim.

    Args:
        material_claim_id: Material claim to evaluate.
        as_of_date: Optional YYYY-MM-DD date used for requirement effectiveness.

    Returns:
        A detailed dictionary of requirement counts, custody controls, and eligibility.
    """
    material_claim_id = _require_nonblank(material_claim_id, "material_claim_id")
    with _con() as connection:
        return _evaluate(connection, material_claim_id, as_of_date)


def calculate_unsupported_claim_amount(
    application_id: str,
    contractor_id: str | None = None,
    canonical_sov_item_id: str | None = None,
) -> dict:
    """Calculate unsupported stored-material claims for a pay application.

    Args:
        application_id: Exact pay-application identifier to aggregate.
        contractor_id: Optional exact contractor identifier.
        canonical_sov_item_id: Optional exact schedule-of-values item identifier.

    Returns:
        A dictionary with unsupported count, cents, claim IDs, and calculation time.
    """
    application_id = _require_nonblank(application_id, "application_id")
    clauses, params = ["application_id = ?"], [application_id]
    if contractor_id is not None:
        clauses.append("contractor_id = ?")
        params.append(contractor_id)
    if canonical_sov_item_id is not None:
        clauses.append("canonical_sov_item_id = ?")
        params.append(canonical_sov_item_id)
    with _con() as connection:
        claims = connection.execute(
            f"SELECT material_claim_id, claimed_amount_cents FROM material_claims WHERE {' AND '.join(clauses)} ORDER BY material_claim_id",
            params,
        ).fetchall()
        unsupported = [claim for claim in claims if not _evaluate(connection, claim["material_claim_id"])["certification_eligible"]]
    return {
        "application_id": application_id,
        "unsupported_claim_count": len(unsupported),
        "unsupported_claimed_amount_cents": sum(claim["claimed_amount_cents"] for claim in unsupported),
        "claim_ids": [claim["material_claim_id"] for claim in unsupported],
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_custody_controls(material_claim_id: str) -> dict:
    """Return each custody location without combining controls across sites.

    Args:
        material_claim_id: Material claim whose custody controls are requested.

    Returns:
        A dictionary containing all locations and a fully controlled location indicator.
    """
    material_claim_id = _require_nonblank(material_claim_id, "material_claim_id")
    with _con() as connection:
        _claim(connection, material_claim_id)
        rows = connection.execute(
            """
            SELECT custody_location_id, location_name, address_line1, city, state_code,
                   postal_code, custody_type, owner_control_flag, segregated_flag,
                   insured_flag, title_control_flag, verified_date, verified_by_id, control_note
            FROM custody_locations WHERE material_claim_id = ?
            ORDER BY custody_location_id
            """,
            (material_claim_id,),
        ).fetchall()
    locations = [dict(row) for row in rows]
    fully_controlled = any(
        row["owner_control_flag"] == 1 and row["segregated_flag"] == 1
        and row["insured_flag"] == 1 and row["title_control_flag"] == 1
        for row in rows
    )
    return {"material_claim_id": material_claim_id, "locations": locations, "has_fully_controlled_location": fully_controlled}


def record_evidence_review(
    material_claim_id: str,
    requirement_id: str,
    evidence_document_id: str | None = None,
    *,
    review_result: str,
    exemption_rule_code: str | None = None,
    reviewer_id: str,
    reviewer_name: str,
    review_note: str,
    expected_existing_review_id: str | None = None,
) -> dict:
    """Create or concurrency-safe update a claim requirement review.

    Args:
        material_claim_id: Claim receiving the review.
        requirement_id: Evidence requirement being adjudicated.
        evidence_document_id: Optional evidence document linked to the same claim.
        review_result: PASS, FAIL, MISSING, or EXEMPT.
        exemption_rule_code: Required matching rule when review_result is EXEMPT.
        reviewer_id: Identifier of the reviewing employee.
        reviewer_name: Display name of the reviewing employee.
        review_note: Analyst rationale persisted with the review.
        expected_existing_review_id: Existing review ID required for an update.

    Returns:
        A dictionary containing the persisted review and whether it was created.
    """
    material_claim_id = _require_nonblank(material_claim_id, "material_claim_id")
    requirement_id = _require_nonblank(requirement_id, "requirement_id")
    reviewer_id = _require_nonblank(reviewer_id, "reviewer_id")
    reviewer_name = _require_nonblank(reviewer_name, "reviewer_name")
    review_note = _require_nonblank(review_note, "review_note")
    if review_result not in {"PASS", "FAIL", "MISSING", "EXEMPT"}:
        raise ValueError("review_result must be PASS, FAIL, MISSING, or EXEMPT")
    if review_result == "MISSING" and evidence_document_id is not None:
        raise ValueError("MISSING reviews cannot reference an evidence document")
    if review_result != "EXEMPT" and exemption_rule_code is not None:
        raise ValueError("exemption_rule_code is only valid for EXEMPT reviews")
    now = datetime.now(timezone.utc).isoformat()
    with _con() as connection:
        claim = _claim(connection, material_claim_id)
        requirement = connection.execute("SELECT * FROM evidence_requirements WHERE requirement_id = ?", (requirement_id,)).fetchone()
        if requirement is None:
            raise ValueError(f"Unknown requirement_id: {requirement_id}")
        if evidence_document_id is not None:
            evidence = connection.execute(
                "SELECT material_claim_id FROM evidence_documents WHERE evidence_document_id = ?", (evidence_document_id,)
            ).fetchone()
            if evidence is None:
                raise ValueError(f"Unknown evidence_document_id: {evidence_document_id}")
            if evidence["material_claim_id"] != material_claim_id:
                raise ValueError("evidence_document_id must belong to material_claim_id")
        if review_result == "EXEMPT":
            if not _eligible_exemption(requirement, claim, exemption_rule_code):
                raise ValueError("The exemption rule does not match the requirement or claim eligibility")
            exemption_applied = 1
        else:
            exemption_applied = 0
            exemption_rule_code = None
        existing = connection.execute(
            "SELECT review_id FROM claim_requirement_reviews WHERE material_claim_id = ? AND requirement_id = ?",
            (material_claim_id, requirement_id),
        ).fetchone()
        if existing is not None and expected_existing_review_id is None:
            return {"error": {"code": "CONFLICT", "message": "A review already exists; provide expected_existing_review_id", "existing_review_id": existing["review_id"]}}
        if existing is None and expected_existing_review_id is not None:
            return {"error": {"code": "CONFLICT", "message": "No existing review matches the expected identifier", "expected_existing_review_id": expected_existing_review_id}}
        if existing is not None and existing["review_id"] != expected_existing_review_id:
            return {"error": {"code": "CONFLICT", "message": "The review changed after it was read", "existing_review_id": existing["review_id"]}}
        if existing is None:
            review_id = _new_review_id(connection, now)
            connection.execute(
                """INSERT INTO claim_requirement_reviews
                   (review_id, material_claim_id, requirement_id, evidence_document_id, review_result,
                    exemption_applied_flag, exemption_rule_code, reviewer_id, reviewer_name, reviewed_at, review_note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (review_id, material_claim_id, requirement_id, evidence_document_id, review_result,
                 exemption_applied, exemption_rule_code, reviewer_id, reviewer_name, now, review_note),
            )
            created = True
        else:
            review_id = existing["review_id"]
            connection.execute(
                """UPDATE claim_requirement_reviews
                   SET evidence_document_id = ?, review_result = ?, exemption_applied_flag = ?,
                       exemption_rule_code = ?, reviewer_id = ?, reviewer_name = ?, reviewed_at = ?, review_note = ?
                   WHERE review_id = ?""",
                (evidence_document_id, review_result, exemption_applied, exemption_rule_code,
                 reviewer_id, reviewer_name, now, review_note, review_id),
            )
            created = False
        row = connection.execute("SELECT * FROM claim_requirement_reviews WHERE review_id = ?", (review_id,)).fetchone()
    return {"review": dict(row), "created": created}


def place_claim_on_hold(material_claim_id: str, reason_code: str, reviewer_id: str, note: str) -> dict:
    """Place an unsupported claim on evidence hold without changing contractor status.

    Args:
        material_claim_id: Claim to reassess and hold.
        reason_code: UNSUPPORTED_EVIDENCE, CUSTODY_CONTROL_FAILURE, or TITLE_NOT_ESTABLISHED.
        reviewer_id: Employee identifier responsible for the hold.
        note: Hold rationale returned as part of the audit response.

    Returns:
        A dictionary containing prior and current certification status plus hold details.
    """
    material_claim_id = _require_nonblank(material_claim_id, "material_claim_id")
    reviewer_id = _require_nonblank(reviewer_id, "reviewer_id")
    note = _require_nonblank(note, "note")
    if reason_code not in {"UNSUPPORTED_EVIDENCE", "CUSTODY_CONTROL_FAILURE", "TITLE_NOT_ESTABLISHED"}:
        raise ValueError("reason_code is not supported")
    held_at = datetime.now(timezone.utc).isoformat()
    with _con() as connection:
        _ensure_hold_table(connection)
        claim = _claim(connection, material_claim_id)
        assessment = _evaluate(connection, material_claim_id)
        title_failure = any(
            item["requirement_code"] in {"TITLE_OWNERSHIP", "BILL_OF_SALE"}
            and item["review_result"] not in {"PASS", "EXEMPT"}
            for item in assessment["requirements"]
        ) or not any(location["title_control_flag"] for location in assessment["custody_locations"])
        if reason_code == "CUSTODY_CONTROL_FAILURE" and assessment["custody_passed"]:
            raise ValueError("The claim has a fully controlled custody location")
        if reason_code == "TITLE_NOT_ESTABLISHED" and not title_failure:
            raise ValueError("The current evidence establishes title control")
        if reason_code == "UNSUPPORTED_EVIDENCE" and assessment["failed_count"] == 0 and assessment["missing_count"] == 0:
            raise ValueError("The claim has no failed or missing evidence requirement")
        previous = claim["certification_status"]
        if previous != "unsupported":
            connection.execute(
                "UPDATE material_claims SET certification_status = 'unsupported' WHERE material_claim_id = ?",
                (material_claim_id,),
            )
        existing_hold = connection.execute(
            """SELECT hold_event_id FROM claim_hold_events
               WHERE material_claim_id = ? AND reason_code = ? AND reviewer_id = ? AND note = ?
                 AND certification_status = 'unsupported'
               ORDER BY hold_event_id DESC LIMIT 1""",
            (material_claim_id, reason_code, reviewer_id, note),
        ).fetchone()
        if existing_hold is None:
            connection.execute(
                """INSERT INTO claim_hold_events
                   (material_claim_id, reason_code, reviewer_id, note,
                    previous_certification_status, certification_status, held_at)
                   VALUES (?, ?, ?, ?, ?, 'unsupported', ?)""",
                (material_claim_id, reason_code, reviewer_id, note, previous, held_at),
            )
    return {
        "material_claim_id": material_claim_id,
        "claim_status": claim["claim_status"],
        "previous_certification_status": previous,
        "certification_status": "unsupported",
        "reason_code": reason_code,
        "held_by": reviewer_id,
        "held_at": held_at,
        "note": note,
    }


def build_material_support_log(
    application_id: str,
    contractor_id: str | None = None,
    include_eligible: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Build a paginated claim-level stored-material support log.

    Args:
        application_id: Exact pay-application identifier.
        contractor_id: Optional exact contractor identifier.
        include_eligible: Include claims that pass evidence and custody controls.
        page: One-based result page.
        page_size: Rows per page, from 1 through 100.

    Returns:
        A dictionary containing recalculated rows, financial totals, and pagination.
    """
    application_id = _require_nonblank(application_id, "application_id")
    _validate_paging(page, page_size, 100)
    clauses, params = ["application_id = ?"], [application_id]
    if contractor_id is not None:
        clauses.append("contractor_id = ?")
        params.append(contractor_id)
    with _con() as connection:
        claims = connection.execute(
            f"SELECT * FROM material_claims WHERE {' AND '.join(clauses)} ORDER BY claim_number, material_claim_id", params
        ).fetchall()
        calculated = []
        for claim in claims:
            assessment = _evaluate(connection, claim["material_claim_id"])
            eligible = assessment["certification_eligible"]
            if not include_eligible and eligible:
                continue
            calculated.append({
                "material_claim_id": claim["material_claim_id"],
                "claim_number": claim["claim_number"],
                "contractor_id": claim["contractor_id"],
                "canonical_sov_item_id": claim["canonical_sov_item_id"],
                "sov_item_description": claim["sov_item_description"],
                "claimed_amount_cents": claim["claimed_amount_cents"],
                "claim_status": claim["claim_status"],
                "required_count": assessment["required_count"],
                "passed_count": assessment["passed_count"],
                "exempt_count": assessment["exempt_count"],
                "failed_count": assessment["failed_count"],
                "missing_count": assessment["missing_count"],
                "custody_passed": assessment["custody_passed"],
                "certification_status": "eligible" if eligible else "unsupported",
                "recommended_exclusion_cents": 0 if eligible else claim["claimed_amount_cents"],
            })
    eligible_amount = sum(row["claimed_amount_cents"] for row in calculated if row["certification_status"] == "eligible")
    unsupported_amount = sum(row["claimed_amount_cents"] for row in calculated if row["certification_status"] == "unsupported")
    start = (page - 1) * page_size
    return {
        "application_id": application_id,
        "rows": calculated[start:start + page_size],
        "totals": {
            "claimed_amount_cents": sum(row["claimed_amount_cents"] for row in calculated),
            "eligible_amount_cents": eligible_amount,
            "unsupported_amount_cents": unsupported_amount,
            "recommended_exclusion_cents": unsupported_amount,
        },
        "page": page,
        "page_size": page_size,
        "total_rows": len(calculated),
    }

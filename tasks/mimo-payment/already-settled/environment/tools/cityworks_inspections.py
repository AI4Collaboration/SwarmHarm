"""MCP-style tools for Cityworks construction inspection and payment review data."""

import sqlite3
from datetime import date
from pathlib import Path


def _con():
    connection = sqlite3.connect(
        Path(__file__).resolve().parent.parent / "system" / "cityworks_inspections" / "state.db"
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_date(value: str, parameter: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{parameter} must use YYYY-MM-DD format.") from exc
    return value


def _pagination(page: int, page_size: int, total_count: int) -> dict:
    if page < 1:
        raise ValueError("page must be at least 1.")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100.")
    return {
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


def _new_identifier(connection: sqlite3.Connection, table: str, column: str, prefix: str, year: int) -> str:
    stem = f"{prefix}-{year % 100:02d}-"
    values = connection.execute(
        f'SELECT "{column}" FROM "{table}" WHERE "{column}" LIKE ?', (stem + "%",)
    ).fetchall()
    suffixes = []
    for row in values:
        try:
            suffixes.append(int(row[0].rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{stem}{max(suffixes, default=0) + 1:04d}"


def search_inspection_work_orders(
    procurement_id: str = None,
    field_project_id: str = None,
    inspection_date_from: str = None,
    inspection_date_to: str = None,
    assigned_inspector_id: str = None,
    work_order_status: str = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Search inspection work orders using project, date, inspector, or status filters.

    Args:
        procurement_id: Optional procurement identifier assigned to the inspected contract.
        field_project_id: Optional Cityworks field project identifier.
        inspection_date_from: Optional inclusive starting inspection date in YYYY-MM-DD format.
        inspection_date_to: Optional inclusive ending inspection date in YYYY-MM-DD format.
        assigned_inspector_id: Optional personnel identifier for the assigned inspector.
        work_order_status: Optional status: OPEN, CLOSED, FINALIZED, or CANCELLED.
        page: One-based result page number.
        page_size: Number of work orders per page, from 1 through 100.

    Returns:
        A dictionary containing work_orders and pagination metadata.
    """
    if not any([procurement_id, field_project_id, inspection_date_from, inspection_date_to, assigned_inspector_id, work_order_status]):
        raise ValueError("Provide at least one work-order filter.")
    if work_order_status and work_order_status not in {"OPEN", "CLOSED", "FINALIZED", "CANCELLED"}:
        raise ValueError("work_order_status must be OPEN, CLOSED, FINALIZED, or CANCELLED.")
    if inspection_date_from:
        _validate_date(inspection_date_from, "inspection_date_from")
    if inspection_date_to:
        _validate_date(inspection_date_to, "inspection_date_to")
    if inspection_date_from and inspection_date_to and inspection_date_from > inspection_date_to:
        raise ValueError("inspection_date_from cannot be later than inspection_date_to.")
    pagination = _pagination(page, page_size, 0)
    clauses, parameters = [], []
    for column, value in [
        ("procurement_id", procurement_id), ("field_project_id", field_project_id),
        ("assigned_inspector_id", assigned_inspector_id), ("work_order_status", work_order_status),
    ]:
        if value:
            clauses.append(f"w.{column} = ?")
            parameters.append(value)
    if inspection_date_from:
        clauses.append("w.inspection_date >= ?")
        parameters.append(inspection_date_from)
    if inspection_date_to:
        clauses.append("w.inspection_date <= ?")
        parameters.append(inspection_date_to)
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM inspection_work_orders w WHERE {where}", parameters).fetchone()[0]
        rows = connection.execute(
            f"""SELECT w.work_order_id, w.procurement_id, w.field_project_id, w.inspection_date,
                       w.work_order_status, w.assigned_inspector_id, w.assigned_project_manager_id
                FROM inspection_work_orders w WHERE {where}
                ORDER BY w.inspection_date DESC, w.work_order_id DESC LIMIT ? OFFSET ?""",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    pagination.update(_pagination(page, page_size, total))
    return {"work_orders": [dict(row) for row in rows], "pagination": pagination}


def list_line_item_observations(
    canonical_sov_item_id: str,
    procurement_id: str = None,
    payment_application_id: str = None,
    observation_date_from: str = None,
    observation_date_to: str = None,
    acceptance_status: str = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List field observations for one canonical schedule-of-values line item.

    Args:
        canonical_sov_item_id: Required canonical schedule-of-values item identifier.
        procurement_id: Optional procurement identifier used to narrow joined work orders.
        payment_application_id: Optional contractor payment application identifier.
        observation_date_from: Optional inclusive production date in YYYY-MM-DD format.
        observation_date_to: Optional inclusive production date in YYYY-MM-DD format.
        acceptance_status: Optional status: ACCEPTED, CONDITIONAL, REJECTED, UNSUPPORTED, or PENDING_REVIEW.
        page: One-based result page number.
        page_size: Number of observations per page, from 1 through 100.

    Returns:
        A dictionary containing observations and pagination metadata.
    """
    if not canonical_sov_item_id:
        raise ValueError("canonical_sov_item_id is required.")
    allowed = {"ACCEPTED", "CONDITIONAL", "REJECTED", "UNSUPPORTED", "PENDING_REVIEW"}
    if acceptance_status and acceptance_status not in allowed:
        raise ValueError("acceptance_status is not recognized.")
    if observation_date_from:
        _validate_date(observation_date_from, "observation_date_from")
    if observation_date_to:
        _validate_date(observation_date_to, "observation_date_to")
    if observation_date_from and observation_date_to and observation_date_from > observation_date_to:
        raise ValueError("observation_date_from cannot be later than observation_date_to.")
    _pagination(page, page_size, 0)
    clauses = ["o.canonical_sov_item_id = ?"]
    parameters = [canonical_sov_item_id]
    if procurement_id:
        clauses.append("w.procurement_id = ?")
        parameters.append(procurement_id)
    if payment_application_id:
        clauses.append("o.payment_application_id = ?")
        parameters.append(payment_application_id)
    if observation_date_from:
        clauses.append("o.production_date >= ?")
        parameters.append(observation_date_from)
    if observation_date_to:
        clauses.append("o.production_date <= ?")
        parameters.append(observation_date_to)
    if acceptance_status:
        clauses.append("o.acceptance_status = ?")
        parameters.append(acceptance_status)
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM inspection_observations o JOIN inspection_work_orders w ON w.work_order_id=o.work_order_id WHERE {where}",
            parameters,
        ).fetchone()[0]
        rows = connection.execute(
            f"""SELECT o.observation_id, o.work_order_id, o.canonical_sov_item_id, o.sov_item_description,
                       o.production_date, o.observed_quantity_milliunits, o.observed_completed_value_cents,
                       o.stored_material_value_cents, o.acceptance_status, o.payment_application_id
                FROM inspection_observations o JOIN inspection_work_orders w ON w.work_order_id=o.work_order_id
                WHERE {where} ORDER BY o.production_date, o.observation_id LIMIT ? OFFSET ?""",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    return {"observations": [dict(row) for row in rows], "pagination": _pagination(page, page_size, total)}


def list_open_deficiencies(
    procurement_id: str = None,
    payment_application_id: str = None,
    observation_id: str = None,
    deficiency_code: str = None,
    as_of_date: str = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List payment deficiencies that remained open on a specified date.

    Args:
        procurement_id: Optional procurement identifier for joined inspection work orders.
        payment_application_id: Optional payment application identifier for joined observations.
        observation_id: Optional inspection observation identifier.
        deficiency_code: Optional deficiency classification code.
        as_of_date: Review date in YYYY-MM-DD format; defaults to the current date.
        page: One-based result page number.
        page_size: Number of deficiencies per page, from 1 through 100.

    Returns:
        A dictionary containing open deficiencies and pagination metadata.
    """
    if not any([procurement_id, payment_application_id, observation_id, deficiency_code]):
        raise ValueError("Provide at least one deficiency filter.")
    as_of_date = as_of_date or date.today().isoformat()
    _validate_date(as_of_date, "as_of_date")
    _pagination(page, page_size, 0)
    clauses = ["f.opened_date <= ?", "(f.resolved_date IS NULL OR f.resolved_date > ?)", "f.case_status IN ('OPEN','UNDER_REVIEW')"]
    parameters = [as_of_date, as_of_date]
    for expression, value in [
        ("w.procurement_id = ?", procurement_id), ("o.payment_application_id = ?", payment_application_id),
        ("f.observation_id = ?", observation_id), ("f.deficiency_code = ?", deficiency_code),
    ]:
        if value:
            clauses.append(expression)
            parameters.append(value)
    where = " AND ".join(clauses)
    base = "FROM deficiency_cases f JOIN inspection_observations o ON o.observation_id=f.observation_id JOIN inspection_work_orders w ON w.work_order_id=f.work_order_id"
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) {base} WHERE {where}", parameters).fetchone()[0]
        rows = connection.execute(
            f"""SELECT f.deficiency_id, f.observation_id, f.work_order_id, f.deficiency_code, f.case_status,
                       f.opened_date, f.resolved_date, f.payment_hold_cents,
                       (SELECT d.decision_code FROM acceptance_decisions d
                        WHERE d.observation_id=f.observation_id AND (d.deficiency_id=f.deficiency_id OR d.deficiency_id IS NULL)
                        ORDER BY d.decision_date DESC, d.decision_id DESC LIMIT 1) AS latest_decision_code
                {base} WHERE {where} ORDER BY f.opened_date, f.deficiency_id LIMIT ? OFFSET ?""",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    return {"deficiencies": [dict(row) for row in rows], "pagination": _pagination(page, page_size, total)}


def calculate_accepted_work_value(
    procurement_id: str,
    payment_application_id: str,
    decision_cutoff_date: str,
    include_conditional: bool = False,
) -> dict:
    """Calculate accepted completed-work value through a decision cutoff date.

    Args:
        procurement_id: Procurement identifier whose closed or finalized work is included.
        payment_application_id: Payment application identifier assigned to observations.
        decision_cutoff_date: Inclusive decision cutoff date in YYYY-MM-DD format.
        include_conditional: Include conditional acceptances when true; otherwise include only accepted decisions.

    Returns:
        A dictionary with accepted value, observation count, and exclusion counts.
    """
    if not procurement_id or not payment_application_id:
        raise ValueError("procurement_id and payment_application_id are required.")
    _validate_date(decision_cutoff_date, "decision_cutoff_date")
    decision_codes = ("ACCEPTED", "CONDITIONAL_ACCEPTANCE") if include_conditional else ("ACCEPTED",)
    placeholders = ",".join("?" for _ in decision_codes)
    common = """FROM inspection_observations o JOIN inspection_work_orders w ON w.work_order_id=o.work_order_id
                WHERE w.procurement_id=? AND o.payment_application_id=? AND w.work_order_status IN ('CLOSED','FINALIZED')
                  AND w.inspection_date<=?"""
    with _con() as connection:
        accepted = connection.execute(
            f"""SELECT COALESCE(SUM(o.observed_completed_value_cents),0), COUNT(*) {common}
                  AND o.observation_type='COMPLETED_WORK' AND o.canonical_sov_item_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM acceptance_decisions d WHERE d.observation_id=o.observation_id
                              AND d.decision_code IN ({placeholders}) AND d.decision_date<=?)
                  AND NOT EXISTS (SELECT 1 FROM deficiency_cases f WHERE f.observation_id=o.observation_id
                                  AND f.opened_date<=? AND f.case_status IN ('OPEN','UNDER_REVIEW')
                                  AND (f.resolved_date IS NULL OR f.resolved_date>?))""",
            [procurement_id, payment_application_id, decision_cutoff_date, *decision_codes, decision_cutoff_date,
             decision_cutoff_date, decision_cutoff_date],
        ).fetchone()
        open_count = connection.execute(
            f"""SELECT COUNT(DISTINCT o.observation_id) {common}
                  AND EXISTS (SELECT 1 FROM deficiency_cases f WHERE f.observation_id=o.observation_id
                              AND f.opened_date<=? AND f.case_status IN ('OPEN','UNDER_REVIEW')
                              AND (f.resolved_date IS NULL OR f.resolved_date>?))""",
            [procurement_id, payment_application_id, decision_cutoff_date, decision_cutoff_date, decision_cutoff_date],
        ).fetchone()[0]
        mapping_count = connection.execute(
            f"SELECT COUNT(*) {common} AND (o.canonical_sov_item_id IS NULL OR o.observation_type='LEGACY_MAPPING_EXCEPTION')",
            [procurement_id, payment_application_id, decision_cutoff_date],
        ).fetchone()[0]
    return {
        "procurement_id": procurement_id,
        "payment_application_id": payment_application_id,
        "decision_cutoff_date": decision_cutoff_date,
        "accepted_completed_work_cents": accepted[0],
        "accepted_observation_count": accepted[1],
        "excluded_open_deficiency_count": open_count,
        "excluded_mapping_exception_count": mapping_count,
    }


def compare_field_and_billed_work(
    procurement_id: str,
    payment_application_id: str,
    decision_cutoff_date: str,
    group_by: str = "canonical_sov_item_id",
) -> dict:
    """Compare accepted field value with contractor-billed work and stored materials.

    Args:
        procurement_id: Procurement identifier assigned to the inspection work orders.
        payment_application_id: Payment application identifier assigned to line-item observations.
        decision_cutoff_date: Inclusive acceptance decision cutoff date in YYYY-MM-DD format.
        group_by: Grouping field; currently only canonical_sov_item_id is supported.

    Returns:
        A dictionary with line-level variances and aggregate accepted and billed totals.
    """
    if group_by != "canonical_sov_item_id":
        raise ValueError("group_by must be canonical_sov_item_id.")
    if not procurement_id or not payment_application_id:
        raise ValueError("procurement_id and payment_application_id are required.")
    _validate_date(decision_cutoff_date, "decision_cutoff_date")
    with _con() as connection:
        rows = connection.execute(
            """SELECT o.canonical_sov_item_id,
                      SUM(CASE WHEN o.observation_type='COMPLETED_WORK' THEN o.observed_completed_value_cents ELSE 0 END) AS billed_completed_work_cents,
                      SUM(CASE WHEN o.observation_type='STORED_MATERIAL' THEN o.stored_material_value_cents ELSE 0 END) AS billed_stored_material_cents,
                      SUM(CASE WHEN o.observation_type='COMPLETED_WORK' AND o.canonical_sov_item_id IS NOT NULL
                                AND EXISTS (SELECT 1 FROM acceptance_decisions d WHERE d.observation_id=o.observation_id
                                            AND d.decision_code='ACCEPTED' AND d.decision_date<=?)
                                AND NOT EXISTS (SELECT 1 FROM deficiency_cases f WHERE f.observation_id=o.observation_id
                                                AND f.opened_date<=? AND f.case_status IN ('OPEN','UNDER_REVIEW')
                                                AND (f.resolved_date IS NULL OR f.resolved_date>?))
                               THEN o.observed_completed_value_cents ELSE 0 END) AS accepted_completed_work_cents,
                      MAX(CASE WHEN o.canonical_sov_item_id IS NULL THEN 1 ELSE 0 END) AS mapping_exception,
                      MAX(CASE WHEN o.observation_type='STORED_MATERIAL' AND o.acceptance_status IN ('UNSUPPORTED','REJECTED') THEN 1 ELSE 0 END) AS unsupported_material,
                      MAX(CASE WHEN EXISTS (SELECT 1 FROM deficiency_cases f WHERE f.observation_id=o.observation_id
                                           AND f.opened_date<=? AND f.case_status IN ('OPEN','UNDER_REVIEW')
                                           AND (f.resolved_date IS NULL OR f.resolved_date>?)) THEN 1 ELSE 0 END) AS open_deficiency
               FROM inspection_observations o JOIN inspection_work_orders w ON w.work_order_id=o.work_order_id
               WHERE w.procurement_id=? AND o.payment_application_id=? AND w.work_order_status IN ('CLOSED','FINALIZED')
                 AND w.inspection_date<=? GROUP BY o.canonical_sov_item_id ORDER BY o.canonical_sov_item_id""",
            [decision_cutoff_date, decision_cutoff_date, decision_cutoff_date, decision_cutoff_date,
             decision_cutoff_date, procurement_id, payment_application_id, decision_cutoff_date],
        ).fetchall()
    lines = []
    for row in rows:
        reasons = []
        if row["mapping_exception"]:
            reasons.append("Unmapped legacy cost code")
        if row["unsupported_material"]:
            reasons.append("Stored-material support not accepted")
        if row["open_deficiency"]:
            reasons.append("Open deficiency at cutoff")
        billed = row["billed_completed_work_cents"]
        accepted = row["accepted_completed_work_cents"]
        lines.append({
            "canonical_sov_item_id": row["canonical_sov_item_id"],
            "accepted_completed_work_cents": accepted,
            "billed_completed_work_cents": billed,
            "billed_stored_material_cents": row["billed_stored_material_cents"],
            "variance_cents": accepted - billed,
            "exception_reason": "; ".join(reasons) if reasons else None,
        })
    return {
        "payment_application_id": payment_application_id,
        "decision_cutoff_date": decision_cutoff_date,
        "lines": lines,
        "totals": {
            "accepted_completed_work_cents": sum(line["accepted_completed_work_cents"] for line in lines),
            "billed_completed_work_cents": sum(line["billed_completed_work_cents"] for line in lines),
            "billed_stored_material_cents": sum(line["billed_stored_material_cents"] for line in lines),
        },
    }


def create_deficiency_case(
    observation_id: str,
    work_order_id: str,
    deficiency_code: str,
    description: str,
    payment_hold_cents: int = 0,
    opened_date: str = None,
) -> dict:
    """Create an open deficiency case for an existing inspection observation.

    Args:
        observation_id: Existing inspection observation identifier.
        work_order_id: Work order that must own the specified observation.
        deficiency_code: Business classification code for the deficiency.
        description: Detailed field or documentation issue requiring resolution.
        payment_hold_cents: Nonnegative payment amount to hold, in cents.
        opened_date: Required case opening date in YYYY-MM-DD format.

    Returns:
        The newly persisted deficiency case as a dictionary.
    """
    if not opened_date:
        raise ValueError("opened_date is required.")
    _validate_date(opened_date, "opened_date")
    if payment_hold_cents < 0:
        raise ValueError("payment_hold_cents cannot be negative.")
    if not deficiency_code.strip() or not description.strip():
        raise ValueError("deficiency_code and description are required.")
    with _con() as connection:
        observation = connection.execute(
            "SELECT work_order_id FROM inspection_observations WHERE observation_id=?", (observation_id,)
        ).fetchone()
        if observation is None:
            raise ValueError(f"Observation {observation_id} was not found.")
        if observation["work_order_id"] != work_order_id:
            raise ValueError("The observation does not belong to the supplied work_order_id.")
        duplicate = connection.execute(
            """SELECT deficiency_id FROM deficiency_cases WHERE observation_id=? AND deficiency_code=?
               AND case_status IN ('OPEN','UNDER_REVIEW')""",
            (observation_id, deficiency_code),
        ).fetchone()
        if duplicate:
            raise ValueError(f"409: open deficiency {duplicate['deficiency_id']} already uses this code for the observation.")
        deficiency_id = _new_identifier(connection, "deficiency_cases", "deficiency_id", "CWI-DEF", date.fromisoformat(opened_date).year)
        connection.execute(
            """INSERT INTO deficiency_cases
               (deficiency_id, observation_id, work_order_id, deficiency_code, case_status, opened_date,
                resolved_date, payment_hold_cents, description) VALUES (?, ?, ?, ?, 'OPEN', ?, NULL, ?, ?)""",
            (deficiency_id, observation_id, work_order_id, deficiency_code, opened_date, payment_hold_cents, description),
        )
        row = connection.execute(
            """SELECT deficiency_id, observation_id, work_order_id, deficiency_code, case_status,
                      opened_date, payment_hold_cents, description FROM deficiency_cases WHERE deficiency_id=?""",
            (deficiency_id,),
        ).fetchone()
    return dict(row)


def record_acceptance_decision(
    observation_id: str,
    deficiency_id: str = None,
    reviewer_id: str = None,
    reviewer_name: str = None,
    decision_code: str = None,
    decision_date: str = None,
    payment_eligible_cents: int = 0,
    rationale: str = None,
) -> dict:
    """Record a payment-review decision for an observation or related deficiency.

    Args:
        observation_id: Existing inspection observation identifier.
        deficiency_id: Optional deficiency that must reference the same observation.
        reviewer_id: Personnel identifier for the reviewer making the decision.
        reviewer_name: Display name of the reviewer making the decision.
        decision_code: ACCEPTED, CONDITIONAL_ACCEPTANCE, REJECTED, or RETURNED_FOR_SUPPORT.
        decision_date: Decision date in YYYY-MM-DD format.
        payment_eligible_cents: Nonnegative amount eligible for payment, in cents.
        rationale: Review rationale supporting the decision and payment treatment.

    Returns:
        The newly persisted acceptance decision as a dictionary.
    """
    allowed = {"ACCEPTED", "CONDITIONAL_ACCEPTANCE", "REJECTED", "RETURNED_FOR_SUPPORT"}
    if decision_code not in allowed:
        raise ValueError("decision_code is not recognized.")
    if not decision_date:
        raise ValueError("decision_date is required.")
    _validate_date(decision_date, "decision_date")
    if payment_eligible_cents < 0:
        raise ValueError("payment_eligible_cents cannot be negative.")
    if not reviewer_id or not reviewer_name or not rationale:
        raise ValueError("reviewer_id, reviewer_name, and rationale are required.")
    if decision_code in {"REJECTED", "RETURNED_FOR_SUPPORT"} and payment_eligible_cents > 0:
        raise ValueError("Rejected or returned decisions cannot carry a positive eligible amount.")
    with _con() as connection:
        observation = connection.execute(
            "SELECT observation_id FROM inspection_observations WHERE observation_id=?", (observation_id,)
        ).fetchone()
        if observation is None:
            raise ValueError(f"Observation {observation_id} was not found.")
        deficiency = None
        if deficiency_id:
            deficiency = connection.execute(
                "SELECT observation_id, case_status FROM deficiency_cases WHERE deficiency_id=?", (deficiency_id,)
            ).fetchone()
            if deficiency is None:
                raise ValueError(f"Deficiency {deficiency_id} was not found.")
            if deficiency["observation_id"] != observation_id:
                raise ValueError("The deficiency does not belong to the supplied observation_id.")
        if decision_code == "ACCEPTED" and payment_eligible_cents > 0:
            if deficiency and deficiency["case_status"] in {"OPEN", "UNDER_REVIEW"}:
                raise ValueError("A positive ACCEPTED decision is not allowed while the linked deficiency remains open.")
            open_case = connection.execute(
                """SELECT deficiency_id FROM deficiency_cases WHERE observation_id=?
                   AND case_status IN ('OPEN','UNDER_REVIEW') LIMIT 1""", (observation_id,)
            ).fetchone()
            if open_case:
                raise ValueError("A positive ACCEPTED decision is not allowed while an observation deficiency remains open.")
        decision_id = _new_identifier(connection, "acceptance_decisions", "decision_id", "CWI-DEC", date.fromisoformat(decision_date).year)
        connection.execute(
            """INSERT INTO acceptance_decisions
               (decision_id, observation_id, deficiency_id, reviewer_id, reviewer_name, decision_code,
                decision_date, payment_eligible_cents, rationale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (decision_id, observation_id, deficiency_id, reviewer_id, reviewer_name, decision_code,
             decision_date, payment_eligible_cents, rationale),
        )
        row = connection.execute(
            """SELECT decision_id, observation_id, deficiency_id, reviewer_id, decision_code,
                      decision_date, payment_eligible_cents, rationale FROM acceptance_decisions WHERE decision_id=?""",
            (decision_id,),
        ).fetchone()
    return dict(row)

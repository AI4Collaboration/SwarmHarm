"""MCP-compatible accessors for Autodesk Construction Cloud field progress data."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _con():
    database = Path(__file__).resolve().parent.parent / "system" / "acc_field_progress" / "state.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_date(value, name):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD format") from exc


def _validate_timestamp(value, name):
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO 8601 timestamp") from exc


def _validate_page(offset, page_size):
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")


def _rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def search_daily_reports(field_project_id: str, start_date: str, end_date: str, inspector_id: str = None, report_status: str = None, offset: int = 0, page_size: int = 50):
    """Search daily reports for one project and a closed date range.

    Args:
        field_project_id: Autodesk Construction Cloud field project identifier.
        start_date: Inclusive report-date lower bound in YYYY-MM-DD format.
        end_date: Inclusive report-date upper bound in YYYY-MM-DD format.
        inspector_id: Optional inspector identifier to match exactly.
        report_status: Optional status: draft, posted, weather_shutdown, or voided.
        offset: Zero-based number of matching records to skip.
        page_size: Maximum records to return, from 1 through 100.

    Returns:
        A dictionary containing items, offset, page_size, and total match count.
    """
    if not field_project_id.strip():
        raise ValueError("field_project_id is required")
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")
    if report_status not in (None, "draft", "posted", "weather_shutdown", "voided"):
        raise ValueError("report_status must be draft, posted, weather_shutdown, or voided")
    _validate_page(offset, page_size)
    clauses = ["field_project_id = ?", "report_date BETWEEN ? AND ?"]
    params = [field_project_id, start_date, end_date]
    if inspector_id is not None:
        clauses.append("inspector_id = ?")
        params.append(inspector_id)
    if report_status is not None:
        clauses.append("report_status = ?")
        params.append(report_status)
    where = " AND ".join(clauses)
    with _con() as con:
        total = con.execute(f"SELECT COUNT(*) FROM daily_reports WHERE {where}", params).fetchone()[0]
        items = _rows(con.execute(
            f"SELECT daily_report_id, field_project_id, report_date, report_status, inspector_id, weather_summary, work_summary, submitted_at FROM daily_reports WHERE {where} ORDER BY report_date DESC, daily_report_id ASC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ))
    return {"items": items, "offset": offset, "page_size": page_size, "total": total}


def list_installed_quantities(field_project_id: str, canonical_sov_item_id: str, start_date: str, end_date: str, accepted_flag: bool = None, include_voided_reports: bool = False, offset: int = 0, page_size: int = 50):
    """List installed-quantity observations for a project, SOV item, and period.

    Args:
        field_project_id: Field project identifier to filter.
        canonical_sov_item_id: Canonical schedule-of-values item identifier.
        start_date: Inclusive daily-report lower bound in YYYY-MM-DD format.
        end_date: Inclusive daily-report upper bound in YYYY-MM-DD format.
        accepted_flag: Optional acceptance filter; true for accepted or false for rejected.
        include_voided_reports: Whether observations on voided reports are included.
        offset: Zero-based number of matching observations to skip.
        page_size: Maximum observations to return, from 1 through 100.

    Returns:
        A dictionary containing observation items, pagination values, and total count.
    """
    if not field_project_id.strip() or not canonical_sov_item_id.strip():
        raise ValueError("field_project_id and canonical_sov_item_id are required")
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")
    _validate_page(offset, page_size)
    clauses = ["d.field_project_id = ?", "i.canonical_sov_item_id = ?", "d.report_date BETWEEN ? AND ?"]
    params = [field_project_id, canonical_sov_item_id, start_date, end_date]
    if not include_voided_reports:
        clauses.append("d.report_status <> 'voided'")
    if accepted_flag is not None:
        clauses.append("i.accepted_flag = ?")
        params.append(int(accepted_flag))
    where = " AND ".join(clauses)
    join = "installed_quantity_entries i JOIN daily_reports d ON d.daily_report_id = i.daily_report_id"
    with _con() as con:
        total = con.execute(f"SELECT COUNT(*) FROM {join} WHERE {where}", params).fetchone()[0]
        items = _rows(con.execute(
            f"SELECT i.quantity_entry_id, i.daily_report_id, d.report_date, d.report_status, i.canonical_sov_item_id, i.installed_quantity_milliunits, i.accepted_flag, i.measurement_method, i.entry_note FROM {join} WHERE {where} ORDER BY d.report_date DESC, i.quantity_entry_id ASC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ))
    for item in items:
        item["accepted_flag"] = bool(item["accepted_flag"])
    return {"items": items, "offset": offset, "page_size": page_size, "total": total}


def calculate_measured_progress(field_project_id: str, canonical_sov_item_id: str, through_date: str, target_quantity_milliunits: int, start_date: str = None):
    """Calculate quantity-supported progress from posted, accepted field entries.

    Args:
        field_project_id: Field project identifier to aggregate.
        canonical_sov_item_id: Canonical schedule-of-values item identifier.
        through_date: Inclusive aggregation end date in YYYY-MM-DD format.
        target_quantity_milliunits: Positive contract target quantity in milliunits.
        start_date: Optional inclusive aggregation start date in YYYY-MM-DD format.

    Returns:
        A dictionary with accepted quantity, target, measured basis points, and excluded voided quantity.
    """
    if not field_project_id.strip() or not canonical_sov_item_id.strip():
        raise ValueError("field_project_id and canonical_sov_item_id are required")
    _validate_date(through_date, "through_date")
    if start_date is not None:
        _validate_date(start_date, "start_date")
        if start_date > through_date:
            raise ValueError("start_date cannot be after through_date")
    if target_quantity_milliunits <= 0:
        raise ValueError("target_quantity_milliunits must be greater than zero")
    date_clause = "d.report_date <= ?" if start_date is None else "d.report_date BETWEEN ? AND ?"
    date_params = [through_date] if start_date is None else [start_date, through_date]
    common = f"d.field_project_id = ? AND i.canonical_sov_item_id = ? AND {date_clause}"
    params = [field_project_id, canonical_sov_item_id] + date_params
    with _con() as con:
        accepted = con.execute(
            f"SELECT COALESCE(SUM(i.installed_quantity_milliunits), 0) FROM installed_quantity_entries i JOIN daily_reports d ON d.daily_report_id=i.daily_report_id WHERE {common} AND d.report_status='posted' AND i.accepted_flag=1",
            params,
        ).fetchone()[0]
        excluded_voided = con.execute(
            f"SELECT COALESCE(SUM(i.installed_quantity_milliunits), 0) FROM installed_quantity_entries i JOIN daily_reports d ON d.daily_report_id=i.daily_report_id WHERE {common} AND d.report_status='voided'",
            params,
        ).fetchone()[0]
    return {"field_project_id": field_project_id, "canonical_sov_item_id": canonical_sov_item_id, "start_date": start_date, "through_date": through_date, "accepted_quantity_milliunits": accepted, "target_quantity_milliunits": target_quantity_milliunits, "measured_percent_bp": accepted * 10000 // target_quantity_milliunits, "excluded_voided_quantity_milliunits": excluded_voided}


def compare_progress_assessments(application_id: str, field_project_id: str, canonical_sov_item_ids: list, current_only: bool = True):
    """Align contractor and City progress assessments for selected SOV items.

    Args:
        application_id: Payment-application identifier to compare.
        field_project_id: Field project identifier to constrain the comparison.
        canonical_sov_item_ids: Nonempty list of canonical SOV item identifiers.
        current_only: Whether to use only records marked as current.

    Returns:
        A dictionary with application_id and paired contractor/City comparison items.
    """
    if not application_id.strip() or not field_project_id.strip():
        raise ValueError("application_id and field_project_id are required")
    if not canonical_sov_item_ids:
        raise ValueError("canonical_sov_item_ids must contain at least one item")
    unique_ids = list(dict.fromkeys(canonical_sov_item_ids))
    marks = ",".join("?" for _ in unique_ids)
    current_clause = "AND is_current = 1" if current_only else ""
    with _con() as con:
        assessments = _rows(con.execute(
            f"SELECT * FROM progress_assessments WHERE application_id=? AND field_project_id=? AND canonical_sov_item_id IN ({marks}) {current_clause} ORDER BY canonical_sov_item_id, assessment_source, version_no DESC",
            [application_id, field_project_id] + unique_ids,
        ))
        disputes = {row[0]: row[1] for row in con.execute(
            f"SELECT a.canonical_sov_item_id, CASE WHEN SUM(CASE WHEN d.resolution_status IN ('open','under_review') THEN 1 ELSE 0 END)>0 THEN 'under_review' ELSE MAX(d.resolution_status) END FROM field_disputes d JOIN progress_assessments a ON a.assessment_id=d.assessment_id WHERE a.application_id=? AND a.field_project_id=? AND a.canonical_sov_item_id IN ({marks}) GROUP BY a.canonical_sov_item_id",
            [application_id, field_project_id] + unique_ids,
        )}
    grouped = {item_id: {"contractor": None, "city": None} for item_id in unique_ids}
    for row in assessments:
        source = row["assessment_source"]
        if grouped[row["canonical_sov_item_id"]][source] is None:
            grouped[row["canonical_sov_item_id"]][source] = row
    items = []
    for item_id in unique_ids:
        contractor, city = grouped[item_id]["contractor"], grouped[item_id]["city"]
        contractor_bp = contractor["percent_complete_bp"] if contractor else None
        city_bp = city["percent_complete_bp"] if city else None
        items.append({"canonical_sov_item_id": item_id, "contractor_assessment_id": contractor["assessment_id"] if contractor else None, "contractor_percent_bp": contractor_bp, "city_assessment_id": city["assessment_id"] if city else None, "city_percent_bp": city_bp, "delta_bp": contractor_bp - city_bp if contractor_bp is not None and city_bp is not None else None, "dispute_status": disputes.get(item_id)})
    return {"application_id": application_id, "items": items}


def list_field_disputes(field_project_id: str, application_id: str = None, resolution_status: str = None, reason_code: str = None, offset: int = 0, page_size: int = 50):
    """List field-progress disputes and their supporting daily reports.

    Args:
        field_project_id: Required project identifier resolved through the assessment.
        application_id: Optional payment-application identifier.
        resolution_status: Optional status: open, under_review, resolved, or withdrawn.
        reason_code: Optional reason code defined by the field-dispute workflow.
        offset: Zero-based number of matching disputes to skip.
        page_size: Maximum disputes to return, from 1 through 100.

    Returns:
        A dictionary containing dispute items, pagination values, and total count.
    """
    if not field_project_id.strip():
        raise ValueError("field_project_id is required")
    if resolution_status not in (None, "open", "under_review", "resolved", "withdrawn"):
        raise ValueError("resolution_status must be open, under_review, resolved, or withdrawn")
    reasons = (None, "unsupported_quantity", "percent_overstatement", "duplicate_sync", "scope_mismatch", "measurement_pending")
    if reason_code not in reasons:
        raise ValueError("reason_code is not recognized")
    _validate_page(offset, page_size)
    clauses, params = ["a.field_project_id = ?"], [field_project_id]
    if application_id is not None:
        clauses.append("a.application_id = ?")
        params.append(application_id)
    if resolution_status is not None:
        clauses.append("fd.resolution_status = ?")
        params.append(resolution_status)
    if reason_code is not None:
        clauses.append("fd.reason_code = ?")
        params.append(reason_code)
    where = " AND ".join(clauses)
    join = "field_disputes fd JOIN progress_assessments a ON a.assessment_id=fd.assessment_id JOIN daily_reports dr ON dr.daily_report_id=fd.daily_report_id"
    with _con() as con:
        total = con.execute(f"SELECT COUNT(*) FROM {join} WHERE {where}", params).fetchone()[0]
        items = _rows(con.execute(
            f"SELECT fd.dispute_id, fd.assessment_id, a.application_id, a.canonical_sov_item_id, fd.reason_code, fd.resolution_status, fd.daily_report_id, dr.report_date, fd.opened_at, fd.resolution_note, fd.resolved_at, fd.resolved_by_id FROM {join} WHERE {where} ORDER BY fd.opened_at DESC, fd.dispute_id ASC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ))
    return {"items": items, "offset": offset, "page_size": page_size, "total": total}


def record_progress_assessment(field_project_id: str, application_id: str, canonical_sov_item_id: str, assessment_source: str, percent_complete_bp: int, target_quantity_milliunits: int, assessment_date: str, assessor_id: str, rationale: str = None):
    """Create a new current progress-assessment version transactionally.

    Args:
        field_project_id: Existing field project identifier.
        application_id: Payment-application identifier for the assessment.
        canonical_sov_item_id: Canonical schedule-of-values item identifier.
        assessment_source: Assessment owner, either contractor or city.
        percent_complete_bp: Completion percentage in basis points from 0 through 10000.
        target_quantity_milliunits: Positive target quantity in milliunits.
        assessment_date: Assessment effective date in YYYY-MM-DD format.
        assessor_id: Person or organization identifier responsible for the assessment.
        rationale: Optional explanation supporting the assessed percentage.

    Returns:
        A dictionary with the new assessment ID, version, current flag, creation time, and superseded ID.
    """
    if assessment_source not in ("contractor", "city"):
        raise ValueError("assessment_source must be contractor or city")
    if not 0 <= percent_complete_bp <= 10000:
        raise ValueError("percent_complete_bp must be between 0 and 10000")
    if target_quantity_milliunits <= 0:
        raise ValueError("target_quantity_milliunits must be greater than zero")
    if not all(value.strip() for value in (field_project_id, application_id, canonical_sov_item_id, assessor_id)):
        raise ValueError("project, application, SOV item, and assessor identifiers are required")
    _validate_date(assessment_date, "assessment_date")
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assessment_id = f"PA-{uuid4().hex[:20].upper()}"
    with _con() as con:
        if con.execute("SELECT 1 FROM field_projects WHERE field_project_id=?", (field_project_id,)).fetchone() is None:
            raise ValueError("field_project_id does not exist")
        current = con.execute("SELECT assessment_id, version_no FROM progress_assessments WHERE field_project_id=? AND application_id=? AND canonical_sov_item_id=? AND assessment_source=? AND is_current=1 ORDER BY version_no DESC LIMIT 1", (field_project_id, application_id, canonical_sov_item_id, assessment_source)).fetchone()
        max_version = con.execute("SELECT COALESCE(MAX(version_no),0) FROM progress_assessments WHERE field_project_id=? AND application_id=? AND canonical_sov_item_id=? AND assessment_source=?", (field_project_id, application_id, canonical_sov_item_id, assessment_source)).fetchone()[0]
        if current:
            con.execute("UPDATE progress_assessments SET is_current=0 WHERE assessment_id=?", (current["assessment_id"],))
        con.execute("INSERT INTO progress_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (assessment_id, field_project_id, application_id, canonical_sov_item_id, assessment_source, percent_complete_bp, target_quantity_milliunits, assessment_date, max_version + 1, 1, assessor_id, rationale, created_at))
    return {"assessment_id": assessment_id, "version_no": max_version + 1, "is_current": True, "created_at": created_at, "superseded_assessment_id": current["assessment_id"] if current else None}


def resolve_field_dispute(dispute_id: str, resolution_status: str, reviewer_id: str, resolution_note: str, resolved_at: str):
    """Move an open field dispute into a terminal resolution state.

    Args:
        dispute_id: Existing dispute identifier.
        resolution_status: Terminal status, either resolved or withdrawn.
        reviewer_id: Identifier of the person approving the disposition.
        resolution_note: Nonempty explanation of the final disposition.
        resolved_at: ISO 8601 timestamp when the decision became effective.

    Returns:
        A dictionary with previous and final status plus persisted resolution fields.
    """
    if resolution_status not in ("resolved", "withdrawn"):
        raise ValueError("resolution_status must be resolved or withdrawn")
    if not dispute_id.strip() or not reviewer_id.strip():
        raise ValueError("dispute_id and reviewer_id are required")
    if not resolution_note.strip():
        raise ValueError("resolution_note must not be blank")
    _validate_timestamp(resolved_at, "resolved_at")
    with _con() as con:
        dispute = con.execute("SELECT resolution_status, opened_at FROM field_disputes WHERE dispute_id=?", (dispute_id,)).fetchone()
        if dispute is None:
            raise ValueError("dispute_id does not exist")
        previous = dispute["resolution_status"]
        if previous not in ("open", "under_review"):
            raise ValueError(f"dispute is already in terminal status {previous}")
        if datetime.fromisoformat(resolved_at.replace("Z", "+00:00")) < datetime.fromisoformat(dispute["opened_at"].replace("Z", "+00:00")):
            raise ValueError("resolved_at cannot be before opened_at")
        con.execute("UPDATE field_disputes SET resolution_status=?, resolution_note=?, resolved_at=?, resolved_by_id=? WHERE dispute_id=?", (resolution_status, resolution_note, resolved_at, reviewer_id, dispute_id))
    return {"dispute_id": dispute_id, "previous_status": previous, "resolution_status": resolution_status, "resolution_note": resolution_note, "resolved_at": resolved_at, "resolved_by_id": reviewer_id}


def summarize_period_production(field_project_id: str, application_id: str = "PAYAPP-FY26-MICRO-001", period_start: str = "2025-09-01", period_end: str = "2025-09-30", canonical_sov_item_ids: list = None):
    """Summarize accepted, rejected, and voided-parent production by SOV item.

    Args:
        field_project_id: Field project identifier to aggregate.
        application_id: Payment-application identifier included in the response context.
        period_start: Inclusive production-period start date in YYYY-MM-DD format.
        period_end: Inclusive production-period end date in YYYY-MM-DD format.
        canonical_sov_item_ids: Optional nonempty list restricting canonical SOV items.

    Returns:
        A dictionary with period context and one production summary per SOV item.
    """
    if not field_project_id.strip() or not application_id.strip():
        raise ValueError("field_project_id and application_id are required")
    _validate_date(period_start, "period_start")
    _validate_date(period_end, "period_end")
    if period_start > period_end:
        raise ValueError("period_start cannot be after period_end")
    clauses = ["d.field_project_id=?", "d.report_date BETWEEN ? AND ?"]
    params = [field_project_id, period_start, period_end]
    if canonical_sov_item_ids is not None:
        if not canonical_sov_item_ids:
            raise ValueError("canonical_sov_item_ids cannot be an empty list")
        ids = list(dict.fromkeys(canonical_sov_item_ids))
        clauses.append(f"i.canonical_sov_item_id IN ({','.join('?' for _ in ids)})")
        params.extend(ids)
    where = " AND ".join(clauses)
    with _con() as con:
        items = _rows(con.execute(
            f"SELECT i.canonical_sov_item_id, COALESCE(SUM(CASE WHEN d.report_status='posted' AND i.accepted_flag=1 THEN i.installed_quantity_milliunits ELSE 0 END),0) AS accepted_quantity_milliunits, COUNT(DISTINCT CASE WHEN d.report_status='posted' AND i.accepted_flag=1 THEN d.report_date END) AS production_day_count, COALESCE(SUM(CASE WHEN d.report_status='posted' AND i.accepted_flag=0 THEN i.installed_quantity_milliunits ELSE 0 END),0) AS rejected_quantity_milliunits, COALESCE(SUM(CASE WHEN d.report_status='voided' THEN i.installed_quantity_milliunits ELSE 0 END),0) AS voided_parent_quantity_milliunits FROM installed_quantity_entries i JOIN daily_reports d ON d.daily_report_id=i.daily_report_id WHERE {where} GROUP BY i.canonical_sov_item_id ORDER BY i.canonical_sov_item_id",
            params,
        ))
    for item in items:
        days = item["production_day_count"]
        item["average_per_production_day_milliunits"] = item["accepted_quantity_milliunits"] / days if days else 0
    return {"field_project_id": field_project_id, "application_id": application_id, "period_start": period_start, "period_end": period_end, "items": items}

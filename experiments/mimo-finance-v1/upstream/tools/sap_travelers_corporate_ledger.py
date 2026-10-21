"""MCP tools for the Travelers Corporate Ledger workspace."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _con() -> sqlite3.Connection:
    """Open the workspace ledger database with dictionary-like rows."""
    connection = sqlite3.connect(
        Path(__file__).resolve().parent.parent / "system" / "sap_travelers_corporate_ledger" / "state.db"
    )
    connection.row_factory = sqlite3.Row
    return connection


def _page(page_size: int, page_token: str | None) -> tuple[int, int]:
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200")
    if page_token is None or page_token == "":
        return 0, page_size
    try:
        offset = int(page_token)
    except ValueError as exc:
        raise ValueError("page_token must be a non-negative row offset") from exc
    if offset < 0:
        raise ValueError("page_token must be a non-negative row offset")
    return offset, page_size


def _paged(sql: str, params: list[object], page_size: int, page_token: str | None) -> dict:
    offset, limit = _page(page_size, page_token)
    with _con() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        rows = [dict(row) for row in connection.execute(f"{sql} LIMIT ? OFFSET ?", [*params, limit, offset])]
    next_token = str(offset + len(rows)) if offset + len(rows) < total else None
    return {"columns": list(rows[0].keys()) if rows else [], "rows": rows, "total": total, "next_page_token": next_token}


def search_ledger_expense_detail(
    document_number: str | None = None,
    posting_date_from: str | None = None,
    posting_date_to: str | None = None,
    pool_id: str | None = None,
    cost_center: str | None = None,
    expense_category_id: str | None = None,
    claim_adjustment_category_id: str | None = None,
    shared_pool_flag: int | None = None,
    specific_identification_flag: int | None = None,
    page_size: int = 50,
    page_token: str | None = None,
) -> dict:
    """Search FY2024 ledger journal lines with business filters and stable pagination.

    Args: document_number: Exact SAP document number. posting_date_from: Inclusive ISO date lower bound.
      posting_date_to: Inclusive ISO date upper bound. pool_id: Expense pool identifier. cost_center: Cost center code.
      expense_category_id: NAIC-style expense category. claim_adjustment_category_id: Claim-adjustment category.
      shared_pool_flag: 0 or 1 shared-pool indicator. specific_identification_flag: 0 or 1 specific-identification indicator.
      page_size: Number of rows to return, from 1 through 200. page_token: Opaque offset token from the prior response.
    Returns: A JSON-serializable dictionary containing columns, rows, total, and next_page_token.
    """
    filters = ["p.analysis_period_id = 'FY2024'"]
    params: list[object] = []
    supplied = [document_number, posting_date_from, posting_date_to, pool_id, cost_center, expense_category_id, claim_adjustment_category_id, shared_pool_flag, specific_identification_flag]
    if not any(value is not None for value in supplied):
        raise ValueError("at least one ledger filter is required")
    for value, clause in ((document_number, "d.document_number = ?"), (pool_id, "d.pool_id = ?"), (cost_center, "d.cost_center = ?"), (expense_category_id, "d.expense_category_id = ?"), (claim_adjustment_category_id, "d.claim_adjustment_category_id = ?"), (shared_pool_flag, "d.shared_pool_flag = ?"), (specific_identification_flag, "d.specific_identification_flag = ?")):
        if value is not None:
            if clause.endswith("flag = ?") and value not in (0, 1):
                raise ValueError("flag filters must be 0 or 1")
            filters.append(clause); params.append(value)
    if posting_date_from is not None:
        filters.append("d.posting_date >= ?"); params.append(posting_date_from)
    if posting_date_to is not None:
        filters.append("d.posting_date <= ?"); params.append(posting_date_to)
    sql = f"SELECT d.* FROM ledger_expense_detail d JOIN expense_pools p ON p.pool_id = d.pool_id WHERE {' AND '.join(filters)} ORDER BY d.posting_date, d.document_number, d.line_number"
    return _paged(sql, params, page_size, page_token)


def query_expense_pools(
    analysis_period_id: str | None = None, expense_category_id: str | None = None, shared_pool_flag: int | None = None,
    summary_row_flag: int | None = None, row_type: str | None = None, segment_id: str | None = None,
    page_size: int = 50, page_token: str | None = None,
) -> dict:
    """Query expense-pool controls and allocations using scoped filters and pagination.

    Args: analysis_period_id: Fiscal analysis period. expense_category_id: Expense category code. shared_pool_flag: 0 or 1 flag.
      summary_row_flag: 0 or 1 summary-control flag. row_type: CONTROL or ALLOCATION. segment_id: Operating segment code.
      page_size: Number of rows to return, from 1 through 200. page_token: Opaque offset token.
    Returns: A dictionary with columns, rows, total, and next_page_token.
    """
    values = [analysis_period_id, expense_category_id, shared_pool_flag, summary_row_flag, row_type, segment_id]
    if not any(value is not None for value in values):
        raise ValueError("at least one pool filter is required")
    clauses = ["1=1"]; params: list[object] = []
    for value, field in ((analysis_period_id, "analysis_period_id"), (expense_category_id, "expense_category_id"), (shared_pool_flag, "shared_pool_flag"), (summary_row_flag, "summary_row_flag"), (row_type, "row_type"), (segment_id, "segment_id")):
        if value is not None:
            if field in ("shared_pool_flag", "summary_row_flag") and value not in (0, 1): raise ValueError(f"{field} must be 0 or 1")
            if field == "row_type" and value not in ("CONTROL", "ALLOCATION"): raise ValueError("row_type must be CONTROL or ALLOCATION")
            clauses.append(f"{field} = ?"); params.append(value)
    sql = f"SELECT * FROM expense_pools WHERE {' AND '.join(clauses)} ORDER BY analysis_period_id, pool_id"
    return _paged(sql, params, page_size, page_token)


def query_legacy_allocations(analysis_period_id: str | None = None, segment_id: str | None = None, allocation_basis: str | None = None, page_size: int = 50, page_token: str | None = None) -> dict:
    """Read legacy segment allocations for a selected period, segment, or basis.

    Args: analysis_period_id: Fiscal analysis period. segment_id: Operating segment code. allocation_basis: Legacy allocation method.
      page_size: Number of rows to return, from 1 through 200. page_token: Opaque offset token.
    Returns: A dictionary with columns, rows, total, and next_page_token.
    """
    if not any(value is not None for value in (analysis_period_id, segment_id, allocation_basis)): raise ValueError("at least one allocation filter is required")
    clauses = ["1=1"]; params: list[object] = []
    for value, field in ((analysis_period_id, "analysis_period_id"), (segment_id, "segment_id"), (allocation_basis, "allocation_basis")):
        if value is not None: clauses.append(f"{field} = ?"); params.append(value)
    return _paged(f"SELECT * FROM legacy_segment_allocations WHERE {' AND '.join(clauses)} ORDER BY analysis_period_id, segment_id", params, page_size, page_token)


def query_premium_denominators(analysis_period_id: str | None = None, segment_id: str | None = None, denominator_status: str | None = None, page_size: int = 50, page_token: str | None = None) -> dict:
    """Read segment earned-premium denominators by period, segment, and approval status.

    Args: analysis_period_id: Fiscal analysis period. segment_id: Operating segment code. denominator_status: APPROVED, DRAFT, or SUPERSEDED.
      page_size: Number of rows to return, from 1 through 200. page_token: Opaque offset token.
    Returns: A dictionary with columns, rows, total, and next_page_token.
    """
    if not any(value is not None for value in (analysis_period_id, segment_id, denominator_status)): raise ValueError("at least one denominator filter is required")
    if denominator_status is not None and denominator_status not in ("APPROVED", "DRAFT", "SUPERSEDED"): raise ValueError("denominator_status is invalid")
    clauses = ["1=1"]; params: list[object] = []
    for value, field in ((analysis_period_id, "analysis_period_id"), (segment_id, "segment_id"), (denominator_status, "denominator_status")):
        if value is not None: clauses.append(f"{field} = ?"); params.append(value)
    return _paged(f"SELECT * FROM segment_premium_denominators WHERE {' AND '.join(clauses)} ORDER BY analysis_period_id, segment_id", params, page_size, page_token)


def reconcile_activity_allocation(analysis_period_id: str, include_exclusions: bool = True, include_summary_control: bool = False) -> dict:
    """Rebuild activity-based AO and shared-service components and reconcile them to controls.

    Args: analysis_period_id: Fiscal analysis period to reconcile. include_exclusions: Include specifically identified and excluded journal lines in detail output.
      include_summary_control: Include the consolidated summary control alongside component controls.
    Returns: A dictionary containing component_controls, rebuilt_components, component_variances, segment_allocations, and consolidated_reconciliation.
    """
    with _con() as c:
        controls = [dict(r) for r in c.execute("SELECT expense_category_id, control_amount_usd FROM expense_pools WHERE analysis_period_id=? AND row_type='CONTROL' AND (summary_row_flag=0 OR ?=1) ORDER BY expense_category_id", (analysis_period_id, int(include_summary_control)))]
        excluded = "" if include_exclusions else " AND d.shared_pool_flag=1 AND d.specific_identification_flag=0 AND d.expense_category_id NOT IN ('INVESTMENT','DEFENSE_COST_CONTAINMENT')"
        rebuilt = [dict(r) for r in c.execute(f"SELECT d.expense_category_id, SUM(d.amount_usd) AS rebuilt_amount_usd FROM ledger_expense_detail d JOIN expense_pools p ON p.pool_id=d.pool_id WHERE p.analysis_period_id=? AND d.expense_category_id IN ('ADJUSTING_OTHER','SHARED_SERVICE'){excluded} GROUP BY d.expense_category_id ORDER BY d.expense_category_id", (analysis_period_id,))]
        variances = []
        control_map = {r['expense_category_id']: r['control_amount_usd'] for r in controls}
        for row in rebuilt:
            variances.append({'expense_category_id': row['expense_category_id'], 'control_amount_usd': control_map.get(row['expense_category_id']), 'rebuilt_amount_usd': row['rebuilt_amount_usd'], 'variance_usd': row['rebuilt_amount_usd'] - control_map[row['expense_category_id']] if row['expense_category_id'] in control_map else None})
        segments = [dict(r) for r in c.execute("SELECT segment_id, SUM(allocated_amount_usd) AS activity_amount_usd FROM expense_pools WHERE analysis_period_id=? AND row_type='ALLOCATION' AND allocation_basis IN ('claim_counts_handling_hours','policy_volume_system_usage') GROUP BY segment_id ORDER BY segment_id", (analysis_period_id,))]
        total = sum(r['activity_amount_usd'] or 0 for r in segments)
    return {'component_controls': controls, 'rebuilt_components': rebuilt, 'component_variances': variances, 'segment_allocations': segments, 'consolidated_reconciliation': {'activity_allocated_amount_usd': total, 'control_amount_usd': sum(r['control_amount_usd'] or 0 for r in controls if r['expense_category_id'] != 'CONSOLIDATED_UNALLOCATED')}}


def calculate_segment_impact(analysis_period_id: str, segment_id: str | None = None, denominator_status: str = 'APPROVED', display_precision_bps: int = 1) -> dict:
    """Compare activity-based and legacy segment allocations against earned-premium denominators.

    Args: analysis_period_id: Fiscal analysis period. segment_id: Optional operating segment filter. denominator_status: Denominator status to join.
      display_precision_bps: Decimal places for the displayed basis-point effect, from 0 through 4.
    Returns: A dictionary containing segment impact rows and aggregate totals.
    """
    if denominator_status not in ('APPROVED', 'DRAFT', 'SUPERSEDED'): raise ValueError('denominator_status is invalid')
    if not 0 <= display_precision_bps <= 4: raise ValueError('display_precision_bps must be between 0 and 4')
    with _con() as c:
        clauses = ["a.analysis_period_id=?", "l.analysis_period_id=?", "d.analysis_period_id=?", "d.denominator_status=?"]
        params: list[object] = [analysis_period_id, analysis_period_id, analysis_period_id, denominator_status]
        if segment_id is not None: clauses.append("a.segment_id=?"); params.append(segment_id)
        sql = f"""SELECT a.segment_id, SUM(a.allocated_amount_usd) AS activity_amount_usd,
          l.legacy_amount_usd, d.earned_premium_usd
          FROM expense_pools a JOIN legacy_segment_allocations l ON l.segment_id=a.segment_id
          JOIN segment_premium_denominators d ON d.segment_id=a.segment_id
          WHERE {' AND '.join(clauses)} AND a.row_type='ALLOCATION'
            AND a.allocation_basis IN ('claim_counts_handling_hours','policy_volume_system_usage')
            AND l.allocation_basis='earned_premium_ratio_legacy'
          GROUP BY a.segment_id, l.legacy_amount_usd, d.earned_premium_usd ORDER BY a.segment_id"""
        rows = []
        for r in c.execute(sql, params):
            item = dict(r); item['impact_usd'] = item['activity_amount_usd'] - item['legacy_amount_usd']; item['expense_ratio_effect_bps'] = item['impact_usd'] / item['earned_premium_usd'] * 10000
            item['expense_ratio_effect_bps_display'] = round(item['expense_ratio_effect_bps'], display_precision_bps); rows.append(item)
    return {'analysis_period_id': analysis_period_id, 'denominator_status': denominator_status, 'rows': rows, 'total_impact_usd': sum(r['impact_usd'] for r in rows)}

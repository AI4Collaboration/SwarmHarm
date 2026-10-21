import sqlite3
from pathlib import Path


def _con():
    """Open the policy and service usage data-mart database."""
    path = Path(__file__).resolve().parent.parent / "system" / "policycenter_servicenow_usage" / "state.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _page(page_size, page_token):
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200")
    if page_token is None:
        return 0
    try:
        offset = int(page_token)
    except (TypeError, ValueError):
        raise ValueError("page_token must be a nonnegative row offset")
    if offset < 0:
        raise ValueError("page_token must be a nonnegative row offset")
    return offset


def _paged_rows(sql, params, page_size, page_token):
    offset = _page(page_size, page_token)
    with _con() as con:
        total = con.execute("SELECT COUNT(*) FROM (" + sql + ")", params).fetchone()[0]
        rows = [dict(row) for row in con.execute(sql + " LIMIT ? OFFSET ?", [*params, page_size, offset])]
    next_token = str(offset + page_size) if offset + len(rows) < total else None
    return {"items": rows, "total": total, "page_size": page_size, "next_page_token": next_token}


def _validate_year(fiscal_year):
    if not 2000 <= fiscal_year <= 2100:
        raise ValueError("fiscal_year must be between 2000 and 2100")


def _validate_pool(con, service_pool_id):
    row = con.execute("SELECT * FROM shared_service_pools WHERE service_pool_id = ?", (service_pool_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown service_pool_id: {service_pool_id}")
    return dict(row)


def search_monthly_usage(segment_id: str = None, service_pool_id: str = None, usage_month: str = None, source_platform: str = None, eligible_for_shared_pool: bool = None, page_size: int = 100, page_token: str = None):
    """Return filtered monthly PolicyCenter and ServiceNow usage records in stable paginated order.

    Args:
        segment_id: Optional canonical usage segment identifier.
        service_pool_id: Optional shared-service pool identifier.
        usage_month: Optional first-of-month ISO date filter.
        source_platform: Optional platform name from the controlled platform list.
        eligible_for_shared_pool: Optional eligibility flag.
        page_size: Number of records to return, from 1 through 200.
        page_token: Opaque row-offset token returned by a prior call.
    Returns:
        A dictionary with items, total, page_size, and next_page_token.
    """
    if all(value is None for value in (segment_id, service_pool_id, usage_month, source_platform, eligible_for_shared_pool)):
        raise ValueError("Provide at least one filter to avoid an unbounded usage export")
    if source_platform is not None and source_platform not in {"PolicyCenter", "ServiceNow", "InvestmentPlatform", "SeparatelyBilledApp"}:
        raise ValueError("source_platform is not recognized")
    clauses, params = [], []
    for column, value in (("segment_id", segment_id), ("service_pool_id", service_pool_id), ("usage_month", usage_month), ("source_platform", source_platform), ("eligible_for_shared_pool", eligible_for_shared_pool)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    sql = "SELECT usage_id, segment_id, service_pool_id, usage_month, source_platform, in_force_policy_equivalents, system_usage_units, eligible_for_shared_pool, source_record_status FROM monthly_policy_system_usage WHERE " + " AND ".join(clauses) + " ORDER BY usage_month, segment_id, usage_id"
    return _paged_rows(sql, params, page_size, page_token)


def get_usage_segments(segment_id: str = None, page_size: int = 100, page_token: str = None):
    """Return the canonical PolicyCenter segment crosswalk with optional paging.

    Args:
        segment_id: Optional canonical segment identifier.
        page_size: Number of records to return, from 1 through 200.
        page_token: Opaque row-offset token returned by a prior call.
    Returns:
        A dictionary with items, total, page_size, and next_page_token.
    """
    if segment_id is None:
        raise ValueError("Provide segment_id to avoid an unbounded segment export")
    return _paged_rows("SELECT segment_id, segment_name, policycenter_segment_code, technology_cost_center_label FROM usage_segments WHERE segment_id = ? ORDER BY segment_id", [segment_id], page_size, page_token)


def get_shared_service_pools(service_pool_id: str = None, eligible_for_abc: bool = None, allocation_scope: str = None, page_size: int = 100, page_token: str = None):
    """Return controlled shared-service pool definitions with optional eligibility and scope filters.

    Args:
        service_pool_id: Optional pool identifier.
        eligible_for_abc: Optional ABC allocation eligibility flag.
        allocation_scope: Optional value among ALL_SHARED_SERVICES, CLAIM_HANDLING, and PREMIUM_ONLY.
        page_size: Number of records to return, from 1 through 200.
        page_token: Opaque row-offset token returned by a prior call.
    Returns:
        A dictionary with items, total, page_size, and next_page_token.
    """
    if service_pool_id is None and eligible_for_abc is None and allocation_scope is None:
        raise ValueError("Provide a pool, eligibility, or allocation_scope filter")
    if allocation_scope is not None and allocation_scope not in {"ALL_SHARED_SERVICES", "CLAIM_HANDLING", "PREMIUM_ONLY"}:
        raise ValueError("allocation_scope is not recognized")
    clauses, params = [], []
    for column, value in (("service_pool_id", service_pool_id), ("eligible_for_abc", eligible_for_abc), ("allocation_scope", allocation_scope)):
        if value is not None:
            clauses.append(f"{column} = ?"); params.append(value)
    sql = (
        "SELECT service_pool_id, service_pool_name, pool_amount_usd, "
        "policy_driver_weight, system_usage_driver_weight, allocation_scope, eligible_for_abc "
        "FROM shared_service_pools WHERE " + " AND ".join(clauses) +
        " ORDER BY CASE WHEN service_pool_id LIKE 'POOL_ARCHIVE_%' THEN 1 ELSE 0 END, service_pool_id"
    )
    return _paged_rows(sql, params, page_size, page_token)


def _driver_rows(con, fiscal_year, service_pool_id, segment_id=None, include_excluded=False):
    start, end = f"{fiscal_year:04d}-01-01", f"{fiscal_year:04d}-12-01"
    clauses = ["usage_month >= ?", "usage_month <= ?", "service_pool_id = ?"]
    params = [start, end, service_pool_id]
    if segment_id is not None:
        clauses.append("segment_id = ?"); params.append(segment_id)
    if not include_excluded:
        clauses.append("eligible_for_shared_pool = 1")
    return con.execute("SELECT segment_id, SUM(in_force_policy_equivalents) policy_equivalents, SUM(system_usage_units) system_usage_units, COUNT(DISTINCT usage_month) observed_months FROM monthly_policy_system_usage WHERE " + " AND ".join(clauses) + " GROUP BY segment_id ORDER BY segment_id", params).fetchall()


def aggregate_policy_drivers(fiscal_year: int, service_pool_id: str, segment_id: str = None, include_excluded: bool = False):
    """Aggregate annual policy-equivalent and system-usage drivers by segment.

    Args:
        fiscal_year: Calendar fiscal year to aggregate.
        service_pool_id: Pool whose monthly records are included.
        segment_id: Optional segment-level restriction.
        include_excluded: Include rows marked ineligible for the shared pool when true.
    Returns:
        A dictionary containing fiscal_year, service_pool_id, rows, and control totals.
    """
    _validate_year(fiscal_year)
    with _con() as con:
        pool = _validate_pool(con, service_pool_id)
        rows = [dict(row) for row in _driver_rows(con, fiscal_year, service_pool_id, segment_id, include_excluded)]
    return {"fiscal_year": fiscal_year, "service_pool_id": service_pool_id, "rows": rows, "control_totals": {"policy_equivalents": sum((r["policy_equivalents"] or 0) for r in rows), "system_usage_units": sum((r["system_usage_units"] or 0) for r in rows), "observed_months": sum(r["observed_months"] for r in rows)}, "include_excluded": include_excluded, "pool_eligible_for_abc": pool["eligible_for_abc"]}


def calculate_service_allocation(fiscal_year: int, service_pool_id: str, rounding: str = "nearest_usd"):
    """Allocate an eligible service pool using independently normalized policy and usage drivers.

    Args:
        fiscal_year: Calendar fiscal year used for the twelve monthly drivers.
        service_pool_id: Eligible shared-service pool to allocate.
        rounding: Allocation rounding mode; currently only nearest_usd is supported.
    Returns:
        A dictionary with pool amount, driver weights, segment allocations, and reconciliation difference.
    """
    _validate_year(fiscal_year)
    if rounding not in {"nearest_usd"}:
        raise ValueError("rounding must be 'nearest_usd'")
    with _con() as con:
        pool = _validate_pool(con, service_pool_id)
        if not pool["eligible_for_abc"]:
            raise ValueError("service_pool_id is not eligible for ABC allocation")
        rows = [dict(row) for row in _driver_rows(con, fiscal_year, service_pool_id)]
    policy_total = sum(r["policy_equivalents"] or 0 for r in rows)
    usage_total = sum(r["system_usage_units"] or 0 for r in rows)
    if not rows or not policy_total or not usage_total:
        raise ValueError("No complete eligible driver detail is available")
    allocations = []
    for row in rows:
        policy_share = row["policy_equivalents"] / policy_total
        usage_share = row["system_usage_units"] / usage_total
        combined = pool["policy_driver_weight"] / 10000 * policy_share + pool["system_usage_driver_weight"] / 10000 * usage_share
        allocations.append({"segment_id": row["segment_id"], "allocated_amount_usd": int(round(pool["pool_amount_usd"] * combined)), "policy_share": policy_share, "system_usage_share": usage_share, "combined_share": combined})
    total = sum(r["allocated_amount_usd"] for r in allocations)
    return {"fiscal_year": fiscal_year, "service_pool_id": service_pool_id, "pool_amount_usd": pool["pool_amount_usd"], "driver_weights": {"policy_driver_weight": pool["policy_driver_weight"], "system_usage_driver_weight": pool["system_usage_driver_weight"]}, "allocations": allocations, "total_allocated_amount_usd": total, "reconciliation_difference_usd": pool["pool_amount_usd"] - total}


def validate_usage_export(fiscal_year: int, service_pool_id: str, fail_on_excluded_platform: bool = False):
    """Run completeness, integrity, platform, crosswalk, and eligibility controls on a usage export.

    Args:
        fiscal_year: Calendar fiscal year to validate.
        service_pool_id: Pool whose export is validated.
        fail_on_excluded_platform: Treat reconciliation-only platforms as a validation failure.
    Returns:
        A dictionary with overall status, named checks, month counts, and issue counters.
    """
    _validate_year(fiscal_year)
    platforms = ("InvestmentPlatform", "SeparatelyBilledApp")
    with _con() as con:
        _validate_pool(con, service_pool_id)
        start, end = f"{fiscal_year:04d}-01-01", f"{fiscal_year:04d}-12-01"
        base = "FROM monthly_policy_system_usage WHERE usage_month >= ? AND usage_month <= ? AND service_pool_id = ?"
        params = [start, end, service_pool_id]
        duplicate_count = con.execute("SELECT COUNT(*) - COUNT(DISTINCT segment_id || '|' || usage_month || '|' || source_platform) " + base, params).fetchone()[0]
        negative_count = con.execute("SELECT COUNT(*) " + base + " AND (in_force_policy_equivalents < 0 OR system_usage_units < 0)", params).fetchone()[0]
        excluded_count = con.execute("SELECT COUNT(*) " + base + " AND source_platform IN (?, ?)", [*params, *platforms]).fetchone()[0]
        missing_crosswalk = con.execute("SELECT COUNT(*) " + base + " AND (segment_id NOT IN (SELECT segment_id FROM usage_segments) OR service_pool_id NOT IN (SELECT service_pool_id FROM shared_service_pools))", params).fetchone()[0]
        eligibility_exceptions = con.execute("SELECT COUNT(*) " + base + " AND source_platform IN (?, ?) AND eligible_for_shared_pool <> 0", [*params, *platforms]).fetchone()[0]
        counts = {r[0]: r[1] for r in con.execute("SELECT segment_id, COUNT(DISTINCT usage_month) " + base + " AND eligible_for_shared_pool = 1 GROUP BY segment_id", params)}
    checks = [
        {"check_name": "month_completeness", "status": "PASS" if all(counts.get(s, 0) == 12 for s in ("SEG_TBI", "SEG_TBSI", "SEG_TPI")) else "FAIL", "issue_count": sum(1 for s in ("SEG_TBI", "SEG_TBSI", "SEG_TPI") if counts.get(s, 0) != 12), "issue_rows": []},
        {"check_name": "duplicate_source_keys", "status": "PASS" if duplicate_count == 0 else "FAIL", "issue_count": duplicate_count, "issue_rows": []},
        {"check_name": "negative_driver_values", "status": "PASS" if negative_count == 0 else "FAIL", "issue_count": negative_count, "issue_rows": []},
        {"check_name": "excluded_platforms", "status": "PASS" if not fail_on_excluded_platform or excluded_count == 0 else "FAIL", "issue_count": excluded_count, "issue_rows": []},
        {"check_name": "crosswalk_integrity", "status": "PASS" if missing_crosswalk == 0 else "FAIL", "issue_count": missing_crosswalk, "issue_rows": []},
        {"check_name": "eligibility_exceptions", "status": "PASS" if eligibility_exceptions == 0 else "FAIL", "issue_count": eligibility_exceptions, "issue_rows": []},
    ]
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL", "fiscal_year": fiscal_year, "service_pool_id": service_pool_id, "checks": checks, "eligible_month_count_by_segment": counts, "duplicate_count": duplicate_count, "excluded_platform_count": excluded_count}

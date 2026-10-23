import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _con():
    database = Path(__file__).resolve().parent.parent / "system" / "salesforce_revenue_cloud" / "state.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_page(page_size: int, offset: int) -> None:
    if not 1 <= page_size <= 200:
        raise ValueError("page_size must be between 1 and 200.")
    if offset < 0:
        raise ValueError("offset must be zero or greater.")


def _one_opportunity(connection, opportunity_id: str = None, contract_id: str = None):
    if not opportunity_id and not contract_id:
        raise ValueError("Provide opportunity_id or contract_id.")
    clauses = []
    parameters = []
    if opportunity_id:
        clauses.append("opportunity_id = ?")
        parameters.append(opportunity_id)
    if contract_id:
        clauses.append("contract_id = ?")
        parameters.append(contract_id)
    rows = connection.execute(
        f"SELECT * FROM sales_opportunities WHERE {' OR '.join(clauses)}", parameters
    ).fetchall()
    if not rows:
        raise ValueError("No sales opportunity matches the supplied identifier.")
    unique = {row["opportunity_id"]: row for row in rows}
    if len(unique) != 1:
        raise ValueError("opportunity_id and contract_id identify different sales opportunities.")
    return next(iter(unique.values()))


def _resolve_quote(connection, contract_id: str = None, opportunity_id: str = None, quote_id: str = None):
    if not contract_id and not opportunity_id and not quote_id:
        raise ValueError("Provide contract_id, opportunity_id, or quote_id.")
    if contract_id or opportunity_id:
        opportunity = _one_opportunity(connection, opportunity_id, contract_id)
    else:
        matches = connection.execute(
            """SELECT DISTINCT so.*
               FROM sales_opportunities so
               JOIN quote_line_items qli ON qli.opportunity_id = so.opportunity_id
               WHERE qli.quote_id = ?""",
            (quote_id,),
        ).fetchall()
        if not matches:
            raise ValueError("No quote matches quote_id.")
        if len(matches) != 1:
            raise ValueError("quote_id is associated with more than one opportunity.")
        opportunity = matches[0]
    selected_quote_id = quote_id or opportunity["controlling_quote_id"]
    if not selected_quote_id:
        raise ValueError("The sales opportunity does not have a controlling quote.")
    belongs = connection.execute(
        "SELECT 1 FROM quote_line_items WHERE opportunity_id = ? AND quote_id = ? LIMIT 1",
        (opportunity["opportunity_id"], selected_quote_id),
    ).fetchone()
    if not belongs:
        raise ValueError("quote_id does not belong to the resolved sales opportunity.")
    return opportunity, selected_quote_id


def _quote_metrics(connection, opportunity_id: str, quote_id: str):
    row = connection.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN line_status = 'ACTIVE' AND duplicate_of_line_id IS NULL
                                 THEN extended_amount_cents ELSE 0 END), 0) AS total_cents,
               SUM(CASE WHEN line_status = 'ACTIVE' AND duplicate_of_line_id IS NULL THEN 1 ELSE 0 END) AS eligible_count,
               SUM(CASE WHEN duplicate_of_line_id IS NOT NULL THEN 1 ELSE 0 END) AS duplicate_count,
               SUM(CASE WHEN line_status <> 'ACTIVE' THEN 1 ELSE 0 END) AS nonactive_count
           FROM quote_line_items
           WHERE opportunity_id = ? AND quote_id = ?""",
        (opportunity_id, quote_id),
    ).fetchone()
    return {
        "total_cents": row["total_cents"],
        "eligible_line_count": row["eligible_count"],
        "excluded_duplicate_line_count": row["duplicate_count"],
        "excluded_nonactive_line_count": row["nonactive_count"],
    }


def _ensure_assignment_history(connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS opportunity_owner_assignment_history (
               assignment_history_id TEXT PRIMARY KEY,
               opportunity_id TEXT NOT NULL,
               previous_owner_id TEXT,
               new_owner_id TEXT NOT NULL,
               assignment_reason TEXT NOT NULL,
               assigned_by_id TEXT NOT NULL,
               expected_current_owner_id TEXT,
               assigned_at TEXT NOT NULL,
               FOREIGN KEY (opportunity_id) REFERENCES sales_opportunities(opportunity_id)
           )"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS assignment_history_no_update
           BEFORE UPDATE ON opportunity_owner_assignment_history
           BEGIN SELECT RAISE(ABORT, 'assignment history is immutable'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS assignment_history_no_delete
           BEFORE DELETE ON opportunity_owner_assignment_history
           BEGIN SELECT RAISE(ABORT, 'assignment history is immutable'); END"""
    )


def search_employer_accounts(
    query: str,
    tax_classification: str = None,
    account_status: str = "ACTIVE",
    page_size: int = 25,
    offset: int = 0,
) -> dict:
    """Search employer accounts by identifier or name with optional account filters.

    Args:
        query: Case-insensitive text matched against account ID, legal name, alias, and normalized legal name.
        tax_classification: Optional exact tax-classification code, such as C_CORPORATION.
        account_status: Optional ACTIVE, INACTIVE, or PROSPECT status filter; pass None to include all statuses.
        page_size: Maximum records to return, from 1 through 200.
        offset: Zero-based number of matching records to skip.

    Returns:
        A dictionary containing records, total_count, offset, and page_size.
    """
    if not query or not query.strip():
        raise ValueError("query must contain search text; unfiltered account exports are not allowed.")
    if account_status not in {None, "ACTIVE", "INACTIVE", "PROSPECT"}:
        raise ValueError("account_status must be ACTIVE, INACTIVE, PROSPECT, or None.")
    _validate_page(page_size, offset)
    term = f"%{query.strip().lower()}%"
    clauses = [
        "(lower(account_id) LIKE ? OR lower(legal_name) LIKE ? OR lower(COALESCE(alias_name, '')) LIKE ? OR normalized_legal_name LIKE ?)"
    ]
    parameters = [term, term, term, term]
    if tax_classification:
        clauses.append("tax_classification = ?")
        parameters.append(tax_classification)
    if account_status:
        clauses.append("account_status = ?")
        parameters.append(account_status)
    where = " AND ".join(clauses)
    with _con() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM employer_accounts WHERE {where}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"""SELECT account_id, legal_name, alias_name, tax_classification,
                       account_owner_id, account_status
                FROM employer_accounts WHERE {where}
                ORDER BY legal_name, account_id LIMIT ? OFFSET ?""",
            [*parameters, page_size, offset],
        ).fetchall()
    return {"records": [dict(row) for row in rows], "total_count": total, "offset": offset, "page_size": page_size}


def get_sales_opportunity(opportunity_id: str = None, contract_id: str = None) -> dict:
    """Retrieve one sales opportunity by its opportunity or contract identifier.

    Args:
        opportunity_id: Optional unique Salesforce opportunity identifier.
        contract_id: Optional unique contract intake identifier.

    Returns:
        A dictionary with contract, employer, requesting party, ownership, quote, amount, and pricing fields.
    """
    with _con() as connection:
        row = _one_opportunity(connection, opportunity_id, contract_id)
    fields = [
        "opportunity_id", "account_id", "contract_id", "requesting_unit_id",
        "requesting_contact_person_id", "opportunity_owner_id", "opportunity_owner_status",
        "submission_status", "requested_deadline", "controlling_quote_id",
        "displayed_quote_total_cents", "pricing_basis_code", "pricing_approval_reference",
    ]
    return {field: row[field] for field in fields}


def list_quote_line_items(
    opportunity_id: str = None,
    quote_id: str = None,
    line_status: str = None,
    include_duplicates: bool = False,
    page_size: int = 50,
    offset: int = 0,
) -> dict:
    """List paginated quote lines for a specified opportunity or quote.

    Args:
        opportunity_id: Optional opportunity identifier used to restrict quote lines.
        quote_id: Optional quote identifier used to restrict quote lines.
        line_status: Optional ACTIVE, SUPERSEDED, or VOID status filter.
        include_duplicates: Whether to include lines carrying a duplicate_of_line_id reference.
        page_size: Maximum records to return, from 1 through 200.
        offset: Zero-based number of matching records to skip.

    Returns:
        A dictionary containing quote-line records, total_count, offset, and page_size.
    """
    if not opportunity_id and not quote_id:
        raise ValueError("Provide opportunity_id or quote_id; unfiltered quote-line exports are not allowed.")
    if line_status not in {None, "ACTIVE", "SUPERSEDED", "VOID"}:
        raise ValueError("line_status must be ACTIVE, SUPERSEDED, VOID, or None.")
    _validate_page(page_size, offset)
    clauses = []
    parameters = []
    if opportunity_id:
        clauses.append("opportunity_id = ?")
        parameters.append(opportunity_id)
    if quote_id:
        clauses.append("quote_id = ?")
        parameters.append(quote_id)
    if line_status:
        clauses.append("line_status = ?")
        parameters.append(line_status)
    if not include_duplicates:
        clauses.append("duplicate_of_line_id IS NULL")
    where = " AND ".join(clauses)
    columns = """quote_line_id, opportunity_id, quote_id, quote_version, service_code,
                 service_description, quantity, unit_price_cents, extended_amount_cents,
                 line_status, duplicate_of_line_id, pricing_attribute_status, finance_worktag_status"""
    with _con() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM quote_line_items WHERE {where}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT {columns} FROM quote_line_items WHERE {where} ORDER BY created_at, quote_line_id LIMIT ? OFFSET ?",
            [*parameters, page_size, offset],
        ).fetchall()
    return {"records": [dict(row) for row in rows], "total_count": total, "offset": offset, "page_size": page_size}


def calculate_active_quote_total(
    contract_id: str = None,
    opportunity_id: str = None,
    quote_id: str = None,
) -> dict:
    """Recalculate an active, nonduplicate quote total from stored line items.

    Args:
        contract_id: Optional contract identifier used to resolve the sales opportunity.
        opportunity_id: Optional opportunity identifier used to resolve the sales opportunity.
        quote_id: Optional quote identifier; otherwise the opportunity's controlling quote is used.

    Returns:
        A dictionary with resolved identifiers, eligible and excluded counts, integer cents, USD amount, and currency.
    """
    with _con() as connection:
        opportunity, selected_quote_id = _resolve_quote(connection, contract_id, opportunity_id, quote_id)
        metrics = _quote_metrics(connection, opportunity["opportunity_id"], selected_quote_id)
    return {
        "opportunity_id": opportunity["opportunity_id"],
        "contract_id": opportunity["contract_id"],
        "controlling_quote_id": selected_quote_id,
        "eligible_line_count": metrics["eligible_line_count"],
        "total_cents": metrics["total_cents"],
        "total_usd": metrics["total_cents"] / 100,
        "currency": "USD",
        "excluded_duplicate_line_count": metrics["excluded_duplicate_line_count"],
        "excluded_nonactive_line_count": metrics["excluded_nonactive_line_count"],
    }


def validate_sales_intake_fields(
    contract_id: str,
    checklist_profile: str = "cscc_nonstandard",
    include_line_findings: bool = True,
) -> dict:
    """Validate required sales-intake and pricing fields before legal routing.

    Args:
        contract_id: Unique contract intake identifier to validate.
        checklist_profile: Checklist ruleset; currently cscc_nonstandard is supported.
        include_line_findings: Whether to include individual incomplete quote-line findings.

    Returns:
        A dictionary with completeness, recomputed proposed value, findings, and deficiency flags.
    """
    if checklist_profile != "cscc_nonstandard":
        raise ValueError("checklist_profile must be cscc_nonstandard.")
    with _con() as connection:
        opportunity = _one_opportunity(connection, contract_id=contract_id)
        findings = []
        opportunity_checks = [
            ("opportunity_owner_id", "Opportunity owner must be assigned before Legal routing."),
            ("requesting_unit_id", "Requesting unit is required for intake routing."),
            ("controlling_quote_id", "A controlling quote is required to substantiate proposed value."),
            ("pricing_basis_code", "Pricing basis must be documented."),
            ("pricing_approval_reference", "Pricing approval reference must be documented."),
        ]
        for field, message in opportunity_checks:
            if not opportunity[field]:
                findings.append({
                    "field": field,
                    "scope": "opportunity",
                    "record_id": opportunity["opportunity_id"],
                    "severity": "ERROR",
                    "message": message,
                })
        proposed_value_cents = 0
        incomplete_rows = []
        if opportunity["controlling_quote_id"]:
            metrics = _quote_metrics(
                connection, opportunity["opportunity_id"], opportunity["controlling_quote_id"]
            )
            proposed_value_cents = metrics["total_cents"]
            incomplete_rows = connection.execute(
                """SELECT quote_line_id FROM quote_line_items
                   WHERE opportunity_id = ? AND quote_id = ? AND line_status = 'ACTIVE'
                     AND duplicate_of_line_id IS NULL AND pricing_attribute_status = 'INCOMPLETE'
                   ORDER BY quote_line_id""",
                (opportunity["opportunity_id"], opportunity["controlling_quote_id"]),
            ).fetchall()
            if include_line_findings:
                for row in incomplete_rows:
                    findings.append({
                        "field": "pricing_attribute_status",
                        "scope": "quote_line",
                        "record_id": row["quote_line_id"],
                        "severity": "ERROR",
                        "message": "Active controlling-quote line has incomplete pricing attributes.",
                    })
        missing_pricing_metadata = not opportunity["pricing_basis_code"] or not opportunity["pricing_approval_reference"]
    return {
        "contract_id": contract_id,
        "is_complete": not findings and not incomplete_rows,
        "proposed_value_cents": proposed_value_cents,
        "proposed_value_usd": proposed_value_cents / 100,
        "findings": findings,
        "missing_owner": not bool(opportunity["opportunity_owner_id"]),
        "missing_pricing_metadata": missing_pricing_metadata,
        "incomplete_pricing_line_count": len(incomplete_rows),
    }


def assign_opportunity_owner(
    opportunity_id: str,
    new_owner_id: str,
    assignment_reason: str,
    assigned_by_id: str,
    expected_current_owner_id: str = None,
) -> dict:
    """Assign an opportunity owner and append an immutable assignment-history record.

    Args:
        opportunity_id: Opportunity receiving the new owner assignment.
        new_owner_id: Salesforce user identifier for the new owner.
        assignment_reason: Business reason supporting the assignment or reassignment.
        assigned_by_id: User identifier for the person performing the assignment.
        expected_current_owner_id: Optional current-owner value required for optimistic concurrency control.

    Returns:
        A dictionary with previous and new owners, assigned status, history identifier, and assignment timestamp.
    """
    if not opportunity_id.strip():
        raise ValueError("opportunity_id must not be blank.")
    if not new_owner_id.strip():
        raise ValueError("new_owner_id must not be blank.")
    if not assignment_reason.strip():
        raise ValueError("assignment_reason must not be blank.")
    if not assigned_by_id.strip():
        raise ValueError("assigned_by_id must not be blank.")
    assignment_history_id = f"OAH-{uuid4().hex[:16].upper()}"
    assigned_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _con() as connection:
        _ensure_assignment_history(connection)
        row = connection.execute(
            "SELECT opportunity_owner_id FROM sales_opportunities WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if not row:
            raise ValueError("No sales opportunity matches opportunity_id.")
        previous_owner_id = row["opportunity_owner_id"]
        if expected_current_owner_id is not None and previous_owner_id != expected_current_owner_id:
            raise ValueError(
                f"Owner assignment conflict: expected {expected_current_owner_id!r}, found {previous_owner_id!r}."
            )
        connection.execute(
            """UPDATE sales_opportunities
               SET opportunity_owner_id = ?, opportunity_owner_status = 'ASSIGNED'
               WHERE opportunity_id = ?""",
            (new_owner_id, opportunity_id),
        )
        connection.execute(
            """INSERT INTO opportunity_owner_assignment_history (
                   assignment_history_id, opportunity_id, previous_owner_id, new_owner_id,
                   assignment_reason, assigned_by_id, expected_current_owner_id, assigned_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                assignment_history_id, opportunity_id, previous_owner_id, new_owner_id,
                assignment_reason, assigned_by_id, expected_current_owner_id, assigned_at,
            ),
        )
    return {
        "opportunity_id": opportunity_id,
        "previous_owner_id": previous_owner_id,
        "new_owner_id": new_owner_id,
        "opportunity_owner_status": "ASSIGNED",
        "assignment_history_id": assignment_history_id,
        "assigned_at": assigned_at,
    }

"""Laserfiche payment-review record tools backed by the local SQLite store."""

import base64
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path


def _con():
    connection = sqlite3.connect(Path(__file__).resolve().parent.parent / "system" / "laserfiche_records" / "state.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _date_value(value: str, parameter: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{parameter} must be an ISO date in YYYY-MM-DD format") from exc


def _timestamp_value(value: str, parameter: str) -> str:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{parameter} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{parameter} must include a UTC offset or Z suffix")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        offset = int(payload["offset"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor is invalid or malformed") from exc
    if offset < 0:
        raise ValueError("cursor offset cannot be negative")
    return offset


def _version_identifier(document_id: str, version_number: int, upload_timestamp: str) -> str:
    token = hashlib.sha256(f"{document_id}|{version_number}|{upload_timestamp}".encode()).hexdigest()[:12].upper()
    return f"DV-REG-{token}"


def _citation_identifier(document_version_id: str, cited_document_id: str, anchor_name: str, created_at: str) -> str:
    token = hashlib.sha256(f"{document_version_id}|{cited_document_id}|{anchor_name}|{created_at}".encode()).hexdigest()[:12].upper()
    return f"CIT-REG-{token}"


def _document_version_row(connection: sqlite3.Connection, document_version_id: str):
    return connection.execute(
        "SELECT dv.*, dr.document_title, dr.document_type, dr.document_status, dr.procurement_id, dr.application_id "
        "FROM document_versions dv JOIN document_register dr ON dr.document_id = dv.document_id "
        "WHERE dv.document_version_id = ?",
        (document_version_id,),
    ).fetchone()


def search_controlled_documents(
    query: str = "",
    procurement_id: str | None = None,
    application_id: str | None = None,
    publisher_id: str | None = None,
    document_status: str | None = "CONTROLLED",
    document_type: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    """Search document metadata using combined text and record filters.

    Args:
        query: Case-insensitive text matched against title, record number, procurement, application, publisher name, type, and status.
        procurement_id: Exact procurement identifier to require.
        application_id: Exact payment-application identifier to require.
        publisher_id: Exact publisher profile identifier to require.
        document_status: Exact status to require, or null to omit the status filter.
        document_type: Exact document type to require.
        limit: Maximum records to return, from 1 through 100.
        cursor: Opaque continuation cursor returned by a prior call.

    Returns:
        A dictionary containing document items and the next cursor, if more matches remain.
    """
    statuses = {"CONTROLLED", "UNDER_REVIEW", "SUPERSEDED", "ARCHIVED", "VOID"}
    types = {"city_standard_form", "payment_request_form", "application_workbook", "payment_application", "reconciliation_workbook", "review_memo", "payment_certificate", "briefing_record", "other"}
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if document_status is not None and document_status not in statuses:
        raise ValueError(f"document_status must be one of {sorted(statuses)} or null")
    if document_type is not None and document_type not in types:
        raise ValueError(f"document_type must be one of {sorted(types)} or null")
    if not any([query.strip(), procurement_id, application_id, publisher_id, document_status, document_type]):
        raise ValueError("provide at least one search or document filter")
    offset = _decode_cursor(cursor)
    where = []
    params = []
    if query.strip():
        term = f"%{query.strip().lower()}%"
        where.append("(LOWER(dr.document_title) LIKE ? OR LOWER(COALESCE(dr.external_record_number,'')) LIKE ? OR LOWER(COALESCE(dr.procurement_id,'')) LIKE ? OR LOWER(COALESCE(dr.application_id,'')) LIKE ? OR LOWER(pp.publisher_name) LIKE ? OR LOWER(dr.document_type) LIKE ? OR LOWER(dr.document_status) LIKE ?)")
        params.extend([term] * 7)
    for column, value in [("dr.procurement_id", procurement_id), ("dr.application_id", application_id), ("dr.publisher_id", publisher_id), ("dr.document_status", document_status), ("dr.document_type", document_type)]:
        if value is not None:
            where.append(f"{column} = ?")
            params.append(value)
    sql = f"""
        SELECT dr.*, pp.publisher_name, pp.canonical_entity_id,
               dv.document_version_id, dv.version_number, dv.effective_date, dv.content_hash
        FROM document_register dr
        JOIN publisher_profiles pp ON pp.publisher_id = dr.publisher_id
        LEFT JOIN document_versions dv ON dv.document_id = dr.document_id AND dv.is_current = 1
        WHERE {' AND '.join(where)}
        ORDER BY dr.created_at DESC, dr.document_id
        LIMIT ? OFFSET ?
    """
    with _con() as connection:
        rows = connection.execute(sql, (*params, limit + 1, offset)).fetchall()
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        current_version = None
        if row["document_version_id"] is not None:
            current_version = {key: row[key] for key in ("document_version_id", "version_number", "effective_date", "content_hash")}
        items.append({
            "document_id": row["document_id"], "document_title": row["document_title"], "document_type": row["document_type"],
            "document_status": row["document_status"], "procurement_id": row["procurement_id"], "application_id": row["application_id"],
            "owner_id": row["owner_id"], "publisher": {"publisher_id": row["publisher_id"], "publisher_name": row["publisher_name"], "canonical_entity_id": row["canonical_entity_id"]},
            "current_version": current_version,
        })
    return {"items": items, "next_cursor": _encode_cursor(offset + limit) if has_more else None}


def get_current_document_version(document_id: str, as_of_date: str = "2025-09-30", include_superseded: bool = False) -> dict:
    """Resolve the effective immutable document version at a requested cutoff.

    Args:
        document_id: Document register identifier to resolve.
        as_of_date: Inclusive ISO date cutoff for effective versions.
        include_superseded: Whether to include all earlier registrations rather than only distinct-content predecessors.

    Returns:
        Document metadata, the effective current version, and qualifying superseded versions; or an error code when not found.
    """
    cutoff = _date_value(as_of_date, "as_of_date")
    with _con() as connection:
        document = connection.execute("SELECT document_id, document_title, document_status FROM document_register WHERE document_id = ?", (document_id,)).fetchone()
        if document is None:
            return {"error": "NOT_FOUND", "document_id": document_id, "as_of_date": cutoff}
        versions = connection.execute("SELECT * FROM document_versions WHERE document_id = ? AND effective_date <= ? ORDER BY effective_date DESC, version_number DESC, upload_timestamp DESC", (document_id, cutoff)).fetchall()
    if not versions:
        return {"error": "NOT_FOUND", "document_id": document_id, "as_of_date": cutoff}
    current = versions[0]
    seen_hashes = {current["content_hash"]}
    superseded = []
    for row in versions[1:]:
        if not include_superseded and row["content_hash"] in seen_hashes:
            continue
        seen_hashes.add(row["content_hash"])
        superseded.append({key: row[key] for key in ("document_version_id", "version_number", "content_hash", "upload_timestamp")})
    return {
        "document": dict(document),
        "current_version": {key: current[key] for key in ("document_version_id", "version_number", "effective_date", "upload_timestamp", "content_hash", "mime_type", "storage_locator", "is_current")},
        "superseded_versions": superseded,
    }


def list_extracted_controls(
    document_version_id: str,
    canonical_field_codes: list = None,
    value_types: list = None,
    limit: int = 100,
    cursor: str | None = None,
) -> dict:
    """List extracted controls for one immutable document version.

    Args:
        document_version_id: Immutable version identifier whose fields should be listed.
        canonical_field_codes: Optional canonical-code allowlist; null or an empty list includes all codes.
        value_types: Optional value-type allowlist; null or an empty list includes all value types.
        limit: Maximum controls to return, from 1 through 200.
        cursor: Opaque continuation cursor returned by a prior call.

    Returns:
        A dictionary with the version identifier, control items, and an optional next cursor.
    """
    allowed_types = {"text", "amount_cents", "integer", "boolean", "formula", "blank"}
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    canonical_field_codes = canonical_field_codes or []
    value_types = value_types or []
    invalid_types = sorted(set(value_types) - allowed_types)
    if invalid_types:
        raise ValueError(f"value_types contains unsupported values: {invalid_types}")
    offset = _decode_cursor(cursor)
    where = ["ec.document_version_id = ?"]
    params = [document_version_id]
    if canonical_field_codes:
        where.append(f"ec.canonical_field_code IN ({','.join('?' for _ in canonical_field_codes)})")
        params.extend(canonical_field_codes)
    if value_types:
        where.append(f"ec.value_type IN ({','.join('?' for _ in value_types)})")
        params.extend(value_types)
    sql = f"""
        SELECT ec.*, pp.publisher_name, pp.canonical_entity_id
        FROM extracted_control_fields ec
        LEFT JOIN publisher_profiles pp ON pp.publisher_id = ec.copyright_administrator_id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(ec.extraction_page, 2147483647), COALESCE(ec.extraction_locator, ''), ec.control_field_id
        LIMIT ? OFFSET ?
    """
    with _con() as connection:
        exists = connection.execute("SELECT 1 FROM document_versions WHERE document_version_id = ?", (document_version_id,)).fetchone()
        if exists is None:
            return {"error": "NOT_FOUND", "document_version_id": document_version_id}
        rows = connection.execute(sql, (*params, limit + 1, offset)).fetchall()
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        administrator = None
        if row["copyright_administrator_id"] is not None:
            administrator = {"publisher_id": row["copyright_administrator_id"], "publisher_name": row["publisher_name"], "canonical_entity_id": row["canonical_entity_id"]}
        items.append({key: row[key] for key in ("control_field_id", "source_field_name", "canonical_field_code", "value_type", "text_value", "amount_cents", "extraction_page", "extraction_locator", "confidence_basis_points")} | {"copyright_administrator": administrator})
    return {"document_version_id": document_version_id, "items": items, "next_cursor": _encode_cursor(offset + limit) if has_more else None}


def trace_anchor_citations(
    anchor_name: str,
    procurement_id: str | None = None,
    application_id: str | None = None,
    as_of_date: str = "2025-09-30",
    citation_status: str = "VERIFIED",
    max_depth: int = 4,
) -> dict:
    """Trace a citation anchor across immutable review and evidence versions.

    Args:
        anchor_name: Exact anchor name used on the initial citation edge.
        procurement_id: Optional procurement scope applied to initial citing documents.
        application_id: Optional application scope applied to initial citing documents.
        as_of_date: Inclusive effective-date cutoff for citing versions.
        citation_status: Citation status to follow.
        max_depth: Maximum citation traversal depth, from 1 through 8.

    Returns:
        A graph dictionary containing version nodes, citation edges, detected cycles, and the cutoff date.
    """
    statuses = {"DRAFT", "VERIFIED", "REJECTED", "SUPERSEDED"}
    if citation_status not in statuses:
        raise ValueError(f"citation_status must be one of {sorted(statuses)}")
    if not 1 <= max_depth <= 8:
        raise ValueError("max_depth must be between 1 and 8")
    cutoff = _date_value(as_of_date, "as_of_date")
    where = ["rc.anchor_name = ?", "rc.citation_status = ?", "from_dv.effective_date <= ?"]
    params = [anchor_name, citation_status, cutoff]
    if procurement_id is not None:
        where.append("from_dr.procurement_id = ?")
        params.append(procurement_id)
    if application_id is not None:
        where.append("from_dr.application_id = ?")
        params.append(application_id)
    with _con() as connection:
        seed_rows = connection.execute(f"""
            SELECT rc.* FROM review_citations rc
            JOIN document_versions from_dv ON from_dv.document_version_id = rc.document_version_id
            JOIN document_register from_dr ON from_dr.document_id = from_dv.document_id
            WHERE {' AND '.join(where)} ORDER BY rc.created_at, rc.citation_id
        """, params).fetchall()
        edges = []
        nodes = {}
        cycles = []
        frontier = [(row, [row["document_version_id"]], 1) for row in seed_rows]
        visited_edges = set()
        while frontier:
            row, path, depth = frontier.pop(0)
            if row["citation_id"] in visited_edges:
                continue
            visited_edges.add(row["citation_id"])
            target_version_id = row["cited_document_version_id"]
            if target_version_id is None:
                target = connection.execute("SELECT document_version_id FROM document_versions WHERE document_id = ? AND effective_date <= ? ORDER BY effective_date DESC, version_number DESC LIMIT 1", (row["cited_document_id"], cutoff)).fetchone()
                target_version_id = target["document_version_id"] if target else None
            edges.append({"citation_id": row["citation_id"], "from_document_version_id": row["document_version_id"], "to_document_id": row["cited_document_id"], "to_document_version_id": target_version_id, "anchor_locator": row["anchor_locator"], "citation_status": row["citation_status"], "reviewer_id": row["reviewer_id"]})
            for version_id in [row["document_version_id"], target_version_id]:
                if version_id and version_id not in nodes:
                    version = _document_version_row(connection, version_id)
                    if version:
                        nodes[version_id] = {"document_id": version["document_id"], "document_version_id": version_id, "document_title": version["document_title"], "document_type": version["document_type"], "content_hash": version["content_hash"]}
            if target_version_id in path:
                cycles.append({"document_version_ids": path + [target_version_id]})
                continue
            if target_version_id and depth < max_depth:
                next_rows = connection.execute("SELECT * FROM review_citations WHERE document_version_id = ? AND citation_status = ? ORDER BY created_at, citation_id", (target_version_id, citation_status)).fetchall()
                frontier.extend((next_row, path + [target_version_id], depth + 1) for next_row in next_rows)
    return {"anchor_name": anchor_name, "nodes": list(nodes.values()), "edges": edges, "cycles": cycles, "cutoff_date": cutoff}


def validate_field_map(procurement_id: str, application_id: str, required_profile: str = "APPENDIX_C_G702", as_of_date: str = "2025-09-30") -> dict:
    """Validate the Appendix C and G702 field map at an effective-date cutoff.

    Args:
        procurement_id: Procurement identifier whose controlled records are evaluated.
        application_id: Payment-application identifier whose controlled records are evaluated.
        required_profile: Validation profile name; currently APPENDIX_C_G702.
        as_of_date: Inclusive ISO date cutoff for effective document versions.

    Returns:
        Validation status, checked versions, code-level results, missing codes, and warnings.
    """
    if required_profile != "APPENDIX_C_G702":
        raise ValueError("required_profile must be APPENDIX_C_G702")
    cutoff = _date_value(as_of_date, "as_of_date")
    required_codes = ["APPENDIX_C_CHANGE_ORDER_FIELD_MAP", "G702_TOTAL_COMPLETED_STORED", "G702_CURRENT_PAYMENT_DUE", "FORM_PUBLISHER_NAME", "FORM_PUBLISHER_LEGAL_NAME"]
    with _con() as connection:
        versions = connection.execute("""
            SELECT dr.document_id, dv.document_version_id, dv.content_hash
            FROM document_register dr JOIN document_versions dv ON dv.document_id = dr.document_id
            WHERE dr.procurement_id = ? AND dr.application_id = ? AND dr.document_status IN ('CONTROLLED','UNDER_REVIEW')
              AND dv.is_current = 1 AND dv.effective_date <= ?
            ORDER BY dr.document_id
        """, (procurement_id, application_id, cutoff)).fetchall()
        version_ids = [row["document_version_id"] for row in versions]
        fields_by_code = {code: [] for code in required_codes}
        if version_ids:
            rows = connection.execute(f"SELECT control_field_id, canonical_field_code, value_type, text_value, amount_cents, document_version_id FROM extracted_control_fields WHERE document_version_id IN ({','.join('?' for _ in version_ids)}) AND canonical_field_code IN ({','.join('?' for _ in required_codes)}) ORDER BY control_field_id", (*version_ids, *required_codes)).fetchall()
            for row in rows:
                fields_by_code[row["canonical_field_code"]].append(row)
        duplicate_hashes = connection.execute("""
            SELECT content_hash, GROUP_CONCAT(document_version_id) AS version_ids
            FROM document_versions WHERE document_id IN (SELECT document_id FROM document_register WHERE procurement_id = ? AND application_id = ?)
            GROUP BY document_id, content_hash HAVING COUNT(*) > 1
        """, (procurement_id, application_id)).fetchall()
    fields = []
    missing_codes = []
    for code in required_codes:
        rows = fields_by_code[code]
        if not rows:
            status = "MISSING"
            missing_codes.append(code)
        elif len({row["document_version_id"] for row in rows}) < len(rows):
            status = "DUPLICATE"
        elif rows[0]["value_type"] == "blank" or (rows[0]["text_value"] is None and rows[0]["amount_cents"] is None):
            status = "BLANK"
        else:
            status = "PRESENT"
        fields.append({"canonical_field_code": code, "status": status, "control_field_ids": [row["control_field_id"] for row in rows]})
    warnings = []
    for duplicate in duplicate_hashes:
        warnings.append({"code": "DUPLICATE_CONTENT_REGISTRATION", "message": "Identical content was registered more than once; only the current version was validated.", "document_version_ids": duplicate["version_ids"].split(",")})
    blank_codes = [field["canonical_field_code"] for field in fields if field["status"] == "BLANK"]
    if blank_codes:
        warnings.append({"code": "CURRENT_CONTROL_FIELDS_BLANK", "message": "Current controlled forms contain blank amount controls that require transaction-level support before payment approval.", "document_version_ids": [row["document_version_id"] for row in versions]})
    valid = bool(versions) and not missing_codes and all(field["status"] not in {"DUPLICATE", "MISSING"} for field in fields)
    return {"valid": valid, "required_profile": required_profile, "cutoff_date": cutoff, "documents_checked": [dict(row) for row in versions], "fields": fields, "missing_codes": missing_codes, "warnings": warnings}


def register_document_version(
    document_id: str,
    version_number: int,
    effective_date: str,
    upload_timestamp: str,
    content_hash: str,
    mime_type: str,
    storage_locator: str,
    registered_by: str,
    make_current: bool = False,
) -> dict:
    """Register an immutable document version and optionally make it current.

    Args:
        document_id: Existing parent document identifier.
        version_number: Positive version sequence unique within the document.
        effective_date: ISO date on which the version becomes effective.
        upload_timestamp: ISO 8601 timestamp when Laserfiche received the bytes.
        content_hash: Immutable content digest, normally prefixed with sha256:.
        mime_type: Media type of the stored document.
        storage_locator: Laserfiche repository locator for the immutable bytes.
        registered_by: Person identifier responsible for registration.
        make_current: Whether to supersede the current row in the same transaction.

    Returns:
        Creation status, registered version metadata, and earlier identical-content registrations; or a conflict code.
    """
    if version_number <= 0:
        raise ValueError("version_number must be greater than zero")
    effective = _date_value(effective_date, "effective_date")
    uploaded = _timestamp_value(upload_timestamp, "upload_timestamp")
    if not content_hash.strip() or not mime_type.strip() or not storage_locator.strip() or not registered_by.strip():
        raise ValueError("content_hash, mime_type, storage_locator, and registered_by are required")
    version_id = _version_identifier(document_id, version_number, uploaded)
    with _con() as connection:
        document = connection.execute("SELECT 1 FROM document_register WHERE document_id = ?", (document_id,)).fetchone()
        if document is None:
            return {"created": False, "error": "DOCUMENT_NOT_FOUND", "document_id": document_id}
        existing = connection.execute("SELECT document_version_id FROM document_versions WHERE document_id = ? AND version_number = ?", (document_id, version_number)).fetchone()
        if existing:
            return {"created": False, "error": "VERSION_EXISTS", "document_version_id": existing["document_version_id"]}
        current = connection.execute("SELECT * FROM document_versions WHERE document_id = ? AND is_current = 1", (document_id,)).fetchone()
        if make_current and current and (effective < current["effective_date"] or version_number <= current["version_number"]):
            return {"created": False, "error": "INVALID_CURRENT_TRANSITION", "current_document_version_id": current["document_version_id"]}
        duplicates = connection.execute("SELECT document_version_id, upload_timestamp FROM document_versions WHERE document_id = ? AND content_hash = ? ORDER BY upload_timestamp", (document_id, content_hash)).fetchall()
        with connection:
            connection.execute("INSERT INTO document_versions (document_version_id,document_id,version_number,effective_date,upload_timestamp,content_hash,mime_type,storage_locator,is_current,superseded_by_version_id,registered_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (version_id, document_id, version_number, effective, uploaded, content_hash, mime_type, storage_locator, int(make_current), None, registered_by))
            if make_current and current:
                connection.execute("UPDATE document_versions SET is_current = 0, superseded_by_version_id = ? WHERE document_version_id = ?", (version_id, current["document_version_id"]))
    return {"created": True, "document_version": {"document_version_id": version_id, "document_id": document_id, "version_number": version_number, "effective_date": effective, "upload_timestamp": uploaded, "content_hash": content_hash, "is_current": int(make_current)}, "duplicate_content_of": [dict(row) for row in duplicates]}


def add_review_citation(
    document_version_id: str,
    cited_document_id: str,
    cited_document_version_id: str | None,
    anchor_name: str,
    anchor_locator: str,
    citation_status: str = "DRAFT",
    reviewer_id: str = "",
    citation_note: str | None = None,
) -> dict:
    """Add a review citation from one immutable version to controlled evidence.

    Args:
        document_version_id: Immutable review-deliverable version containing the citation.
        cited_document_id: Controlled evidence document referenced by the citation.
        cited_document_version_id: Optional exact evidence version; required for VERIFIED citations.
        anchor_name: Stable machine-readable anchor name.
        anchor_locator: Human-readable page, worksheet, cell, or section locator.
        citation_status: DRAFT, VERIFIED, REJECTED, or SUPERSEDED.
        reviewer_id: Person identifier responsible for the citation.
        citation_note: Optional reviewer explanation persisted with the citation.

    Returns:
        Creation status and the complete persisted citation, or a validation error code.
    """
    statuses = {"DRAFT", "VERIFIED", "REJECTED", "SUPERSEDED"}
    if citation_status not in statuses:
        raise ValueError(f"citation_status must be one of {sorted(statuses)}")
    if not anchor_name.strip() or not anchor_locator.strip() or not reviewer_id.strip():
        raise ValueError("anchor_name, anchor_locator, and reviewer_id are required")
    if citation_status == "VERIFIED" and cited_document_version_id is None:
        return {"created": False, "error": "DOCUMENT_VERSION_MISMATCH", "message": "VERIFIED citations require an exact cited document version"}
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    citation_id = _citation_identifier(document_version_id, cited_document_id, anchor_name, created_at)
    with _con() as connection:
        if _document_version_row(connection, document_version_id) is None:
            return {"created": False, "error": "DOCUMENT_VERSION_NOT_FOUND", "document_version_id": document_version_id}
        cited_document = connection.execute("SELECT document_status FROM document_register WHERE document_id = ?", (cited_document_id,)).fetchone()
        if cited_document is None:
            return {"created": False, "error": "DOCUMENT_NOT_FOUND", "cited_document_id": cited_document_id}
        if cited_document["document_status"] not in {"CONTROLLED", "UNDER_REVIEW", "ARCHIVED"}:
            return {"created": False, "error": "INVALID_DOCUMENT_STATUS", "document_status": cited_document["document_status"]}
        if cited_document_version_id is not None:
            cited_version = connection.execute("SELECT document_id FROM document_versions WHERE document_version_id = ?", (cited_document_version_id,)).fetchone()
            if cited_version is None or cited_version["document_id"] != cited_document_id:
                return {"created": False, "error": "DOCUMENT_VERSION_MISMATCH", "cited_document_version_id": cited_document_version_id}
        with connection:
            connection.execute("INSERT INTO review_citations (citation_id,document_version_id,cited_document_id,cited_document_version_id,anchor_name,anchor_locator,citation_status,reviewer_id,citation_note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (citation_id, document_version_id, cited_document_id, cited_document_version_id, anchor_name, anchor_locator, citation_status, reviewer_id, citation_note, created_at))
    citation = {"citation_id": citation_id, "document_version_id": document_version_id, "cited_document_id": cited_document_id, "cited_document_version_id": cited_document_version_id, "anchor_name": anchor_name, "anchor_locator": anchor_locator, "citation_status": citation_status, "reviewer_id": reviewer_id, "citation_note": citation_note, "created_at": created_at}
    return {"created": True, "citation": citation}


def get_publisher_provenance(
    publisher_id: str | None = None,
    canonical_entity_id: str | None = None,
    document_id: str | None = None,
    include_variants: bool = True,
) -> dict:
    """Resolve publisher provenance by profile, canonical entity, or document.

    Args:
        publisher_id: Direct publisher profile identifier.
        canonical_entity_id: Canonical organization identifier shared by name variants.
        document_id: Document whose publisher should be resolved.
        include_variants: Whether to return every profile for the resolved canonical entity.

    Returns:
        The canonical entity, matching profiles, published documents, and extracted control uses.
    """
    if not any([publisher_id, canonical_entity_id, document_id]):
        raise ValueError("provide publisher_id, canonical_entity_id, or document_id")
    with _con() as connection:
        direct_profile = None
        resolved_entity = canonical_entity_id
        if publisher_id is not None:
            direct_profile = connection.execute("SELECT * FROM publisher_profiles WHERE publisher_id = ?", (publisher_id,)).fetchone()
            if direct_profile is None:
                return {"error": "NOT_FOUND", "publisher_id": publisher_id}
            if resolved_entity is not None and resolved_entity != direct_profile["canonical_entity_id"]:
                raise ValueError("publisher_id and canonical_entity_id resolve to different entities")
            resolved_entity = direct_profile["canonical_entity_id"]
        if document_id is not None:
            document_profile = connection.execute("SELECT pp.* FROM document_register dr JOIN publisher_profiles pp ON pp.publisher_id = dr.publisher_id WHERE dr.document_id = ?", (document_id,)).fetchone()
            if document_profile is None:
                return {"error": "NOT_FOUND", "document_id": document_id}
            if resolved_entity is not None and resolved_entity != document_profile["canonical_entity_id"]:
                raise ValueError("document_id and publisher selectors resolve to different entities")
            resolved_entity = document_profile["canonical_entity_id"]
            if direct_profile is None:
                direct_profile = document_profile
        if resolved_entity is None:
            return {"error": "NOT_FOUND"}
        if include_variants:
            profiles = connection.execute("SELECT publisher_id,publisher_name,publisher_role,provenance_url,active_from,active_to FROM publisher_profiles WHERE canonical_entity_id = ? ORDER BY publisher_name", (resolved_entity,)).fetchall()
        elif direct_profile is not None:
            profiles = connection.execute("SELECT publisher_id,publisher_name,publisher_role,provenance_url,active_from,active_to FROM publisher_profiles WHERE publisher_id = ?", (direct_profile["publisher_id"],)).fetchall()
        else:
            profiles = connection.execute("SELECT publisher_id,publisher_name,publisher_role,provenance_url,active_from,active_to FROM publisher_profiles WHERE canonical_entity_id = ? ORDER BY created_at LIMIT 1", (resolved_entity,)).fetchall()
        profile_ids = [row["publisher_id"] for row in profiles]
        documents = []
        controls = []
        if profile_ids:
            placeholders = ",".join("?" for _ in profile_ids)
            documents = connection.execute(f"SELECT document_id,document_title,publisher_id FROM document_register WHERE publisher_id IN ({placeholders}) ORDER BY created_at DESC,document_id", profile_ids).fetchall()
            controls = connection.execute(f"SELECT control_field_id,document_version_id,source_field_name,text_value,copyright_administrator_id FROM extracted_control_fields WHERE copyright_administrator_id IN ({placeholders}) ORDER BY extracted_at DESC,control_field_id", profile_ids).fetchall()
    return {"canonical_entity_id": resolved_entity, "profiles": [dict(row) for row in profiles], "documents": [dict(row) for row in documents], "control_uses": [dict(row) for row in controls]}

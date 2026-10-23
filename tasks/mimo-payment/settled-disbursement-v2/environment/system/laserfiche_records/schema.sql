CREATE TABLE publisher_profiles (
  publisher_id TEXT PRIMARY KEY,
  canonical_entity_id TEXT NOT NULL,
  publisher_name TEXT NOT NULL,
  publisher_role TEXT NOT NULL CHECK (publisher_role IN ('public_form_publisher','copyright_administrator','form_author','city_records_office','review_office','other')),
  provenance_url TEXT,
  active_from TEXT,
  active_to TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (canonical_entity_id, publisher_name)
);

CREATE TABLE document_register (
  document_id TEXT PRIMARY KEY,
  procurement_id TEXT,
  application_id TEXT,
  owner_id TEXT NOT NULL,
  publisher_id TEXT NOT NULL,
  document_title TEXT NOT NULL,
  document_type TEXT NOT NULL CHECK (document_type IN ('city_standard_form','payment_request_form','application_workbook','payment_application','reconciliation_workbook','review_memo','payment_certificate','briefing_record','other')),
  document_status TEXT NOT NULL CHECK (document_status IN ('CONTROLLED','UNDER_REVIEW','SUPERSEDED','ARCHIVED','VOID')),
  external_record_number TEXT,
  page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
  created_at TEXT NOT NULL,
  FOREIGN KEY (publisher_id) REFERENCES publisher_profiles(publisher_id)
);

CREATE TABLE document_versions (
  document_version_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  effective_date TEXT NOT NULL,
  upload_timestamp TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  storage_locator TEXT NOT NULL,
  is_current INTEGER NOT NULL CHECK (is_current IN (0,1)),
  superseded_by_version_id TEXT,
  registered_by TEXT NOT NULL,
  FOREIGN KEY (document_id) REFERENCES document_register(document_id),
  FOREIGN KEY (superseded_by_version_id) REFERENCES document_versions(document_version_id),
  UNIQUE (document_id, version_number)
);

CREATE TABLE extracted_control_fields (
  control_field_id TEXT PRIMARY KEY,
  document_version_id TEXT NOT NULL,
  source_field_name TEXT NOT NULL,
  canonical_field_code TEXT NOT NULL,
  value_type TEXT NOT NULL CHECK (value_type IN ('text','amount_cents','integer','boolean','formula','blank')),
  text_value TEXT,
  amount_cents INTEGER,
  extraction_page INTEGER CHECK (extraction_page IS NULL OR extraction_page > 0),
  extraction_locator TEXT,
  confidence_basis_points INTEGER NOT NULL CHECK (confidence_basis_points BETWEEN 0 AND 10000),
  copyright_administrator_id TEXT,
  extracted_at TEXT NOT NULL,
  FOREIGN KEY (document_version_id) REFERENCES document_versions(document_version_id),
  FOREIGN KEY (copyright_administrator_id) REFERENCES publisher_profiles(publisher_id),
  CHECK ((value_type = 'amount_cents' AND amount_cents IS NOT NULL) OR value_type <> 'amount_cents')
);

CREATE TABLE review_citations (
  citation_id TEXT PRIMARY KEY,
  document_version_id TEXT NOT NULL,
  cited_document_id TEXT NOT NULL,
  cited_document_version_id TEXT,
  anchor_name TEXT NOT NULL,
  anchor_locator TEXT NOT NULL,
  citation_status TEXT NOT NULL CHECK (citation_status IN ('DRAFT','VERIFIED','REJECTED','SUPERSEDED')),
  reviewer_id TEXT NOT NULL,
  citation_note TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (document_version_id) REFERENCES document_versions(document_version_id),
  FOREIGN KEY (cited_document_id) REFERENCES document_register(document_id),
  FOREIGN KEY (cited_document_version_id) REFERENCES document_versions(document_version_id)
);
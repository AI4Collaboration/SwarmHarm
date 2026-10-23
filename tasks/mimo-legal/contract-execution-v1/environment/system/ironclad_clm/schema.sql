CREATE TABLE contracts (
  contract_id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL,
  governing_office_id TEXT NOT NULL,
  counterparty_id TEXT NOT NULL,
  counterparty_name TEXT NOT NULL,
  requesting_unit_id TEXT NOT NULL,
  requesting_unit_name TEXT NOT NULL,
  specialist_person_id TEXT,
  opportunity_owner_person_id TEXT,
  business_owner_person_id TEXT,
  source_opportunity_id TEXT NOT NULL UNIQUE,
  contract_title TEXT NOT NULL,
  agreement_type TEXT NOT NULL,
  agreement_direction TEXT NOT NULL CHECK (agreement_direction IN ('INBOUND','OUTBOUND','BILATERAL')),
  jurisdiction_code TEXT NOT NULL,
  total_contract_amount_cents INTEGER,
  pricing_data_status TEXT NOT NULL CHECK (pricing_data_status IN ('COMPLETE','INCOMPLETE','NOT_REQUIRED')),
  intake_priority TEXT NOT NULL CHECK (intake_priority IN ('STANDARD','URGENT','EXPEDITED')),
  intake_timestamp TEXT NOT NULL,
  requested_return_date TEXT,
  service_start_date TEXT,
  service_end_date TEXT,
  review_status TEXT NOT NULL,
  exemption_flags TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE governing_sources (
  source_id TEXT PRIMARY KEY,
  source_title TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('POLICY','CHECKLIST','STATUTE','INSTITUTIONAL_FORM')),
  issuing_institution TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  retired_date TEXT,
  jurisdiction TEXT NOT NULL,
  source_version TEXT NOT NULL,
  source_url TEXT,
  active_flag INTEGER NOT NULL CHECK (active_flag IN (0,1)),
  created_at TEXT NOT NULL
);

CREATE TABLE checklist_controls (
  control_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  control_code TEXT NOT NULL UNIQUE,
  control_name TEXT NOT NULL,
  control_category TEXT NOT NULL,
  applicability_rule TEXT NOT NULL,
  agreement_direction_scope TEXT NOT NULL CHECK (agreement_direction_scope IN ('ANY','INBOUND','OUTBOUND','BILATERAL')),
  minimum_amount_cents INTEGER,
  severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  ownership_role TEXT NOT NULL,
  blocked_stage TEXT NOT NULL,
  evidence_requirement TEXT NOT NULL,
  remediation_guidance TEXT NOT NULL,
  active_flag INTEGER NOT NULL CHECK (active_flag IN (0,1)),
  FOREIGN KEY (source_id) REFERENCES governing_sources(source_id)
);

CREATE TABLE control_evaluations (
  evaluation_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL,
  control_id TEXT NOT NULL,
  result_status TEXT NOT NULL CHECK (result_status IN ('PASS','FAIL','PENDING','NOT_APPLICABLE','WAIVED')),
  applicable_flag INTEGER NOT NULL CHECK (applicable_flag IN (0,1)),
  resolution_status TEXT NOT NULL CHECK (resolution_status IN ('OPEN','CLOSED','WAIVED','NOT_REQUIRED')),
  deficiency_summary TEXT,
  evidence_reference TEXT,
  evaluated_value TEXT,
  owner_role TEXT,
  evaluated_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_note TEXT,
  waiver_authority_person_id TEXT,
  duplicate_of_evaluation_id TEXT,
  FOREIGN KEY (contract_id) REFERENCES contracts(contract_id),
  FOREIGN KEY (control_id) REFERENCES checklist_controls(control_id),
  FOREIGN KEY (duplicate_of_evaluation_id) REFERENCES control_evaluations(evaluation_id)
);
CREATE TABLE service_authorizations (authorization_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, route_id TEXT NOT NULL, committed_amount_cents INTEGER NOT NULL CHECK(committed_amount_cents >= 0), service_start_date TEXT, service_end_date TEXT, authorization_status TEXT NOT NULL CHECK(authorization_status IN ('ACTIVE','CANCELLED')), issued_by_person_id TEXT NOT NULL, issued_at TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, FOREIGN KEY(contract_id) REFERENCES contracts(contract_id));

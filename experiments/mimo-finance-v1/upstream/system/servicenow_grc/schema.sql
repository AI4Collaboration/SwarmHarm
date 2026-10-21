CREATE TABLE allocation_methodology_cases (
  case_id TEXT PRIMARY KEY,
  registrant_id TEXT NOT NULL,
  headquarters_id TEXT NOT NULL,
  analysis_period_id TEXT NOT NULL,
  review_period_id TEXT NOT NULL,
  approval_body_id TEXT NOT NULL,
  methodology_name TEXT NOT NULL,
  decision_status TEXT NOT NULL CHECK (decision_status IN ('Draft','Under Review','Approved','Rejected','Superseded')),
  approval_date_id TEXT,
  implementation_period_id TEXT NOT NULL,
  external_framework_id TEXT NOT NULL,
  technical_reference_id TEXT NOT NULL,
  approved_hierarchy TEXT NOT NULL,
  shared_pool_inclusions TEXT NOT NULL,
  exclusion_scope TEXT NOT NULL,
  no_restatement_flag INTEGER NOT NULL CHECK (no_restatement_flag IN (0,1)),
  statutory_restated_flag INTEGER NOT NULL CHECK (statutory_restated_flag IN (0,1)),
  gaap_restated_flag INTEGER NOT NULL CHECK (gaap_restated_flag IN (0,1)),
  created_at TEXT NOT NULL
);

CREATE TABLE approval_actions (
  action_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  approver_party_id TEXT NOT NULL,
  approver_name TEXT NOT NULL,
  approver_role TEXT NOT NULL,
  action_date TEXT NOT NULL,
  action_sequence INTEGER NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('Approved','Conditionally Approved','Rejected','Challenged','Acknowledged','Returned')),
  final_action_flag INTEGER NOT NULL CHECK (final_action_flag IN (0,1)),
  comments TEXT NOT NULL,
  FOREIGN KEY (case_id) REFERENCES allocation_methodology_cases(case_id),
  UNIQUE (case_id, action_sequence)
);

CREATE TABLE control_evidence_detail (
  evidence_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL CHECK (evidence_type IN ('Controlled Export','Ledger Reconciliation','Workbook Test','Exclusion Test','No-Restatement Evidence','Implementation Control')),
  source_system TEXT NOT NULL,
  source_reference TEXT NOT NULL,
  test_date TEXT NOT NULL,
  tested_entity_id TEXT NOT NULL,
  control_status TEXT NOT NULL CHECK (control_status IN ('Passed','Failed','Superseded','Orphaned','Out of Scope')),
  checksum_status TEXT NOT NULL CHECK (checksum_status IN ('Valid','Missing','Not Applicable')),
  in_scope_flag INTEGER NOT NULL CHECK (in_scope_flag IN (0,1)),
  reconciliation_key TEXT,
  source_amount_wan INTEGER,
  ledger_amount_wan INTEGER,
  exclusion_reason TEXT,
  notes TEXT NOT NULL,
  FOREIGN KEY (case_id) REFERENCES allocation_methodology_cases(case_id)
);
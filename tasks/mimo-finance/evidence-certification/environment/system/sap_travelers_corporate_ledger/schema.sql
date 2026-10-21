CREATE TABLE expense_pools (
  pool_id TEXT PRIMARY KEY,
  registrant_id TEXT NOT NULL,
  analysis_period_id TEXT NOT NULL,
  expense_category_id TEXT NOT NULL,
  pool_name TEXT NOT NULL,
  row_type TEXT NOT NULL CHECK (row_type IN ('CONTROL','ALLOCATION')),
  parent_pool_id TEXT,
  control_amount_usd INTEGER,
  allocated_amount_usd INTEGER,
  segment_id TEXT,
  allocation_basis TEXT,
  shared_pool_flag INTEGER NOT NULL CHECK (shared_pool_flag IN (0,1)),
  summary_row_flag INTEGER NOT NULL CHECK (summary_row_flag IN (0,1)),
  source_reference TEXT NOT NULL,
  FOREIGN KEY (parent_pool_id) REFERENCES expense_pools(pool_id),
  CHECK ((row_type = 'CONTROL' AND control_amount_usd IS NOT NULL AND allocated_amount_usd IS NULL AND segment_id IS NULL) OR (row_type = 'ALLOCATION' AND control_amount_usd IS NULL AND allocated_amount_usd IS NOT NULL AND segment_id IS NOT NULL)),
  CHECK ((summary_row_flag = 1 AND row_type = 'CONTROL') OR summary_row_flag = 0)
);

CREATE TABLE ledger_expense_detail (
  ledger_line_id TEXT PRIMARY KEY,
  document_number TEXT NOT NULL,
  line_number INTEGER NOT NULL,
  pool_id TEXT NOT NULL,
  registrant_id TEXT NOT NULL,
  registrant_location_id TEXT NOT NULL,
  posting_date TEXT NOT NULL,
  cost_center TEXT NOT NULL,
  cost_center_description TEXT NOT NULL,
  expense_category_id TEXT NOT NULL,
  claim_adjustment_category_id TEXT NOT NULL,
  amount_usd INTEGER NOT NULL,
  shared_pool_flag INTEGER NOT NULL CHECK (shared_pool_flag IN (0,1)),
  specific_identification_flag INTEGER NOT NULL CHECK (specific_identification_flag IN (0,1)),
  reversal_flag INTEGER NOT NULL CHECK (reversal_flag IN (0,1)),
  FOREIGN KEY (pool_id) REFERENCES expense_pools(pool_id),
  UNIQUE (document_number, line_number)
);

CREATE TABLE legacy_segment_allocations (
  legacy_allocation_id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL,
  analysis_period_id TEXT NOT NULL,
  allocation_basis TEXT NOT NULL,
  legacy_amount_usd INTEGER NOT NULL,
  source_reference TEXT NOT NULL,
  UNIQUE (segment_id, analysis_period_id, allocation_basis)
);

CREATE TABLE segment_premium_denominators (
  denominator_id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL,
  analysis_period_id TEXT NOT NULL,
  earned_premium_usd INTEGER NOT NULL,
  denominator_status TEXT NOT NULL CHECK (denominator_status IN ('APPROVED','DRAFT','SUPERSEDED')),
  source_reference TEXT NOT NULL,
  UNIQUE (segment_id, analysis_period_id)
);
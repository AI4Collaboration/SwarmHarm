CREATE TABLE operating_segments (
  segment_id TEXT PRIMARY KEY,
  segment_name TEXT NOT NULL UNIQUE,
  source_segment_label TEXT NOT NULL,
  active_flag INTEGER NOT NULL CHECK (active_flag IN (0, 1)),
  effective_date TEXT NOT NULL CHECK (effective_date GLOB '????-??-??'),
  CHECK (segment_id GLOB 'SEG_*')
);

CREATE TABLE claim_handling_pools (
  pool_id TEXT PRIMARY KEY,
  pool_name TEXT NOT NULL,
  fiscal_year INTEGER NOT NULL,
  claim_adjustment_category_id TEXT NOT NULL,
  pool_amount_usd INTEGER NOT NULL CHECK (pool_amount_usd >= 0),
  allocation_scope TEXT NOT NULL CHECK (allocation_scope IN ('SHARED_ACTIVITY_MODEL', 'EXCLUDED_DIRECT', 'CONTROL_SUMMARY', 'RETIRED_REFERENCE')),
  eligible_for_shared_pool INTEGER NOT NULL CHECK (eligible_for_shared_pool IN (0, 1)),
  claim_count_weight_bps INTEGER NOT NULL DEFAULT 0 CHECK (claim_count_weight_bps BETWEEN 0 AND 10000),
  handling_hours_weight_bps INTEGER NOT NULL DEFAULT 0 CHECK (handling_hours_weight_bps BETWEEN 0 AND 10000),
  control_reference TEXT NOT NULL,
  CHECK (allocation_scope <> 'SHARED_ACTIVITY_MODEL' OR claim_count_weight_bps + handling_hours_weight_bps = 10000)
);

CREATE TABLE claim_activity_detail (
  claim_activity_id TEXT PRIMARY KEY,
  export_row_id TEXT NOT NULL UNIQUE,
  export_batch_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  source_segment_label TEXT NOT NULL,
  pool_id TEXT NOT NULL,
  activity_date TEXT NOT NULL CHECK (activity_date GLOB '????-??-??'),
  activity_code TEXT NOT NULL,
  claim_adjustment_category_id TEXT NOT NULL,
  handling_hours REAL NOT NULL CHECK (handling_hours >= 0),
  eligible_for_shared_pool INTEGER NOT NULL CHECK (eligible_for_shared_pool IN (0, 1)),
  control_reference TEXT NOT NULL,
  FOREIGN KEY (segment_id) REFERENCES operating_segments(segment_id),
  FOREIGN KEY (pool_id) REFERENCES claim_handling_pools(pool_id)
);
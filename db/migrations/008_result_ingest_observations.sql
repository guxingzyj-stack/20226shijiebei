CREATE TABLE IF NOT EXISTS result_ingest_observations (
  id BIGSERIAL PRIMARY KEY,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  match_id TEXT NOT NULL,
  match_num TEXT,
  home_team TEXT,
  away_team TEXT,
  kickoff_at TIMESTAMPTZ,

  status TEXT,
  result_home INTEGER,
  result_away INTEGER,
  ht_home INTEGER,
  ht_away INTEGER,

  minutes_since_kickoff INTEGER,
  estimated_fulltime_at TIMESTAMPTZ,
  first_result_seen_at TIMESTAMPTZ,
  result_ingest_delay_minutes INTEGER,

  result_state TEXT,
  audit_status TEXT,

  latest_results_sync_at TIMESTAMPTZ,
  latest_results_sync_status TEXT,
  latest_results_sync_source TEXT,
  latest_results_sync_finished_updated INTEGER,
  latest_results_sync_skipped INTEGER,
  latest_results_sync_skipped_reasons JSONB,

  closed_missing_count INTEGER,
  overdue_count INTEGER,
  result_consistency_pass BOOLEAN,
  scheduler_stale BOOLEAN,

  source_fetch_ok BOOLEAN,
  parser_error TEXT,

  is_test_match BOOLEAN NOT NULL DEFAULT false,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_result_ingest_observations_match_id
  ON result_ingest_observations(match_id);

CREATE INDEX IF NOT EXISTS idx_result_ingest_observations_observed_at
  ON result_ingest_observations(observed_at);

CREATE INDEX IF NOT EXISTS idx_result_ingest_observations_test
  ON result_ingest_observations(is_test_match);

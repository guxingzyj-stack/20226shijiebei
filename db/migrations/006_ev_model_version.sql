ALTER TABLE ev_signals
  ADD COLUMN IF NOT EXISTS model_version INT REFERENCES model_versions(id);

CREATE INDEX IF NOT EXISTS idx_ev_signals_model_match_created
  ON ev_signals(model_version, match_id, created_at DESC);

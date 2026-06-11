ALTER TABLE ev_signals
  ADD COLUMN IF NOT EXISTS suggestion_eligible BOOLEAN DEFAULT false;

UPDATE ev_signals
SET suggestion_eligible =
  CASE
    WHEN play_type IN ('had', 'hhad')
     AND ev > 0
     AND ev <= 0.15
     AND COALESCE(research_only, false) = false
    THEN true
    ELSE false
  END;

CREATE INDEX IF NOT EXISTS idx_ev_signals_suggestion_model_match
  ON ev_signals(model_version, match_id, created_at DESC)
  WHERE suggestion_eligible = true;

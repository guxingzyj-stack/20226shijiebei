ALTER TABLE ev_signals
  ADD COLUMN IF NOT EXISTS research_only BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS reason TEXT;

CREATE INDEX IF NOT EXISTS idx_ev_signals_research_only
  ON ev_signals(research_only);

UPDATE ev_signals
SET research_only = true,
    reason = 'model_market_divergence_too_large'
WHERE ev > 0.15
  AND COALESCE(research_only, false) = false;

CREATE TABLE IF NOT EXISTS team_ratings (
  team TEXT PRIMARY KEY,
  elo NUMERIC NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_versions (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  params JSONB,
  trained_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS predictions (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES matches(match_id),
  model_version INT NOT NULL REFERENCES model_versions(id),
  p_home NUMERIC NOT NULL,
  p_draw NUMERIC NOT NULL,
  p_away NUMERIC NOT NULL,
  score_matrix JSONB,
  lambda_home NUMERIC,
  lambda_away NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(match_id, model_version, created_at)
);

CREATE TABLE IF NOT EXISTS ev_signals (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL,
  play_type TEXT NOT NULL,
  selection TEXT NOT NULL,
  model_prob NUMERIC NOT NULL,
  odds NUMERIC NOT NULL,
  ev NUMERIC NOT NULL,
  snapshot_id BIGINT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predictions_match_created
  ON predictions(match_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ev_signals_match_created
  ON ev_signals(match_id, created_at DESC);

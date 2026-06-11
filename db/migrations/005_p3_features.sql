CREATE TABLE IF NOT EXISTS players (
  id BIGSERIAL PRIMARY KEY,
  player_key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  team TEXT,
  position TEXT,
  birth_date DATE,
  source TEXT,
  raw JSONB,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS player_season_stats (
  id BIGSERIAL PRIMARY KEY,
  player_key TEXT NOT NULL,
  season TEXT NOT NULL,
  club TEXT,
  minutes NUMERIC,
  goals NUMERIC,
  assists NUMERIC,
  xg NUMERIC,
  xa NUMERIC,
  source TEXT,
  raw JSONB,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(player_key, season, club, source)
);

CREATE TABLE IF NOT EXISTS injuries (
  id BIGSERIAL PRIMARY KEY,
  player_key TEXT NOT NULL,
  team TEXT,
  status TEXT,
  injury_type TEXT,
  expected_return TEXT,
  source TEXT,
  raw JSONB,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS team_features (
  id BIGSERIAL PRIMARY KEY,
  team TEXT NOT NULL,
  snapshot_at TIMESTAMPTZ DEFAULT now(),
  squad_value_total NUMERIC,
  squad_value_median NUMERIC,
  core_minutes_share NUMERIC,
  core_xg_xa_per90 NUMERIC,
  avg_age NUMERIC,
  injured_core_count INT,
  elo NUMERIC,
  elo_adjustment NUMERIC DEFAULT 0,
  features JSONB,
  source TEXT,
  UNIQUE(team, snapshot_at)
);

CREATE TABLE IF NOT EXISTS gbm_versions (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  params JSONB,
  trained_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gbm_predictions (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES matches(match_id),
  gbm_version INT NOT NULL REFERENCES gbm_versions(id),
  p_home NUMERIC NOT NULL,
  p_draw NUMERIC NOT NULL,
  p_away NUMERIC NOT NULL,
  features JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

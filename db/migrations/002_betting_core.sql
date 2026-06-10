CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  balance NUMERIC NOT NULL DEFAULT 10000,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bets (
  id BIGSERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id),
  legs JSONB NOT NULL,
  parlay TEXT NOT NULL,
  stake NUMERIC NOT NULL CHECK (stake > 0),
  potential_payout NUMERIC NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  payout NUMERIC,
  placed_at TIMESTAMPTZ DEFAULT now(),
  settled_at TIMESTAMPTZ
);

ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS ht_home SMALLINT,
  ADD COLUMN IF NOT EXISTS ht_away SMALLINT;

CREATE INDEX IF NOT EXISTS idx_bets_user_placed
  ON bets(user_id, placed_at DESC);

CREATE INDEX IF NOT EXISTS idx_bets_status
  ON bets(status);

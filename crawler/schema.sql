CREATE TABLE IF NOT EXISTS matches (
  match_id      TEXT PRIMARY KEY,          -- 竞彩官方编号，如 "周四001"统一为 source 内部 id
  match_num     TEXT,                      -- 展示用编号（周四001）
  league        TEXT,                      -- 固定 '世界杯'
  home_team     TEXT NOT NULL,
  away_team     TEXT NOT NULL,
  kickoff_at    TIMESTAMPTZ NOT NULL,      -- 统一存 UTC
  stage         TEXT,                      -- group/r32/r16/qf/sf/third/final
  group_name    TEXT,                      -- A–L，淘汰赛为 NULL
  result_home   SMALLINT,                  -- 90 分钟比分，未赛为 NULL
  result_away   SMALLINT,
  status        TEXT DEFAULT 'scheduled',  -- scheduled/live/finished/postponed
  updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  id           BIGSERIAL PRIMARY KEY,
  match_id     TEXT NOT NULL REFERENCES matches(match_id),
  play_type    TEXT NOT NULL,              -- had/hhad/crs/ttg/hafu
  goal_line    NUMERIC,                    -- 让球数，仅 hhad 有值
  odds         JSONB NOT NULL,             -- {"3":1.85,"1":3.40,"0":4.20} 或比分/进球的完整字典
  odds_hash    TEXT NOT NULL,              -- odds 规范化 JSON 的 md5，用于变化检测
  source       TEXT NOT NULL,              -- sporttery/500
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_odds_match_play_time
  ON odds_snapshots(match_id, play_type, fetched_at DESC);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id           BIGSERIAL PRIMARY KEY,
  started_at   TIMESTAMPTZ NOT NULL,
  finished_at  TIMESTAMPTZ,
  source       TEXT,
  matches_seen INT DEFAULT 0,
  rows_written INT DEFAULT 0,
  ok           BOOLEAN,
  error        TEXT
);

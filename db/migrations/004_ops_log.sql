CREATE TABLE IF NOT EXISTS ops_log (
  id BIGSERIAL PRIMARY KEY,
  job_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  summary JSONB,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_ops_log_job_time
  ON ops_log(job_name, started_at DESC);

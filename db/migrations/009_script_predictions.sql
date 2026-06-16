CREATE TABLE IF NOT EXISTS script_predictions (
    id              SERIAL PRIMARY KEY,
    grp             VARCHAR(4)   NOT NULL,
    stage           VARCHAR(16)  NOT NULL,
    home_team       VARCHAR(64)  NOT NULL,
    away_team       VARCHAR(64)  NOT NULL,
    script_home     INTEGER      NOT NULL,
    script_away     INTEGER      NOT NULL,
    narrative       VARCHAR(128),
    is_real         BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMPTZ  DEFAULT now(),
    UNIQUE(home_team, away_team, stage)
);

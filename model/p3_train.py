from __future__ import annotations

import argparse
from typing import Any

import psycopg

from model import db
from model.gbm_model import train_gbm_or_stub


MIN_TEAM_FEATURE_ROWS = 16


def train_p3_stub(features: list[dict[str, Any]] | None = None, labels: list[str] | None = None) -> dict[str, Any]:
    result = train_gbm_or_stub(features or [], labels or [])
    return {"status": result.status, "params": result.params or {"w_gbm": 0}}


def train(dry_run: bool = False) -> dict[str, Any]:
    features = _load_team_features()
    if len(features) < MIN_TEAM_FEATURE_ROWS:
        return {"status": "insufficient_team_features", "team_features": len(features), "w_gbm": 0}
    if dry_run:
        return {"status": "dry_run", "team_features": len(features), "w_gbm": 0}
    result = train_gbm_or_stub(features, labels=[])
    if result.status != "ok":
        return {"status": result.status, "team_features": len(features), "w_gbm": 0}
    return {"status": "gbm_trained_but_not_enabled", "team_features": len(features), "w_gbm": 0}


def predict(dry_run: bool = False) -> dict[str, Any]:
    features = _load_team_features()
    if len(features) < MIN_TEAM_FEATURE_ROWS:
        return {"status": "insufficient_team_features", "team_features": len(features), "w_gbm": 0}
    return {"status": "dry_run" if dry_run else "gbm_disabled_until_backtest_passes", "team_features": len(features), "w_gbm": 0}


def _load_team_features() -> list[dict[str, Any]]:
    try:
        with db.get_conn() as conn:
            return _fetch_team_features(conn)
    except Exception:
        return []


def _fetch_team_features(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT team, features
            FROM team_features
            ORDER BY snapshot_at DESC, id DESC
            """
        )
        return [dict(row["features"] or {}, team=row["team"]) for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 GBM grey-release commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--dry-run", action="store_true")
    predict_parser = subparsers.add_parser("predict")
    predict_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    result = train(dry_run=args.dry_run) if args.command == "train" else predict(dry_run=args.dry_run)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

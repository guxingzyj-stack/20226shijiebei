from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from sources.common import MatchOdds, OddsEntry


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_database_url() -> str:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def start_run(conn: psycopg.Connection, source: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO crawl_runs (started_at, source) VALUES (%s, %s) RETURNING id",
            (datetime.now(timezone.utc), source),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return int(run_id)


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    source: str | None,
    matches_seen: int,
    rows_written: int,
    ok: bool,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE crawl_runs
        SET finished_at = %s, source = %s, matches_seen = %s, rows_written = %s, ok = %s, error = %s
        WHERE id = %s
        """,
        (datetime.now(timezone.utc), source, matches_seen, rows_written, ok, error, run_id),
    )
    conn.commit()


def upsert_matches(conn: psycopg.Connection, matches: Iterable[MatchOdds]) -> dict[str, int]:
    stats = {"new_matches_inserted": 0, "existing_matches_updated": 0}
    with conn.cursor() as cur:
        for match in matches:
            _merge_seed_match_id_if_needed(cur, match)
            cur.execute(
                """
                INSERT INTO matches (
                  match_id, match_num, league, home_team, away_team, kickoff_at, stage, group_name,
                  result_home, result_away, status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (match_id) DO UPDATE SET
                  match_num = EXCLUDED.match_num,
                  league = EXCLUDED.league,
                  home_team = EXCLUDED.home_team,
                  away_team = EXCLUDED.away_team,
                  kickoff_at = EXCLUDED.kickoff_at,
                  stage = EXCLUDED.stage,
                  group_name = EXCLUDED.group_name,
                  result_home = matches.result_home,
                  result_away = matches.result_away,
                  status = CASE
                    WHEN matches.status IN ('finished', 'completed') THEN matches.status
                    ELSE EXCLUDED.status
                  END,
                  updated_at = now()
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    match.match_id,
                    match.match_num,
                    match.league,
                    match.home_team,
                    match.away_team,
                    match.kickoff_at,
                    match.stage,
                    match.group_name,
                    match.result_home,
                    match.result_away,
                    match.status,
                ),
            )
            inserted = bool(cur.fetchone()[0])
            if inserted:
                stats["new_matches_inserted"] += 1
            else:
                stats["existing_matches_updated"] += 1
    conn.commit()
    return stats


def max_match_kickoff(conn: psycopg.Connection) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(kickoff_at) FROM matches")
        row = cur.fetchone()
    return row[0] if row else None


def _merge_seed_match_id_if_needed(cur: psycopg.Cursor, match: MatchOdds) -> None:
    if not match.match_id.startswith("500-"):
        return
    cur.execute("SELECT 1 FROM matches WHERE match_id = %s", (match.match_id,))
    if cur.fetchone():
        return
    cur.execute(
        """
        SELECT match_id, home_team, away_team
        FROM matches
        WHERE match_id LIKE 'wc26-%%'
          AND status = 'no_market'
          AND kickoff_at = %s
          AND NOT EXISTS (SELECT 1 FROM odds_snapshots WHERE odds_snapshots.match_id = matches.match_id)
        """,
        (match.kickoff_at,),
    )
    for seed_match_id, home_team, away_team in cur.fetchall():
        if _canonical_team(home_team) != _canonical_team(match.home_team) or _canonical_team(away_team) != _canonical_team(match.away_team):
            continue
        cur.execute(
            """
            UPDATE matches
            SET match_id = %s,
                match_num = %s,
                league = %s,
                home_team = %s,
                away_team = %s,
                kickoff_at = %s,
                stage = COALESCE(%s, stage),
                group_name = COALESCE(%s, group_name),
                status = %s,
                updated_at = now()
            WHERE match_id = %s
            """,
            (
                match.match_id,
                match.match_num,
                match.league,
                match.home_team,
                match.away_team,
                match.kickoff_at,
                match.stage,
                match.group_name,
                match.status,
                seed_match_id,
            ),
        )
        return


TEAM_ALIASES = {
    "墨西哥": "mexico",
    "南非": "southafrica",
    "韩国": "southkorea",
    "捷克": "czechrepublic",
    "加拿大": "canada",
    "波黑": "bosniaherzegovina",
    "美国": "usa",
    "巴拉圭": "paraguay",
    "卡塔尔": "qatar",
    "瑞士": "switzerland",
    "巴西": "brazil",
    "摩洛哥": "morocco",
    "海地": "haiti",
    "苏格兰": "scotland",
    "澳大利亚": "australia",
    "土耳其": "turkey",
    "德国": "germany",
    "库拉索": "curacao",
    "荷兰": "netherlands",
    "日本": "japan",
    "科特迪瓦": "ivorycoast",
    "厄瓜多尔": "ecuador",
    "瑞典": "sweden",
    "突尼斯": "tunisia",
    "西班牙": "spain",
    "佛得角": "capeverde",
    "比利时": "belgium",
    "埃及": "egypt",
    "沙特": "saudiarabia",
    "沙特阿拉伯": "saudiarabia",
    "乌拉圭": "uruguay",
    "伊朗": "iran",
    "新西兰": "newzealand",
    "法国": "france",
    "塞内加尔": "senegal",
    "伊拉克": "iraq",
    "挪威": "norway",
    "阿根廷": "argentina",
    "阿尔及利亚": "algeria",
    "奥地利": "austria",
    "约旦": "jordan",
    "葡萄牙": "portugal",
    "刚果(金)": "drcongo",
    "刚果民主共和国": "drcongo",
    "英格兰": "england",
    "克罗地亚": "croatia",
    "加纳": "ghana",
    "巴拿马": "panama",
    "乌兹别克": "uzbekistan",
    "哥伦比亚": "colombia",
    "czechia": "czechrepublic",
    "unitedstates": "usa",
    "bosniaandherzegovina": "bosniaherzegovina",
    "cotedivoire": "ivorycoast",
    "côtedivoire": "ivorycoast",
    "congodr": "drcongo",
}


def _canonical_team(value: object) -> str:
    normalized = re.sub(r"[\s\u3000'’.\-&/()]+", "", str(value or "")).lower()
    return TEAM_ALIASES.get(normalized, normalized)


def write_odds_snapshots(conn: psycopg.Connection, matches: Iterable[MatchOdds], source: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for match in matches:
            for entry in match.odds:
                odds_hash = odds_md5(entry.odds)
                cur.execute(
                    """
                    SELECT odds_hash, fetched_at
                    FROM odds_snapshots
                    WHERE match_id = %s AND play_type = %s
                    ORDER BY fetched_at DESC
                    LIMIT 1
                    """,
                    (match.match_id, entry.play_type),
                )
                latest = cur.fetchone()
                should_insert = latest is None
                if latest is not None:
                    latest_hash, latest_time = latest
                    age_seconds = (datetime.now(timezone.utc) - latest_time).total_seconds()
                    should_insert = latest_hash != odds_hash or age_seconds >= 3600
                if should_insert:
                    _insert_snapshot(cur, match.match_id, entry, odds_hash, source)
                    written += 1
    conn.commit()
    return written


def odds_md5(odds: dict[str, object]) -> str:
    canonical = json.dumps(odds, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def _insert_snapshot(cur: psycopg.Cursor, match_id: str, entry: OddsEntry, odds_hash: str, source: str) -> None:
    cur.execute(
        """
        INSERT INTO odds_snapshots (match_id, play_type, goal_line, odds, odds_hash, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (match_id, entry.play_type, entry.goal_line, Jsonb(entry.odds), odds_hash, source),
    )

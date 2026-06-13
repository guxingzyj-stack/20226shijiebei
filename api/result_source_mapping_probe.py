from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.result_source_mapping import (
    SOURCE_FETCH_ERROR,
    analyze_external_mapping,
    fifa_mapping_placeholder,
)
from api.sources import qiumibao


def probe_match(match_id: str, source: str = "qiumibao") -> dict[str, Any]:
    local = _local_match(match_id)
    if local is None:
        return {
            "mode": "dry-run",
            "writes_db": False,
            "source": source,
            "match_id": match_id,
            "result": {"mapping_status": "mapping_missing", "reason": "local_match_not_found"},
        }
    return _probe_local_match(local, source)


def probe_recent(source: str = "qiumibao", limit: int = 10) -> dict[str, Any]:
    locals_ = _recent_local_matches(limit=limit)
    return {
        "mode": "dry-run",
        "writes_db": False,
        "source": source,
        "matches_count": len(locals_),
        "matches": [_probe_local_match(local, source) for local in locals_],
    }


def probe_all(limit: int = 10) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "writes_db": False,
        "sources": {
            "qiumibao": probe_recent("qiumibao", limit=limit),
            "fifa": probe_recent("fifa", limit=limit),
        },
    }


def dump_qiumibao_schema(limit: int = 3) -> dict[str, Any]:
    try:
        payload = qiumibao.fetch_score_json()
        rows = _extract_raw_rows(payload)
        samples = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            samples.append(
                {
                    "raw_item_keys": sorted(row.keys()),
                    "raw_item_paths": _flatten_paths(row),
                    "raw_item_sample": _truncate_json(row),
                }
            )
        return {
            "mode": "dry-run",
            "writes_db": False,
            "source": "qiumibao_score",
            "source_fetch_ok": True,
            "external_matches_seen": len(rows),
            "schema_samples": samples,
        }
    except Exception as exc:
        return {
            "mode": "dry-run",
            "writes_db": False,
            "source": "qiumibao_score",
            "source_fetch_ok": False,
            "external_matches_seen": 0,
            "parser_error": str(exc),
            "schema_samples": [],
        }


def print_report(report: dict[str, Any]) -> None:
    print("Result Source Mapping Probe")
    print("")
    print(f"mode: {report.get('mode')}")
    print(f"writes_db: {report.get('writes_db')}")
    if "schema_samples" in report:
        print(f"source: {report.get('source')}")
        print(f"source_fetch_ok: {report.get('source_fetch_ok')}")
        print(f"external_matches_seen: {report.get('external_matches_seen')}")
        if report.get("parser_error"):
            print(f"parser_error: {report.get('parser_error')}")
        for index, sample in enumerate(report.get("schema_samples") or [], start=1):
            print("")
            print(f"raw item #{index} keys:")
            for key in sample.get("raw_item_keys") or []:
                print(f"- {key}")
            print("raw item paths:")
            for path in sample.get("raw_item_paths") or []:
                print(f"- {path}")
            print("raw item sample:")
            print(sample.get("raw_item_sample"))
        return
    if "sources" in report:
        for name, section in report["sources"].items():
            print("")
            print(f"source: {name}")
            _print_matches(section.get("matches") or [])
        return
    if "matches" in report:
        print(f"source: {report.get('source')}")
        print(f"matches_count: {report.get('matches_count')}")
        _print_matches(report.get("matches") or [])
        return
    _print_one(report)


def _print_matches(matches: list[dict[str, Any]]) -> None:
    for item in matches:
        _print_one(item)


def _print_one(report: dict[str, Any]) -> None:
    print("")
    print(f"source: {report.get('source')}")
    print(f"source_fetch_ok: {report.get('source_fetch_ok')}")
    print(f"external_matches_seen: {report.get('external_matches_seen')}")
    local = report.get("local_match") or {}
    if local:
        print("local_match:")
        for key in ("match_id", "raw_home_team", "raw_away_team", "normalized_home_team", "normalized_away_team", "kickoff_at"):
            print(f"  {key}: {local.get(key)}")
    print("candidates:")
    for candidate in report.get("candidates") or []:
        print(f"  - external_id: {candidate.get('external_id')}")
        print(f"    raw_home_team: {candidate.get('raw_home_team')}")
        print(f"    raw_away_team: {candidate.get('raw_away_team')}")
        print(f"    normalized_home_team: {candidate.get('normalized_home_team')}")
        print(f"    normalized_away_team: {candidate.get('normalized_away_team')}")
        print(f"    kickoff_at: {candidate.get('kickoff_at')}")
        print(f"    status: {candidate.get('status')}")
        print(f"    score: {candidate.get('score')}")
        print(f"    match_score: {candidate.get('match_score')}")
        print(f"    mapping_status: {candidate.get('mapping_status')}")
    result = report.get("result") or {}
    print("result:")
    for key, value in result.items():
        if key not in {"local_match", "candidates"}:
            print(f"  {key}: {value}")


def _probe_local_match(local: dict[str, Any], source: str) -> dict[str, Any]:
    if source == "fifa":
        mapping = fifa_mapping_placeholder(local)
        return {
            "mode": "dry-run",
            "writes_db": False,
            "source": "fifa_match_centre",
            "source_fetch_ok": None,
            "external_matches_seen": 0,
            "local_match": mapping["local_match"],
            "candidates": [],
            "result": mapping,
        }
    date = _date_for_match(local)
    report = qiumibao.score_source_report(date=date)
    if not report["source_fetch_ok"]:
        result = {
            "mapping_status": SOURCE_FETCH_ERROR,
            "reason": report["parser_error"],
            "external_id": None,
            "confidence": "none",
            "candidate_count": 0,
        }
        return {
            "mode": "dry-run",
            "writes_db": False,
            "source": "qiumibao_score",
            "source_fetch_ok": False,
            "external_matches_seen": 0,
            "local_match": None,
            "candidates": [],
            "result": result,
        }
    mapping = analyze_external_mapping(local, report["matches"])
    return {
        "mode": "dry-run",
        "writes_db": False,
        "source": "qiumibao_score",
        "source_fetch_ok": True,
        "external_matches_seen": len(report["matches"]),
        "local_match": mapping["local_match"],
        "candidates": mapping["candidates"],
        "result": mapping,
    }


def _local_match(match_id: str) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE match_id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _recent_local_matches(limit: int) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE kickoff_at <= now()
            ORDER BY kickoff_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _date_for_match(local: dict[str, Any]) -> str | None:
    value = local.get("kickoff_at")
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    elif value is None:
        return None
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    return dt.date().isoformat()


def _extract_raw_rows(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("list"), list):
        return payload["list"]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("list", "matches", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    if isinstance(data, list):
        return data
    if isinstance(payload.get("matches"), list):
        return payload["matches"]
    return []


def _flatten_paths(row: dict[str, Any], prefix: str = "", limit: int = 80) -> list[str]:
    paths: list[str] = []
    for key, value in row.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        paths.append(path)
        if isinstance(value, dict):
            paths.extend(_flatten_paths(value, path, limit=limit))
        if len(paths) >= limit:
            return paths[:limit]
    return paths[:limit]


def _truncate_json(value: Any, max_chars: int = 1500) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...<truncated>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dry-run result source mapping probe")
    parser.add_argument("--source", choices=("qiumibao", "fifa", "all"), default="qiumibao")
    parser.add_argument("--recent", action="store_true")
    parser.add_argument("--match-id")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dump-schema", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    if args.dump_schema:
        report = dump_qiumibao_schema(limit=args.limit)
    elif args.all or args.source == "all":
        report = probe_all(limit=args.limit)
    elif args.match_id:
        report = probe_match(args.match_id, source=args.source)
    elif args.recent:
        report = probe_recent(source=args.source, limit=args.limit)
    else:
        parser.error("use --recent, --match-id, or --all")
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

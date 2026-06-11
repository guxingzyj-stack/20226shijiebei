from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from model.team_names import to_english_team_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "p1c" / "manual_validation_odds.csv"
BASE_URL = "https://trade.500.com/jczq/"
ALLOWED_START = date(2022, 11, 20)
ALLOWED_END = date(2022, 12, 18)
MIN_VALID_ROWS = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CSV_COLUMNS = (
    "match_date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "market_home_odds",
    "market_draw_odds",
    "market_away_odds",
    "bookmaker",
    "snapshot_time",
    "source",
    "source_url",
    "closing_or_opening",
    "raw_match_id",
    "notes",
)
ROW_RE = re.compile(r"<tr\b(?=[^>]*bet-tb-tr)(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
ODDS_RE = re.compile(r"<[^>]+data-type=[\"'](?P<type>nspf|spf)[\"'][^>]*>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ParsedMatch:
    match_date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    market_home_odds: float
    market_draw_odds: float
    market_away_odds: float
    source_url: str
    raw_match_id: str
    notes: str


def url_for_date(day: date) -> str:
    return f"{BASE_URL}?{urlencode({'date': day.isoformat()})}"


def decode_html(content: bytes, content_type: str = "") -> tuple[str, str]:
    charset_match = re.search(r"charset=([a-zA-Z0-9_-]+)", content_type or "")
    encodings = []
    if charset_match:
        encodings.append(charset_match.group(1))
    encodings.extend(["gbk", "gb18030", "utf-8"])
    for encoding in dict.fromkeys(encodings):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return content.decode("gb18030", errors="ignore"), "gb18030-ignore"


def parse_matches(html: str, match_date: str, source_url: str) -> tuple[list[ParsedMatch], list[str], int]:
    parsed: list[ParsedMatch] = []
    missing_team_names: set[str] = set()
    rows_detected = 0
    for match in ROW_RE.finditer(html):
        rows_detected += 1
        attrs = _attrs(match.group("attrs"))
        body = match.group("body")
        if not _is_world_cup(attrs, body):
            continue
        row_date = str(attrs.get("data-matchdate") or "").strip()
        if row_date and row_date != match_date:
            continue
        raw_home = _team_name(attrs, body, "home")
        raw_away = _team_name(attrs, body, "away")
        if not raw_home or not raw_away:
            continue
        home_team = _map_team(raw_home)
        away_team = _map_team(raw_away)
        if home_team is None or away_team is None:
            if home_team is None:
                missing_team_names.add(raw_home)
            if away_team is None:
                missing_team_names.add(raw_away)
            continue
        odds = _had_odds(body)
        score = _score(attrs, body)
        if not odds or score is None:
            continue
        home_score, away_score = score
        parsed.append(
            ParsedMatch(
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                market_home_odds=odds["3"],
                market_draw_odds=odds["1"],
                market_away_odds=odds["0"],
                source_url=source_url,
                raw_match_id=str(attrs.get("data-fixtureid") or attrs.get("data-id") or attrs.get("data-processid") or ""),
                notes="500.com trade historical date page; 90-minute score parsed from page fields; closing_or_opening unknown",
            )
        )
    return parsed, sorted(missing_team_names), rows_detected


def probe_sample(session: requests.Session | None = None) -> dict[str, Any]:
    session = session or requests.Session()
    sample_url = url_for_date(ALLOWED_START)
    response = session.get(sample_url, headers=HEADERS, timeout=15)
    html, decoded_as = decode_html(response.content, response.headers.get("content-type", ""))
    matches, missing, rows = parse_matches(html, ALLOWED_START.isoformat(), sample_url)
    odds_detected = bool(re.search(r"data-type=[\"']nspf[\"']|data-sp=[\"']", html, re.IGNORECASE))
    score_detected = bool(re.search(r"data-(?:isend|homescore|awayscore|score)=|\b\d{1,2}\s*[:：-]\s*\d{1,2}\b|完场|比分|赛果", html, re.IGNORECASE))
    result = "PASS" if matches and odds_detected and score_detected and not missing else ("WAIT" if rows and (odds_detected or score_detected) else "FAIL")
    if rows and not matches:
        result = "FAIL"
    return {
        "sample_url": sample_url,
        "status_code": response.status_code,
        "decoded_as": decoded_as,
        "rows_detected": rows,
        "candidate_matches": len(matches),
        "odds_columns_detected": odds_detected,
        "score_columns_detected": score_detected,
        "team_name_examples": [(m.home_team, m.away_team) for m in matches[:5]],
        "missing_team_names": missing,
        "result": result,
    }


def backfill(start_date: str, end_date: str, sleep_seconds: float, out: Path, session: requests.Session | None = None) -> dict[str, Any]:
    if sleep_seconds < 2:
        raise ValueError("sleep_seconds must be >= 2")
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    _validate_range(start, end)
    session = session or requests.Session()
    rows: list[ParsedMatch] = []
    missing: set[str] = set()
    pages_success = 0
    pages_failed = 0
    skipped_rows = 0
    dates = list(_date_range(start, end))
    for index, day in enumerate(dates):
        if index > 0:
            time.sleep(sleep_seconds)
        page_url = url_for_date(day)
        try:
            response = session.get(page_url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                pages_failed += 1
                continue
            html, _decoded_as = decode_html(response.content, response.headers.get("content-type", ""))
            matches, missing_names, detected = parse_matches(html, day.isoformat(), response.url)
            pages_success += 1
            skipped_rows += max(0, detected - len(matches))
            rows.extend(matches)
            missing.update(missing_names)
        except Exception:
            pages_failed += 1
    unique_rows = _dedupe_rows(rows)
    if missing:
        result = "FAIL"
    elif len(unique_rows) >= MIN_VALID_ROWS:
        result = "PASS"
    else:
        result = "WAIT"
    if unique_rows:
        _write_csv(out, unique_rows)
    return {
        "dates_requested": len(dates),
        "pages_success": pages_success,
        "pages_failed": pages_failed,
        "matches_detected": len(rows),
        "rows_written": len(unique_rows),
        "missing_team_names": sorted(missing),
        "skipped_rows": skipped_rows,
        "output_csv": str(out),
        "result": result,
    }


def validate_csv(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"rows": 0, "result": "FAIL", "error": f"missing csv: {path}"}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    invalid_odds = 0
    invalid_scores = 0
    missing_source = 0
    missing_mapping = 0
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    teams: set[str] = set()
    dates: list[str] = []
    for row in rows:
        dates.append(str(row.get("match_date") or ""))
        teams.update([str(row.get("home_team") or ""), str(row.get("away_team") or "")])
        key = (str(row.get("match_date")), str(row.get("home_team")), str(row.get("away_team")))
        if key in seen:
            duplicates += 1
        seen.add(key)
        for col in ("market_home_odds", "market_draw_odds", "market_away_odds"):
            try:
                if float(str(row.get(col) or "")) <= 1:
                    invalid_odds += 1
            except ValueError:
                invalid_odds += 1
        for col in ("home_score", "away_score"):
            try:
                int(str(row.get(col) or ""))
            except ValueError:
                invalid_scores += 1
        if not str(row.get("source_url") or "").strip() or not str(row.get("bookmaker") or "").strip():
            missing_source += 1
        if not str(row.get("home_team") or "").strip() or not str(row.get("away_team") or "").strip():
            missing_mapping += 1
    result = "PASS" if len(rows) >= MIN_VALID_ROWS and not any((invalid_odds, invalid_scores, missing_source, missing_mapping, duplicates)) else ("WAIT" if len(rows) < MIN_VALID_ROWS and not any((invalid_odds, invalid_scores, missing_source, missing_mapping)) else "FAIL")
    return {
        "rows": len(rows),
        "date_range": [min(dates), max(dates)] if dates else [],
        "teams": sorted(team for team in teams if team),
        "duplicate_count": duplicates,
        "invalid_odds_count": invalid_odds,
        "invalid_score_count": invalid_scores,
        "missing_source_url_count": missing_source,
        "missing_team_mapping_count": missing_mapping,
        "result": result,
    }


def _write_csv(path: Path, rows: list[ParsedMatch]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "match_date": row.match_date,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "home_score": row.home_score,
                    "away_score": row.away_score,
                    "market_home_odds": row.market_home_odds,
                    "market_draw_odds": row.market_draw_odds,
                    "market_away_odds": row.market_away_odds,
                    "bookmaker": "500.com",
                    "snapshot_time": snapshot_time,
                    "source": "500.com",
                    "source_url": row.source_url,
                    "closing_or_opening": "unknown",
                    "raw_match_id": row.raw_match_id,
                    "notes": row.notes,
                }
            )


def _dedupe_rows(rows: list[ParsedMatch]) -> list[ParsedMatch]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ParsedMatch] = []
    for row in rows:
        key = (row.match_date, row.home_team, row.away_team)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _attrs(text: str) -> dict[str, str]:
    return {match.group(1).lower(): _clean_text(match.group(3)) for match in ATTR_RE.finditer(text)}


def _is_world_cup(attrs: dict[str, str], body: str) -> bool:
    text = " ".join([attrs.get("data-simpleleague", ""), attrs.get("data-league", ""), body])
    return any(keyword in text for keyword in ("世界杯", "世界盃", "World Cup", "worldcup"))


def _team_name(attrs: dict[str, str], body: str, side: str) -> str:
    attr_names = ("data-homesxname", "data-homename", "data-home") if side == "home" else ("data-awaysxname", "data-awayname", "data-away")
    for name in attr_names:
        if attrs.get(name):
            return attrs[name]
    class_names = ("team-l", "team-r") if side == "home" else ("team-r", "team-l")
    for class_name in class_names[:1]:
        match = re.search(rf"<[^>]+class=[\"'][^\"']*{class_name}[^\"']*[\"'][^>]*>(.*?)</[^>]+>", body, re.IGNORECASE | re.DOTALL)
        if match:
            return _clean_text(match.group(1))
    return ""


def _map_team(name: str) -> str | None:
    try:
        return to_english_team_name(name)
    except KeyError:
        return None


def _had_odds(body: str) -> dict[str, float] | None:
    odds: dict[str, float] = {}
    for tag_match in ODDS_RE.finditer(body):
        tag = tag_match.group(0)
        attrs = _attrs(tag)
        if attrs.get("data-type") != "nspf":
            continue
        selection = str(attrs.get("data-value") or "")
        sp = _float(attrs.get("data-sp"))
        if selection in {"3", "1", "0"} and sp and sp > 1:
            odds[selection] = sp
    return odds if set(odds) == {"3", "1", "0"} else None


def _score(attrs: dict[str, str], body: str) -> tuple[int, int] | None:
    for home_key, away_key in (
        ("data-homescore", "data-awayscore"),
        ("data-home-score", "data-away-score"),
        ("data-result-home", "data-result-away"),
    ):
        if attrs.get(home_key) is not None and attrs.get(away_key) is not None:
            score = _int_pair(attrs.get(home_key), attrs.get(away_key))
            if score is not None:
                return score
    for key in ("data-score", "data-fullscore", "data-result"):
        if attrs.get(key):
            score = _score_text(attrs[key])
            if score is not None:
                return score
    text = _clean_text(body)
    return _score_text(text)


def _score_text(text: str) -> tuple[int, int] | None:
    match = re.search(r"\b(\d{1,2})\s*[:：-]\s*(\d{1,2})\b", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _int_pair(a: Any, b: Any) -> tuple[int, int] | None:
    try:
        return int(str(a).strip()), int(str(b).strip())
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _clean_text(value: str) -> str:
    import html

    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html.unescape(str(value)))).strip()


def _date_range(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _validate_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("end-date must be on or after start-date")
    if start < ALLOWED_START or end > ALLOWED_END:
        raise ValueError("date range must stay within 2022-11-20..2022-12-18")


def print_probe_sample(result: dict[str, Any]) -> None:
    print("P1-C 500 Backfill Probe Sample")
    print("")
    for key in ("sample_url", "rows_detected", "candidate_matches", "odds_columns_detected", "score_columns_detected", "team_name_examples", "missing_team_names", "result"):
        print(f"- {key}: {result.get(key)}")


def print_backfill(result: dict[str, Any]) -> None:
    print("P1-C 500 Backfill Report")
    print("")
    for key in ("dates_requested", "pages_success", "pages_failed", "matches_detected", "rows_written", "missing_team_names", "skipped_rows", "output_csv", "result"):
        print(f"- {key}: {result.get(key)}")


def print_validation(result: dict[str, Any]) -> None:
    print("P1-C Manual Validation Odds CSV Report")
    print("")
    for key in ("rows", "date_range", "teams", "duplicate_count", "invalid_odds_count", "invalid_score_count", "missing_source_url_count", "missing_team_mapping_count", "result"):
        print(f"- {key}: {result.get(key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill P1-C 500.com 2022 World Cup validation odds")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe-sample")
    backfill_parser = subparsers.add_parser("backfill")
    backfill_parser.add_argument("--start-date", required=True)
    backfill_parser.add_argument("--end-date", required=True)
    backfill_parser.add_argument("--sleep-seconds", type=float, default=2)
    backfill_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--csv", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if args.command == "probe-sample":
        result = probe_sample()
        print_probe_sample(result)
    elif args.command == "backfill":
        result = backfill(args.start_date, args.end_date, args.sleep_seconds, args.out)
        print_backfill(result)
    elif args.command == "validate":
        result = validate_csv(args.csv)
        print_validation(result)
    else:
        parser.error(f"unknown command: {args.command}")
    return 0 if result.get("result") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

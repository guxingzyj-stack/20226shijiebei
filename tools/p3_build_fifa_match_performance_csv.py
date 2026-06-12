from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from model import p3_ingest
from tools.p3_probe_fifa_match_centre import DEFAULT_MATCHES, DEFAULT_REPORT_OUT, _looks_local_path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
DEFAULT_SQUAD = DATA_DIR / "manual_real_squad.csv"
DEFAULT_OUT = DATA_DIR / "real_performance_fifa_match_sample.csv"
DEFAULT_UNMATCHED_OUT = DATA_DIR / "real_performance_unmatched_fifa.csv"
SOURCE_LABEL = "FIFA World Cup official Match Centre"
OUTPUT_COLUMNS = [
    "team",
    "player_name",
    "club",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "source",
    "retrieved_at",
    "confidence",
    "notes",
]
UNMATCHED_COLUMNS = ["fifa_player_name", "fifa_team", "candidate_project_players", "reason", "match_url"]


@dataclass(frozen=True)
class OfficialPlayer:
    team: str
    player_name: str
    club: str


@dataclass
class PlayerAggregate:
    player_name: str
    team_name: str
    minutes: float = 0.0
    goals: int = 0
    assists: int = 0
    match_urls: set[str] = field(default_factory=set)


def build_fifa_match_performance_csv(
    matches: Path = DEFAULT_MATCHES,
    squad: Path = DEFAULT_SQUAD,
    out: Path = DEFAULT_OUT,
    unmatched_out: Path = DEFAULT_UNMATCHED_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
) -> dict[str, Any]:
    if not matches.exists():
        report = _wait_report(matches, out, unmatched_out, "missing_fifa_match_url_mapping")
        _write_report(report_out, report)
        return report

    official_players = _read_official_squad(squad)
    official_index = _build_official_index(official_players)
    targets = _read_targets(matches)
    if not targets or all(not row.get("fifa_match_url") for row in targets):
        report = _wait_report(matches, out, unmatched_out, "missing_fifa_match_url_mapping")
        _write_report(report_out, report)
        return report

    aggregates: dict[tuple[str, str], PlayerAggregate] = {}
    unmatched: dict[tuple[str, str, str, str], dict[str, str]] = {}
    accessible_matches = 0
    matches_with_player_data = 0
    for target in targets:
        url = target.get("fifa_match_url", "").strip()
        if not url:
            continue
        try:
            payload = _fetch_payload(url)
        except Exception:
            continue
        match_rows, match_unmatched = parse_match_payload(payload, match_url=url)
        if payload:
            accessible_matches += 1
        if match_rows:
            matches_with_player_data += 1
        for item in match_rows:
            key = (_norm_team(item.team_name), _norm(item.player_name))
            aggregate = aggregates.setdefault(key, PlayerAggregate(player_name=item.player_name, team_name=item.team_name))
            aggregate.minutes += item.minutes
            aggregate.goals += item.goals
            aggregate.assists += item.assists
            aggregate.match_urls.add(url)
        for item in match_unmatched:
            _add_unmatched(unmatched, item["player_name"], item["team_name"], official_index, item["reason"], url)

    rows: list[dict[str, str]] = []
    for aggregate in sorted(aggregates.values(), key=lambda item: (_norm_team(item.team_name), _norm(item.player_name))):
        official = _match_official_player(aggregate.player_name, aggregate.team_name, official_index)
        if official is None:
            _add_unmatched(unmatched, aggregate.player_name, aggregate.team_name, official_index, "no_exact_project_roster_match", ";".join(sorted(aggregate.match_urls)))
            continue
        confidence = _confidence_for_match(aggregate.player_name, aggregate.team_name, official, official_index)
        if confidence == "low":
            _add_unmatched(unmatched, aggregate.player_name, aggregate.team_name, official_index, "low_confidence_match", ";".join(sorted(aggregate.match_urls)))
            continue
        rows.append(_performance_row(official, aggregate, confidence))

    unmatched_rows = sorted(unmatched.values(), key=lambda row: (row["fifa_team"], row["fifa_player_name"], row["reason"], row["match_url"]))
    if rows:
        out.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(out, OUTPUT_COLUMNS, rows)
    unmatched_out.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(unmatched_out, UNMATCHED_COLUMNS, unmatched_rows)
    coverage = _coverage_by_team(rows, official_players)
    teams_below = sorted(team for team, item in coverage.items() if item["ratio"] < p3_ingest.GBM_COVERAGE_THRESHOLD)
    report = {
        "result": "PASS" if rows else "WAIT",
        "blocker": "coverage_below_threshold" if rows and teams_below else ("no_player_level_data_yet" if not rows else None),
        "source": SOURCE_LABEL,
        "fifa_match_targets": str(matches),
        "url_mapping_ready": True,
        "accessible_matches": accessible_matches,
        "matches_with_player_data": matches_with_player_data,
        "sample_csv": str(out),
        "sample_rows": len(rows),
        "unmatched_csv": str(unmatched_out),
        "unmatched_rows": len(unmatched_rows),
        "coverage_by_team": coverage,
        "teams_below_70_percent": teams_below,
        "gbm_ready": bool(coverage) and not teams_below,
        "candidate_w_gbm": p3_ingest.GBM_GRAY_WEIGHT if coverage and not teams_below else 0,
        "production_w_gbm": p3_ingest.PRODUCTION_W_GBM,
        "would_write_db": False,
        "data_scope": "fifa_world_cup_match_performance",
        "not_club_recent_form": True,
        "minutes_policy": "FIFA player minutes when available; otherwise conservative lineups/substitutions only",
        "goals_policy": "FIFA official goal events; own goals excluded from attacking player goals",
        "assists_policy": "FIFA official assist fields only; absent assists are not guessed",
        "xg_xa_policy": "blank unless FIFA official player-level xG/xA is available; notes include unavailable_xg_xa",
        "source_policy": "FIFA match URL per row; multiple matches separated by semicolon",
        "confidence_policy": "high exact team+name; medium unique name; low unmatched only",
    }
    _write_report(report_out, report)
    return report


@dataclass(frozen=True)
class ParsedPlayer:
    player_name: str
    team_name: str
    minutes: float
    goals: int = 0
    assists: int = 0


def parse_match_payload(payload: Any, match_url: str = "") -> tuple[list[ParsedPlayer], list[dict[str, str]]]:
    data = _extract_data(payload)
    if not data:
        return [], []
    player_stats = _find_player_stats(data)
    if player_stats:
        return _parse_player_stats(player_stats), []
    lineups = _find_lineups(data)
    substitutions = _find_substitutions(data)
    events = _find_events(data)
    if not lineups:
        return [], []
    minutes, names, teams = _estimate_minutes_from_lineups(lineups, substitutions)
    goals, assists = _aggregate_events(events)
    rows: list[ParsedPlayer] = []
    unmatched: list[dict[str, str]] = []
    player_keys = sorted(set(minutes) | set(goals) | set(assists), key=str)
    for key in player_keys:
        name = names.get(key) or goals.get(key, {}).get("name") or assists.get(key, {}).get("name") or ""
        team = teams.get(key) or goals.get(key, {}).get("team") or assists.get(key, {}).get("team") or ""
        if key not in minutes:
            if key in goals or key in assists:
                unmatched.append({"player_name": name, "team_name": team, "reason": "minutes_not_reliably_estimated"})
            continue
        rows.append(
            ParsedPlayer(
                player_name=name,
                team_name=team,
                minutes=minutes[key],
                goals=int(goals.get(key, {}).get("count", 0)),
                assists=int(assists.get(key, {}).get("count", 0)),
            )
        )
    return rows, unmatched


def print_report(report: dict[str, Any]) -> None:
    print("P3 FIFA Match Performance CSV Report")
    for key in (
        "result",
        "blocker",
        "source",
        "fifa_match_targets",
        "url_mapping_ready",
        "accessible_matches",
        "matches_with_player_data",
        "sample_csv",
        "sample_rows",
        "unmatched_csv",
        "unmatched_rows",
        "teams_below_70_percent",
        "gbm_ready",
        "candidate_w_gbm",
        "production_w_gbm",
        "would_write_db",
    ):
        print(f"- {key}: {report.get(key)}")


def _fetch_payload(url: str) -> Any:
    if _looks_local_path(url):
        text = Path(url).read_text(encoding="utf-8")
    else:
        req = Request(url, headers={"User-Agent": "worldcup-p3-fifa-match-builder/1.0"})
        with urlopen(req, timeout=20) as response:
            text = response.read(500_000).decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(text)
    return text


def _extract_data(payload: Any) -> Any:
    if isinstance(payload, (dict, list)):
        return payload
    text = str(payload or "")
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', text, re.I | re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
    return {}


def _find_player_stats(data: Any) -> list[dict[str, Any]]:
    rows = _find_lists_by_key(data, {"playerStats", "player_stats", "playersStatistics", "playerStatistics"})
    for row in rows:
        if row and isinstance(row[0], dict) and any(_has_any_key(item, {"minutes", "minutesPlayed", "mins"}) for item in row):
            return row
    return []


def _find_lineups(data: Any) -> list[dict[str, Any]]:
    rows = _find_lists_by_key(data, {"lineups", "lineUps", "startingXI", "starting11"})
    return rows[0] if rows else []


def _find_substitutions(data: Any) -> list[dict[str, Any]]:
    rows = _find_lists_by_key(data, {"substitutions", "subs"})
    return rows[0] if rows else []


def _find_events(data: Any) -> list[dict[str, Any]]:
    rows = _find_lists_by_key(data, {"events", "matchEvents", "timeline"})
    return rows[0] if rows else []


def _find_lists_by_key(data: Any, keys: set[str]) -> list[list[dict[str, Any]]]:
    found: list[list[dict[str, Any]]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and isinstance(value, list):
                found.append(value)
            found.extend(_find_lists_by_key(value, keys))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_lists_by_key(item, keys))
    return found


def _parse_player_stats(rows: list[dict[str, Any]]) -> list[ParsedPlayer]:
    parsed: list[ParsedPlayer] = []
    for row in rows:
        minutes = _number(row.get("minutes") or row.get("minutesPlayed") or row.get("mins"))
        name = _player_name(row)
        team = _team_name(row)
        if minutes is None or not name:
            continue
        parsed.append(
            ParsedPlayer(
                player_name=name,
                team_name=team,
                minutes=minutes,
                goals=int(_number(row.get("goals")) or 0),
                assists=int(_number(row.get("assists")) or 0),
            )
        )
    return parsed


def _estimate_minutes_from_lineups(lineups: list[dict[str, Any]], substitutions: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, str], dict[str, str]]:
    starters: set[str] = set()
    sub_on: dict[str, float] = {}
    sub_off: dict[str, float] = {}
    names: dict[str, str] = {}
    teams: dict[str, str] = {}
    for team_row in lineups:
        team_name = _team_name(team_row)
        players = team_row.get("players") or team_row.get("lineup") or team_row.get("startingXI") or []
        for player in players:
            key = _player_key(player)
            if not key:
                continue
            names[key] = _player_name(player)
            teams[key] = team_name or _team_name(player)
            if _is_starting(player):
                starters.add(key)
            elif _number(player.get("minuteOn") or player.get("subOnMinute")) is not None:
                sub_on[key] = float(_number(player.get("minuteOn") or player.get("subOnMinute")) or 0)
    for sub in substitutions:
        minute = min(float(_number(sub.get("minute") or sub.get("time")) or 0), 90.0)
        off = sub.get("playerOff") or sub.get("out") or sub.get("off") or {}
        on = sub.get("playerOn") or sub.get("in") or sub.get("on") or {}
        off_key = _player_key(off)
        on_key = _player_key(on)
        if off_key:
            names.setdefault(off_key, _player_name(off))
            teams.setdefault(off_key, _team_name(sub))
            sub_off[off_key] = minute
            starters.add(off_key)
        if on_key:
            names.setdefault(on_key, _player_name(on))
            teams.setdefault(on_key, _team_name(sub))
            sub_on[on_key] = minute
    minutes: dict[str, float] = {}
    for key in starters:
        minutes[key] = sub_off.get(key, 90.0)
    for key, minute in sub_on.items():
        minutes[key] = max(0.0, 90.0 - minute)
    return minutes, names, teams


def _aggregate_events(events: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    goals: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": "", "team": ""})
    assists: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": "", "team": ""})
    for event in events:
        event_type = str(event.get("type") or event.get("eventType") or event.get("kind") or "").lower()
        if "goal" in event_type and "own" not in event_type:
            player = event.get("player") or event.get("scorer") or {}
            key = _player_key(player)
            if key:
                goals[key]["count"] += 1
                goals[key]["name"] = _player_name(player)
                goals[key]["team"] = _team_name(event) or _team_name(player)
        assist = event.get("assist") or event.get("assistedBy")
        if assist:
            key = _player_key(assist)
            if key:
                assists[key]["count"] += 1
                assists[key]["name"] = _player_name(assist)
                assists[key]["team"] = _team_name(event) or _team_name(assist)
    return dict(goals), dict(assists)


def _read_targets(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_official_squad(path: Path) -> list[OfficialPlayer]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            OfficialPlayer(
                team=p3_ingest._project_team_name(row.get("team", "")),
                player_name=str(row.get("player_name") or "").strip(),
                club=str(row.get("club") or "").strip(),
            )
            for row in csv.DictReader(handle)
            if str(row.get("team") or "").strip() and str(row.get("player_name") or "").strip()
        ]


def _build_official_index(players: list[OfficialPlayer]) -> dict[str, Any]:
    by_team_name: dict[tuple[str, str], OfficialPlayer] = {}
    by_name: dict[str, list[OfficialPlayer]] = defaultdict(list)
    team_players: dict[str, list[OfficialPlayer]] = defaultdict(list)
    for player in players:
        by_team_name[(_norm_team(player.team), _norm(player.player_name))] = player
        by_name[_norm(player.player_name)].append(player)
        team_players[_norm_team(player.team)].append(player)
    return {"by_team_name": by_team_name, "by_name": by_name, "team_players": team_players}


def _match_official_player(player_name: str, team_name: str, official_index: dict[str, Any]) -> OfficialPlayer | None:
    key = (_norm_team(team_name), _norm(player_name))
    if key in official_index["by_team_name"]:
        return official_index["by_team_name"][key]
    matches = official_index["by_name"].get(_norm(player_name), [])
    if len(matches) == 1:
        return matches[0]
    return None


def _confidence_for_match(player_name: str, team_name: str, official: OfficialPlayer, official_index: dict[str, Any]) -> str:
    if (_norm_team(team_name), _norm(player_name)) in official_index["by_team_name"]:
        return "high"
    if len(official_index["by_name"].get(_norm(player_name), [])) == 1:
        return "medium"
    return "low"


def _add_unmatched(unmatched: dict[tuple[str, str, str, str], dict[str, str]], player_name: str, team_name: str, official_index: dict[str, Any], reason: str, match_url: str) -> None:
    candidates = _candidate_project_players(player_name, team_name, official_index)
    key = (player_name, team_name, reason, match_url)
    unmatched[key] = {
        "fifa_player_name": player_name,
        "fifa_team": team_name,
        "candidate_project_players": "; ".join(candidates[:10]),
        "reason": reason,
        "match_url": match_url,
    }


def _candidate_project_players(player_name: str, team_name: str, official_index: dict[str, Any]) -> list[str]:
    team_key = _norm_team(team_name)
    name_key = _norm(player_name)
    candidates = [
        f"{player.team}::{player.player_name}"
        for player in official_index["team_players"].get(team_key, [])
        if name_key and (name_key in _norm(player.player_name) or _norm(player.player_name) in name_key)
    ]
    if not candidates:
        candidates.extend(f"{player.team}::{player.player_name}" for player in official_index["by_name"].get(name_key, []))
    return sorted(set(candidates))


def _performance_row(official: OfficialPlayer, aggregate: PlayerAggregate, confidence: str) -> dict[str, str]:
    notes = f"fifa_match_data; match_count={len(aggregate.match_urls)}; unavailable_xg_xa; not_club_recent_form"
    return {
        "team": official.team,
        "player_name": official.player_name,
        "club": official.club,
        "minutes_recent": _format_number(aggregate.minutes),
        "goals_recent": str(aggregate.goals),
        "assists_recent": str(aggregate.assists),
        "xg_recent": "",
        "xa_recent": "",
        "source": ";".join(sorted(aggregate.match_urls)) or SOURCE_LABEL,
        "retrieved_at": date.today().isoformat(),
        "confidence": confidence,
        "notes": notes,
    }


def _coverage_by_team(rows: list[dict[str, str]], official_players: list[OfficialPlayer]) -> dict[str, dict[str, Any]]:
    roster_by_team: dict[str, set[str]] = defaultdict(set)
    complete_by_team: dict[str, set[str]] = defaultdict(set)
    for player in official_players:
        roster_by_team[player.team].add(p3_ingest._real_player_key({"team": player.team, "player_name": player.player_name}))
    for row in rows:
        if p3_ingest._has_complete_recent_performance(row):
            complete_by_team[p3_ingest._project_team_name(row["team"])].add(p3_ingest._real_player_key(row))
    coverage: dict[str, dict[str, Any]] = {}
    for team in sorted(roster_by_team):
        total = len(roster_by_team[team])
        complete = len(roster_by_team[team] & complete_by_team.get(team, set()))
        coverage[team] = {"players": total, "complete": complete, "ratio": complete / total if total else 0.0}
    return coverage


def _wait_report(matches: Path, out: Path, unmatched_out: Path, reason: str) -> dict[str, Any]:
    return {
        "result": "WAIT",
        "blocker": reason,
        "source": SOURCE_LABEL,
        "fifa_match_targets": str(matches),
        "url_mapping_ready": False,
        "accessible_matches": 0,
        "matches_with_player_data": 0,
        "sample_csv": str(out),
        "sample_rows": 0,
        "unmatched_csv": str(unmatched_out),
        "unmatched_rows": 0,
        "coverage_by_team": {},
        "teams_below_70_percent": [],
        "gbm_ready": False,
        "candidate_w_gbm": 0,
        "production_w_gbm": p3_ingest.PRODUCTION_W_GBM,
        "would_write_db": False,
        "data_scope": "fifa_world_cup_match_performance",
        "not_club_recent_form": True,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P3 FIFA MatchData Report",
        "",
        "## Scope",
        "- data_scope: fifa_world_cup_match_performance",
        "- not_club_recent_form: true",
        "- FIFA MatchData is official World Cup match performance data, not pre-match club recent form.",
        "",
        "## CSV Summary",
        f"- result: {report.get('result')}",
        f"- blocker: {report.get('blocker')}",
        f"- fifa_match_targets: `{report.get('fifa_match_targets')}`",
        f"- accessible_matches: {report.get('accessible_matches', 0)}",
        f"- matches_with_player_data: {report.get('matches_with_player_data', 0)}",
        f"- sample_csv: `{report.get('sample_csv')}`",
        f"- sample_rows: {report.get('sample_rows', 0)}",
        f"- unmatched_csv: `{report.get('unmatched_csv')}`",
        f"- unmatched_rows: {report.get('unmatched_rows', 0)}",
        "",
        "## Coverage",
        f"- coverage_by_team: `{report.get('coverage_by_team', {})}`",
        f"- teams_below_70_percent: `{report.get('teams_below_70_percent', [])}`",
        f"- gbm_ready: {str(report.get('gbm_ready', False)).lower()}",
        f"- candidate_w_gbm: {report.get('candidate_w_gbm', 0)}",
        f"- production_w_gbm: {report.get('production_w_gbm', 0)}",
        f"- would_write_db: {str(report.get('would_write_db', False)).lower()}",
        "",
        "## Policies",
        f"- minutes_policy: {report.get('minutes_policy', 'FIFA player minutes or conservative lineups/substitutions')}",
        f"- goals_policy: {report.get('goals_policy', 'FIFA official goal events only')}",
        f"- assists_policy: {report.get('assists_policy', 'FIFA official assists only')}",
        f"- xg_xa_policy: {report.get('xg_xa_policy', 'blank with unavailable_xg_xa notes')}",
        f"- source_policy: {report.get('source_policy', 'FIFA match URL per row')}",
        f"- confidence_policy: {report.get('confidence_policy', 'high exact team+name; medium unique name; low unmatched only')}",
        "",
        "## Safety",
        "If FIFA player-level data or URL mapping is missing, the adapter reports WAIT. Do not fabricate match performance data, do not write production DB, and do not enable betting.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _has_any_key(row: dict[str, Any], keys: set[str]) -> bool:
    return any(key in row for key in keys)


def _player_key(row: dict[str, Any]) -> str:
    player = row.get("player") if isinstance(row.get("player"), dict) else row
    value = player.get("id") or player.get("playerId") or player.get("player_id") or player.get("name") or player.get("playerName") or player.get("player_name")
    return str(value or "").strip()


def _player_name(row: dict[str, Any]) -> str:
    player = row.get("player") if isinstance(row.get("player"), dict) else row
    return str(player.get("name") or player.get("playerName") or player.get("player_name") or "").strip()


def _team_name(row: dict[str, Any]) -> str:
    team = row.get("team") if isinstance(row.get("team"), dict) else row
    return str(team.get("name") or team.get("teamName") or team.get("team_name") or row.get("teamName") or row.get("team_name") or "").strip()


def _is_starting(row: dict[str, Any]) -> bool:
    value = row.get("starting") if "starting" in row else row.get("isStarting")
    if isinstance(value, bool):
        return value
    role = str(row.get("role") or row.get("status") or "").lower()
    return role in {"starter", "starting", "startingxi", "starting xi"}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm_team(value: str) -> str:
    return _norm(p3_ingest._project_team_name(value))


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build P3-Light FIFA MatchData performance CSV")
    parser.add_argument("--matches", type=Path, default=DEFAULT_MATCHES)
    parser.add_argument("--squad", type=Path, default=DEFAULT_SQUAD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--unmatched-out", type=Path, default=DEFAULT_UNMATCHED_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args(argv)
    report = build_fifa_match_performance_csv(
        matches=args.matches,
        squad=args.squad,
        out=args.out,
        unmatched_out=args.unmatched_out,
        report_out=args.report_out,
    )
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

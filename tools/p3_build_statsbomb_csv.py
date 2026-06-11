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
from typing import Any, Iterable

from model import p3_ingest


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
DEFAULT_STATSBOMB_ROOT = DATA_DIR / "statsbomb_open_data"
DEFAULT_SQUAD = DATA_DIR / "manual_real_squad.csv"
DEFAULT_OUT = DATA_DIR / "real_performance_statsbomb_sample.csv"
DEFAULT_UNMATCHED_OUT = DATA_DIR / "real_performance_unmatched_statsbomb.csv"
DEFAULT_REPORT_OUT = ROOT / "docs" / "P3_STATSBOMB_OPEN_DATA_REPORT.md"
SOURCE_URL = "https://github.com/statsbomb/open-data"
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
UNMATCHED_COLUMNS = [
    "statsbomb_player_name",
    "statsbomb_team",
    "candidate_project_players",
    "reason",
]


@dataclass
class OfficialPlayer:
    team: str
    player_name: str
    club: str


@dataclass
class PlayerAggregate:
    player_id: int | str
    player_name: str
    team_name: str
    minutes: float = 0.0
    goals: int = 0
    assists: int = 0
    match_ids: set[str] = field(default_factory=set)
    minutes_matches: int = 0


@dataclass
class MatchInfo:
    match_id: str
    competition_id: str
    season_id: str
    competition_name: str
    season_name: str
    match_date: str
    home_team: str
    away_team: str


def build_statsbomb_csv(
    statsbomb_root: Path = DEFAULT_STATSBOMB_ROOT,
    squad: Path = DEFAULT_SQUAD,
    out: Path = DEFAULT_OUT,
    unmatched_out: Path = DEFAULT_UNMATCHED_OUT,
    report_out: Path = DEFAULT_REPORT_OUT,
    max_matches: int | None = None,
    competitions: set[str] | None = None,
    min_confidence: str = "medium",
) -> dict[str, Any]:
    if not statsbomb_root.exists():
        report = _wait_report(
            statsbomb_root=statsbomb_root,
            squad=squad,
            out=out,
            unmatched_out=unmatched_out,
            report_out=report_out,
            reason="statsbomb_root_missing",
        )
        _write_report(report_out, report)
        return report

    competitions_json = statsbomb_root / "data" / "competitions.json"
    matches_dir = statsbomb_root / "data" / "matches"
    events_dir = statsbomb_root / "data" / "events"
    lineups_dir = statsbomb_root / "data" / "lineups"
    if not competitions_json.exists() or not matches_dir.exists():
        report = _wait_report(
            statsbomb_root=statsbomb_root,
            squad=squad,
            out=out,
            unmatched_out=unmatched_out,
            report_out=report_out,
            reason="statsbomb_required_files_missing",
        )
        _write_report(report_out, report)
        return report

    official_players = _read_official_squad(squad)
    official_index = _build_official_index(official_players)
    competition_rows = _load_json(competitions_json)
    competition_meta = _competition_meta(competition_rows)
    matches = _load_matches(matches_dir, competition_meta, competitions=competitions)
    if max_matches is not None:
        matches = matches[:max_matches]

    aggregates: dict[tuple[str, str], PlayerAggregate] = {}
    unmatched: dict[tuple[str, str, str], dict[str, str]] = {}
    processed_events = 0
    processed_lineups = 0
    missing_events = 0
    missing_lineups = 0

    for match in matches:
        lineups_path = lineups_dir / f"{match.match_id}.json"
        events_path = events_dir / f"{match.match_id}.json"
        if not lineups_path.exists():
            missing_lineups += 1
            continue
        if not events_path.exists():
            missing_events += 1
            continue
        lineups = _load_json(lineups_path)
        events = _load_json(events_path)
        processed_lineups += 1
        processed_events += 1
        match_minutes = _estimate_match_minutes(lineups)
        goals, assists = _aggregate_events(events)
        player_names = _player_names_from_lineups(lineups)
        player_teams = _player_teams_from_lineups(lineups)
        player_ids = sorted(set(player_names) | set(match_minutes) | set(goals) | set(assists))
        for player_id in player_ids:
            player_name = player_names.get(player_id) or goals.get(player_id, {}).get("name") or assists.get(player_id, {}).get("name") or ""
            team_name = player_teams.get(player_id, "")
            key = (str(player_id), team_name or player_name)
            aggregate = aggregates.setdefault(
                key,
                PlayerAggregate(player_id=player_id, player_name=player_name, team_name=team_name),
            )
            aggregate.player_name = aggregate.player_name or player_name
            aggregate.team_name = aggregate.team_name or team_name
            if player_id in match_minutes:
                aggregate.minutes += match_minutes[player_id]
                aggregate.minutes_matches += 1
            aggregate.goals += int(goals.get(player_id, {}).get("count", 0))
            aggregate.assists += int(assists.get(player_id, {}).get("count", 0))
            if player_id in match_minutes or player_id in goals or player_id in assists:
                aggregate.match_ids.add(match.match_id)

    rows: list[dict[str, str]] = []
    for aggregate in sorted(aggregates.values(), key=lambda item: (_norm(item.team_name), _norm(item.player_name))):
        if aggregate.minutes <= 0:
            if aggregate.goals or aggregate.assists:
                _add_unmatched(unmatched, aggregate, official_index, "minutes_not_reliably_estimated")
            continue
        official = _match_official_player(aggregate, official_index)
        if official is None:
            _add_unmatched(unmatched, aggregate, official_index, "no_exact_project_roster_match")
            continue
        confidence = _confidence_for_match(aggregate, official, official_index)
        if _confidence_rank(confidence) < _confidence_rank(min_confidence):
            _add_unmatched(unmatched, aggregate, official_index, f"confidence_below_{min_confidence}")
            continue
        rows.append(_performance_row(official, aggregate, confidence))

    unmatched_rows = sorted(unmatched.values(), key=lambda row: (row["statsbomb_team"], row["statsbomb_player_name"], row["reason"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    unmatched_out.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(out, OUTPUT_COLUMNS, rows)
    _write_csv(unmatched_out, UNMATCHED_COLUMNS, unmatched_rows)
    coverage = _coverage_by_team(rows, official_players)
    teams_below = sorted(team for team, item in coverage.items() if item["ratio"] < p3_ingest.GBM_COVERAGE_THRESHOLD)
    report = {
        "result": "PASS",
        "blocker": "coverage_below_threshold" if teams_below else None,
        "statsbomb_root": str(statsbomb_root),
        "clone_or_pull_success": True,
        "competitions_count": len(competition_rows),
        "matches_count": len(matches),
        "events_files_count": processed_events,
        "lineups_files_count": processed_lineups,
        "missing_events_files_count": missing_events,
        "missing_lineups_files_count": missing_lineups,
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
        "source": SOURCE_URL,
        "minutes_policy": "conservative lineups positions intervals only; uncertain minutes omitted",
        "goals_policy": "Shot events with shot.outcome.name=Goal; own goals excluded",
        "assists_policy": "pass.goal_assist=true plus conservative assisted_shot_id/key_pass_id linkage",
        "xg_xa_policy": "left blank for P3-Light; notes include unavailable_xg_xa",
        "confidence": f"{min_confidence}+ only",
    }
    _write_report(report_out, report)
    return report


def print_report(report: dict[str, Any]) -> None:
    print("P3 StatsBomb Open Data Adapter Report")
    for key in (
        "result",
        "blocker",
        "statsbomb_root",
        "competitions_count",
        "matches_count",
        "events_files_count",
        "lineups_files_count",
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


def _wait_report(statsbomb_root: Path, squad: Path, out: Path, unmatched_out: Path, report_out: Path, reason: str) -> dict[str, Any]:
    return {
        "result": "WAIT",
        "blocker": reason,
        "statsbomb_root": str(statsbomb_root),
        "squad": str(squad),
        "competitions_count": 0,
        "matches_count": 0,
        "events_files_count": 0,
        "lineups_files_count": 0,
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
        "report_out": str(report_out),
    }


def _read_official_squad(path: Path) -> list[OfficialPlayer]:
    rows = _read_csv(path)
    return [
        OfficialPlayer(
            team=p3_ingest._project_team_name(row.get("team", "")),
            player_name=str(row.get("player_name") or "").strip(),
            club=str(row.get("club") or "").strip(),
        )
        for row in rows
        if str(row.get("team") or "").strip() and str(row.get("player_name") or "").strip()
    ]


def _build_official_index(players: list[OfficialPlayer]) -> dict[str, Any]:
    by_team_name: dict[tuple[str, str], OfficialPlayer] = {}
    by_name: dict[str, list[OfficialPlayer]] = defaultdict(list)
    team_players: dict[str, list[OfficialPlayer]] = defaultdict(list)
    for player in players:
        team_key = _norm_team(player.team)
        name_key = _norm(player.player_name)
        by_team_name[(team_key, name_key)] = player
        by_name[name_key].append(player)
        team_players[team_key].append(player)
    return {"by_team_name": by_team_name, "by_name": by_name, "team_players": team_players}


def _load_matches(matches_dir: Path, competition_meta: dict[tuple[str, str], dict[str, str]], competitions: set[str] | None = None) -> list[MatchInfo]:
    matches: list[MatchInfo] = []
    for path in sorted(matches_dir.glob("*/*.json")):
        competition_id = path.parent.name
        season_id = path.stem
        meta = competition_meta.get((competition_id, season_id), {})
        if competitions and not _competition_selected(competition_id, season_id, meta, competitions):
            continue
        for row in _load_json(path):
            matches.append(
                MatchInfo(
                    match_id=str(row.get("match_id")),
                    competition_id=competition_id,
                    season_id=season_id,
                    competition_name=str(meta.get("competition_name") or row.get("competition", {}).get("competition_name") or ""),
                    season_name=str(meta.get("season_name") or row.get("season", {}).get("season_name") or ""),
                    match_date=str(row.get("match_date") or ""),
                    home_team=str(row.get("home_team", {}).get("home_team_name") or ""),
                    away_team=str(row.get("away_team", {}).get("away_team_name") or ""),
                )
            )
    return sorted(matches, key=lambda match: (match.match_date, match.match_id))


def _competition_selected(competition_id: str, season_id: str, meta: dict[str, str], competitions: set[str]) -> bool:
    tokens = {competition_id, season_id, f"{competition_id}/{season_id}", _norm(meta.get("competition_name", "")), _norm(meta.get("season_name", ""))}
    wanted = {_norm(item) for item in competitions} | competitions
    return bool(tokens & wanted)


def _competition_meta(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, str]]:
    meta: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row.get("competition_id")), str(row.get("season_id")))
        meta[key] = {
            "competition_name": str(row.get("competition_name") or ""),
            "season_name": str(row.get("season_name") or ""),
        }
    return meta


def _estimate_match_minutes(lineups: list[dict[str, Any]]) -> dict[int | str, float]:
    minutes: dict[int | str, float] = {}
    for team in lineups:
        for player in team.get("lineup", []):
            player_id = _player_id(player)
            intervals: list[tuple[float, float]] = []
            for position in player.get("positions") or []:
                start = _position_time(position.get("from"), default_start=True)
                end = _position_time(position.get("to"), default_start=False)
                if start is None or end is None or end <= start:
                    continue
                intervals.append((start, min(end, 120.0)))
            if intervals:
                minutes[player_id] = round(sum(end - start for start, end in intervals), 2)
    return minutes


def _position_time(value: Any, default_start: bool) -> float | None:
    if value is None or value == "":
        return 0.0 if default_start else 90.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0 if default_start else 90.0
    if ":" in text:
        first = text.split(":", 1)[0]
        return float(first) if first.isdigit() else None
    try:
        return float(text)
    except ValueError:
        return None


def _aggregate_events(events: list[dict[str, Any]]) -> tuple[dict[int | str, dict[str, Any]], dict[int | str, dict[str, Any]]]:
    goals: dict[int | str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": ""})
    assists: dict[int | str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": ""})
    key_pass_by_shot: dict[str, tuple[int | str, str]] = {}
    for event in events:
        if _event_type(event) != "Pass":
            continue
        player = event.get("player") or {}
        player_id = _entity_id(player)
        player_name = _entity_name(player)
        pass_data = event.get("pass") or {}
        if pass_data.get("goal_assist") is True:
            assists[player_id]["count"] += 1
            assists[player_id]["name"] = player_name
        assisted_shot_id = pass_data.get("assisted_shot_id")
        if assisted_shot_id:
            key_pass_by_shot[str(assisted_shot_id)] = (player_id, player_name)
    for event in events:
        if _event_type(event) != "Shot":
            continue
        shot = event.get("shot") or {}
        outcome = (shot.get("outcome") or {}).get("name")
        if outcome != "Goal" or shot.get("type", {}).get("name") == "Own Goal":
            continue
        player = event.get("player") or {}
        player_id = _entity_id(player)
        goals[player_id]["count"] += 1
        goals[player_id]["name"] = _entity_name(player)
        key_pass_id = shot.get("key_pass_id") or event.get("id")
        if key_pass_id and str(key_pass_id) in key_pass_by_shot:
            assist_player_id, assist_player_name = key_pass_by_shot[str(key_pass_id)]
            assists[assist_player_id]["count"] += 1
            assists[assist_player_id]["name"] = assist_player_name
    return dict(goals), dict(assists)


def _player_names_from_lineups(lineups: list[dict[str, Any]]) -> dict[int | str, str]:
    names: dict[int | str, str] = {}
    for team in lineups:
        for player in team.get("lineup", []):
            names[_player_id(player)] = str(player.get("player_name") or "").strip()
    return names


def _player_teams_from_lineups(lineups: list[dict[str, Any]]) -> dict[int | str, str]:
    teams: dict[int | str, str] = {}
    for team in lineups:
        team_name = str(team.get("team_name") or "").strip()
        for player in team.get("lineup", []):
            teams[_player_id(player)] = team_name
    return teams


def _match_official_player(aggregate: PlayerAggregate, official_index: dict[str, Any]) -> OfficialPlayer | None:
    team_key = _norm_team(aggregate.team_name)
    name_key = _norm(aggregate.player_name)
    if (team_key, name_key) in official_index["by_team_name"]:
        return official_index["by_team_name"][(team_key, name_key)]
    name_matches = official_index["by_name"].get(name_key, [])
    if len(name_matches) == 1:
        return name_matches[0]
    return None


def _confidence_for_match(aggregate: PlayerAggregate, official: OfficialPlayer, official_index: dict[str, Any]) -> str:
    if (_norm_team(aggregate.team_name), _norm(aggregate.player_name)) in official_index["by_team_name"]:
        return "high"
    return "medium"


def _add_unmatched(unmatched: dict[tuple[str, str, str], dict[str, str]], aggregate: PlayerAggregate, official_index: dict[str, Any], reason: str) -> None:
    candidates = _candidate_project_players(aggregate, official_index)
    key = (aggregate.player_name, aggregate.team_name, reason)
    unmatched[key] = {
        "statsbomb_player_name": aggregate.player_name,
        "statsbomb_team": aggregate.team_name,
        "candidate_project_players": "; ".join(candidates[:10]),
        "reason": reason,
    }


def _candidate_project_players(aggregate: PlayerAggregate, official_index: dict[str, Any]) -> list[str]:
    team_key = _norm_team(aggregate.team_name)
    name_key = _norm(aggregate.player_name)
    candidates: list[str] = []
    for player in official_index["team_players"].get(team_key, []):
        if name_key and (name_key in _norm(player.player_name) or _norm(player.player_name) in name_key):
            candidates.append(f"{player.team}::{player.player_name}")
    if not candidates:
        candidates.extend(f"{player.team}::{player.player_name}" for player in official_index["by_name"].get(name_key, []))
    return sorted(set(candidates))


def _performance_row(official: OfficialPlayer, aggregate: PlayerAggregate, confidence: str) -> dict[str, str]:
    notes = (
        "statsbomb_open_data_partial; unavailable_xg_xa; "
        f"match_count={len(aggregate.match_ids)}; minutes_estimation=conservative"
    )
    return {
        "team": official.team,
        "player_name": official.player_name,
        "club": official.club,
        "minutes_recent": _format_number(aggregate.minutes),
        "goals_recent": str(aggregate.goals),
        "assists_recent": str(aggregate.assists),
        "xg_recent": "",
        "xa_recent": "",
        "source": SOURCE_URL,
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


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P3 StatsBomb Open Data Report",
        "",
        "## 1. Source Structure",
        "StatsBomb Open Data is read from `data/competitions.json`, `data/matches/*/*.json`, `data/events/*.json`, and `data/lineups/*.json`. The adapter does not read `players/players.json`.",
        "",
        "## 2. Counts",
        f"- statsbomb_root: `{report.get('statsbomb_root')}`",
        f"- competitions_count: {report.get('competitions_count', 0)}",
        f"- matches_count: {report.get('matches_count', 0)}",
        f"- events_files_count: {report.get('events_files_count', 0)}",
        f"- lineups_files_count: {report.get('lineups_files_count', 0)}",
        "",
        "## 3. Outputs",
        f"- matched_players: {report.get('sample_rows', 0)}",
        f"- unmatched_players: {report.get('unmatched_rows', 0)}",
        f"- sample_csv: `{report.get('sample_csv')}`",
        f"- unmatched_csv: `{report.get('unmatched_csv')}`",
        "",
        "## 4. Coverage",
        f"- coverage_by_team: `{report.get('coverage_by_team', {})}`",
        f"- teams_below_70_percent: `{report.get('teams_below_70_percent', [])}`",
        "",
        "## 5. Policies",
        f"- minutes_policy: {report.get('minutes_policy', 'conservative')}",
        f"- goals_policy: {report.get('goals_policy', 'Shot Goal events only')}",
        f"- assists_policy: {report.get('assists_policy', 'conservative pass assist linkage')}",
        f"- xg_xa_policy: {report.get('xg_xa_policy', 'blank with unavailable_xg_xa notes')}",
        f"- source: {SOURCE_URL}",
        "",
        "## 6. Status",
        "This is a partial sample and does not guarantee 70% coverage across the 48-team roster.",
        f"- result: {report.get('result')}",
        f"- blocker: {report.get('blocker')}",
        f"- gbm_ready: {str(report.get('gbm_ready', False)).lower()}",
        f"- candidate_w_gbm: {report.get('candidate_w_gbm', 0)}",
        f"- production_w_gbm: {report.get('production_w_gbm', 0)}",
        f"- would_write_db: {str(report.get('would_write_db', False)).lower()}",
        "",
        "## 7. Safety",
        "P3-Light remains WAIT when coverage is below threshold. Betting should not be enabled from this report.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _event_type(event: dict[str, Any]) -> str:
    return str((event.get("type") or {}).get("name") or "")


def _entity_id(entity: dict[str, Any]) -> int | str:
    return entity.get("id") or entity.get("player_id") or ""


def _entity_name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or entity.get("player_name") or "").strip()


def _player_id(player: dict[str, Any]) -> int | str:
    return player.get("player_id") or player.get("id") or ""


def _norm_team(value: str) -> str:
    return _norm(p3_ingest._project_team_name(value))


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _confidence_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value, 2)


def _parse_competitions(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build P3-Light StatsBomb Open Data partial performance CSV")
    parser.add_argument("--statsbomb-root", type=Path, default=DEFAULT_STATSBOMB_ROOT)
    parser.add_argument("--squad", type=Path, default=DEFAULT_SQUAD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--unmatched-out", type=Path, default=DEFAULT_UNMATCHED_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--max-matches", type=int)
    parser.add_argument("--competitions")
    parser.add_argument("--min-confidence", choices=("low", "medium", "high"), default="medium")
    args = parser.parse_args(argv)
    report = build_statsbomb_csv(
        statsbomb_root=args.statsbomb_root,
        squad=args.squad,
        out=args.out,
        unmatched_out=args.unmatched_out,
        report_out=args.report_out,
        max_matches=args.max_matches,
        competitions=_parse_competitions(args.competitions),
        min_confidence=args.min_confidence,
    )
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

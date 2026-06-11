from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model import p3_ingest


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "data" / "schedule" / "worldcup2026_schedule.csv"
DATA_DIR = ROOT / "data" / "p3"
BACKLOG_PATH = DATA_DIR / "p3_collection_backlog.csv"

MIN_SQUAD_ROWS_PER_TEAM = 10
MIN_STATS_ROWS_PER_TEAM = 4
MIN_NUMERIC_STATS_ROWS_PER_TEAM = 4
FIRST_PHASE_MATCHES = 24


@dataclass(frozen=True)
class TeamCoverage:
    team: str
    priority: str
    first_match_num: str
    first_kickoff_at: str
    first_opponent: str
    squad_rows: int
    player_stats_rows: int
    numeric_stats_rows: int
    injuries_rows: int
    source_rows: int
    retrieved_at_rows: int
    confidence_rows: int

    @property
    def missing_items(self) -> list[str]:
        missing: list[str] = []
        if self.squad_rows < MIN_SQUAD_ROWS_PER_TEAM:
            missing.append("squad")
        if self.player_stats_rows < MIN_STATS_ROWS_PER_TEAM:
            missing.append("player_stats")
        if self.numeric_stats_rows < MIN_NUMERIC_STATS_ROWS_PER_TEAM:
            missing.append("numeric_recent_stats")
        if self.injuries_rows < 1:
            missing.append("injury_status")
        if self.source_rows < self.squad_rows + self.player_stats_rows + self.injuries_rows:
            missing.append("source")
        if self.retrieved_at_rows < self.squad_rows + self.player_stats_rows + self.injuries_rows:
            missing.append("retrieved_at")
        if self.confidence_rows < self.squad_rows + self.player_stats_rows + self.injuries_rows:
            missing.append("confidence")
        return missing

    @property
    def status(self) -> str:
        if not self.missing_items:
            return "complete"
        if self.squad_rows or self.player_stats_rows or self.injuries_rows:
            return "partial"
        return "missing"


def generate_report(data_dir: Path = DATA_DIR, schedule_path: Path = SCHEDULE_PATH) -> dict[str, Any]:
    teams, first_matches = _schedule_teams(schedule_path)
    real_rows = p3_ingest._read_real_rows(data_dir) if p3_ingest._real_csv_exists(data_dir) else {"squad": [], "player_stats": [], "injuries": []}
    coverage = [_coverage_for_team(team, first_matches[team], real_rows) for team in teams]
    summary = {
        "teams_total": len(coverage),
        "complete_teams": sum(1 for row in coverage if row.status == "complete"),
        "partial_teams": sum(1 for row in coverage if row.status == "partial"),
        "missing_teams": sum(1 for row in coverage if row.status == "missing"),
        "first_phase_total": sum(1 for row in coverage if row.priority == "P0"),
        "first_phase_complete": sum(1 for row in coverage if row.priority == "P0" and row.status == "complete"),
        "teams_with_numeric_stats": sum(1 for row in coverage if row.numeric_stats_rows >= MIN_NUMERIC_STATS_ROWS_PER_TEAM),
    }
    blocker = None
    if summary["complete_teams"] < summary["teams_total"]:
        blocker = "player_data_incomplete"
    if summary["teams_with_numeric_stats"] < summary["teams_total"]:
        blocker = "numeric_recent_stats_incomplete"
    return {
        "result": "PASS" if blocker is None else "WAIT",
        "blocker": blocker,
        "thresholds": {
            "min_squad_rows_per_team": MIN_SQUAD_ROWS_PER_TEAM,
            "min_stats_rows_per_team": MIN_STATS_ROWS_PER_TEAM,
            "min_numeric_stats_rows_per_team": MIN_NUMERIC_STATS_ROWS_PER_TEAM,
        },
        "summary": summary,
        "coverage": [row_to_dict(row) for row in coverage],
        "next_backlog": [row_to_dict(row) for row in coverage if row.status != "complete"],
    }


def write_backlog(report: dict[str, Any], path: Path = BACKLOG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "priority",
        "team",
        "first_match_num",
        "first_kickoff_at",
        "first_opponent",
        "status",
        "squad_rows",
        "player_stats_rows",
        "numeric_stats_rows",
        "injuries_rows",
        "missing_items",
        "suggested_action",
    ]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["next_backlog"]:
            writer.writerow(
                {
                    "priority": row["priority"],
                    "team": row["team"],
                    "first_match_num": row["first_match_num"],
                    "first_kickoff_at": row["first_kickoff_at"],
                    "first_opponent": row["first_opponent"],
                    "status": row["status"],
                    "squad_rows": row["squad_rows"],
                    "player_stats_rows": row["player_stats_rows"],
                    "numeric_stats_rows": row["numeric_stats_rows"],
                    "injuries_rows": row["injuries_rows"],
                    "missing_items": "|".join(row["missing_items"]),
                    "suggested_action": _suggested_action(row["missing_items"]),
                }
            )
    return path


def row_to_dict(row: TeamCoverage) -> dict[str, Any]:
    return {
        "team": row.team,
        "priority": row.priority,
        "first_match_num": row.first_match_num,
        "first_kickoff_at": row.first_kickoff_at,
        "first_opponent": row.first_opponent,
        "status": row.status,
        "squad_rows": row.squad_rows,
        "player_stats_rows": row.player_stats_rows,
        "numeric_stats_rows": row.numeric_stats_rows,
        "injuries_rows": row.injuries_rows,
        "missing_items": row.missing_items,
    }


def _coverage_for_team(team: str, first_match: dict[str, str], real_rows: dict[str, list[dict[str, str]]]) -> TeamCoverage:
    canonical = _canonical_team(team)
    squad = [row for row in real_rows.get("squad", []) if _canonical_team(row.get("team", "")) == canonical]
    stats = [row for row in real_rows.get("player_stats", []) if _canonical_team(row.get("team", "")) == canonical]
    injuries = [row for row in real_rows.get("injuries", []) if _canonical_team(row.get("team", "")) == canonical]
    all_rows = squad + stats + injuries
    return TeamCoverage(
        team=team,
        priority=first_match["priority"],
        first_match_num=first_match["match_num"],
        first_kickoff_at=first_match["kickoff_at"],
        first_opponent=first_match["opponent"],
        squad_rows=len(squad),
        player_stats_rows=len(stats),
        numeric_stats_rows=sum(1 for row in stats if _has_numeric_recent_stat(row)),
        injuries_rows=len(injuries),
        source_rows=sum(1 for row in all_rows if str(row.get("source") or "").strip()),
        retrieved_at_rows=sum(1 for row in all_rows if str(row.get("retrieved_at") or "").strip()),
        confidence_rows=sum(1 for row in all_rows if str(row.get("confidence") or "").strip()),
    )


def _schedule_teams(schedule_path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with schedule_path.open("r", encoding="utf-8-sig", newline="") as fp:
        rows = [dict(row) for row in csv.DictReader(fp) if row.get("stage") == "Group stage"]
    first_matches: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=1):
        priority = "P0" if index <= FIRST_PHASE_MATCHES else "P1"
        for side, other in (("home_team", "away_team"), ("away_team", "home_team")):
            team = str(row[side]).strip()
            if team not in first_matches:
                first_matches[team] = {
                    "match_num": str(row["match_num"]),
                    "kickoff_at": str(row["kickoff_at"]),
                    "opponent": str(row[other]).strip(),
                    "priority": priority,
                }
    return sorted(first_matches), first_matches


def _has_numeric_recent_stat(row: dict[str, str]) -> bool:
    return any(_is_number(row.get(column)) for column in ("minutes_recent", "goals_recent", "assists_recent", "xg_recent", "xa_recent"))


def _is_number(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


TEAM_ALIASES = {
    "curacao": "curacao",
    "curaçao": "curacao",
    "cotedivoire": "ivorycoast",
    "côtedivoire": "ivorycoast",
    "ivorycoast": "ivorycoast",
    "drcongo": "drcongo",
    "congodr": "drcongo",
    "bosniaherzegovina": "bosniaherzegovina",
    "bosniaandherzegovina": "bosniaherzegovina",
    "czechia": "czechrepublic",
    "czechrepublic": "czechrepublic",
    "usa": "usa",
    "unitedstates": "usa",
}


def _canonical_team(value: str) -> str:
    normalized = re.sub(r"[\s\u3000'’.\-&/()]+", "", str(value or "")).lower()
    return TEAM_ALIASES.get(normalized, normalized)


def _suggested_action(missing_items: list[str]) -> str:
    if "squad" in missing_items:
        return "collect reviewed squad rows first"
    if "numeric_recent_stats" in missing_items:
        return "collect recent minutes/goals/assists/xg/xa for core players"
    if "injury_status" in missing_items:
        return "collect source-backed injury status row"
    return "complete metadata fields"


def print_report(report: dict[str, Any]) -> None:
    print("P3 Player Data Audit Report")
    print("")
    print("1. Summary")
    for key, value in report["summary"].items():
        print(f"- {key}: {value}")
    print("")
    print("2. Thresholds")
    for key, value in report["thresholds"].items():
        print(f"- {key}: {value}")
    print("")
    print("3. Next backlog")
    for row in report["next_backlog"][:20]:
        print(
            f"- {row['priority']} {row['team']}: status={row['status']} "
            f"squad={row['squad_rows']} stats={row['player_stats_rows']} numeric={row['numeric_stats_rows']} "
            f"injuries={row['injuries_rows']} missing={','.join(row['missing_items'])}"
        )
    print("")
    print(f"- blocker: {report['blocker']}")
    print(f"result: {report['result']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit P3 real player data coverage without writing production DB.")
    parser.add_argument("--write-backlog", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = generate_report()
    if args.write_backlog:
        path = write_backlog(report)
        report["backlog_path"] = str(path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
        if args.write_backlog:
            print(f"- backlog_path: {report['backlog_path']}")
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

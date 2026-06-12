from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
DEFAULT_MATCHES = DATA_DIR / "fifa_match_targets.csv"
DEFAULT_TEMPLATE = DATA_DIR / "fifa_match_targets_template.csv"
DEFAULT_REPORT_OUT = ROOT / "docs" / "P3_FIFA_MATCH_DATA_REPORT.md"
TARGET_COLUMNS = ["project_match_id", "fifa_match_url", "home_team", "away_team", "kickoff_at", "status"]
USER_AGENT = "worldcup-p3-fifa-match-probe/1.0"
MAX_TEXT_BYTES = 300_000


@dataclass(frozen=True)
class ProbeTarget:
    project_match_id: str
    fifa_match_url: str
    home_team: str
    away_team: str
    kickoff_at: str
    status: str


def probe_match_centre(matches: Path = DEFAULT_MATCHES, report_out: Path = DEFAULT_REPORT_OUT) -> dict[str, Any]:
    if not matches.exists():
        _write_target_template(DEFAULT_TEMPLATE)
        report = {
            "result": "WAIT",
            "reason": "missing_fifa_match_url_mapping",
            "needs_fifa_match_url_mapping": True,
            "fifa_match_targets": str(matches),
            "template": str(DEFAULT_TEMPLATE),
            "targets": [],
            "accessible_matches": 0,
            "matches_with_player_data": 0,
            "data_scope": "fifa_world_cup_match_performance",
            "not_club_recent_form": True,
        }
        _write_report(report_out, report)
        return report

    targets = _read_targets(matches)
    rows = [_probe_target(target) for target in targets]
    accessible = sum(1 for row in rows if row["accessible"])
    player_data = sum(1 for row in rows if _has_player_data(row))
    if not targets or all(not target.fifa_match_url for target in targets):
        result = "WAIT"
        reason = "missing_fifa_match_url_mapping"
    elif any(row["status"] == "FAIL" for row in rows) and player_data == 0:
        result = "FAIL"
        reason = "fifa_match_page_unusable"
    elif player_data:
        result = "PASS"
        reason = None
    else:
        result = "WAIT"
        reason = "no_player_level_data_yet"
    report = {
        "result": result,
        "reason": reason,
        "needs_fifa_match_url_mapping": result == "WAIT" and reason == "missing_fifa_match_url_mapping",
        "fifa_match_targets": str(matches),
        "targets": rows,
        "accessible_matches": accessible,
        "matches_with_player_data": player_data,
        "data_scope": "fifa_world_cup_match_performance",
        "not_club_recent_form": True,
    }
    _write_report(report_out, report)
    return report


def print_report(report: dict[str, Any]) -> None:
    print("P3 FIFA Match Centre Probe Report")
    print(f"- result: {report.get('result')}")
    print(f"- reason: {report.get('reason')}")
    print(f"- needs_fifa_match_url_mapping: {str(report.get('needs_fifa_match_url_mapping', False)).lower()}")
    print(f"- accessible_matches: {report.get('accessible_matches', 0)}")
    print(f"- matches_with_player_data: {report.get('matches_with_player_data', 0)}")
    for row in report.get("targets", [])[:20]:
        print(f"- match_url: {row.get('match_url')}")
        print(f"  accessible: {str(row.get('accessible')).lower()}")
        print(f"  has_lineups: {str(row.get('has_lineups')).lower()}")
        print(f"  has_substitutions: {str(row.get('has_substitutions')).lower()}")
        print(f"  has_goals: {str(row.get('has_goals')).lower()}")
        print(f"  has_assists: {str(row.get('has_assists')).lower()}")
        print(f"  has_player_stats: {str(row.get('has_player_stats')).lower()}")
        print(f"  has_match_stats: {str(row.get('has_match_stats')).lower()}")
        print(f"  public_json_detected: {str(row.get('public_json_detected')).lower()}")
        print(f"  status: {row.get('status')}")
        print(f"  reason: {row.get('reason')}")


def analyze_match_page(text: str, status_code: int | None = 200, content_type: str = "") -> dict[str, Any]:
    lower = text.lower()
    login = any(marker in lower for marker in ("sign in", "log in", "login required", "subscribe", "captcha"))
    accessible = bool(status_code and 200 <= status_code < 400) and not login
    public_json = "application/json" in content_type.lower() or "__next_data__" in lower or "self.__next_f.push" in lower or _json_like(text)
    has_lineups = any(marker in lower for marker in ("lineup", "line-ups", "starting xi", "starting 11", "substitutes"))
    has_substitutions = any(marker in lower for marker in ("substitution", "substitutions", "replaced by"))
    has_goals = any(marker in lower for marker in ("goal", "goalscorer", "scorer"))
    has_assists = "assist" in lower
    has_player_stats = any(marker in lower for marker in ("player stats", "player statistics", "minutes played", "playerstats", "players"))
    has_match_stats = any(marker in lower for marker in ("match stats", "match statistics", "possession", "shots on target"))
    if login:
        status = "FAIL"
        reason = "login_or_access_wall_detected"
    elif not accessible:
        status = "FAIL"
        reason = "page_not_accessible"
    elif has_lineups or has_player_stats or public_json:
        status = "PASS"
        reason = None
    else:
        status = "WAIT"
        reason = "no_player_level_data_detected"
    return {
        "accessible": accessible,
        "has_lineups": has_lineups,
        "has_substitutions": has_substitutions,
        "has_goals": has_goals,
        "has_assists": has_assists,
        "has_player_stats": has_player_stats,
        "has_match_stats": has_match_stats,
        "public_json_detected": public_json,
        "status": status,
        "reason": reason,
    }


def _probe_target(target: ProbeTarget) -> dict[str, Any]:
    if not target.fifa_match_url:
        analysis = {
            "accessible": False,
            "has_lineups": False,
            "has_substitutions": False,
            "has_goals": False,
            "has_assists": False,
            "has_player_stats": False,
            "has_match_stats": False,
            "public_json_detected": False,
            "status": "WAIT",
            "reason": "missing_fifa_match_url",
        }
    else:
        try:
            status_code, content_type, text = _fetch_text(target.fifa_match_url)
            analysis = analyze_match_page(text, status_code=status_code, content_type=content_type)
        except Exception as exc:  # pragma: no cover - exercised via CLI only
            analysis = {
                "accessible": False,
                "has_lineups": False,
                "has_substitutions": False,
                "has_goals": False,
                "has_assists": False,
                "has_player_stats": False,
                "has_match_stats": False,
                "public_json_detected": False,
                "status": "FAIL",
                "reason": f"fetch_error:{type(exc).__name__}",
            }
    return {
        "project_match_id": target.project_match_id,
        "match_url": target.fifa_match_url,
        "home_team": target.home_team,
        "away_team": target.away_team,
        **analysis,
    }


def _has_player_data(row: dict[str, Any]) -> bool:
    return bool(row.get("accessible") and (row.get("has_lineups") or row.get("has_player_stats") or row.get("public_json_detected")))


def _fetch_text(url: str) -> tuple[int | None, str, str]:
    if _looks_local_path(url):
        path = Path(url)
        return 200, "application/json" if path.suffix.lower() == ".json" else "text/html", path.read_text(encoding="utf-8")[:MAX_TEXT_BYTES]
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as response:
        raw = response.read(MAX_TEXT_BYTES)
        return response.status, response.headers.get("content-type", ""), raw.decode("utf-8", errors="replace")


def _looks_local_path(value: str) -> bool:
    return bool(value) and not re.match(r"https?://", value, flags=re.I) and Path(value).exists()


def _json_like(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _read_targets(path: Path) -> list[ProbeTarget]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            ProbeTarget(
                project_match_id=str(row.get("project_match_id") or "").strip(),
                fifa_match_url=str(row.get("fifa_match_url") or "").strip(),
                home_team=str(row.get("home_team") or "").strip(),
                away_team=str(row.get("away_team") or "").strip(),
                kickoff_at=str(row.get("kickoff_at") or "").strip(),
                status=str(row.get("status") or "").strip(),
            )
            for row in reader
        ]


def _write_target_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=TARGET_COLUMNS).writeheader()


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P3 FIFA MatchData Report",
        "",
        "## Scope",
        "- data_scope: fifa_world_cup_match_performance",
        "- not_club_recent_form: true",
        "- source: FIFA World Cup official Match Centre public pages or public JSON loaded by those pages",
        "",
        "## Probe Summary",
        f"- result: {report.get('result')}",
        f"- reason: {report.get('reason')}",
        f"- needs_fifa_match_url_mapping: {str(report.get('needs_fifa_match_url_mapping', False)).lower()}",
        f"- fifa_match_targets: `{report.get('fifa_match_targets')}`",
        f"- accessible_matches: {report.get('accessible_matches', 0)}",
        f"- matches_with_player_data: {report.get('matches_with_player_data', 0)}",
        "",
        "## Match Rows",
    ]
    for row in report.get("targets", [])[:50]:
        lines.extend(
            [
                f"- match_url: {row.get('match_url')}",
                f"  accessible: {str(row.get('accessible')).lower()}",
                f"  has_lineups: {str(row.get('has_lineups')).lower()}",
                f"  has_substitutions: {str(row.get('has_substitutions')).lower()}",
                f"  has_goals: {str(row.get('has_goals')).lower()}",
                f"  has_assists: {str(row.get('has_assists')).lower()}",
                f"  has_player_stats: {str(row.get('has_player_stats')).lower()}",
                f"  has_match_stats: {str(row.get('has_match_stats')).lower()}",
                f"  public_json_detected: {str(row.get('public_json_detected')).lower()}",
                f"  status: {row.get('status')}",
                f"  reason: {row.get('reason')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Safety",
            "FIFA MatchData is official World Cup match performance data. It is not club recent form. If URL mapping or player-level data is missing, P3-Light remains WAIT and betting should not be enabled.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe FIFA Match Centre pages for P3-Light player-level data")
    parser.add_argument("--matches", type=Path, default=DEFAULT_MATCHES)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args(argv)
    report = probe_match_centre(matches=args.matches, report_out=args.report_out)
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

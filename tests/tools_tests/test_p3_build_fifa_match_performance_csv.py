from __future__ import annotations

import csv
import json
from pathlib import Path

from model import p3_ingest
from tools import p3_build_fifa_match_performance_csv as builder


SQUAD_HEADER = (
    "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,"
    "xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
)


def test_builder_missing_url_mapping_waits_without_fake_csv(tmp_path: Path) -> None:
    report = builder.build_fifa_match_performance_csv(
        matches=tmp_path / "missing.csv",
        squad=_write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")]),
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["result"] == "WAIT"
    assert report["blocker"] == "missing_fifa_match_url_mapping"
    assert report["sample_rows"] == 0
    assert report["would_write_db"] is False
    assert not (tmp_path / "sample.csv").exists()


def test_builder_match_not_started_or_no_player_data_waits(tmp_path: Path) -> None:
    payload = tmp_path / "match.json"
    payload.write_text(json.dumps({"match": {"status": "scheduled"}}), encoding="utf-8")
    targets = _write_targets(tmp_path, str(payload))

    report = builder.build_fifa_match_performance_csv(
        matches=targets,
        squad=_write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")]),
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["result"] == "WAIT"
    assert report["blocker"] == "no_player_level_data_yet"
    assert report["sample_rows"] == 0


def test_lineups_substitutions_goals_and_assists_build_sample(tmp_path: Path) -> None:
    payload = tmp_path / "match.json"
    payload.write_text(json.dumps(_match_payload()), encoding="utf-8")
    targets = _write_targets(tmp_path, str(payload))
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])
    out = tmp_path / "real_performance_fifa_match_sample.csv"

    report = builder.build_fifa_match_performance_csv(
        matches=targets,
        squad=squad,
        out=out,
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    rows = _read_csv(out)
    assert report["result"] == "PASS"
    assert report["sample_rows"] == 1
    assert rows[0]["team"] == "Mexico"
    assert rows[0]["minutes_recent"] == "70"
    assert rows[0]["goals_recent"] == "1"
    assert rows[0]["assists_recent"] == "1"
    assert rows[0]["xg_recent"] == ""
    assert rows[0]["xa_recent"] == ""
    assert "unavailable_xg_xa" in rows[0]["notes"]
    assert "not_club_recent_form" in rows[0]["notes"]
    assert report["would_write_db"] is False


def test_absent_assist_is_not_guessed(tmp_path: Path) -> None:
    payload_data = _match_payload()
    payload_data["events"] = [{"type": "goal", "player": {"id": "p1", "name": "Mexico Player"}, "team": {"name": "Mexico"}}]
    payload = tmp_path / "match.json"
    payload.write_text(json.dumps(payload_data), encoding="utf-8")

    report = builder.build_fifa_match_performance_csv(
        matches=_write_targets(tmp_path, str(payload)),
        squad=_write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")]),
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    rows = _read_csv(tmp_path / "sample.csv")
    assert report["sample_rows"] == 1
    assert rows[0]["assists_recent"] == "0"


def test_unmatched_and_fuzzy_players_do_not_enter_main_csv(tmp_path: Path) -> None:
    payload = tmp_path / "match.json"
    data = _match_payload(player_name="Mexico Plaer")
    payload.write_text(json.dumps(data), encoding="utf-8")

    report = builder.build_fifa_match_performance_csv(
        matches=_write_targets(tmp_path, str(payload)),
        squad=_write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")]),
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["sample_rows"] == 0
    unmatched = _read_csv(tmp_path / "unmatched.csv")
    assert unmatched[0]["reason"] == "no_exact_project_roster_match"


def test_sample_csv_can_be_validated_and_coverage_below_threshold(tmp_path: Path) -> None:
    payload = tmp_path / "match.json"
    payload.write_text(json.dumps(_match_payload()), encoding="utf-8")
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club"), ("Mexico", "Other Player", "Club")])
    out = tmp_path / "real_performance_fifa_match_sample.csv"

    report = builder.build_fifa_match_performance_csv(
        matches=_write_targets(tmp_path, str(payload)),
        squad=squad,
        out=out,
        unmatched_out=tmp_path / "real_performance_unmatched_fifa.csv",
        report_out=tmp_path / "report.md",
    )
    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)
    features = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=True)

    assert report["gbm_ready"] is False
    assert validation["ok"] is True
    assert validation["performance_rows_validated"] == 1
    assert features["gbm_ready"] is False
    assert features["candidate_w_gbm"] == 0


def _match_payload(player_name: str = "Mexico Player") -> dict:
    return {
        "lineups": [
            {
                "team": {"name": "Mexico"},
                "players": [
                    {"id": "p1", "name": player_name, "starting": True},
                    {"id": "p2", "name": "Bench Player", "starting": False},
                ],
            }
        ],
        "substitutions": [
            {
                "minute": 70,
                "team": {"name": "Mexico"},
                "playerOff": {"id": "p1", "name": player_name},
                "playerOn": {"id": "p2", "name": "Bench Player"},
            }
        ],
        "events": [
            {
                "type": "goal",
                "team": {"name": "Mexico"},
                "player": {"id": "p1", "name": player_name},
                "assist": {"id": "p1", "name": player_name},
            }
        ],
    }


def _write_targets(tmp_path: Path, url: str) -> Path:
    path = tmp_path / "targets.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["project_match_id", "fifa_match_url", "home_team", "away_team", "kickoff_at", "status"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "project_match_id": "test-1",
                "fifa_match_url": url,
                "home_team": "Mexico",
                "away_team": "South Africa",
                "kickoff_at": "2026-06-12T00:00:00Z",
                "status": "finished",
            }
        )
    return path


def _write_squad(tmp_path: Path, players: list[tuple[str, str, str]]) -> Path:
    for filename in ("manual_real_squad.csv", "manual_real_player_stats.csv", "manual_real_injuries.csv"):
        with (tmp_path / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "team",
                    "player_name",
                    "position",
                    "age",
                    "club",
                    "minutes_recent",
                    "goals_recent",
                    "assists_recent",
                    "xg_recent",
                    "xa_recent",
                    "injury_status",
                    "source",
                    "retrieved_at",
                    "confidence",
                    "notes",
                ],
            )
            writer.writeheader()
            for team, name, club in players:
                writer.writerow(
                    {
                        "team": team,
                        "player_name": name,
                        "position": "FW",
                        "age": "25",
                        "club": club,
                        "source": "manual",
                        "retrieved_at": "2026-06-12",
                        "confidence": "high",
                        "notes": "test",
                    }
                )
    return tmp_path / "manual_real_squad.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

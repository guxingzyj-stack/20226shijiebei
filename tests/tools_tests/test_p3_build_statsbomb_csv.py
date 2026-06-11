from __future__ import annotations

import csv
import json
from pathlib import Path

from tools import p3_build_statsbomb_csv as builder


SQUAD_HEADER = (
    "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,"
    "xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
)


def test_missing_statsbomb_root_returns_wait(tmp_path: Path) -> None:
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])

    report = builder.build_statsbomb_csv(
        statsbomb_root=tmp_path / "missing",
        squad=squad,
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["result"] == "WAIT"
    assert report["blocker"] == "statsbomb_root_missing"
    assert report["would_write_db"] is False


def test_does_not_require_players_json(tmp_path: Path) -> None:
    root = _statsbomb_root(tmp_path)
    _write_match(root, match_id=1)
    _write_lineups(root, match_id=1, player_name="Mexico Player")
    _write_events(root, match_id=1, player_name="Mexico Player")
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])

    report = builder.build_statsbomb_csv(
        statsbomb_root=root,
        squad=squad,
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["result"] == "PASS"
    assert not (root / "data" / "players" / "players.json").exists()


def test_goals_assists_minutes_and_blank_xg_xa_are_written(tmp_path: Path) -> None:
    root = _statsbomb_root(tmp_path)
    _write_match(root, match_id=1)
    _write_lineups(root, match_id=1, player_name="Mexico Player")
    _write_events(root, match_id=1, player_name="Mexico Player")
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])
    out = tmp_path / "sample.csv"

    report = builder.build_statsbomb_csv(
        statsbomb_root=root,
        squad=squad,
        out=out,
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    rows = _read_csv(out)
    assert report["sample_rows"] == 1
    assert rows[0]["team"] == "Mexico"
    assert rows[0]["minutes_recent"] == "75"
    assert rows[0]["goals_recent"] == "1"
    assert rows[0]["assists_recent"] == "1"
    assert rows[0]["xg_recent"] == ""
    assert rows[0]["xa_recent"] == ""
    assert "unavailable_xg_xa" in rows[0]["notes"]
    assert report["would_write_db"] is False


def test_uncertain_minutes_do_not_enter_main_csv(tmp_path: Path) -> None:
    root = _statsbomb_root(tmp_path)
    _write_match(root, match_id=1)
    _write_lineups(root, match_id=1, player_name="Mexico Player", positions=[])
    _write_events(root, match_id=1, player_name="Mexico Player")
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])

    report = builder.build_statsbomb_csv(
        statsbomb_root=root,
        squad=squad,
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["sample_rows"] == 0
    assert report["unmatched_rows"] == 1
    unmatched = _read_csv(tmp_path / "unmatched.csv")
    assert unmatched[0]["reason"] == "minutes_not_reliably_estimated"


def test_unmatched_player_stays_out_of_main_csv(tmp_path: Path) -> None:
    root = _statsbomb_root(tmp_path)
    _write_match(root, match_id=1)
    _write_lineups(root, match_id=1, player_name="StatsBomb Only")
    _write_events(root, match_id=1, player_name="StatsBomb Only")
    squad = _write_squad(tmp_path, [("Mexico", "Mexico Player", "Club")])

    report = builder.build_statsbomb_csv(
        statsbomb_root=root,
        squad=squad,
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["sample_rows"] == 0
    assert report["unmatched_rows"] == 1
    assert _read_csv(tmp_path / "sample.csv") == []


def test_coverage_below_threshold_keeps_gbm_not_ready(tmp_path: Path) -> None:
    root = _statsbomb_root(tmp_path)
    _write_match(root, match_id=1)
    _write_lineups(root, match_id=1, player_name="Mexico Player 1")
    _write_events(root, match_id=1, player_name="Mexico Player 1")
    squad = _write_squad(
        tmp_path,
        [
            ("Mexico", "Mexico Player 1", "Club"),
            ("Mexico", "Mexico Player 2", "Club"),
        ],
    )

    report = builder.build_statsbomb_csv(
        statsbomb_root=root,
        squad=squad,
        out=tmp_path / "sample.csv",
        unmatched_out=tmp_path / "unmatched.csv",
        report_out=tmp_path / "report.md",
    )

    assert report["coverage_by_team"]["Mexico"]["ratio"] == 0.5
    assert report["teams_below_70_percent"] == ["Mexico"]
    assert report["gbm_ready"] is False
    assert report["candidate_w_gbm"] == 0


def _statsbomb_root(tmp_path: Path) -> Path:
    root = tmp_path / "statsbomb_open_data"
    (root / "data" / "matches" / "1").mkdir(parents=True)
    (root / "data" / "events").mkdir(parents=True)
    (root / "data" / "lineups").mkdir(parents=True)
    (root / "data" / "competitions.json").write_text(
        json.dumps(
            [
                {
                    "competition_id": 1,
                    "season_id": 1,
                    "competition_name": "Test Cup",
                    "season_name": "2026",
                }
            ]
        ),
        encoding="utf-8",
    )
    return root


def _write_match(root: Path, match_id: int) -> None:
    (root / "data" / "matches" / "1" / "1.json").write_text(
        json.dumps(
            [
                {
                    "match_id": match_id,
                    "match_date": "2026-06-12",
                    "home_team": {"home_team_name": "Mexico"},
                    "away_team": {"away_team_name": "South Africa"},
                }
            ]
        ),
        encoding="utf-8",
    )


def _write_lineups(root: Path, match_id: int, player_name: str, positions: list[dict] | None = None) -> None:
    if positions is None:
        positions = [{"from": "00:00", "to": "75:00", "position": "Center Forward"}]
    (root / "data" / "lineups" / f"{match_id}.json").write_text(
        json.dumps(
            [
                {
                    "team_name": "Mexico",
                    "lineup": [
                        {
                            "player_id": 10,
                            "player_name": player_name,
                            "positions": positions,
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )


def _write_events(root: Path, match_id: int, player_name: str) -> None:
    (root / "data" / "events" / f"{match_id}.json").write_text(
        json.dumps(
            [
                {
                    "id": "pass-1",
                    "type": {"name": "Pass"},
                    "player": {"id": 10, "name": player_name},
                    "pass": {"goal_assist": True},
                },
                {
                    "id": "shot-1",
                    "type": {"name": "Shot"},
                    "player": {"id": 10, "name": player_name},
                    "shot": {"outcome": {"name": "Goal"}},
                },
            ]
        ),
        encoding="utf-8",
    )


def _write_squad(tmp_path: Path, players: list[tuple[str, str, str]]) -> Path:
    path = tmp_path / "manual_real_squad.csv"
    lines = [SQUAD_HEADER]
    for team, name, club in players:
        lines.append(f"{team},{name},FW,25,{club},,,,,,,,manual,2026-06-12,high,test\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

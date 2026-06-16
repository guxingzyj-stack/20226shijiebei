from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api import import_script_predictions
from api import script_compare
from api.main import app


def test_script_prediction_migration_creates_only_independent_table() -> None:
    sql = Path("db/migrations/009_script_predictions.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists script_predictions" in sql
    assert "alter table matches" not in sql
    assert "alter table predictions" not in sql
    assert "alter table odds_snapshots" not in sql
    assert "alter table bets" not in sql


def test_script_prediction_json_loads_72_rows() -> None:
    rows = import_script_predictions.load_script_prediction_file()

    assert len(rows) == 72
    assert rows[0]["home_team"]
    assert rows[0]["away_team"]
    assert Path("api/script_assets/script_predictions_groupstage.json").is_file()


def test_import_script_is_idempotent_and_only_targets_script_table() -> None:
    source = inspect.getsource(import_script_predictions).lower()

    assert "on conflict (home_team, away_team, stage) do update" in source
    assert "insert into script_predictions" in source
    assert "insert into matches" not in source
    assert "update matches" not in source
    assert "delete from matches" not in source
    assert "insert into predictions" not in source
    assert "update predictions" not in source
    assert "insert into odds_snapshots" not in source
    assert "insert into bets" not in source
    assert "from model" not in source
    assert "import model" not in source


def test_root_import_script_is_thin_wrapper() -> None:
    source = Path("scripts/import_script_predictions.py").read_text(encoding="utf-8")

    assert "from api.import_script_predictions import main" in source
    assert "INSERT INTO" not in source.upper()


def test_script_assets_are_inside_api_package() -> None:
    api_json = Path("api/script_assets/script_predictions_groupstage.json")
    api_importer = Path("api/import_script_predictions.py")

    assert api_json.is_file()
    assert api_importer.is_file()
    assert len(import_script_predictions.load_script_prediction_file(api_json)) == 72


def test_import_script_dry_run_does_not_write_db(monkeypatch, capsys) -> None:
    called = False

    def fake_upsert(rows):
        nonlocal called
        called = True
        return len(rows)

    monkeypatch.setattr(import_script_predictions, "upsert_script_predictions", fake_upsert)

    exit_code = import_script_predictions.main(["--dry-run"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called is False
    assert "- mode: dry-run" in output
    assert "- rows_loaded: 72" in output
    assert "- rows_upserted: 0" in output
    assert "- would_write_db: False" in output


def test_script_compare_handles_same_and_reversed_home_away_and_hits() -> None:
    scripts = [
        _script("A", "墨 西 哥", "南 非", 2, 0, is_real=True),
        _script("A", "卡 塔 尔", "瑞 士", 2, 1),
        _script("A", "美国", "巴拉圭", 0, 0),
        _script("A", "不存在主队", "不存在客队", 1, 0),
    ]
    matches = [
        _match("m1", "墨西哥", "南非", "finished", 2, 0),
        _match("m2", "瑞士", "卡塔尔", "completed", 1, 2),
        _match("m3", "美国", "巴拉圭", "scheduled", None, None),
    ]
    items = script_compare.build_script_match_items(
        scripts,
        matches,
        {
            "m1": {"p_home": 0.6, "p_draw": 0.25, "p_away": 0.15},
            "m2": {"probabilities": {"home": 0.2, "draw": 0.3, "away": 0.5}},
        },
    )
    overview = script_compare.build_script_overview(items)

    assert items[0]["status"] == script_compare.COMPARED
    assert items[0]["real_score"] == "2:0"
    assert items[0]["direction_hit"] is True
    assert items[0]["exact_hit"] is True
    assert items[0]["model_prob"] == {"home": 0.6, "draw": 0.25, "away": 0.15}
    assert items[0]["is_real"] is True
    assert items[0]["sample_type"] == "known_result_seed"
    assert items[0]["excluded_from_prediction_metrics"] is True
    assert items[0]["comment"] == script_compare.COMMENT_REAL_SAMPLE

    assert items[1]["status"] == script_compare.COMPARED
    assert items[1]["real_score"] == "2:1"
    assert items[1]["exact_hit"] is True
    assert items[1]["model_prob"] == {"home": 0.2, "draw": 0.3, "away": 0.5}
    assert items[1]["is_real"] is False
    assert items[1]["sample_type"] == "script_projection"
    assert items[1]["excluded_from_prediction_metrics"] is False

    assert items[2]["status"] == script_compare.PENDING
    assert items[2]["direction_hit"] is None
    assert items[3]["status"] == script_compare.NOT_YET

    assert overview["total_predictions"] == 4
    assert overview["compared_count"] == 2
    assert overview["all_direction_hits"] == 2
    assert overview["all_exact_hits"] == 2
    assert overview["all_direction_accuracy"] == 1.0
    assert overview["all_exact_accuracy"] == 1.0
    assert overview["real_count"] == 1
    assert overview["real_direction_hits"] == 1
    assert overview["real_exact_hits"] == 1
    assert overview["real_direction_accuracy"] == 1.0
    assert overview["real_exact_accuracy"] == 1.0
    assert overview["script_count"] == 1
    assert overview["script_direction_hits"] == 1
    assert overview["script_exact_hits"] == 1
    assert overview["script_direction_accuracy"] == 1.0
    assert overview["script_exact_accuracy"] == 1.0
    assert overview["direction_hits"] == overview["script_direction_hits"]
    assert overview["exact_hits"] == overview["script_exact_hits"]
    assert overview["direction_accuracy"] == overview["script_direction_accuracy"]
    assert overview["exact_accuracy"] == overview["script_exact_accuracy"]


def test_script_overview_excludes_known_real_samples_from_main_accuracy() -> None:
    items = [
        {"status": script_compare.COMPARED, "is_real": True, "direction_hit": True, "exact_hit": True},
        {"status": script_compare.COMPARED, "is_real": True, "direction_hit": True, "exact_hit": True},
        {"status": script_compare.COMPARED, "is_real": False, "direction_hit": True, "exact_hit": False},
        {"status": script_compare.COMPARED, "is_real": False, "direction_hit": False, "exact_hit": False},
    ]

    overview = script_compare.build_script_overview(items)

    assert overview["compared_count"] == 4
    assert overview["all_direction_accuracy"] == 0.75
    assert overview["all_exact_accuracy"] == 0.5
    assert overview["real_count"] == 2
    assert overview["real_exact_accuracy"] == 1.0
    assert overview["script_count"] == 2
    assert overview["script_direction_hits"] == 1
    assert overview["script_exact_hits"] == 0
    assert overview["script_direction_accuracy"] == 0.5
    assert overview["script_exact_accuracy"] == 0.0
    assert overview["direction_accuracy"] == overview["script_direction_accuracy"]
    assert overview["exact_accuracy"] == overview["script_exact_accuracy"]


def test_script_compare_is_real_does_not_override_real_score() -> None:
    scripts = [_script("A", "墨西哥", "南非", 0, 5, is_real=True)]
    matches = [_match("m1", "墨西哥", "南非", "finished", 2, 0)]

    item = script_compare.build_script_match_items(scripts, matches, {})[0]

    assert item["status"] == script_compare.COMPARED
    assert item["direction_hit"] is False
    assert item["exact_hit"] is False
    assert item["is_real"] is True
    assert item["comment"] == script_compare.COMMENT_REAL_SAMPLE


def test_script_compare_reads_latest_prediction_by_match_order() -> None:
    source = " ".join(inspect.getsource(script_compare._load_latest_predictions).split()).lower()

    assert "from predictions" in source
    assert "where match_id = %s" in source
    assert "order by created_at desc, id desc" in source


def test_script_api_routes_return_expected_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.main.script_compare.script_overview",
        lambda: {
            "total_predictions": 72,
            "compared_count": 1,
            "pending_count": 70,
            "not_yet_count": 1,
            "direction_hits": 1,
            "exact_hits": 1,
            "direction_accuracy": 1,
            "exact_accuracy": 1,
        },
    )
    monkeypatch.setattr(
        "api.main.script_compare.script_matches",
        lambda group=None, stage=None: {
            "overview": {"total_predictions": 1},
            "matches": [
                {
                    "group": group or "A",
                    "stage": stage or "group",
                    "home_team": "墨西哥",
                    "away_team": "南非",
                    "script_score": "2:0",
                    "narrative": "东道主主场制胜",
                    "status": "COMPARED",
                    "real_score": "2:0",
                    "direction_hit": True,
                    "exact_hit": True,
                    "is_real": False,
                    "sample_type": "script_projection",
                    "excluded_from_prediction_metrics": False,
                    "model_prob": {"home": 0.6, "draw": 0.25, "away": 0.15},
                    "comment": script_compare.COMMENT_EXACT,
                }
            ],
        },
    )

    client = TestClient(app)
    overview = client.get("/api/script/overview").json()
    matches = client.get("/api/script/matches?group=A&stage=group").json()

    assert overview["total_predictions"] == 72
    assert matches["matches"][0]["group"] == "A"
    assert matches["matches"][0]["script_score"] == "2:0"
    assert matches["matches"][0]["is_real"] is False
    assert matches["matches"][0]["sample_type"] == "script_projection"
    assert matches["matches"][0]["excluded_from_prediction_metrics"] is False
    assert matches["matches"][0]["model_prob"]["home"] == 0.6
    assert matches["matches"][0]["comment"] == script_compare.COMMENT_EXACT


def test_script_compare_module_does_not_write_core_tables() -> None:
    source = Path("api/script_compare.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "insert into matches",
        "update matches",
        "delete from matches",
        "insert into predictions",
        "update predictions",
        "delete from predictions",
        "insert into odds_snapshots",
        "update odds_snapshots",
        "delete from odds_snapshots",
        "insert into bets",
        "update bets",
        "delete from bets",
        "insert into users",
        "update users",
        "delete from users",
    ]

    for phrase in forbidden:
        assert phrase not in source


def _script(group: str, home: str, away: str, home_score: int, away_score: int, is_real: bool = False) -> dict:
    return {
        "grp": group,
        "stage": "group",
        "home_team": home,
        "away_team": away,
        "script_home": home_score,
        "script_away": away_score,
        "narrative": "测试剧本",
        "is_real": is_real,
    }


def _match(match_id: str, home: str, away: str, status: str, home_score: int | None, away_score: int | None) -> dict:
    return {
        "match_id": match_id,
        "match_num": "TEST001",
        "home_team": home,
        "away_team": away,
        "kickoff_at": datetime(2026, 6, 11, tzinfo=timezone.utc),
        "status": status,
        "result_home": home_score,
        "result_away": away_score,
    }

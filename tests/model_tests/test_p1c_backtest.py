from __future__ import annotations

from pathlib import Path

import pytest

from model import p1c_backtest


def _row(score: tuple[int, int], odds: tuple[float, float, float]) -> p1c_backtest.BacktestRow:
    return p1c_backtest.BacktestRow(
        match_date="2024-01-01",
        home_team="A",
        away_team="B",
        home_score=score[0],
        away_score=score[1],
        market_home_odds=odds[0],
        market_draw_odds=odds[1],
        market_away_odds=odds[2],
        bookmaker="manual",
        snapshot_time="2024-01-01T00:00:00Z",
        source="manual_csv",
    )


def test_rps_and_weight_search_find_market_weight_for_market_like_rows() -> None:
    rows = [
        _row((2, 0), (1.2, 8.0, 12.0)),
        _row((1, 1), (8.0, 1.2, 12.0)),
        _row((0, 2), (12.0, 8.0, 1.2)),
    ]
    result = p1c_backtest.run_backtest(rows, min_matches=3)

    assert result["result"] == "PASS"
    assert result["market_rps"] < result["dc_rps"]
    assert result["best_w_dc"] == 0.0
    assert result["blended_rps"] == pytest.approx(result["market_rps"])


def test_insufficient_rows_waits_without_fake_metrics() -> None:
    result = p1c_backtest.run_backtest([], min_matches=1)

    assert result["result"] == "WAIT"
    assert result["status"] == "insufficient_historical_market_data"
    assert result["market_rps"] is None
    assert result["best_w_dc"] is None


def test_manual_historical_csv_validation(tmp_path: Path) -> None:
    path = tmp_path / "historical.csv"
    path.write_text(
        "match_date,home_team,away_team,home_score,away_score,market_home_odds,market_draw_odds,market_away_odds,bookmaker,snapshot_time,source\n"
        "2024-01-01,A,B,2,1,1.80,3.40,4.00,book,2024-01-01T00:00:00Z,manual_csv\n",
        encoding="utf-8",
    )

    report = p1c_backtest.validate_manual_csv(path)

    assert report["ok"] is True
    assert report["rows"] == 1

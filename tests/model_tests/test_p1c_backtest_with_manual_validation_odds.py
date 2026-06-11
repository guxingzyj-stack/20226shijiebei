from __future__ import annotations

from pathlib import Path

from model import p1c_backtest


def test_backtest_prefers_manual_validation_odds(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    validation = tmp_path / "manual_validation_odds.csv"
    template = tmp_path / "manual_historical_market_odds_template.csv"
    header = "match_date,home_team,away_team,home_score,away_score,market_home_odds,market_draw_odds,market_away_odds,bookmaker,snapshot_time,source\n"
    validation.write_text(header + "2022-11-20,Qatar,Ecuador,0,2,3.20,3.10,2.05,500.com,2026-06-11T00:00:00+00:00,500.com\n", encoding="utf-8")
    template.write_text(header, encoding="utf-8")
    monkeypatch.setattr(p1c_backtest, "MANUAL_VALIDATION_ODDS", validation)
    monkeypatch.setattr(p1c_backtest, "MANUAL_MARKET_ODDS_TEMPLATE", template)

    report = p1c_backtest.validate_manual_csv()
    rows = p1c_backtest.load_manual_rows()

    assert report["rows"] == 1
    assert rows[0].home_team == "Qatar"
    assert p1c_backtest.discover_sources()["manual_csv"]["path"] == str(validation)


def test_backtest_weight_search_uses_real_rows_not_fake_metrics() -> None:
    rows = [
        p1c_backtest.BacktestRow("2022-11-20", "Qatar", "Ecuador", 0, 2, 5.0, 3.0, 1.5, "500.com", "2026-06-11T00:00:00+00:00", "500.com")
        for _ in range(30)
    ]

    result = p1c_backtest.run_backtest(rows)

    assert result["result"] == "PASS"
    assert result["market_rps"] is not None
    assert result["dc_rps"] is not None
    assert result["best_w_dc"] in p1c_backtest.WEIGHT_GRID

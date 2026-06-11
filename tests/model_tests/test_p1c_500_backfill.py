from __future__ import annotations

from pathlib import Path

import pytest

from model import p1c_500_backfill


def _html(home: str = "卡塔尔", away: str = "厄瓜多尔", home_score: str = "0", away_score: str = "2", home_odds: str = "3.20") -> str:
    return f"""
    <table>
      <tr class="bet-tb-tr" data-simpleleague="世界杯" data-fixtureid="1001"
          data-homesxname="{home}" data-awaysxname="{away}"
          data-matchdate="2022-11-20"
          data-homescore="{home_score}" data-awayscore="{away_score}">
        <td><p class="betbtn" data-type="nspf" data-value="3" data-sp="{home_odds}">胜</p></td>
        <td><p class="betbtn" data-type="nspf" data-value="1" data-sp="3.10">平</p></td>
        <td><p class="betbtn" data-type="nspf" data-value="0" data-sp="2.05">负</p></td>
      </tr>
    </table>
    """


def test_gbk_page_parse_odds_score_and_team_mapping() -> None:
    html = _html()
    decoded, encoding = p1c_500_backfill.decode_html(html.encode("gbk"), "text/html; charset=gbk")
    rows, missing, detected = p1c_500_backfill.parse_matches(decoded, "2022-11-20", "https://trade.500.com/jczq/?date=2022-11-20")

    assert encoding == "gbk"
    assert detected == 1
    assert missing == []
    assert len(rows) == 1
    assert rows[0].home_team == "Qatar"
    assert rows[0].away_team == "Ecuador"
    assert rows[0].home_score == 0
    assert rows[0].away_score == 2
    assert rows[0].market_home_odds == 3.20


def test_missing_team_mapping_reports_error() -> None:
    rows, missing, detected = p1c_500_backfill.parse_matches(_html(home="未知队"), "2022-11-20", "url")

    assert detected == 1
    assert rows == []
    assert missing == ["未知队"]


def test_date_mismatch_is_rejected() -> None:
    rows, missing, detected = p1c_500_backfill.parse_matches(_html(), "2022-11-21", "url")

    assert detected == 1
    assert missing == []
    assert rows == []


def test_odds_less_than_or_equal_one_is_not_parsed() -> None:
    rows, missing, detected = p1c_500_backfill.parse_matches(_html(home_odds="1.00"), "2022-11-20", "url")

    assert detected == 1
    assert missing == []
    assert rows == []


def test_validate_csv_waits_when_rows_less_than_30(tmp_path: Path) -> None:
    out = tmp_path / "odds.csv"
    row = p1c_500_backfill.ParsedMatch("2022-11-20", "Qatar", "Ecuador", 0, 2, 3.2, 3.1, 2.05, "url", "1001", "test")
    p1c_500_backfill._write_csv(out, [row])

    report = p1c_500_backfill.validate_csv(out)

    assert report["rows"] == 1
    assert report["invalid_odds_count"] == 0
    assert report["invalid_score_count"] == 0
    assert report["result"] == "WAIT"


def test_backfill_rejects_sleep_under_two_seconds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sleep_seconds"):
        p1c_500_backfill.backfill("2022-11-20", "2022-11-20", 1.0, tmp_path / "out.csv")

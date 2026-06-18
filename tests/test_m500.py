import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler"))

from sources import m500  # noqa: E402
from sources.common import SourceError  # noqa: E402


class FakeResponse:
    def __init__(self, html: str, url: str = "https://trade.500.com/jczq/") -> None:
        self.status_code = 200
        self.url = url
        self.content = html.encode("gbk", errors="ignore")


class FakeSession:
    def __init__(self, pages: dict[tuple[str, str], str]) -> None:
        self.pages = pages
        self.calls: list[dict[str, str]] = []

    def get(self, url: str, params=None, headers=None, timeout=None):  # noqa: ANN001
        params = dict(params or {})
        self.calls.append(params)
        play = params.get("playid", "had_hhad")
        date_text = params.get("date", "")
        return FakeResponse(self.pages.get((date_text, play), "<html><body></body></html>"))


def _had_row(match_id: str, date_text: str, match_num: str = "001") -> str:
    return f"""
    <table><tr class="bet-tb-tr" data-fixtureid="{match_id}" data-homesxname="Home {match_id}"
      data-awaysxname="Away {match_id}" data-matchdate="{date_text}" data-matchtime="20:00"
      data-rangqiu="-1" data-simpleleague="World Cup" data-matchnum="{match_num}" data-isend="0">
      <td>
        <p class="betbtn" data-sp="1.80" data-type="nspf" data-value="3"></p>
        <p class="betbtn" data-sp="3.20" data-type="nspf" data-value="1"></p>
        <p class="betbtn" data-sp="4.50" data-type="nspf" data-value="0"></p>
        <p class="betbtn" data-sp="2.40" data-type="spf" data-value="3"></p>
        <p class="betbtn" data-sp="3.50" data-type="spf" data-value="1"></p>
        <p class="betbtn" data-sp="2.10" data-type="spf" data-value="0"></p>
      </td>
    </tr></table>
    """


def _crs_row(match_id: str, date_text: str) -> str:
    return f"""
    <table>
      <tr class="bet-tb-tr" data-fixtureid="{match_id}" data-homesxname="Home {match_id}"
        data-awaysxname="Away {match_id}" data-matchdate="{date_text}" data-matchtime="20:00"
        data-simpleleague="World Cup" data-matchnum="001" data-isend="0"></tr>
      <tr class="bet-more-wrap">
        <td><p class="sbetbtn" data-sp="6.00" data-type="bf" data-value="1:0"></p></td>
      </tr>
    </table>
    """


class M500ParserTests(unittest.TestCase):
    def test_empty_intercept_page_is_failure(self) -> None:
        html = "<html><body><h1>Access Verification</h1><p>No match table here.</p></body></html>"
        with self.assertRaises(SourceError):
            m500.parse_html_or_raise(html, "2026-06-10")

    def test_had_hhad_world_cup_row_parses(self) -> None:
        html = """
        <table><tr class="bet-tb-tr" data-fixtureid="1359172" data-homesxname="墨西哥"
          data-awaysxname="南非" data-matchdate="2026-06-12" data-matchtime="03:00"
          data-rangqiu="-1" data-simpleleague="世界杯" data-matchnum="周四001" data-isend="0">
          <td class="td td-betbtn">
            <div class="betbtn-row itm-rangB1">
              <p class="betbtn" data-sp="1.30" data-type="nspf" data-value="3"></p>
              <p class="betbtn" data-sp="4.15" data-type="nspf" data-value="1"></p>
              <p class="betbtn" data-sp="8.40" data-type="nspf" data-value="0"></p>
            </div>
            <div class="betbtn-row itm-rangB2">
              <p class="betbtn" data-sp="2.07" data-type="spf" data-value="3"></p>
              <p class="betbtn" data-sp="3.28" data-type="spf" data-value="1"></p>
              <p class="betbtn" data-sp="2.93" data-type="spf" data-value="0"></p>
            </div>
          </td>
        </tr></table>
        """
        matches = m500.parse_html_or_raise(html, "2026-06-10")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].match_id, "500-1359172")
        self.assertEqual({entry.play_type for entry in matches[0].odds}, {"had", "hhad"})
        self.assertEqual(matches[0].status, "scheduled")

    def test_sale_closed_is_not_finished(self) -> None:
        html = """
        <table><tr class="bet-tb-tr" data-fixtureid="1359172" data-homesxname="Mexico"
          data-awaysxname="South Africa" data-matchdate="2026-06-12" data-matchtime="03:00"
          data-simpleleague="世界杯" data-matchnum="001" data-isend="1">
          <td class="td td-betbtn">
            <p class="betbtn" data-sp="1.30" data-type="nspf" data-value="3"></p>
            <p class="betbtn" data-sp="4.15" data-type="nspf" data-value="1"></p>
            <p class="betbtn" data-sp="8.40" data-type="nspf" data-value="0"></p>
          </td>
        </tr></table>
        """

        matches = m500.parse_html_or_raise(html, "2026-06-10")

        self.assertEqual(matches[0].status, "closed")

    def test_full_scan_parses_multiple_dates_without_real_network(self) -> None:
        pages = {
            ("2026-06-20", "had_hhad"): _had_row("1359300", "2026-06-20", "020"),
            ("2026-06-21", "had_hhad"): _had_row("1359301", "2026-06-21", "021"),
        }
        session = FakeSession(pages)

        matches = m500.fetch_full_scan(session, date_texts=["2026-06-20", "2026-06-21", "2026-06-22"])

        self.assertEqual([match.match_id for match in matches], ["500-1359300", "500-1359301"])
        self.assertTrue(all(match.match_id.startswith("500-") for match in matches))
        summary = m500.get_last_scan_summary()
        self.assertEqual(summary["parsed_matches_seen"], 2)
        self.assertEqual(summary["active_dates"], ["2026-06-20", "2026-06-21"])

    def test_full_scan_merges_secondary_market_odds(self) -> None:
        pages = {
            ("2026-06-20", "had_hhad"): _had_row("1359300", "2026-06-20", "020"),
            ("2026-06-20", "271"): _crs_row("1359300", "2026-06-20"),
        }
        session = FakeSession(pages)

        matches = m500.fetch_full_scan(session, date_texts=["2026-06-20"])

        self.assertEqual(len(matches), 1)
        self.assertEqual({entry.play_type for entry in matches[0].odds}, {"had", "hhad", "crs"})

    def test_full_scan_skips_secondary_pages_for_empty_dates(self) -> None:
        session = FakeSession({})

        with self.assertRaises(SourceError):
            m500.fetch_full_scan(session, date_texts=["2026-06-22"])

        self.assertEqual(session.calls, [{"date": "2026-06-22"}])

    def test_full_scan_deduplicates_repeated_sales_windows(self) -> None:
        pages = {
            ("2026-06-20", "had_hhad"): _had_row("1359300", "2026-06-20", "020"),
            ("2026-06-21", "had_hhad"): _had_row("1359300", "2026-06-20", "020"),
        }
        session = FakeSession(pages)

        matches = m500.fetch_full_scan(session, date_texts=["2026-06-20", "2026-06-21"])

        self.assertEqual(len(matches), 1)
        optional_calls = [call for call in session.calls if "playid" in call]
        self.assertEqual(len(optional_calls), 3)
        self.assertEqual(m500.get_last_scan_summary()["unique_sales_windows"], 1)


if __name__ == "__main__":
    unittest.main()

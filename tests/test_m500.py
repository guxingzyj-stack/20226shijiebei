import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler"))

from sources import m500  # noqa: E402
from sources.common import SourceError  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()

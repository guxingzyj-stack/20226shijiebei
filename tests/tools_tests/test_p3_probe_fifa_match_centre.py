from __future__ import annotations

import csv
from pathlib import Path

from tools import p3_probe_fifa_match_centre as probe


def test_probe_missing_targets_writes_template_and_waits(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "fifa_match_targets_template.csv"
    monkeypatch.setattr(probe, "DEFAULT_TEMPLATE", template)

    report = probe.probe_match_centre(matches=tmp_path / "missing.csv", report_out=tmp_path / "report.md")

    assert report["result"] == "WAIT"
    assert report["reason"] == "missing_fifa_match_url_mapping"
    assert report["needs_fifa_match_url_mapping"] is True
    assert template.exists()


def test_analyze_match_page_detects_player_data() -> None:
    html = """
    <html><script id="__NEXT_DATA__" type="application/json">{}</script>
    <body>Starting XI Lineups Substitutions Goals Assists Player Stats Match Stats</body></html>
    """

    result = probe.analyze_match_page(html, status_code=200, content_type="text/html")

    assert result["accessible"] is True
    assert result["has_lineups"] is True
    assert result["has_substitutions"] is True
    assert result["has_goals"] is True
    assert result["has_assists"] is True
    assert result["has_player_stats"] is True
    assert result["has_match_stats"] is True
    assert result["public_json_detected"] is True
    assert result["status"] == "PASS"


def test_probe_local_target_without_player_data_waits(tmp_path: Path) -> None:
    page = tmp_path / "match.html"
    page.write_text("<html><body>Match not started</body></html>", encoding="utf-8")
    targets = tmp_path / "targets.csv"
    _write_targets(targets, str(page))

    report = probe.probe_match_centre(matches=targets, report_out=tmp_path / "report.md")

    assert report["result"] == "WAIT"
    assert report["accessible_matches"] == 1
    assert report["matches_with_player_data"] == 0
    assert report["targets"][0]["reason"] == "no_player_level_data_detected"


def _write_targets(path: Path, url: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=probe.TARGET_COLUMNS)
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

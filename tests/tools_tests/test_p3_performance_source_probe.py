from __future__ import annotations

from tools import p3_performance_source_probe as probe


def test_source_probe_waits_without_usable_source() -> None:
    candidates = [
        probe.CandidateSource(
            source_name="blocked_fbref_dataset",
            url="https://example.com/fbref-derived",
            source_risk="high",
            notes="blocked",
            blocked=True,
        )
    ]

    report = probe.probe_sources(candidates=candidates, fetcher=lambda _url, _timeout: (200, "text/html", "player minutes goals assists"))

    assert report["result"] == "WAIT"
    assert report["usable_sources"] == []


def test_source_probe_accepts_low_risk_page_with_required_stats() -> None:
    candidates = [
        probe.CandidateSource(
            source_name="authorized_export_page",
            url="https://example.com/export",
            source_risk="low",
            notes="authorized",
        )
    ]

    report = probe.probe_sources(
        candidates=candidates,
        fetcher=lambda _url, _timeout: (200, "text/html", "player statistics minutes goals assists xg xa"),
    )

    assert report["result"] == "PASS"
    assert report["usable_sources"] == ["authorized_export_page"]


def test_source_probe_rejects_login_wall() -> None:
    candidates = [
        probe.CandidateSource(
            source_name="login_source",
            url="https://example.com/stats",
            source_risk="low",
            notes="login",
        )
    ]

    report = probe.probe_sources(
        candidates=candidates,
        fetcher=lambda _url, _timeout: (200, "text/html", "please log in to see player statistics minutes goals assists"),
    )

    row = report["candidate_sources"][0]
    assert report["result"] == "WAIT"
    assert row["requires_login"] is True
    assert row["recommended_use"] == "no"


def test_analyze_text_detects_required_fields() -> None:
    result = probe.analyze_text("Player statistics: minutes, goals, assists, expected goals, xA")

    assert result == {
        "contains_player_stats": True,
        "contains_minutes": True,
        "contains_goals": True,
        "contains_assists": True,
        "contains_xg_xa": True,
    }

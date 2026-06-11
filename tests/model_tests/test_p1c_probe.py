from __future__ import annotations

from dataclasses import dataclass

from model import p1c_probe


def test_url_candidate_generation_stays_within_sampled_range() -> None:
    candidates = p1c_probe.build_candidate_urls("2022-11-20", "2022-12-18")

    assert candidates
    assert all("500.com" in candidate.url for candidate in candidates)
    assert any("2022-11-20" in candidate.url for candidate in candidates)
    assert any("2022-12-18" in candidate.url for candidate in candidates)
    assert not any("2022-11-19" in candidate.url for candidate in candidates)


def test_decode_gbk_and_utf8_fallback() -> None:
    gbk_text, gbk_used = p1c_probe.decode_response("世界杯".encode("gbk"), {"content-type": "text/html; charset=gbk"})
    utf8_text, utf8_used = p1c_probe.decode_response("World Cup".encode("utf-8"), {"content-type": "text/html"})

    assert gbk_text == "世界杯"
    assert gbk_used.lower() == "gbk"
    assert utf8_text == "World Cup"
    assert utf8_used == "utf-8"


def test_odds_like_pattern_detection() -> None:
    html = "<tr class='bet-tb-tr' data-simpleleague='世界杯'><p class='betbtn' data-type='nspf' data-sp='1.23'>胜</p></tr>"

    result = p1c_probe.analyze_response("https://trade.500.com/jczq/?date=2022-11-20", 200, "text/html", html.encode(), html, "utf-8")

    assert result.contains_worldcup_keywords is True
    assert result.contains_odds_like_fields is True
    assert result.likely_usable is True


def test_score_like_pattern_detection() -> None:
    html = "<html><body>世界杯 完场 比分 2:1 data-isend='1'</body></html>"

    result = p1c_probe.analyze_response("https://live.500.com/wanchang.php?e=2022-11-20", 200, "text/html", html.encode(), html, "utf-8")

    assert result.contains_score_like_fields is True


def test_waf_or_empty_page_is_not_usable() -> None:
    html = "<html><body>captcha verify robot</body></html>"

    result = p1c_probe.analyze_response("https://trade.500.com/jczq/", 403, "text/html", html.encode(), html, "utf-8")

    assert result.likely_usable is False
    assert "waf_or_empty" in result.notes


def test_run_probe_uses_mock_session_without_real_network() -> None:
    session = MockSession(
        b"<tr class='bet-tb-tr' data-simpleleague='\xca\xc0\xbd\xe7\xb1\xad'><p data-type='nspf' data-sp='1.88'></p></tr>"
    )

    report = p1c_probe.run_probe("2022-11-20", "2022-11-20", 10, session=session)  # type: ignore[arg-type]

    assert report["summary"]["candidates_tested"] > 0
    assert report["summary"]["result"] == "PASS"
    assert session.calls > 0


@dataclass
class MockResponse:
    content: bytes
    url: str
    status_code: int = 200

    @property
    def headers(self) -> dict[str, str]:
        return {"content-type": "text/html; charset=gbk"}


class MockSession:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls = 0

    def get(self, url: str, headers: dict[str, str], timeout: float) -> MockResponse:
        _ = headers, timeout
        self.calls += 1
        return MockResponse(content=self.content, url=url)

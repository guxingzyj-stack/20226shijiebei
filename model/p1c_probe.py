from __future__ import annotations

import argparse
import html
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests


BASE_URL = "https://trade.500.com/jczq/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
PLAY_PARAMS = (
    ("had_hhad", {"playid": "269", "g": "2"}),
    ("ttg", {"playid": "270", "g": "2"}),
    ("crs", {"playid": "271", "g": "2"}),
    ("hafu", {"playid": "272", "g": "2"}),
)
WORLDCUP_KEYWORDS = ("世界杯", "世界盃", "World Cup", "worldcup", "世界杯2022")
ODDS_PATTERNS = (
    re.compile(r"data-sp=[\"'][0-9]{1,2}\.[0-9]{1,2}[\"']", re.IGNORECASE),
    re.compile(r"data-type=[\"'](?:nspf|spf|bf|jqs|bqc)[\"']", re.IGNORECASE),
    re.compile(r"\b[1-9]\d?\.\d{2}\b"),
)
SCORE_PATTERNS = (
    re.compile(r"\b\d{1,2}\s*[:：-]\s*\d{1,2}\b"),
    re.compile(r"data-(?:isend|homescore|awayscore|score)=", re.IGNORECASE),
    re.compile(r"(?:完场|已结束|赛果|比分)"),
)
WAF_PATTERNS = (
    re.compile(r"(?:waf|captcha|verify|robot|forbidden|access denied|安全验证)", re.IGNORECASE),
    re.compile(r"<script[^>]*>.*?</script>\s*<noscript", re.IGNORECASE | re.DOTALL),
)


@dataclass(frozen=True)
class Candidate:
    label: str
    url: str


@dataclass
class ProbeResult:
    url: str
    status_code: int | None
    content_type: str
    decoded_as: str
    bytes: int
    contains_worldcup_keywords: bool
    contains_odds_like_fields: bool
    contains_score_like_fields: bool
    likely_usable: bool
    notes: str
    text_summary: str
    keyword_hits: list[str]
    odds_context: str
    table_context: str


def build_candidate_urls(start_date: str, end_date: str, max_dates: int = 3) -> list[Candidate]:
    dates = _sample_dates(_parse_date(start_date), _parse_date(end_date), max_dates=max_dates)
    candidates: list[Candidate] = []
    for day in dates:
        day_text = day.isoformat()
        candidates.append(Candidate("trade_date", _url(BASE_URL, {"date": day_text})))
        for play, params in PLAY_PARAMS:
            candidates.append(Candidate(f"trade_{play}_date", _url(BASE_URL, {**params, "date": day_text})))
        candidates.append(Candidate("trade_result_date", _url("https://trade.500.com/jczq/index.php", {"date": day_text})))
        candidates.append(Candidate("score_date", _url("https://live.500.com/wanchang.php", {"e": day_text})))
    seen: set[str] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        unique.append(candidate)
    return unique


def decode_response(content: bytes, headers: dict[str, str] | None = None) -> tuple[str, str]:
    headers = headers or {}
    content_type = headers.get("content-type") or headers.get("Content-Type") or ""
    charset_match = re.search(r"charset=([a-zA-Z0-9_-]+)", content_type)
    encodings = []
    if charset_match:
        encodings.append(charset_match.group(1))
    encodings.extend(["utf-8", "gbk"])
    for encoding in dict.fromkeys(encodings):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore"), "utf-8-ignore"


def probe_url(session: requests.Session, candidate: Candidate, timeout: float) -> ProbeResult:
    try:
        response = session.get(candidate.url, headers=HEADERS, timeout=timeout)
    except Exception as exc:
        return ProbeResult(
            url=candidate.url,
            status_code=None,
            content_type="",
            decoded_as="",
            bytes=0,
            contains_worldcup_keywords=False,
            contains_odds_like_fields=False,
            contains_score_like_fields=False,
            likely_usable=False,
            notes=f"request_error: {exc}",
            text_summary="",
            keyword_hits=[],
            odds_context="",
            table_context="",
        )
    text, decoded_as = decode_response(response.content, dict(response.headers))
    return analyze_response(candidate.url, response.status_code, response.headers.get("content-type", ""), response.content, text, decoded_as)


def analyze_response(url: str, status_code: int, content_type: str, content: bytes, text: str, decoded_as: str) -> ProbeResult:
    stripped = _strip_text(text)
    keyword_hits = [keyword for keyword in WORLDCUP_KEYWORDS if keyword.lower() in text.lower()]
    contains_worldcup_keywords = bool(keyword_hits)
    contains_odds_like_fields = any(pattern.search(text) for pattern in ODDS_PATTERNS)
    contains_score_like_fields = any(pattern.search(text) for pattern in SCORE_PATTERNS)
    waf_like = _is_waf_or_empty(status_code, text)
    likely_usable = status_code == 200 and contains_worldcup_keywords and contains_odds_like_fields and not waf_like
    notes = []
    if waf_like:
        notes.append("waf_or_empty_or_js_shell")
    if contains_odds_like_fields and not contains_score_like_fields:
        notes.append("odds found; score linkage unclear")
    if contains_worldcup_keywords and not contains_odds_like_fields:
        notes.append("world cup keyword found; odds structure unclear")
    if not contains_worldcup_keywords:
        notes.append("no 2022 world cup keyword hit")
    return ProbeResult(
        url=url,
        status_code=status_code,
        content_type=content_type,
        decoded_as=decoded_as,
        bytes=len(content),
        contains_worldcup_keywords=contains_worldcup_keywords,
        contains_odds_like_fields=contains_odds_like_fields,
        contains_score_like_fields=contains_score_like_fields,
        likely_usable=likely_usable,
        notes="; ".join(notes) or "ok",
        text_summary=stripped[:300],
        keyword_hits=keyword_hits[:8],
        odds_context=_context(text, ODDS_PATTERNS),
        table_context=_table_context(text),
    )


def run_probe(start_date: str, end_date: str, timeout_seconds: float, session: requests.Session | None = None) -> dict[str, Any]:
    session = session or requests.Session()
    deadline = time.monotonic() + timeout_seconds
    results: list[ProbeResult] = []
    for candidate in build_candidate_urls(start_date, end_date):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        results.append(probe_url(session, candidate, timeout=max(0.5, min(5.0, remaining))))
    usable = [result for result in results if result.likely_usable]
    partial = [result for result in results if result.status_code == 200 and (result.contains_worldcup_keywords or result.contains_odds_like_fields)]
    if usable:
        status = "PASS"
        next_step = "Use best candidate for a small manual HTML structure review before writing backfill."
    elif partial:
        status = "WAIT"
        next_step = "Review limited HTML snippets manually; fields are not clear enough for backfill."
    else:
        status = "FAIL"
        next_step = "Do not backfill from 500.com until a usable historical page is found."
    return {
        "results": results,
        "summary": {
            "candidates_tested": len(results),
            "usable_candidates": len(usable),
            "best_candidate_url": usable[0].url if usable else (partial[0].url if partial else None),
            "recommended_next_step": next_step,
            "result": status,
        },
    }


def print_report(report: dict[str, Any]) -> None:
    print("P1-C 500.com Historical Probe Report")
    print("")
    print("1. Candidate URLs")
    for result in report["results"]:
        print(f"- url: {result.url}")
        print(f"  status_code: {result.status_code}")
        print(f"  content_type: {result.content_type}")
        print(f"  decoded_as: {result.decoded_as}")
        print(f"  bytes: {result.bytes}")
        print(f"  contains_worldcup_keywords: {str(result.contains_worldcup_keywords).lower()}")
        print(f"  contains_odds_like_fields: {str(result.contains_odds_like_fields).lower()}")
        print(f"  contains_score_like_fields: {str(result.contains_score_like_fields).lower()}")
        print(f"  likely_usable: {str(result.likely_usable).lower()}")
        print(f"  notes: {_limit(result.notes, 180)}")
        print(f"  keyword_hits: {result.keyword_hits}")
        print(f"  text_summary: {_limit(result.text_summary, 300)}")
        print(f"  odds_context: {_limit(result.odds_context, 800)}")
        print(f"  table_context: {_limit(result.table_context, 800)}")
    print("")
    print("2. Summary")
    summary = report["summary"]
    print(f"- candidates_tested: {summary['candidates_tested']}")
    print(f"- usable_candidates: {summary['usable_candidates']}")
    print(f"- best_candidate_url: {summary['best_candidate_url']}")
    print(f"- recommended_next_step: {summary['recommended_next_step']}")
    print(f"- result: {summary['result']}")


def _sample_dates(start: date, end: date, max_dates: int) -> list[date]:
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    dates = [start]
    if end != start:
        midpoint = start + timedelta(days=(end - start).days // 2)
        dates.append(midpoint)
        dates.append(end)
    unique = []
    for day in dates[:max_dates]:
        if day not in unique:
            unique.append(day)
    return unique


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _url(base: str, params: dict[str, str]) -> str:
    return f"{base}?{urlencode(params)}"


def _strip_text(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", without_tags).strip()


def _context(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 180)
            end = min(len(text), match.end() + 180)
            return _strip_text(text[start:end])
    return ""


def _table_context(text: str) -> str:
    for marker in ("bet-tb-tr", "<table", "data-simpleleague", "betbtn", "比分", "赛果"):
        index = text.lower().find(marker.lower())
        if index >= 0:
            return _strip_text(text[max(0, index - 180) : min(len(text), index + 620)])
    return ""


def _is_waf_or_empty(status_code: int, text: str) -> bool:
    if status_code in {401, 403, 429, 503}:
        return True
    stripped = _strip_text(text)
    has_probe_markers = any(keyword.lower() in text.lower() for keyword in WORLDCUP_KEYWORDS) or any(pattern.search(text) for pattern in ODDS_PATTERNS)
    if len(stripped) < 80 and not has_probe_markers:
        return True
    return any(pattern.search(text) for pattern in WAF_PATTERNS)


def _limit(value: str, limit: int) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    return value[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe 500.com historical World Cup odds page shapes")
    parser.add_argument("--start-date", default="2022-11-20")
    parser.add_argument("--end-date", default="2022-12-18")
    parser.add_argument("--timeout-seconds", type=float, default=10)
    args = parser.parse_args(argv)
    report = run_probe(args.start_date, args.end_date, args.timeout_seconds)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

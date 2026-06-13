from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import html
import re
from typing import Any
from urllib.request import Request, urlopen

from api.ops_log import sanitize_error
from api.result_source_mapping import normalize_team_name


ZHIBO8_URL = "https://www.zhibo8.cc/"
USER_AGENT = "Mozilla/5.0"
NON_FINALS_RE = re.compile(r"男篮|女篮|篮球|U\d+|青年|沙滩|室内|五人制|预选赛|电子|电竞")
NON_MATCH_RE = re.compile(r"开幕式|闭幕式|抽签|颁奖|发布会|纪录片|典礼")


@dataclass(frozen=True)
class Zhibo8Match:
    source_name: str
    zhibo8_match_ref: str | None
    zhibo8_url: str | None
    zhibo8_text_url: str | None = None
    zhibo8_score_url: str | None = None
    zhibo8_animation_url: str | None = None
    zhibo8_raw_links: list[str] | None = None
    possible_zhibo8_ids: list[str] | None = None
    possible_qiumibao_ids: list[str] | None = None
    possible_external_ids: list[str] | None = None
    home_team: str | None = None
    away_team: str | None = None
    normalized_home_team: str = ""
    normalized_away_team: str = ""
    kickoff_at: str | None = None
    league: str | None = None
    status_text: str | None = None
    score: str | None = None
    parser_error: str | None = None


def fetch_homepage(timeout: int = 15, fetcher=None) -> str:
    if fetcher is not None:
        return str(fetcher())
    req = Request(ZHIBO8_URL, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body.decode("utf-8", errors="replace")


def homepage_source_report(fetcher=fetch_homepage) -> dict[str, Any]:
    try:
        html_text = fetcher()
        matches = parse_worldcup_matches(html_text)
        return {
            "source_name": "zhibo8",
            "source_fetch_ok": True,
            "parser_error": None if matches else "parser_error: no worldcup schedule items parsed",
            "matches": [match.__dict__ for match in matches],
        }
    except Exception as exc:
        return {
            "source_name": "zhibo8",
            "source_fetch_ok": False,
            "parser_error": sanitize_error(exc),
            "matches": [],
        }


def parse_worldcup_matches(html_text: str) -> list[Zhibo8Match]:
    items = re.findall(r"<li\b[^>]*label=\"[^\"]*\"[\s\S]*?</li>", str(html_text), flags=re.I)
    matches: list[Zhibo8Match] = []
    seen: set[str] = set()
    for item in items:
        match = normalize_schedule_item(item)
        if match is None:
            continue
        key = match.zhibo8_match_ref or f"{match.home_team}-{match.away_team}-{match.kickoff_at}"
        if key in seen:
            continue
        seen.add(key)
        matches.append(match)
    return matches


def normalize_schedule_item(li_html: str) -> Zhibo8Match | None:
    label = _attr(li_html, "label") or ""
    data_type = _attr(li_html, "data-type") or ""
    data_time = _attr(li_html, "data-time") or ""
    match_ref = _first_match(li_html, r'id="saishi(\d+)"')
    if data_type and data_type != "football":
        return None
    if "世界杯" not in label:
        return None
    if NON_FINALS_RE.search(label) or NON_MATCH_RE.search(label):
        return None
    if not match_ref or match_ref == "0" or not data_time:
        return None
    league = _strip_tags(_first_match(li_html, r'<span class="_league">([\s\S]*?)</span>') or "")
    if NON_FINALS_RE.search(league) or NON_MATCH_RE.search(league):
        return None
    teams_html = _first_match(li_html, r'<span class="_teams">([\s\S]*?)</span></b>') or ""
    parts = re.split(r"<img\b[^>]*>", teams_html, flags=re.I)
    if len(parts) < 3:
        links = _raw_links(li_html)
        id_groups = _possible_id_groups(links, match_ref)
        return Zhibo8Match(
            "zhibo8",
            match_ref,
            _detail_url(li_html),
            _typed_link(links, "text"),
            _typed_link(links, "score"),
            _typed_link(links, "animation"),
            links,
            id_groups["possible_zhibo8_ids"],
            id_groups["possible_qiumibao_ids"],
            id_groups["possible_external_ids"],
            None,
            None,
            "",
            "",
            _parse_beijing_time(data_time),
            league,
            parser_error="parser_missing_team_fields",
        )
    home = _strip_tags(parts[0])
    away = _strip_tags(parts[-1])
    if not home or not away:
        links = _raw_links(li_html)
        id_groups = _possible_id_groups(links, match_ref)
        return Zhibo8Match(
            "zhibo8",
            match_ref,
            _detail_url(li_html),
            _typed_link(links, "text"),
            _typed_link(links, "score"),
            _typed_link(links, "animation"),
            links,
            id_groups["possible_zhibo8_ids"],
            id_groups["possible_qiumibao_ids"],
            id_groups["possible_external_ids"],
            home or None,
            away or None,
            normalize_team_name(home),
            normalize_team_name(away),
            _parse_beijing_time(data_time),
            league,
            parser_error="parser_missing_team_fields",
        )
    middle = _strip_tags(" ".join(parts[1:-1]))
    score = _score_from_text(middle)
    links = _raw_links(li_html)
    id_groups = _possible_id_groups(links, match_ref)
    return Zhibo8Match(
        source_name="zhibo8",
        zhibo8_match_ref=match_ref,
        zhibo8_url=_detail_url(li_html),
        zhibo8_text_url=_typed_link(links, "text"),
        zhibo8_score_url=_typed_link(links, "score"),
        zhibo8_animation_url=_typed_link(links, "animation"),
        zhibo8_raw_links=links,
        possible_zhibo8_ids=id_groups["possible_zhibo8_ids"],
        possible_qiumibao_ids=id_groups["possible_qiumibao_ids"],
        possible_external_ids=id_groups["possible_external_ids"],
        home_team=home,
        away_team=away,
        normalized_home_team=normalize_team_name(home),
        normalized_away_team=normalize_team_name(away),
        kickoff_at=_parse_beijing_time(data_time),
        league=league,
        status_text=middle or None,
        score=score,
        parser_error=None,
    )


def _attr(text: str, name: str) -> str | None:
    return _first_match(text, rf'{re.escape(name)}="([^"]*)"')


def _first_match(text: str, pattern: str) -> str | None:
    found = re.search(pattern, text, flags=re.I)
    return html.unescape(found.group(1)).strip() if found else None


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value))).strip()


def _parse_beijing_time(value: str) -> str | None:
    found = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", value or "")
    if not found:
        return None
    local = datetime(
        int(found.group(1)),
        int(found.group(2)),
        int(found.group(3)),
        int(found.group(4)),
        int(found.group(5)),
        tzinfo=timezone(timedelta(hours=8)),
    )
    return local.astimezone(timezone.utc).isoformat()


def _detail_url(text: str) -> str | None:
    path = _first_match(text, r'href="((?:https?:)?//[^"]+|/?zhibo/zuqiu/[^"]+|/?/zhibo/zuqiu/[^"]+)"')
    if not path:
        return None
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("http"):
        return path
    return "https://www.zhibo8.com" + (path if path.startswith("/") else "/" + path)


def _raw_links(text: str) -> list[str]:
    values = [_absolute_url(html.unescape(item).strip()) for item in re.findall(r'href="([^"]+)"', text, flags=re.I)]
    seen: set[str] = set()
    links: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            links.append(value)
    return links


def _absolute_url(path: str) -> str | None:
    if not path:
        return None
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("http"):
        return path
    return "https://www.zhibo8.com" + (path if path.startswith("/") else "/" + path)


def _typed_link(links: list[str], kind: str) -> str | None:
    patterns = {
        "text": ("zhibo", "live", "text"),
        "score": ("bifen", "score"),
        "animation": ("donghua", "animation", "flash", "dc"),
    }
    for link in links:
        lowered = link.lower()
        if any(pattern in lowered for pattern in patterns[kind]):
            return link
    return None


def _possible_id_groups(links: list[str], match_ref: str | None) -> dict[str, list[str]]:
    zhibo8_ids: list[str] = []
    qiumibao_ids: list[str] = []
    external_ids: list[str] = []
    if match_ref:
        zhibo8_ids.append(str(match_ref))
    for link in links:
        lowered = link.lower()
        ids = re.findall(r"(?<!\d)(\d{5,})(?!\d)", link)
        if "qiumibao.com" in lowered or "bifen4pc" in lowered or "dc4pc" in lowered or "match_event" in lowered:
            qiumibao_ids.extend(ids)
        elif "zhibo8.com" in lowered or "zhibo8.cc" in lowered or re.search(r"match\d+v?", lowered):
            zhibo8_ids.extend(ids)
        else:
            external_ids.extend(ids)
    return {
        "possible_zhibo8_ids": _dedupe(zhibo8_ids),
        "possible_qiumibao_ids": _dedupe(qiumibao_ids),
        "possible_external_ids": _dedupe(external_ids),
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _score_from_text(value: str) -> str | None:
    text = re.sub(r"大比分\d+\s*-\s*\d+", "", value or "")
    found = re.search(r"(\d+)\s*-\s*(\d+)", text)
    return f"{found.group(1)}-{found.group(2)}" if found else None

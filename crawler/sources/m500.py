from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import time
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag

from sources.common import MatchOdds, OddsEntry, SourceError, clean_float, is_world_cup_league


SOURCE_NAME = "500"
BASE_URL = "https://trade.500.com/jczq/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
PLAY_URLS = {
    "had_hhad": "?playid=269&g=2",
    "crs": "?playid=271&g=2",
    "ttg": "?playid=270&g=2",
    "hafu": "?playid=272&g=2",
}
TYPE_TO_PLAY = {
    "nspf": "had",
    "spf": "hhad",
    "bf": "crs",
    "jqs": "ttg",
    "bqc": "hafu",
}
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_FULL_SCAN_DAYS_AHEAD = 21
LAST_SCAN_SUMMARY: dict[str, object] = {}


@dataclass
class ProbePlayResult:
    play: str
    url: str
    ok: bool
    selector: str
    rows: int
    matches: int
    data_shape: str
    reason: str | None = None


def fetch_all(session: requests.Session | None = None) -> list[MatchOdds]:
    return fetch_full_scan(session)


def fetch_full_scan(
    session: requests.Session | None = None,
    *,
    start_date: datetime | None = None,
    days_ahead: int | None = None,
    date_texts: list[str] | None = None,
) -> list[MatchOdds]:
    session = session or requests.Session()
    merged: dict[str, MatchOdds] = {}
    errors: list[str] = []
    if date_texts is None:
        today = (start_date or datetime.now(SHANGHAI)).date()
        scan_days = _full_scan_days_ahead(days_ahead)
        date_texts = [(today + timedelta(days=offset)).isoformat() for offset in range(scan_days + 1)]

    summary: dict[str, object] = {
        "dates_tested": list(date_texts),
        "active_dates": [],
        "unique_sales_windows": 0,
        "source_urls": [],
        "raw_events_seen": 0,
        "parsed_matches_seen": 0,
        "latest_kickoff_seen": None,
        "errors": errors,
    }
    seen_sales_windows: set[tuple[str, ...]] = set()

    for date_text in date_texts:
        try:
            params = _request_params("had_hhad", date_text)
            summary["source_urls"].append(_prepared_url(BASE_URL, params))
            html = fetch_html(session, BASE_URL, params)
            summary["raw_events_seen"] = int(summary["raw_events_seen"]) + _raw_match_rows(html)
            had_matches = parse_html(html, date_text, "had_hhad")
            for match in had_matches:
                _merge_match(merged, match)
            if not had_matches:
                continue
            sales_window = tuple(sorted(match.match_id for match in had_matches))
            if sales_window in seen_sales_windows:
                continue
            seen_sales_windows.add(sales_window)
            summary["unique_sales_windows"] = int(summary["unique_sales_windows"]) + 1
            summary["active_dates"].append(date_text)
        except Exception as exc:
            errors.append(f"had_hhad {date_text}: {exc}")
            continue

        for play in ("crs", "ttg", "hafu"):
            _optional_scan_sleep()
            try:
                params = _request_params(play, date_text)
                summary["source_urls"].append(_prepared_url(BASE_URL, params))
                html = fetch_html(session, BASE_URL, params)
                summary["raw_events_seen"] = int(summary["raw_events_seen"]) + _raw_match_rows(html)
                for match in parse_html(html, date_text, play):
                    _merge_match(merged, match)
            except Exception as exc:
                # TODO: crs/ttg/hafu are P0.5-tolerated if 500.com changes page shape.
                errors.append(f"{play} {date_text}: {exc}")

    matches = sorted(merged.values(), key=lambda item: item.kickoff_at)
    if matches:
        summary["parsed_matches_seen"] = len(matches)
        summary["latest_kickoff_seen"] = max(match.kickoff_at for match in matches).isoformat()

    global LAST_SCAN_SUMMARY
    LAST_SCAN_SUMMARY = summary
    if not matches:
        raise SourceError(f"500.com returned 0 World Cup matches; errors={'; '.join(errors) or 'none'}")
    return matches


def get_last_scan_summary() -> dict[str, object]:
    return dict(LAST_SCAN_SUMMARY)


def _full_scan_days_ahead(days_ahead: int | None) -> int:
    if days_ahead is None:
        try:
            days_ahead = int(os.getenv("M500_FULL_SCAN_DAYS_AHEAD", str(DEFAULT_FULL_SCAN_DAYS_AHEAD)))
        except ValueError:
            days_ahead = DEFAULT_FULL_SCAN_DAYS_AHEAD
    return max(0, min(days_ahead, 45))


def _optional_scan_sleep() -> None:
    try:
        seconds = float(os.getenv("M500_SCAN_SLEEP_SECONDS", "0"))
    except ValueError:
        seconds = 0
    if seconds > 0:
        time.sleep(seconds)


def _request_params(play: str, date_text: str) -> dict[str, str]:
    if play == "had_hhad":
        return {"date": date_text}
    playid = PLAY_URLS[play].split("playid=", 1)[1].split("&", 1)[0]
    return {"playid": playid, "g": "2", "date": date_text}


def _prepared_url(url: str, params: dict[str, str]) -> str:
    request = requests.Request("GET", url, params=params).prepare()
    return request.url or url


def _raw_match_rows(html: str) -> int:
    return len(BeautifulSoup(html, "lxml").select("tr.bet-tb-tr"))


def fetch_html(session: requests.Session, url: str, params: dict[str, str] | None = None) -> str:
    response = session.get(url, params=params, headers=HEADERS, timeout=15)
    if response.status_code != 200:
        raise SourceError(f"HTTP {response.status_code} from {response.url}")
    return decode_gbk(response)


def decode_gbk(response: requests.Response) -> str:
    return response.content.decode("gbk", errors="ignore")


def parse_html_or_raise(html: str, date_text: str, play: str = "had_hhad") -> list[MatchOdds]:
    matches = parse_html(html, date_text, play)
    if not matches:
        dump_parse_failure(html)
        raise SourceError(f"500.com parsed 0 World Cup matches for play={play}")
    return matches


def parse_html(html: str, date_text: str, play: str = "had_hhad") -> list[MatchOdds]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("tr.bet-tb-tr")
    parsed: list[MatchOdds] = []
    for row in rows:
        if not _is_world_cup_row(row):
            continue
        match = _parse_match_row(row, date_text)
        if play == "had_hhad":
            match.odds.extend(_parse_button_odds(row, {"nspf", "spf"}))
        elif play == "crs":
            more_row = row.find_next_sibling("tr", class_="bet-more-wrap")
            if more_row:
                match.odds.extend(_parse_button_odds(more_row, {"bf"}))
        elif play == "ttg":
            match.odds.extend(_parse_button_odds(row, {"jqs"}))
        elif play == "hafu":
            match.odds.extend(_parse_button_odds(row, {"bqc"}))
        if match.odds:
            parsed.append(match)
    return parsed


def probe(session: requests.Session | None = None) -> tuple[str, int, str, list[MatchOdds]]:
    session = session or requests.Session()
    date_text = datetime.now(SHANGHAI).date().isoformat()
    response = session.get(BASE_URL, params={"date": date_text}, headers=HEADERS, timeout=15)
    html = decode_gbk(response)
    prefix = html[:500]
    if response.status_code != 200:
        return response.url, response.status_code, prefix, []
    return response.url, response.status_code, prefix, parse_html(html, date_text, "had_hhad")


def probe_play_pages(session: requests.Session | None = None, date_text: str | None = None) -> list[ProbePlayResult]:
    session = session or requests.Session()
    date_text = date_text or datetime.now(SHANGHAI).date().isoformat()
    results: list[ProbePlayResult] = []
    for play, url_part in (
        ("had", PLAY_URLS["had_hhad"]),
        ("hhad", PLAY_URLS["had_hhad"]),
        ("crs", PLAY_URLS["crs"]),
        ("ttg", PLAY_URLS["ttg"]),
        ("hafu", PLAY_URLS["hafu"]),
    ):
        url = urljoin(BASE_URL, f"{url_part}&date={date_text}")
        try:
            response = session.get(url, headers=HEADERS, timeout=15)
            html = decode_gbk(response)
            soup = BeautifulSoup(html, "lxml")
            rows = len(soup.select("tr.bet-tb-tr"))
            if response.status_code != 200:
                results.append(_blocked(play, response.url, rows, f"HTTP {response.status_code}"))
                continue
            parse_play = "had_hhad" if play in {"had", "hhad"} else play
            matches = parse_html(html, date_text, parse_play)
            selector, shape = _probe_selector(play)
            ok = bool(matches)
            results.append(
                ProbePlayResult(
                    play=play,
                    url=response.url,
                    ok=ok,
                    selector=selector,
                    rows=rows,
                    matches=len(matches),
                    data_shape=shape,
                    reason=None if ok else "0 World Cup matches parsed",
                )
            )
        except Exception as exc:
            results.append(_blocked(play, url, 0, str(exc)))
    return results


def dump_parse_failure(html: str) -> Path:
    path = Path("/tmp") / f"parse_fail_{int(time.time())}.html"
    path.write_text(html, encoding="utf-8", errors="ignore")
    return path


def sample_match_json(match: MatchOdds) -> dict[str, object]:
    return {
        "match_id": match.match_id,
        "match_num": match.match_num,
        "league": match.league,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "kickoff_at": match.kickoff_at.isoformat(),
        "status": match.status,
        "odds": [
            {"play_type": item.play_type, "goal_line": str(item.goal_line) if item.goal_line is not None else None, "odds": item.odds}
            for item in match.odds
        ],
    }


def _parse_match_row(row: Tag, date_text: str) -> MatchOdds:
    attrs = row.attrs
    match_id = str(attrs.get("data-fixtureid") or attrs.get("data-id") or attrs.get("data-processid") or "")
    match_num = str(attrs.get("data-matchnum") or "")
    home = str(attrs.get("data-homesxname") or _team_name(row, "team-l"))
    away = str(attrs.get("data-awaysxname") or _team_name(row, "team-r"))
    kickoff = _parse_kickoff(str(attrs.get("data-matchdate") or date_text), str(attrs.get("data-matchtime") or "00:00"))
    return MatchOdds(
        match_id=f"500-{match_id}",
        match_num=match_num or None,
        league="世界杯",
        home_team=home,
        away_team=away,
        kickoff_at=kickoff,
        status=_status_from_sale_attrs(attrs),
    )


def _status_from_sale_attrs(attrs: dict[str, object]) -> str:
    isend = str(attrs.get("data-isend") or attrs.get("isend") or "").strip().lower()
    sale_status = str(attrs.get("data-status") or attrs.get("status") or "").strip().lower()
    if isend in {"1", "true", "yes"} or sale_status in {"closed", "sale_closed", "stop", "stopped"}:
        return "closed"
    return "scheduled"


def _parse_button_odds(scope: Tag, allowed_types: set[str]) -> list[OddsEntry]:
    grouped: dict[str, dict[str, float]] = {}
    goal_line: Decimal | None = None
    parent_match = scope if scope.name == "tr" and "bet-tb-tr" in (scope.get("class") or []) else scope.find_previous("tr", class_="bet-tb-tr")
    if isinstance(parent_match, Tag) and parent_match.get("data-rangqiu"):
        try:
            goal_line = Decimal(str(parent_match["data-rangqiu"]).strip())
        except Exception:
            goal_line = None
    for button in scope.select("[data-sp][data-type][data-value]"):
        odds_type = str(button.get("data-type"))
        if odds_type not in allowed_types:
            continue
        play_type = TYPE_TO_PLAY[odds_type]
        value = str(button.get("data-value"))
        odd = clean_float(button.get("data-sp"))
        if odd is None:
            continue
        grouped.setdefault(play_type, {})[value] = odd
    return [
        OddsEntry(play_type=play_type, odds=odds, goal_line=goal_line if play_type == "hhad" else None)
        for play_type, odds in grouped.items()
    ]


def _merge_match(merged: dict[str, MatchOdds], match: MatchOdds) -> None:
    existing = merged.get(match.match_id)
    if existing is None:
        merged[match.match_id] = match
        return
    seen = {(entry.play_type, tuple(sorted(entry.odds.items()))) for entry in existing.odds}
    for entry in match.odds:
        key = (entry.play_type, tuple(sorted(entry.odds.items())))
        if key not in seen:
            existing.odds.append(entry)


def _is_world_cup_row(row: Tag) -> bool:
    league = str(row.get("data-simpleleague") or "")
    if is_world_cup_league(league):
        return True
    event_cell = row.select_one("td.td-evt")
    return is_world_cup_league(event_cell.get_text(" ", strip=True) if event_cell else "")


def _parse_kickoff(date_text: str, time_text: str) -> datetime:
    dt = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=SHANGHAI).astimezone(timezone.utc)


def _team_name(row: Tag, class_name: str) -> str:
    node = row.select_one(f"a.{class_name}")
    return node.get_text(strip=True) if node else ""


def _probe_selector(play: str) -> tuple[str, str]:
    if play == "had":
        return "tr.bet-tb-tr[data-simpleleague] p.betbtn[data-type=nspf][data-value][data-sp]", "server-rendered HTML/GBK"
    if play == "hhad":
        return "tr.bet-tb-tr[data-simpleleague] p.betbtn[data-type=spf][data-value][data-sp]", "server-rendered HTML/GBK"
    if play == "crs":
        return "tr.bet-tb-tr + tr.bet-more-wrap p.sbetbtn[data-type=bf][data-value][data-sp]", "server-rendered expandable HTML/GBK"
    if play == "ttg":
        return "tr.bet-tb-tr[data-simpleleague] p.betbtn[data-type=jqs][data-value][data-sp]", "server-rendered HTML/GBK"
    return "tr.bet-tb-tr[data-simpleleague] p.betbtn[data-type=bqc][data-value][data-sp]", "server-rendered HTML/GBK"


def _blocked(play: str, url: str, rows: int, reason: str) -> ProbePlayResult:
    selector, shape = _probe_selector(play)
    return ProbePlayResult(play=play, url=url, ok=False, selector=selector, rows=rows, matches=0, data_shape=shape, reason=reason)

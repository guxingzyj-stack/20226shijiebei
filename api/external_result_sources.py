from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from api.ops_log import sanitize_error
from api.result_source_mapping import normalize_team_name


ROOT = Path(__file__).resolve().parents[1]
FIFA_TARGETS_CSV = ROOT / "data" / "fifa_match_targets.csv"
P3_FIFA_TARGETS_CSV = ROOT / "data" / "p3" / "fifa_match_targets.csv"
FIFA_SCHEDULE_PAGE = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums"
THESPORTSDB_URL_TEMPLATE = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={date}&s=Soccer"
ESPN_SCOREBOARD_URL_TEMPLATES = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}",
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world_cup/scoreboard?dates={date}",
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldcup/scoreboard?dates={date}",
)
NEW_YORK_TZ = ZoneInfo("America/New_York")
FINAL_STATUSES = {"finished", "complete", "completed", "full-time", "fulltime", "ft", "match finished"}
TARGET_TEAMS = {
    "卡塔尔",
    "瑞士",
    "巴西",
    "摩洛哥",
    "海地",
    "苏格兰",
    "澳大利亚",
    "土耳其",
    "德国",
    "库拉索",
    "荷兰",
    "日本",
    "美国",
    "韩国",
    "捷克",
    "波黑",
    "伊朗",
    "科特迪瓦",
    "刚果(金)",
    "沙特阿拉伯",
    "新西兰",
    "佛得角",
    "\u897f\u73ed\u7259",
    "\u6bd4\u5229\u65f6",
    "\u57c3\u53ca",
    "\u4e4c\u62c9\u572d",
    "\u6cd5\u56fd",
    "\u585e\u5185\u52a0\u5c14",
    "\u4f0a\u62c9\u514b",
    "\u632a\u5a01",
    "\u963f\u6839\u5ef7",
    "\u963f\u5c14\u53ca\u5229\u4e9a",
    "\u5965\u5730\u5229",
    "\u7ea6\u65e6",
    "\u8461\u8404\u7259",
    "\u4e4c\u5179\u522b\u514b",
    "\u54e5\u4f26\u6bd4\u4e9a",
    "\u82f1\u683c\u5170",
    "\u514b\u7f57\u5730\u4e9a",
    "\u52a0\u7eb3",
    "\u5df4\u62ff\u9a6c",
}


@dataclass(frozen=True)
class ExternalResultEvent:
    source: str
    source_url: str
    external_id: str | None
    raw_home: str | None
    raw_away: str | None
    home_team: str
    away_team: str
    kickoff_at: datetime | None
    status: str
    raw_status: str | None
    result_home: int | None
    result_away: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_url": self.source_url,
            "external_id": self.external_id,
            "raw_home": self.raw_home,
            "raw_away": self.raw_away,
            "normalized_home": self.home_team,
            "normalized_away": self.away_team,
            "kickoff_at": self.kickoff_at.isoformat() if self.kickoff_at else None,
            "status": self.status,
            "raw_status": self.raw_status,
            "result_home": self.result_home,
            "result_away": self.result_away,
        }


def fetch_source_events(source: str, match_date: str) -> dict[str, Any]:
    if source == "thesportsdb":
        return fetch_thesportsdb_events(match_date)
    if source == "fifa":
        return fetch_fifa_events(match_date)
    if source == "espn":
        return fetch_espn_events(match_date)
    raise ValueError("source must be thesportsdb, fifa, or espn")


def fetch_thesportsdb_events(match_date: str) -> dict[str, Any]:
    url = THESPORTSDB_URL_TEMPLATE.format(date=match_date)
    try:
        payload = _fetch_json(url)
        raw_events = payload.get("events") or []
        events = [parse_thesportsdb_event(item, source_url=url) for item in raw_events]
        events = [event for event in events if event is not None]
        return _source_report("thesportsdb", url, events, None)
    except Exception as exc:
        return _source_report("thesportsdb", url, [], sanitize_error(exc), fetch_ok=False)


def fetch_espn_events(match_date: str) -> dict[str, Any]:
    compact_date = match_date.replace("-", "")
    errors: list[str] = []
    empty_urls: list[str] = []
    for template in ESPN_SCOREBOARD_URL_TEMPLATES:
        url = template.format(date=compact_date)
        try:
            payload = _fetch_json(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        raw_events = payload.get("events") or []
        if not raw_events:
            empty_urls.append(url)
            continue
        events = [parse_espn_event(item, source_url=url) for item in raw_events]
        events = [event for event in events if event is not None]
        report = _source_report("espn", url, events, None)
        report["source_attempted_urls"] = list(ESPN_SCOREBOARD_URL_TEMPLATES)
        return report
    fallback_url = ESPN_SCOREBOARD_URL_TEMPLATES[0].format(date=compact_date)
    parser_error = "; ".join(errors) if errors and not empty_urls else None
    report = _source_report("espn", fallback_url, [], parser_error, fetch_ok=not errors or bool(empty_urls))
    report["source_attempted_urls"] = list(ESPN_SCOREBOARD_URL_TEMPLATES)
    return report


def fetch_espn_events_for_dates(scoreboard_dates: list[str]) -> dict[str, Any]:
    events_by_id: dict[str, dict[str, Any]] = {}
    attempted_dates: list[str] = []
    source_urls: list[str] = []
    parser_errors: list[str] = []
    fetch_ok = False
    for scoreboard_date in scoreboard_dates:
        attempted_dates.append(scoreboard_date)
        report = fetch_espn_events(_scoreboard_date_to_iso(scoreboard_date))
        source_urls.append(str(report.get("source_url")))
        if report.get("source_fetch_ok"):
            fetch_ok = True
        if report.get("parser_error"):
            parser_errors.append(str(report.get("parser_error")))
        for event in report.get("events", []):
            key = str(event.get("external_id") or f"{event.get('normalized_home')}:{event.get('normalized_away')}:{event.get('kickoff_at')}")
            event = dict(event)
            event["external_source_date"] = scoreboard_date
            events_by_id.setdefault(key, event)
    return {
        "source": "espn",
        "source_fetch_ok": fetch_ok,
        "source_url": ",".join(url for url in source_urls if url),
        "events_seen": len(events_by_id),
        "events": list(events_by_id.values()),
        "parser_error": "; ".join(parser_errors) if parser_errors and not fetch_ok else None,
        "scoreboard_dates": attempted_dates,
    }


def espn_scoreboard_dates_for_kickoff(kickoff_at: datetime) -> list[str]:
    kickoff_utc = kickoff_at if kickoff_at.tzinfo else kickoff_at.replace(tzinfo=timezone.utc)
    kickoff_utc = kickoff_utc.astimezone(timezone.utc)
    candidates = [
        kickoff_utc.astimezone(NEW_YORK_TZ).strftime("%Y%m%d"),
        kickoff_utc.strftime("%Y%m%d"),
        (kickoff_utc.date() - date.resolution).strftime("%Y%m%d"),
        (kickoff_utc.date() + date.resolution).strftime("%Y%m%d"),
    ]
    deduped: list[str] = []
    for item in candidates:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _scoreboard_date_to_iso(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def parse_espn_event(item: dict[str, Any], source_url: str) -> ExternalResultEvent | None:
    competition = (item.get("competitions") or [{}])[0] or {}
    competitors = competition.get("competitors") or []
    home = next((row for row in competitors if row.get("homeAway") == "home"), None)
    away = next((row for row in competitors if row.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    raw_home = _espn_team_name(home)
    raw_away = _espn_team_name(away)
    if not raw_home or not raw_away:
        return None
    status_type = ((item.get("status") or {}).get("type") or {})
    completed = bool(status_type.get("completed"))
    raw_status = _text(status_type.get("name") or status_type.get("state") or status_type.get("description"))
    status = _normalize_espn_status(status_type)
    if completed:
        status = "finished"
    return ExternalResultEvent(
        source="espn",
        source_url=source_url,
        external_id=_text(item.get("id")),
        raw_home=raw_home,
        raw_away=raw_away,
        home_team=normalize_team_name(raw_home),
        away_team=normalize_team_name(raw_away),
        kickoff_at=_parse_datetime(item.get("date")),
        status=status,
        raw_status=raw_status,
        result_home=_optional_int(home.get("score")),
        result_away=_optional_int(away.get("score")),
    )


def _espn_team_name(competitor: dict[str, Any]) -> str | None:
    team = competitor.get("team") or {}
    return _text(_first(team, "displayName", "shortDisplayName", "name", "abbreviation"))


def _normalize_espn_status(status_type: dict[str, Any]) -> str:
    name = str(status_type.get("name") or "").strip().lower()
    state = str(status_type.get("state") or "").strip().lower()
    description = str(status_type.get("description") or "").strip().lower()
    joined = " ".join([name, state, description])
    if bool(status_type.get("completed")) or any(token in joined for token in ("post", "final", "full time", "full-time", "ft")):
        return "finished"
    if any(token in joined for token in ("in", "live", "halftime", "half")):
        return "live"
    return "scheduled"


def parse_thesportsdb_event(item: dict[str, Any], source_url: str) -> ExternalResultEvent | None:
    home = _first(item, "strHomeTeam", "strHomeTeamShort", "home_team")
    away = _first(item, "strAwayTeam", "strAwayTeamShort", "away_team")
    if not home or not away:
        event = str(_first(item, "strEvent") or "")
        if " vs " in event:
            home, away = [part.strip() for part in event.split(" vs ", 1)]
    if not home or not away:
        return None
    return ExternalResultEvent(
        source="thesportsdb",
        source_url=source_url,
        external_id=_text(_first(item, "idEvent")),
        raw_home=_text(home),
        raw_away=_text(away),
        home_team=normalize_team_name(home),
        away_team=normalize_team_name(away),
        kickoff_at=_parse_thesportsdb_datetime(item),
        status=_normalize_status(_first(item, "strStatus", "strProgress", "strResult")),
        raw_status=_text(_first(item, "strStatus", "strProgress", "strResult")),
        result_home=_optional_int(_first(item, "intHomeScore")),
        result_away=_optional_int(_first(item, "intAwayScore")),
    )


def fetch_fifa_events(match_date: str, targets_csv: Path | None = None) -> dict[str, Any]:
    targets_csv = targets_csv or _default_fifa_targets_csv()
    source_url = str(targets_csv)
    if not targets_csv.exists():
        return _source_report("fifa", source_url, [], "missing_fifa_match_url_mapping", fetch_ok=True)
    try:
        rows = _read_fifa_targets(targets_csv)
        events: list[ExternalResultEvent] = []
        target_details: list[dict[str, Any]] = []
        for row in rows:
            kickoff = _parse_datetime(row.get("kickoff_at"))
            if not kickoff or kickoff.date().isoformat() != match_date:
                continue
            url = str(row.get("fifa_match_url") or row.get("fifa_url") or "").strip()
            if not url:
                target_details.append(_fifa_target_detail(row, fetch_ok=False, reason="missing_url_mapping"))
                continue
            try:
                fetched = _fetch_text(url)
            except Exception as exc:
                target_details.append(_fifa_target_detail(row, fetch_ok=False, reason=f"fetch_error:{type(exc).__name__}"))
                continue
            event = parse_fifa_event(row, fetched, source_url=url)
            target_details.append(_fifa_target_detail(row, event=event, fetch_ok=True, reason=None))
            events.append(event)
        report = _source_report("fifa", source_url, events, None)
        report["target_details"] = target_details
        report["missing_url_mapping_count"] = sum(1 for item in target_details if item["reason"] == "missing_url_mapping")
        report["verified_url_count"] = sum(1 for item in target_details if item["fetch_ok"])
        return report
    except Exception as exc:
        return _source_report("fifa", source_url, [], sanitize_error(exc), fetch_ok=False)


def parse_fifa_event(row: dict[str, Any], text: str, source_url: str) -> ExternalResultEvent:
    score = _extract_score(text)
    status = _extract_status(text) or row.get("status")
    home = row.get("home_team")
    away = row.get("away_team")
    return ExternalResultEvent(
        source="fifa",
        source_url=source_url,
        external_id=_text(row.get("fifa_match_id") or row.get("project_match_id") or row.get("local_match_id") or source_url),
        raw_home=_text(home),
        raw_away=_text(away),
        home_team=normalize_team_name(home),
        away_team=normalize_team_name(away),
        kickoff_at=_parse_datetime(row.get("kickoff_at")),
        status=_normalize_status(status),
        raw_status=_text(status),
        result_home=score[0] if score else None,
        result_away=score[1] if score else None,
    )


def probe_source(source: str, match_date: str) -> dict[str, Any]:
    report = fetch_source_events(source, match_date)
    events = report["events"]
    target_events = [
        event
        for event in events
        if event["normalized_home"] in TARGET_TEAMS or event["normalized_away"] in TARGET_TEAMS
    ]
    final_with_score = [
        event
        for event in target_events
        if event["status"] == "finished" and event["result_home"] is not None and event["result_away"] is not None
    ]
    report.update(
        {
            "target_matches_seen": len(target_events),
            "sample_events": events[:10],
            "target_samples": target_events[:10],
            "missing_url_mapping_count": report.get("missing_url_mapping_count", 0),
            "verified_url_count": report.get("verified_url_count", 0),
            "target_details": report.get("target_details", []),
            "conclusion": _probe_conclusion(report["source_fetch_ok"], events, target_events, final_with_score, report.get("parser_error")),
            "writes_db": False,
        }
    )
    return report


def discover_fifa_urls(match_date: str, limit: int = 5) -> dict[str, Any]:
    try:
        text = _fetch_text(FIFA_SCHEDULE_PAGE)
    except Exception as exc:
        return {
            "source": "fifa",
            "discover_url": True,
            "source_fetch_ok": False,
            "source_url": FIFA_SCHEDULE_PAGE,
            "parser_error": sanitize_error(exc),
            "discovered_urls": [],
            "writes_db": False,
        }
    urls = _discover_urls_from_text(text, limit=limit)
    return {
        "source": "fifa",
        "discover_url": True,
        "source_fetch_ok": True,
        "source_url": FIFA_SCHEDULE_PAGE,
        "parser_error": None,
        "date": match_date,
        "discovered_urls": urls,
        "discovered_count": len(urls),
        "writes_db": False,
        "result": "WAIT" if not urls else "PASS",
        "reason": None if urls else "no_match_centre_urls_detected_on_schedule_page",
    }


def classify_thesportsdb_date_pair(historical_report: dict[str, Any], current_report: dict[str, Any]) -> str:
    if not historical_report.get("source_fetch_ok") and not current_report.get("source_fetch_ok"):
        return "THESPORTSDB_UNREACHABLE"
    if historical_report.get("events_seen", 0) > 0 and current_report.get("events_seen", 0) == 0:
        return "THESPORTSDB_DELAYED_FREE_TIER"
    if (
        historical_report.get("target_matches_seen", 0) > 0
        and current_report.get("target_matches_seen", 0) > 0
    ):
        return "THESPORTSDB_USABLE_AS_STRUCTURED_FALLBACK_CANDIDATE"
    if historical_report.get("events_seen", 0) > 0 or current_report.get("events_seen", 0) > 0:
        return "THESPORTSDB_NO_TARGET_MATCHES"
    return "THESPORTSDB_EMPTY"


def print_probe_report(report: dict[str, Any]) -> None:
    if report.get("discover_url"):
        _safe_print("FIFA URL Discovery Report")
        for key in ("source_fetch_ok", "source_url", "date", "discovered_count", "parser_error", "result", "reason", "writes_db"):
            _safe_print(f"- {key}: {report.get(key)}")
        _safe_print("discovered_urls:")
        for item in report.get("discovered_urls", []):
            _safe_print(f"  - url: {item.get('url')}")
            _safe_print(f"    fifa_match_id: {item.get('fifa_match_id')}")
            _safe_print(f"    slug: {item.get('slug')}")
            _safe_print(f"    content_id: {item.get('content_id')}")
            _safe_print(f"    fetch_ok: {item.get('fetch_ok')}")
        return
    _safe_print("External Result Source Probe Report")
    for key in ("source", "source_fetch_ok", "source_url", "events_seen", "target_matches_seen", "missing_url_mapping_count", "verified_url_count", "parser_error", "conclusion", "writes_db"):
        _safe_print(f"- {key}: {report.get(key)}")
    if report.get("target_details"):
        _safe_print("target_details:")
        for item in report.get("target_details", [])[:20]:
            _safe_print(f"  - local_match_id: {item.get('local_match_id')}")
            _safe_print(f"    local_home_team: {item.get('local_home_team')}")
            _safe_print(f"    local_away_team: {item.get('local_away_team')}")
            _safe_print(f"    fifa_url: {item.get('fifa_url')}")
            _safe_print(f"    fetch_ok: {item.get('fetch_ok')}")
            _safe_print(f"    raw_home: {item.get('raw_home')}")
            _safe_print(f"    raw_away: {item.get('raw_away')}")
            _safe_print(f"    normalized_home: {item.get('normalized_home')}")
            _safe_print(f"    normalized_away: {item.get('normalized_away')}")
            _safe_print(f"    status: {item.get('status')}")
            _safe_print(f"    score: {item.get('result_home')}-{item.get('result_away')}")
            _safe_print(f"    kickoff_at: {item.get('kickoff_at')}")
            _safe_print(f"    team_match_status: {item.get('team_match_status')}")
            _safe_print(f"    time_match_status: {item.get('time_match_status')}")
            _safe_print(f"    reason: {item.get('reason')}")
    _safe_print("sample_events:")
    for item in report.get("sample_events", []):
        _safe_print(f"  - external_id: {item.get('external_id')}")
        _safe_print(f"    raw_home: {item.get('raw_home')}")
        _safe_print(f"    raw_away: {item.get('raw_away')}")
        _safe_print(f"    normalized_home: {item.get('normalized_home')}")
        _safe_print(f"    normalized_away: {item.get('normalized_away')}")
        _safe_print(f"    kickoff_at: {item.get('kickoff_at')}")
        _safe_print(f"    status: {item.get('status')}")
        _safe_print(f"    score: {item.get('result_home')}-{item.get('result_away')}")


def _safe_print(value: Any) -> None:
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _source_report(source: str, source_url: str, events: list[ExternalResultEvent], parser_error: str | None, fetch_ok: bool = True) -> dict[str, Any]:
    return {
        "source": source,
        "source_fetch_ok": fetch_ok,
        "source_url": source_url,
        "events_seen": len(events),
        "events": [event.as_dict() for event in events],
        "parser_error": parser_error,
    }


def _probe_conclusion(fetch_ok: bool, events: list[dict[str, Any]], target_events: list[dict[str, Any]], final_with_score: list[dict[str, Any]], parser_error: str | None) -> str:
    if not fetch_ok:
        return "THESPORTSDB_UNREACHABLE" if parser_error else "SOURCE_UNREACHABLE"
    if not events:
        return "SOURCE_EMPTY_OR_DELAYED"
    if final_with_score:
        return "STRUCTURED_FALLBACK_CANDIDATE"
    if target_events:
        return "TARGET_MATCHES_WITHOUT_FINAL_SCORE"
    return "THESPORTSDB_NO_TARGET_MATCHES"


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "worldcup-result-source-probe/1.0"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    if not re.match(r"https?://", url, flags=re.I):
        return Path(url).read_text(encoding="utf-8")
    request = Request(url, headers={"User-Agent": "worldcup-result-source-probe/1.0"})
    with urlopen(request, timeout=20) as response:
        body = response.read()
    for encoding in ("utf-8", "gb18030"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _read_fifa_targets(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = []
        for row in csv.DictReader(fh):
            item = dict(row)
            item["project_match_id"] = str(item.get("project_match_id") or item.get("local_match_id") or "").strip()
            item["local_match_id"] = str(item.get("local_match_id") or item.get("project_match_id") or "").strip()
            item["fifa_match_url"] = str(item.get("fifa_match_url") or item.get("fifa_url") or "").strip()
            item["fifa_url"] = item["fifa_match_url"]
            rows.append(item)
        return rows


def _default_fifa_targets_csv() -> Path:
    return FIFA_TARGETS_CSV if FIFA_TARGETS_CSV.exists() else P3_FIFA_TARGETS_CSV


def _fifa_target_detail(row: dict[str, Any], fetch_ok: bool, reason: str | None, event: ExternalResultEvent | None = None) -> dict[str, Any]:
    event_dict = event.as_dict() if event else {}
    local_home = normalize_team_name(row.get("home_team"))
    local_away = normalize_team_name(row.get("away_team"))
    team_match = (
        event is not None
        and event.home_team == local_home
        and event.away_team == local_away
    )
    local_time = _parse_datetime(row.get("kickoff_at"))
    event_time = event.kickoff_at if event else None
    delta = abs((local_time - event_time).total_seconds()) / 60 if local_time and event_time else None
    return {
        "local_match_id": row.get("local_match_id") or row.get("project_match_id"),
        "local_home_team": row.get("home_team"),
        "local_away_team": row.get("away_team"),
        "fifa_url": row.get("fifa_url") or row.get("fifa_match_url"),
        "fetch_ok": fetch_ok,
        "raw_home": event_dict.get("raw_home"),
        "raw_away": event_dict.get("raw_away"),
        "normalized_home": event_dict.get("normalized_home"),
        "normalized_away": event_dict.get("normalized_away"),
        "status": event_dict.get("status"),
        "result_home": event_dict.get("result_home"),
        "result_away": event_dict.get("result_away"),
        "kickoff_at": event_dict.get("kickoff_at") or (local_time.isoformat() if local_time else None),
        "team_match_status": "matched" if team_match else ("not_checked" if event is None else "team_mismatch"),
        "time_match_status": "matched" if delta is not None and delta <= 120 else ("not_checked" if event is None else "time_mismatch"),
        "reason": reason,
    }


def _discover_urls_from_text(text: str, limit: int) -> list[dict[str, Any]]:
    candidates: list[str] = []
    for match in re.finditer(r'https?://[^"\'<>\s]+', text):
        url = match.group(0)
        if any(token in url.lower() for token in ("match-centre", "matchcentre", "/match/", "matches")):
            candidates.append(url)
    for match in re.finditer(r'/(?:en/)?[^"\'<>\s]*(?:match-centre|matchcentre|match/)[^"\'<>\s]+', text, flags=re.I):
        candidates.append("https://www.fifa.com" + match.group(0))
    seen: set[str] = set()
    rows = []
    for url in candidates:
        clean = url.rstrip(".,);")
        if clean in seen:
            continue
        seen.add(clean)
        rows.append(
            {
                "url": clean,
                "fifa_match_id": _first_match(clean, r"(?:match|id)[-/=]?(\d{4,})"),
                "slug": _first_match(clean, r"/([^/?#]+)(?:[?#].*)?$"),
                "content_id": _first_match(clean, r"(?:contentId|content_id)=([A-Za-z0-9-]+)"),
                "fetch_ok": None,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _parse_thesportsdb_datetime(item: dict[str, Any]) -> datetime | None:
    raw_date = _text(_first(item, "dateEvent"))
    raw_time = _text(_first(item, "strTimestamp", "strTime"))
    if raw_time and "T" in raw_time:
        return _parse_datetime(raw_time)
    if not raw_date:
        return None
    clock = raw_time or "00:00:00"
    if len(clock) == 5:
        clock = f"{clock}:00"
    return _parse_datetime(f"{raw_date}T{clock}+00:00")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    compact = text.replace(" ", "").replace("_", "").replace("-", "")
    if text in FINAL_STATUSES or compact in {"matchfinished", "fulltime", "finished", "complete", "completed", "ft"}:
        return "finished"
    if any(token in compact for token in ("postponed", "cancelled", "abandoned", "suspended")):
        return "postponed"
    if any(token in compact for token in ("live", "inplay", "halftime")):
        return "live"
    return "scheduled"


def _extract_score(text: str) -> tuple[int, int] | None:
    patterns = [
        r'"homeScore"\s*:\s*(\d+).*?"awayScore"\s*:\s*(\d+)',
        r'"home_score"\s*:\s*(\d+).*?"away_score"\s*:\s*(\d+)',
        r'"scoreHome"\s*:\s*(\d+).*?"scoreAway"\s*:\s*(\d+)',
        r"(?<!\d)(\d{1,2})\s*[-:]\s*(\d{1,2})(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S | re.I)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def _extract_status(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("match finished", "full-time", "full time", '"finished"', '"completed"', '"ft"')):
        return "finished"
    return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _first_match(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value, flags=re.I)
    return match.group(1) if match else None


def _first(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

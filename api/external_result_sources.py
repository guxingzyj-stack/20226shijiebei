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

from api.ops_log import sanitize_error
from api.result_source_mapping import normalize_team_name


ROOT = Path(__file__).resolve().parents[1]
FIFA_TARGETS_CSV = ROOT / "data" / "p3" / "fifa_match_targets.csv"
THESPORTSDB_URL_TEMPLATE = "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={date}&s=Soccer"
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
    raise ValueError("source must be thesportsdb or fifa")


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


def fetch_fifa_events(match_date: str, targets_csv: Path = FIFA_TARGETS_CSV) -> dict[str, Any]:
    source_url = str(targets_csv)
    if not targets_csv.exists():
        return _source_report("fifa", source_url, [], "missing_fifa_match_url_mapping", fetch_ok=True)
    try:
        rows = _read_fifa_targets(targets_csv)
        events: list[ExternalResultEvent] = []
        for row in rows:
            kickoff = _parse_datetime(row.get("kickoff_at"))
            if not kickoff or kickoff.date().isoformat() != match_date:
                continue
            url = str(row.get("fifa_match_url") or "").strip()
            if not url:
                continue
            fetched = _fetch_text(url)
            events.append(parse_fifa_event(row, fetched, source_url=url))
        return _source_report("fifa", source_url, events, None)
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
        external_id=_text(row.get("project_match_id") or row.get("fifa_match_id") or source_url),
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
            "conclusion": _probe_conclusion(report["source_fetch_ok"], events, target_events, final_with_score, report.get("parser_error")),
            "writes_db": False,
        }
    )
    return report


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
    _safe_print("External Result Source Probe Report")
    for key in ("source", "source_fetch_ok", "source_url", "events_seen", "target_matches_seen", "parser_error", "conclusion", "writes_db"):
        _safe_print(f"- {key}: {report.get(key)}")
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
        return [dict(row) for row in csv.DictReader(fh)]


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

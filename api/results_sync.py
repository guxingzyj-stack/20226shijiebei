from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import os
import re
import sys
from typing import Any
from urllib.request import Request, urlopen

from api.db import connect
from api.ops_log import record_ops_log, sanitize_error


DEFAULT_RESULTS_URL = "https://trade.500.com/jczq/"
DEFAULT_SOURCE_NAME = "500_trade_jczq"
DEFAULT_SOURCE_TYPE = "html_page"
SCORE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*[:-]\s*(\d{1,2})(?!\d)")


@dataclass(frozen=True)
class ParsedResult:
    match_id: str
    status: str
    result_home: int | None = None
    result_away: int | None = None
    ht_home: int | None = None
    ht_away: int | None = None


@dataclass
class ResultsSyncStats:
    source_name: str = DEFAULT_SOURCE_NAME
    source_type: str = DEFAULT_SOURCE_TYPE
    source_status: str = "not_started"
    source_fetch_ok: bool = False
    source_last_success_at: str | None = None
    matches_seen: int = 0
    finished_updated: int = 0
    halftime_updated: int = 0
    postponed_updated: int = 0
    skipped: int = 0
    errors: int = 0
    skipped_reasons: dict[str, int] | None = None
    overdue_closed_matches: list[dict[str, Any]] | None = None


class _RowsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._row_attrs: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row_attrs = {name.lower(): value or "" for name, value in attrs}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._row_attrs is not None:
            text = data.strip()
            if text:
                self._text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "tr" or self._row_attrs is None:
            return
        self.rows.append({"attrs": self._row_attrs, "text": " ".join(self._text)})
        self._row_attrs = None
        self._text = []


def parse_results_html(html: str) -> list[ParsedResult]:
    parser = _RowsParser()
    parser.feed(html)
    results: list[ParsedResult] = []
    for row in parser.rows:
        parsed = _parse_row(row["attrs"], row["text"])
        if parsed is not None:
            results.append(parsed)
    return results


def sync_results(results: list[ParsedResult], repository: Any, dry_run: bool = False) -> ResultsSyncStats:
    stats = ResultsSyncStats(matches_seen=len(results), skipped_reasons={})
    for result in results:
        try:
            if result.status == "finished":
                if result.result_home is None or result.result_away is None:
                    _skip(stats, "missing_result_score")
                    continue
                if _already_finished_with_result(repository, result.match_id):
                    _skip(stats, "already_finished_with_result")
                    continue
                if not dry_run:
                    updated = repository.update_finished(result)
                    if updated is False:
                        _skip(stats, "match_id_not_found")
                        continue
                stats.finished_updated += 1
                if result.ht_home is not None and result.ht_away is not None:
                    stats.halftime_updated += 1
            elif result.status == "postponed":
                if not dry_run:
                    updated = repository.update_postponed(result)
                    if updated is False:
                        _skip(stats, "match_id_not_found")
                        continue
                stats.postponed_updated += 1
            else:
                _skip(stats, "not_finished_status")
        except Exception:
            stats.errors += 1
            _skip(stats, "row_error")
    return stats


class PostgresResultsRepository:
    def match_state(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT match_id, status, result_home, result_away
                FROM matches
                WHERE match_id = %s
                """,
                (match_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"match_id": row[0], "status": row[1], "result_home": row[2], "result_away": row[3]}

    def update_finished(self, result: ParsedResult) -> bool:
        now = datetime.now(timezone.utc)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE matches
                SET result_home = %s,
                    result_away = %s,
                    ht_home = COALESCE(%s, ht_home),
                    ht_away = COALESCE(%s, ht_away),
                    status = 'finished',
                    updated_at = %s
                WHERE match_id = %s
                """,
                (result.result_home, result.result_away, result.ht_home, result.ht_away, now, result.match_id),
            )
            return bool(cur.rowcount)

    def update_postponed(self, result: ParsedResult) -> bool:
        now = datetime.now(timezone.utc)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE matches
                SET status = 'postponed',
                    updated_at = %s
                WHERE match_id = %s
                """,
                (now, result.match_id),
            )
            return bool(cur.rowcount)


def fetch_results_html(url: str | None = None) -> str:
    target = url or os.getenv("RESULTS_SYNC_URL", DEFAULT_RESULTS_URL)
    request = Request(target, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
    for encoding in ("gb18030", "utf-8"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def print_stats(stats: ResultsSyncStats) -> None:
    print("results_sync:")
    print(f"- source_name: {stats.source_name}")
    print(f"- source_type: {stats.source_type}")
    print(f"- source_status: {stats.source_status}")
    print(f"- source_fetch_ok: {stats.source_fetch_ok}")
    print(f"- source_last_success_at: {stats.source_last_success_at}")
    print(f"- matches_seen: {stats.matches_seen}")
    print(f"- finished_updated: {stats.finished_updated}")
    print(f"- halftime_updated: {stats.halftime_updated}")
    print(f"- postponed_updated: {stats.postponed_updated}")
    print(f"- skipped: {stats.skipped}")
    print(f"- errors: {stats.errors}")
    print("- skipped_reasons:")
    for reason, count in sorted((stats.skipped_reasons or {}).items()):
        print(f"  - {reason}: {count}")
    if stats.overdue_closed_matches is not None:
        print("- overdue_closed_matches:")
        for row in stats.overdue_closed_matches:
            print(
                "  - "
                f"match_id: {row.get('match_id')}, "
                f"home_team: {row.get('home_team')}, "
                f"away_team: {row.get('away_team')}, "
                f"kickoff_at: {row.get('kickoff_at')}, "
                f"source_seen: {row.get('source_seen')}, "
                f"source_status: {row.get('source_status')}, "
                f"source_score: {row.get('source_score')}, "
                f"skipped_reason: {row.get('skipped_reason')}"
            )


def run_results_sync_job(dry_run: bool = False, record_log: bool = False) -> ResultsSyncStats:
    started_at = datetime.now(timezone.utc)
    source_name = os.getenv("RESULTS_SYNC_SOURCE_NAME", DEFAULT_SOURCE_NAME).strip() or DEFAULT_SOURCE_NAME
    source_type = os.getenv("RESULTS_SYNC_SOURCE_TYPE", DEFAULT_SOURCE_TYPE).strip() or DEFAULT_SOURCE_TYPE
    try:
        html = fetch_results_html()
        results = parse_results_html(html)
        stats = sync_results(results, PostgresResultsRepository(), dry_run=dry_run)
        stats.source_name = source_name
        stats.source_type = source_type
        stats.source_status = "ok"
        stats.source_fetch_ok = True
        stats.source_last_success_at = datetime.now(timezone.utc).isoformat()
        stats.overdue_closed_matches = _diagnose_overdue_closed_matches(results)
        if record_log:
            record_ops_log("results_sync", "ok" if stats.errors == 0 else "error", started_at, _stats_summary(stats), None if stats.errors == 0 else "results_sync row errors")
        return stats
    except Exception as exc:
        if record_log:
            record_ops_log(
                "results_sync",
                "error",
                started_at,
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "source_status": "fetch_error",
                    "source_fetch_ok": False,
                },
                sanitize_error(exc),
            )
        raise


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "once"
    if command not in {"once", "dry-run"}:
        print("usage: python -m api.results_sync [once|dry-run]", file=sys.stderr)
        return 2
    stats = run_results_sync_job(dry_run=command == "dry-run", record_log=command == "once")
    print_stats(stats)
    return 0 if stats.errors == 0 else 1


def _stats_summary(stats: ResultsSyncStats) -> dict[str, Any]:
    return {
        "source_name": stats.source_name,
        "source_type": stats.source_type,
        "source_status": stats.source_status,
        "source_fetch_ok": stats.source_fetch_ok,
        "source_last_success_at": stats.source_last_success_at,
        "matches_seen": stats.matches_seen,
        "finished_updated": stats.finished_updated,
        "halftime_updated": stats.halftime_updated,
        "postponed_updated": stats.postponed_updated,
        "skipped": stats.skipped,
        "errors": stats.errors,
        "skipped_reasons": stats.skipped_reasons or {},
        "overdue_closed_matches": stats.overdue_closed_matches or [],
    }


def _skip(stats: ResultsSyncStats, reason: str) -> None:
    stats.skipped += 1
    if stats.skipped_reasons is None:
        stats.skipped_reasons = {}
    stats.skipped_reasons[reason] = stats.skipped_reasons.get(reason, 0) + 1


def _already_finished_with_result(repository: Any, match_id: str) -> bool:
    match_state = getattr(repository, "match_state", None)
    if not callable(match_state):
        return False
    row = match_state(match_id)
    if row is None:
        return False
    return row.get("status") in {"finished", "completed"} and row.get("result_home") is not None and row.get("result_away") is not None


def _diagnose_overdue_closed_matches(results: list[ParsedResult]) -> list[dict[str, Any]]:
    try:
        from api.result_overdue_report import overdue_matches

        rows = overdue_matches()
    except Exception:
        return []
    by_id = {item.match_id: item for item in results}
    diagnostics: list[dict[str, Any]] = []
    for row in rows[:20]:
        match_id = str(row.get("match_id"))
        source = by_id.get(match_id)
        source_score = None
        skipped_reason = "source_not_found"
        if source is not None:
            source_score = (
                f"{source.result_home}-{source.result_away}"
                if source.result_home is not None and source.result_away is not None
                else None
            )
            if source.status != "finished":
                skipped_reason = "source_not_finished"
            elif source_score is None:
                skipped_reason = "missing_result_score"
            else:
                skipped_reason = "would_update_on_next_run"
        diagnostics.append(
            {
                **row,
                "source_seen": source is not None,
                "source_status": source.status if source else None,
                "source_score": source_score,
                "skipped_reason": skipped_reason,
            }
        )
    return diagnostics


def _parse_row(attrs: dict[str, str], text: str) -> ParsedResult | None:
    match_id = _first_attr(attrs, "data-match-id", "data-matchid", "data-id", "match-id", "id")
    if match_id and not match_id.startswith("500-"):
        match_id = _extract_match_id(match_id) or match_id
    if not match_id:
        match_id = _extract_match_id(text)
    if not match_id:
        return None

    status = _normalize_status(_first_attr(attrs, "data-status", "status") or text)
    full_score = _parse_score(_first_attr(attrs, "data-score", "data-full-score", "data-result-score", "score"))
    half_score = _parse_score(_first_attr(attrs, "data-half-score", "data-ht-score", "half-score", "ht-score"))
    if full_score is None and status == "finished":
        scores = SCORE_PATTERN.findall(text)
        if scores:
            full_score = (int(scores[0][0]), int(scores[0][1]))
            if len(scores) > 1:
                half_score = (int(scores[1][0]), int(scores[1][1]))

    return ParsedResult(
        match_id=match_id,
        status=status,
        result_home=full_score[0] if full_score else None,
        result_away=full_score[1] if full_score else None,
        ht_home=half_score[0] if half_score else None,
        ht_away=half_score[1] if half_score else None,
    )


def _first_attr(attrs: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = attrs.get(name)
        if value:
            return value.strip()
    return None


def _extract_match_id(value: str) -> str | None:
    match = re.search(r"500-\d+", value)
    return match.group(0) if match else None


def _parse_score(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = SCORE_PATTERN.search(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _normalize_status(value: str) -> str:
    lowered = value.lower()
    if any(token in lowered for token in ("postponed", "abandoned", "cancelled", "延期", "推迟", "腰斩", "取消")):
        return "postponed"
    if any(token in lowered for token in ("finished", "完场", "已完", "赛果")):
        return "finished"
    if any(token in lowered for token in ("live", "进行", "中场")):
        return "live"
    return "scheduled"


if __name__ == "__main__":
    raise SystemExit(main())

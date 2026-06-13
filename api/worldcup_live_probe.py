from __future__ import annotations

import argparse
import json
from typing import Any

from api.sources import qiumibao, zhibo8
from api.worldcup_live_source import (
    compare_local_all_overdue,
    compare_local_match,
    compare_local_recent_finished,
    fetch_worldcup_live_report,
    map_local_all_overdue,
    map_local_match,
    map_local_recent,
    map_local_recent_finished,
    map_local_upcoming,
    map_qiumibao_by_time_all_overdue,
    map_qiumibao_by_time_match,
    map_qiumibao_by_time_recent_finished,
    map_qiumibao_by_time_upcoming,
    qiumibao_known_result_candidates_recent_finished,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run probe for the zhibo8 + qiumibao World Cup live source chain.")
    parser.add_argument("--recent", action="store_true", help="Fetch current zhibo8/qiumibao live chain and print a merged summary.")
    parser.add_argument("--match-id", help="Compare one local match against the live source chain.")
    parser.add_argument("--dump-zhibo8", action="store_true", help="Dump parsed zhibo8 schedule rows.")
    parser.add_argument("--dump-qiumibao", action="store_true", help="Dump parsed qiumibao score rows.")
    parser.add_argument("--dump-qiumibao-raw", action="store_true", help="Dump raw qiumibao score rows and field diagnostics.")
    parser.add_argument("--compare-local", action="store_true", help="Compare local matches against live source rows.")
    parser.add_argument("--map-local", action="store_true", help="Map live source rows to local matches with candidate scoring.")
    parser.add_argument("--map-qiumibao-by-time", action="store_true", help="Map qiumibao score rows to local matches by UTC kickoff time only.")
    parser.add_argument("--qiumibao-known-result-candidates", action="store_true", help="Dry-run known-result qiumibao team-id candidate discovery.")
    parser.add_argument("--football-like-only", action="store_true", help="Filter qiumibao time candidates to classified/football-like rows.")
    parser.add_argument("--show-candidates", action="store_true", help="Always print qiumibao time candidate details.")
    parser.add_argument("--recent-finished", action="store_true", help="Use recent finished local matches for --compare-local.")
    parser.add_argument("--upcoming", action="store_true", help="Use upcoming scheduled/closed local matches for --map-local.")
    parser.add_argument("--all-overdue", action="store_true", help="Use overdue local matches for --compare-local.")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)

    if args.dump_zhibo8:
        _print_source_report("zhibo8", zhibo8.homepage_source_report(), args.limit)
        return 0

    if args.dump_qiumibao:
        _print_source_report("qiumibao_score", qiumibao.score_source_report(), args.limit)
        return 0

    if args.dump_qiumibao_raw:
        _print_qiumibao_raw_report(qiumibao.raw_score_source_report(), args.limit)
        return 0

    if args.qiumibao_known_result_candidates:
        _print_known_result_candidates_report(qiumibao_known_result_candidates_recent_finished(args.limit), args.limit)
        return 0

    if args.map_qiumibao_by_time:
        if args.match_id:
            _print_qiumibao_time_mapping_report(map_qiumibao_by_time_match(args.match_id, football_like_only=args.football_like_only), args.limit, show_candidates=args.show_candidates)
        elif args.all_overdue:
            _print_qiumibao_time_mapping_report(map_qiumibao_by_time_all_overdue(football_like_only=args.football_like_only), args.limit, show_candidates=args.show_candidates)
        elif args.recent_finished:
            _print_qiumibao_time_mapping_report(map_qiumibao_by_time_recent_finished(args.limit, football_like_only=args.football_like_only), args.limit, show_candidates=args.show_candidates)
        else:
            _print_qiumibao_time_mapping_report(map_qiumibao_by_time_upcoming(args.limit, football_like_only=args.football_like_only), args.limit, show_candidates=args.show_candidates)
        return 0

    if args.map_local:
        if args.match_id:
            _print_mapping_report(map_local_match(args.match_id), args.limit)
        elif args.all_overdue:
            _print_mapping_report(map_local_all_overdue(), args.limit)
        elif args.recent_finished:
            _print_mapping_report(map_local_recent_finished(args.limit), args.limit)
        elif args.upcoming:
            _print_mapping_report(map_local_upcoming(args.limit), args.limit)
        else:
            _print_mapping_report(map_local_recent(args.limit), args.limit)
        return 0

    if args.match_id:
        _print_compare_report(compare_local_match(args.match_id), args.limit)
        return 0

    if args.compare_local:
        if args.all_overdue:
            _print_compare_report(compare_local_all_overdue(), args.limit)
        else:
            _print_compare_report(compare_local_recent_finished(args.limit), args.limit)
        return 0

    _print_live_report(fetch_worldcup_live_report(), args.limit)
    return 0


def _print_source_report(name: str, report: dict[str, Any], limit: int) -> None:
    matches = report.get("matches") or []
    print(f"{name} Source Dump")
    print(f"- mode: dry-run")
    print(f"- writes_db: false")
    print(f"- source_fetch_ok: {_bool(report.get('source_fetch_ok'))}")
    print(f"- parser_error: {report.get('parser_error')}")
    print(f"- matches_seen: {len(matches)}")
    print(f"- shown: {min(limit, len(matches))}")
    for row in matches[:limit]:
        print("- match:")
        for key in _source_keys(row):
            print(f"  - {key}: {_compact(row.get(key))}")


def _print_qiumibao_raw_report(report: dict[str, Any], limit: int) -> None:
    rows = report.get("raw_rows") or []
    print("Qiumibao Raw Dump")
    print("- mode: dry-run")
    print("- writes_db: false")
    print(f"- source_fetch_ok: {_bool(report.get('source_fetch_ok'))}")
    print(f"- source_url: {_compact(report.get('source_url'))}")
    print(f"- date: {_compact(report.get('date'))}")
    print(f"- parser_error: {_compact(report.get('parser_error'))}")
    print(f"- rows_seen: {report.get('rows_seen', len(rows))}")
    print(f"- shown: {min(limit, len(rows))}")
    print("classification_field_candidates:")
    for key, value in (report.get("classification_field_candidates") or {}).items():
        print(f"- {key}:")
        print(f"  - status: {_compact(value.get('status'))}")
        print(f"  - count: {value.get('count', 0)}")
        print(f"  - sample_values: {_compact(value.get('sample_values'))}")
    for index, row in enumerate(rows[:limit]):
        print("raw_match:")
        print(f"  - index: {index}")
        print(f"  - keys: {_compact(sorted(str(key) for key in row.keys()))}")
        print("  - raw_json:")
        _print_limited_mapping(row, indent="      ")


def _print_live_report(report: dict[str, Any], limit: int) -> None:
    print("WorldCup Live Source Probe Report")
    _print_common(report)
    matches = report.get("matches") or []
    print(f"- shown_matches: {min(limit, len(matches))}")
    for row in matches[:limit]:
        print("- match:")
        for key in (
            "home_team",
            "away_team",
            "normalized_home_team",
            "normalized_away_team",
            "kickoff_at",
            "status",
            "score",
            "half_score",
            "zhibo8_match_ref",
            "possible_zhibo8_ids",
            "possible_qiumibao_ids",
            "possible_external_ids",
            "qiumibao_match_id",
            "qiumibao_link_status",
            "qiumibao_left_id",
            "qiumibao_right_id",
            "mapping_status",
            "mapping_reason",
        ):
            print(f"  - {key}: {_compact(row.get(key))}")


def _print_compare_report(report: dict[str, Any], limit: int) -> None:
    print("WorldCup Live Source Local Compare Report")
    _print_common(report)
    comparisons = report.get("comparisons") or []
    print(f"- comparisons_seen: {len(comparisons)}")
    print(f"- shown_comparisons: {min(limit, len(comparisons))}")
    for row in comparisons[:limit]:
        print("- comparison:")
        for key in (
            "local_match_id",
            "local_home_team",
            "local_away_team",
            "local_kickoff_at",
            "live_home_team",
            "live_away_team",
            "live_kickoff_at",
            "qiumibao_match_id",
            "live_status",
            "live_score",
            "live_half_score",
            "comparison_status",
            "suggested_action",
            "reason",
        ):
            print(f"  - {key}: {_compact(row.get(key))}")


def _print_mapping_report(report: dict[str, Any], limit: int) -> None:
    print("WorldCup Live Local Mapping Report")
    _print_common(report)
    print(f"- local_matches_seen: {report.get('local_matches_seen', 0)}")
    print(f"- comparison_status_summary: {json.dumps(report.get('comparison_status_summary') or {}, ensure_ascii=False, sort_keys=True)}")
    mappings = report.get("mappings") or []
    print(f"- shown_mappings: {min(limit, len(mappings))}")
    for row in mappings[:limit]:
        local = row.get("local_match") or {}
        best = row.get("best_candidate") or {}
        print("- local_match:")
        for key in (
            "match_id",
            "match_num",
            "raw_home_team",
            "raw_away_team",
            "normalized_home_team",
            "normalized_away_team",
            "kickoff_at",
            "status",
            "result",
        ):
            print(f"  - {key}: {_compact(local.get(key))}")
        print("  best_candidate:")
        if best:
            for key in (
                "live_home_team",
                "live_away_team",
                "normalized_live_home_team",
                "normalized_live_away_team",
                "live_kickoff_at",
                "live_status",
                "live_score",
                "live_half_score",
                "zhibo8_match_ref",
                "qiumibao_match_id",
                "possible_zhibo8_ids",
                "possible_qiumibao_ids",
                "possible_external_ids",
                "qiumibao_link_status",
                "match_score",
                "confidence",
                "mapping_status",
                "mapping_reason",
                "next_step",
            ):
                print(f"    - {key}: {_compact(best.get(key))}")
        else:
            print("    - none")
        print(f"  - mapping_status: {_compact(row.get('mapping_status'))}")
        print(f"  - confidence: {_compact(row.get('confidence'))}")
        print(f"  - comparison_status: {_compact(row.get('comparison_status'))}")
        print(f"  - qiumibao_link_status: {_compact(row.get('qiumibao_link_status'))}")
        print(f"  - next_step: {_compact(row.get('next_step'))}")
        print(f"  - reason: {_compact(row.get('reason'))}")
        print(f"  - candidates_count: {len(row.get('candidates') or [])}")


def _print_qiumibao_time_mapping_report(report: dict[str, Any], limit: int, show_candidates: bool = False) -> None:
    print("Qiumibao Time Mapping Report")
    print("- mode: dry-run")
    print("- writes_db: false")
    print(f"- source_fetch_ok: {_bool(report.get('source_fetch_ok'))}")
    print(f"- parser_error: {_compact(report.get('parser_error'))}")
    print(f"- local_matches_seen: {report.get('local_matches_seen', 0)}")
    print(f"- qiumibao_matches_seen: {report.get('qiumibao_matches_seen', 0)}")
    print(f"- mapping_status_summary: {json.dumps(report.get('mapping_status_summary') or {}, ensure_ascii=False, sort_keys=True)}")
    print(f"- matched_by_time_count: {report.get('matched_by_time_count', 0)}")
    print(f"- no_qiumibao_time_candidate_count: {report.get('no_qiumibao_time_candidate_count', 0)}")
    print(f"- ambiguous_qiumibao_candidates_count: {report.get('ambiguous_qiumibao_candidates_count', 0)}")
    print(f"- ambiguous_local_candidates_count: {report.get('ambiguous_local_candidates_count', 0)}")
    print(f"- matched_by_time_after_football_filter_count: {report.get('matched_by_time_after_football_filter_count', 0)}")
    print(f"- ambiguous_after_football_filter_count: {report.get('ambiguous_after_football_filter_count', 0)}")
    print(f"- football_like_only: {_bool(report.get('football_like_only'))}")
    print(f"- overdue_count: {report.get('overdue_count', 0)}")
    mappings = report.get("mappings") or []
    print(f"- shown_mappings: {min(limit, len(mappings))}")
    for row in mappings[:limit]:
        local = row.get("local_match") or {}
        best = row.get("best_candidate") or {}
        print("- local_match:")
        for key in (
            "match_id",
            "match_num",
            "raw_home_team",
            "raw_away_team",
            "normalized_home_team",
            "normalized_away_team",
            "kickoff_at_utc",
            "status",
            "local_result",
        ):
            print(f"  - {key}: {_compact(local.get(key))}")
        print(f"  - mapping_status: {_compact(row.get('mapping_status'))}")
        print(f"  - confidence: {_compact(row.get('confidence'))}")
        print(f"  - reason: {_compact(row.get('reason'))}")
        print(f"  - before_filter_candidates_count: {row.get('before_filter_candidates_count', 0)}")
        print(f"  - after_filter_candidates_count: {row.get('after_filter_candidates_count', 0)}")
        print(f"  - filtered_out_count: {row.get('filtered_out_count', 0)}")
        print(f"  - filtered_out_reasons_summary: {json.dumps(row.get('filtered_out_reasons_summary') or {}, ensure_ascii=False, sort_keys=True)}")
        print("  best_candidate:")
        if best:
            _print_qiumibao_candidate(best, indent="    ")
        else:
            print("    - none")
        print(f"  - candidates_count: {len(row.get('candidates') or [])}")
        if show_candidates or row.get("mapping_status") in {"ambiguous_qiumibao_candidates", "ambiguous_after_football_filter", "ambiguous_local_candidates"}:
            print("  candidates:")
            for candidate in (row.get("candidates") or [])[:limit]:
                print("    - candidate:")
                _print_qiumibao_candidate(candidate, indent="        ")


def _print_known_result_candidates_report(report: dict[str, Any], limit: int) -> None:
    print("Qiumibao Known Result Candidate Report")
    print("- mode: dry-run")
    print("- writes_db: false")
    print(f"- source_fetch_ok: {_bool(report.get('source_fetch_ok'))}")
    print(f"- parser_error: {_compact(report.get('parser_error'))}")
    print(f"- local_matches_seen: {report.get('local_matches_seen', 0)}")
    print(f"- qiumibao_matches_seen: {report.get('qiumibao_matches_seen', 0)}")
    for row in (report.get("known_result_candidates") or [])[:limit]:
        print("known_result_candidate:")
        for key in ("local_match_id", "local_home_team", "local_away_team", "local_result", "local_kickoff_at_utc"):
            print(f"  - {key}: {_compact(row.get(key))}")
        print("  candidates:")
        for candidate in row.get("candidates") or []:
            print("    - candidate:")
            _print_qiumibao_candidate(candidate, indent="        ", include_score_direction=True)


def _print_qiumibao_candidate(candidate: dict[str, Any], indent: str, include_score_direction: bool = False) -> None:
    keys = (
        "qiumibao_match_id",
        "qiumibao_start_time_raw",
        "qiumibao_start_time_utc",
        "time_diff_seconds",
        "raw_status",
        "status",
        "qiumibao_state",
        "qiumibao_period_cn",
        "result_home",
        "result_away",
        "qiumibao_score",
        "qiumibao_half_score",
        "qiumibao_left_id",
        "qiumibao_right_id",
        "sport_filter_status",
        "classification_fields",
        "raw_keys",
        "raw_home_team",
        "raw_away_team",
        "normalized_home_team",
        "normalized_away_team",
    )
    for key in keys:
        print(f"{indent}- {key}: {_compact(candidate.get(key))}")
    if include_score_direction:
        print(f"{indent}- score_match_direction: {_compact(candidate.get('score_match_direction'))}")


def _print_common(report: dict[str, Any]) -> None:
    print("- mode: dry-run")
    print("- writes_db: false")
    print(f"- source_fetch_ok: {_bool(report.get('source_fetch_ok'))}")
    print(f"- zhibo8_matches_seen: {report.get('zhibo8_matches_seen', 0)}")
    print(f"- qiumibao_matches_seen: {report.get('qiumibao_matches_seen', 0)}")
    print(f"- merged_matches_count: {report.get('merged_matches_count', 0)}")
    print(f"- mapping_status_summary: {json.dumps(report.get('mapping_status_summary') or {}, ensure_ascii=False, sort_keys=True)}")
    print(f"- conflicts_count: {report.get('conflicts_count', 0)}")
    print(f"- overdue_count: {report.get('overdue_count', 0)}")


def _source_keys(row: dict[str, Any]) -> tuple[str, ...]:
    if "zhibo8_match_ref" in row:
        return (
            "zhibo8_match_ref",
            "home_team",
            "away_team",
            "normalized_home_team",
            "normalized_away_team",
            "kickoff_at",
            "league",
            "status_text",
            "score",
            "zhibo8_text_url",
            "zhibo8_score_url",
            "zhibo8_animation_url",
            "zhibo8_raw_links",
            "possible_zhibo8_ids",
            "possible_qiumibao_ids",
            "possible_external_ids",
            "parser_error",
        )
    return (
        "external_id",
        "home_team",
        "away_team",
        "kickoff_at",
        "status",
        "result_home",
        "result_away",
        "ht_home",
        "ht_away",
        "left_id",
        "right_id",
        "period_cn",
        "raw_status",
        "start_time_raw",
        "start_time_utc",
        "sport_filter_status",
        "classification_fields",
        "raw_keys",
    )


def _bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _compact(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= 180 else text[:177] + "..."


def _print_limited_mapping(value: dict[str, Any], indent: str) -> None:
    for key in sorted(str(item) for item in value.keys()):
        item = value.get(key)
        if isinstance(item, dict):
            print(f"{indent}{key}:")
            for child_key in sorted(str(child) for child in item.keys()):
                print(f"{indent}  {child_key}: {_compact(item.get(child_key))}")
        elif isinstance(item, list):
            print(f"{indent}{key}: {_compact(item[:3])}")
        else:
            print(f"{indent}{key}: {_compact(item)}")


if __name__ == "__main__":
    raise SystemExit(main())

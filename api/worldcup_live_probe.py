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
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run probe for the zhibo8 + qiumibao World Cup live source chain.")
    parser.add_argument("--recent", action="store_true", help="Fetch current zhibo8/qiumibao live chain and print a merged summary.")
    parser.add_argument("--match-id", help="Compare one local match against the live source chain.")
    parser.add_argument("--dump-zhibo8", action="store_true", help="Dump parsed zhibo8 schedule rows.")
    parser.add_argument("--dump-qiumibao", action="store_true", help="Dump parsed qiumibao score rows.")
    parser.add_argument("--compare-local", action="store_true", help="Compare local matches against live source rows.")
    parser.add_argument("--map-local", action="store_true", help="Map live source rows to local matches with candidate scoring.")
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
            "possible_qiumibao_ids",
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
                "possible_qiumibao_ids",
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
            "possible_qiumibao_ids",
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
    )


def _bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _compact(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= 180 else text[:177] + "..."


if __name__ == "__main__":
    raise SystemExit(main())

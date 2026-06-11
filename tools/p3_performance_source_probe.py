from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
USER_SOURCE_FILE = DATA_DIR / "real_performance_squad_source.csv"
RAW_PERFORMANCE_DIR = DATA_DIR / "raw_performance"

USER_AGENT = "worldcup-p3-source-probe/1.0"
MAX_BYTES = 50_000
STAT_KEYWORDS = ("player", "minutes", "goals", "assists", "xg", "xa")
FORBIDDEN_MARKERS = ("fbref", "transfermarkt", "oddsportal", "betexplorer")


@dataclass(frozen=True)
class CandidateSource:
    source_name: str
    url: str
    source_risk: str
    notes: str
    blocked: bool = False
    requires_login_hint: bool = False


def default_candidates() -> list[CandidateSource]:
    return [
        CandidateSource(
            source_name="local_user_real_performance_squad_source_csv",
            url=str(USER_SOURCE_FILE),
            source_risk="low",
            notes="User-provided local CSV. Accepted only when present and validated by p3_build_real_performance_csv.",
        ),
        CandidateSource(
            source_name="local_user_raw_performance_csv_directory",
            url=str(RAW_PERFORMANCE_DIR),
            source_risk="low",
            notes="User-provided raw CSV directory. Accepted only when files are present and validated.",
        ),
        CandidateSource(
            source_name="FootyStats CSV downloads",
            url="https://footystats.org/download-stats-csv",
            source_risk="medium",
            notes="Potentially usable only with explicit plan/license and user-provided export authorization.",
            requires_login_hint=True,
        ),
        CandidateSource(
            source_name="Kaggle player stats datasets",
            url="https://www.kaggle.com/datasets/hubertsidorowicz/football-players-stats-2025-2026",
            source_risk="high",
            notes="Not adopted when sourced from FBref or when authorization cannot be verified.",
            blocked=True,
            requires_login_hint=True,
        ),
        CandidateSource(
            source_name="Understat public pages",
            url="https://understat.com/",
            source_risk="medium",
            notes="League-specific xG pages; does not provide audited full 48-team squad coverage by itself.",
        ),
        CandidateSource(
            source_name="FIFA public tournament pages",
            url="https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026",
            source_risk="low",
            notes="Official source, but public tournament pages usually do not expose club minutes/goals/assists/xG/xA CSV.",
        ),
    ]


def probe_sources(
    candidates: Iterable[CandidateSource] | None = None,
    fetcher: Callable[[str, int], tuple[int | None, str, str]] | None = None,
    timeout_seconds: int = 8,
) -> dict[str, object]:
    candidates = list(candidates or default_candidates())
    fetcher = fetcher or _fetch_url
    rows = [_probe_candidate(candidate, fetcher, timeout_seconds) for candidate in candidates]
    usable = [row for row in rows if row["recommended_use"] == "yes"]
    blocked = [row for row in rows if row["recommended_use"] == "no"]
    result = "PASS" if usable else "WAIT"
    return {
        "candidate_sources": rows,
        "usable_sources": [row["source_name"] for row in usable],
        "blocked_sources": [row["source_name"] for row in blocked],
        "recommended_next_step": _recommended_next_step(result, usable),
        "result": result,
    }


def print_report(report: dict[str, object]) -> None:
    print("P3 Performance Source Probe Report")
    print("")
    print("1. Candidate sources")
    for row in report["candidate_sources"]:
        print(f"- source_name: {row['source_name']}")
        print(f"  url: {row['url']}")
        print(f"  accessible: {str(row['accessible']).lower()}")
        print(f"  contains_player_stats: {str(row['contains_player_stats']).lower()}")
        print(f"  contains_minutes: {str(row['contains_minutes']).lower()}")
        print(f"  contains_goals: {str(row['contains_goals']).lower()}")
        print(f"  contains_assists: {str(row['contains_assists']).lower()}")
        print(f"  contains_xg_xa: {str(row['contains_xg_xa']).lower()}")
        print(f"  requires_login: {str(row['requires_login']).lower()}")
        print(f"  source_risk: {row['source_risk']}")
        print(f"  recommended_use: {row['recommended_use']}")
        print(f"  notes: {row['notes']}")
    print("")
    print("2. Summary")
    print(f"- usable_sources: {report['usable_sources']}")
    print(f"- blocked_sources: {report['blocked_sources']}")
    print(f"- recommended_next_step: {report['recommended_next_step']}")
    print(f"- result: {report['result']}")


def _probe_candidate(
    candidate: CandidateSource,
    fetcher: Callable[[str, int], tuple[int | None, str, str]],
    timeout_seconds: int,
) -> dict[str, object]:
    if candidate.url.endswith(".csv") or "raw_performance" in candidate.url:
        return _probe_local_candidate(candidate)
    if candidate.blocked or _contains_forbidden_marker(candidate.url):
        return _blocked_row(candidate, accessible=False, notes=candidate.notes)
    try:
        status_code, content_type, text = fetcher(candidate.url, timeout_seconds)
    except Exception as exc:  # pragma: no cover - exercised through mock tests
        return _blocked_row(candidate, accessible=False, notes=f"{candidate.notes}; fetch_error={type(exc).__name__}")
    text = text[:MAX_BYTES]
    analysis = analyze_text(text)
    accessible = bool(status_code and 200 <= status_code < 400)
    requires_login = candidate.requires_login_hint or _looks_like_login_wall(text)
    recommended = (
        accessible
        and not requires_login
        and candidate.source_risk == "low"
        and analysis["contains_player_stats"]
        and analysis["contains_minutes"]
        and analysis["contains_goals"]
        and analysis["contains_assists"]
    )
    notes = f"{candidate.notes}; status_code={status_code}; content_type={content_type}"
    return {
        "source_name": candidate.source_name,
        "url": candidate.url,
        "accessible": accessible,
        **analysis,
        "requires_login": requires_login,
        "source_risk": candidate.source_risk,
        "recommended_use": "yes" if recommended else "no",
        "notes": notes,
    }


def analyze_text(text: str) -> dict[str, bool]:
    lower = text.lower()
    return {
        "contains_player_stats": "player" in lower and ("stat" in lower or "statistics" in lower),
        "contains_minutes": "minutes" in lower or "mins" in lower,
        "contains_goals": "goals" in lower or "goal" in lower,
        "contains_assists": "assists" in lower or "assist" in lower,
        "contains_xg_xa": "xg" in lower or "expected goals" in lower or "xa" in lower,
    }


def _probe_local_candidate(candidate: CandidateSource) -> dict[str, object]:
    path = Path(candidate.url)
    if path.is_dir():
        files = sorted(path.glob("*.csv"))
        accessible = bool(files)
        notes = f"{candidate.notes}; csv_files={len(files)}"
    else:
        accessible = path.exists()
        notes = f"{candidate.notes}; exists={accessible}"
    return {
        "source_name": candidate.source_name,
        "url": candidate.url,
        "accessible": accessible,
        "contains_player_stats": accessible,
        "contains_minutes": accessible,
        "contains_goals": accessible,
        "contains_assists": accessible,
        "contains_xg_xa": False,
        "requires_login": False,
        "source_risk": candidate.source_risk,
        "recommended_use": "yes" if accessible else "no",
        "notes": notes,
    }


def _blocked_row(candidate: CandidateSource, accessible: bool, notes: str) -> dict[str, object]:
    return {
        "source_name": candidate.source_name,
        "url": candidate.url,
        "accessible": accessible,
        "contains_player_stats": False,
        "contains_minutes": False,
        "contains_goals": False,
        "contains_assists": False,
        "contains_xg_xa": False,
        "requires_login": candidate.requires_login_hint,
        "source_risk": candidate.source_risk,
        "recommended_use": "no",
        "notes": notes,
    }


def _fetch_url(url: str, timeout_seconds: int) -> tuple[int | None, str, str]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_seconds)
    return response.status_code, response.headers.get("content-type", ""), response.text[:MAX_BYTES]


def _contains_forbidden_marker(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in FORBIDDEN_MARKERS)


def _looks_like_login_wall(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in ("sign in", "log in", "login", "subscribe", "pricing", "captcha"))


def _recommended_next_step(result: str, usable: list[dict[str, object]]) -> str:
    if result == "PASS":
        return f"Review and transform authorized source: {usable[0]['source_name']}"
    return "WAIT: provide an authorized CSV or reviewed public export before generating real_performance_squad.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe legal P3 recent performance data sources")
    parser.add_argument("--timeout-seconds", type=int, default=8)
    args = parser.parse_args(argv)
    report = probe_sources(timeout_seconds=args.timeout_seconds)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

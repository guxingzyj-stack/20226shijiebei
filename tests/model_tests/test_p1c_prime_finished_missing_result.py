from __future__ import annotations

from datetime import datetime, timezone

from model import p1c_prime


def test_finished_with_null_score_is_not_evaluable() -> None:
    kickoff = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    report = p1c_prime.build_prospective_calibration_summary(
        [
            p1c_prime.MatchRow(
                match_id="500-1359172",
                status="finished",
                kickoff_at=kickoff,
                result_home=None,
                result_away=None,
                home_team="Mexico",
                away_team="South Africa",
            )
        ],
        [],
        [],
        min_required_matches=1,
    )

    assert report["data_availability"]["evaluable_matches"] == 0
    assert report["skips"]["finished_but_missing_result"] == 1
    assert report["skipped_match_details"][0]["skip_reason"] == "finished_but_missing_result"
    assert report["result"] == "WAIT"


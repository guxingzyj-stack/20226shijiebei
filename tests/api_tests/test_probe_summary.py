import json

from ops import probe_summary


def match_payload(model_version=35, ev_model_version=35, ev="0.2", research_only=True, suggestion_eligible=False):
    return {
        "match_id": "500-1",
        "prediction_status": {"available": True, "reason": None},
        "latest_prediction": {"model_version": model_version},
        "ev_signals": [
            {
                "model_version": ev_model_version,
                "ev": ev,
                "research_only": research_only,
                "suggestion_eligible": suggestion_eligible,
            }
        ],
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_probe_summary_pass(tmp_path):
    leaderboard = [{"username": "real", "roi": "0"}]
    write_json(tmp_path / "leaderboard.json", leaderboard)
    write_json(tmp_path / "mexico.json", match_payload())
    write_json(tmp_path / "germany.json", match_payload())

    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    assert summary["result"] == "PASS"
    assert summary["leaderboard"]["has_roi"] is True
    assert summary["mexico"]["ev_model_version_aligned"] is True


def test_probe_summary_warns_on_test_users(tmp_path):
    write_json(tmp_path / "leaderboard.json", [{"username": "codex_blocker_1", "roi": "0"}])
    write_json(tmp_path / "mexico.json", match_payload())
    write_json(tmp_path / "germany.json", match_payload())

    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    assert summary["result"] == "WARN"
    assert summary["leaderboard"]["test_user_count"] == 1


def test_probe_summary_fails_on_internal_id(tmp_path):
    write_json(tmp_path / "leaderboard.json", [{"id": 1, "username": "real", "roi": "0"}])
    write_json(tmp_path / "mexico.json", match_payload())
    write_json(tmp_path / "germany.json", match_payload())

    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    assert summary["result"] == "FAIL"


def test_probe_summary_fails_on_model_version_mismatch(tmp_path):
    write_json(tmp_path / "leaderboard.json", [{"username": "real", "roi": "0"}])
    write_json(tmp_path / "mexico.json", match_payload(model_version=35, ev_model_version=34))
    write_json(tmp_path / "germany.json", match_payload())

    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    assert summary["result"] == "FAIL"


def test_probe_summary_fails_on_unprotected_high_ev(tmp_path):
    write_json(tmp_path / "leaderboard.json", [{"username": "real", "roi": "0"}])
    write_json(tmp_path / "mexico.json", match_payload(research_only=False, suggestion_eligible=True))
    write_json(tmp_path / "germany.json", match_payload())

    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    assert summary["result"] == "FAIL"
    assert summary["mexico"]["unprotected_high_ev_count"] == 1


def test_probe_summary_prints_expected_sections(tmp_path, capsys):
    write_json(tmp_path / "leaderboard.json", [{"username": "real", "roi": "0"}])
    write_json(tmp_path / "mexico.json", match_payload())
    write_json(tmp_path / "germany.json", match_payload())
    summary = probe_summary.summarize(tmp_path / "mexico.json", tmp_path / "germany.json", tmp_path / "leaderboard.json")

    probe_summary.print_summary(summary)

    output = capsys.readouterr().out
    assert "Production Probe Summary" in output
    assert "1. leaderboard" in output
    assert "2. Mexico" in output
    assert "3. Germany" in output

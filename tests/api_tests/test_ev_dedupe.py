from api.db import _dedupe_and_sort_ev_signals


def test_dedupe_ev_signals_keeps_latest_per_selection_then_sorts_by_ev():
    rows = [
        {"play_type": "crs", "selection": "1:3", "ev": 2.46, "created_at": "2026-06-10T10:00:00Z"},
        {"play_type": "crs", "selection": "1:3", "ev": 2.10, "created_at": "2026-06-10T11:00:00Z"},
        {"play_type": "crs", "selection": "0:3", "ev": 3.00, "created_at": "2026-06-10T09:00:00Z"},
        {"play_type": "had", "selection": "3", "ev": 0.12, "created_at": "2026-06-10T12:00:00Z"},
    ]

    deduped = _dedupe_and_sort_ev_signals(rows, limit=20)

    assert [(row["play_type"], row["selection"]) for row in deduped] == [
        ("crs", "0:3"),
        ("crs", "1:3"),
        ("had", "3"),
    ]
    assert deduped[1]["created_at"] == "2026-06-10T11:00:00Z"
    assert deduped[1]["ev"] == 2.10


def test_dedupe_ev_signals_applies_limit():
    rows = [
        {"play_type": "crs", "selection": str(index), "ev": index, "created_at": "2026-06-10T10:00:00Z"}
        for index in range(25)
    ]

    deduped = _dedupe_and_sort_ev_signals(rows, limit=20)

    assert len(deduped) == 20
    assert deduped[0]["ev"] == 24
    assert deduped[-1]["ev"] == 5

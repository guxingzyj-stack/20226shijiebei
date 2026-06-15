from __future__ import annotations

import inspect

from api.db import Database


def test_latest_prediction_uses_match_latest_row_not_global_model_version() -> None:
    source = inspect.getsource(Database.latest_prediction)
    compact = " ".join(source.split()).lower()

    assert "from predictions" in compact
    assert "where match_id = %s" in compact
    assert "order by created_at desc, id desc" in compact
    assert "from model_versions" not in compact


def test_ev_signals_align_to_match_latest_prediction_version() -> None:
    latest_source = " ".join(inspect.getsource(Database.latest_ev_signals).split()).lower()
    best_source = " ".join(inspect.getsource(Database.best_ev_signal).split()).lower()

    for source in (latest_source, best_source):
        assert "select p.model_version from predictions p" in source
        assert "where p.match_id = %s" in source
        assert "order by p.created_at desc, p.id desc" in source

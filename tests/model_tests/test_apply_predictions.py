from contextlib import contextmanager

from model import apply_predictions


def test_repeated_predict_once_does_not_append_predict_run_to_model_version_name(monkeypatch):
    inserted_names: list[str] = []

    @contextmanager
    def fake_conn():
        yield object()

    def fake_fetch_latest_model_version(_conn):
        if inserted_names:
            return {"id": len(inserted_names), "name": inserted_names[-1], "params": apply_predictions.DEFAULT_MODEL_PARAMS}
        return {
            "id": 1,
            "name": "p1b-dixon-coles-predict-run-predict-run",
            "params": apply_predictions.DEFAULT_MODEL_PARAMS,
        }

    def fake_insert_model_version(_conn, name, _params):
        inserted_names.append(name)
        return len(inserted_names)

    monkeypatch.setattr(apply_predictions.db, "get_conn", fake_conn)
    monkeypatch.setattr(apply_predictions.db, "fetch_team_ratings", lambda _conn: {})
    monkeypatch.setattr(apply_predictions.db, "fetch_latest_model_version", fake_fetch_latest_model_version)
    monkeypatch.setattr(apply_predictions.db, "insert_model_version", fake_insert_model_version)
    monkeypatch.setattr(apply_predictions.db, "fetch_upcoming_matches", lambda _conn: [])
    monkeypatch.setattr(apply_predictions.db, "update_model_version_params", lambda _conn, _model_version_id, _params: None)

    apply_predictions.predict_once()
    apply_predictions.predict_once()

    assert inserted_names == [
        "p1b-dixon-coles-predict-run",
        "p1b-dixon-coles-predict-run",
    ]

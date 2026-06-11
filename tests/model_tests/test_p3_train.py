from model import p3_train


def test_train_returns_zero_weight_when_team_features_insufficient(monkeypatch):
    monkeypatch.setattr(p3_train, "_load_team_features", lambda: [])

    result = p3_train.train(dry_run=True)

    assert result["status"] == "insufficient_team_features"
    assert result["w_gbm"] == 0


def test_train_returns_gbm_unavailable_without_lightgbm(monkeypatch):
    monkeypatch.setattr(p3_train, "_load_team_features", lambda: [{"team": str(index), "elo": 1500} for index in range(16)])
    monkeypatch.setattr(p3_train, "train_gbm_or_stub", lambda *args, **kwargs: type("Result", (), {"status": "gbm_unavailable"})())

    result = p3_train.train()

    assert result["status"] == "gbm_unavailable"
    assert result["w_gbm"] == 0


def test_predict_dry_run_keeps_gbm_zero_weight(monkeypatch):
    monkeypatch.setattr(p3_train, "_load_team_features", lambda: [{"team": str(index), "elo": 1500} for index in range(16)])

    result = p3_train.predict(dry_run=True)

    assert result["status"] == "dry_run"
    assert result["w_gbm"] == 0

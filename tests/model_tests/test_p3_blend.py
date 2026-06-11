from model.p3_blend import blend_three_way, choose_p3_weights, normalize_blend_weights


def test_weights_normalize():
    weights = normalize_blend_weights({"w_dc": 2, "w_market": 1, "w_gbm": 1})

    assert sum(weights.values()) == 1
    assert weights["w_dc"] == 0.5


def test_zero_gbm_equivalent_to_p1():
    p_dc = {"3": 0.5, "1": 0.3, "0": 0.2}
    p_market = {"3": 0.4, "1": 0.3, "0": 0.3}

    blended = blend_three_way(p_dc, p_market, {"3": 0.9, "1": 0.05, "0": 0.05}, {"w_dc": 0.3, "w_market": 0.7, "w_gbm": 0})

    assert abs(blended["3"] - 0.43) < 1e-12
    assert abs(blended["1"] - 0.30) < 1e-12
    assert abs(blended["0"] - 0.27) < 1e-12


def test_gbm_worse_than_p1_gets_zero_weight():
    result = choose_p3_weights({"w_dc": 0.3, "w_market": 0.7}, "ok", p1_rps=0.20, gbm_rps=0.25, requested_w_gbm=0.2)

    assert result["status"] == "gbm_zero_weight_rps_worse_than_p1"
    assert result["weights"]["w_gbm"] == 0


def test_gbm_unavailable_gets_zero_weight():
    result = choose_p3_weights({"w_dc": 0.3, "w_market": 0.7}, "gbm_unavailable")

    assert result["weights"]["w_gbm"] == 0

from model.production_checks import missing_ev_play_types, probability_sum_ok, score_matrix_shape_ok


def test_score_matrix_shape_check_detects_bad_shape():
    assert score_matrix_shape_ok([[0.0 for _ in range(11)] for _ in range(11)])
    assert not score_matrix_shape_ok([[0.0 for _ in range(10)] for _ in range(11)])
    assert not score_matrix_shape_ok([[0.0 for _ in range(11)] for _ in range(10)])


def test_probability_sum_check():
    assert probability_sum_ok({"p_home": 0.5, "p_draw": 0.25, "p_away": 0.25})
    assert not probability_sum_ok({"p_home": 0.5, "p_draw": 0.25, "p_away": 0.20})


def test_missing_ev_play_types():
    missing = missing_ev_play_types([{"play_type": "had"}, {"play_type": "hhad"}])
    assert {"crs", "ttg", "hafu"} <= missing

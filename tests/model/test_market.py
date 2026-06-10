import pytest

from model.market import _shin_raw_probs, normalize_probs, proportional_devig, shin_devig_three_way


def test_proportional_devig_sums_to_one():
    probs = proportional_devig({"3": 1.30, "1": 4.15, "0": 8.40})
    assert sum(probs.values()) == pytest.approx(1.0)


def test_shin_devig_sums_to_one_and_positive():
    odds = {"3": 1.30, "1": 4.15, "0": 8.40}
    shin = shin_devig_three_way(odds)
    assert sum(shin.values()) == pytest.approx(1.0)
    assert all(value > 0 for value in shin.values())


def test_shin_equal_odds_are_close_to_one_third():
    shin = shin_devig_three_way({"3": 2.0, "1": 2.0, "0": 2.0})
    assert shin["3"] == pytest.approx(1 / 3)
    assert shin["1"] == pytest.approx(1 / 3)
    assert shin["0"] == pytest.approx(1 / 3)


def test_shin_rejects_invalid_odds():
    with pytest.raises(ValueError, match="positive"):
        shin_devig_three_way({"3": 1.30, "1": 0.0, "0": 8.40})
    with pytest.raises(ValueError, match="three selections"):
        shin_devig_three_way({"3": 1.30, "1": 4.15})


def test_shin_does_not_fallback_to_proportional_for_skewed_market():
    odds = {"3": 1.30, "1": 4.15, "0": 8.40}
    prop = proportional_devig(odds)
    shin = shin_devig_three_way(odds)

    assert abs(sum(shin.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in shin.values())
    assert any(abs(shin[k] - prop[k]) > 1e-6 for k in odds)


def test_shin_raw_probs_formula_shape():
    odds = {"3": 1.30, "1": 4.15, "0": 8.40}
    raw = _shin_raw_probs(odds, z=0.01)

    assert set(raw.keys()) == set(odds.keys())
    assert all(v > 0 for v in raw.values())


def test_normalize_probs():
    assert normalize_probs({"a": 2, "b": 2}) == {"a": 0.5, "b": 0.5}
    with pytest.raises(ValueError):
        normalize_probs({"a": 0, "b": 0})

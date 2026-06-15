from __future__ import annotations

import builtins
import importlib
import sys

from api._devig import calc_three_way_margin_and_vig, proportional_devig_three_way
from api.banter import build_banter
from api.verdict import build_verdict
from api.vig import calculate_had_vig, market_implied_prob_had


def test_verdict_draw_highest_has_priority():
    result = build_verdict(0.34, 0.36, 0.30, "荷兰", "日本")

    assert result == {"verdict_type": "draw_favored", "verdict": "模型认为平局可能性最大"}


def test_verdict_strong_home_and_away():
    assert build_verdict(0.61, 0.2, 0.19, "巴西", "摩洛哥") == {
        "verdict_type": "strong_home",
        "verdict": "模型看好巴西获胜",
    }
    assert build_verdict(0.18, 0.2, 0.62, "韩国", "德国") == {
        "verdict_type": "strong_away",
        "verdict": "模型看好德国获胜",
    }


def test_verdict_lean_and_balanced():
    assert build_verdict(0.48, 0.3, 0.22, "阿根廷", "墨西哥")["verdict_type"] == "lean_home"
    assert build_verdict(0.42, 0.31, 0.27, "阿根廷", "墨西哥") == {
        "verdict_type": "balanced",
        "verdict": "模型认为这场势均力敌",
    }
    assert build_verdict(None, None, None, "阿根廷", "墨西哥")["verdict_type"] == "balanced"


def test_banter_draw_favored_skips_historical_meme():
    result = build_banter("m1", "荷兰", "日本", 0.33, 0.35, 0.32, "draw_favored")

    assert result["banter_type"] == "draw_favored"
    assert "巨人杀手" not in result["banter"]


def test_banter_balanced_skips_morocco_meme():
    result = build_banter("m2", "巴西", "摩洛哥", 0.34, 0.33, 0.33, "balanced")

    assert result["banter_type"] == "balanced"
    assert "摩洛哥 2022 年杀进四强" not in result["banter"]


def test_banter_historical_meme_allowed_for_leaning_verdicts_and_is_stable():
    first = build_banter("m3", "荷兰", "日本", 0.55, 0.25, 0.20, "lean_home")
    second = build_banter("m3", "荷兰", "日本", 0.55, 0.25, 0.20, "lean_home")

    assert first == second
    assert first["banter_type"] == "historical_japan"
    assert "巨人杀手" in first["banter"]


def test_banter_historical_priority_and_favorite_and_base_pools():
    assert build_banter("m4", "日本", "摩洛哥", 0.66, 0.2, 0.14, "strong_home")["banter_type"] == "historical_japan"
    assert build_banter("m5", "阿根廷", "沙特", 0.18, 0.2, 0.62, "strong_away")["banter_type"] == "historical_saudi"
    favorite = build_banter("m6", "法国", "厄瓜多尔", 0.70, 0.2, 0.1, "strong_home")
    assert favorite["banter_type"] == "favorite"
    base = build_banter("m7", "法国", "厄瓜多尔", 0.50, 0.3, 0.2, "lean_home")
    assert base["banter_type"] == "base"


def test_had_vig_calculation_and_missing_odds():
    result = calculate_had_vig({"3": 2.0, "1": 3.0, "0": 4.0})

    assert result is not None
    assert abs(result["margin"] - (1 / 2.0 + 1 / 3.0 + 1 / 4.0 - 1)) < 1e-12
    assert abs(result["vig"] - (result["margin"] / (1 + result["margin"]))) < 1e-12
    assert calculate_had_vig({"3": 2.0, "1": 3.0}) is None


def test_market_implied_prob_sums_to_one():
    probs = market_implied_prob_had({"3": 1.8, "1": 3.5, "0": 5.0})

    assert probs is not None
    assert set(probs) == {"home", "draw", "away"}
    assert abs(sum(probs.values()) - 1.0) < 1e-9


def test_api_devig_margin_is_reasonable():
    result = calc_three_way_margin_and_vig(1.86, 3.33, 3.43)

    assert result is not None
    assert result["margin"] > 0
    assert 0 < result["vig"] < 0.15


def test_api_proportional_devig_three_way_sums_to_one():
    probs = proportional_devig_three_way(1.86, 3.33, 3.43)

    assert probs is not None
    assert abs(sum(probs.values()) - 1.0) < 1e-12


def test_api_vig_imports_without_model_package(monkeypatch):
    sys.modules.pop("api.vig", None)
    original_import = builtins.__import__

    def blocked_model_import(name, *args, **kwargs):
        if name == "model" or name.startswith("model."):
            raise ModuleNotFoundError("blocked model import in API test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_model_import)

    module = importlib.import_module("api.vig")

    assert module.market_implied_prob_had({"3": 2.0, "1": 3.0, "0": 4.0}) is not None

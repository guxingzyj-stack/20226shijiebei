from __future__ import annotations

from model.dixon_coles import lambdas_from_elo, score_matrix, three_way_probs
from model.market import normalize_probs


DEFAULT_SANITY_PARAMS = {"c": 0.2739041058888925, "k": 0.5, "H": 165.2903826781101, "rho": -0.037923562385050666}


def scenario_probs(
    elo_home: float,
    elo_away: float,
    is_home: bool,
    params: dict[str, float] | None = None,
) -> dict[str, float]:
    params = {**DEFAULT_SANITY_PARAMS, **(params or {})}
    lambda_home, lambda_away = lambdas_from_elo(elo_home, elo_away, params["c"], params["k"], params["H"], is_home)
    p_home, p_draw, p_away = three_way_probs(score_matrix(lambda_home, lambda_away, params["rho"]))
    probs = normalize_probs({"3": p_home, "1": p_draw, "0": p_away})
    return {
        "elo_home": elo_home,
        "elo_away": elo_away,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "p_home": probs["3"],
        "p_draw": probs["1"],
        "p_away": probs["0"],
    }


def sanity_report(params: dict[str, float] | None = None) -> dict[str, dict[str, float]]:
    return {
        "Argentina vs Haiti": scenario_probs(1900, 1100, False, params),
        "Equal Elo neutral": scenario_probs(1500, 1500, False, params),
    }


def main() -> int:
    report = sanity_report()
    for name, values in report.items():
        print(f"{name}:")
        for key, value in values.items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

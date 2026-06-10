from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests


RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_RESULTS_PATH = DATA_DIR / "international_results.csv"
REQUIRED_COLUMNS = ["date", "home_team", "away_team", "home_score", "away_score", "tournament", "neutral"]


def download_results(path: Path = DEFAULT_RESULTS_PATH, url: str = RESULTS_URL) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def load_results(path: Path = DEFAULT_RESULTS_PATH, since: str = "2015-01-01") -> pd.DataFrame:
    data = pd.read_csv(path, usecols=REQUIRED_COLUMNS, parse_dates=["date"])
    data = data[data["date"] >= pd.Timestamp(since)].copy()
    data = data.dropna(subset=REQUIRED_COLUMNS)
    data["home_score"] = data["home_score"].astype(int)
    data["away_score"] = data["away_score"].astype(int)
    data["neutral"] = data["neutral"].astype(bool)
    return data.sort_values("date").reset_index(drop=True)

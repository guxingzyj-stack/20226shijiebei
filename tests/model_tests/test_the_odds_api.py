import pytest

from model.the_odds_api import MISSING_API_KEY_MESSAGE, extract_h2h_matches, get_api_key


def test_missing_the_odds_api_key_is_clear_and_secret_free(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        get_api_key()

    assert str(excinfo.value) == MISSING_API_KEY_MESSAGE
    assert "apiKey=" not in str(excinfo.value)


def test_snapshot_json_extracts_h2h_match_with_median_bookmaker_odds():
    snapshot = {
        "timestamp": "2022-12-18T12:00:00Z",
        "data": [
            {
                "id": "event-1",
                "sport_key": "soccer_fifa_world_cup",
                "commence_time": "2022-12-18T15:00:00Z",
                "home_team": "Argentina",
                "away_team": "France",
                "bookmakers": [
                    {
                        "key": "bet365",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Argentina", "price": 2.0},
                                    {"name": "Draw", "price": 3.0},
                                    {"name": "France", "price": 4.0},
                                ],
                            }
                        ],
                    },
                    {
                        "key": "pinnacle",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Argentina", "price": 3.0},
                                    {"name": "Draw", "price": 5.0},
                                    {"name": "France", "price": 5.0},
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }

    rows = extract_h2h_matches(snapshot)

    assert len(rows) == 1
    assert rows[0].odds == {"3": 2.5, "1": 4.0, "0": 4.5}
    assert rows[0].bookmaker == "median_available_bookmakers:bet365,pinnacle"


def test_snapshot_json_uses_team_alias_matching():
    snapshot = {
        "timestamp": "2022-11-29T18:00:00Z",
        "data": [
            {
                "id": "event-2",
                "sport_key": "soccer_fifa_world_cup",
                "commence_time": "2022-11-29T19:00:00Z",
                "home_team": "USA",
                "away_team": "IR Iran",
                "bookmakers": [
                    {
                        "key": "unibet",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "United States", "price": 2.2},
                                    {"name": "Draw", "price": 3.2},
                                    {"name": "Iran", "price": 3.6},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    rows = extract_h2h_matches(snapshot)

    assert len(rows) == 1
    assert rows[0].home_team == "United States"
    assert rows[0].away_team == "Iran"

from decimal import Decimal

from api.settlement import MatchResult, settle_leg, settle_parlay


def test_had_home_draw_away():
    assert settle_leg("had", "3", MatchResult(2, 0)) == "win"
    assert settle_leg("had", "1", MatchResult(1, 1)) == "win"
    assert settle_leg("had", "0", MatchResult(0, 2)) == "win"


def test_hhad_exact_handicap_draw():
    assert settle_leg("hhad", "1", MatchResult(2, 1), goal_line=-1) == "win"


def test_ttg_seven_plus():
    assert settle_leg("ttg", "7", MatchResult(4, 3)) == "win"
    assert settle_leg("ttg", "6", MatchResult(4, 3)) == "lose"


def test_crs_exact_and_other_buckets():
    assert settle_leg("crs", "10", MatchResult(1, 0)) == "win"
    assert settle_leg("crs", "\u80dc\u5176\u4ed6", MatchResult(6, 0)) == "win"
    assert settle_leg("crs", "\u5e73\u5176\u4ed6", MatchResult(4, 4)) == "win"
    assert settle_leg("crs", "\u8d1f\u5176\u4ed6", MatchResult(0, 6)) == "win"


def test_hafu_covers_common_combinations():
    assert settle_leg("hafu", "33", MatchResult(2, 0, ht_home=1, ht_away=0)) == "win"
    assert settle_leg("hafu", "13", MatchResult(2, 1, ht_home=0, ht_away=0)) == "win"
    assert settle_leg("hafu", "01", MatchResult(1, 1, ht_home=0, ht_away=1)) == "win"


def test_hafu_missing_half_time_is_void():
    assert settle_leg("hafu", "33", MatchResult(2, 0)) == "void"


def test_parlay_all_win_loss_and_void_leg():
    legs = [
        {"match_id": "m1", "play_type": "had", "selection": "3", "odds": "2.00"},
        {"match_id": "m2", "play_type": "ttg", "selection": "7", "odds": "3.00"},
    ]
    results = {"m1": MatchResult(1, 0), "m2": MatchResult(4, 3)}
    settled = settle_parlay(legs, results, Decimal("10"))
    assert settled["status"] == "won"
    assert settled["payout"] == Decimal("60.00")

    results["m2"] = MatchResult(1, 0)
    settled = settle_parlay(legs, results, Decimal("10"))
    assert settled["status"] == "lost"
    assert settled["payout"] == Decimal("0")

    void_leg = [{"match_id": "m3", "play_type": "hafu", "selection": "33", "odds": "5.00"}]
    settled = settle_parlay(void_leg, {"m3": MatchResult(1, 0)}, Decimal("10"))
    assert settled["status"] == "won"
    assert settled["payout"] == Decimal("10")

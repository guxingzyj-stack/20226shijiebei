from __future__ import annotations

from datetime import date

from model import p3_fifa_squad_pdf


def test_parse_table_row_maps_official_profile_fields() -> None:
    raw_row = [
        "7",
        "FW",
        "MAHREZ Riyad",
        None,
        "Riyad Karim",
        "MAHREZ",
        None,
        "MAHREZ",
        "21/02/1991",
        None,
        "Al Ahli FC (KSA)",
        None,
        "179",
        "116",
        "38",
    ]

    row = p3_fifa_squad_pdf.parse_table_row(
        raw_row,
        team="Algeria",
        team_code="ALG",
        page_index=1,
        retrieved_at="2026-06-12",
    )

    assert row is not None
    assert row["team"] == "Algeria"
    assert row["player_name"] == "MAHREZ Riyad"
    assert row["position"] == "FW"
    assert row["club"] == "Al Ahli FC (KSA)"
    assert row["height_cm"] == "179"
    assert row["caps"] == "116"
    assert row["national_team_goals"] == "38"
    assert row["source"] == p3_fifa_squad_pdf.SOURCE_URL


def test_parse_table_row_ignores_header() -> None:
    assert (
        p3_fifa_squad_pdf.parse_table_row(
            ["#", "POS", "PLAYER NAME"],
            team="Algeria",
            team_code="ALG",
            page_index=1,
            retrieved_at="2026-06-12",
        )
        is None
    )


def test_age_from_dob_is_deterministic() -> None:
    assert p3_fifa_squad_pdf._age_from_dob("21/02/1991", today=date(2026, 6, 12)) == "35"

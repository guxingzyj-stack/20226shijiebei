from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crawler"))

from sources import m500  # noqa: E402


def test_data_isend_maps_to_closed_not_finished() -> None:
    assert m500._status_from_sale_attrs({"data-isend": "1"}) == "closed"


def test_open_sale_maps_to_scheduled() -> None:
    assert m500._status_from_sale_attrs({"data-isend": "0"}) == "scheduled"


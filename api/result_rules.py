from __future__ import annotations

from typing import Any


FINISHED_STATUSES = {"finished", "completed"}


def ready_for_result_evaluation(row: dict[str, Any]) -> bool:
    return (
        str(row.get("status") or "").strip().lower() in FINISHED_STATUSES
        and row.get("result_home") is not None
        and row.get("result_away") is not None
    )


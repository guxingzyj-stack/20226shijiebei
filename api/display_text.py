from __future__ import annotations

import re
from typing import Any


CJK = r"\u3400-\u4dbf\u4e00-\u9fff"
CJK_PUNCT = r"，。！？；：、（）《》“”‘’"
SPACE_CHARS = r"\u0020\u00a0\u1680\u180e\u2000-\u200d\u202f\u205f\u3000\ufeff"
ZERO_WIDTH_TRANSLATION = {
    ord("\ufeff"): None,
    ord("\u180e"): None,
    ord("\u200b"): None,
    ord("\u200c"): None,
    ord("\u200d"): None,
}


def compact_cjk_spaces(text: str | None) -> str | None:
    if text is None:
        return None

    value = str(text).translate(ZERO_WIDTH_TRANSLATION)
    value = value.replace("\u00a0", " ").replace("\u3000", " ").strip()

    value = re.sub(rf"(?<=[{CJK}])[{SPACE_CHARS}]+(?=[{CJK}])", "", value)
    value = re.sub(rf"(?<=[{CJK}])[{SPACE_CHARS}]+(?=[{CJK_PUNCT}])", "", value)
    value = re.sub(rf"(?<=[{CJK_PUNCT}])[{SPACE_CHARS}]+(?=[{CJK}])", "", value)
    value = re.sub(rf"(?<=[{CJK}])[{SPACE_CHARS}]+(?=\()", "", value)
    value = re.sub(rf"(?<=\()[{SPACE_CHARS}]+(?=[{CJK}])", "", value)
    value = re.sub(rf"(?<=[{CJK}])[{SPACE_CHARS}]+(?=\))", "", value)
    value = re.sub(r"[ \t\r\n]+", " ", value).strip()
    return value


def clean_display_text(text: str | None) -> str | None:
    return compact_cjk_spaces(text)


def clean_match_public_fields(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("league", "home_team", "away_team", "verdict", "banter"):
        if key in payload:
            payload[key] = clean_display_text(payload.get(key))

    prediction_status = payload.get("prediction_status")
    if isinstance(prediction_status, dict):
        prediction_status["message"] = clean_display_text(prediction_status.get("message"))

    latest_prediction = payload.get("latest_prediction")
    if isinstance(latest_prediction, dict):
        for key in ("display_name", "model_version_name"):
            if key in latest_prediction:
                latest_prediction[key] = clean_display_text(latest_prediction.get(key))

    return payload

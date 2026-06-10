from __future__ import annotations


CN_TO_EN = {
    "阿根廷": "Argentina",
    "澳大利亚": "Australia",
    "巴西": "Brazil",
    "比利时": "Belgium",
    "波黑": "Bosnia and Herzegovina",
    "加拿大": "Canada",
    "智利": "Chile",
    "哥伦比亚": "Colombia",
    "哥斯达": "Costa Rica",
    "哥斯达黎加": "Costa Rica",
    "克罗地亚": "Croatia",
    "捷克": "Czechia",
    "丹麦": "Denmark",
    "厄瓜多尔": "Ecuador",
    "英格兰": "England",
    "法国": "France",
    "德国": "Germany",
    "加纳": "Ghana",
    "伊朗": "Iran",
    "意大利": "Italy",
    "日本": "Japan",
    "韩国": "South Korea",
    "墨西哥": "Mexico",
    "摩洛哥": "Morocco",
    "荷兰": "Netherlands",
    "尼日利亚": "Nigeria",
    "波兰": "Poland",
    "葡萄牙": "Portugal",
    "卡塔尔": "Qatar",
    "沙特": "Saudi Arabia",
    "塞内加尔": "Senegal",
    "塞尔维亚": "Serbia",
    "南非": "South Africa",
    "西班牙": "Spain",
    "瑞士": "Switzerland",
    "突尼斯": "Tunisia",
    "乌拉圭": "Uruguay",
    "美国": "United States",
    "威尔士": "Wales",
}


def to_english_team_name(name: str) -> str:
    try:
        return CN_TO_EN[name]
    except KeyError as exc:
        raise KeyError(f"unmapped team name: {name}") from exc


def find_unmapped_teams(db_teams: set[str]) -> set[str]:
    return set(db_teams) - set(CN_TO_EN)

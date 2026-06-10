from __future__ import annotations


CN_TO_EN = {
    "阿根廷": "Argentina",
    "阿尔及利亚": "Algeria",
    "澳大利亚": "Australia",
    "奥地利": "Austria",
    "巴拉圭": "Paraguay",
    "巴拿马": "Panama",
    "巴西": "Brazil",
    "比利时": "Belgium",
    "波黑": "Bosnia and Herzegovina",
    "佛得角": "Cape Verde",
    "刚果(金)": "DR Congo",
    "加拿大": "Canada",
    "智利": "Chile",
    "哥伦比亚": "Colombia",
    "哥斯达": "Costa Rica",
    "哥斯达黎加": "Costa Rica",
    "克罗地亚": "Croatia",
    "库拉索": "Curaçao",
    "捷克": "Czechia",
    "丹麦": "Denmark",
    "厄瓜多尔": "Ecuador",
    "埃及": "Egypt",
    "英格兰": "England",
    "法国": "France",
    "德国": "Germany",
    "加纳": "Ghana",
    "伊朗": "Iran",
    "伊拉克": "Iraq",
    "意大利": "Italy",
    "日本": "Japan",
    "约旦": "Jordan",
    "韩国": "South Korea",
    "墨西哥": "Mexico",
    "摩洛哥": "Morocco",
    "荷兰": "Netherlands",
    "新西兰": "New Zealand",
    "尼日利亚": "Nigeria",
    "挪威": "Norway",
    "波兰": "Poland",
    "葡萄牙": "Portugal",
    "卡塔尔": "Qatar",
    "沙特": "Saudi Arabia",
    "沙特阿拉伯": "Saudi Arabia",
    "塞内加尔": "Senegal",
    "塞尔维亚": "Serbia",
    "南非": "South Africa",
    "苏格兰": "Scotland",
    "西班牙": "Spain",
    "瑞典": "Sweden",
    "瑞士": "Switzerland",
    "突尼斯": "Tunisia",
    "土耳其": "Turkey",
    "乌拉圭": "Uruguay",
    "乌兹别克": "Uzbekistan",
    "美国": "United States",
    "威尔士": "Wales",
    "海地": "Haiti",
    "科特迪瓦": "Ivory Coast",
}


def to_english_team_name(name: str) -> str:
    try:
        return CN_TO_EN[name]
    except KeyError as exc:
        raise KeyError(f"unmapped team name: {name}") from exc


def find_unmapped_teams(db_teams: set[str]) -> set[str]:
    return set(db_teams) - set(CN_TO_EN)

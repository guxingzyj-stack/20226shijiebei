import pytest

from model.team_names import find_unmapped_teams, to_english_team_name


def test_paraguay_mapping():
    assert to_english_team_name("巴拉圭") == "Paraguay"


def test_current_p0_team_mappings():
    teams = {
        "乌兹别克",
        "乌拉圭",
        "伊拉克",
        "伊朗",
        "佛得角",
        "克罗地亚",
        "刚果(金)",
        "加拿大",
        "加纳",
        "南非",
        "卡塔尔",
        "厄瓜多尔",
        "哥伦比亚",
        "土耳其",
        "埃及",
        "塞内加尔",
        "墨西哥",
        "奥地利",
        "巴拉圭",
        "巴拿马",
        "巴西",
        "库拉索",
        "德国",
        "挪威",
        "捷克",
        "摩洛哥",
        "新西兰",
        "日本",
        "比利时",
        "沙特阿拉伯",
        "法国",
        "波黑",
        "海地",
        "澳大利亚",
        "瑞典",
        "瑞士",
        "科特迪瓦",
        "突尼斯",
        "约旦",
        "美国",
        "苏格兰",
        "英格兰",
        "荷兰",
        "葡萄牙",
        "西班牙",
        "阿尔及利亚",
        "阿根廷",
        "韩国",
    }
    assert find_unmapped_teams(teams) == set()


def test_unmapped_team_raises_key_error_with_original_name():
    with pytest.raises(KeyError, match="未知队"):
        to_english_team_name("未知队")

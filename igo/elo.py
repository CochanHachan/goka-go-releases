# -*- coding: utf-8 -*-
"""碁華 ELO レーティングシステム"""
from igo.lang import get_language

# --------------- Elo Rating System ---------------
# (rank_str, elo_min, elo_max) - ordered highest to lowest
ELO_RANGES = [
    # Pro ranks
    ("プロ9段", 3951, 4100),
    ("プロ8段", 3901, 3950),
    ("プロ7段", 3851, 3900),
    ("プロ6段", 3801, 3850),
    ("プロ5段", 3701, 3800),
    ("プロ4段", 3601, 3700),
    ("プロ3段", 3501, 3600),
    ("プロ2段", 3401, 3500),
    ("プロ初段", 3301, 3400),
    # Amateur dan ranks
    ("9段", 3100, 3300),
    ("8段", 3000, 3099),
    ("7段", 2900, 2999),
    ("6段", 2800, 2899),
    ("5段", 2650, 2799),
    ("4段", 2500, 2649),
    ("3段", 2350, 2499),
    ("2段", 2200, 2349),
    ("1段", 2050, 2199),
    # Amateur kyu ranks
    ("1級", 1900, 2049),
    ("2級", 1800, 1899),
    ("3級", 1700, 1799),
    ("4級", 1600, 1699),
    ("5級", 1500, 1599),
    ("6級", 1400, 1499),
    ("7級", 1300, 1399),
    ("8級", 1200, 1299),
    ("9級", 1100, 1199),
    ("10級", 1000, 1099),
    ("11級", 940, 999),
    ("12級", 880, 939),
    ("13級", 820, 879),
    ("14級", 760, 819),
    ("15級", 700, 759),
    ("16級", 640, 699),
    ("17級", 580, 639),
    ("18級", 520, 579),
    ("19級", 460, 519),
    ("20級", 400, 459),
]
ELO_K_FACTOR = 32
ELO_MIN = 400
ELO_MAX = 4200  # Chinese Pro 9 Dan reaches 4200

# -----------------------------------------------------------------------
# 各国語版 ELO レーティング対応表
# -----------------------------------------------------------------------
# 中国語版（日本基準より約+100 ELO）
ELO_RANGES_ZH = [
    ("职业九段", 4051, 4200),
    ("职业八段", 4001, 4050),
    ("职业七段", 3951, 4000),
    ("职业六段", 3901, 3950),
    ("职业五段", 3801, 3900),
    ("职业四段", 3701, 3800),
    ("职业三段", 3601, 3700),
    ("职业二段", 3501, 3600),
    ("职业初段", 3401, 3500),
    ("九段",    3200, 3400),
    ("八段",    3100, 3199),
    ("七段",    3000, 3099),
    ("六段",    2900, 2999),
    ("五段",    2750, 2899),
    ("四段",    2600, 2749),
    ("三段",    2450, 2599),
    ("二段",    2300, 2449),
    ("一段",    2150, 2299),
    ("一级",    2000, 2149),
    ("二级",    1900, 1999),
    ("三级",    1800, 1899),
    ("四级",    1700, 1799),
    ("五级",    1600, 1699),
    ("六级",    1500, 1599),
    ("七级",    1400, 1499),
    ("八级",    1300, 1399),
    ("九级",    1200, 1299),
    ("十级",    1100, 1199),
    ("十一级",  1040, 1099),
    ("十二级",   980, 1039),
    ("十三级",   920,  979),
    ("十四级",   860,  919),
    ("十五级",   800,  859),
    ("十六级",   740,  799),
    ("十七级",   680,  739),
    ("十八级",   620,  679),
    ("十九级",   560,  619),
    ("二十级",   500,  559),
]

# 英語版（EGF/AGA 基準、日本基準より約+50 ELO）
ELO_RANGES_EN = [
    ("Pro 9 Dan", 4001, 4150),
    ("Pro 8 Dan", 3951, 4000),
    ("Pro 7 Dan", 3901, 3950),
    ("Pro 6 Dan", 3851, 3900),
    ("Pro 5 Dan", 3751, 3850),
    ("Pro 4 Dan", 3651, 3750),
    ("Pro 3 Dan", 3551, 3650),
    ("Pro 2 Dan", 3451, 3550),
    ("Pro 1 Dan", 3351, 3450),
    ("9 Dan",    3150, 3350),
    ("8 Dan",    3050, 3149),
    ("7 Dan",    2950, 3049),
    ("6 Dan",    2850, 2949),
    ("5 Dan",    2700, 2849),
    ("4 Dan",    2550, 2699),
    ("3 Dan",    2400, 2549),
    ("2 Dan",    2250, 2399),
    ("1 Dan",    2100, 2249),
    ("1 Kyu",    1950, 2099),
    ("2 Kyu",    1850, 1949),
    ("3 Kyu",    1750, 1849),
    ("4 Kyu",    1650, 1749),
    ("5 Kyu",    1550, 1649),
    ("6 Kyu",    1450, 1549),
    ("7 Kyu",    1350, 1449),
    ("8 Kyu",    1250, 1349),
    ("9 Kyu",    1150, 1249),
    ("10 Kyu",   1050, 1149),
    ("11 Kyu",    990, 1049),
    ("12 Kyu",    930,  989),
    ("13 Kyu",    870,  929),
    ("14 Kyu",    810,  869),
    ("15 Kyu",    750,  809),
    ("16 Kyu",    690,  749),
    ("17 Kyu",    630,  689),
    ("18 Kyu",    570,  629),
    ("19 Kyu",    510,  569),
    ("20 Kyu",    450,  509),
]

# 韓国語版（韓国オンライン基準、日本基準より約-300 ELO）
ELO_RANGES_KO = [
    ("프로9단",  3651, 3800),
    ("프로8단",  3601, 3650),
    ("프로7단",  3551, 3600),
    ("프로6단",  3501, 3550),
    ("프로5단",  3401, 3500),
    ("프로4단",  3301, 3400),
    ("프로3단",  3201, 3300),
    ("프로2단",  3101, 3200),
    ("프로초단", 3001, 3100),
    ("9단",    2800, 3000),
    ("8단",    2700, 2799),
    ("7단",    2600, 2699),
    ("6단",    2500, 2599),
    ("5단",    2350, 2499),
    ("4단",    2200, 2349),
    ("3단",    2050, 2199),
    ("2단",    1900, 2049),
    ("1단",    1750, 1899),
    ("1급",    1600, 1749),
    ("2급",    1500, 1599),
    ("3급",    1400, 1499),
    ("4급",    1300, 1399),
    ("5급",    1200, 1299),
    ("6급",    1100, 1199),
    ("7급",    1000, 1099),
    ("8급",     900,  999),
    ("9급",     800,  899),
    ("10급",    700,  799),
    ("11급",    640,  699),
    ("12급",    580,  639),
    ("13급",    520,  579),
    ("14급",    460,  519),
    ("15급",    400,  459),
]

# 言語コード → ELO対応表
ELO_RANGES_BY_LANG = {
    "ja": ELO_RANGES,
    "zh": ELO_RANGES_ZH,
    "en": ELO_RANGES_EN,
    "ko": ELO_RANGES_KO,
}

# 棋力サブレベル（弱・中・強）の多言語表示
_SUB_LEVEL_LABELS = {
    "ja": ("弱", "中", "強"),
    "en": ("-",  "=",  "+"),
    "zh": ("弱", "中", "强"),
    "ko": ("약", "중", "강"),
}


def get_elo_ranges(lang=None):
    """指定言語のELO対応表を返す。省略時は現在の言語。"""
    if lang is None:
        lang = get_language()
    return ELO_RANGES_BY_LANG.get(lang, ELO_RANGES)


def rank_to_initial_elo(rank_str):
    """Convert rank string to initial Elo (center of range).
    Searches all language tables."""
    for ranges in ELO_RANGES_BY_LANG.values():
        for r, elo_min, elo_max in ranges:
            if r == rank_str:
                return (elo_min + elo_max) // 2
    return 1050  # default: 10級 center


def _is_dan_rank(rank_str):
    """段位かどうか判定（全言語対応）。"""
    r = rank_str
    return ("段" in r or "단" in r or "Dan" in r or "dan" in r)


def elo_to_rank(elo):
    """Convert Elo to rank string in the current language."""
    ranges = get_elo_ranges()
    lo = ranges[-1][1]
    hi = ranges[0][2]
    elo_c = max(lo, min(hi, elo))
    for r, elo_min, elo_max in ranges:
        if elo_min <= elo_c <= elo_max:
            return r
    return ranges[-1][0]


def elo_to_display_rank(elo):
    """Convert Elo to localized display rank with sub-level."""
    if elo <= 0:
        return "---"
    lang = get_language()
    ranges = get_elo_ranges(lang)
    sub = _SUB_LEVEL_LABELS.get(lang, _SUB_LEVEL_LABELS["ja"])
    lo = ranges[-1][1]
    hi = ranges[0][2]
    elo_c = max(lo, min(hi, elo))
    for r, elo_min, elo_max in ranges:
        if elo_min <= elo_c <= elo_max:
            span = elo_max - elo_min + 1
            third = span / 3.0
            if elo_c < elo_min + third:
                return "{}({})".format(r, sub[0])
            elif elo_c < elo_min + 2 * third:
                return "{}({})".format(r, sub[1])
            else:
                return "{}({})".format(r, sub[2])
    return "{}({})".format(ranges[-1][0], sub[0])


def calculate_elo_update(my_elo, opp_elo, my_score):
    """Calculate new Elo rating. my_score: 1.0=win, 0.0=loss, 0.5=draw."""
    expected = 1.0 / (1.0 + 10.0 ** ((opp_elo - my_elo) / 400.0))
    new_elo = round(my_elo + ELO_K_FACTOR * (my_score - expected))
    return max(ELO_MIN, new_elo)


def rank_to_localized(ja_rank_key, lang=None):
    """日本語ランクキーを指定言語の対応ランク文字列に変換する。"""
    if lang is None:
        lang = get_language()
    if lang == "ja":
        return ja_rank_key
    # 日本語テーブルでELO中間値を求める
    for r, elo_min, elo_max in ELO_RANGES:
        if r == ja_rank_key:
            mid = (elo_min + elo_max) // 2
            target = ELO_RANGES_BY_LANG.get(lang, ELO_RANGES)
            for tr, tmin, tmax in target:
                if tmin <= mid <= tmax:
                    return tr
            break
    return ja_rank_key  # fallback


def get_localized_go_ranks():
    """現在の言語のELO対応表からアマチュア段級リストを返す（登録画面用）。"""
    ranges = get_elo_ranges()
    pro_prefixes = ("プロ", "职业", "Pro ", "프로")
    return [r for r, _, _ in ranges
            if not any(r.startswith(p) for p in pro_prefixes)]


def localized_rank_to_internal(localized_str):
    """コンボで選択されたランク文字列をそのまま返す（言語別テーブルを直接使用）。"""
    return localized_str

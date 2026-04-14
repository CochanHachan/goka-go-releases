# -*- coding: utf-8 -*-
"""碁華 列挙型定義 — 表示文字列とロジックの分離（デグレ原因 #9 対策）"""
import enum


class TimeControl(enum.Enum):
    """持ち時間制度。内部ロジックでは文字列 "Fischer" / "10分" ではなくこの enum を使う。"""
    BYOYOMI = "byoyomi"
    FISCHER = "fischer"

    @classmethod
    def from_display(cls, display_str: str) -> "TimeControl":
        """コンボボックスの表示文字列から enum に変換する。
        "Fischer" → FISCHER, "10分" 等 → BYOYOMI"""
        if display_str == "Fischer":
            return cls.FISCHER
        return cls.BYOYOMI


# ---------------------------------------------------------------------------
# 持ち時間の表示文字列 ↔ 数値変換
# ---------------------------------------------------------------------------

def parse_main_time_minutes(display_str: str) -> int:
    """表示文字列 "10分" → 10。Fischer の場合は呼ばない想定。"""
    return int(display_str.replace("\u5206", ""))


def parse_byo_time_seconds(display_str: str) -> int:
    """表示文字列 "30秒" → 30。"""
    return int(display_str.replace("\u79d2", ""))


def parse_byo_periods(display_str: str) -> int:
    """表示文字列 "5回" → 5, "∞" → 0。"""
    if display_str == "\u221e":
        return 0
    return int(display_str.replace("\u56de", ""))


def parse_komi(display_str: str) -> float:
    """表示文字列 "7目半" → 7.5, "6目半" → 6.5, "5目半" → 5.5。"""
    if "5" in display_str:
        return 5.5
    if "6" in display_str:
        return 6.5
    return 7.5


def format_komi_display(komi: float) -> str:
    """コミ数値 → 表示文字列。7.5 → "7目半"。"""
    return "{}\u76ee\u534a".format(int(komi))


def format_time_display(time_control: str, main_time: int, byo_time: int,
                        byo_periods: int, fischer_increment: int = 0) -> str:
    """持ち時間設定 → 表示文字列。time_control は "byoyomi" or "fischer"。"""
    main_m = main_time // 60
    if time_control == "fischer":
        return "F {}\u5206+{}\u79d2".format(main_m, fischer_increment)
    byo_str = "\u221e" if byo_periods == 0 else str(byo_periods)
    return "{}\u5206+{}\u79d2\u00d7{}".format(main_m, byo_time, byo_str)

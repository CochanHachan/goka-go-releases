# -*- coding: utf-8 -*-
"""碁華 対局状態の集約 — 散在していた状態を1か所に（デグレ原因 #1 対策）

app.py に散らばっていた _cloud_main_time, _cloud_byo_time, _cloud_byo_periods,
_cloud_komi, _cloud_time_control, _cloud_fischer_increment, _is_hosting,
_match_settings 等を MatchSettings / MatchState に集約する。
"""
import logging
import json
import socket

from igo.constants import NET_UDP_PORT

logger = logging.getLogger(__name__)


class MatchSettings:
    """対局条件を保持するデータクラス。

    従来は App に _cloud_main_time, _cloud_byo_time ... と個別属性で散在していた。
    MatchSettings に集約することで、設定の受け渡しが1オブジェクトで完結する。
    """
    __slots__ = (
        "main_time", "byo_time", "byo_periods", "komi",
        "time_control", "fischer_increment",
    )

    def __init__(self, main_time=600, byo_time=30, byo_periods=5,
                 komi=7.5, time_control="byoyomi", fischer_increment=0):
        self.main_time = main_time
        self.byo_time = byo_time
        self.byo_periods = byo_periods
        self.komi = komi
        self.time_control = time_control
        self.fischer_increment = fischer_increment

    def to_dict(self):
        """WebSocket送信やネットワーク通信で使う dict を返す。"""
        return {
            "main_time": self.main_time,
            "byo_time": self.byo_time,
            "byo_periods": self.byo_periods,
            "komi": self.komi,
            "time_control": self.time_control,
            "fischer_increment": self.fischer_increment,
        }

    @classmethod
    def from_dict(cls, d):
        """dict から MatchSettings を復元する。"""
        return cls(
            main_time=d.get("main_time", 600),
            byo_time=d.get("byo_time", 30),
            byo_periods=d.get("byo_periods", 5),
            komi=d.get("komi", 7.5),
            time_control=d.get("time_control", "byoyomi"),
            fischer_increment=d.get("fischer_increment", 0),
        )

    @classmethod
    def from_tuple(cls, t):
        """旧 _match_settings タプル (main_time, byo_time, byo_periods, komi, time_control, fischer_increment) から変換。"""
        return cls(
            main_time=t[0], byo_time=t[1], byo_periods=t[2],
            komi=t[3], time_control=t[4], fischer_increment=t[5],
        )

    def as_tuple(self):
        """旧互換: (main_time, byo_time, byo_periods, komi, time_control, fischer_increment)"""
        return (self.main_time, self.byo_time, self.byo_periods,
                self.komi, self.time_control, self.fischer_increment)


def broadcast_match_taken(host_name):
    """match_taken を LAN にブロードキャストする。

    従来は match_dialog._cancel_hosting, _hosting_timeout, _on_close,
    app._cancel_hosting_if_active, app._on_server_connect の 5か所に
    コピーペーストされていた UDP ブロードキャストを共通化する。
    （デグレ原因 #8: コピペコード対策）
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = json.dumps({
            "type": "match_taken",
            "host_name": host_name,
        }).encode("utf-8")
        sock.sendto(msg, ("<broadcast>", NET_UDP_PORT + 1))
        sock.close()
    except OSError:
        logger.debug("Failed to broadcast match_taken", exc_info=True)

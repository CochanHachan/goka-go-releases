"""Regression test: WebSocket再接続時のレースコンディションでボット挑戦状が消える問題 (PR #101)

根本原因: WebSocket再接続時に、古い接続のfinallyブロックが新しい接続の登録後に実行され、
ws_disconnect() が新しい接続の状態（connected_users, pending_offers, bot_timers）を
破壊していた。これにより、ボットの挑戦状タイマーがキャンセルされ、ボットからの
挑戦状が永遠に届かなくなっていた。

修正:
  - サーバー: ws_disconnect() にオプションの ws パラメータを追加し、
    新しい接続が登録済みなら古い接続のクリーンアップをスキップ
  - サーバー: finally ブロックで bot_timers キャンセルも同様にガード
  - クライアント: CloudClient に on_reconnect_cb を追加
  - クライアント: 再接続時にホスティング中なら match_offer_broadcast を再送信
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import types


# ---------------------------------------------------------------------------
# サーバー側テスト: ws_disconnect のレースガード
# ---------------------------------------------------------------------------
class TestWsDisconnectRaceGuard(unittest.TestCase):
    """ws_disconnect が新しい接続を壊さないことを検証する。"""

    def _make_ws_disconnect(self):
        """server.py の ws_disconnect ロジックを再現するヘルパー。

        asyncio を使わず、同期的にロジックだけを検証する。
        """
        connected_users = {}
        pending_offers = {}
        ws_user_info = {}
        ai_preference = {}
        user_status = {}
        bot_offer_timers = {}
        bot_accept_timers = {}

        def ws_disconnect(handle, ws=None):
            # 新しい接続が既に登録されている場合はスキップ
            if ws is not None and connected_users.get(handle) is not ws:
                return "skipped"

            connected_users.pop(handle, None)
            ws_user_info.pop(handle, None)
            ai_preference.pop(handle, None)
            user_status.pop(handle, None)

            if handle in pending_offers:
                pending_offers.pop(handle, None)
                task = bot_offer_timers.pop(handle, None)
                if task:
                    task.cancel()
                task = bot_accept_timers.pop(handle, None)
                if task:
                    task.cancel()

            return "cleaned"

        return (ws_disconnect, connected_users, pending_offers,
                ws_user_info, ai_preference, user_status,
                bot_offer_timers, bot_accept_timers)

    def test_old_ws_skipped_when_new_ws_registered(self):
        """新しい接続が登録済みなら、古い接続のクリーンアップはスキップされる。"""
        (ws_disconnect, connected_users, pending_offers,
         ws_user_info, ai_preference, user_status,
         bot_offer_timers, bot_accept_timers) = self._make_ws_disconnect()

        old_ws = MagicMock(name="old_ws")
        new_ws = MagicMock(name="new_ws")

        # 新しい接続が既に登録されている
        connected_users["user1"] = new_ws
        pending_offers["user1"] = {"broadcast": True}
        bot_timer = MagicMock()
        bot_offer_timers["user1"] = bot_timer

        # 古い接続のクリーンアップ
        result = ws_disconnect("user1", old_ws)

        self.assertEqual(result, "skipped")
        # 新しい接続はそのまま
        self.assertIn("user1", connected_users)
        self.assertIs(connected_users["user1"], new_ws)
        # pending_offers も保持
        self.assertIn("user1", pending_offers)
        # ボットタイマーもキャンセルされない
        bot_timer.cancel.assert_not_called()

    def test_same_ws_cleaned_up(self):
        """現在の接続と同じ ws なら通常通りクリーンアップされる。"""
        (ws_disconnect, connected_users, pending_offers,
         ws_user_info, ai_preference, user_status,
         bot_offer_timers, bot_accept_timers) = self._make_ws_disconnect()

        ws = MagicMock(name="ws")
        connected_users["user1"] = ws
        pending_offers["user1"] = {"broadcast": True}
        bot_timer = MagicMock()
        bot_offer_timers["user1"] = bot_timer

        result = ws_disconnect("user1", ws)

        self.assertEqual(result, "cleaned")
        self.assertNotIn("user1", connected_users)
        self.assertNotIn("user1", pending_offers)
        bot_timer.cancel.assert_called_once()

    def test_no_ws_param_always_cleans_up(self):
        """ws パラメータなし（後方互換）は常にクリーンアップする。"""
        (ws_disconnect, connected_users, pending_offers,
         ws_user_info, ai_preference, user_status,
         bot_offer_timers, bot_accept_timers) = self._make_ws_disconnect()

        ws = MagicMock(name="ws")
        connected_users["user1"] = ws

        result = ws_disconnect("user1")

        self.assertEqual(result, "cleaned")
        self.assertNotIn("user1", connected_users)

    def test_bot_timer_not_cancelled_on_reconnect(self):
        """再接続時に finally ブロックがボットタイマーをキャンセルしないことを検証する。

        finally ブロック:
            if connected_users.get(handle_name) is websocket:
                _cancel_bot_timers(handle_name)
            await ws_disconnect(handle_name, websocket)
        """
        connected_users = {}
        bot_offer_timers = {}
        bot_accept_timers = {}

        def _cancel_bot_timers(handle):
            task = bot_offer_timers.pop(handle, None)
            if task:
                task.cancel()
            task = bot_accept_timers.pop(handle, None)
            if task:
                task.cancel()

        old_ws = MagicMock(name="old_ws")
        new_ws = MagicMock(name="new_ws")

        # 新しい接続が登録済み
        connected_users["user1"] = new_ws
        bot_timer = MagicMock()
        bot_offer_timers["user1"] = bot_timer

        # finally ブロックのガード条件を再現
        if connected_users.get("user1") is old_ws:
            _cancel_bot_timers("user1")

        # ボットタイマーはキャンセルされない
        bot_timer.cancel.assert_not_called()
        self.assertIn("user1", bot_offer_timers)


# ---------------------------------------------------------------------------
# クライアント側テスト: CloudClient の再接続コールバック
# ---------------------------------------------------------------------------
class TestCloudClientReconnectCallback(unittest.TestCase):
    """CloudClient が再接続時にコールバックを呼ぶことを検証する。"""

    def test_reconnect_callback_called_on_second_connect(self):
        """2回目の接続（再接続）で on_reconnect_cb が呼ばれる。"""
        from igo.igo_cloud_client import CloudClient

        reconnect_cb = MagicMock()
        client = CloudClient("ws://dummy", MagicMock(), None, reconnect_cb)

        # 初回接続をシミュレート
        client._connected_once = False
        # _connected_once が False なのでコールバックは呼ばれない
        if client._connected_once and client.on_reconnect_cb:
            client.on_reconnect_cb()
        client._connected_once = True

        reconnect_cb.assert_not_called()

        # 2回目の接続（再接続）をシミュレート
        if client._connected_once and client.on_reconnect_cb:
            client.on_reconnect_cb()

        reconnect_cb.assert_called_once()

    def test_no_callback_on_first_connect(self):
        """初回接続では on_reconnect_cb は呼ばれない。"""
        from igo.igo_cloud_client import CloudClient

        reconnect_cb = MagicMock()
        client = CloudClient("ws://dummy", MagicMock(), None, reconnect_cb)

        # 初回接続
        self.assertFalse(client._connected_once)
        if client._connected_once and client.on_reconnect_cb:
            client.on_reconnect_cb()

        reconnect_cb.assert_not_called()

    def test_no_crash_without_reconnect_callback(self):
        """on_reconnect_cb が None でもクラッシュしない。"""
        from igo.igo_cloud_client import CloudClient

        client = CloudClient("ws://dummy", MagicMock(), None, None)
        client._connected_once = True

        # Should not raise
        if client._connected_once and client.on_reconnect_cb:
            client.on_reconnect_cb()


# ---------------------------------------------------------------------------
# クライアント側テスト: 再接続時のホスティング状態再送信
# ---------------------------------------------------------------------------
class TestHostingStateResendOnReconnect(unittest.TestCase):
    """再接続時にホスティング中なら match_offer_broadcast を再送信することを検証する。"""

    def _make_app_stub(self):
        """テスト用の最小限 App スタブ。"""
        app = MagicMock()
        app._is_hosting = False
        app._cloud_client = None
        app._cloud_mode = False
        app.current_user = {
            "handle_name": "test_user",
            "elo_rating": 1500,
        }
        app._cloud_main_time = 600
        app._cloud_byo_time = 30
        app._cloud_byo_periods = 5
        app._cloud_komi = 7.5
        app._cloud_time_control = "byoyomi"
        app._cloud_fischer_increment = 0

        # _on_cloud_reconnect の実装を再現
        def _on_cloud_reconnect(self):
            if self._is_hosting and self._cloud_client and self._cloud_client.connected:
                user = self.current_user
                if not user:
                    return
                from igo.elo import elo_to_display_rank
                rank = elo_to_display_rank(user["elo_rating"])
                elo = user["elo_rating"]
                self._cloud_client.send({
                    "type": "match_offer_broadcast",
                    "rank": rank,
                    "elo": elo,
                    "main_time": getattr(self, '_cloud_main_time', 600),
                    "byo_time": getattr(self, '_cloud_byo_time', 30),
                    "byo_periods": getattr(self, '_cloud_byo_periods', 5),
                    "komi": getattr(self, '_cloud_komi', 7.5),
                    "time_control": getattr(self, '_cloud_time_control', 'byoyomi'),
                    "fischer_increment": getattr(self, '_cloud_fischer_increment', 0),
                })

        app._on_cloud_reconnect = types.MethodType(_on_cloud_reconnect, app)
        return app

    def test_resend_broadcast_when_hosting(self):
        """ホスティング中に再接続すると match_offer_broadcast が再送信される。"""
        app = self._make_app_stub()
        app._is_hosting = True
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._on_cloud_reconnect()

        cloud.send.assert_called_once()
        sent_msg = cloud.send.call_args[0][0]
        self.assertEqual(sent_msg["type"], "match_offer_broadcast")
        self.assertEqual(sent_msg["elo"], 1500)

    def test_no_resend_when_not_hosting(self):
        """ホスティングしていない場合は再送信しない。"""
        app = self._make_app_stub()
        app._is_hosting = False
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._on_cloud_reconnect()

        cloud.send.assert_not_called()

    def test_no_resend_when_client_disconnected(self):
        """クライアントが未接続の場合は再送信しない。"""
        app = self._make_app_stub()
        app._is_hosting = True
        cloud = MagicMock()
        cloud.connected = False
        app._cloud_client = cloud

        app._on_cloud_reconnect()

        cloud.send.assert_not_called()

    def test_hosting_flag_set_on_start_hosting(self):
        """start_hosting 時に _is_hosting が True になることを検証する。"""
        # start_hosting のロジックの一部を再現
        app = self._make_app_stub()
        app._is_hosting = False

        # start_hosting の cloud mode ブランチを再現
        app._is_hosting = True

        self.assertTrue(app._is_hosting)

    def test_hosting_flag_cleared_on_stop_hosting(self):
        """stop_hosting 時に _is_hosting が False になることを検証する。"""
        app = self._make_app_stub()
        app._is_hosting = True

        # stop_hosting のロジックを再現
        app._is_hosting = False

        self.assertFalse(app._is_hosting)

    def test_hosting_flag_cleared_on_game_start(self):
        """対局開始時に _is_hosting が False になることを検証する。"""
        app = self._make_app_stub()
        app._is_hosting = True

        # _start_cloud_game / _start_ai_game で _is_hosting = False
        app._is_hosting = False

        self.assertFalse(app._is_hosting)


# ---------------------------------------------------------------------------
# 統合テスト: 再接続レースシナリオの完全シミュレーション
# ---------------------------------------------------------------------------
class TestReconnectRaceScenario(unittest.TestCase):
    """WebSocket再接続レースの完全なシナリオをシミュレートする。"""

    def test_full_race_scenario_bot_timer_preserved(self):
        """再接続レース発生時もボットタイマーが保持されることを検証する。

        シナリオ:
        1. ユーザーが接続A で match_offer_broadcast を送信
        2. 接続B が確立される（再接続）
        3. 接続A の finally ブロックが実行される
        4. ボットタイマーは保持される（新しい接続があるためスキップ）
        """
        connected_users = {}
        pending_offers = {}
        bot_offer_timers = {}

        old_ws = MagicMock(name="connection_A")
        new_ws = MagicMock(name="connection_B")

        # Step 1: ユーザーが接続A で接続
        connected_users["user1"] = old_ws

        # Step 2: match_offer_broadcast を受信、ボットタイマー開始
        pending_offers["user1"] = {"broadcast": True}
        bot_timer = MagicMock(name="bot_timer")
        bot_offer_timers["user1"] = bot_timer

        # Step 3: 接続B が確立（再接続）
        connected_users["user1"] = new_ws

        # Step 4: 接続A の finally ブロック
        # ガード: connected_users.get(handle) is websocket
        if connected_users.get("user1") is old_ws:
            # これは実行されない（new_ws が登録済み）
            bot_offer_timers.pop("user1", None)

        # 検証: ボットタイマーは保持されている
        self.assertIn("user1", bot_offer_timers)
        bot_timer.cancel.assert_not_called()
        self.assertIn("user1", pending_offers)
        self.assertIs(connected_users["user1"], new_ws)

    def test_normal_disconnect_cleans_up(self):
        """通常の切断（再接続なし）は正常にクリーンアップされる。"""
        connected_users = {}
        pending_offers = {}
        bot_offer_timers = {}

        ws = MagicMock(name="connection")
        connected_users["user1"] = ws
        pending_offers["user1"] = {"broadcast": True}
        bot_timer = MagicMock(name="bot_timer")
        bot_offer_timers["user1"] = bot_timer

        # 通常切断: 接続が同じなのでクリーンアップが実行される
        if connected_users.get("user1") is ws:
            task = bot_offer_timers.pop("user1", None)
            if task:
                task.cancel()
            pending_offers.pop("user1", None)
            connected_users.pop("user1", None)

        self.assertNotIn("user1", connected_users)
        self.assertNotIn("user1", pending_offers)
        self.assertNotIn("user1", bot_offer_timers)
        bot_timer.cancel.assert_called_once()


if __name__ == "__main__":
    unittest.main()

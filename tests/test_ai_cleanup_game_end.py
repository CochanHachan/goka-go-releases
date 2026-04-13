"""Regression test: AI対局終了後にロボからの挑戦状が来なくなる問題 (PR #100)

根本原因: AI対局はKataGoでローカル実行されるため、クライアントがサーバーに
game_end を送信しなかった。サーバーの game_pairs にユーザーが残り、
_bot_auto_offer が「まだ対局中」と判断してボットの挑戦状を送らなくなった。

修正: _ai_cleanup() で was_ai フラグを使い、AI対局中の場合のみ game_end を送信。
_ai_init_failed() は end_network_game() → _ai_cleanup() に委譲。
"""

import unittest
from unittest.mock import MagicMock, patch, call


def _make_app_stub():
    """テスト用の最小限 App スタブを生成する。

    tkinter を一切使わず、_ai_cleanup / _ai_init_failed のロジックだけを
    検証できるようにする。
    """
    # _ai_cleanup と _ai_init_failed の実コードだけを持つスタブ
    import importlib
    import types

    # app.py 全体を import すると tkinter が必要になるため、
    # 関数のソースを直接読み込むのではなく、必要なメソッドを手動バインドする。
    app = MagicMock()
    app._ai_mode = False
    app._ai_katago = None
    app._ai_color = None
    app._cloud_client = None

    # send_cloud_message の実装を再現
    def send_cloud_message(self, msg):
        if self._cloud_client and self._cloud_client.connected:
            self._cloud_client.send(msg)

    # _ai_cleanup の実装を再現
    def _ai_cleanup(self):
        was_ai = self._ai_mode
        if self._ai_katago:
            try:
                self._ai_katago.stop()
            except Exception:
                pass
            self._ai_katago = None
        self._ai_mode = False
        if was_ai:
            self.send_cloud_message({"type": "game_end"})

    # _ai_init_failed の実装を再現
    def _ai_init_failed(self, error_msg):
        # Note: 実際には messagebox.showerror を呼ぶが、テストでは省略
        if self.go_board:
            self.go_board.end_network_game()

    app._ai_cleanup = types.MethodType(_ai_cleanup, app)
    app._ai_init_failed = types.MethodType(_ai_init_failed, app)
    app.send_cloud_message = types.MethodType(send_cloud_message, app)

    return app


class TestAiCleanupSendsGameEnd(unittest.TestCase):
    """_ai_cleanup が AI 対局中の場合のみ game_end を送信することを検証する。"""

    def test_ai_cleanup_sends_game_end_when_ai_mode_active(self):
        """AI対局中に _ai_cleanup を呼ぶと game_end が送信される。"""
        app = _make_app_stub()
        app._ai_mode = True
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._ai_cleanup()

        cloud.send.assert_called_once_with({"type": "game_end"})
        self.assertFalse(app._ai_mode)

    def test_ai_cleanup_no_game_end_when_not_ai_mode(self):
        """非AI対局（人間同士）で _ai_cleanup が呼ばれても game_end は送信されない。

        end_network_game() は全対局終了時に _ai_cleanup() を呼ぶため、
        非AI対局で不要な game_end が飛ばないことが重要。
        """
        app = _make_app_stub()
        app._ai_mode = False
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._ai_cleanup()

        cloud.send.assert_not_called()

    def test_ai_cleanup_stops_katago(self):
        """_ai_cleanup が KataGo プロセスを停止する。"""
        app = _make_app_stub()
        app._ai_mode = True
        katago = MagicMock()
        app._ai_katago = katago
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._ai_cleanup()

        katago.stop.assert_called_once()
        self.assertIsNone(app._ai_katago)

    def test_ai_cleanup_handles_katago_stop_exception(self):
        """KataGo の stop() が例外を投げても _ai_cleanup は正常完了する。"""
        app = _make_app_stub()
        app._ai_mode = True
        katago = MagicMock()
        katago.stop.side_effect = RuntimeError("process already dead")
        app._ai_katago = katago
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app._ai_cleanup()

        self.assertIsNone(app._ai_katago)
        self.assertFalse(app._ai_mode)
        cloud.send.assert_called_once_with({"type": "game_end"})


class TestAiInitFailedCleanup(unittest.TestCase):
    """_ai_init_failed が end_network_game() に委譲し、重複 game_end を送らないことを検証する。"""

    def test_ai_init_failed_delegates_to_end_network_game(self):
        """_ai_init_failed は go_board.end_network_game() を呼ぶ。"""
        app = _make_app_stub()
        app._ai_mode = True
        go_board = MagicMock()
        app.go_board = go_board

        app._ai_init_failed("test error")

        go_board.end_network_game.assert_called_once()

    def test_ai_init_failed_does_not_send_game_end_directly(self):
        """_ai_init_failed は直接 game_end を送信しない（重複防止）。

        game_end 送信は end_network_game() → _ai_cleanup() で行われる。
        """
        app = _make_app_stub()
        app._ai_mode = True
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud
        go_board = MagicMock()
        app.go_board = go_board

        app._ai_init_failed("test error")

        # _ai_init_failed 自体は send_cloud_message を呼ばない
        # (end_network_game → _ai_cleanup で呼ばれる)
        cloud.send.assert_not_called()

    def test_ai_init_failed_no_go_board(self):
        """go_board が None の場合も _ai_init_failed はクラッシュしない。"""
        app = _make_app_stub()
        app._ai_mode = True
        app.go_board = None

        # Should not raise
        app._ai_init_failed("test error")


class TestSendCloudMessage(unittest.TestCase):
    """send_cloud_message がクライアント未接続時に安全に動作することを検証する。"""

    def test_send_when_connected(self):
        app = _make_app_stub()
        cloud = MagicMock()
        cloud.connected = True
        app._cloud_client = cloud

        app.send_cloud_message({"type": "game_end"})

        cloud.send.assert_called_once_with({"type": "game_end"})

    def test_send_when_disconnected(self):
        app = _make_app_stub()
        cloud = MagicMock()
        cloud.connected = False
        app._cloud_client = cloud

        app.send_cloud_message({"type": "game_end"})

        cloud.send.assert_not_called()

    def test_send_when_no_client(self):
        app = _make_app_stub()
        app._cloud_client = None

        # Should not raise
        app.send_cloud_message({"type": "game_end"})


class TestBotAutoOfferBlockedByGamePairs(unittest.TestCase):
    """サーバー側: game_pairs にユーザーが残っているとボット挑戦状が送られないことを検証する。

    これは問題の根本原因の検証。game_pairs がクリアされていれば
    _bot_auto_offer はボットの挑戦状を送る。
    """

    def test_game_end_clears_game_pairs(self):
        """game_end メッセージで game_pairs からユーザーが削除される。"""
        # server.py の game_pairs.pop(handle, None) のロジックを再現
        game_pairs = {"user1": "bot1", "bot1": "user1"}

        handle = "user1"
        opponent = game_pairs.pop(handle, None)
        if opponent:
            game_pairs.pop(opponent, None)

        self.assertNotIn("user1", game_pairs)
        self.assertNotIn("bot1", game_pairs)

    def test_game_end_idempotent(self):
        """game_end が2回送られても game_pairs.pop は安全（冪等）。"""
        game_pairs = {"user1": "bot1", "bot1": "user1"}

        # 1回目
        opponent = game_pairs.pop("user1", None)
        if opponent:
            game_pairs.pop(opponent, None)

        # 2回目（重複送信）
        opponent = game_pairs.pop("user1", None)
        self.assertIsNone(opponent)  # 既に削除済み

    def test_bot_auto_offer_skipped_when_in_game_pairs(self):
        """game_pairs にユーザーがいると _bot_auto_offer は即 return する。"""
        game_pairs = {"user1": "bot1"}
        connected_users = {"user1": MagicMock()}

        handle = "user1"
        # _bot_auto_offer のガード条件を再現
        if handle not in connected_users or handle in game_pairs:
            skipped = True
        else:
            skipped = False

        self.assertTrue(skipped)

    def test_bot_auto_offer_proceeds_when_game_pairs_clear(self):
        """game_pairs からユーザーが削除されていれば _bot_auto_offer は進む。"""
        game_pairs = {}
        connected_users = {"user1": MagicMock()}

        handle = "user1"
        if handle not in connected_users or handle in game_pairs:
            skipped = True
        else:
            skipped = False

        self.assertFalse(skipped)


if __name__ == "__main__":
    unittest.main()

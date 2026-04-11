# -*- coding: utf-8 -*-
"""碁華 アプリケーションコントローラ"""
import sys
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import os
import socket
import threading
import json
import time as _time
import random

from igo.glossy_button import GlossyButton
from igo.window_settings import WindowSettings
from igo.lang import L, set_language, get_language
from igo.constants import (
    APP_NAME, APP_VERSION, APP_BUILD, UPDATE_CHECK_URL,
    BOARD_SIZE, CELL_SIZE, MARGIN,
    EMPTY, BLACK, WHITE,
    TIME_LIMIT, NET_TCP_PORT, NET_UDP_PORT,
    HAS_CLOUD, CLOUD_SERVER_URL, API_BASE_URL,
)
from igo.config import (
    _get_app_data_dir, _get_install_dir, _init_config_if_needed,
    get_offer_timeout_ms,
)
from igo.elo import (
    elo_to_rank, elo_to_display_rank, calculate_elo_update,
    rank_to_initial_elo, get_elo_ranges,
)
from igo.theme import (
    THEMES, T, get_current_theme_name,
    _load_theme_from_config, _save_language_to_config,
)
from igo.database import UserDatabase
from igo.timer import ByoyomiTimer
from igo.network import _net_send, _net_recv, GameServer, NetworkGame
from igo.game_logic import GoGame
from igo.katago import KataGoGTP
from igo.sgf import save_sgf, load_sgf
from igo.promotion import PromotionPopup
from igo.login_screen import LoginScreen
from igo.register_screen import RegisterScreen
from igo.match_dialog import MatchDialog
from igo.match_offer_dialog import MatchOfferDialog
from igo.kifu_dialog import KifuDialog
from igo.go_board import GoBoard
import igo.rendering as _rendering_mod


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 初期化完了まで非表示（show_loginで表示）
        self.root.title("\u7881\u83ef")
        self.root.configure(bg=T("root_bg"))

        _db_path = os.path.join(_get_app_data_dir(), "ui_settings.db")
        self._ws = WindowSettings(_db_path, "game")
        self._current_screen = "login"
        init_size = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)

        # Enter key: invoke button or move to next widget (like Tab)
        def _on_enter(event):
            w = event.widget
            if isinstance(w, tk.Button):
                w.invoke()
                return "break"
            elif hasattr(w, '_command') and callable(getattr(w, '_command', None)):
                # GlossyButton (Canvas) - already handled by widget's own <Return> binding
                return "break"
            else:
                w.tk_focusNext().focus_set()
                return "break"
        self.root.bind_all("<Return>", _on_enter)

        # --- Menu bar ---
        self._build_menubar()

        self.db = UserDatabase()
        self.current_user = None

        # Create frames
        self._login_frame = tk.Frame(self.root, bg="white")
        self._game_frame = tk.Frame(self.root, bg=T("root_bg"))
        self.login_screen = LoginScreen(self._login_frame, self)
        self._register_frame = tk.Frame(self.root, bg=T("root_bg"))
        self.register_screen = RegisterScreen(self._register_frame, self)
        self.go_board = None
        self._show_winrate = True  # Default: show winrate
        self._server = None
        self._net_game = None
        self._match_listener_sock = None
        self._match_listening = False
        self._offer_dialog_open = False
        self._current_offer_dialog = None
        self._current_match_dialog = None
        self._current_kifu_dialog = None
        self._last_focused_dialog = None
        self._declined_offers = set()
        self.root.bind("<FocusIn>", lambda e: self._lift_open_dialogs() if e.widget == self.root else None)
        self._current_file_path = None

        # Cloud mode
        self._cloud_mode = False
        self._cloud_client = None
        self._auth_token = None

        # AI mode
        self._ai_mode = False
        self._ai_katago = None
        self._ai_color = None

        self._current_frame = None
        self._update_dialog_shown = False  # 二重ダイアログ防止フラグ
        # 更新確認を先に行い、更新がなければログイン画面を表示
        self._check_for_update_background()

    def _build_menubar(self):
        menubar = tk.Menu(self.root)
        self._menubar = menubar
        # Do not show menu on login/register screens

        # ファイル(F)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=L("menu_new"), accelerator="Ctrl+N", command=self._file_new)
        file_menu.add_command(label=L("menu_open"), accelerator="Ctrl+O", command=self._file_open)
        file_menu.add_separator()
        file_menu.add_command(label=L("menu_save"), accelerator="Ctrl+S", command=self._file_save)
        file_menu.add_command(label=L("menu_saveas"), accelerator="Ctrl+Shift+A", command=self._file_save_as)
        file_menu.add_separator()
        file_menu.add_command(label=L("menu_exit"), accelerator="Alt+F4", command=self._file_exit)
        menubar.add_cascade(label=L("menu_file"), menu=file_menu)

        # 設定(G)
        settings_menu = tk.Menu(menubar, tearoff=0)
        # 再生スピード(S)サブメニュー
        speed_menu = tk.Menu(settings_menu, tearoff=0)
        if not hasattr(self, '_auto_speed_var'):
            self._auto_speed_var = tk.StringVar(value="2")
        for sec in ["1", "2", "3", "5", "10"]:
            speed_menu.add_radiobutton(label=L("menu_speed_sec", sec),
                variable=self._auto_speed_var, value=sec)
        settings_menu.add_cascade(label=L("menu_speed"), menu=speed_menu)
        # 言語(L)サブメニュー
        lang_menu = tk.Menu(settings_menu, tearoff=0)
        if not hasattr(self, '_lang_var'):
            self._lang_var = tk.StringVar(value=get_language())
        else:
            self._lang_var.set(get_language())
        for code, label in [("ja", "日本語"), ("en", "English"), ("zh", "中文"), ("ko", "한국어")]:
            lang_menu.add_radiobutton(label=label, variable=self._lang_var, value=code,
                command=lambda c=code: self._change_language(c))
        settings_menu.add_cascade(label=L("menu_language"), menu=lang_menu)
        # AIロボ サブメニュー
        ai_menu = tk.Menu(settings_menu, tearoff=0)
        if not hasattr(self, '_ai_enabled_var'):
            self._ai_enabled_var = tk.StringVar(value=self._load_ai_setting())
        ai_menu.add_radiobutton(label=L("menu_ai_on"), variable=self._ai_enabled_var,
            value="on", command=self._change_ai_setting)
        ai_menu.add_radiobutton(label=L("menu_ai_off"), variable=self._ai_enabled_var,
            value="off", command=self._change_ai_setting)
        settings_menu.add_cascade(label=L("menu_ai_robot"), menu=ai_menu)
        # 秒読みサブメニュー
        byoyomi_menu = tk.Menu(settings_menu, tearoff=0)
        if not hasattr(self, '_byoyomi_voice_var'):
            self._byoyomi_voice_var = tk.StringVar(value=self._load_byoyomi_voice_setting())
        self._byoyomi_voice_enabled = self._byoyomi_voice_var.get() == "on"
        byoyomi_menu.add_radiobutton(label=L("menu_voice_on"), variable=self._byoyomi_voice_var,
            value="on", command=self._change_byoyomi_voice_setting)
        byoyomi_menu.add_radiobutton(label=L("menu_voice_off"), variable=self._byoyomi_voice_var,
            value="off", command=self._change_byoyomi_voice_setting)
        settings_menu.add_cascade(label=L("menu_byoyomi_voice"), menu=byoyomi_menu)
        menubar.add_cascade(label=L("menu_settings"), menu=settings_menu)

        # 表示(V)
        view_menu = tk.Menu(menubar, tearoff=0)
        # 碁盤選択サブメニュー
        board_select_menu = tk.Menu(view_menu, tearoff=0)
        if not hasattr(self, '_board_type_var'):
            self._board_type_var = tk.StringVar(value="dark")
        board_select_menu.add_radiobutton(label=L("menu_board_dark"),
            variable=self._board_type_var, value="dark",
            command=self._change_board_texture)
        board_select_menu.add_radiobutton(label=L("menu_board_light"),
            variable=self._board_type_var, value="light",
            command=self._change_board_texture)
        view_menu.add_cascade(label=L("menu_board"), menu=board_select_menu)
        menubar.add_cascade(label=L("menu_view"), menu=view_menu)

        # 対局(P)
        game_menu = tk.Menu(menubar, tearoff=0)
        self._game_menu = game_menu
        game_menu.add_command(label=L("menu_game_start"), command=self._menu_match)
        game_menu.add_command(label=L("menu_resign"), command=self._menu_resign, state="disabled")
        game_menu.add_command(label=L("menu_pass"), command=self._menu_pass, state="disabled")
        game_menu.add_command(label=L("menu_score"), command=self._menu_score, state="disabled")
        game_menu.add_command(label=L("menu_kifu"), command=self._menu_kifu)
        game_menu.add_separator()
        game_menu.add_command(label=L("menu_review"), command=self._menu_review_start, state="disabled")
        game_menu.add_command(label=L("menu_review_end"), command=self._menu_review_end, state="disabled")
        menubar.add_cascade(label=L("menu_game"), menu=game_menu)

        # ヘルプ(H)
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=L("menu_help"), menu=help_menu)
        help_menu.add_command(label=L("menu_howto"), command=self._show_howtoplay)
        help_menu.add_command(label=L("menu_features"), command=self._show_features)
        help_menu.add_separator()
        help_menu.add_command(label=L("menu_about"), command=self._show_about)

    def _change_language(self, lang_code):
        """言語を変更してDBとconfigに保存。メニューバーを即時再構築。"""
        _save_language_to_config(lang_code)
        set_language(lang_code)
        if self.current_user:
            self.db.set_user_language(self.current_user["id"], lang_code)
            self._api_update_language(self.current_user.get("handle_name", ""), lang_code)
        # メニューバーを新しい言語で即時再構築
        self._build_menubar()
        self.root.config(menu=self._menubar)
        if self.go_board:
            self._sync_game_menu_state()
        messagebox.showinfo(
            L("menu_language"),
            L("lang_restart")
        )

    def _set_title(self, center_text=""):
        """タイトルバーを設定する。碁華は左、center_textを中央に配置。"""
        prefix = "碁華"
        if not center_text:
            self.root.title(prefix)
            return
        # ウィンドウ幅から全角スペースの数を推定
        try:
            win_w = self.root.winfo_width()
            # タイトルバーフォント: 全角≒12px程度
            total_chars = max(30, win_w // 12)
        except Exception:
            total_chars = 55
        # OS側ボタン(閉じる等)とアイコン分の補正
        # テキストが長い(対局中VS表示)場合は補正を控えめに
        text_len = len(center_text)
        extra = 8 if text_len < 20 else 3
        pad = max(0, (total_chars - text_len) // 2 - len(prefix) + extra)
        title = "{}{}{}".format(prefix, "\u3000" * pad, center_text)
        self.root.title(title)

    def _load_ai_setting(self):
        """WindowSettingsからAIロボ設定を読み込む。デフォルトは'on'。"""
        val = self._ws.load("ai_enabled", "on")
        return val if val in ("on", "off") else "on"

    def _load_byoyomi_voice_setting(self):
        """WindowSettingsから秒読み設定を読み込む。デフォルトは'on'。"""
        val = self._ws.load("byoyomi_voice", "on")
        return val if val in ("on", "off") else "on"

    def _change_byoyomi_voice_setting(self):
        """秒読み設定を変更してDBに保存。"""
        val = self._byoyomi_voice_var.get()
        self._byoyomi_voice_enabled = val == "on"
        try:
            self._ws.save("byoyomi_voice", val)
        except Exception:
            pass

    def _change_ai_setting(self):
        """AIロボ設定を変更してDBに保存し、サーバーに通知。"""
        val = self._ai_enabled_var.get()
        try:
            self._ws.save("ai_enabled", val)
        except Exception:
            pass
        # サーバーに通知
        if self._cloud_client and self._cloud_client.connected:
            self._cloud_client.send({
                "type": "set_ai_preference",
                "ai_enabled": val == "on",
            })

    # ------------------------------------------------------------------
    # ヘルプメニュー ハンドラ
    # ------------------------------------------------------------------
    def _show_howtoplay(self):
        win = tk.Toplevel(self.root)
        win.title("遊び方")
        win.resizable(False, False)
        win.transient(self.root)
        text = (
            "【遊び方】\n\n"
            "1. ログインしてください。\n"
            "2. 「対局」ボタンで対局申込画面を開きます。\n"
            "3. 相手が申込を送ってくると挑戦状が届きます。\n"
            "4. 承諾すると対局が始まります。\n"
            "5. 交互に着手し、終局したら「地合計算」で勝敗を確認します。\n"
            "6. 「投了」で途中で対局を終わらせることができます。\n"
            "7. 「棋譜」で過去の対局を並べ直すことができます。\n"
        )
        tk.Label(win, text=text, justify="left", padx=20, pady=20,
                 font=("Yu Gothic UI", 10)).pack()
        tk.Button(win, text="閉じる", command=win.destroy,
                  width=10).pack(pady=(0, 12))
        win.grab_set()

    def _show_features(self):
        win = tk.Toplevel(self.root)
        win.title("機能")
        win.resizable(False, False)
        win.transient(self.root)
        text = (
            "【主な機能】\n\n"
            "・LAN / クラウド 対戦\n"
            "・ELO レーティングによる棋力管理\n"
            "・昇段 / 昇級時の演出（桜吹雪）\n"
            "・棋譜の保存・再生\n"
            "・秒読み付き対局時計\n"
            "・地合計算（終局判定）\n"
            "・ダークテーマ対応\n"
        )
        tk.Label(win, text=text, justify="left", padx=20, pady=20,
                 font=("Yu Gothic UI", 10)).pack()
        tk.Button(win, text="閉じる", command=win.destroy,
                  width=10).pack(pady=(0, 12))
        win.grab_set()

    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title(L("title_about"))
        win.resizable(False, False)
        win.transient(self.root)
        info = (
            "{}\n\n"
            "Version : {}\n"
            "Build   : {}\n\n"
            "Python + Tkinter 製 ネット対戦型囲碁アプリ"
        ).format(APP_NAME, APP_VERSION, APP_BUILD)
        tk.Label(win, text=info, justify="center", padx=30, pady=20,
                 font=("Yu Gothic UI", 10)).pack()
        tk.Button(win, text=L("btn_close"), command=win.destroy,
                  width=10).pack(pady=(0, 12))
        win.grab_set()

    # ------------------------------------------------------------------
    # 自動更新
    # ------------------------------------------------------------------
    # ── アップデートマーカー管理 ─────────────────────
    _UPDATE_MARKER_NAME = "goka_update_marker.json"
    _MAX_UPDATE_ATTEMPTS = 3
    _ATTEMPT_WINDOW_SEC = 600          # 10分

    @staticmethod
    def _marker_path():
        """アップデート試行マーカーファイルのパス。"""
        from igo.config import _get_app_data_dir
        return os.path.join(_get_app_data_dir(), App._UPDATE_MARKER_NAME)

    @classmethod
    def _read_marker(cls):
        """マーカーを読み取り dict を返す。存在しなければ空 dict。"""
        try:
            with open(cls._marker_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def _write_marker(cls, data):
        try:
            with open(cls._marker_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def _delete_marker(cls):
        try:
            os.remove(cls._marker_path())
        except Exception:
            pass

    @classmethod
    def _should_skip_update(cls, target_version, _log=None):
        """同じバージョンへの更新を短期間に何度も試行している場合 True。"""
        import time as _t
        m = cls._read_marker()
        if m.get("version") != target_version:
            return False
        attempts = m.get("attempts", 0)
        last_ts = m.get("last_ts", 0)
        elapsed = _t.time() - last_ts
        if elapsed > cls._ATTEMPT_WINDOW_SEC:
            # ウィンドウ超過 → リセット
            return False
        if attempts >= cls._MAX_UPDATE_ATTEMPTS:
            if _log:
                _log("SKIP: v{} attempted {} times in {:.0f}s".format(
                    target_version, attempts, elapsed))
            return True
        return False

    @classmethod
    def _record_attempt(cls, target_version):
        """更新試行を記録する。"""
        import time as _t
        m = cls._read_marker()
        if m.get("version") != target_version:
            m = {"version": target_version, "attempts": 0, "last_ts": 0}
        now = _t.time()
        if now - m.get("last_ts", 0) > cls._ATTEMPT_WINDOW_SEC:
            m["attempts"] = 0
        m["attempts"] = m.get("attempts", 0) + 1
        m["last_ts"] = now
        cls._write_marker(m)

    # ── 更新チェック本体 ───────────────────────
    def _check_for_update_background(self):
        """更新確認。アップデート直後ならスキップして即ログイン。
        それ以外はバックグラウンドでHTTPチェックを行う。"""
        _log_path = os.path.join(os.path.expanduser("~"), "goka_update_log.txt")

        def _write_log(msg):
            try:
                with open(_log_path, "a", encoding="utf-8") as _f:
                    _f.write("{}\n".format(msg))
            except Exception:
                pass

        # ── アップデート直後の再起動時は同期的にスキップ（高速化） ──
        _marker = self._read_marker()
        if _marker.get("version") and _marker.get("version") == APP_VERSION:
            _write_log("Just updated to v{}, skipping check".format(APP_VERSION))
            self._delete_marker()
            self.show_login()
            return

        def _fetch_version_json():
            """version.json を取得。SSL検証 → 失敗時はSSL検証なしでリトライ。"""
            import urllib.request, ssl
            # 1回目: SSL検証あり
            try:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=3, context=ctx) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e1:
                _write_log("SSL verified request failed: {}".format(e1))

            # 2回目: SSL検証なし（PyInstallerバンドルでの証明書問題を回避）
            ctx2 = ssl.create_default_context()
            ctx2.check_hostname = False
            ctx2.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=3, context=ctx2) as r:
                return json.loads(r.read().decode("utf-8"))

        def _worker():
            _write_log("=== Update check started ===")
            _write_log("APP_VERSION: {}".format(APP_VERSION))
            _write_log("URL: {}".format(UPDATE_CHECK_URL))
            try:
                data = _fetch_version_json()
                latest = data.get("version", "")
                dl_url = data.get("download_url", "")
                notes = data.get("release_notes", "")
                _write_log("Remote version: {}".format(latest))
                _write_log("Is newer: {}".format(self._is_newer(latest, APP_VERSION)))
                if latest and dl_url and self._is_newer(latest, APP_VERSION):
                    # ── ループ防止チェック ──
                    if self._should_skip_update(latest, _log=_write_log):
                        _write_log("Update skipped (too many attempts)")
                        self.root.after(0, self.show_login)
                        return
                    if self._update_dialog_shown:
                        _write_log("Update dialog already shown, skipping")
                        return  # ダイアログ側でshow_loginを呼ぶ
                    self._update_dialog_shown = True
                    _write_log("Showing update dialog")
                    self.root.after(0, lambda: self._show_update_dialog(
                        latest, dl_url, notes))
                    return  # ダイアログ側で処理する
                else:
                    # 更新不要 → 前回の更新が成功したとみなしマーカー削除
                    self._delete_marker()
                _write_log("No update needed")
                self.root.after(0, self.show_login)
                return
            except Exception as _ue:
                _write_log("Error: {}".format(_ue))
                try:
                    import traceback
                    _write_log(traceback.format_exc())
                except Exception:
                    pass
            # 更新不要 or チェック失敗 → ログイン画面を表示
            self.root.after(0, self.show_login)
        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def _is_newer(remote, current):
        """バージョン文字列を比較して remote > current なら True。"""
        def _v(s):
            try:
                return tuple(int(x) for x in s.strip().split("."))
            except Exception:
                return (0,)
        return _v(remote) > _v(current)

    def _show_update_dialog(self, latest, dl_url, notes):
        """更新ダイアログを表示する。「後でする」→ログイン画面へ。"""
        # ── カラーパレット ──────────────────────
        _BG        = "#000000"
        _FG        = "#E0E0E0"
        _ACCENT    = "#D4A645"
        _BTN_PRI   = "#8B2020"
        _BTN_PRI_H = "#A52A2A"
        _BTN_SEC   = "#1A2A5C"
        _BTN_SEC_H = "#253A7A"
        _BTN_FG    = "#FFFFFF"
        _LINE_CLR  = "#D4A645"
        _FONT      = "Yu Gothic UI"

        def _rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
            pts = [
                x1+r, y1,  x2-r, y1,
                x2, y1,  x2, y1+r,
                x2, y2-r,  x2, y2,
                x2-r, y2,  x1+r, y2,
                x1, y2,  x1, y2-r,
                x1, y1+r,  x1, y1,
            ]
            return canvas.create_polygon(pts, smooth=True, **kw)

        class _HoverButton(tk.Canvas):
            def __init__(self, parent, text, btn_width, btn_height, radius,
                         base_color, hover_color, fg, font, command, bg=None):
                canvas_bg = bg if bg else _BG
                super().__init__(parent, width=btn_width, height=btn_height,
                                 bg=canvas_bg, highlightthickness=0, bd=0)
                self._cmd = command
                self._base = base_color
                self._hover = hover_color
                self._btn_w = btn_width
                self._btn_h = btn_height
                self._radius = radius
                self._text = text
                self._fg = fg
                self._font = font
                self._draw(self._base)
                self.bind("<Enter>", lambda e: self._draw(self._hover))
                self.bind("<Leave>", lambda e: self._draw(self._base))
                self.bind("<ButtonRelease-1>", lambda e: self._cmd())

            def _draw(self, color):
                self.delete("all")
                _rounded_rect(self, 2, 2, self._btn_w - 2, self._btn_h - 2,
                               self._radius, fill=color, outline="")
                self.create_text(self._btn_w // 2, self._btn_h // 2,
                                 text=self._text, fill=self._fg,
                                 font=self._font)

        win = tk.Toplevel()
        win.title("アップデート")
        win.configure(bg=_BG)
        win.withdraw()

        outer = tk.Frame(win, bg=_BG, padx=30, pady=24)
        outer.pack(fill="both", expand=True)

        _gap = 8
        tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(0, _gap))

        tk.Label(outer, text="アプリが進化しました",
                 font=(_FONT, 16, "bold"),
                 fg=_ACCENT, bg=_BG).pack(anchor="center")
        tk.Label(outer, text="アップデートしてください",
                 font=(_FONT, 16, "bold"),
                 fg=_ACCENT, bg=_BG).pack(anchor="center", pady=(0, _gap))

        tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(0, 20))

        tk.Label(outer, text="旧バージョン : {}".format(APP_VERSION),
                 font=(_FONT, 12), fg=_FG, bg=_BG,
                 anchor="center").pack(fill="x", pady=(0, 4))
        tk.Label(outer, text="新バージョン : {}".format(latest),
                 font=(_FONT, 12), fg=_FG, bg=_BG,
                 anchor="center").pack(fill="x", pady=(0, 24))

        _btn_w = 150
        _btn_h = 44
        btn_frame = tk.Frame(outer, bg=_BG)
        btn_frame.pack(pady=(0, 4))
        btn_font = (_FONT, 13)

        _HoverButton(btn_frame, text="アップデート",
                     btn_width=_btn_w, btn_height=_btn_h, radius=14,
                     base_color=_BTN_PRI, hover_color=_BTN_PRI_H,
                     fg=_BTN_FG, font=btn_font, bg=_BG,
                     command=lambda: self._do_update(win, dl_url, latest)
                     ).pack(side="left", padx=(0, 12))

        def _skip_update():
            win.destroy()
            self.show_login()

        win.protocol("WM_DELETE_WINDOW", _skip_update)

        _HoverButton(btn_frame, text="後でする",
                     btn_width=_btn_w, btn_height=_btn_h, radius=14,
                     base_color=_BTN_SEC, hover_color=_BTN_SEC_H,
                     fg=_BTN_FG, font=btn_font, bg=_BG,
                     command=_skip_update
                     ).pack(side="left")

        def _finalize():
            win.update_idletasks()
            rw = win.winfo_reqwidth()
            rh = win.winfo_reqheight()
            sx = win.winfo_screenwidth()
            sy = win.winfo_screenheight()
            x = (sx - rw) // 2
            y = (sy - rh) // 2
            win.geometry("+{}+{}".format(x, y))
            win.resizable(False, False)
            win.deiconify()

        win.after(100, _finalize)

    def _do_update(self, dialog, dl_url, latest):
        """ZIPをダウンロード→解凍→アプリ終了→バッチで上書き→再起動。"""
        import urllib.request, zipfile, tempfile, ssl
        from igo.update_progress import show_update_progress

        _log_path = os.path.join(os.path.expanduser("~"),
                                 "goka_update_log.txt")

        def _log(msg):
            try:
                with open(_log_path, "a", encoding="utf-8") as f:
                    f.write("{}\n".format(msg))
            except Exception:
                pass

        _log("=== _do_update called ===")
        # ── 試行を記録（ループ防止） ──
        self._record_attempt(latest)
        dialog.destroy()
        prog = show_update_progress(self.root)

        # PyInstaller exe のパスから正しいアプリディレクトリを取得
        app_exe = sys.executable
        app_dir = os.path.dirname(app_exe)
        _log("sys.executable: {}".format(app_exe))
        _log("app_dir: {}".format(app_dir))

        def _worker():
            try:
                import time as _t
                tmp_dir = tempfile.mkdtemp()
                zip_path = os.path.join(tmp_dir, "update.zip")
                _log("Downloading to: {}".format(zip_path))
                # SSL検証あり → 失敗時はSSL検証なしでリトライ
                _dl_ok = False
                try:
                    ctx = ssl.create_default_context()
                    req = urllib.request.Request(dl_url, headers={"User-Agent": "GokaGo-Updater"})
                    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                        with open(zip_path, "wb") as zf_out:
                            import shutil as _shutil
                            _shutil.copyfileobj(resp, zf_out)
                    _dl_ok = True
                except Exception as _e1:
                    _log("SSL download failed: {}".format(_e1))
                if not _dl_ok:
                    _log("Retrying without SSL verification")
                    ctx2 = ssl.create_default_context()
                    ctx2.check_hostname = False
                    ctx2.verify_mode = ssl.CERT_NONE
                    req2 = urllib.request.Request(dl_url, headers={"User-Agent": "GokaGo-Updater"})
                    with urllib.request.urlopen(req2, timeout=60, context=ctx2) as resp:
                        with open(zip_path, "wb") as zf_out:
                            import shutil as _shutil
                            _shutil.copyfileobj(resp, zf_out)
                zip_size = os.path.getsize(zip_path)
                _log("Downloaded: {} bytes".format(zip_size))

                # 「解凍中」を表示して2.5秒待つ
                self.root.after(0, lambda: prog["set_status"]("解凍中"))
                _t.sleep(2.5)

                extract_dir = os.path.join(tmp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    _log("ZIP entries: {}".format(len(zf.namelist())))
                    zf.extractall(extract_dir)
                _log("Extracted OK")

                # ── ZIP内のトップレベルサブフォルダ自動検出 ──
                entries = [e for e in os.listdir(extract_dir)
                           if os.path.isdir(os.path.join(extract_dir, e))]
                if len(entries) == 1:
                    candidate = os.path.join(extract_dir, entries[0])
                    if any(f.endswith(".exe") for f in os.listdir(candidate)
                           if os.path.isfile(os.path.join(candidate, f))):
                        extract_dir = candidate
                        _log("Using inner dir: {}".format(extract_dir))
                    else:
                        _log("Inner dir has no exe, keeping: {}".format(
                            extract_dir))
                else:
                    _log("Top-level entries: {}".format(entries))

                # コピー元に exe が存在するか事前検証
                src_exe = os.path.join(extract_dir, os.path.basename(app_exe))
                if not os.path.isfile(src_exe):
                    raise RuntimeError(
                        "コピー元に {} が見つかりません: {}".format(
                            os.path.basename(app_exe), extract_dir))
                _log("Source exe OK: {}".format(src_exe))

                # 「インストール中」を表示して2.5秒待つ
                self.root.after(0, lambda: prog["set_status"]("インストール中"))
                _t.sleep(2.5)

                # 「アップデートは正常に終了しました。」を表示して1.5秒待つ
                if "show_complete" in prog:
                    self.root.after(0, lambda: prog["show_complete"]())
                else:
                    self.root.after(0, lambda: prog["set_status"]("アップデート完了"))
                _t.sleep(1.5)

                bat_path = os.path.join(tmp_dir, "goka_update.bat")
                _log_file = os.path.join(
                    os.path.expanduser("~"), "goka_update_batch.log")
                with open(bat_path, "w", encoding="utf-8") as bf:
                    bf.write("@echo off\n")
                    bf.write("chcp 65001 >nul\n")
                    bf.write('set "LOGFILE={}"\n'.format(_log_file))
                    bf.write('echo [%date% %time%] === Update batch start === >> "%LOGFILE%"\n')
                    bf.write('echo SRC={} >> "%LOGFILE%"\n'.format(extract_dir))
                    bf.write('echo DST={} >> "%LOGFILE%"\n'.format(app_dir))
                    bf.write('echo EXE={} >> "%LOGFILE%"\n'.format(app_exe))
                    # --- プロセス終了待機 (最大30秒) ---
                    bf.write("set WAIT_COUNT=0\n")
                    bf.write(":WAIT\n")
                    bf.write('tasklist /FI "IMAGENAME eq goka_go.exe"'
                             ' 2>NUL | find /I "goka_go.exe" >NUL\n')
                    bf.write("if %ERRORLEVEL% NEQ 0 goto COPY\n")
                    bf.write("set /a WAIT_COUNT+=1\n")
                    bf.write("if %WAIT_COUNT% GEQ 30 (\n")
                    bf.write('  echo [%time%] Timeout waiting for process >> "%LOGFILE%"\n')
                    bf.write("  goto COPY\n")
                    bf.write(")\n")
                    bf.write("timeout /t 1 /nobreak >nul\n")
                    bf.write("goto WAIT\n")
                    # --- robocopy (第1手段) ---
                    bf.write(":COPY\n")
                    bf.write('echo [%time%] Trying robocopy >> "%LOGFILE%"\n')
                    bf.write('robocopy "{}" "{}" /E /IS /IT /R:3 /W:2 /NFL /NDL /NJH /NJS >> "%LOGFILE%" 2>&1\n'.format(
                        extract_dir, app_dir))
                    bf.write("if %ERRORLEVEL% LSS 8 (\n")
                    bf.write('  echo [%time%] robocopy OK (exit=%ERRORLEVEL%) >> "%LOGFILE%"\n')
                    bf.write("  goto VERIFY\n")
                    bf.write(")\n")
                    # --- xcopy フォールバック (第2手段) ---
                    bf.write('echo [%time%] robocopy failed (%ERRORLEVEL%), trying xcopy >> "%LOGFILE%"\n')
                    bf.write('xcopy /s /y /q "{}\\*" "{}\\" >> "%LOGFILE%" 2>&1\n'.format(
                        extract_dir, app_dir))
                    bf.write("if %ERRORLEVEL% EQU 0 (\n")
                    bf.write('  echo [%time%] xcopy OK >> "%LOGFILE%"\n')
                    bf.write("  goto VERIFY\n")
                    bf.write(")\n")
                    # --- コピー失敗時: UAC昇格でリトライ ---
                    bf.write('echo [%time%] xcopy failed, trying UAC elevation >> "%LOGFILE%"\n')
                    bf.write('if "%~1"=="__ELEVATED__" (\n')
                    bf.write('  echo [%time%] Already elevated, giving up >> "%LOGFILE%"\n')
                    bf.write("  goto FAIL\n")
                    bf.write(")\n")
                    bf.write('powershell -Command "Start-Process cmd -ArgumentList '
                             "'/c \"%~f0\" __ELEVATED__'"
                             ' -Verb RunAs" 2>> "%LOGFILE%"\n')
                    bf.write("goto END\n")
                    # --- 検証: exe が更新されたか確認 ---
                    bf.write(":VERIFY\n")
                    bf.write('if exist "{}" (\n'.format(app_exe))
                    bf.write('  echo [%time%] Verified: exe exists >> "%LOGFILE%"\n')
                    bf.write('  start "" "{}"\n'.format(app_exe))
                    bf.write('  echo [%time%] App restarted >> "%LOGFILE%"\n')
                    bf.write(") else (\n")
                    bf.write('  echo [%time%] VERIFY FAILED: exe not found >> "%LOGFILE%"\n')
                    bf.write(")\n")
                    bf.write("goto END\n")
                    bf.write(":FAIL\n")
                    bf.write('echo [%time%] Update FAILED >> "%LOGFILE%"\n')
                    bf.write(":END\n")
                    bf.write('echo [%time%] === Update batch end === >> "%LOGFILE%"\n')

                _log("Batch: {}".format(bat_path))
                self.root.after(0, lambda: self._launch_update(
                    prog, bat_path, _log))
            except Exception as e:
                import traceback
                _log("WORKER ERROR: {}".format(e))
                _log(traceback.format_exc())
                def _show_err(err=e):
                    prog["close"]()
                    self.root.deiconify()
                    messagebox.showerror("更新エラー", str(err))
                    self.show_login()
                self.root.after(0, _show_err)
        threading.Thread(target=_worker, daemon=True).start()

    def _launch_update(self, prog, bat_path, _log=None):
        """バッチを起動してアプリを終了する。"""
        import subprocess
        try:
            if _log:
                _log("_launch_update called")
            prog["close"]()
            if _log:
                _log("prog closed")
            # バッチを非表示で実行（黒い画面を出さない）
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            subprocess.Popen(
                ['cmd', '/c', bat_path],
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if _log:
                _log("batch launched, destroying root")
            self.root.destroy()
        except Exception as e:
            if _log:
                import traceback
                _log("LAUNCH ERROR: {}".format(e))
                _log(traceback.format_exc())


    def _user_screen_name(self, screen_name):
        """ログイン中ならユーザー別のscreen_nameを返す。"""
        if screen_name == "game" and self.current_user:
            return "game_{}".format(self.current_user["handle_name"])
        return screen_name

    def _save_geometry(self, screen_name=None):
        if screen_name is None:
            screen_name = self._current_screen
        ws = WindowSettings(self._ws._db_path, self._user_screen_name(screen_name))
        ws.save_window(self.root)

    def _apply_geometry(self, screen_name):
        init_size = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)
        defaults = {
            "login": "500x400",
            "register": "{}x{}".format(*RegisterScreen.DEFAULT_SIZE),
            "game": "{}x{}".format(init_size, init_size + 120),
        }
        user_key = self._user_screen_name(screen_name)
        ws = WindowSettings(self._ws._db_path, user_key)
        ws.restore_window(self.root, default_geometry=defaults.get(screen_name, "500x400"))
        self._current_screen = screen_name

    def _switch_frame(self, frame):
        if self._current_frame:
            self._current_frame.pack_forget()
        self._current_frame = frame
        frame.pack(expand=True, fill="both")

    def show_login(self):
        self.root.withdraw()
        self.root.title("\u7881\u83ef")
        self.root.minsize(400, 400)
        self._save_geometry()
        self.root.config(menu="")
        self.login_screen.reset()
        self._switch_frame(self._login_frame)
        self._apply_geometry("login")
        self.root.configure(bg="white")
        login_w, login_h = 460, 420
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        lx = (screen_w - login_w) // 2
        ly = (screen_h - login_h) // 2
        self.root.geometry("{}x{}+{}+{}".format(login_w, login_h, lx, ly))
        self.root.resizable(False, False)  # deiconify前に設定（後から変更するとちらつく）
        self.root.update_idletasks()
        self.root.deiconify()

    def show_register(self):
        self._save_geometry()
        self.root.config(menu="")
        for w in self._register_frame.winfo_children():
            w.destroy()
        self.register_screen = RegisterScreen(self._register_frame, self)
        self._switch_frame(self._register_frame)
        self._apply_geometry("register")

    def _api_update_language(self, handle, lang_code):
        """Update language on the server (non-blocking)."""
        if not self._auth_token:
            return
        import urllib.request as _urlreq
        import json as _json, threading as _thr
        def _do():
            try:
                _data = _json.dumps({
                    "handle_name": handle,
                    "language": lang_code,
                    "token": self._auth_token,
                }).encode("utf-8")
                _req = _urlreq.Request(
                    API_BASE_URL + "/api/user/language",
                    data=_data,
                    headers={"Content-Type": "application/json"},
                    method="PUT"
                )
                _urlreq.urlopen(_req, timeout=5).close()
            except Exception as _e:
                print("[Language update failed]", _e)
        _thr.Thread(target=_do, daemon=True).start()

    def on_login_success(self, user):
        self.current_user = user
        # ログイン画面で選んだ言語を優先する（サーバーDBのデフォルト"ja"で上書きしない）
        login_lang = get_language()  # ログイン画面で既に設定済み
        set_language(login_lang)
        _save_language_to_config(login_lang)
        user["language"] = login_lang
        # サーバーDBに言語を保存（次回ログイン時に復元用）
        self._api_update_language(user.get("handle_name", ""), login_lang)
        # メニューバーを現在の言語で再構築
        self._build_menubar()
        self.root.resizable(True, True)
        self.root.config(menu=self._menubar)
        # Restore board texture preference
        handle = user["handle_name"]
        saved_tex = self._ws.load("board_texture_{}".format(handle))
        if saved_tex in ("dark", "light"):
            _rendering_mod._board_texture_type = saved_tex
            _rendering_mod._board_texture_original = None  # Force reload
            self._board_type_var.set(saved_tex)
        else:
            self._board_type_var.set("dark")
        # Destroy old game frame contents
        for w in self._game_frame.winfo_children():
            w.destroy()
        self.go_board = GoBoard(self._game_frame, self)
        if hasattr(self.go_board, "score_btn"):
            self.go_board.score_btn.config(state="disabled")
        # Show placeholder names in light gray until match starts
        self.go_board.set_players(
            black_name="\u30b8\u30e7\u30f3\u30ec\u30ce\u30f3",
            black_rank="",
            white_name="\u30af\u30e9\u30d7\u30c8\u30f3",
            white_rank=""
        )
        self.go_board.black_name_label.config(fg="#b0b0b0")
        self.go_board.black_rank_label.config(fg="#b0b0b0")
        self.go_board.white_name_label.config(fg="#b0b0b0")
        self.go_board.white_rank_label.config(fg="#b0b0b0")
        # Show logged-in user in title bar
        rank = elo_to_display_rank(user["elo_rating"]) if user["elo_rating"] else ""
        self._set_title("{}（{}）".format(user["handle_name"], rank))
        self._save_geometry()
        self._switch_frame(self._game_frame)
        self._apply_geometry("game")
        self._start_match_listener()
        self._update_online_status(True)
        # Sync game menu state
        self._sync_game_menu_state()
        # Connect to cloud server after UI is ready (non-blocking)
        self.root.after(500, self._connect_cloud)
        # Keyboard shortcuts for file menu
        self.root.bind_all("<Control-n>", lambda e: self._file_new())
        self.root.bind_all("<Control-o>", lambda e: self._file_open())
        self.root.bind_all("<Control-s>", lambda e: self._file_save())
        self.root.bind_all("<Control-Shift-A>", lambda e: self._file_save_as())
        self.root.after(5000, self._online_heartbeat)

    # --- Network match methods ---

    def start_hosting(self, main_time, byo_time, byo_periods, komi, on_connect_cb):
        self._stop_match_listener()
        user = self.current_user
        name = user["handle_name"] if user else "?"
        rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
        self._hosting_elo = user["elo_rating"] if user else 0
        self._hosting_cb = on_connect_cb
        self._match_settings = (main_time, byo_time, byo_periods, komi)

        if self._cloud_mode and self._cloud_client:
            # Cloud mode: broadcast offer via WebSocket
            self._cloud_main_time = main_time
            self._cloud_byo_time = byo_time
            self._cloud_byo_periods = byo_periods
            self._cloud_komi = komi
            self._cloud_client.send({
                "type": "match_offer_broadcast",
                "rank": rank,
                "elo": self._hosting_elo,
                "main_time": main_time,
                "byo_time": byo_time,
                "byo_periods": byo_periods,
                "komi": komi,
            })
        else:
            # LAN mode: UDP broadcast + TCP
            self._server = GameServer(name, rank, main_time, byo_time, byo_periods,
                                       self._on_server_connect, komi=komi,
                                       elo=self._hosting_elo)
            self._server.start()

    def stop_hosting(self):
        if self._cloud_mode and self._cloud_client:
            self._cloud_client.send({"type": "match_cancel"})
        if self._server:
            self._server.stop()
            self._server = None

    def _on_server_connect(self, conn, addr, msg):
        """Called from server thread when opponent accepts."""
        # Broadcast match_taken so other clients close offer dialogs
        try:
            _tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _tsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            _tmsg = json.dumps({"type": "match_taken",
                "host_name": self.current_user["handle_name"] if self.current_user else "",
                "accepter_name": msg.get("name", "")
            }).encode("utf-8")
            _tsock.sendto(_tmsg, ("<broadcast>", NET_UDP_PORT + 1))
            _tsock.close()
        except Exception:
            pass
        import random
        host_color = random.choice([BLACK, WHITE])
        accepter_color = "white" if host_color == BLACK else "black"
        _net_send(conn, {
            "type": "game_start",
            "your_color": accepter_color,
            "main_time": self._match_settings[0],
            "byo_time": self._match_settings[1],
            "byo_periods": self._match_settings[2],
            "komi": self._match_settings[3],
        })
        self._server.stop()
        self._server = None
        self._net_game = NetworkGame(conn, self._on_net_message, self._on_net_disconnect)
        self._net_game.start()
        opponent_name = msg.get("name", "?")
        opponent_rank = msg.get("rank", "?")
        opponent_elo = msg.get("elo", rank_to_initial_elo(opponent_rank))
        mt, bt, bp, km = self._match_settings
        self.root.after(0, lambda: self._start_network_game(
            host_color, opponent_name, opponent_rank, mt, bt, bp, km, opponent_elo))
        if self._hosting_cb:
            self._hosting_cb(msg)

    def join_match(self, ip, offer, on_done_cb):
        def _connect():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                port = offer.get("port", NET_TCP_PORT)
                sock.connect((ip, port))
                user = self.current_user
                name = user["handle_name"] if user else "?"
                rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
                elo = user["elo_rating"] if user else 0
                _net_send(sock, {
                    "type": "match_accept",
                    "name": name,
                    "rank": rank,
                    "elo": elo,
                })
                msg = _net_recv(sock)
                if msg and msg.get("type") == "game_start":
                    sock.settimeout(None)
                    self._net_game = NetworkGame(sock, self._on_net_message, self._on_net_disconnect)
                    self._net_game.start()
                    my_color = WHITE if msg.get("your_color") == "white" else BLACK
                    mt = msg.get("main_time", 600)
                    bt = msg.get("byo_time", 30)
                    bp = msg.get("byo_periods", 5)
                    km = msg.get("komi", 7.5)
                    opponent_name = offer.get("name", "?")
                    opponent_rank = offer.get("rank", "?")
                    opponent_elo = offer.get("elo", rank_to_initial_elo(opponent_rank))
                    self.root.after(0, lambda: self._start_network_game(
                        my_color, opponent_name, opponent_rank, mt, bt, bp, km, opponent_elo))
                    if on_done_cb:
                        on_done_cb()
                else:
                    sock.close()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "\u30a8\u30e9\u30fc", "\u63a5\u7d9a\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f: {}".format(e)))
        threading.Thread(target=_connect, daemon=True).start()

    def _start_network_game(self, my_color, opponent_name, opponent_rank, main_time, byo_time, byo_periods, komi=7.5, opponent_elo=0):
        if not self.go_board:
            return
        user = self.current_user
        my_name = user["handle_name"] if user else "?"
        my_rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
        # Restore name label colors from placeholder gray
        self.go_board.black_name_label.config(fg=T("text_primary"))
        self.go_board.black_rank_label.config(fg=T("rank_fg"))
        self.go_board.white_name_label.config(fg=T("text_primary"))
        self.go_board.white_rank_label.config(fg=T("rank_fg"))
        if my_color == BLACK:
            self.go_board.set_players(
                black_name=my_name, black_rank=my_rank,
                white_name=opponent_name, white_rank=opponent_rank)
        else:
            self.go_board.set_players(
                black_name=opponent_name, black_rank=opponent_rank,
                white_name=my_name, white_rank=my_rank)
        self.go_board.setup_network_game(my_color, main_time, byo_time, byo_periods, komi)
        self.go_board.opponent_elo = opponent_elo
        # Update title bar: 黒名(棋力) VS 白名(棋力) コミX目半
        b_name = self.go_board.black_name
        b_rank = self.go_board.black_rank
        w_name = self.go_board.white_name
        w_rank = self.go_board.white_rank
        if komi == int(komi):
            komi_str = "\u30b3\u30df{}\u76ee".format(int(komi))
        else:
            komi_str = "\u30b3\u30df{}\u76ee\u534a".format(int(komi))
        self._set_title("{}({})  VS  {}({})  {}".format(
            b_name, b_rank, w_name, w_rank, komi_str))

    def _update_elo_after_game(self, winner_color):
        """Update Elo rating for the local user after game ends."""
        user = self.current_user
        if not user or not self.go_board:
            return
        my_elo = user["elo_rating"]
        if not my_elo:
            return
        opp_elo = getattr(self.go_board, 'opponent_elo', 0)
        if not opp_elo:
            opp_elo = getattr(self.go_board, '_last_opponent_elo', 0)
        if not opp_elo:
            return
        my_color = self.go_board.my_color
        if my_color is None:
            my_color = getattr(self.go_board, '_last_my_color', None)
        if my_color is None:
            return
        if winner_color is None:  # draw
            my_score = 0.5
        elif my_color == winner_color:
            my_score = 1.0
        else:
            my_score = 0.0
        old_rank = elo_to_rank(my_elo)
        new_elo = calculate_elo_update(my_elo, opp_elo, my_score)
        new_rank = elo_to_rank(new_elo)
        new_display = elo_to_display_rank(new_elo)
        # Update ELO on server (non-blocking)
        self._api_update_elo(user["handle_name"], new_elo)
        # Update in-memory
        if self.current_user:
            self.current_user["elo_rating"] = new_elo
        # Update panel display
        if self.go_board:
            if my_color == BLACK:
                self.go_board.set_players(black_rank=new_display)
                self.go_board.black_rank_label.config(fg=T("rank_fg"))
            else:
                self.go_board.set_players(white_rank=new_display)
                self.go_board.white_rank_label.config(fg=T("rank_fg"))
            user_now = self.current_user
            if user_now:
                self._set_title("{}（{}）".format(
                    user_now["handle_name"], new_display))
        # Promotion dialog
        if new_rank != old_rank:
            rank_order = [r for r, _, _ in get_elo_ranges()]
            old_idx = rank_order.index(old_rank) if old_rank in rank_order else len(rank_order)
            new_idx = rank_order.index(new_rank) if new_rank in rank_order else len(rank_order)
            if new_idx < old_idx:  # lower index = higher rank
                try:
                    pname = user["handle_name"]
                except Exception:
                    pname = ""
                self._promotion_popup = PromotionPopup(self.root, rank=new_rank, player_name=pname)
                self._promotion_popup.show()

    def _save_game_record(self, result_str):
        """Save game record to database after game ends."""
        if not self.go_board:
            return
        gb = self.go_board
        history = gb._replay_history if gb._reviewing else gb.game.move_history
        if not history:
            return
        try:
            self.db.save_game_record(
                black_name=gb.black_name,
                black_rank=gb.black_rank,
                white_name=gb.white_name,
                white_rank=gb.white_rank,
                result=result_str,
                komi=gb._komi,
                move_history=history
            )
        except Exception as e:
            print("棋譜保存エラー:", e)

    def send_net_message(self, msg):
        if getattr(self, '_ai_mode', False):
            self._ai_handle_user_move(msg)
            return
        if self._cloud_mode and self._cloud_client:
            self._cloud_client.send(msg)
        elif self._net_game:
            self._net_game.send(msg)

    def _on_net_message(self, msg):
        """Called from network thread."""
        # Set resign flag immediately in network thread to prevent race
        if msg.get("type") == "resign" and self.go_board:
            self.go_board._resign_disconnect = True
        self.root.after(0, lambda: self._handle_net_message(msg))

    def _handle_net_message(self, msg):
        if not self.go_board:
            return
        msg_type = msg.get("type")
        if msg_type == "move":
            x = msg.get("x", 0)
            y = msg.get("y", 0)
            self.go_board.handle_network_move(x, y)
        elif msg_type == "pass":
            self.go_board.handle_network_pass()
        elif msg_type == "resign":
            opponent_color = WHITE if self.go_board.my_color == BLACK else BLACK
            self.go_board.handle_network_resign(opponent_color)
        elif msg_type == "timeout":
            player_str = msg.get("player", "")
            loser_color = BLACK if player_str == "black" else WHITE
            self.go_board.handle_network_timeout(loser_color)

    def _on_net_disconnect(self):
        """Called from network thread when connection drops."""
        self._net_game = None
        self.root.after(0, self._handle_disconnect)

    def _handle_disconnect(self):
        # Skip disconnect message if it was triggered by resignation or double pass
        if self.go_board and getattr(self.go_board, '_resign_disconnect', False):
            self.go_board._resign_disconnect = False
            return
        if self.go_board and getattr(self.go_board, '_pass_disconnect', False):
            self.go_board._pass_disconnect = False
            return
        if self.go_board and getattr(self.go_board, '_timeout_disconnect', False):
            self.go_board._timeout_disconnect = False
            return
        if self.go_board and self.go_board.net_mode:
            self.go_board.end_network_game()
            messagebox.showinfo("\u5207\u65ad",
                "\u76f8\u624b\u3068\u306e\u63a5\u7d9a\u304c\u5207\u308c\u307e\u3057\u305f")


    def _update_online_status(self, online=True):
        """Broadcast online status via UDP for admin screen."""
        if not self.current_user:
            return
        handle = self.current_user["handle_name"]
        # Include opponent info if in a game
        opponent = ""
        if self.go_board and self.go_board.net_mode:
            my_color = self.go_board.my_color
            if my_color == BLACK:
                opponent = self.go_board.white_name
            elif my_color == WHITE:
                opponent = self.go_board.black_name
        msg = json.dumps({"type": "heartbeat", "handle": handle,
                          "online": online, "opponent": opponent}).encode("utf-8")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(msg, ("<broadcast>", 19940))
            sock.close()
        except Exception:
            pass

    def _online_heartbeat(self):
        if self.current_user and self._current_frame == self._game_frame:
            self._update_online_status(True)
        # Always reschedule so the heartbeat chain never breaks
        self.root.after(5000, self._online_heartbeat)

    def _start_match_listener(self):
        if self._match_listening:
            return
        self._match_listening = True
        self._offer_dialog_open = False
        self._start_taken_cleanup_listener()
        # Note: _declined_offers is NOT cleared here so declined offers stay filtered
        try:
            self._match_listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._match_listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._match_listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            self._match_listener_sock.settimeout(1.0)
            self._match_listener_sock.bind(("", NET_UDP_PORT))
            threading.Thread(target=self._match_listen_loop, daemon=True).start()
        except Exception:
            self._match_listening = False

    def _stop_match_listener(self):
        self._match_listening = False
        try:
            if self._match_listener_sock:
                self._match_listener_sock.close()
        except Exception:
            pass
        self._match_listener_sock = None

    def _resume_match_listener(self):
        self._offer_dialog_open = False
        self._start_match_listener()

    def _start_taken_cleanup_listener(self):
        """Listen for match_taken to remove from _declined_offers."""
        if hasattr(self, "_taken_cleanup_running") and self._taken_cleanup_running:
            return
        self._taken_cleanup_running = True
        def _listen():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.settimeout(1.0)
                s.bind(("", NET_UDP_PORT + 1))
                while self._taken_cleanup_running:
                    try:
                        data, addr = s.recvfrom(4096)
                        msg = json.loads(data.decode("utf-8"))
                        if msg.get("type") == "match_taken":
                            host_name = msg.get("host_name", "")
                            self._declined_offers.discard(host_name)
                    except socket.timeout:
                        continue
                    except Exception:
                        if self._taken_cleanup_running:
                            continue
                        break
                s.close()
            except Exception:
                pass
        threading.Thread(target=_listen, daemon=True).start()

    def _match_listen_loop(self):
        while self._match_listening:
            try:
                data, addr = self._match_listener_sock.recvfrom(4096)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "match_offer":
                    my_name = ""
                    if self.current_user:
                        my_name = self.current_user["handle_name"]
                    sender = msg.get("name", "")
                    if sender != my_name and sender not in self._declined_offers:
                        if self._offer_dialog_open and self._current_offer_dialog:
                            # Add to existing MatchOfferDialog
                            msg["_addr"] = addr[0]
                            msg["_time"] = _time.time()
                            self.root.after(0, lambda m=msg: self._current_offer_dialog.add_cloud_offer(m))
                        elif not self._offer_dialog_open:
                            self._offer_dialog_open = True
                            self.root.after(0, lambda m=msg, a=addr[0]: self._show_offer(m, a))
            except socket.timeout:
                continue
            except Exception:
                if self._match_listening:
                    continue
                return

    def _show_offer(self, offer, addr):
        if not self.go_board or self.go_board.net_mode:
            self._offer_dialog_open = False
            return
        self._stop_match_listener()
        self._current_offer_dialog = MatchOfferDialog(self.root, self, offer, addr)


    # --- Cloud mode methods ---

    def _api_update_elo(self, handle, new_elo):
        """Update ELO rating on the GCP server (non-blocking)."""
        if not self._auth_token:
            return
        import urllib.request as _urlreq, urllib.parse as _urlparse
        import json as _json, threading as _thr
        def _do():
            try:
                _data = _json.dumps({
                    "elo": float(new_elo),
                    "token": self._auth_token,
                }).encode("utf-8")
                _path = "/api/user/{}/elo".format(_urlparse.quote(handle, safe=""))
                _req = _urlreq.Request(
                    API_BASE_URL + _path,
                    data=_data,
                    headers={"Content-Type": "application/json"},
                    method="PUT"
                )
                _urlreq.urlopen(_req, timeout=5).close()
            except Exception as _e:
                print("[ELO update failed]", _e)
        _thr.Thread(target=_do, daemon=True).start()

    def _connect_cloud(self):
        """Connect to the cloud WebSocket server."""
        try:
            from igo.igo_cloud_client import CloudClient
        except ImportError:
            return
        if self._cloud_client and self._cloud_client.connected:
            return
        if not self.current_user:
            return
        handle = self.current_user["handle_name"]
        rank = elo_to_display_rank(self.current_user["elo_rating"])
        elo = self.current_user["elo_rating"]

        def on_cloud_msg(msg):
            # Route to UI thread
            self.root.after(0, lambda: self._handle_cloud_message(msg))

        def on_cloud_disconnect():
            self.root.after(0, self._on_cloud_disconnect)

        self._cloud_client = CloudClient(CLOUD_SERVER_URL, on_cloud_msg, on_cloud_disconnect)
        self._cloud_client.connect(handle, rank, elo, token=self._auth_token or "")
        self._cloud_mode = True
        # AIロボ設定をサーバーに通知
        ai_val = getattr(self, '_ai_enabled_var', None)
        ai_on = True if ai_val is None else (ai_val.get() == "on")
        self.root.after(1000, lambda: self._cloud_client.send({
            "type": "set_ai_preference", "ai_enabled": ai_on,
        }) if self._cloud_client and self._cloud_client.connected else None)

    def _disconnect_cloud(self):
        """Disconnect from the cloud server."""
        if self._cloud_client:
            self._cloud_client.disconnect()
            self._cloud_client = None
        self._cloud_mode = False

    def _on_cloud_disconnect(self):
        """Handle cloud connection drop."""
        if self.go_board and self.go_board.net_mode:
            self.go_board.end_network_game()
            messagebox.showinfo("切断", "サーバーとの接続が切れました")

    def _handle_cloud_message(self, msg):
        """Handle messages from the cloud server."""
        msg_type = msg.get("type")

        if msg_type == "online_list":
            # Update admin screen if open
            pass  # TODO: update online list display

        elif msg_type == "match_offer":
            # Someone is offering a match
            sender = msg.get("from", "")
            if not self.go_board or self.go_board.net_mode:
                return
            if sender in self._declined_offers:
                return
            offer = {
                "type": "match_offer",
                "name": sender,
                "rank": msg.get("rank", ""),
                "elo": msg.get("elo", 0),
                "main_time": msg.get("main_time", 600),
                "byo_time": msg.get("byo_time", 30),
                "byo_periods": msg.get("byo_periods", 5),
                "komi": msg.get("komi", 7.5),
            }
            # Case 1: MatchDialog is open (user is hosting/browsing) -> add to its list
            if self._current_match_dialog:
                self._current_match_dialog.add_cloud_offer(offer)
            # Case 2: MatchOfferDialog is already open -> add to it
            elif self._offer_dialog_open and self._current_offer_dialog:
                self._current_offer_dialog.add_cloud_offer(offer)
            # Case 3: No dialog open -> create new MatchOfferDialog
            elif not self._offer_dialog_open:
                self._offer_dialog_open = True
                self._show_cloud_offer(offer)

        elif msg_type == "match_accepted":
            # Our offer was accepted
            opponent = msg.get("from", "")
            opponent_rank = msg.get("rank", "")
            opponent_elo = msg.get("elo", 0)
            my_color = BLACK if msg.get("your_color") == "black" else WHITE
            is_bot = msg.get("is_bot", False)
            bot_visits = msg.get("bot_visits", 50)
            if is_bot:
                self._start_ai_game(my_color, opponent, opponent_rank, opponent_elo, bot_visits)
            else:
                self._start_cloud_game(my_color, opponent, opponent_rank, opponent_elo)

        elif msg_type == "match_started":
            # We accepted someone's offer, game starts
            opponent = msg.get("opponent", "")
            opponent_rank = msg.get("rank", "")
            opponent_elo = msg.get("elo", 0)
            my_color = BLACK if msg.get("your_color") == "black" else WHITE
            is_bot = msg.get("is_bot", False)
            bot_visits = msg.get("bot_visits", 50)
            if is_bot:
                self._start_ai_game(my_color, opponent, opponent_rank, opponent_elo, bot_visits)
            else:
                self._start_cloud_game(my_color, opponent, opponent_rank, opponent_elo)

        elif msg_type == "match_declined":
            # Our offer was declined
            pass  # could show notification

        elif msg_type == "match_cancelled":
            # An offer was cancelled - remove from dialogs too
            sender = msg.get("from", "")
            self._declined_offers.discard(sender)
            if sender:
                if self._current_offer_dialog:
                    if sender in self._current_offer_dialog._offers:
                        del self._current_offer_dialog._offers[sender]
                        self._current_offer_dialog._refresh_list()
                if self._current_match_dialog:
                    if sender in self._current_match_dialog._offers:
                        del self._current_match_dialog._offers[sender]
                        self._current_match_dialog._refresh_list()

        elif msg_type == "match_taken":
            # A match offer was taken by someone else - remove both offerer and accepter
            for key in ("offerer", "accepter"):
                name = msg.get(key, "")
                if not name:
                    continue
                if self._current_offer_dialog:
                    if name in self._current_offer_dialog._offers:
                        del self._current_offer_dialog._offers[name]
                        self._current_offer_dialog._refresh_list()
                if self._current_match_dialog:
                    if name in self._current_match_dialog._offers:
                        del self._current_match_dialog._offers[name]
                        self._current_match_dialog._refresh_list()

        elif msg_type in ("move", "pass", "resign", "timeout", "score_result"):
            # Game message from opponent - route to go_board
            if self.go_board:
                self._handle_net_message(msg)

        elif msg_type == "opponent_disconnected":
            # Opponent disconnected during game
            if self.go_board and self.go_board.net_mode:
                self.go_board.end_network_game()
                messagebox.showinfo("切断", "相手との接続が切れました")

    def _show_cloud_offer(self, offer):
        """Show match offer from cloud."""
        if not self.go_board or self.go_board.net_mode:
            self._offer_dialog_open = False
            return
        try:
            self._current_offer_dialog = MatchOfferDialog(self.root, self, offer, None, cloud_mode=True)
        except Exception:
            self._offer_dialog_open = False

    def _start_cloud_game(self, my_color, opponent_name, opponent_rank, opponent_elo):
        """Start a game via cloud."""
        if not self.go_board:
            return
        # 対局成立時にダイアログの_hostingを先にリセットしてmatch_cancel送信を防止
        if self._current_match_dialog:
            self._current_match_dialog._hosting = False
        # Close any open match dialogs
        if self._current_match_dialog:
            try:
                self._current_match_dialog._on_close()
            except Exception:
                pass
            self._current_match_dialog = None
        if self._current_offer_dialog:
            try:
                self._current_offer_dialog._close()
            except Exception:
                pass
            self._current_offer_dialog = None
            self._offer_dialog_open = False
        # Use current match settings or defaults
        main_time = getattr(self, '_cloud_main_time', 600)
        byo_time = getattr(self, '_cloud_byo_time', 30)
        byo_periods = getattr(self, '_cloud_byo_periods', 5)
        komi = getattr(self, '_cloud_komi', 7.5)

        self._start_network_game(my_color, opponent_name, opponent_rank,
                                  main_time, byo_time, byo_periods, komi, opponent_elo)

    def _start_ai_game(self, my_color, opponent_name, opponent_rank, opponent_elo, bot_visits):
        """Start a game against AI bot using KataGo GTP."""
        if not self.go_board:
            return
        # AI対局時もダイアログの_hostingをリセットしてmatch_cancel送信を防止
        if self._current_match_dialog:
            self._current_match_dialog._hosting = False
        # Close any open match dialogs
        if self._current_match_dialog:
            try:
                self._current_match_dialog._on_close()
            except Exception:
                pass
            self._current_match_dialog = None
        if self._current_offer_dialog:
            try:
                self._current_offer_dialog._close()
            except Exception:
                pass
            self._current_offer_dialog = None
            self._offer_dialog_open = False

        self._ai_mode = True
        self._ai_katago = None
        self._ai_color = WHITE if my_color == BLACK else BLACK  # AI's color

        # Use current match settings
        main_time = getattr(self, '_cloud_main_time', 600)
        byo_time = getattr(self, '_cloud_byo_time', 30)
        byo_periods = getattr(self, '_cloud_byo_periods', 5)
        komi = getattr(self, '_cloud_komi', 7.5)

        self._start_network_game(my_color, opponent_name, opponent_rank,
                                  main_time, byo_time, byo_periods, komi, opponent_elo)

        # Start KataGo in background thread (model loading takes time)
        def _init_katago():
            try:
                katago = KataGoGTP(visits=bot_visits)
                katago.start()
                katago.set_boardsize(19)
                katago.set_komi(komi)
                katago.clear_board()
                self._ai_katago = katago
                # If AI is black (plays first), make AI move
                if self._ai_color == BLACK:
                    self.root.after(100, self._ai_make_move)
            except Exception as e:
                self.root.after(0, lambda: self._ai_init_failed(str(e)))

        threading.Thread(target=_init_katago, daemon=True).start()

    def _ai_init_failed(self, error_msg):
        """Handle KataGo initialization failure."""
        from tkinter import messagebox as _mb
        _mb.showerror("AI エラー", "KataGoの起動に失敗しました:\n{}".format(error_msg))
        self._ai_mode = False
        if self.go_board:
            self.go_board.end_network_game()

    def _ai_make_move(self):
        """Ask KataGo to generate a move in a background thread."""
        if not self._ai_mode or not self._ai_katago or not self.go_board:
            return
        if self.go_board.game.game_over:
            return

        ai_color_str = "B" if self._ai_color == BLACK else "W"

        def _run():
            try:
                result = self._ai_katago.genmove(ai_color_str)
                if result:
                    self.root.after(0, lambda: self._ai_apply_move(result))
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _ai_apply_move(self, vertex):
        """Apply AI's move to the board (called on main thread)."""
        if not self.go_board or self.go_board.game.game_over:
            return
        if not self._ai_mode:
            return

        vertex_lower = vertex.lower().strip()

        if vertex_lower == "resign":
            opponent_color = self._ai_color
            self.go_board.handle_network_resign(opponent_color)
            self._ai_cleanup()
            return

        if vertex_lower == "pass":
            self.go_board.handle_network_pass()
            # handle_network_pass() already handles game_over case
            # (calls end_network_game + _calculate_score), so just cleanup AI
            if self.go_board.game.game_over:
                self._ai_cleanup()
            return

        # Parse vertex to coords
        action, col, row = KataGoGTP.gtp_vertex_to_coords(vertex)
        if action == "move" and col >= 0 and row >= 0:
            self.go_board.handle_network_move(col, row)

    def _ai_handle_user_move(self, msg):
        """Handle a user move/pass/resign during AI game."""
        if not self._ai_mode:
            return
        # KataGoがまだ初期化中なら少し待ってリトライ
        if not self._ai_katago:
            self.root.after(500, lambda: self._ai_handle_user_move(msg))
            return
        msg_type = msg.get("type")

        if msg_type == "move":
            x = msg.get("x", 0)
            y = msg.get("y", 0)
            # Tell KataGo about user's move
            user_color = "B" if self._ai_color == WHITE else "W"
            gtp_vertex = KataGoGTP.coords_to_gtp_vertex(x, y)
            self._ai_katago.play(user_color, gtp_vertex)
            # Ask AI for response
            self.root.after(100, self._ai_make_move)

        elif msg_type == "pass":
            user_color = "B" if self._ai_color == WHITE else "W"
            self._ai_katago.play(user_color, "pass")
            # Check if game already ended (double pass handled in _pass_turn)
            if self.go_board and not self.go_board.game.game_over:
                self.root.after(100, self._ai_make_move)
            else:
                self._ai_cleanup()

        elif msg_type == "resign":
            self._ai_cleanup()

    def _ai_cleanup(self):
        """Stop KataGo and reset AI mode."""
        if self._ai_katago:
            try:
                self._ai_katago.stop()
            except Exception:
                pass
            self._ai_katago = None
        self._ai_mode = False

    def send_cloud_message(self, msg):
        """Send a game message via cloud."""
        if self._cloud_client and self._cloud_client.connected:
            self._cloud_client.send(msg)

    def _send_status(self, status: str):
        """サーバーにステータスを送信する。"""
        if self._cloud_client and self._cloud_client.connected:
            self._cloud_client.send({"type": "set_status", "status": status})

    # --- Game menu methods ---

    def _menu_match(self):
        if self.go_board:
            self.go_board._open_match_dialog()

    def _menu_resign(self):
        if self.go_board:
            self.go_board._resign()

    def _menu_pass(self):
        if self.go_board:
            self.go_board._pass_turn()

    def _menu_score(self):
        if self.go_board:
            self.go_board._calculate_score()

    def _menu_kifu(self):
        if self.go_board:
            self.go_board._open_kifu_dialog()

    def _menu_review_start(self):
        """Start review mode: allow free play from current position."""
        if not self.go_board:
            return
        gb = self.go_board
        if gb.net_mode:
            return
        # Save current game state for restoring later
        import copy
        gb._review_saved_game_history = list(gb.game.move_history)
        gb._review_was_reviewing = gb._reviewing
        gb._review_saved_index = gb._replay_index if gb._reviewing else len(gb.game.move_history)
        gb._review_was_auto = gb._auto_playing if gb._reviewing else False
        gb._review_saved_replay_history = list(gb._replay_history) if gb._reviewing else list(gb.game.move_history)
        # Stop auto-play if running
        if gb._auto_playing:
            gb._auto_stop()
        # Enable board clicking for free play
        gb._review_mode = True
        # Build a fresh game from current position
        g = GoGame()
        history = gb._review_saved_replay_history
        target_index = gb._review_saved_index
        for i in range(target_index):
            if i < len(history):
                action, player, x, y = history[i]
                if action == "move":
                    g.current_player = player
                    g.place_stone(x, y)
                elif action == "pass":
                    g.current_player = player
                    g.pass_turn()
        gb.game = g
        # Set up nav bar for review navigation
        gb._reviewing = True
        gb._replay_history = list(g.move_history)
        gb._replay_index = len(gb._replay_history)
        gb._nav_inner.pack(anchor="center")
        gb._position_nav_bar()
        # Disable auto button during review
        gb._auto_btn.config(state="disabled")
        gb._full_redraw()
        # Update menu
        self._sync_game_menu_state()

    def _menu_review_end(self):
        """End review mode: restore to saved position."""
        if not self.go_board:
            return
        gb = self.go_board
        if not getattr(gb, '_review_mode', False):
            return
        gb._review_mode = False
        # Restore replay history and rebuild game to saved position
        gb._replay_history = list(gb._review_saved_replay_history)
        gb._replay_index = gb._review_saved_index
        # Rebuild game from saved history
        g = GoGame()
        for i in range(gb._review_saved_index):
            if i < len(gb._replay_history):
                action, player, x, y = gb._replay_history[i]
                if action == "move":
                    g.current_player = player
                    g.place_stone(x, y)
                elif action == "pass":
                    g.current_player = player
                    g.pass_turn()
        gb.game = g
        gb._full_redraw()
        gb.black_cap_label.config(text="\u2191 {}".format(g.captured_black))
        gb.white_cap_label.config(text="\u2191 {}".format(g.captured_white))
        if gb._review_was_reviewing:
            # Was in nav bar review mode - restore nav bar
            gb._reviewing = True
            gb._nav_inner.pack(anchor="center")
            gb._position_nav_bar()
            gb._auto_btn.config(state="normal")
            # Resume auto-play if it was running
            if getattr(gb, '_review_was_auto', False):
                gb._auto_play_start()
        else:
            # Was on idle board - hide nav bar
            gb._reviewing = False
            gb._nav_inner.pack_forget()
            gb.nav_frame.place_forget()
        # Update menu
        self._sync_game_menu_state()

    def _sync_game_menu_state(self):
        """Sync game menu item states with toolbar button states."""
        if not self.go_board:
            return
        gb = self.go_board
        in_game = gb.net_mode and not gb.game.game_over
        in_review = getattr(gb, '_review_mode', False)
        # 投了・パス (only on my turn during network game)
        if in_game and gb.my_color is not None:
            is_my_turn = gb.game.current_player == gb.my_color
            resign_state = "normal" if is_my_turn else "disabled"
        else:
            resign_state = "normal" if in_game else "disabled"
        pass_state = resign_state
        self._game_menu.entryconfig(L("menu_resign"), state=resign_state)
        self._game_menu.entryconfig(L("menu_pass"), state=pass_state)
        # 地合計算
        score_state = str(gb.score_btn.cget("state")) if hasattr(gb, "score_btn") else "disabled"
        self._game_menu.entryconfig(L("menu_score"), state=score_state)
        # 検討: active when not in game, not in offer dialog, not already reviewing
        if not in_game and not in_review and not self._offer_dialog_open:
            self._game_menu.entryconfig(L("menu_review"), state="normal")
        else:
            self._game_menu.entryconfig(L("menu_review"), state="disabled")
        # 検討終了: active only when in review mode
        if in_review:
            self._game_menu.entryconfig(L("menu_review_end"), state="normal")
        else:
            self._game_menu.entryconfig(L("menu_review_end"), state="disabled")
        # 初期化ボタン: disabled during active game
        if hasattr(gb, 'reset_btn'):
            gb.reset_btn.config(state="disabled" if in_game else "normal")

    # --- File menu methods ---

    def _change_board_texture(self):
        """Change board texture between dark and light."""
        new_type = self._board_type_var.get()
        if new_type == _rendering_mod._board_texture_type:
            return
        _rendering_mod._board_texture_type = new_type
        _rendering_mod._board_texture_original = None  # Force reload
        # Save preference
        handle = self.current_user["handle_name"] if self.current_user else "default"
        self._ws.save("board_texture_{}".format(handle), new_type)
        # Reset texture cache and redraw
        if self.go_board:
            self.go_board._board_tex = None
            self.go_board._board_tex_size = (0, 0)
            self.go_board._full_redraw()

    def _cancel_hosting_if_active(self):
        """ホスト中なら match_taken をブロードキャストして申請を取り消す。"""
        dlg = getattr(self, '_current_match_dialog', None)
        if dlg and hasattr(dlg, '_hosting') and dlg._hosting:
            try:
                _tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                _tsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                _tmsg = json.dumps({"type": "match_taken",
                    "host_name": self.current_user["handle_name"] if self.current_user else ""
                }).encode("utf-8")
                _tsock.sendto(_tmsg, ("<broadcast>", NET_UDP_PORT + 1))
                _tsock.close()
            except Exception:
                pass
            try:
                self.stop_hosting()
            except Exception:
                pass

    def _lift_open_dialogs(self):
        """Bring all open dialogs above the main board window.
        The last focused dialog comes on top."""
        entries = []
        for dlg in [self._current_match_dialog, self._current_offer_dialog]:
            if dlg and hasattr(dlg, 'win'):
                entries.append((dlg, dlg.win))
        if self._current_kifu_dialog and hasattr(self._current_kifu_dialog, 'dlg'):
            entries.append((self._current_kifu_dialog, self._current_kifu_dialog.dlg))
        last = self._last_focused_dialog
        # Lift non-last-focused first, last-focused last (ends up on top)
        for dlg, win in entries:
            if dlg is not last:
                try:
                    win.lift()
                except Exception:
                    pass
        for dlg, win in entries:
            if dlg is last:
                try:
                    win.lift()
                except Exception:
                    pass

    def _reset_to_initial(self):
        """Reset everything to initial logged-in state."""
        if not self.go_board:
            return
        gb = self.go_board
        # Stop auto-play if running
        if getattr(gb, '_auto_playing', False):
            gb._auto_stop()
        # Stop review mode
        if getattr(gb, '_review_mode', False):
            gb._review_mode = False
        # Hide nav bar
        gb.hide_nav_bar()
        # Close network game if active
        if self._net_game:
            self._net_game.stop()
            self._net_game = None
        gb.end_network_game()
        # Close any open dialogs (match offer, match dialog)
        if getattr(self, '_current_offer_dialog', None):
            try:
                dlg = self._current_offer_dialog
                dlg._cleanup()
                dlg.win.destroy()
            except Exception:
                pass
            self._offer_dialog_open = False
            self._current_offer_dialog = None
        if getattr(self, '_current_match_dialog', None):
            try:
                dlg = self._current_match_dialog
                # Cancel hosting (broadcasts match_taken so other clients remove this user)
                if hasattr(dlg, '_hosting') and dlg._hosting:
                    try:
                        dlg._cancel_hosting()
                    except Exception:
                        pass
                # Stop listening
                if hasattr(dlg, '_listening'):
                    dlg._listening = False
                dlg.win.destroy()
            except Exception:
                pass
            self._current_match_dialog = None
        # Also stop any hosting on the App level
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        # Clear declined offers
        self._declined_offers = set()
        # Reset board
        gb.game = GoGame()
        gb._timer_running = False
        gb.timer_black = None
        gb.timer_white = None
        gb._full_redraw()
        gb.black_time_label.config(text="00:00", font=("Consolas", 18, "bold"))
        gb.white_time_label.config(text="00:00", font=("Consolas", 18, "bold"))
        gb.black_cap_label.config(text="\u2191 0")
        gb.white_cap_label.config(text="\u2191 0")
        gb.black_winrate_label.config(text="")
        gb.white_winrate_label.config(text="")
        # Hide overlay if visible
        gb._hide_overlay()
        gb.canvas.bind("<Button-1>", gb.on_click)
        # Reset placeholder names and clear rank
        gb.set_players(
            black_name="\u30b8\u30e7\u30f3\u30ec\u30ce\u30f3",
            black_rank="",
            white_name="\u30af\u30e9\u30d7\u30c8\u30f3",
            white_rank=""
        )
        gb.black_name_label.config(fg="#b0b0b0", text="\u30b8\u30e7\u30f3\u30ec\u30ce\u30f3")
        gb.black_rank_label.config(fg="#b0b0b0", text="")
        gb.white_name_label.config(fg="#b0b0b0", text="\u30af\u30e9\u30d7\u30c8\u30f3")
        gb.white_rank_label.config(fg="#b0b0b0", text="")
        # Reset buttons
        if hasattr(gb, "score_btn"):
            gb.score_btn.config(state="disabled")
        if hasattr(gb, "kifu_btn"):
            gb.kifu_btn.config(state="normal")
        if hasattr(gb, "pass_btn"):
            gb.pass_btn.config(state="disabled")
        if hasattr(gb, "resign_btn"):
            gb.resign_btn.config(state="disabled")
        # Reset title bar
        user = self.current_user
        if user:
            rank = elo_to_display_rank(user["elo_rating"]) if user["elo_rating"] else ""
            self._set_title("{}（{}）".format(user["handle_name"], rank))
        # Restart match listener
        self._start_match_listener()
        # Tell server to reset state and restart bot timers
        if self._cloud_mode and self._cloud_client and self._cloud_client.connected:
            self._cloud_client.send({"type": "reset_state"})
        # Sync menu state
        self._sync_game_menu_state()
        self._current_file_path = None

    def _file_new(self):
        """Reset board for new game (same as 初期化)."""
        self._reset_to_initial()

    def _file_open(self):
        """Open SGF file."""
        from tkinter import filedialog as _fd
        path = _fd.askopenfilename(
            filetypes=[("SGF files", "*.sgf"), ("All files", "*.*")],
            title="\u68cb\u8b5c\u3092\u958b\u304f")
        if not path:
            return
        try:
            moves, metadata = load_sgf(path)
        except Exception as e:
            from tkinter import messagebox as _mb
            _mb.showerror("\u30a8\u30e9\u30fc", "SGF\u30d5\u30a1\u30a4\u30eb\u306e\u8aad\u307f\u8fbc\u307f\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002\n{}".format(e))
            return
        if self.go_board:
            # Stop match listener so offer dialogs don't appear
            self._stop_match_listener()
            if self._net_game:
                self._net_game.stop()
                self._net_game = None
            self.go_board.load_sgf_to_board(moves, metadata)
        self._current_file_path = path

    def _file_save(self):
        """Save to current file, or ask for filename."""
        if self._current_file_path:
            self._do_save(self._current_file_path)
        else:
            self._file_save_as()

    def _file_save_as(self):
        """Save with file dialog."""
        from tkinter import filedialog as _fd
        path = _fd.asksaveasfilename(
            defaultextension=".sgf",
            filetypes=[("SGF files", "*.sgf"), ("All files", "*.*")],
            title="\u68cb\u8b5c\u3092\u4fdd\u5b58")
        if not path:
            return
        self._do_save(path)
        self._current_file_path = path

    def _do_save(self, path):
        """Actually save the SGF file."""
        if not self.go_board:
            return
        gb = self.go_board
        history = gb._replay_history if gb._reviewing else gb.game.move_history
        # Determine result
        result = ""
        if gb.game.winner == BLACK:
            result = "B+R"
        elif gb.game.winner == WHITE:
            result = "W+R"
        try:
            save_sgf(path, history,
                     black_name=gb.black_name, white_name=gb.white_name,
                     black_rank=gb.black_rank, white_rank=gb.white_rank,
                     komi=gb._komi, result=result)
        except Exception as e:
            from tkinter import messagebox as _mb
            _mb.showerror("\u30a8\u30e9\u30fc", "\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002\n{}".format(e))

    def _file_exit(self):
        """Exit the application."""
        self._on_app_close()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self.root.mainloop()

    def _on_app_close(self):
        self._cancel_hosting_if_active()
        self._save_geometry()
        self._update_online_status(False)
        self._stop_match_listener()
        self._taken_cleanup_running = False
        if self._net_game:
            self._net_game.stop()
        if self._server:
            self._server.stop()
        self.root.destroy()


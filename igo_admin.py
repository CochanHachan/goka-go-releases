# -*- coding: utf-8 -*-
import base64
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from tksheet import Sheet
import os
import json
import socket
import threading
import time as _time
import traceback
import urllib.request
import urllib.error
import urllib.parse
import re
import sys
import unicodedata
import tempfile
import subprocess
from pathlib import Path
from window_settings import WindowSettings
from cryptography.fernet import Fernet
from igo_game import T, get_current_theme_name, THEMES, elo_to_display_rank
from igo.register_screen import RegisterScreen
from glossy_pill_button import GlossyButton
from igo.constants import APP_VERSION


def _admin_app_base_dir():
    """igo_config.json / ui_settings.db を置くディレクトリ。PyInstaller では exe と同じフォルダ。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

# Notebook 行の高さ（pack だとタブが最小高さに潰れやすいため grid + 固定高さで確保）
_ADMIN_TAB_AREA_HEIGHT = 252
_ADMIN_UPDATE_CHECK_URL = "https://goka-igo.com/version.json"
_ADMIN_UPDATE_TITLE = "管理者ツール更新"
_ADMIN_UPDATE_APP_VERSION = APP_VERSION

# ---------------------------------------------------------------------------
# パスワード暗号化キー（管理者PCのみに保存）
# ---------------------------------------------------------------------------
_ADMIN_KEY_FILE = Path.home() / ".goka_admin_encryption_key"

def _get_admin_fernet() -> Fernet:
    """管理者用暗号化キーを読み込む。なければ新規生成。"""
    if _ADMIN_KEY_FILE.exists():
        key = _ADMIN_KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        _ADMIN_KEY_FILE.write_bytes(key)
    return Fernet(key)

_admin_fernet = _get_admin_fernet()

def admin_encrypt(plain_text: str) -> str:
    """平文パスワードをFernet暗号化。"""
    return "ENC:" + _admin_fernet.encrypt(plain_text.encode("utf-8")).decode("ascii")

def admin_decrypt(encrypted: str) -> str:
    """暗号化パスワードを復号。B64:は仮保管、ENC:はFernet暗号文。"""
    if not encrypted:
        return ""
    if encrypted.startswith("B64:"):
        try:
            return base64.b64decode(encrypted[4:]).decode("utf-8")
        except Exception:
            return "（復号不可）"
    if encrypted.startswith("ENC:"):
        try:
            return _admin_fernet.decrypt(encrypted[4:].encode("ascii")).decode("utf-8")
        except Exception:
            return "（復号不可）"
    return encrypted

# ---------------------------------------------------------------------------
# 環境切替フラグ（constants_env.py から読み込み）
# ステージングビルド時は constants_env.py の _ENV を "staging" に変更する
# ---------------------------------------------------------------------------
from igo.constants_env import _ENV

_ADMIN_SERVER_CONFIG = {
    "production": {
        "api_base_url": "http://34.85.118.112:8000",
        "title":        "碁華 - 管理者画面",
    },
    "staging": {
        "api_base_url": "http://136.110.101.14:8000",
        "title":        "碁華 - 管理者画面 [STAGING]",
    },
}

def _resolve_admin_env() -> str:
    """管理者画面の接続先環境を決定する。

    優先順位:
      1) CLI引数 --env=production|staging
      2) 環境変数 GOKA_ENV_OVERRIDE
      3) constants_env.py の _ENV
    """
    env = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--env="):
            env = arg.split("=", 1)[1].strip().lower()
            break
    if not env:
        # 実行ファイル横の設定（前回選択）を読む
        cfg_path = os.path.join(_admin_app_base_dir(), "igo_config.json")
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    env = str(saved.get("admin_env", "")).strip().lower()
        except Exception:
            env = ""
    if not env:
        env = os.environ.get("GOKA_ENV_OVERRIDE", "").strip().lower()
    if not env:
        env = _ENV
    if env not in _ADMIN_SERVER_CONFIG:
        raise RuntimeError(
            "Unknown admin env={!r}. Must be 'production' or 'staging'.".format(env)
        )
    return env

_ACTIVE_ENV = _resolve_admin_env()
_admin_cfg = _ADMIN_SERVER_CONFIG[_ACTIVE_ENV]
API_BASE_URL = _admin_cfg["api_base_url"]
_ADMIN_TITLE = _admin_cfg["title"]


def _normalize_num_text(text: str) -> str:
    """全角数字やカンマ混じりを正規化して数値文字列に寄せる。"""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = s.strip().replace(",", "").replace(" ", "")
    import re as _re
    s = _re.sub(r'[^\d.\-]+$', '', s)
    return s


def _to_int(value, default: int = 0, *, min_value=None, max_value=None) -> int:
    """UI入力の数値変換を一元化する。変換不能時は default。"""
    try:
        n = int(_normalize_num_text(value))
    except Exception:
        n = default
    if min_value is not None and n < min_value:
        n = min_value
    if max_value is not None and n > max_value:
        n = max_value
    return n


def _to_float(value, default: float = 0.0, *, min_value=None, max_value=None) -> float:
    """UI入力の小数変換を一元化する。変換不能時は default。"""
    try:
        n = float(_normalize_num_text(value))
    except Exception:
        n = default
    if min_value is not None and n < min_value:
        n = min_value
    if max_value is not None and n > max_value:
        n = max_value
    return n


def _num_sort_key(val):
    """ソート時の数値比較（カンマ/全角を許容）。"""
    if val is None:
        val = ""
    s = _normalize_num_text(val)
    try:
        return (0, float(s))
    except Exception:
        return (1, str(val).lower())


def _convert_time_string_vba_style(s_input: str) -> str:
    """H.M.S(または H,M,S) を「○時間○分○秒」に変換する。"""
    s = unicodedata.normalize("NFKC", str(s_input or "")).strip()
    if not s:
        return ""
    # 区切りは . / , のどちらでも受ける
    parts = re.split(r"[.,]", s)
    if len(parts) != 3:
        return "入力形式エラー"
    try:
        h = int(_normalize_num_text(parts[0]))
        m = int(_normalize_num_text(parts[1]))
        sec = int(_normalize_num_text(parts[2]))
    except Exception:
        return "入力形式エラー"
    if h < 0 or m < 0 or sec < 0:
        return "入力形式エラー"
    result = ""
    if h > 0:
        result += "{}時間".format(h)
    if m > 0:
        result += "{}分".format(m)
    if sec > 0:
        result += "{}秒".format(sec)
    if not result:
        result = "0秒"
    return result


def _canonical_hms_text(s_input: str) -> str:
    """H.M.S 形式を正規化した文字列で返す。形式不正時は空文字。"""
    s = unicodedata.normalize("NFKC", str(s_input or "")).strip()
    if not s:
        return ""
    parts = re.split(r"[.,]", s)
    if len(parts) != 3:
        return ""
    try:
        h = int(_normalize_num_text(parts[0]))
        m = int(_normalize_num_text(parts[1]))
        sec = int(_normalize_num_text(parts[2]))
    except Exception:
        return ""
    if h < 0 or m < 0 or sec < 0:
        return ""
    return "{}.{}.{}".format(h, m, sec)


def _duration_seconds_from_text(text: str, default_seconds: int = 0) -> int:
    """H.M.S / 日本語時間文字列 / 素の数値 を秒に変換する。"""
    raw = str(text or "").strip()
    if not raw:
        return default_seconds

    # 1) H.M.S
    hms = _canonical_hms_text(raw)
    if hms:
        h, m, s = [int(x) for x in hms.split(".")]
        return h * 3600 + m * 60 + s

    # 2) 「10時間5分30秒」系
    m = re.fullmatch(r"\s*(?:(\d+)\s*時間)?\s*(?:(\d+)\s*分)?\s*(?:(\d+)\s*秒)?\s*", raw)
    if m:
        hh = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        ss = int(m.group(3) or 0)
        if hh or mm or ss or "0秒" in raw:
            return hh * 3600 + mm * 60 + ss

    # 3) 素の秒数/分数
    try:
        return int(_normalize_num_text(raw))
    except Exception:
        return default_seconds


def _seconds_to_japanese_hms_text(total_seconds: int) -> str:
    """秒数を「○時間○分○秒」へ変換する。"""
    sec = max(0, int(total_seconds))
    h = sec // 3600
    rem = sec % 3600
    m = rem // 60
    s = rem % 60
    return _convert_time_string_vba_style("{}.{}.{}".format(h, m, s))


def _height_ratio_from_text(
    value,
    default_ratio: float,
    *,
    min_percent: int = 10,
    max_percent: int = 100,
) -> float:
    """高さ入力（90 / 90% / 0.9）を比率(0.0-1.0)に正規化する。"""
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        ratio = default_ratio
    else:
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        try:
            num = float(_normalize_num_text(raw))
            if num > 1.0:
                ratio = num / 100.0
            else:
                ratio = num
        except Exception:
            ratio = default_ratio
    min_ratio = min_percent / 100.0
    max_ratio = max_percent / 100.0
    if ratio < min_ratio:
        ratio = min_ratio
    if ratio > max_ratio:
        ratio = max_ratio
    return ratio


def _height_ratio_to_percent_text(ratio: float) -> str:
    """比率(0.0-1.0)を表示用パーセント文字列へ変換する。"""
    pct = int(round(max(0.0, min(1.0, float(ratio))) * 100))
    return "{}%".format(pct)


class AdminApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(_ADMIN_TITLE)
        self.root.configure(bg=T("root_bg"))
        self.root.geometry("1000x900")
        self.root.minsize(800, 780)

        # Enter key: invoke button or move to next widget
        def _on_enter(event):
            w = event.widget
            if isinstance(w, tk.Button):
                w.invoke()
                return "break"
            else:
                w.tk_focusNext().focus_set()
                return "break"
        self.root.bind_all("<Return>", _on_enter)

        _base = _admin_app_base_dir()
        self._config_path = os.path.join(_base, "igo_config.json")
        _db_path = os.path.join(_base, "ui_settings.db")
        self._ws = WindowSettings(_db_path, "admin")
        self._active_env = _ACTIVE_ENV
        self._api_base_url = _ADMIN_SERVER_CONFIG[self._active_env]["api_base_url"]
        self._online_users = {}
        self._opponents = {}
        self._online_lock = threading.Lock()
        self._refresh_gen = 0  # 世代カウンター: 手動リフレッシュ時にインクリメントし、古い自動リフレッシュ結果を破棄する
        self._build_main()
        self._ws.restore_window(self.root, default_geometry="1000x900")
        self._start_heartbeat_listener()
        self._check_for_update_background()
        self._refresh()
        self._auto_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _check_for_update_background(self):
        """管理者ツールの起動時更新チェック（PyInstaller実行時のみ）。"""
        if not getattr(sys, "frozen", False):
            return
        if not _ADMIN_UPDATE_CHECK_URL:
            return

        def _is_newer(remote, current):
            def _v(s):
                try:
                    return tuple(int(x) for x in str(s).strip().split("."))
                except Exception:
                    return ()
            return _v(remote) > _v(current)

        def _worker():
            try:
                req = urllib.request.Request(_ADMIN_UPDATE_CHECK_URL)
                req.add_header("User-Agent", "GokaAdmin/{} (Windows)".format(_ADMIN_UPDATE_APP_VERSION))
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                latest = str(data.get("version", "")).strip()
                dl_url = str(data.get("admin_download_url", "")).strip()
                notes = str(data.get("release_notes", "")).strip()
                if not latest or not dl_url:
                    return
                if not _is_newer(latest, _ADMIN_UPDATE_APP_VERSION):
                    return
                self.root.after(0, lambda: self._prompt_admin_update(latest, dl_url, notes))
            except Exception:
                # 更新チェック失敗は通常起動を優先
                return

        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_admin_update(self, latest: str, download_url: str, notes: str):
        msg = (
            "管理者ツールの新しいバージョンがあります。\n\n"
            "現在: {}\n"
            "最新: {}\n\n"
            "{}\n\n"
            "今すぐ更新しますか？"
        ).format(_ADMIN_UPDATE_APP_VERSION, latest, notes or "更新内容あり")
        if not messagebox.askyesno(_ADMIN_UPDATE_TITLE, msg):
            return
        self._download_and_launch_admin_update(download_url)

    def _download_and_launch_admin_update(self, download_url: str):
        try:
            suffix = ".exe"
            lower = download_url.lower()
            if lower.endswith(".zip"):
                suffix = ".zip"
            dst = os.path.join(tempfile.gettempdir(), "goka_admin_update" + suffix)
            urllib.request.urlretrieve(download_url, dst)
            if dst.lower().endswith(".exe"):
                if hasattr(os, "startfile"):
                    os.startfile(dst)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen([dst])
                self.root.destroy()
                os._exit(0)
            messagebox.showinfo(
                _ADMIN_UPDATE_TITLE,
                "更新ファイルをダウンロードしました: {}\n手動で適用してください。".format(dst),
            )
        except Exception as e:
            messagebox.showerror(_ADMIN_UPDATE_TITLE, "更新に失敗しました:\n{}".format(e))

    def _start_heartbeat_listener(self):
        """Listen for UDP heartbeat broadcasts from game clients on port 19940."""
        def _listener():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                except Exception:
                    pass
                sock.bind(("0.0.0.0", 19940))
                sock.settimeout(2.0)
            except Exception as e:
                print("Heartbeat listener failed:", e)
                return
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode("utf-8"))
                    if msg.get("type") == "heartbeat":
                        handle = msg.get("handle", "")
                        online = msg.get("online", True)
                        opponent = msg.get("opponent", "")
                        with self._online_lock:
                            if online:
                                self._online_users[handle] = _time.time()
                                self._opponents[handle] = opponent
                            else:
                                self._online_users.pop(handle, None)
                                self._opponents.pop(handle, None)
                except socket.timeout:
                    pass
                except Exception:
                    pass
        t = threading.Thread(target=_listener, daemon=True)
        t.start()

    def _is_online(self, handle_name):
        with self._online_lock:
            last_seen = self._online_users.get(handle_name)
            if last_seen is None:
                return False
            return (_time.time() - last_seen) < 15

    def _build_main(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, minsize=_ADMIN_TAB_AREA_HEIGHT, weight=0)

        # ============================================================
        # ヘッダー: タイトル + 登録ユーザー数 + オンライン人数
        # ============================================================
        header = tk.Frame(self.root, bg=T("root_bg"))
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        tk.Label(header, text="管理者画面",
                 font=("Yu Gothic UI", 18, "bold"),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left")

        # 右側に情報ラベル
        info_frame = tk.Frame(header, bg=T("root_bg"))
        info_frame.pack(side="right")

        self.status_label = tk.Label(info_frame, text="登録ユーザー数: 0",
                                      font=("Yu Gothic UI", 11),
                                      fg=T("text_primary"), bg=T("root_bg"))
        self.status_label.pack(side="left", padx=(0, 16))

        self.online_count_label = tk.Label(info_frame, text="オンライン: 0人",
                                            font=("Yu Gothic UI", 11, "bold"),
                                            fg=T("active_green"), bg=T("root_bg"))
        self.online_count_label.pack(side="left")
        # 常時表示の接続先切替（1本運用でも見失わない位置）
        env_frame = tk.Frame(info_frame, bg=T("root_bg"))
        env_frame.pack(side="left", padx=(14, 0))
        tk.Label(env_frame, text="接続先:",
                 font=("Yu Gothic UI", 10, "bold"),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left", padx=(0, 4))
        self._env_var = tk.StringVar(value=self._active_env)
        tk.Radiobutton(env_frame, text="本番",
                       variable=self._env_var, value="production",
                       command=self._on_env_selected,
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=T("root_bg"),
                       selectcolor=T("input_bg"),
                       activebackground=T("root_bg"),
                       activeforeground=T("text_primary")).pack(side="left", padx=(0, 2))
        tk.Radiobutton(env_frame, text="テスト",
                       variable=self._env_var, value="staging",
                       command=self._on_env_selected,
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=T("root_bg"),
                       selectcolor=T("input_bg"),
                       activebackground=T("root_bg"),
                       activeforeground=T("text_primary")).pack(side="left")
        env_now = "本番" if self._active_env == "production" else "テスト"
        self._env_info_label = tk.Label(
            env_frame,
            text="現在: {} ({})".format(env_now, self._api_base_url),
            font=("Yu Gothic UI", 9),
            fg=T("text_primary"),
            bg=T("root_bg"),
        )
        self._env_info_label.pack(side="left", padx=(8, 0))
        self._runtime_info_label = tk.Label(
            info_frame,
            text="",
            font=("Yu Gothic UI", 8),
            fg=T("text_primary"),
            bg=T("root_bg"),
        )
        self._runtime_info_label.pack(side="left", padx=(10, 0))

        # ============================================================
        # メインテーブル
        # ============================================================
        tree_border = tk.Frame(self.root, bd=1, relief="solid", bg="#bfbfbf")
        tree_border.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        tree_frame = tk.Frame(tree_border, bg=T("root_bg"))
        tree_frame.pack(fill="both", expand=True, padx=1, pady=1)

        self._admin_headers = ["ID", "ハンドルネーム", "氏名", "パスワード",
                               "棋力", "Elo", "ログイン回数", "対局回数", "ステータス", "対戦相手", "メール", "登録日"]
        self.tree = Sheet(tree_frame,
            headers=self._admin_headers, data=[],
            show_x_scrollbar=True, show_y_scrollbar=True,
            show_row_index=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.set_options(
            table_bg="white", table_fg="black",
            grid_color="#d9d9d9",
            header_bg="#f3f3f3", header_fg="black",
            index_bg="#f3f3f3", index_fg="black",
            selected_cells_bg="#d9d9d9", selected_cells_fg="black",
            selected_rows_bg="#d9d9d9", selected_rows_fg="black",
            selected_columns_bg="#d9d9d9", selected_columns_fg="black",
            header_selected_columns_bg="#e2f0d9",
            header_selected_columns_fg="#217346",
        )
        self.tree.set_all_row_heights(25)
        try:
            self.tree.font(("Yu Gothic UI", 10, "normal"))
            self.tree.header_font(("Yu Gothic UI", 10, "normal"))
        except Exception:
            pass
        self.tree.enable_bindings()
        self.tree.disable_bindings("edit_cell", "edit_header", "edit_index",
            "rc_select", "rc_insert_row", "rc_delete_row",
            "rc_insert_column", "rc_delete_column",
            "copy", "cut", "paste", "undo", "delete")
        self._admin_col_widths_set = False
        for i, w in enumerate([40, 130, 120, 110, 100, 70, 90, 90, 110, 100, 180, 160]):
            self.tree.column_width(column=i, width=w)
        self._highlighted_row = None
        # 初期表示は ID 列で昇順に固定（IDとアカウント対応を追いやすくする）
        self._sort_column = 0
        self._sort_ascending = True
        self.tree.extra_bindings("cell_select", self._on_cell_select)
        self.tree.CH.bind("<Button-1>", self._on_header_mouse_down, add="+")
        self.tree.CH.bind("<ButtonRelease-1>", self._on_header_mouse_up, add="+")
        self.tree.bind("<Double-1>", self._on_sheet_double_click)
        try:
            self.tree.MT.bind("<Double-1>", self._on_sheet_double_click, add="+")
        except Exception:
            pass

        # ============================================================
        # タブ（シートとボタン欄の間）
        # Accessサンプルに合わせて「時間」「サイズ・位置」の項目を配置
        # ============================================================
        tab_outer = tk.Frame(
            self.root, bg=T("root_bg"), height=_ADMIN_TAB_AREA_HEIGHT)
        tab_outer.grid_propagate(False)
        # 縦は nsew にしない（セルが余るとタブ枠まで伸び、中身が無い空白が巨大に見える）
        tab_outer.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 0))
        tab_outer.grid_columnconfigure(0, weight=1)
        tab_outer.grid_rowconfigure(0, weight=1)
        self._admin_tabs = ttk.Notebook(tab_outer)
        self._admin_tabs.grid(row=0, column=0, sticky="nsew")

        self._admin_tab_size_pos = tk.Frame(self._admin_tabs, bg="white")
        self._admin_tab_time = tk.Frame(self._admin_tabs, bg="white")
        self._admin_tabs.add(self._admin_tab_time, text="時間")
        self._admin_tabs.add(self._admin_tab_size_pos, text="サイズ・位置")

        _tab_bg = "white"

        server_settings = None
        current_timeout = 3
        current_fischer_main = 5
        current_fischer_inc = 10
        current_bot_delay = 30
        try:
            server_settings = self._api_get("/api/settings")
            if server_settings:
                current_timeout = int(server_settings.get("offer_timeout_min", 3))
                current_fischer_main = int(server_settings.get("fischer_main_time", 300)) // 60
                current_fischer_inc = int(server_settings.get("fischer_increment", 10))
                current_bot_delay = int(server_settings.get("bot_offer_delay", 30))
        except Exception:
            pass
        self._timeout_var = tk.StringVar(value=str(current_timeout))
        self._fischer_main_var = tk.StringVar(value=str(current_fischer_main))
        self._fischer_inc_var = tk.StringVar(value=str(current_fischer_inc))
        self._bot_delay_var = tk.StringVar(value=str(current_bot_delay))

        cfg = self._load_config_safely()

        time_row = tk.Frame(self._admin_tab_time, bg=_tab_bg)
        time_row.pack(fill="x", padx=18, pady=16)

        left_time = tk.Frame(time_row, bg=_tab_bg)
        left_time.pack(side="left", padx=(0, 26), anchor="n")

        def _time_line(parent, label, var):
            row = tk.Frame(parent, bg=_tab_bg)
            row.pack(anchor="w", pady=3)
            tk.Label(row, text=label, width=14, anchor="w",
                     font=("Yu Gothic UI", 10),
                     fg=T("text_primary"), bg=_tab_bg).pack(side="left", padx=(0, 8))
            ent = tk.Entry(row, textvariable=var, width=14,
                           font=("Yu Gothic UI", 10))
            ent.pack(side="left")
            return ent

        timeout_ent = _time_line(left_time, "申請待時間", self._timeout_var)
        bot_ent = _time_line(left_time, "ロボ出現時間", self._bot_delay_var)
        fmain_ent = _time_line(left_time, "フィッシャー持ち時間", self._fischer_main_var)
        finc_ent = _time_line(left_time, "フィッシャー加算時間", self._fischer_inc_var)
        self._time_preview_label = tk.Label(
            left_time,
            text="",
            justify="left",
            font=("Yu Gothic UI", 9),
            fg=T("text_primary"),
            bg=_tab_bg,
        )
        self._time_preview_label.pack(anchor="w", pady=(8, 0))
        conv_row = tk.Frame(left_time, bg=_tab_bg)
        conv_row.pack(anchor="w", pady=(8, 0))
        tk.Label(conv_row, text="時間変換(H.M.S)", width=14, anchor="w",
                 font=("Yu Gothic UI", 10),
                 fg=T("text_primary"), bg=_tab_bg).pack(side="left", padx=(0, 8))
        self._time_convert_input_var = tk.StringVar(value="")
        convert_ent = tk.Entry(conv_row, textvariable=self._time_convert_input_var, width=14,
                               font=("Yu Gothic UI", 10))
        convert_ent.pack(side="left")
        self._time_convert_result_label = tk.Label(
            left_time,
            text="",
            justify="left",
            font=("Yu Gothic UI", 9),
            fg=T("text_primary"),
            bg=_tab_bg,
        )
        self._time_convert_result_label.pack(anchor="w", pady=(2, 0))

        def _refresh_time_preview(*_args):
            wait_s = _duration_seconds_from_text(self._timeout_var.get(), default_seconds=180)
            bot_s = _duration_seconds_from_text(self._bot_delay_var.get(), default_seconds=30)
            fish_main_s = _duration_seconds_from_text(self._fischer_main_var.get(), default_seconds=300)
            fish_inc = _duration_seconds_from_text(self._fischer_inc_var.get(), default_seconds=10)
            lines = [
                "申請待時間: {}".format(_seconds_to_japanese_hms_text(wait_s)),
                "ロボ出現時間: {}".format(_seconds_to_japanese_hms_text(bot_s)),
                "フィッシャー持ち時間: {}".format(_seconds_to_japanese_hms_text(fish_main_s)),
                "フィッシャー加算時間: {}".format(_seconds_to_japanese_hms_text(fish_inc)),
            ]
            self._time_preview_label.config(text="\n".join(lines))
            src = self._time_convert_input_var.get()
            if src.strip():
                converted = _convert_time_string_vba_style(src)
                self._time_convert_result_label.config(text="変換結果: {}".format(converted))
            else:
                self._time_convert_result_label.config(text="")

        self._timeout_var.trace_add("write", _refresh_time_preview)
        self._bot_delay_var.trace_add("write", _refresh_time_preview)
        self._fischer_main_var.trace_add("write", _refresh_time_preview)
        self._fischer_inc_var.trace_add("write", _refresh_time_preview)
        self._time_convert_input_var.trace_add("write", _refresh_time_preview)
        _refresh_time_preview()

        # Access互換: フォーカスアウト時に必ず時間文字へ正規化して表示を変える
        def _normalize_time_var_on_focusout(var):
            raw = str(var.get() or "").strip()
            if not raw:
                return
            sec = _duration_seconds_from_text(raw, default_seconds=0)
            var.set(_seconds_to_japanese_hms_text(sec))

        timeout_ent.bind("<FocusOut>", lambda _e: _normalize_time_var_on_focusout(self._timeout_var))
        bot_ent.bind("<FocusOut>", lambda _e: _normalize_time_var_on_focusout(self._bot_delay_var))
        fmain_ent.bind("<FocusOut>", lambda _e: _normalize_time_var_on_focusout(self._fischer_main_var))
        finc_ent.bind("<FocusOut>", lambda _e: _normalize_time_var_on_focusout(self._fischer_inc_var))

        # H.M.S 入力はフォーカスアウト時に「正規化H.M.S」に補正し、変換結果を即反映
        def _on_hms_focusout(_e):
            raw = self._time_convert_input_var.get()
            if not raw.strip():
                self._time_convert_result_label.config(text="")
                return
            canonical = _canonical_hms_text(raw)
            if canonical:
                self._time_convert_input_var.set(canonical)
                self._time_convert_result_label.config(
                    text="変換結果: {}".format(_convert_time_string_vba_style(canonical))
                )
            else:
                self._time_convert_result_label.config(text="変換結果: 入力形式エラー")

        convert_ent.bind("<FocusOut>", _on_hms_focusout)

        right_default = tk.LabelFrame(
            time_row, text="デフォルト持ち時間",
            font=("Yu Gothic UI", 10),
            fg=T("text_primary"), bg=_tab_bg,
            bd=1, relief="groove", padx=10, pady=8
        )
        right_default.pack(side="left", anchor="n")

        _srv_main = _to_int(server_settings.get("default_main_time_min", 10) if server_settings else 10, 10, min_value=1, max_value=180)
        _srv_byo_sec = _to_int(server_settings.get("default_byoyomi_sec", 30) if server_settings else 30, 30, min_value=1, max_value=180)
        _srv_byo_count = _to_int(server_settings.get("default_byoyomi_count", 3) if server_settings else 3, 3, min_value=1, max_value=30)
        _srv_komi = _to_float(server_settings.get("default_komi", 7.5) if server_settings else 7.5, 7.5, min_value=-50.0, max_value=50.0)
        self._default_main_time_var = tk.StringVar(value=str(_srv_main))
        self._default_byoyomi_sec_var = tk.StringVar(value=str(_srv_byo_sec))
        self._default_byoyomi_count_var = tk.StringVar(value="{}\u56de".format(_srv_byo_count))
        self._default_komi_var = tk.StringVar(value="{}\u76ee\u534a".format(_srv_komi))

        def _default_line(parent, label, var):
            row = tk.Frame(parent, bg=_tab_bg)
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=label, width=10, anchor="w",
                     font=("Yu Gothic UI", 10),
                     fg=T("text_primary"), bg=_tab_bg).pack(side="left", padx=(0, 10))
            tk.Entry(row, textvariable=var, width=12,
                     font=("Yu Gothic UI", 10)).pack(side="left")

        _default_line(right_default, "持ち時間", self._default_main_time_var)
        _default_line(right_default, "秒読み時間", self._default_byoyomi_sec_var)
        _default_line(right_default, "秒読み回数", self._default_byoyomi_count_var)
        _default_line(right_default, "コミ", self._default_komi_var)
        tk.Label(right_default, text="※インストール時のデフォルト",
                 font=("Yu Gothic UI", 9),
                 fg=T("text_primary"), bg=_tab_bg).pack(anchor="w", pady=(6, 0))

        size_root = tk.Frame(self._admin_tab_size_pos, bg=_tab_bg)
        size_root.pack(anchor="w", padx=18, pady=16)
        size_frame = tk.LabelFrame(
            size_root, text="アプリインストール時のデフォルト値",
            font=("Yu Gothic UI", 10),
            fg=T("text_primary"), bg=_tab_bg,
            bd=1, relief="groove", padx=10, pady=8
        )
        size_frame.pack(anchor="w")
        tk.Label(size_frame, text="\u203bWindows\u4f5c\u696d\u9818\u57df\u5185\u306e\u5272\u5408\u3092\u793a\u3059",
                 font=("Yu Gothic UI", 9),
                 fg=T("text_primary"), bg=_tab_bg).pack(anchor="w", pady=(0, 6))

        self._board_frame_height_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("board_frame_height", 0.78), 0.78)))
        self._board_frame_width_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("board_frame_width", 0.60), 0.60)))
        self._match_apply_height_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("match_apply_height", 0.40), 0.40)))
        self._match_apply_width_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("match_apply_width", 0.30), 0.30)))
        self._challenge_accept_height_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("challenge_accept_height", 0.40), 0.40)))
        self._challenge_accept_width_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("challenge_accept_width", 0.30), 0.30)))
        self._sakura_dialog_height_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("sakura_dialog_height", 0.36), 0.36)))
        self._sakura_dialog_width_var = tk.StringVar(
            value=_height_ratio_to_percent_text(
                _height_ratio_from_text(cfg.get("sakura_dialog_width", 0.50), 0.50)))

        def _size_line(parent, label, h_var, w_var):
            row = tk.Frame(parent, bg=_tab_bg)
            row.pack(anchor="w", pady=3)
            tk.Label(row, text=label, width=14, anchor="w",
                     font=("Yu Gothic UI", 10),
                     fg=T("text_primary"), bg=_tab_bg).pack(side="left", padx=(0, 4))
            tk.Label(row, text="\u9ad8\u3055",
                     font=("Yu Gothic UI", 9),
                     fg=T("text_primary"), bg=_tab_bg).pack(side="left")
            h_ent = tk.Entry(row, textvariable=h_var, width=6,
                             font=("Yu Gothic UI", 10))
            h_ent.pack(side="left", padx=(2, 6))
            tk.Label(row, text="\u6a2a\u5e45",
                     font=("Yu Gothic UI", 9),
                     fg=T("text_primary"), bg=_tab_bg).pack(side="left")
            w_ent = tk.Entry(row, textvariable=w_var, width=6,
                             font=("Yu Gothic UI", 10))
            w_ent.pack(side="left", padx=(2, 0))
            return h_ent, w_ent

        board_h_ent, board_w_ent = _size_line(size_frame, "\u57fa\u76e4\u30d5\u30ec\u30fc\u30e0", self._board_frame_height_var, self._board_frame_width_var)
        match_h_ent, match_w_ent = _size_line(size_frame, "\u5bfe\u5c40\u7533\u8fbc\u753b\u9762", self._match_apply_height_var, self._match_apply_width_var)
        challenge_h_ent, challenge_w_ent = _size_line(size_frame, "\u6311\u6226\u72b6\u53d7\u4ed8\u753b\u9762", self._challenge_accept_height_var, self._challenge_accept_width_var)

        # 桜吹雪ダイアログ（インストールデフォルトではなく管理者がいつでも変更可能）
        sakura_frame = tk.LabelFrame(
            size_root, text="\u685c\u5439\u96ea\u30c0\u30a4\u30a2\u30ed\u30b0\uff08\u7ba1\u7406\u8005\u8a2d\u5b9a\uff09",
            font=("Yu Gothic UI", 10),
            fg=T("text_primary"), bg=_tab_bg,
            bd=1, relief="groove", padx=10, pady=8
        )
        sakura_frame.pack(anchor="w", pady=(8, 0))
        sakura_h_ent, sakura_w_ent = _size_line(sakura_frame, "\u685c\u5439\u96ea\u30c0\u30a4\u30a2\u30ed\u30b0", self._sakura_dialog_height_var, self._sakura_dialog_width_var)

        def _normalize_height_percent_on_focusout(var, default_ratio):
            ratio = _height_ratio_from_text(var.get(), default_ratio)
            var.set(_height_ratio_to_percent_text(ratio))

        board_h_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._board_frame_height_var, 0.78))
        board_w_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._board_frame_width_var, 0.60))
        match_h_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._match_apply_height_var, 0.40))
        match_w_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._match_apply_width_var, 0.30))
        challenge_h_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._challenge_accept_height_var, 0.40))
        challenge_w_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._challenge_accept_width_var, 0.30))
        sakura_h_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._sakura_dialog_height_var, 0.36))
        sakura_w_ent.bind("<FocusOut>", lambda _e: _normalize_height_percent_on_focusout(self._sakura_dialog_width_var, 0.50))

        # --- テーマ設定（サイズ・位置タブ）---
        theme_frame = tk.LabelFrame(self._admin_tab_size_pos, text="テーマ",
                                     font=("Yu Gothic UI", 9),
                                     fg=T("text_primary"), bg=_tab_bg,
                                     bd=1, relief="groove", padx=6, pady=2)
        theme_frame.pack(anchor="w", padx=18, pady=(2, 8))

        self._theme_var = tk.StringVar(value=get_current_theme_name())
        tk.Radiobutton(theme_frame, text="ダーク",
                       variable=self._theme_var, value="dark",
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=_tab_bg,
                       selectcolor=T("input_bg"),
                       activebackground=_tab_bg,
                       activeforeground=T("text_primary")
                       ).pack(side="left", padx=(0, 4))
        tk.Radiobutton(theme_frame, text="ライト",
                       variable=self._theme_var, value="light",
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=_tab_bg,
                       selectcolor=T("input_bg"),
                       activebackground=_tab_bg,
                       activeforeground=T("text_primary")
                       ).pack(side="left")

        # ============================================================
        # ボタンバー: 削除 | 新規登録 | OK | 閉じる
        # ============================================================
        bottom = tk.Frame(self.root, bg=T("root_bg"))
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 8))

        # --- 削除ボタン（赤） ---
        self._delete_btn = GlossyButton(
            bottom,
            text="削除",
            base_color=(180, 50, 50),
            gradient=1.0, gloss=1.0, depth=0.2,
            corner_radius=None,
            text_color=(255, 255, 255),
            text_size=12,
            text_stroke=True,
            text_stroke_width=2,
            text_stroke_color=None,
            width=100, height=30,
            command=self._delete_user,
            focus_border_color=(162, 32, 65),
            focus_border_width=2,
            bg=T("root_bg"),
        )
        self._delete_btn.pack(side="left", padx=(0, 16))

        # --- 閉じるボタン（グレー）--- 右端
        self._close_btn = GlossyButton(
            bottom,
            text="閉じる",
            base_color=(159, 160, 160),
            gradient=1.0, gloss=1.0, depth=0.2,
            corner_radius=None,
            text_color=(255, 255, 255),
            text_size=12,
            text_stroke=True,
            text_stroke_width=2,
            text_stroke_color=None,
            width=100, height=30,
            command=self._on_close,
            focus_border_color=(89, 88, 87),
            focus_border_width=2,
            bg=T("root_bg"),
        )
        self._close_btn.pack(side="right")

        # --- OKボタン（緑）--- 閉じるの左
        self._ok_btn = GlossyButton(
            bottom,
            text="OK",
            base_color=(85, 165, 45),
            gradient=1.0, gloss=1.0, depth=0.2,
            corner_radius=None,
            text_color=(255, 255, 255),
            text_size=12,
            text_stroke=True,
            text_stroke_width=2,
            text_stroke_color=None,
            width=100, height=30,
            command=self._on_ok,
            focus_border_color=(0, 100, 0),
            focus_border_width=2,
            bg=T("root_bg"),
        )
        self._ok_btn.pack(side="right", padx=(0, 8))

        # --- 新規登録ボタン（青）--- OKの左
        self._register_btn = GlossyButton(
            bottom,
            text="新規登録",
            base_color=(50, 100, 180),
            gradient=1.0, gloss=1.0, depth=0.2,
            corner_radius=None,
            text_color=(255, 255, 255),
            text_size=12,
            text_stroke=True,
            text_stroke_width=2,
            text_stroke_color=None,
            width=100, height=30,
            command=self._open_register_dialog,
            focus_border_color=(30, 70, 140),
            focus_border_width=2,
            bg=T("root_bg"),
        )
        self._register_btn.pack(side="right", padx=(0, 8))

    # =================================================================
    # テーマ / タイムアウト適用
    # =================================================================
    def _on_ok(self):
        """OKボタン: テーマとタイムアウトを両方適用する。"""
        self._apply_env_switch_if_needed()
        self._apply_theme()
        self._apply_timeout()
        self._apply_fischer()
        self._apply_bot_delay()
        self._apply_default_time_values()
        self._apply_size_position_defaults()

    def _apply_env_switch_if_needed(self) -> bool:
        """接続先切替があれば保存して即時反映する。"""
        selected = (self._env_var.get() or "").strip().lower()
        if selected not in ("production", "staging"):
            selected = self._active_env
        if selected == self._active_env:
            return False
        self._switch_env_live(selected)
        return False

    def _on_env_selected(self):
        """ヘッダーの接続先ラジオ選択時に即時切替する。"""
        self._apply_env_switch_if_needed()

    def _switch_env_live(self, selected: str):
        """接続先を即時に切替し、一覧を再読込する。"""
        cfg = self._load_config_safely()
        cfg["admin_env"] = selected
        self._save_config_safely(cfg)

        self._active_env = selected
        self._api_base_url = _ADMIN_SERVER_CONFIG[selected]["api_base_url"]
        self.root.title(_ADMIN_SERVER_CONFIG[selected]["title"])
        env_now = "本番" if selected == "production" else "テスト"
        self._env_info_label.config(
            text="現在: {} ({})".format(env_now, self._api_base_url)
        )
        self._runtime_info_label.config(text="接続先情報: 切替中...")
        self._refresh()

    def _relaunch_admin_with_env(self, env: str) -> None:
        """同じ管理者ツールを指定環境で再起動する。"""
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                os.spawnl(os.P_NOWAIT, exe, exe, "--env={}".format(env))
                return
            py = sys.executable
            script = os.path.abspath(__file__)
            os.spawnl(os.P_NOWAIT, py, py, script, "--env={}".format(env))
        except Exception as e:
            messagebox.showerror("再起動エラー", str(e))

    def _load_config_safely(self):
        cfg = self._ws.load("admin_config", {})
        return cfg if isinstance(cfg, dict) else {}

    def _save_config_safely(self, cfg):
        try:
            self._ws.save("admin_config", cfg)
        except Exception:
            pass

    def _apply_theme(self):
        new_theme = self._theme_var.get()
        self._api_put("/api/settings", {"theme": new_theme})
        cfg = self._load_config_safely()
        cfg["theme"] = new_theme
        self._save_config_safely(cfg)

    def _apply_timeout(self):
        seconds = _duration_seconds_from_text(self._timeout_var.get(), default_seconds=180)
        minutes = _to_int(seconds // 60, 3, min_value=1, max_value=10)
        self._api_put("/api/settings", {"offer_timeout_min": minutes})
        cfg = self._load_config_safely()
        cfg["offer_timeout_min"] = minutes
        self._save_config_safely(cfg)

    def _apply_bot_delay(self):
        raw_seconds = _duration_seconds_from_text(self._bot_delay_var.get(), default_seconds=30)
        seconds = _to_int(raw_seconds, 30, min_value=10, max_value=600)
        self._api_put("/api/settings", {"bot_offer_delay": seconds})
        cfg = self._load_config_safely()
        cfg["bot_offer_delay"] = seconds
        self._save_config_safely(cfg)

    def _apply_fischer(self):
        main_raw_seconds = _duration_seconds_from_text(self._fischer_main_var.get(), default_seconds=300)
        main_min = _to_int(main_raw_seconds // 60, 5, min_value=1, max_value=30)
        inc_raw_seconds = _duration_seconds_from_text(self._fischer_inc_var.get(), default_seconds=10)
        inc_sec = _to_int(inc_raw_seconds, 10, min_value=1, max_value=300)
        main_sec = main_min * 60
        self._api_put("/api/settings", {"fischer_main_time": main_sec, "fischer_increment": inc_sec})
        cfg = self._load_config_safely()
        cfg["fischer_main_time"] = main_sec
        cfg["fischer_increment"] = inc_sec
        self._save_config_safely(cfg)

    def _apply_default_time_values(self):
        cfg = self._load_config_safely()
        default_main = _to_int(self._default_main_time_var.get(), 10, min_value=1, max_value=180)
        byoyomi_sec = _to_int(self._default_byoyomi_sec_var.get(), 30, min_value=1, max_value=180)
        byoyomi_count = _to_int(self._default_byoyomi_count_var.get(), 3, min_value=1, max_value=30)
        komi = _to_float(self._default_komi_var.get(), 7.5, min_value=-50.0, max_value=50.0)
        self._default_main_time_var.set(str(default_main))
        self._default_byoyomi_sec_var.set(str(byoyomi_sec))
        self._default_byoyomi_count_var.set("{}\u56de".format(byoyomi_count))
        self._default_komi_var.set("{}\u76ee\u534a".format(komi))
        cfg["default_main_time_min"] = default_main
        cfg["default_byoyomi_sec"] = byoyomi_sec
        cfg["default_byoyomi_count"] = byoyomi_count
        cfg["default_komi"] = komi
        self._save_config_safely(cfg)
        self._api_put("/api/settings", {
            "default_main_time_min": default_main,
            "default_byoyomi_sec": byoyomi_sec,
            "default_byoyomi_count": byoyomi_count,
            "default_komi": komi,
        })

    def _apply_size_position_defaults(self):
        cfg = self._load_config_safely()
        board_h = _height_ratio_from_text(self._board_frame_height_var.get(), 0.78)
        board_w = _height_ratio_from_text(self._board_frame_width_var.get(), 0.60)
        match_h = _height_ratio_from_text(self._match_apply_height_var.get(), 0.40)
        match_w = _height_ratio_from_text(self._match_apply_width_var.get(), 0.30)
        challenge_h = _height_ratio_from_text(self._challenge_accept_height_var.get(), 0.40)
        challenge_w = _height_ratio_from_text(self._challenge_accept_width_var.get(), 0.30)
        sakura_h = _height_ratio_from_text(self._sakura_dialog_height_var.get(), 0.36)
        sakura_w = _height_ratio_from_text(self._sakura_dialog_width_var.get(), 0.50)
        self._board_frame_height_var.set(_height_ratio_to_percent_text(board_h))
        self._board_frame_width_var.set(_height_ratio_to_percent_text(board_w))
        self._match_apply_height_var.set(_height_ratio_to_percent_text(match_h))
        self._match_apply_width_var.set(_height_ratio_to_percent_text(match_w))
        self._challenge_accept_height_var.set(_height_ratio_to_percent_text(challenge_h))
        self._challenge_accept_width_var.set(_height_ratio_to_percent_text(challenge_w))
        self._sakura_dialog_height_var.set(_height_ratio_to_percent_text(sakura_h))
        self._sakura_dialog_width_var.set(_height_ratio_to_percent_text(sakura_w))
        cfg["board_frame_height"] = board_h
        cfg["board_frame_width"] = board_w
        cfg["match_apply_height"] = match_h
        cfg["match_apply_width"] = match_w
        cfg["challenge_accept_height"] = challenge_h
        cfg["challenge_accept_width"] = challenge_w
        cfg["sakura_dialog_height"] = sakura_h
        cfg["sakura_dialog_width"] = sakura_w
        self._save_config_safely(cfg)
        self._api_put("/api/settings", {
            "board_frame_height": board_h,
            "board_frame_width": board_w,
            "match_apply_height": match_h,
            "match_apply_width": match_w,
            "challenge_accept_height": challenge_h,
            "challenge_accept_width": challenge_w,
            "sakura_dialog_height": sakura_h,
            "sakura_dialog_width": sakura_w,
        })

    # =================================================================
    # テーブル操作
    # =================================================================
    def _on_header_mouse_down(self, event):
        self._header_press_x = event.x

    def _on_header_mouse_up(self, event):
        press_x = getattr(self, '_header_press_x', None)
        if press_x is None:
            return
        if abs(event.x - press_x) > 5:
            return
        self._header_sort(event.x)

    def _header_sort(self, x):
        col = None
        cumulative = 0
        for i in range(len(self._admin_headers)):
            w = self.tree.column_width(column=i)
            if x < cumulative + w:
                col = i
                break
            cumulative += w
        if col is None:
            return
        if self._sort_column == col:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = col
            self._sort_ascending = True
        data = self.tree.get_sheet_data()
        if not data:
            return
        def sort_key(row):
            val = row[col] if col < len(row) else ""
            return _num_sort_key(val)
        data.sort(key=sort_key, reverse=not self._sort_ascending)
        self.tree.set_sheet_data(data, redraw=False, reset_col_positions=False)
        headers = list(self._admin_headers)
        arrow = " ▲" if self._sort_ascending else " ▼"
        headers[col] = headers[col] + arrow
        self.tree.headers(headers)
        num_cols = len(self._admin_headers)
        for i in range(num_cols):
            if i == col:
                self.tree.CH.cell_options[i] = {"highlight": ("#e2f0d9", "#217346")}
            else:
                self.tree.CH.cell_options[i] = {"highlight": ("#f3f3f3", "black")}
        if self._highlighted_row is not None:
            self.tree.dehighlight_rows(self._highlighted_row)
            self._highlighted_row = None
        self.tree.redraw()
        self._prev_rows = [r[:] for r in data]

    def _on_cell_select(self, event):
        selected_cells = self.tree.get_selected_cells()
        if not selected_cells:
            return
        row_idx = list(selected_cells)[0][0]
        if self._highlighted_row is not None:
            self.tree.dehighlight_rows(self._highlighted_row)
        self.tree.highlight_rows(rows=[row_idx], bg="#DCE9F6", fg="#000000")
        self._highlighted_row = row_idx

    def _on_sheet_double_click(self, event):
        sel = self.tree.get_currently_selected()
        if sel is None or sel.row is None or sel.column is None:
            return
        self._open_elo_editor(sel.row, sel.column)

    def _open_elo_editor(self, row, col):
        data = self.tree.get_sheet_data()
        if row >= len(data):
            return
        if col != 5:
            return
        vals = data[row]
        handle = vals[1]
        if handle.startswith("AIロボ"):
            return
        current_elo = str(vals[5]).replace(",", "")

        dlg = tk.Toplevel(self.root)
        dlg.title("Elo編集 - {}".format(handle))
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="ハンドル: {}".format(handle),
                 font=("Yu Gothic UI", 12)).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5))
        tk.Label(dlg, text="現在の棋力: {}".format(vals[4]),
                 font=("Yu Gothic UI", 11)).grid(row=1, column=0, columnspan=2, padx=15, pady=2)

        tk.Label(dlg, text="Elo:", font=("Yu Gothic UI", 11)).grid(row=2, column=0, padx=(15, 5), pady=10, sticky="e")
        elo_var = tk.StringVar(value=current_elo)
        elo_entry = tk.Entry(dlg, textvariable=elo_var, font=("Yu Gothic UI", 11), width=8)
        elo_entry.grid(row=2, column=1, padx=(0, 15), pady=10, sticky="w")
        elo_entry.select_range(0, "end")
        elo_entry.focus_set()

        preview_label = tk.Label(dlg, text="", font=("Yu Gothic UI", 11), fg="blue")
        preview_label.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 5))

        def update_preview(*args):
            elo_txt = _normalize_num_text(elo_var.get())
            if not elo_txt or not elo_txt.lstrip("-").isdigit():
                preview_label.config(text="")
                return
            elo_val = _to_int(elo_txt, 0, min_value=0, max_value=5000)
            preview_label.config(text="→ {}".format(elo_to_display_rank(elo_val)))
        elo_var.trace_add("write", update_preview)
        update_preview()

        def do_save():
            elo_txt = _normalize_num_text(elo_var.get())
            if not elo_txt or not elo_txt.lstrip("-").isdigit():
                messagebox.showwarning("警告", "数値を入力してください")
                return
            new_elo = _to_int(elo_txt, 0, min_value=0, max_value=5000)
            self._api_put("/api/user/{}/elo".format(handle),
                          {"elo": new_elo, "token": "admin", "count_match": False})
            dlg.destroy()
            self._refresh()

        btn_frame = tk.Frame(dlg)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(5, 15))
        tk.Button(btn_frame, text="保存", font=("Yu Gothic UI", 11), width=8,
                  command=do_save).pack(side="left", padx=5)
        tk.Button(btn_frame, text="キャンセル", font=("Yu Gothic UI", 11), width=8,
                  command=dlg.destroy).pack(side="left", padx=5)

        dlg.bind("<Return>", lambda e: do_save())

        dlg.update_idletasks()
        pw = dlg.winfo_reqwidth()
        ph = dlg.winfo_reqheight()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dlg.geometry("+{}+{}".format(rx + (rw - pw) // 2, ry + (rh - ph) // 2))

    # =================================================================
    # ユーザー新規登録ダイアログ
    # =================================================================
    def _open_register_dialog(self):
        """管理者画面から既存の RegisterScreen をダイアログとして表示"""
        dlg = tk.Toplevel(self.root)
        dlg.title("ユーザー新規登録")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("{}x{}".format(*RegisterScreen.DEFAULT_SIZE))
        dlg.resizable(False, False)

        def _on_success(handle):
            dlg.destroy()
            messagebox.showinfo("完了",
                "ユーザー '{}' を登録しました。".format(handle))
            self._refresh()

        RegisterScreen(
            dlg, self,
            on_close=dlg.destroy,
            on_register_success=_on_success,
        )

        # ダイアログを親ウィンドウの中央に配置
        dlg.update_idletasks()
        pw = dlg.winfo_reqwidth()
        ph = dlg.winfo_reqheight()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dlg.geometry("+{}+{}".format(rx + (rw - pw) // 2, ry + (rh - ph) // 2))

    # =================================================================
    # パスワード移行
    # =================================================================
    def _migrate_password_enc(self, handle, new_enc):
        try:
            data = {"handle_name": handle, "password_enc": new_enc}
            self._api_put("/api/user/password_enc", data)
        except Exception as e:
            print("Password migration error:", handle, e)

    # =================================================================
    # API
    # =================================================================
    def _api_get(self, path):
        try:
            url = self._api_base_url + urllib.parse.quote(path, safe="/=?&")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("API GET error:", path, e)
            return None

    def _api_put(self, path, data):
        try:
            url = self._api_base_url + urllib.parse.quote(path, safe="/=?&")
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="PUT")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("API PUT error:", path, e)
            return None

    def _update_runtime_info_label(self):
        info = self._api_get("/api/runtime-info")
        if not info:
            self._runtime_info_label.config(
                text="接続先情報: 取得失敗（server.py 未更新の可能性）"
            )
            return
        env = info.get("env", "?")
        db_name = os.path.basename(str(info.get("db_path", "")))
        self._runtime_info_label.config(
            text="接続先情報 env={} db={}".format(env, db_name)
        )

    # =================================================================
    # AIボット定義
    # =================================================================
    AI_BOTS = {
        "AIロボ1":  {"elo": 430,  "rank": "20級"},
        "AIロボ2":  {"elo": 490,  "rank": "19級"},
        "AIロボ3":  {"elo": 550,  "rank": "18級"},
        "AIロボ4":  {"elo": 610,  "rank": "17級"},
        "AIロボ5":  {"elo": 670,  "rank": "16級"},
        "AIロボ6":  {"elo": 730,  "rank": "15級"},
        "AIロボ7":  {"elo": 790,  "rank": "14級"},
        "AIロボ8":  {"elo": 850,  "rank": "13級"},
        "AIロボ9":  {"elo": 910,  "rank": "12級"},
        "AIロボ10": {"elo": 970,  "rank": "11級"},
        "AIロボ11": {"elo": 1050, "rank": "10級"},
        "AIロボ12": {"elo": 1150, "rank": "9級"},
        "AIロボ13": {"elo": 1250, "rank": "8級"},
        "AIロボ14": {"elo": 1350, "rank": "7級"},
        "AIロボ15": {"elo": 1450, "rank": "6級"},
        "AIロボ16": {"elo": 1550, "rank": "5級"},
        "AIロボ17": {"elo": 1650, "rank": "4級"},
        "AIロボ18": {"elo": 1750, "rank": "3級"},
        "AIロボ19": {"elo": 1850, "rank": "2級"},
        "AIロボ20": {"elo": 1975, "rank": "1級"},
        "AIロボ21": {"elo": 2125, "rank": "1段"},
        "AIロボ22": {"elo": 2275, "rank": "2段"},
        "AIロボ23": {"elo": 2425, "rank": "3段"},
        "AIロボ24": {"elo": 2575, "rank": "4段"},
        "AIロボ25": {"elo": 2725, "rank": "5段"},
        "AIロボ26": {"elo": 2850, "rank": "6段"},
        "AIロボ27": {"elo": 2950, "rank": "7段"},
        "AIロボ28": {"elo": 3050, "rank": "8段"},
        "AIロボ29": {"elo": 3150, "rank": "9段"},
        "AIロボ30": {"elo": 3250, "rank": "9段"},
    }

    # =================================================================
    # データ更新
    # =================================================================
    def _refresh(self, force=False):
        self._update_runtime_info_label()
        self._refresh_gen += 1  # 進行中の自動リフレッシュ結果を無効化
        users = self._api_get("/api/users")
        if users is None:
            self.status_label.config(text="サーバーに接続できません", fg=T("error_red"))
            return
        self._refresh_with_data(users, force)

    def _refresh_with_data(self, users, force=False):
        online_count = 0
        rows = []
        for u in users:
            handle = u.get("handle_name", "")
            is_online = u.get("online", False)
            status_text = u.get("status", "") if is_online else ""
            if is_online:
                online_count += 1
            elo = u.get("elo", 0)
            elo_int = round(elo) if elo else 0
            display_rank = elo_to_display_rank(elo_int) if elo_int else u.get("rank", "")
            pw_enc = u.get("password_enc", "")
            pw_plain = admin_decrypt(pw_enc)
            if pw_enc.startswith("B64:") and pw_plain and pw_plain != "（復号不可）":
                new_enc = admin_encrypt(pw_plain)
                self._migrate_password_enc(handle, new_enc)
            created = u.get("created_at", "")
            user_id = u.get("id", "")
            opponent = u.get("opponent", "")
            email = u.get("email", "")
            login_count = _to_int(u.get("login_count", 0), 0, min_value=0)
            match_count = _to_int(u.get("match_count", 0), 0, min_value=0)
            rows.append([
                user_id, handle, u.get("real_name", ""),
                pw_plain, display_rank, f"{elo_int:,}", login_count, match_count,
                status_text, opponent, email, created
            ])
        # 実ユーザーIDと衝突しにくいよう、ボットは 900000 番台の正数IDを割り当てる
        for bot_idx, (bot_name, bot_info) in enumerate(self.AI_BOTS.items(), start=1):
            rows.append([
                900000 + bot_idx, bot_name, "AI",
                "", bot_info["rank"], f"{bot_info['elo']:,}", 0, 0, "オンライン", "", "", ""
            ])
            online_count += 1

        if force or rows != getattr(self, '_prev_rows', None):
            self._prev_rows = [r[:] for r in rows]
            selected_handle = None
            sel = self.tree.get_currently_selected()
            if sel and sel.row is not None:
                data = self.tree.get_sheet_data()
                if sel.row < len(data):
                    selected_handle = data[sel.row][1]
            self.tree.set_sheet_data(rows, redraw=False, reset_col_positions=False)
            try:
                self.tree.align_columns(columns=[0, 5, 6, 7], align="e")
            except Exception:
                pass
            if not self._admin_col_widths_set:
                ncols = len(self._admin_headers)
                defaults = [40, 130, 120, 110, 100, 70, 90, 90, 110, 100, 180, 160]
                self._ws.restore_column_widths(self.tree, ncols, defaults)
                # 過去設定に極端な幅が保存されているケースの保険
                try:
                    if self.tree.column_width(column=10) < 100:
                        self.tree.column_width(column=10, width=180)
                except Exception:
                    pass
                self._admin_col_widths_set = True
            if self._sort_column is not None:
                data = self.tree.get_sheet_data()
                col = self._sort_column
                def sort_key(row):
                    val = row[col] if col < len(row) else ""
                    return _num_sort_key(val)
                data.sort(key=sort_key, reverse=not self._sort_ascending)
                self.tree.set_sheet_data(data, redraw=False, reset_col_positions=False)
                headers = list(self._admin_headers)
                arrow = " ▲" if self._sort_ascending else " ▼"
                headers[col] = headers[col] + arrow
                self.tree.headers(headers)
                num_cols = len(self._admin_headers)
                for i in range(num_cols):
                    if i == col:
                        self.tree.CH.cell_options[i] = {"highlight": ("#e2f0d9", "#217346")}
                    else:
                        self.tree.CH.cell_options[i] = {"highlight": ("#f3f3f3", "black")}
            if self._highlighted_row is not None:
                self.tree.dehighlight_rows(self._highlighted_row)
                self._highlighted_row = None
            self.tree.deselect()
            self.tree.redraw()

        self.status_label.config(
            text="登録ユーザー数: {}".format(len(users)),
            fg=T("text_primary"))
        self.online_count_label.config(
            text="オンライン: {}人".format(online_count))

    def _auto_refresh(self):
        if not getattr(self, '_refresh_busy', False):
            self._refresh_busy = True
            threading.Thread(target=self._refresh_async, daemon=True).start()
        self.root.after(1500, self._auto_refresh)

    def _refresh_async(self):
        """バックグラウンドでAPIを呼び出し、結果をメインスレッドに渡す。"""
        gen = self._refresh_gen  # 開始時の世代を記録
        try:
            users = self._api_get("/api/users")
            self.root.after(0, lambda: self._apply_refresh(users, gen))
        except Exception:
            self._refresh_busy = False

    def _apply_refresh(self, users, gen):
        """メインスレッドでUIを更新する。

        gen が現在の _refresh_gen と一致しない場合、このデータは
        手動リフレッシュ（Elo保存等）より前に取得された古いデータ
        なので破棄する。これにより保存直後に表示が元に戻る問題を防ぐ。
        """
        self._refresh_busy = False
        if gen != self._refresh_gen:
            return  # 古いデータを破棄
        if users is None:
            self.status_label.config(text="サーバーに接続できません", fg=T("error_red"))
            return
        self._refresh_with_data(users)

    def _delete_user(self):
        if self._highlighted_row is None:
            return
        data = self.tree.get_sheet_data()
        if self._highlighted_row >= len(data):
            return
        row = data[self._highlighted_row]
        handle = row[1]
        if handle == "admin":
            messagebox.showwarning("警告", "管理者アカウントは削除できません")
            return
        if messagebox.askyesno("確認", "'{}'を削除しますか？".format(handle)):
            try:
                req = urllib.request.Request(
                    self._api_base_url + "/api/user/" + urllib.parse.quote(handle, safe=''), method="DELETE")
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                messagebox.showerror("エラー", str(e))
            self._refresh()

    # =================================================================
    # 設定保存/読込
    # =================================================================
    def _on_close(self):
        ncols = len(self._admin_headers)
        self._ws.save_window(self.root, self.tree, ncols)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _run_admin_with_guard():
    """pythonw 起動時でも例外を可視化し、プロセスを確実に終了する。"""
    try:
        AdminApp().run()
    except Exception:
        tb = traceback.format_exc()
        log_path = os.path.join(_admin_app_base_dir(), "igo_admin_error.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            log_path = ""
        msg = "予期しないエラーで終了しました。"
        if log_path:
            msg += "\n\nログ: {}".format(log_path)
        else:
            msg += "\n\n詳細ログの保存に失敗しました。"
        msg += "\n\n詳細:\n{}".format(tb.splitlines()[-1] if tb else "unknown error")
        try:
            messagebox.showerror("管理者画面エラー", msg)
        except Exception:
            pass
        # 例外後にスレッドが残ってもプロセスがバックグラウンドに残らないよう強制終了
        os._exit(1)


if __name__ == "__main__":
    _run_admin_with_guard()

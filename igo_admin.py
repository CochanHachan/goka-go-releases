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
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from window_settings import WindowSettings
from cryptography.fernet import Fernet
from igo_game import T, get_current_theme_name, THEMES, elo_to_display_rank
from igo.register_screen import RegisterScreen
from glossy_pill_button import GlossyButton

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

API_BASE_URL = "http://34.24.176.248:8000"


class AdminApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("碁華 - 管理者画面")
        self.root.configure(bg=T("root_bg"))
        self.root.geometry("1000x600")
        self.root.minsize(800, 500)

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

        self._config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "igo_config.json")
        _db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ui_settings.db")
        self._ws = WindowSettings(_db_path, "admin")
        self._online_users = {}
        self._opponents = {}
        self._online_lock = threading.Lock()
        self._build_main()
        self._ws.restore_window(self.root, default_geometry="1000x600")
        self._start_heartbeat_listener()
        self._refresh()
        self._auto_refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        # ============================================================
        # ヘッダー: タイトル + 登録ユーザー数 + オンライン人数
        # ============================================================
        header = tk.Frame(self.root, bg=T("root_bg"))
        header.pack(fill="x", padx=12, pady=(10, 4))

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

        # ============================================================
        # メインテーブル
        # ============================================================
        tree_border = tk.Frame(self.root, bd=1, relief="solid", bg="#bfbfbf")
        tree_border.pack(fill="both", expand=True, padx=12, pady=4)
        tree_frame = tk.Frame(tree_border, bg=T("root_bg"))
        tree_frame.pack(fill="both", expand=True, padx=1, pady=1)

        self._admin_headers = ["ID", "ハンドルネーム", "氏名", "パスワード",
                               "棋力", "Elo", "ステータス", "対戦相手", "メール", "登録日"]
        self.tree = Sheet(tree_frame,
            headers=self._admin_headers, data=[],
            show_x_scrollbar=False, show_y_scrollbar=True,
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
        for i, w in enumerate([40, 130, 120, 110, 100, 70, 80, 100, 60, 160]):
            self.tree.column_width(column=i, width=w)
        self._highlighted_row = None
        self._sort_column = None
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
        # 設定バー: タイムアウト | Fischer | テーマ
        # ============================================================
        settings_bar = tk.Frame(self.root, bg=T("root_bg"))
        settings_bar.pack(fill="x", padx=12, pady=(4, 0))

        # ============================================================
        # ボタンバー: 削除 | 新規登録 | OK | 閉じる
        # ============================================================
        bottom = tk.Frame(self.root, bg=T("root_bg"))
        bottom.pack(fill="x", padx=12, pady=(4, 8))

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

        # --- 対局申込タイムアウト ---
        timeout_frame = tk.Frame(settings_bar, bg=T("root_bg"))
        timeout_frame.pack(side="left", padx=(0, 16))

        tk.Label(timeout_frame, text="対局申込タイムアウト",
                 font=("Yu Gothic UI", 10),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left", padx=(0, 4))

        current_timeout = 3
        server_settings = None
        try:
            server_settings = self._api_get("/api/settings")
            if server_settings:
                current_timeout = int(server_settings.get("offer_timeout_min", 3))
        except Exception:
            pass

        self._timeout_var = tk.StringVar(value=str(current_timeout))
        timeout_vals = [str(i) for i in range(1, 11)]
        timeout_cb = ttk.Combobox(timeout_frame, textvariable=self._timeout_var,
            values=timeout_vals, state="readonly",
            font=("Yu Gothic UI", 10), width=3)
        timeout_cb.pack(side="left", padx=2)

        tk.Label(timeout_frame, text="分",
                 font=("Yu Gothic UI", 10),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left")

        # --- フィッシャー時間設定 ---
        fischer_frame = tk.Frame(settings_bar, bg=T("root_bg"))
        fischer_frame.pack(side="left", padx=(0, 16))

        tk.Label(fischer_frame, text="Fischer",
                 font=("Yu Gothic UI", 10, "bold"),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left", padx=(0, 4))

        current_fischer_main = 5
        current_fischer_inc = 10
        try:
            if server_settings:
                current_fischer_main = int(server_settings.get("fischer_main_time", 300)) // 60
                current_fischer_inc = int(server_settings.get("fischer_increment", 10))
        except Exception:
            pass

        self._fischer_main_var = tk.StringVar(value=str(current_fischer_main))
        fischer_main_vals = [str(i) for i in range(1, 31)]
        fischer_main_cb = ttk.Combobox(fischer_frame, textvariable=self._fischer_main_var,
            values=fischer_main_vals, state="readonly",
            font=("Yu Gothic UI", 10), width=3)
        fischer_main_cb.pack(side="left", padx=2)

        tk.Label(fischer_frame, text="分+",
                 font=("Yu Gothic UI", 10),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left")

        self._fischer_inc_var = tk.StringVar(value=str(current_fischer_inc))
        fischer_inc_vals = [str(i) for i in [5, 10, 15, 20, 25, 30]]
        fischer_inc_cb = ttk.Combobox(fischer_frame, textvariable=self._fischer_inc_var,
            values=fischer_inc_vals, state="readonly",
            font=("Yu Gothic UI", 10), width=3)
        fischer_inc_cb.pack(side="left", padx=2)

        tk.Label(fischer_frame, text="秒",
                 font=("Yu Gothic UI", 10),
                 fg=T("text_primary"), bg=T("root_bg")).pack(side="left")

        # --- テーマ設定 ---
        theme_frame = tk.LabelFrame(settings_bar, text="テーマ",
                                     font=("Yu Gothic UI", 9),
                                     fg=T("text_primary"), bg=T("root_bg"),
                                     bd=1, relief="groove", padx=6, pady=2)
        theme_frame.pack(side="left", padx=(0, 16))

        self._theme_var = tk.StringVar(value=get_current_theme_name())
        tk.Radiobutton(theme_frame, text="ダーク",
                       variable=self._theme_var, value="dark",
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=T("root_bg"),
                       selectcolor=T("input_bg"),
                       activebackground=T("root_bg"),
                       activeforeground=T("text_primary")
                       ).pack(side="left", padx=(0, 4))
        tk.Radiobutton(theme_frame, text="ライト",
                       variable=self._theme_var, value="light",
                       font=("Yu Gothic UI", 10),
                       fg=T("text_primary"), bg=T("root_bg"),
                       selectcolor=T("input_bg"),
                       activebackground=T("root_bg"),
                       activeforeground=T("text_primary")
                       ).pack(side="left")

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
        self._apply_theme()
        self._apply_timeout()
        self._apply_fischer()

    def _apply_theme(self):
        new_theme = self._theme_var.get()
        self._api_put("/api/settings", {"theme": new_theme})
        try:
            cfg = {}
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["theme"] = new_theme
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
        except Exception:
            pass

    def _apply_timeout(self):
        try:
            minutes = int(self._timeout_var.get())
        except ValueError:
            return
        self._api_put("/api/settings", {"offer_timeout_min": minutes})
        try:
            cfg = {}
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["offer_timeout_min"] = minutes
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
        except Exception:
            pass

    def _apply_fischer(self):
        try:
            main_min = int(self._fischer_main_var.get())
            inc_sec = int(self._fischer_inc_var.get())
        except ValueError:
            return
        main_sec = main_min * 60
        self._api_put("/api/settings", {"fischer_main_time": main_sec, "fischer_increment": inc_sec})
        try:
            cfg = {}
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["fischer_main_time"] = main_sec
            cfg["fischer_increment"] = inc_sec
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
        except Exception:
            pass

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
            if val is None:
                val = ""
            try:
                # コンマ区切り数値をfloatに変換
                return (0, float(str(val).replace(",", "")))
            except (ValueError, TypeError):
                return (1, str(val).lower())
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
            try:
                elo_val = int(elo_var.get())
                preview_label.config(text="→ {}".format(elo_to_display_rank(elo_val)))
            except ValueError:
                preview_label.config(text="")
        elo_var.trace_add("write", update_preview)
        update_preview()

        def do_save():
            try:
                new_elo = int(elo_var.get())
                if new_elo < 0 or new_elo > 5000:
                    messagebox.showwarning("警告", "Eloは0〜5000の範囲で入力してください")
                    return
                self._api_put("/api/user/{}/elo".format(handle),
                              {"elo": new_elo, "token": "admin"})
                dlg.destroy()
                self._refresh()
            except ValueError:
                messagebox.showwarning("警告", "数値を入力してください")

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
            url = API_BASE_URL + urllib.parse.quote(path, safe="/=?&")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("API GET error:", path, e)
            return None

    def _api_put(self, path, data):
        try:
            url = API_BASE_URL + urllib.parse.quote(path, safe="/=?&")
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="PUT")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print("API PUT error:", path, e)
            return None

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
            rows.append([
                user_id, handle, u.get("real_name", ""),
                pw_plain, display_rank, f"{elo_int:,}", status_text, opponent, email, created
            ])
        for bot_name, bot_info in self.AI_BOTS.items():
            rows.append([
                "", bot_name, "AI",
                "", bot_info["rank"], f"{bot_info['elo']:,}", "オンライン", "", "", ""
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
                self.tree.align_columns(columns=[0, 5], align="e")
            except Exception:
                pass
            if not self._admin_col_widths_set:
                ncols = len(self._admin_headers)
                defaults = [40, 130, 120, 110, 100, 70, 110, 100, 180, 160]
                self._ws.restore_column_widths(self.tree, ncols, defaults)
                self._admin_col_widths_set = True
            if self._sort_column is not None:
                data = self.tree.get_sheet_data()
                col = self._sort_column
                def sort_key(row):
                    val = row[col] if col < len(row) else ""
                    if val is None:
                        val = ""
                    try:
                        return (0, float(str(val).replace(",", "")))
                    except (ValueError, TypeError):
                        return (1, str(val).lower())
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
        try:
            users = self._api_get("/api/users")
            self.root.after(0, lambda: self._apply_refresh(users))
        except Exception:
            self._refresh_busy = False

    def _apply_refresh(self, users):
        """メインスレッドでUIを更新する。"""
        self._refresh_busy = False
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
                    API_BASE_URL + "/api/user/" + urllib.parse.quote(handle, safe=''), method="DELETE")
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


if __name__ == "__main__":
    AdminApp().run()

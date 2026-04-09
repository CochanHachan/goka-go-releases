# -*- coding: utf-8 -*-
"""碁華 ログイン画面"""
import tkinter as tk
from tkinter import ttk

from igo.glossy_button import GlossyButton
from igo.lang import L, set_language, get_language
from igo.constants import API_BASE_URL
from igo.theme import T, _save_language_to_config
from igo.ui_helpers import _entry_cfg, _validate_ascii, _disable_ime_for


class LoginScreen:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        bg = "white"
        fg = "#333333"
        green = "#3a7a3a"
        label_font = ("Yu Gothic UI", 10)
        title_font = ("Yu Gothic UI", 20, "bold")

        container = tk.Frame(parent, bg=bg, padx=40, pady=30)
        container.place(relx=0.5, rely=0.5, anchor="center")
        self.container = container

        # --- Language selector (top right) ---
        lang_bar = tk.Frame(container, bg=bg)
        lang_bar.pack(fill="x", pady=(10, 0))
        _lang_options = [("日本語", "ja"), ("English", "en"), ("中文", "zh"), ("한국어", "ko")]
        self._lang_var = tk.StringVar()
        _cur = get_language()
        for label, code in _lang_options:
            if code == _cur:
                self._lang_var.set(label)
                break
        import tkinter.ttk as _ttk
        # コンボボックスの背景色を白に設定
        _style = _ttk.Style()
        _style.configure("White.TCombobox", fieldbackground="white", background="white")
        self._lang_combo = _ttk.Combobox(lang_bar, textvariable=self._lang_var,
            values=[lbl for lbl, _ in _lang_options], state="readonly", width=10,
            style="White.TCombobox")
        self._lang_combo.pack(side="right")
        # "Language" ラベルをコンボの左に配置（side="right"で後にpackしたものが左に来る）
        tk.Label(lang_bar, text="Language", font=("Yu Gothic UI", 10),
                 bg=bg, fg="#333333").pack(side="right", padx=(0, 5))
        self._lang_options_map = {lbl: code for lbl, code in _lang_options}
        self._lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        # --- Title ---
        self._title_label = tk.Label(container, text=L("login_title"),
                 font=title_font, bg=bg, fg=green)
        self._title_label.pack(pady=(20, 30))

        # --- Form ---
        form = tk.Frame(container, bg=bg)
        form.pack(padx=0, fill="x")

        # Import RoundedEntry and OutlineButton
        try:
            from igo.login_form import RoundedEntry, OutlineButton
            self._has_rounded = True
        except ImportError:
            self._has_rounded = False

        # ハンドルネーム
        self._name_label = tk.Label(form, text=L("login_handle"),
                 font=label_font, bg=bg, fg=fg, anchor="w")
        self._name_label.pack(anchor="w")
        if self._has_rounded:
            self._name_entry = RoundedEntry(form, width=380, height=42,
                border_color="#c0c0c0", focus_border_color=green, parent_bg=bg)
            self._name_entry.pack(pady=(4, 12), anchor="w")
            self.login_handle = self._name_entry
        else:
            self.login_handle = tk.Entry(form, **_entry_cfg())
            self.login_handle.pack(fill="x", ipady=4, pady=(0, 8))

        # パスワード
        self._pw_label = tk.Label(form, text=L("login_password"),
                 font=label_font, bg=bg, fg=fg, anchor="w")
        self._pw_label.pack(anchor="w")
        if self._has_rounded:
            self._pw_entry = RoundedEntry(form, width=380, height=42,
                border_color="#c0c0c0", focus_border_color=green,
                show="\u25cf", parent_bg=bg)
            self._pw_entry.pack(pady=(4, 25), anchor="w")
            self.login_password = self._pw_entry
            # ASCII validation on internal entry
            _vcmd_pw = (form.register(_validate_ascii), '%P')
            self._pw_entry._entry.config(validate="key", validatecommand=_vcmd_pw)
            _disable_ime_for(self._pw_entry._entry)
        else:
            _vcmd_pw = (form.register(_validate_ascii), '%P')
            self.login_password = tk.Entry(form, show="*",
                validate="key", validatecommand=_vcmd_pw, **_entry_cfg())
            self.login_password.pack(fill="x", ipady=4, pady=(0, 12))
            _disable_ime_for(self.login_password)

        # --- Buttons ---
        btn_frame = tk.Frame(form, bg=bg)
        btn_frame.pack(anchor="w")

        # ログインボタン（GlossyButton: 緑）
        self._login_btn = GlossyButton(btn_frame, text=L("login_btn"),
                  width=180, height=46, base_color=(55, 130, 55),
                  text_color="white", font=("Yu Gothic UI", 13, "bold"),
                  depth=0.6, focus_border_color=(40, 120, 40),
                  command=self._do_login, bg=bg)
        self._login_btn.pack(side="left", padx=(0, 10))

        # アカウント作成ボタン（OutlineButton: 緑枠・緑文字）
        if self._has_rounded:
            self._register_btn = OutlineButton(btn_frame,
                text=L("btn_create_account"),
                width=180, height=46, corner_radius=10,
                border_color="#4a8c4a", text_color="#3a6a3a",
                font=("Yu Gothic UI", 12),
                command=lambda: self.app.show_register(), parent_bg=bg)
            self._register_btn.pack(side="left")
        else:
            tk.Button(btn_frame, text=L("btn_create_account"),
                      font=("", 11), command=lambda: self.app.show_register(),
                      bg=bg, fg=green, relief="solid", bd=1, padx=20, pady=4,
                      cursor="hand2").pack(side="left")

        # --- Error label ---
        self.error_label = tk.Label(container, text="", font=("Yu Gothic UI", 10),
                                     bg=bg, fg="#cc5050")
        self.error_label.pack(pady=(15, 0))

        # --- Focus & key bindings ---
        if self._has_rounded:
            self._name_entry.focus_set()
            self._name_entry.bind_entry("<Return>", lambda e: self._pw_entry.focus_set())
            self._pw_entry.bind_entry("<Return>", lambda e: self._do_login())
        else:
            self.login_handle.after(100, lambda: self.login_handle.focus_set())

    def _on_lang_change(self, _e=None):
        code = self._lang_options_map.get(self._lang_var.get(), "ja")
        set_language(code)
        _save_language_to_config(code)
        self._title_label.config(text=L("login_title"))
        self._name_label.config(text=L("login_handle"))
        self._pw_label.config(text=L("login_password"))
        self._login_btn.set_text(L("login_btn"))
        # アカウント作成ボタンのテキストも更新
        if self._has_rounded and hasattr(self._register_btn, '_text_id'):
            self._register_btn.itemconfig(self._register_btn._text_id, text=L("btn_create_account"))

    def _do_login(self):
        handle = self.login_handle.get().strip()
        pw = self.login_password.get().strip()
        if not handle or not pw:
            self.error_label.config(text=L("login_empty"))
            return
        import urllib.request as _urlreq, json as _json
        try:
            _data = _json.dumps({"handle_name": handle, "password": pw}).encode("utf-8")
            _req = _urlreq.Request(
                API_BASE_URL + "/api/login",
                data=_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with _urlreq.urlopen(_req, timeout=10) as _resp:
                _result = _json.loads(_resp.read().decode("utf-8"))
        except Exception as _e:
            self.error_label.config(text=L("login_server_error"))
            return
        if not _result.get("success"):
            self.error_label.config(text=_result.get("message", L("login_failed")))
            return
        self.app._auth_token = _result.get("token", "")
        _user = dict(_result.get("user", {}))
        _user["elo_rating"] = _user.pop("elo", 0)
        _user.setdefault("language", get_language())
        _user.setdefault("id", 0)
        _user.setdefault("password_plain", "")
        self.error_label.config(text="")
        self.app.on_login_success(_user)

    def reset(self):
        if hasattr(self.login_handle, 'set'):
            self.login_handle.set("")
            self.login_password.set("")
        else:
            self.login_handle.delete(0, "end")
            self.login_password.delete(0, "end")
        self.error_label.config(text="")
        # ハンドルネーム入力欄にカーソルを移動（deiconify後に確実にフォーカスするためafter使用）
        self.parent.after(100, self.login_handle.focus_set)


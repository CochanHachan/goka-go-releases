# -*- coding: utf-8 -*-
"""碁華 ユーザー登録画面"""
import tkinter as tk
from tkinter import messagebox, ttk

from igo.glossy_button import GlossyButton
from igo.lang import L, get_language
from igo.constants import API_BASE_URL
from igo.theme import T
from igo.elo import (
    rank_to_initial_elo, elo_to_rank, rank_to_localized,
    get_localized_go_ranks, localized_rank_to_internal,
)
from igo.ui_helpers import (
    _entry_cfg, _validate_ascii, _disable_ime_for,
    _configure_combo_style, _apply_combo_listbox_style,
)


class RegisterScreen:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app

        container = tk.Frame(parent, bg=T("container_bg"), padx=20, pady=20)
        container.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(container, text=L("reg_title"),
                 font=("", 22, "bold"),
                 fg=T("accent_gold"), bg=T("container_bg")).pack(pady=(0, 8))

        form = tk.Frame(container, bg=T("container_bg"))
        form.pack(fill="x")

        _sp = 8  # 各項目の等間隔スペース

        # fields: (lang_key, entry_key, is_pw)
        fields = [
            ("reg_realname",  "realname",  False),
            ("reg_handle",    "handle",    False),
            ("reg_email",     "email",     False),
            ("reg_password",  "password",  True),
            ("reg_password2", "password2", True),
        ]
        self.entries = {}
        self._handle_warn_label = None
        for lang_key, entry_key, is_pw in fields:
            tk.Label(form, text=L(lang_key), font=("", 11),
                     fg=T("text_secondary"), bg=T("container_bg"), anchor="w").pack(fill="x", pady=(_sp, 2))
            if is_pw:
                _vcmd = (form.register(_validate_ascii), '%P')
                e = tk.Entry(form, show="*",
                    validate="key", validatecommand=_vcmd, **_entry_cfg())
                _disable_ime_for(e)
            else:
                e = tk.Entry(form, **_entry_cfg())
            if entry_key == "email":
                _disable_ime_for(e)
            e.pack(fill="x", ipady=4, pady=(0, 0))
            self.entries[entry_key] = e
            if entry_key == "handle":
                self._handle_warn_label = tk.Label(form, text="", font=("", 9),
                    fg=T("error_red"), bg=T("container_bg"), anchor="w")
                _sv = tk.StringVar()
                e.config(textvariable=_sv)
                self._handle_sv = _sv
                self._handle_entry = e
                def _on_handle_change(*args, _w=self._handle_warn_label, _e=e):
                    val = self._handle_sv.get()
                    if len(val) > 20:
                        _w.config(text=L("reg_handle_warn"))
                        try:
                            _w.pack(after=_e, fill="x", pady=(2, 0))
                        except tk.TclError:
                            pass
                    else:
                        _w.config(text="")
                        _w.pack_forget()
                _sv.trace_add("write", _on_handle_change)

        tk.Label(form, text=L("reg_rank"), font=("", 11),
                 fg=T("text_secondary"), bg=T("container_bg"), anchor="w").pack(fill="x", pady=(_sp, 2))
        _loc_ranks = get_localized_go_ranks()
        self.rank_var = tk.StringVar(value=rank_to_localized("1\u7d1a"))
        style = ttk.Style()
        _configure_combo_style(style, "Dark.TCombobox")
        self.rank_combo = ttk.Combobox(form, textvariable=self.rank_var,
            values=_loc_ranks, state="readonly", style="Dark.TCombobox",
            font=("", 11))
        self.rank_combo.pack(fill="x", ipady=4, pady=(0, 0))
        _apply_combo_listbox_style(self.rank_combo)

        self.error_label = tk.Label(form, text="", font=("", 10),
                                     fg=T("error_red"), bg=T("container_bg"))
        self.error_label.pack(fill="x", pady=(0, 0))

        btn_frame = tk.Frame(form, bg=T("container_bg"))
        btn_frame.pack(pady=(_sp, 0))

        self._register_btn = GlossyButton(btn_frame, text=L("reg_btn"),
                  width=180, height=40, base_color=(50, 150, 50),
                  focus_border_color=(40, 120, 40),
                  command=self._do_register, bg=T("container_bg"))
        self._register_btn.pack(side="left", padx=(0, 12))

        self._back_btn = GlossyButton(btn_frame, text=L("reg_back"),
                  width=100, height=40, base_color=(50, 150, 50),
                  focus_border_color=(40, 120, 40),
                  command=lambda: self.app.show_login(), bg=T("container_bg"))
        self._back_btn.pack(side="left")

        # Set initial focus to name entry
        self.entries["realname"].after(100, lambda: self.entries["realname"].focus_set())

    def _do_register(self):
        name = self.entries["realname"].get().strip()
        handle = self.entries["handle"].get().strip()
        email = self.entries["email"].get().strip()
        pw = self.entries["password"].get().strip()
        pw2 = self.entries["password2"].get().strip()
        rank = localized_rank_to_internal(self.rank_var.get())

        if not name or not handle or not pw:
            self.error_label.config(text="\u5168\u3066\u306e\u9805\u76ee\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044")
            return
        if len(handle) > 20:
            self.error_label.config(text="\u30cf\u30f3\u30c9\u30eb\u30cd\u30fc\u30e0\u306f20\u5b57\u4ee5\u5185\u3067\u3059\u3002")
            entry = self.entries["handle"]
            def _delayed_focus():
                entry.focus_force()
                entry.config(selectbackground="#FFFF99", selectforeground="black")
                entry.select_range(0, "end")
                entry.icursor("end")
            self.app.root.after(50, _delayed_focus)
            return
        if len(pw) < 4:
            self.error_label.config(text="\u30d1\u30b9\u30ef\u30fc\u30c9\u306f\uff14\u6587\u5b57\u4ee5\u4e0a\u3067\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044")
            return
        if pw != pw2:
            self.error_label.config(text="\u30d1\u30b9\u30ef\u30fc\u30c9\u304c\u4e00\u81f4\u3057\u307e\u305b\u3093")
            return

        initial_elo = rank_to_initial_elo(rank)
        # サーバーに送るrankは日本語ベース（サブレベルなし）
        base_rank = elo_to_rank(initial_elo)
        import urllib.request as _urlreq, json as _json
        try:
            _data = _json.dumps({
                "real_name": name,
                "handle_name": handle,
                "password": pw,
                "rank": base_rank,
                "elo": initial_elo,
                "email": email,
            }).encode("utf-8")
            _req = _urlreq.Request(
                API_BASE_URL + "/api/register",
                data=_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with _urlreq.urlopen(_req, timeout=10) as _resp:
                _result = _json.loads(_resp.read().decode("utf-8"))
            ok = _result.get("success", False)
            err = _result.get("message", "\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f")
        except Exception as _e:
            ok = False
            err = "\u30b5\u30fc\u30d0\u30fc\u306b\u63a5\u7d9a\u3067\u304d\u307e\u305b\u3093"
        if not ok:
            self.error_label.config(text=err)
            return

        self.error_label.config(text="")
        messagebox.showinfo("\u5b8c\u4e86",
            "\u30a2\u30ab\u30a6\u30f3\u30c8\u3092\u4f5c\u6210\u3057\u307e\u3057\u305f\u3002\u30ed\u30b0\u30a4\u30f3\u3057\u3066\u304f\u3060\u3055\u3044\u3002")
        self.app.show_login()

    def reset(self):
        for e in self.entries.values():
            e.delete(0, "end")
        self.error_label.config(text="")

# -*- coding: utf-8 -*-
"""碁華 対局申し込みダイアログ"""
import tkinter as tk
from tkinter import ttk
import os
import socket
import threading
import json
import time as _time

from glossy_button import GlossyButton
from lang import L, get_language
from window_settings import WindowSettings
from igo.constants import NET_UDP_PORT, BLACK, WHITE
from igo.theme import T
from igo.elo import elo_to_display_rank
from igo.config import get_offer_timeout_ms
from igo.ui_helpers import _configure_combo_style, _apply_combo_listbox_style

# Lazy import: tksheet
Sheet = None
def _ensure_tksheet():
    global Sheet
    if Sheet is None:
        from tksheet import Sheet as _Sheet
        Sheet = _Sheet


class MatchDialog:
    """Dialog for setting up and discovering LAN matches."""
    def __init__(self, parent_root, app):
        self.app = app
        self.win = tk.Toplevel(parent_root)
        self.win.withdraw()  # Hide until positioned
        self.win.title("\u5bfe\u5c40\u7533\u3057\u8fbc\u307f")
        self.win.configure(bg=T("container_bg"))
        self.win.resizable(False, True)  # 横固定、縦のみ変更可
        self.win.transient(parent_root)
        # Restore saved height or use default
        handle = app.current_user["handle_name"] if app.current_user else "default"
        self._ws = WindowSettings(app._ws._db_path, "match_dialog_{}".format(handle))
        saved_h = self._ws.load("height")
        dw = 460
        dh = saved_h if saved_h and isinstance(saved_h, int) else 520
        # Center on parent window
        self.win.update_idletasks()
        pw = parent_root.winfo_width()
        ph = parent_root.winfo_height()
        px = parent_root.winfo_x()
        py = parent_root.winfo_y()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.win.geometry("{}x{}+{}+{}".format(dw, dh, x, y))

        self._udp_sock = None
        self._listening = False
        self._offers = {}  # ip -> offer dict
        self._hosting = False

        self._build_ui()
        self._start_udp_listen()
        self.win.protocol("WM_DELETE_WINDOW", self._close_reject_all)
        # Show after fully built and positioned
        self.win.deiconify()
        app._last_focused_dialog = self
        def _on_focus(e, win=self.win, dlg=self, a=app):
            try:
                if e.widget.winfo_toplevel() == win:
                    win.lift()
                    a._last_focused_dialog = dlg
            except Exception:
                pass
        self.win.bind("<FocusIn>", _on_focus)

    def _build_ui(self):
        bg = T("container_bg")
        fg = T("text_primary")
        lfg = T("text_secondary")

        # --- Player banner ---
        user = self.app.current_user
        if user:
            handle = user["handle_name"] if user["handle_name"] else ""
            rank = elo_to_display_rank(user["elo_rating"]) if user["elo_rating"] else user["rank"]
            player_text = "\u3000{}\uff08{}）".format(handle, rank) if rank else handle
        else:
            player_text = ""
        try:
            from teal_banner import TealBanner
            banner_frame = tk.Frame(self.win, bg=bg, height=50)
            banner_frame.pack(fill="x", pady=(12, 6), padx=12)
            banner_frame.pack_propagate(False)
            self._banner = TealBanner(banner_frame,
                text=player_text, width=420, height=48,
                font_weight="normal",
                text_color=(40, 45, 38),
                text_stroke_color=None,
                bg_edge=(189, 213, 149),
                bg_center=(217, 242, 208),
                border_color=(187, 210, 143),
                border_width=None,
                bg=bg)
            self._banner.pack(fill="both", expand=True)
            def _on_match_banner_resize(event):
                new_w = event.width - 2
                if new_w > 50 and new_w != self._banner._width:
                    self._banner.update_size(new_w, 48)
            banner_frame.bind("<Configure>", _on_match_banner_resize)
        except Exception as e:
            print("TealBanner error:", e)
            tk.Label(self.win, text=player_text,
                     font=("", 13, "bold"), fg=fg, bg=bg).pack(pady=(12, 4))

        # --- Settings section ---
        settings_lf = tk.LabelFrame(self.win, text="\u5bfe\u5c40\u6761\u4ef6\u8a2d\u5b9a",
                                     font=("", 10), fg=fg, bg=bg, padx=8, pady=6)
        settings_lf.pack(fill="x", padx=12, pady=(8, 4))

        # Configure combobox style with groove
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Groove.TCombobox",
                         borderwidth=4,
                         relief="groove",
                         fieldbackground="#fffde7",
                         background="#e0e0e0",
                         arrowcolor="#1976d2",
                         padding=5)
        style.map("Groove.TCombobox",
                  fieldbackground=[("focus", "#fff176")],
                  bordercolor=[("focus", "#ff5722")],
                  relief=[("focus", "groove")])

        # Left: settings grid, Right: buttons (use grid for vertical alignment)
        settings_inner = tk.Frame(settings_lf, bg=bg)
        settings_inner.pack(fill="x")

        left_frame = tk.Frame(settings_inner, bg=bg)
        left_frame.pack(side="left", fill="both", expand=True)

        right_frame = tk.Frame(settings_inner, bg=bg)
        right_frame.pack(side="right", padx=(8, 0))

        COMBO_W = 6

        # Use grid layout for precise alignment
        tk.Label(left_frame, text="\u6301\u3061\u6642\u9593", font=("", 10),
                 fg=lfg, bg=bg, anchor="e").grid(row=0, column=0, sticky="e", padx=(0, 4), pady=4)
        self.main_time_var = tk.StringVar(value="10\u5206")
        main_vals = ["{}\u5206".format(i) for i in range(1, 61)]
        cb1 = ttk.Combobox(left_frame, textvariable=self.main_time_var,
            values=main_vals, state="readonly", style="Groove.TCombobox",
            font=("", 10), width=COMBO_W)
        cb1.grid(row=0, column=1, padx=2, pady=4)
        tk.Label(left_frame, text="\u30b3\u30df", font=("", 10),
                 fg=lfg, bg=bg, anchor="e").grid(row=0, column=2, sticky="e", padx=(8, 4), pady=4)
        self.komi_var = tk.StringVar(value="6\u76ee\u534a")
        komi_vals = ["5\u76ee\u534a", "6\u76ee\u534a", "7\u76ee\u534a"]
        cb4 = ttk.Combobox(left_frame, textvariable=self.komi_var,
            values=komi_vals, state="readonly", style="Groove.TCombobox",
            font=("", 10), width=COMBO_W)
        cb4.grid(row=0, column=3, padx=2, pady=4)

        tk.Label(left_frame, text="\u79d2\u8aad\u307f", font=("", 10),
                 fg=lfg, bg=bg, anchor="e").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=4)
        self.byo_time_var = tk.StringVar(value="30\u79d2")
        byo_vals = ["{}\u79d2".format(i) for i in [10, 20, 30, 40, 50, 60]]
        cb2 = ttk.Combobox(left_frame, textvariable=self.byo_time_var,
            values=byo_vals, state="readonly", style="Groove.TCombobox",
            font=("", 10), width=COMBO_W)
        cb2.grid(row=1, column=1, padx=2, pady=4)
        tk.Label(left_frame, text="\u56de\u6570", font=("", 10),
                 fg=lfg, bg=bg, anchor="e").grid(row=1, column=2, sticky="e", padx=(8, 4), pady=4)
        self.byo_periods_var = tk.StringVar(value="5\u56de")
        period_vals = ["\u221e"] + ["{}\u56de".format(i) for i in range(1, 11)]
        cb3 = ttk.Combobox(left_frame, textvariable=self.byo_periods_var,
            values=period_vals, state="readonly", style="Groove.TCombobox",
            font=("", 10), width=COMBO_W)
        cb3.grid(row=1, column=3, padx=2, pady=4)

        # Right side: 対局申込 + 取消 buttons
        self.host_btn = GlossyButton(right_frame, text=L("btn_host"),
                  width=100, height=30, base_color=(50, 150, 50),
                  focus_border_color=(40, 120, 40),
                  command=self._start_hosting, bg=bg)
        self.host_btn.pack(pady=(0, 4))

        self.cancel_btn = GlossyButton(right_frame, text=L("btn_cancel"),
                  width=100, height=30, base_color=(180, 50, 50),
                  focus_border_color=(140, 40, 40),
                  command=self._cancel_hosting, bg=bg)
        self.cancel_btn.pack()
        self.cancel_btn._disabled = True
        self.cancel_btn.configure(cursor="")

        # Status message
        self.host_status = tk.Label(self.win, text="", font=("", 10),
                                     fg=T("accent_gold"), bg=bg)
        self.host_status.pack(pady=(2, 0))

        # Winrate checkbox
        self.winrate_var = tk.BooleanVar(value=True)
        winrate_check = tk.Checkbutton(self.win, text="\u5f62\u52e2\u5224\u65ad\u3092\u8868\u793a\u3059\u308b",
                                        variable=self.winrate_var,
                                        font=("", 9), fg=fg, bg=bg,
                                        activebackground=bg, selectcolor="white",
                                        anchor="w")
        winrate_check.pack(fill="x", padx=16, pady=(2, 0))

        # --- Separator ---
        sep = tk.Frame(self.win, bg=T("separator"), height=1)
        sep.pack(fill="x", padx=12, pady=(2, 2))

        # --- Match list ---
        tk.Label(self.win, text="\u6311\u6226\u72b6",
                 font=("", 11, "bold"), fg=fg, bg=bg, anchor="w").pack(fill="x", padx=14, pady=(1, 2))

        # --- Buttons first (side=bottom) so grid doesn't push them off ---
        btn_frame = tk.Frame(self.win, bg=bg)
        btn_frame.pack(side="bottom", fill="x", padx=12, pady=(4, 8))

        list_border = tk.Frame(self.win, bd=1, relief="solid", bg="#bfbfbf")
        list_border.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame = tk.Frame(list_border, bg=T("input_bg"))
        list_frame.pack(fill="both", expand=True, padx=1, pady=1)

        _ensure_tksheet()
        self.match_list = Sheet(list_frame,
            headers=["対局者", "棋力", "持ち時間", "コミ"], data=[],
            show_x_scrollbar=False, show_y_scrollbar=True,
            show_row_index=False)
        self.match_list.pack(fill="both", expand=True)
        self.match_list.set_options(
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
        self.match_list.set_all_row_heights(25)
        try:
            self.match_list.font(("Yu Gothic UI", 10, "normal"))
            self.match_list.header_font(("Yu Gothic UI", 10, "normal"))
        except Exception:
            pass
        self.match_list.enable_bindings()
        self.match_list.disable_bindings("edit_cell", "edit_header", "edit_index",
            "rc_select", "rc_insert_row", "rc_delete_row",
            "rc_insert_column", "rc_delete_column",
            "copy", "cut", "paste", "undo", "delete")
        # Restore saved column widths or use defaults
        self._ws.restore_column_widths(self.match_list, 4, [120, 80, 120, 70])
        self._match_highlighted_row = None
        self.match_list.extra_bindings("cell_select", self._on_match_cell_select)

        from glossy_pill_button import GlossyButton as GlossyPillButton
        _lang = get_language()
        _accept_text  = {"ja": "承諾", "en": "Accept",  "zh": "接受", "ko": "수락"}.get(_lang, "承諾")
        _decline_text = {"ja": "辞退", "en": "Decline", "zh": "拒绝", "ko": "거절"}.get(_lang, "辞退")
        _close_text   = {"ja": "閉じる", "en": "Close",  "zh": "关闭", "ko": "닫기"}.get(_lang, "閉じる")

        GlossyPillButton(btn_frame, text=_close_text,
            base_color=(159, 160, 160), text_size=13, width=110, height=32,
            focus_border_color=(89, 88, 87), focus_border_width=2,
            command=self._close_reject_all, bg=bg).pack(side="right")

        # Accept button (initially hidden)
        self._match_accept_btn = GlossyPillButton(btn_frame, text=_accept_text,
            base_color=(85, 165, 45), text_size=13, width=110, height=32,
            focus_border_color=(0, 100, 0), focus_border_width=2,
            command=self._accept_match, bg=bg)
        self._match_accept_btn.pack(side="left", padx=(0, 8))
        self._match_accept_btn.pack_forget()

        # Reject button (initially hidden)
        self._match_reject_btn = GlossyPillButton(btn_frame, text=_decline_text,
            base_color=(232, 57, 41), text_size=13, width=110, height=32,
            focus_border_color=(162, 32, 65), focus_border_width=2,
            command=self._reject_match, bg=bg)
        self._match_reject_btn.pack(side="left", padx=(0, 8))
        self._match_reject_btn.pack_forget()

    def _get_byo_periods_int(self):
        v = self.byo_periods_var.get()
        if v == "\u221e":
            return 0
        return int(v.replace("\u56de", ""))

    def _get_komi_float(self):
        v = self.komi_var.get()
        if "5" in v:
            return 5.5
        elif "7" in v:
            return 7.5
        return 6.5

    def _start_hosting(self):
        if self._hosting:
            return
        self._hosting = True
        main_t = int(self.main_time_var.get().replace("\u5206", "")) * 60
        byo_t = int(self.byo_time_var.get().replace("\u79d2", ""))
        byo_p = self._get_byo_periods_int()
        komi = self._get_komi_float()
        user = self.app.current_user
        self.host_status.config(text="\u5bfe\u5c40\u76f8\u624b\u3092\u5f85\u3063\u3066\u3044\u307e\u3059...",
                                fg=T("active_green"))
        self.host_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        # Save winrate preference to app
        self.app._show_winrate = self.winrate_var.get()
        self.app.start_hosting(main_t, byo_t, byo_p, komi, self._on_opponent_found)
        self._host_timeout_id = self.win.after(get_offer_timeout_ms(), self._hosting_timeout)

    def _hosting_timeout(self):
        """Auto-cancel hosting after 60 seconds with no response."""
        # Broadcast match_taken so receivers close their dialogs silently
        try:
            _tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _tsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            _tmsg = json.dumps({"type": "match_taken",
                "host_name": self.app.current_user["handle_name"] if self.app.current_user else ""
            }).encode("utf-8")
            _tsock.sendto(_tmsg, ("<broadcast>", NET_UDP_PORT + 1))
            _tsock.close()
        except Exception:
            pass
        if self._hosting:
            self.app.stop_hosting()
            self._hosting = False
        self.host_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.host_status.config(
            text="\u5bfe\u5c40\u6761\u4ef6\u3092\u627f\u8afe\u3059\u308b\u30d7\u30ec\u30a4\u30e4\u30fc\u304c\u5b58\u5728\u3057\u307e\u305b\u3093\u3067\u3057\u305f",
            fg=T("error_red"))

    def _cancel_hosting(self):
        """Cancel the current match offer."""
        if hasattr(self, "_host_timeout_id"):
            try:
                self.win.after_cancel(self._host_timeout_id)
            except Exception:
                pass
        # Broadcast match_taken so receivers close their dialogs
        try:
            _tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _tsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            _tmsg = json.dumps({"type": "match_taken",
                "host_name": self.app.current_user["handle_name"] if self.app.current_user else ""
            }).encode("utf-8")
            _tsock.sendto(_tmsg, ("<broadcast>", NET_UDP_PORT + 1))
            _tsock.close()
        except Exception:
            pass
        if self._hosting:
            self.app.stop_hosting()
            self._hosting = False
        self.host_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.host_status.config(text="\u7533\u3057\u8fbc\u307f\u3092\u53d6\u308a\u6d88\u3057\u307e\u3057\u305f",
                                fg=T("text_disabled"))

    def _on_opponent_found(self, opponent_info):
        """Called from network thread when opponent connects."""
        self.win.after(0, lambda: self._handle_opponent(opponent_info))

    def _handle_opponent(self, opponent_info):
        if hasattr(self, "_host_timeout_id"):
            self.win.after_cancel(self._host_timeout_id)
        self._on_close()

    def _start_udp_listen(self):
        self._listening = True
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass
        self._udp_sock.settimeout(1.0)
        self._udp_sock.bind(("", NET_UDP_PORT))
        threading.Thread(target=self._udp_recv_loop, daemon=True).start()
        self._refresh_list_timer()

    def _udp_recv_loop(self):
        while self._listening:
            try:
                data, addr = self._udp_sock.recvfrom(4096)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "match_offer":
                    # Skip own broadcasts
                    my_name = ""
                    if self.app.current_user:
                        my_name = self.app.current_user["handle_name"]
                    sender_name = msg.get("name", "")
                    if sender_name != my_name and sender_name not in self.app._declined_offers:
                        msg["_addr"] = addr[0]
                        msg["_time"] = _time.time()
                        self._offers[sender_name] = msg
            except socket.timeout:
                continue
            except Exception:
                if self._listening:
                    continue
                return

    def add_cloud_offer(self, offer):
        """Add a match offer received from cloud to the LAN list."""
        name = offer.get("name", "?")
        if name in self._offers:
            self._offers[name]["_time"] = _time.time()
            return
        offer["_addr"] = None
        offer["_time"] = _time.time()
        self._offers[name] = offer
        self._refresh_list()

    def _refresh_list_timer(self):
        if not self._listening:
            return
        self._refresh_list()
        self.win.after(2000, self._refresh_list_timer)

    def _refresh_list(self):
        now = _time.time()
        # Remove stale offers (>8 seconds old) - only for LAN offers
        stale = [k for k, v in self._offers.items()
                 if v.get("_addr") is not None and now - v.get("_time", 0) > 8]
        for k in stale:
            del self._offers[k]
        rows = []
        for ip, offer in self._offers.items():
            byo_p = offer.get("byo_periods", 5)
            byo_str = "\u221e" if byo_p == 0 else str(byo_p)
            main_m = offer.get("main_time", 600) // 60
            komi = offer.get("komi", 6.5)
            komi_str = "{}\u76ee\u534a".format(int(komi))
            time_str = "{}\u5206+{}\u79d2\u00d7{}".format(main_m, offer.get("byo_time", 30), byo_str)
            rows.append([offer.get("name", "?"), offer.get("rank", "?"),
                         time_str, komi_str])
        self.match_list.set_sheet_data(rows, redraw=False, reset_col_positions=False)
        if not getattr(self, '_match_col_widths_set', False):
            self._ws.restore_column_widths(self.match_list, 4, [120, 80, 120, 70])
            self._match_col_widths_set = True
        self.match_list.redraw()
        # Show/hide accept & reject buttons based on offers
        if rows:
            self._match_accept_btn.pack(side="left", padx=(0, 8))
            self._match_reject_btn.pack(side="left", padx=(0, 8))
        else:
            self._match_accept_btn.pack_forget()
            self._match_reject_btn.pack_forget()

    def _on_match_cell_select(self, event):
        """Highlight selected row."""
        selected_cells = self.match_list.get_selected_cells()
        if not selected_cells:
            return
        row_idx = list(selected_cells)[0][0]
        if self._match_highlighted_row is not None:
            self.match_list.dehighlight_rows(self._match_highlighted_row)
        self.match_list.highlight_rows(rows=[row_idx], bg="#DCE9F6", fg="#000000")
        self._match_highlighted_row = row_idx

    def _accept_match(self):
        if self._match_highlighted_row is None:
            return
        idx = self._match_highlighted_row
        keys = list(self._offers.keys())
        if idx >= len(keys):
            return
        key = keys[idx]
        offer = self._offers[key]
        self._listening = False
        try:
            self._udp_sock.close()
        except Exception:
            pass

        if offer.get("_addr") is None:
            # Cloud offer: accept via WebSocket
            user = self.app.current_user
            rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
            elo = user["elo_rating"] if user else 0
            self.app._cloud_main_time = offer.get("main_time", 600)
            self.app._cloud_byo_time = offer.get("byo_time", 30)
            self.app._cloud_byo_periods = offer.get("byo_periods", 5)
            self.app._cloud_komi = offer.get("komi", 6.5)
            self.app.send_cloud_message({
                "type": "match_accept",
                "target": key,
                "rank": rank,
                "elo": elo,
            })
            self._on_close()
        else:
            # LAN offer: TCP connect
            self.app.join_match(offer["_addr"], offer, self._on_join_done)

    def _reject_match(self):
        """Reject selected offer only."""
        if self._match_highlighted_row is None:
            return
        idx = self._match_highlighted_row
        keys = list(self._offers.keys())
        if idx >= len(keys):
            return
        name = keys[idx]
        self.app._declined_offers.add(name)
        del self._offers[name]
        self._match_highlighted_row = None
        self._refresh_list()

    def _close_reject_all(self):
        """Cancel own hosting, reject all incoming offers, close dialog."""
        # Add all current offers to declined list
        for name in list(self._offers.keys()):
            self.app._declined_offers.add(name)
        self._offers.clear()
        self._on_close()

    def _on_join_done(self):
        self.win.after(0, self._on_close)

    def _save_col_widths(self):
        """Save current column widths to DB."""
        try:
            widths = [self.match_list.column_width(column=i) for i in range(4)]
            self._ws.save("column_widths", widths)
        except Exception:
            pass

    def _save_height(self):
        """Save current dialog height to DB."""
        try:
            h = self.win.winfo_height()
            if h > 100:
                self._ws.save("height", h)
        except Exception:
            pass

    def _on_close(self):
        self._save_col_widths()
        self._save_height()
        self._listening = False
        if hasattr(self, "_host_timeout_id"):
            try:
                self.win.after_cancel(self._host_timeout_id)
            except Exception:
                pass
        if self._hosting:
            try:
                _tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                _tsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                _tmsg = json.dumps({"type": "match_taken",
                    "host_name": self.app.current_user["handle_name"] if self.app.current_user else ""
                }).encode("utf-8")
                _tsock.sendto(_tmsg, ("<broadcast>", NET_UDP_PORT + 1))
                _tsock.close()
            except Exception:
                pass
            self.app.stop_hosting()
            self._hosting = False
        try:
            self._udp_sock.close()
        except Exception:
            pass
        self.win.destroy()
        self.app._current_match_dialog = None
        if self.app._last_focused_dialog is self:
            self.app._last_focused_dialog = None
        self.app._start_match_listener()





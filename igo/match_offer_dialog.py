# -*- coding: utf-8 -*-
"""碁華 対局申し込み通知ダイアログ"""
import tkinter as tk
from tkinter import ttk
import socket
import threading
import json
import time as _time

from igo.lang import L, get_language
from igo.window_settings import WindowSettings
from igo.constants import NET_UDP_PORT, BLACK, WHITE
from igo.theme import T
from igo.elo import elo_to_display_rank

# Lazy import: tksheet
Sheet = None
def _ensure_tksheet():
    global Sheet
    if Sheet is None:
        from tksheet import Sheet as _Sheet
        Sheet = _Sheet


class MatchOfferDialog:
    """Popup that lists all incoming match offers on the LAN or cloud."""
    def __init__(self, parent_root, app, first_offer, first_addr, cloud_mode=False):
        self.app = app
        self.parent_root = parent_root
        self._cloud_mode = cloud_mode
        self.win = tk.Toplevel(parent_root)
        self.win.withdraw()  # Hide until positioned
        self.win.title("\u5bfe\u5c40\u306e\u7533\u3057\u8fbc\u307f\u3067\u3059\uff01")
        self._parchment_bg = "#ede0cc"
        self._parchment_light = "#f5efe4"
        self.win.configure(bg=self._parchment_bg)
        self.win.resizable(True, True)
        self.win.transient(parent_root)
        self.win.protocol("WM_DELETE_WINDOW", self._close_all)

        # Restore window size (position is always centered on parent)
        handle = app.current_user["handle_name"] if app.current_user else "default"
        self._ws = WindowSettings(app._ws._db_path, "offer_dialog_{}".format(handle))
        self._saved_size = self._ws.load("geometry")

        # Offers dict: name -> {offer_data, addr, _time}
        self._offers = {}
        self._udp_sock = None
        self._listening = False
        self._taken_listening = False
        self._closed = False
        self._offer_col_widths_set = False

        # Build UI
        bg = self._parchment_bg
        try:
            from igo.teal_banner import TealBanner
            banner_frame = tk.Frame(self.win, bg=bg, height=50)
            banner_frame.pack(fill="x", pady=(6, 8), padx=16)
            banner_frame.pack_propagate(False)
            self._banner = TealBanner(banner_frame,
                text="\u6311\u6226\u72b6\u304c\u5c4a\u3044\u3066\u3044\u307e\u3059\uff01",
                width=420, height=48,
                font_weight="normal",
                text_color=(255, 0, 0),
                text_stroke_color=None,
                bg_edge=(255, 222, 173),
                bg_center=(250, 240, 230),
                border_color=(210, 105, 30),
                border_width=3,
                bg=bg)
            self._banner.pack(fill="both", expand=True)
            # Resize banner when frame width changes
            def _on_banner_resize(event):
                new_w = event.width - 2
                if new_w > 50 and new_w != self._banner._width:
                    self._banner.update_size(new_w, 48)
            banner_frame.bind("<Configure>", _on_banner_resize)
        except Exception as e:
            print("TealBanner error:", e)
            tk.Label(self.win, text="\u6311\u6226\u72b6\u304c\u5c4a\u3044\u3066\u3044\u307e\u3059\uff01",
                     font=("", 14, "bold"), fg=T("accent_gold"), bg=bg).pack(pady=(12, 8))

        # --- Buttons first (side=bottom) so list doesn't push them off ---
        btn_frame = tk.Frame(self.win, bg=bg)
        btn_frame.pack(side="bottom", fill="x", pady=(0, 8), padx=16)

        list_border = tk.Frame(self.win, bd=1, relief="solid", bg="#c4a870")
        list_border.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        list_frame = tk.Frame(list_border, bg=self._parchment_light)
        list_frame.pack(fill="both", expand=True, padx=1, pady=1)
        _ensure_tksheet()
        self.offer_list = Sheet(list_frame,
            headers=["\u5bfe\u5c40\u8005", "\u68cb\u529b", "\u6301\u3061\u6642\u9593", "\u30b3\u30df"], data=[],
            show_x_scrollbar=False, show_y_scrollbar=True,
            show_row_index=False)
        self.offer_list.pack(fill="both", expand=True)
        self.offer_list.set_options(
            table_bg=self._parchment_light, table_fg="#333333",
            grid_color="#d4c4a8",
            header_bg="#e8dcc8", header_fg="#4a3520",
            index_bg="#e8dcc8", index_fg="#4a3520",
            selected_cells_bg="#DCE9F6", selected_cells_fg="#000000",
            selected_rows_bg="#DCE9F6", selected_rows_fg="#000000",
            selected_columns_bg="#DCE9F6", selected_columns_fg="#000000",
        )
        self.offer_list.set_all_row_heights(25)
        try:
            self.offer_list.font(("Yu Gothic UI", 10, "normal"))
            self.offer_list.header_font(("Yu Gothic UI", 10, "normal"))
        except Exception:
            pass
        self.offer_list.enable_bindings()
        self.offer_list.disable_bindings("edit_cell", "edit_header", "edit_index",
            "rc_select", "rc_insert_row", "rc_delete_row",
            "rc_insert_column", "rc_delete_column",
            "copy", "cut", "paste", "undo", "delete")
        # Restore saved column widths or use defaults
        self._ws.restore_column_widths(self.offer_list, 4, [120, 80, 120, 70])
        self._offer_highlighted_row = None
        self.offer_list.extra_bindings("cell_select", self._on_offer_cell_select)
        from igo.glossy_pill_button import GlossyButton as GlossyPillButton
        _lang = get_language()
        _accept_text  = {"ja": "承諾", "en": "Accept",  "zh": "接受", "ko": "수락"}.get(_lang, "承諾")
        _decline_text = {"ja": "辞退", "en": "Decline", "zh": "拒绝", "ko": "거절"}.get(_lang, "辞退")
        _close_text   = {"ja": "閉じる", "en": "Close",  "zh": "关闭", "ko": "닫기"}.get(_lang, "閉じる")
        GlossyPillButton(btn_frame, text=_close_text,
            base_color=(159, 160, 160), text_size=13, width=110, height=32,
            focus_border_color=(89, 88, 87), focus_border_width=2,
            command=self._close_all, bg=bg).pack(side="right", padx=4)
        GlossyPillButton(btn_frame, text=_decline_text,
            base_color=(232, 57, 41), text_size=13, width=110, height=32,
            focus_border_color=(162, 32, 65), focus_border_width=2,
            command=self._decline, bg=bg).pack(side="right", padx=4)
        GlossyPillButton(btn_frame, text=_accept_text,
            base_color=(85, 165, 45), text_size=13, width=110, height=32,
            focus_border_color=(0, 100, 0), focus_border_width=2,
            command=self._accept, bg=bg).pack(side="right", padx=4)

        # Always center on parent, restore size if saved
        self.win.update_idletasks()
        pw = parent_root.winfo_width()
        ph = parent_root.winfo_height()
        px = parent_root.winfo_x()
        py = parent_root.winfo_y()
        if self._saved_size:
            # saved_size is "WxH" or "WxH+X+Y", extract W and H only
            size_part = self._saved_size.split("+")[0]
            parts = size_part.split("x")
            if len(parts) == 2:
                try:
                    dw, dh = int(parts[0]), int(parts[1])
                except ValueError:
                    dw, dh = 440, 420
            else:
                dw, dh = 440, 420
        else:
            dw, dh = 440, 420
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.win.geometry("{}x{}+{}+{}".format(dw, dh, x, y))
        self.win.minsize(440, 420)

        # Add first offer
        self._add_offer(first_offer, first_addr)
        # Show in list with auto-select
        rows = []
        for name, offer in self._offers.items():
            vals = self._format_offer_values(offer)
            rows.append(list(vals))
        self.offer_list.set_sheet_data(rows, redraw=False)
        self._ws.restore_column_widths(self.offer_list, 4, [120, 80, 120, 70])
        def _force_header_color():
            for i in range(4):
                self.offer_list.CH.cell_options[i] = {"highlight": ("#e8dcc8", "#4a3520")}
            self.offer_list.set_options(header_bg="#e8dcc8", header_fg="#4a3520")
            self.offer_list.CH.config(background="#e8dcc8")
            self.offer_list.redraw()
            self.offer_list.deselect()
            if self._offers and self._offer_highlighted_row is None:
                try:
                    self.offer_list.select_row(0)
                    self._offer_highlighted_row = 0
                except Exception:
                    pass
        _force_header_color()
        self.win.after(200, _force_header_color)

        # Start listening for more offers and match_taken
        self._start_udp_listen()
        self._start_taken_listener()
        self._refresh_timer()
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

    def add_cloud_offer(self, offer):
        """Add a new offer from cloud to the existing dialog."""
        name = offer.get("name", "?")
        if name in self._offers:
            self._offers[name]["_time"] = _time.time()
            return
        self._add_offer(offer, None)
        self._refresh_list()

    def _add_offer(self, offer, addr):
        name = offer.get("name", "?")
        offer["_addr"] = addr
        offer["_time"] = _time.time()
        self._offers[name] = offer

    def _format_offer_values(self, offer):
        name = offer.get("name", "?")
        rank = offer.get("rank", "?")
        main_m = offer.get("main_time", 600) // 60
        byo_t = offer.get("byo_time", 30)
        byo_p = offer.get("byo_periods", 5)
        byo_str = "\u221e" if byo_p == 0 else str(byo_p)
        komi = offer.get("komi", 6.5)
        komi_str = "{}\u76ee\u534a".format(int(komi))
        time_str = "{}\u5206+{}\u79d2\u00d7{}".format(main_m, byo_t, byo_str)
        return (name, rank, time_str, komi_str)

    def _refresh_timer(self):
        if self._closed:
            return
        self._refresh_list()
        self.win.after(2000, self._refresh_timer)

    def _refresh_list(self):
        now = _time.time()
        # Remove stale offers: LAN >8s, Cloud >60s (safety net)
        timeout = 60 if self._cloud_mode else 8
        stale = [k for k, v in self._offers.items() if now - v.get("_time", 0) > timeout]
        for k in stale:
            del self._offers[k]
        # Save selection
        sel_name = None
        sel = self.offer_list.get_currently_selected()
        if sel and sel.row is not None:
            old_keys = self._get_display_keys()
            if sel.row < len(old_keys):
                sel_name = old_keys[sel.row]
        # Update sheet
        rows = []
        new_sel_row = None
        for i, (name, offer) in enumerate(self._offers.items()):
            vals = self._format_offer_values(offer)
            rows.append(list(vals))
            if name == sel_name:
                new_sel_row = i
        self.offer_list.set_sheet_data(rows, redraw=False, reset_col_positions=False)
        if not self._offer_col_widths_set:
            self._ws.restore_column_widths(self.offer_list, 4, [120, 80, 120, 70])
            self._offer_col_widths_set = True
        for i in range(4):
            self.offer_list.CH.cell_options[i] = {"highlight": ("#e8dcc8", "#4a3520")}
        self.offer_list.set_options(header_bg="#e8dcc8", header_fg="#4a3520")
        self.offer_list.CH.config(background="#e8dcc8")
        self.offer_list.redraw()
        if new_sel_row is not None:
            self.offer_list.highlight_rows(rows=[new_sel_row], bg="#DCE9F6", fg="#000000")
            self._offer_highlighted_row = new_sel_row
        else:
            self.offer_list.deselect()
            if self._offers:
                try:
                    self.offer_list.select_row(0)
                    self._offer_highlighted_row = 0
                except Exception:
                    pass
        # Auto-close if no offers remain
        if not self._offers:
            self._close()

    def _get_display_keys(self):
        return list(self._offers.keys())

    def _start_udp_listen(self):
        self._listening = True
        try:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            self._udp_sock.settimeout(1.0)
            self._udp_sock.bind(("", NET_UDP_PORT))
            threading.Thread(target=self._udp_recv_loop, daemon=True).start()
        except Exception:
            self._listening = False

    def _udp_recv_loop(self):
        while self._listening:
            try:
                data, addr = self._udp_sock.recvfrom(4096)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "match_offer":
                    my_name = ""
                    if self.app.current_user:
                        my_name = self.app.current_user["handle_name"]
                    sender = msg.get("name", "")
                    if sender != my_name and sender not in self.app._declined_offers:
                        msg["_addr"] = addr[0]
                        msg["_time"] = _time.time()
                        self._offers[sender] = msg
            except socket.timeout:
                continue
            except Exception:
                if self._listening:
                    continue
                return

    def _start_taken_listener(self):
        self._taken_listening = True
        try:
            self._taken_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._taken_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._taken_sock.settimeout(1.0)
            self._taken_sock.bind(("", NET_UDP_PORT + 1))
            threading.Thread(target=self._taken_listen_loop, daemon=True).start()
        except Exception:
            self._taken_listening = False

    def _taken_listen_loop(self):
        while self._taken_listening:
            try:
                data, addr = self._taken_sock.recvfrom(4096)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "match_taken":
                    changed = False
                    for key in ("host_name", "accepter_name"):
                        name = msg.get(key, "")
                        if name and name in self._offers:
                            del self._offers[name]
                            changed = True
                    if changed:
                        try:
                            self.win.after(0, self._refresh_list)
                        except Exception:
                            pass
            except socket.timeout:
                continue
            except Exception:
                if self._taken_listening:
                    continue
                return

    def _decline(self):
        """Decline selected offer and remove from list."""
        keys = list(self._offers.keys())
        if not keys:
            self._close()
            return
        if self._offer_highlighted_row is None:
            return
        idx = self._offer_highlighted_row
        if idx >= len(keys):
            return
        name = keys[idx]
        self.app._declined_offers.add(name)
        del self._offers[name]
        self._offer_highlighted_row = None
        self._refresh_list()
        # Close if no offers remain
        if not self._offers:
            self._close()

    def _on_offer_cell_select(self, event):
        """Highlight selected row."""
        selected_cells = self.offer_list.get_selected_cells()
        if not selected_cells:
            return
        row_idx = list(selected_cells)[0][0]
        if self._offer_highlighted_row is not None:
            self.offer_list.dehighlight_rows(self._offer_highlighted_row)
        self.offer_list.highlight_rows(rows=[row_idx], bg="#DCE9F6", fg="#000000")
        self._offer_highlighted_row = row_idx

    def _accept(self):
        keys = list(self._offers.keys())
        if not keys:
            return
        if self._offer_highlighted_row is None:
            return
        idx = self._offer_highlighted_row
        if idx >= len(keys):
            return
        name = keys[idx]
        offer = self._offers[name]
        self._save_col_widths()
        self._cleanup()
        self.win.destroy()
        if self.app.go_board:
            self.app.go_board._prepare_for_new_game()

        if self._cloud_mode:
            # Cloud mode: send accept via WebSocket
            user = self.app.current_user
            rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
            elo = user["elo_rating"] if user else 0
            self.app._cloud_main_time = offer.get("main_time", 600)
            self.app._cloud_byo_time = offer.get("byo_time", 30)
            self.app._cloud_byo_periods = offer.get("byo_periods", 5)
            self.app._cloud_komi = offer.get("komi", 6.5)
            self.app.send_cloud_message({
                "type": "match_accept",
                "target": name,
                "rank": rank,
                "elo": elo,
            })
        else:
            # LAN mode: TCP connect
            addr = offer.get("_addr", "")
            self.app.join_match(addr, offer, self._on_join_result)

    def _on_join_result(self):
        pass

    def _close_all(self):
        """Close button / X button: decline all offers and close."""
        for name in list(self._offers.keys()):
            self.app._declined_offers.add(name)
        self._close()

    def _save_col_widths(self):
        """Save current column widths and window geometry to DB."""
        try:
            widths = [self.offer_list.column_width(column=i) for i in range(4)]
            self._ws.save("column_widths", widths)
        except Exception:
            pass
        try:
            self._ws.save("geometry", self.win.geometry())
        except Exception:
            pass

    def _close(self):
        self._save_col_widths()
        self._cleanup()
        try:
            self.win.destroy()
        except Exception:
            pass
        self.app._offer_dialog_open = False
        self.app._current_offer_dialog = None
        if self.app._last_focused_dialog is self:
            self.app._last_focused_dialog = None
        self.app._resume_match_listener()

    def _cleanup(self):
        self._closed = True
        self._listening = False
        self._taken_listening = False
        try:
            if self._udp_sock:
                self._udp_sock.close()
        except Exception:
            pass
        try:
            if hasattr(self, "_taken_sock") and self._taken_sock:
                self._taken_sock.close()
        except Exception:
            pass



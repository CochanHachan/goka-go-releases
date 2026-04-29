# -*- coding: utf-8 -*-
"""碁華 対局申し込み通知ダイアログ"""
import logging
import tkinter as tk
from tkinter import ttk
import socket
import threading
import json
import time as _time

from igo.lang import L, get_language
from igo.window_settings import WindowSettings
from igo.constants import NET_UDP_PORT, BLACK, WHITE
from igo.config import get_offer_timeout_ms
from igo.config import get_ui_height_ratio
from igo.config import get_primary_work_area_rect
from igo.theme import T
from igo.elo import elo_to_display_rank
from igo.enums import format_komi_display, format_time_display

logger = logging.getLogger(__name__)

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
        self.win.title(L("title_offer_dialog"))
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
        self._taken_sock = None
        self._listening = False
        self._taken_listening = False
        self._closed = False
        self._offer_col_widths_set = False
        self._refresh_timer_id = None  # after() ID for periodic refresh
        self._display_keys = []  # offer names in display order

        # Build UI
        bg = self._parchment_bg
        try:
            from igo.teal_banner import TealBanner
            banner_frame = tk.Frame(self.win, bg=bg, height=50)
            banner_frame.pack(fill="x", pady=(6, 8), padx=16)
            banner_frame.pack_propagate(False)
            self._banner = TealBanner(banner_frame,
                text=L("offer_arrived"),
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
        except (ImportError, tk.TclError) as e:
            logger.debug("TealBanner unavailable: %s", e)
            tk.Label(self.win, text=L("offer_arrived"),
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
            headers=[L("col_player"), L("col_strength"), L("col_time"), L("col_komi")], data=[],
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
        except (tk.TclError, AttributeError):
            pass  # font not available on this platform
        self.offer_list.enable_bindings()
        self.offer_list.disable_bindings("edit_cell", "edit_header", "edit_index",
            "rc_select", "rc_insert_row", "rc_delete_row",
            "rc_insert_column", "rc_delete_column",
            "copy", "cut", "paste", "undo", "delete")
        # Restore saved column widths or use defaults
        self._ws.restore_column_widths(self.offer_list, 4, [120, 80, 120, 70])
        self._selected_offer_key = None  # offer name, not row index
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
                    dw = int(parts[0])
                except ValueError:
                    dw, dh = 440, 420
            else:
                dw, dh = 440, 420
        else:
            dw, dh = 440, 420
        try:
            wr = get_primary_work_area_rect()
            work_h = wr[3] if wr else max(1, parent_root.winfo_screenheight())
            dh = int(work_h * get_ui_height_ratio("challenge_accept_height", 0.40))
            dh = max(420, dh)
        except Exception:
            pass
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
            if self._offers and self._selected_offer_key is None:
                keys = list(self._offers.keys())
                try:
                    self.offer_list.select_row(0)
                    self._selected_offer_key = keys[0]
                except (tk.TclError, IndexError):
                    pass  # list empty or widget not ready
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
            except tk.TclError:
                pass  # widget destroyed during focus event
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
        komi = offer.get("komi", 7.5)
        komi_str = format_komi_display(komi)
        time_str = format_time_display(
            offer.get("time_control", "byoyomi"),
            offer.get("main_time", 600),
            offer.get("byo_time", 30),
            offer.get("byo_periods", 5),
            fischer_increment=offer.get("fischer_increment", 0),
        )
        return (name, rank, time_str, komi_str)

    def _refresh_timer(self):
        if self._closed:
            return
        self._refresh_list()
        self._refresh_timer_id = self.win.after(2000, self._refresh_timer)

    def _refresh_list(self):
        now = _time.time()
        # Remove stale offers: LAN >8s, Cloud > offer_timeout setting (safety net)
        timeout = (get_offer_timeout_ms() / 1000) if self._cloud_mode else 8
        stale = [k for k, v in self._offers.items() if now - v.get("_time", 0) > timeout]
        for k in stale:
            del self._offers[k]
        # Build display rows, tracking offer keys for selection
        rows = []
        display_keys = []
        new_sel_row = None
        for i, (name, offer) in enumerate(self._offers.items()):
            vals = self._format_offer_values(offer)
            rows.append(list(vals))
            display_keys.append(name)
            if name == self._selected_offer_key:
                new_sel_row = i
        self._display_keys = display_keys
        self.offer_list.set_sheet_data(rows, redraw=False, reset_col_positions=False)
        if not self._offer_col_widths_set:
            self._ws.restore_column_widths(self.offer_list, 4, [120, 80, 120, 70])
            self._offer_col_widths_set = True
        for i in range(4):
            self.offer_list.CH.cell_options[i] = {"highlight": ("#e8dcc8", "#4a3520")}
        self.offer_list.set_options(header_bg="#e8dcc8", header_fg="#4a3520")
        self.offer_list.CH.config(background="#e8dcc8")
        self.offer_list.redraw()
        self.offer_list.deselect()
        if new_sel_row is not None:
            self.offer_list.highlight_rows(rows=[new_sel_row], bg="#DCE9F6", fg="#000000")
        elif display_keys:
            # Auto-select first offer
            try:
                self.offer_list.select_row(0)
                self.offer_list.highlight_rows(rows=[0], bg="#DCE9F6", fg="#000000")
                self._selected_offer_key = display_keys[0]
            except (tk.TclError, IndexError):
                self._selected_offer_key = None
        else:
            self._selected_offer_key = None
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
            except OSError:
                pass  # SO_BROADCAST not supported on this platform
            self._udp_sock.settimeout(1.0)
            self._udp_sock.bind(("", NET_UDP_PORT))
            threading.Thread(target=self._udp_recv_loop, daemon=True).start()
        except OSError:
            logger.debug("Failed to bind UDP socket for offer listener", exc_info=True)
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
                    if sender != my_name and not self.app.is_offer_declined(sender):
                        msg["_addr"] = addr[0]
                        msg["_time"] = _time.time()
                        self._offers[sender] = msg
            except socket.timeout:
                continue
            except (OSError, ValueError, UnicodeDecodeError):
                if self._listening:
                    logger.debug("UDP recv error in offer dialog", exc_info=True)
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
        except OSError:
            logger.debug("Failed to bind taken listener socket", exc_info=True)
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
                        except tk.TclError:
                            pass  # window already destroyed
            except socket.timeout:
                continue
            except (OSError, ValueError, UnicodeDecodeError):
                if self._taken_listening:
                    logger.debug("Taken listener recv error", exc_info=True)
                    continue
                return

    def _decline(self):
        """Decline selected offer and remove from list."""
        if not self._offers:
            self._close()
            return
        if self._selected_offer_key is None:
            return
        name = self._selected_offer_key
        if name not in self._offers:
            return
        self.app.decline_offer(name)
        del self._offers[name]
        self._selected_offer_key = None
        self._refresh_list()
        # Close if no offers remain
        if not self._offers:
            self._close()

    def _on_offer_cell_select(self, event):
        """Highlight selected row and track by offer key."""
        selected_cells = self.offer_list.get_selected_cells()
        if not selected_cells:
            return
        row_idx = list(selected_cells)[0][0]
        if row_idx < len(self._display_keys):
            self._selected_offer_key = self._display_keys[row_idx]
        self.offer_list.deselect()
        self.offer_list.highlight_rows(rows=[row_idx], bg="#DCE9F6", fg="#000000")

    def _accept(self):
        if self._selected_offer_key is None:
            return
        name = self._selected_offer_key
        if name not in self._offers:
            return
        offer = self._offers[name]
        self._save_col_widths()
        self._shutdown(reason="accept")
        if self.app.go_board:
            self.app.go_board._prepare_for_new_game()

        if self._cloud_mode:
            # Cloud mode: send accept via WebSocket
            user = self.app.current_user
            rank = elo_to_display_rank(user["elo_rating"]) if user else "?"
            elo = user["elo_rating"] if user else 0
            self.app.set_cloud_game_params(offer)
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
        self.app.decline_all_offers(self._offers.keys())
        self._close()

    def _save_col_widths(self):
        """Save current column widths and window geometry to DB."""
        try:
            widths = [self.offer_list.column_width(column=i) for i in range(4)]
            self._ws.save("column_widths", widths)
        except (tk.TclError, AttributeError):
            logger.debug("Failed to save offer column widths", exc_info=True)
        try:
            self._ws.save("geometry", self.win.geometry())
        except tk.TclError:
            logger.debug("Failed to save offer dialog geometry", exc_info=True)

    def _close(self):
        """Normal close path: save state, shutdown, notify app."""
        self._save_col_widths()
        self._shutdown(reason="close")

    def _shutdown(self, reason="close"):
        """Consolidated shutdown: stop threads, close sockets, destroy window, notify app.

        reason: 'close' (user closed), 'accept' (offer accepted), 'auto' (no offers left)
        """
        if self._closed:
            return
        self._closed = True
        self._listening = False
        self._taken_listening = False
        # Cancel refresh timer
        if self._refresh_timer_id is not None:
            try:
                self.win.after_cancel(self._refresh_timer_id)
            except tk.TclError:
                pass  # window already destroyed
            self._refresh_timer_id = None
        # Close sockets
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except OSError:
                pass  # socket already closed
        if self._taken_sock:
            try:
                self._taken_sock.close()
            except OSError:
                pass  # socket already closed
        # Destroy window
        try:
            self.win.destroy()
        except tk.TclError:
            pass  # window already destroyed
        self.app.on_offer_dialog_closed(self, reason=reason)

    # --- Public interface for app.py ---

    def remove_offer_by_name(self, name):
        """Remove an offer by sender name. Called from app.py on match_cancelled/match_taken."""
        if name in self._offers:
            del self._offers[name]
            self._refresh_list()

    def get_offers(self):
        """Return a copy of the current offers dict."""
        return dict(self._offers)



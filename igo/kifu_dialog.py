# -*- coding: utf-8 -*-
"""碁華 棋譜ダイアログ"""
import tkinter as tk

from igo.glossy_button import GlossyButton
from igo.lang import L
from igo.constants import BLACK, WHITE
from igo.sgf import _parse_sgf_text
from igo.window_settings import WindowSettings

# Lazy import: tksheet
Sheet = None
def _ensure_tksheet():
    global Sheet
    if Sheet is None:
        from tksheet import Sheet as _Sheet
        Sheet = _Sheet


class KifuDialog:
    """Dialog to browse and replay game records (棋譜)."""

    def __init__(self, parent, app, go_board):
        self.app = app
        self.go_board = go_board
        self._sort_col = None
        self._sort_reverse = True  # newest first by default
        self._highlighted_row = None
        self._records = []  # list of (id, played_at, black_name, white_name, result)

        self._ws = WindowSettings(app._ws._db_path, "kifu_dialog")

        self.dlg = tk.Toplevel(parent)
        self.dlg.title("棋譜一覧")
        self.dlg.transient(parent)
        self.dlg.resizable(True, True)
        app._current_kifu_dialog = self
        app._last_focused_dialog = self
        def _on_focus(e, win=self.dlg, dlg=self, a=app):
            try:
                if e.widget.winfo_toplevel() == win:
                    win.lift()
                    a._last_focused_dialog = dlg
            except Exception:
                pass
        self.dlg.bind("<FocusIn>", _on_focus)

        # Restore saved geometry or center on parent
        saved_geo = self._ws.load("geometry")
        if saved_geo:
            self.dlg.geometry(saved_geo)
        else:
            self.dlg.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_x()
            py = parent.winfo_y()
            w, h = 620, 420
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.dlg.geometry("{}x{}+{}+{}".format(w, h, x, y))

        # Title label
        tk.Label(self.dlg, text="棋譜一覧", font=("", 14, "bold"),
                 fg="#996600").pack(pady=(10, 5))

        # Grid frame
        grid_border = tk.Frame(self.dlg, bd=1, relief="solid", bg="#bfbfbf")
        grid_border.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        list_frame = tk.Frame(grid_border)
        list_frame.pack(fill="both", expand=True, padx=1, pady=1)

        _ensure_tksheet()
        headers = ["棋譜番号", "対局日", "黒番", "白番", "勝敗"]
        self.kifu_list = Sheet(list_frame,
            headers=headers, data=[],
            show_x_scrollbar=False, show_y_scrollbar=True,
            show_row_index=False)
        self.kifu_list.pack(fill="both", expand=True)
        self.kifu_list.set_options(
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
        self.kifu_list.set_all_row_heights(25)
        try:
            self.kifu_list.font(("Yu Gothic UI", 10, "normal"))
            self.kifu_list.header_font(("Yu Gothic UI", 10, "normal"))
        except Exception:
            pass
        self.kifu_list.enable_bindings()
        self.kifu_list.disable_bindings("edit_cell", "edit_header", "edit_index",
            "rc_select", "rc_insert_row", "rc_delete_row",
            "rc_insert_column", "rc_delete_column",
            "copy", "cut", "paste", "undo", "delete")
        self.kifu_list.extra_bindings("cell_select", self._on_cell_select)
        # Header click for sorting
        self.kifu_list.extra_bindings("column_select", self._on_header_click)

        # OK / Close buttons (right-aligned)
        btn_frame = tk.Frame(self.dlg)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        bg_color = btn_frame.cget("bg")
        # デザイン2: 閉じるボタン (right)
        close_btn = GlossyButton(btn_frame,
            text=L("btn_close"), width=100, height=33,
            base_color=(125, 125, 125), text_color="white",
            font=("Yu Gothic UI", 11, "bold"),
            focus_border_width=2, focus_border_color=(89, 84, 85),
            depth=0.7, command=self._close, bg=bg_color)
        close_btn.pack(side="right", padx=(5, 0))
        # デザイン1: 表示ボタン（緑）(left of close)
        ok_btn = GlossyButton(btn_frame,
            text=L("btn_show"), width=100, height=30,
            base_color=(50, 150, 50), text_color="white",
            font=("Yu Gothic UI", 11, "bold"),
            focus_border_width=3, focus_border_color=(40, 120, 40),
            depth=0.7, command=self._on_ok, bg=bg_color)
        ok_btn.pack(side="right")

        self.dlg.protocol("WM_DELETE_WINDOW", self._close)

        # Load data
        self._load_records()

    def _load_records(self):
        """Load game records from DB."""
        if not self.app or not self.app.current_user:
            return
        handle = self.app.current_user["handle_name"]
        rows = self.app.db.get_game_records_for_user(handle)
        self._records = []
        display_rows = []
        for row in rows:
            rec_id = row[0]
            played_at = row[1]
            black_name = row[2]
            white_name = row[3]
            result = row[4]
            self._records.append((rec_id, played_at, black_name, white_name, result))
            kifu_no = "R{:06d}".format(rec_id)
            display_rows.append([kifu_no, played_at, black_name, white_name, result])
        self.kifu_list.set_sheet_data(display_rows, redraw=False)
        self._ws.restore_column_widths(self.kifu_list, 5, [90, 130, 100, 100, 140])
        # Force header color
        def _force_header():
            for i in range(5):
                self.kifu_list.CH.cell_options[i] = {"highlight": ("#f3f3f3", "black")}
            self.kifu_list.set_options(header_bg="#f3f3f3", header_fg="black")
            self.kifu_list.CH.config(background="#f3f3f3")
            self.kifu_list.redraw()
        _force_header()
        self.dlg.after(200, _force_header)

    def _on_cell_select(self, event):
        selected = self.kifu_list.get_selected_cells()
        if not selected:
            return
        row_idx = list(selected)[0][0]
        # Dehighlight previous
        if self._highlighted_row is not None:
            self.kifu_list.dehighlight_rows(self._highlighted_row)
        # Toggle or highlight
        if self._highlighted_row == row_idx:
            self._highlighted_row = None
            return
        self.kifu_list.highlight_rows(rows=[row_idx], bg="#DCE9F6", fg="#000000")
        self._highlighted_row = row_idx

    def _on_ok(self):
        """Load selected kifu and close dialog."""
        if self._highlighted_row is None:
            return
        row_idx = self._highlighted_row
        if row_idx < len(self._records):
            rec_id = self._records[row_idx][0]
            self._load_kifu(rec_id)

    def _load_kifu(self, record_id):
        """Load a game record onto the board and close dialog."""
        sgf_text = self.app.db.get_game_record_sgf(record_id)
        if not sgf_text:
            return
        # Parse SGF from text
        moves, metadata = _parse_sgf_text(sgf_text)
        self.go_board.load_sgf_to_board(moves, metadata)
        self._close()

    def _on_header_click(self, event):
        """Sort by clicked column."""
        selected = self.kifu_list.get_selected_columns()
        if not selected:
            return
        col = list(selected)[0]
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False
        # Sort _records by column
        # columns: 0=id, 1=played_at, 2=black_name, 3=white_name, 4=result
        self._records.sort(key=lambda r: r[col], reverse=self._sort_reverse)
        # Rebuild display
        display_rows = []
        for rec in self._records:
            kifu_no = "R{:06d}".format(rec[0])
            display_rows.append([kifu_no, rec[1], rec[2], rec[3], rec[4]])
        self.kifu_list.set_sheet_data(display_rows, redraw=False, reset_col_positions=False)
        self._highlighted_row = None
        # Force header color - sorted column in light green, others default
        def _force_header():
            for i in range(5):
                if i == col:
                    self.kifu_list.CH.cell_options[i] = {"highlight": ("#e2f0d9", "#217346")}
                else:
                    self.kifu_list.CH.cell_options[i] = {"highlight": ("#f3f3f3", "black")}
            self.kifu_list.set_options(header_bg="#f3f3f3", header_fg="black")
            self.kifu_list.CH.config(background="#f3f3f3")
            self.kifu_list.redraw()
        _force_header()
        self.dlg.after(200, _force_header)

    def _close(self):
        try:
            self._ws.save_window(self.dlg, self.kifu_list, 5)
        except Exception:
            pass
        self.app._current_kifu_dialog = None
        if self.app._last_focused_dialog is self:
            self.app._last_focused_dialog = None
        self.dlg.destroy()


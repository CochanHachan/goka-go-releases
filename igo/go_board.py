# -*- coding: utf-8 -*-
"""碁華 碁盤GUI"""
import logging
import tkinter as tk
from tkinter import messagebox
import os
import threading
import json
import time as _time

from igo.lang import L, get_language

logger = logging.getLogger(__name__)
from igo.constants import (
    BOARD_SIZE, CELL_SIZE, MARGIN, STONE_RADIUS, STAR_RADIUS,
    EMPTY, BLACK, WHITE, STAR_POINTS, TIME_LIMIT,
    NET_UDP_PORT, HAS_CLOUD, API_BASE_URL,
)
from igo.theme import T
from igo.elo import elo_to_display_rank, rank_to_initial_elo
from igo.byoyomi_sound import play_byoyomi_sound, play_byoyomi_start, play_timeout_sound
from igo.game_logic import GoGame, _neighbors
from igo.katago import (
    KataGoGTP, _katago_score, _katago_winrate, calculate_territory_chinese,
)
from igo.rendering import _make_stone_photoimage, _make_board_texture
from igo.sound import _play_stone_sound
from igo.timer import ByoyomiTimer, FischerTimer
from igo.sgf import save_sgf, load_sgf
from igo.network import _net_send


class GoBoard:
    def __init__(self, parent, app=None):
        self.game = GoGame()
        self.parent = parent
        self.app = app
        self.root = parent.winfo_toplevel()

        self.cell_size = CELL_SIZE
        self.margin = MARGIN
        self.stone_radius = STONE_RADIUS
        self._resize_job = None
        self._stone_cache = {}
        self._board_tex = None
        self._board_tex_size = (0, 0)
        self.offset_x = 0
        self.offset_y = 0
        self._timer_running = False
        self._katago_tune_timer_hold = False  # OpenCL autotuning 中のみ True（秒読みカウント停止）
        self.net_mode = False
        self.my_color = None
        self.timer_black = None  # ByoyomiTimer
        self.timer_white = None

        self.black_name = L("player_default")
        self.black_rank = ""
        self.white_name = L("player_default")
        self.white_rank = ""

        # Toolbar (ShogiGUI style, right below menubar)
        if self.app:
            # --- ツールバー ---
            self._toolbar_outer = tk.Frame(parent, bg=parent.cget("bg"))
            self._toolbar_outer.pack(fill="x", padx=6, pady=(10, 4))
            toolbar = tk.Frame(self._toolbar_outer, bg=parent.cget("bg"), bd=0)
            toolbar.pack(fill="x")
            # --- 各列を均等ウェイトで設定（7ボタン分）---
            for _col in range(7):
                toolbar.columnconfigure(_col, weight=1)
            # --- ボタンスタイル ---
            normal_cfg = dict(font=("Meiryo UI", 9), bg="#dcdcdc", fg="#222222",
                              bd=1, relief="solid", padx=12, pady=4,
                              activebackground="#d0d0d0", activeforeground="#111111",
                              disabledforeground="#a0a0a0", cursor="hand2",
                              highlightthickness=0)
            primary_cfg = dict(normal_cfg)
            # --- ボタン配置（gridで横のみ均等拡張）---
            tk.Button(toolbar, text=L("btn_game"), command=self._open_match_dialog,
                      **primary_cfg).grid(row=0, column=0, sticky="ew", padx=(0, 2))
            self.resign_btn = tk.Button(toolbar, text=L("btn_resign"),
                      command=self._resign, state="disabled", **normal_cfg)
            self.resign_btn.grid(row=0, column=1, sticky="ew", padx=2)
            self.pass_btn = tk.Button(toolbar, text=L("btn_pass"),
                      command=self._pass_turn, state="disabled", **normal_cfg)
            self.pass_btn.grid(row=0, column=2, sticky="ew", padx=2)
            self.score_btn = tk.Button(toolbar, text=L("btn_score"),
                      command=self._calculate_score, state="disabled", **normal_cfg)
            self.score_btn.grid(row=0, column=3, sticky="ew", padx=2)
            self.kifu_btn = tk.Button(toolbar, text=L("btn_kifu"), command=self._open_kifu_dialog,
                      **normal_cfg)
            self.kifu_btn.grid(row=0, column=4, sticky="ew", padx=2)
            self.reset_btn = tk.Button(toolbar, text=L("btn_reset"),
                      command=lambda: self.app._reset_to_initial(), **normal_cfg)
            self.reset_btn.grid(row=0, column=5, sticky="ew", padx=2)
            tk.Button(toolbar, text=L("btn_logout"), command=self._logout,
                      **primary_cfg).grid(row=0, column=6, sticky="ew", padx=(2, 0))

        # --- Top bar: Player panels ---
        self.top_frame = tk.Frame(parent, bg=T("root_bg"))
        self.top_frame.pack(fill="x", padx=6, pady=(10, 4))

        # Use grid for 50:50 split
        self.top_frame.columnconfigure(0, weight=1, uniform="panel")
        self.top_frame.columnconfigure(1, weight=1, uniform="panel")

        # Black player panel (left)
        self.black_panel = tk.Frame(self.top_frame, bg=T("container_bg"), bd=0,
                                     highlightbackground=T("panel_highlight"),
                                     highlightthickness=2)
        self.black_panel.grid(row=0, column=0, padx=(0, 3), sticky="nsew")

        bp_top = tk.Frame(self.black_panel, bg=T("container_bg"))
        bp_top.pack(fill="x", padx=8, pady=(3, 0))

        panel_bg = T("panel_bg_rgb")
        self._panel_black_img = _make_stone_photoimage(self.root, 10, True, panel_bg)
        tk.Label(bp_top, image=self._panel_black_img,
                 bg=T("container_bg")).pack(side="left", padx=(0, 5))
        self.black_name_label = tk.Label(
            bp_top, text=self.black_name, font=("Yu Gothic UI", 12, "bold"),
            fg=T("text_primary"), bg=T("container_bg"), anchor="w")
        self.black_name_label.pack(side="left")
        self.black_rank_label = tk.Label(
            bp_top, text=self.black_rank, font=("Yu Gothic UI", 10, "bold"),
            fg=T("rank_fg"), bg=T("container_bg"), anchor="w")
        self.black_rank_label.pack(side="left", padx=(4, 0))

        self.black_cap_label = tk.Label(
            bp_top, text="\u2191 0", font=("Yu Gothic UI", 10),
            fg=T("cap_fg"), bg=T("container_bg"))
        self.black_cap_label.pack(side="right")

        bp_bottom = tk.Frame(self.black_panel, bg=T("container_bg"), height=38)
        bp_bottom.pack(fill="x", padx=8, pady=(0, 2))
        bp_bottom.pack_propagate(False)
        self.black_time_label = tk.Label(
            bp_bottom, text="00:00", font=("Yu Gothic UI", 18, "bold"),
            fg=T("timer_active"), bg=T("container_bg"), anchor="w")
        self.black_time_label.pack(side="left")
        self._komi = 7.5
        self._rules = "japanese"
        self.komi_label = tk.Label(
            bp_bottom, text="", font=("Yu Gothic UI", 9),
            fg=T("text_disabled"), bg=T("container_bg"), anchor="e")
        self.komi_label.pack(side="right")
        self.black_winrate_label = tk.Label(
            bp_bottom, text="", font=("Yu Gothic UI", 11, "bold"),
            fg="#4CAF50", bg=T("container_bg"), anchor="e")
        self.black_winrate_label.pack(side="right", padx=(0, 0))

        # White player panel (right)
        self.white_panel = tk.Frame(self.top_frame, bg=T("container_bg"), bd=0,
                                     highlightbackground=T("panel_inactive"),
                                     highlightthickness=2)
        self.white_panel.grid(row=0, column=1, padx=(3, 0), sticky="nsew")

        wp_top = tk.Frame(self.white_panel, bg=T("container_bg"))
        wp_top.pack(fill="x", padx=8, pady=(3, 0))

        self.white_cap_label = tk.Label(
            wp_top, text="\u2191 0", font=("Yu Gothic UI", 10),
            fg=T("cap_fg"), bg=T("container_bg"))
        self.white_cap_label.pack(side="left")

        self.white_rank_label = tk.Label(
            wp_top, text=self.white_rank, font=("Yu Gothic UI", 10, "bold"),
            fg=T("rank_fg"), bg=T("container_bg"), anchor="e")
        self.white_rank_label.pack(side="right", padx=(4, 0))
        self.white_name_label = tk.Label(
            wp_top, text=self.white_name, font=("Yu Gothic UI", 12, "bold"),
            fg=T("text_primary"), bg=T("container_bg"), anchor="e")
        self.white_name_label.pack(side="right")
        self._panel_white_img = _make_stone_photoimage(self.root, 10, False, panel_bg)
        tk.Label(wp_top, image=self._panel_white_img,
                 bg=T("container_bg")).pack(side="right", padx=(0, 5))

        wp_bottom = tk.Frame(self.white_panel, bg=T("container_bg"), height=38)
        wp_bottom.pack(fill="x", padx=8, pady=(0, 2))
        wp_bottom.pack_propagate(False)
        self.white_time_label = tk.Label(
            wp_bottom, text="00:00", font=("Yu Gothic UI", 18, "bold"),
            fg=T("timer_inactive"), bg=T("container_bg"), anchor="e")
        self.white_time_label.pack(side="right")
        self.white_winrate_label = tk.Label(
            wp_bottom, text="", font=("Yu Gothic UI", 11, "bold"),
            fg="#4CAF50", bg=T("container_bg"), anchor="w")
        self.white_winrate_label.pack(side="left", padx=(8, 0))

        # Navigation bar for kifu replay (initially hidden, packed side=bottom BEFORE canvas)
        self._reviewing = False
        self._review_mode = False
        self._replay_index = 0
        self._replay_history = []
        self.nav_frame = tk.Frame(parent, bg=T("root_bg"))
        self._nav_inner = tk.Frame(self.nav_frame, bg=T("root_bg"))
        nav_inner = self._nav_inner
        # nav_inner is NOT packed yet (hidden until show_nav_bar)
        # Load navigation button images
        _img_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._nav_images = {}
        _nav_img_names = [
            ("first", "nav_first.png"),
            ("prevX", "nav_prevX.png"),
            ("prev",  "nav_prev.png"),
            ("auto",  "nav_auto.png"),
            ("next",  "nav_next.png"),
            ("nextX", "nav_nextX.png"),
            ("last",  "nav_last.png"),
        ]
        for key, fname in _nav_img_names:
            path = os.path.join(_img_dir, fname)
            if os.path.exists(path):
                self._nav_images[key] = tk.PhotoImage(file=path)
            else:
                self._nav_images[key] = None
        # Also load stop image
        stop_path = os.path.join(_img_dir, "nav_stop.png")
        if os.path.exists(stop_path):
            self._nav_images["stop"] = tk.PhotoImage(file=stop_path)
        else:
            self._nav_images["stop"] = None
        nav_btn_cfg = dict(bg=T("root_bg"), activebackground=T("hover_bg"),
                           relief="flat", bd=0, cursor="hand2")
        _cmds = [
            ("first", self._nav_first),
            ("prevX", self._nav_prev20),
            ("prev",  self._nav_prev),
            ("auto",  self._auto_toggle),
            ("next",  self._nav_next),
            ("nextX", self._nav_next20),
            ("last",  self._nav_last),
        ]
        _fallback = ["\u23ee", "\u23ea", "\u25c0", "Auto", "\u25b6", "\u23e9", "\u23ed"]
        self._nav_buttons = []
        for i, (key, cmd) in enumerate(_cmds):
            img = self._nav_images.get(key)
            if img:
                btn = tk.Button(nav_inner, image=img, command=cmd, **nav_btn_cfg)
            else:
                btn = tk.Button(nav_inner, text=_fallback[i], command=cmd,
                                font=("", 12), fg=T("text_primary"), **nav_btn_cfg)
            btn.pack(side="left", padx=1)
            self._nav_buttons.append(btn)
            if key == "auto":
                self._auto_btn = btn
                self._auto_btn_index = i

        # Speed (seconds per move) - use App's shared variable if available
        if self.app and hasattr(self.app, '_auto_speed_var'):
            self._auto_speed_var = self.app._auto_speed_var
        else:
            self._auto_speed_var = tk.StringVar(value="2")

        # Auto-play state
        self._auto_playing = False
        self._auto_play_after_id = None
        # nav_frame uses place() to sit right below the board
        # (pack with expand=True canvas would push it to window bottom)

        # Board canvas
        self.canvas = tk.Canvas(parent, bg=T("root_bg"), highlightthickness=0)
        self.canvas.pack(expand=True, fill="both", padx=0, pady=0)

        self._stone_ids = {}
        self._last_move_marker = None  # canvas item id for last move marker
        self._last_move_pos = None     # (bx, by) of last move
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", self.on_click)


        self.root.after(50, self._initial_draw)

    def _logout(self):
        self._timer_running = False
        if self.app:
            self.app._cancel_hosting_if_active()
            self.app._save_geometry()
            self.app._stop_match_listener()
            self.app._update_online_status(False)
            self.app._disconnect_cloud()
            self.app.root.destroy()

    def set_players(self, black_name="", black_rank="",
                    white_name="", white_rank=""):
        if black_name:
            self.black_name = black_name
            self.black_name_label.config(text=black_name)
        if black_rank:
            self.black_rank = black_rank
            self.black_rank_label.config(text=black_rank)
        if white_name:
            self.white_name = white_name
            self.white_name_label.config(text=white_name)
        if white_rank:
            self.white_rank = white_rank
            self.white_rank_label.config(text=white_rank)

    # --- Timer ---

    def _start_timer(self):
        if not self._timer_running:
            self._timer_running = True
            self._timer_gen = getattr(self, '_timer_gen', 0) + 1
            self._tick(self._timer_gen)

    def _tick(self, gen=None):
        # 世代カウンターで古いコールバックを無視する。
        # _start_timer() が呼ばれるたびに _timer_gen がインクリメントされ、
        # 旧世代の root.after コールバックは自動的に無効化される。
        if gen is not None and gen != getattr(self, '_timer_gen', 0):
            return
        if self.game.game_over or not self._timer_running:
            return
        # KataGo OpenCL 初回チューニング中は持ち時間を進めない（承諾直後から読み始める仕様の例外）
        if getattr(self, "_katago_tune_timer_hold", False):
            self.root.after(1000, self._tick, getattr(self, '_timer_gen', 0))
            return
        if self.timer_black and self.timer_white:
            # ByoyomiTimer mode
            if self.game.current_player == BLACK:
                alive = self.timer_black.tick()
                if not alive:
                    self.game.time_out(BLACK)
                    self._update_time_display()
                    self._play_byoyomi_if_enabled(None, is_timeout=True)
                    if self.net_mode and self.app:
                        self.app.send_net_message({"type": "timeout", "player": "black"})
                    self._show_time_out(BLACK)
                    return
                self._play_byoyomi_if_enabled(self.timer_black)
            else:
                alive = self.timer_white.tick()
                if not alive:
                    self.game.time_out(WHITE)
                    self._update_time_display()
                    self._play_byoyomi_if_enabled(None, is_timeout=True)
                    if self.net_mode and self.app:
                        self.app.send_net_message({"type": "timeout", "player": "white"})
                    self._show_time_out(WHITE)
                    return
                self._play_byoyomi_if_enabled(self.timer_white)
        else:
            # Legacy simple timer
            if self.game.current_player == BLACK:
                self.game.time_black -= 1
                if self.game.time_black <= 0:
                    self.game.time_black = 0
                    self.game.time_out(BLACK)
                    self._update_time_display()
                    self._show_time_out(BLACK)
                    return
            else:
                self.game.time_white -= 1
                if self.game.time_white <= 0:
                    self.game.time_white = 0
                    self.game.time_out(WHITE)
                    self._update_time_display()
                    self._show_time_out(WHITE)
                    return
        self._update_time_display()
        self.root.after(1000, self._tick, getattr(self, '_timer_gen', 0))

    def _format_time(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return "{:d}:{:02d}".format(m, s)

    def _update_time_display(self):
        is_black_turn = self.game.current_player == BLACK
        if self.timer_black and self.timer_white:
            bt_text = self.timer_black.display_text()
            wt_text = self.timer_white.display_text()
            self.black_time_label.config(text=bt_text)
            self.white_time_label.config(text=wt_text)
            # Font size: smaller for byoyomi text
            bf = ("Yu Gothic UI", 12, "bold") if self.timer_black.in_byoyomi else ("Yu Gothic UI", 22, "bold")
            wf = ("Yu Gothic UI", 12, "bold") if self.timer_white.in_byoyomi else ("Yu Gothic UI", 22, "bold")
            self.black_time_label.config(font=bf)
            self.white_time_label.config(font=wf)
            # Colors
            if is_black_turn:
                bfg = T("timer_byoyomi") if self.timer_black.in_byoyomi else T("timer_active")
                wfg = T("timer_inactive")
            else:
                bfg = T("timer_inactive")
                wfg = T("timer_byoyomi") if self.timer_white.in_byoyomi else T("timer_active")
            self.black_time_label.config(fg=bfg)
            self.white_time_label.config(fg=wfg)
        else:
            # タイマー未設定（対局前/初期化後）は00:00表示
            if self.timer_black is None or self.timer_white is None:
                self.black_time_label.config(
                    text="00:00", font=("Yu Gothic UI", 18, "bold"),
                    fg=T("timer_inactive"))
                self.white_time_label.config(
                    text="00:00", font=("Yu Gothic UI", 18, "bold"),
                    fg=T("timer_inactive"))
            else:
                bt = self.game.time_black
                wt = self.game.time_white
                self.black_time_label.config(text=self._format_time(bt))
                self.white_time_label.config(text=self._format_time(wt))
                if is_black_turn:
                    self.black_time_label.config(fg=T("timer_active"))
                    self.white_time_label.config(fg=T("timer_inactive"))
                else:
                    self.black_time_label.config(fg=T("timer_inactive"))
                    self.white_time_label.config(fg=T("timer_active"))
                if bt <= 30:
                    self.black_time_label.config(fg=T("timer_byoyomi"))
                if wt <= 30:
                    self.white_time_label.config(fg=T("timer_byoyomi"))
        if is_black_turn:
            self.black_panel.config(highlightbackground=T("panel_highlight"))
            self.white_panel.config(highlightbackground=T("panel_inactive"))
        else:
            self.black_panel.config(highlightbackground=T("panel_inactive"))
            self.white_panel.config(highlightbackground=T("panel_highlight"))

    def _play_byoyomi_if_enabled(self, timer, is_timeout=False):
        """秒読み設定がオンの場合、音声を再生する。
        持ち時間中は読まない。秒読みフェーズに入ってから読む。
        フィッシャーの場合は残り10秒以下でカウントダウン音声を再生。"""
        if self.app and not getattr(self.app, '_byoyomi_voice_enabled', True):
            return
        if is_timeout:
            play_timeout_sound()
            return
        if timer is None:
            return
        # フィッシャータイマーの場合：残り10秒以下でカウントダウン
        if isinstance(timer, FischerTimer):
            if timer.remaining <= 10:
                play_byoyomi_sound(timer.remaining)
            return
        # 秒読みフェーズのみ音声を再生
        if timer.in_byoyomi:
            # 秒読み開始の瞬間を検知（byo_remaining がフルリセットされた直後）
            if not getattr(timer, '_byoyomi_start_announced', False):
                timer._byoyomi_start_announced = True
                play_byoyomi_start()
                return  # 開始アナウンスだけ再生、秒数は次のtickから
            play_byoyomi_sound(timer.byo_remaining)

    def _show_time_out(self, loser):
        """Show timeout result - called on the side whose clock ran out."""
        self._timer_running = False
        winner_color = WHITE if loser == BLACK else BLACK
        # Determine if I won or lost
        if self.net_mode and self.my_color == winner_color:
            # I won - opponent timed out
            if self.my_color == BLACK:
                opp_name = getattr(self, "white_name", L("opponent_default"))
            else:
                opp_name = getattr(self, "black_name", L("opponent_default"))
            msg = L("timeout_opponent", opp_name)
        elif self.net_mode:
            msg = L("timeout_self")
        else:
            winner = L("color_white") if loser == BLACK else L("color_black")
            msg = L("timeout_winner", winner)
        # Save game record before closing network
        if self.app:
            result = "白時間切れ勝ち" if winner_color == WHITE else "黒時間切れ勝ち"
            self.app._save_game_record(result)
        # Close network before messagebox
        self._timeout_disconnect = True
        if self.app and self.app._net_game:
            self.app._net_game.stop()
            self.app._net_game = None
        self.end_network_game()
        def _after_timeout_ok():
            if self.app:
                self.app._update_elo_after_game(winner_color)
            self.show_nav_bar()
        self._show_centered_msgbox(L("timeout_title"), msg, callback=_after_timeout_ok)

    # --- Drawing ---

    def _initial_draw(self):
        self._recalc_sizes()
        self._build_stone_images()
        self._full_redraw()

    def _on_canvas_configure(self, event):
        if event.width < 10 or event.height < 10:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(150, self._handle_resize)

    def _handle_resize(self):
        self._resize_job = None
        old_cell = self.cell_size
        self._recalc_sizes()
        if self.cell_size != old_cell:
            self._build_stone_images()
        self._align_panels()
        self._full_redraw()
        self._position_nav_bar()

    def _align_panels(self):
        cs = self.cell_size
        pad = cs // 2 + 4
        board_w = (BOARD_SIZE - 1) * cs + 2 * pad
        try:
            win_w = self.root.winfo_width()
        except tk.TclError:
            return  # window not yet realized
        side_pad = max(6, (win_w - board_w) // 2)
        self.top_frame.pack_configure(padx=side_pad)
        if hasattr(self, '_toolbar_outer'):
            self._toolbar_outer.pack_configure(padx=side_pad)

    def _recalc_sizes(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        usable = min(w, h)
        self.cell_size = max(12, usable // (BOARD_SIZE + 1))
        board_span = self.cell_size * (BOARD_SIZE - 1)
        self.margin = (usable - board_span) // 2
        self.offset_x = (w - (self.margin * 2 + board_span)) // 2
        # Push board to top: offset by negative half margin
        self.offset_y = -(self.margin // 2)
        self.stone_radius = max(6, int(self.cell_size * 0.50))
        self.star_radius = max(2, int(self.cell_size * 0.08))

    def _build_stone_images(self):
        r = self.stone_radius
        if r in self._stone_cache:
            self._black_img, self._white_img = self._stone_cache[r]
            return
        board_bg = T("board_bg_rgb")
        self._black_img = _make_stone_photoimage(self.root, r, True, board_bg)
        self._white_img = _make_stone_photoimage(self.root, r, False, board_bg)
        self._stone_cache[r] = (self._black_img, self._white_img)

    def _full_redraw(self):
        self.canvas.delete("all")
        self._stone_ids = {}
        self._last_move_marker = None
        self._draw_grid()
        for by in range(BOARD_SIZE):
            for bx in range(BOARD_SIZE):
                color = self.game.board[by][bx]
                if color != EMPTY:
                    cx = self.offset_x + self.margin + bx * self.cell_size
                    cy = self.offset_y + self.margin + by * self.cell_size
                    self._draw_stone(bx, by, cx, cy, color)
        # Redraw last move marker
        if self._last_move_pos:
            lx, ly = self._last_move_pos
            stone_color = self.game.board[ly][lx]
            if stone_color != EMPTY:
                self._draw_last_move_marker(lx, ly, stone_color)

    def _draw_grid(self):
        m = self.margin
        cs = self.cell_size
        ox = self.offset_x
        oy = self.offset_y
        pad = cs // 2 + 4
        bx0 = ox + m - pad
        by0 = oy + m - pad
        bx1 = ox + m + (BOARD_SIZE - 1) * cs + pad
        by1 = oy + m + (BOARD_SIZE - 1) * cs + pad
        tex_w = bx1 - bx0
        tex_h = by1 - by0
        if tex_w > 0 and tex_h > 0:
            if self._board_tex_size != (tex_w, tex_h):
                self._board_tex = _make_board_texture(self.root, tex_w, tex_h)
                self._board_tex_size = (tex_w, tex_h)
            self.canvas.create_image(bx0, by0, image=self._board_tex, anchor="nw")
            self.canvas.create_rectangle(bx0, by0, bx1, by1,
                fill="", outline=T("board_outline"), width=2)
        for i in range(BOARD_SIZE):
            x = ox + m + i * cs
            y0 = oy + m
            y1 = oy + m + (BOARD_SIZE - 1) * cs
            self.canvas.create_line(x, y0, x, y1, fill=T("grid_line"))
        for i in range(BOARD_SIZE):
            y = oy + m + i * cs
            x0 = ox + m
            x1 = ox + m + (BOARD_SIZE - 1) * cs
            self.canvas.create_line(x0, y, x1, y, fill=T("grid_line"))
        sr = self.star_radius
        for sx, sy in STAR_POINTS:
            cx = ox + m + sx * cs
            cy = oy + m + sy * cs
            self.canvas.create_oval(
                cx - sr, cy - sr, cx + sr, cy + sr, fill=T("grid_line"))

    def on_click(self, event):
        # Overlay check
        if getattr(self, "_resign_overlay_visible", False):
            current = self.canvas.find_withtag("current")
            if current and "resign_overlay_button" in self.canvas.gettags(current[0]):
                self._hide_overlay()
            return
        # Only allow clicks during: network game (own turn) or review mode
        review_mode = getattr(self, '_review_mode', False)
        if review_mode:
            pass  # Allow free play
        elif self.net_mode:
            # Network game: only on own turn
            if self.my_color is not None and self.game.current_player != self.my_color:
                return
        else:
            # Not in game and not in review mode: don't allow
            return
        if self.game.game_over:
            return
        m = self.margin
        cs = self.cell_size
        ox = self.offset_x
        oy = self.offset_y
        bx = round((event.x - ox - m) / cs)
        by = round((event.y - oy - m) / cs)
        if not (0 <= bx < BOARD_SIZE and 0 <= by < BOARD_SIZE):
            return
        cx = ox + m + bx * cs
        cy = oy + m + by * cs
        dist = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
        if dist > cs * 0.45:
            return
        player = self.game.current_player
        ok, captured = self.game.place_stone(bx, by)
        if not ok:
            return
        # Skip timer/network in review mode
        if review_mode:
            # Update replay history for nav button navigation
            self._replay_history = list(self.game.move_history)
            self._replay_index = len(self._replay_history)
        else:
            # Notify ByoyomiTimer of move
            if self.timer_black and player == BLACK:
                self.timer_black.on_move()
            if self.timer_white and player == WHITE:
                self.timer_white.on_move()
            if not self._timer_running:
                self._start_timer()
            # Send move to network
            if self.net_mode and self.app:
                self.app.send_net_message({"type": "move", "x": bx, "y": by})
        for rx, ry in captured:
            key = (rx, ry)
            if key in self._stone_ids:
                self.canvas.delete(self._stone_ids[key])
                del self._stone_ids[key]
        self._draw_stone(bx, by, cx, cy, player)
        self._draw_last_move_marker(bx, by, player)
        _play_stone_sound()
        self._update_time_display()
        self.black_cap_label.config(
            text="\u2191 {}".format(self.game.captured_black))
        self.white_cap_label.config(
            text="\u2191 {}".format(self.game.captured_white))
        # Update win rate after each move
        self._update_winrate()
        # Sync button state after turn change
        self._sync_turn_buttons()

    def _draw_stone(self, bx, by, cx, cy, player):
        img = self._black_img if player == BLACK else self._white_img
        item_id = self.canvas.create_image(cx, cy, image=img, anchor="center")
        self._stone_ids[(bx, by)] = item_id

    def _draw_last_move_marker(self, bx, by, player):
        """Draw a square marker on the last played stone."""
        # Remove previous marker
        if self._last_move_marker is not None:
            try:
                self.canvas.delete(self._last_move_marker)
            except tk.TclError:
                pass  # canvas item already deleted
            self._last_move_marker = None
        self._last_move_pos = (bx, by)
        cx = self.offset_x + self.margin + bx * self.cell_size
        cy = self.offset_y + self.margin + by * self.cell_size
        # Square size: ~18% of cell size (half-side length)
        s = max(int(self.cell_size * 0.15), 2)
        # Color: white marker on black stone, black marker on white stone
        color = "#FFFFFF" if player == BLACK else "#000000"
        self._last_move_marker = self.canvas.create_rectangle(
            cx - s, cy - s, cx + s, cy + s,
            fill=color, outline=color, width=1)

    def handle_network_move(self, x, y):
        """Apply a move received from the network."""
        player = self.game.current_player
        ok, captured = self.game.place_stone(x, y)
        if not ok:
            return
        if player == BLACK and self.timer_black:
            self.timer_black.on_move()
        if player == WHITE and self.timer_white:
            self.timer_white.on_move()
        if not self._timer_running:
            self._start_timer()
        cx = self.offset_x + self.margin + x * self.cell_size
        cy = self.offset_y + self.margin + y * self.cell_size
        for rx, ry in captured:
            key = (rx, ry)
            if key in self._stone_ids:
                self.canvas.delete(self._stone_ids[key])
                del self._stone_ids[key]
        self._draw_stone(x, y, cx, cy, player)
        self._draw_last_move_marker(x, y, player)
        _play_stone_sound()
        self._update_time_display()
        self.black_cap_label.config(
            text="\u2191 {}".format(self.game.captured_black))
        self.white_cap_label.config(
            text="\u2191 {}".format(self.game.captured_white))
        # Update win rate after network move
        self._update_winrate()
        # Sync button state after turn change
        self._sync_turn_buttons()

    def _show_temp_overlay(self, text, duration=2000):
        """Show a temporary message overlay on the board that fades after duration ms."""
        self.canvas.update_idletasks()
        cx = self.canvas.winfo_width() // 2
        cy = self.canvas.winfo_height() // 2
        if cx < 10 or cy < 10:
            return
        tag = "_temp_overlay"
        bg = self.canvas.create_rectangle(
            cx - 200, cy - 30, cx + 200, cy + 30,
            fill="#000000", stipple="gray50", outline="",
            tags=tag)
        txt = self.canvas.create_text(
            cx, cy, text=text, fill="#ffffff",
            font=("", 18, "bold"), tags=tag)
        self.canvas.tag_raise(tag)
        def _remove():
            try:
                self.canvas.delete(tag)
            except tk.TclError:
                pass  # canvas or tag already gone
        self.root.after(duration, _remove)

    def set_katago_tune_timer_hold(self, hold):
        """True の間は _tick が持ち時間を減らさない（KataGo OpenCL autotuning 専用）。"""
        self._katago_tune_timer_hold = bool(hold)

    def set_katago_init_overlay(self, message):
        """盤面下端の KataGo 初期化メッセージ。文言は igo/lang.py のキー経由で渡すこと。None/空で消去。"""
        tag = "katago_init_overlay"
        try:
            self.canvas.delete(tag)
        except tk.TclError:
            return
        if not message:
            return

        def _paint(attempt=0):
            self.canvas.update_idletasks()
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w < 40 or h < 40:
                # 対局開始直後は canvas の winfo がまだ 1x1 等のことがあり、無言で return していた
                if attempt < 60:
                    self.root.after(50, lambda: _paint(attempt + 1))
                return
            pad_x = 16
            y1 = h - 52
            y2 = h - 12
            self.canvas.create_rectangle(
                pad_x, y1, w - pad_x, y2,
                fill="#1a1a1a", outline="", stipple="",
                tags=tag)
            self.canvas.create_text(
                w // 2, (y1 + y2) // 2,
                text=message,
                fill="#f5f5f5",
                font=("Meiryo", 11, "bold"),
                tags=tag,
                width=w - pad_x * 2 - 8,
            )
            self.canvas.tag_raise(tag)

        self.root.after(0, lambda: _paint(0))

    def handle_network_pass(self):
        """Handle pass from network opponent."""
        # Show pass notification
        if self.my_color == BLACK:
            opp_name = getattr(self, "white_name", L("opponent_default"))
        else:
            opp_name = getattr(self, "black_name", L("opponent_default"))
        self._show_temp_overlay(L("opponent_passed", opp_name), duration=5000)
        # Grant Fischer increment (or reset byoyomi) for the opponent who passed
        opp_color = self.game.current_player
        if opp_color == BLACK and self.timer_black:
            self.timer_black.on_move()
        if opp_color == WHITE and self.timer_white:
            self.timer_white.on_move()
        self.game.pass_turn()
        self._update_time_display()
        # Sync button state after turn change
        self._sync_turn_buttons()
        if self.game.game_over:
            self._timer_running = False
            self._pass_disconnect = True
            self.end_network_game()
            # Delay score calculation so pass notification is visible
            self._delayed_score_after_id = self.root.after(3000, self._calculate_score)

    def handle_network_timeout(self, loser_color):
        """Handle timeout notification from network opponent."""
        # If the game already ended (local timer also fired), ignore duplicate
        if self.game.game_over:
            return
        self.game.time_out(loser_color)
        self._timer_running = False
        winner_color = WHITE if loser_color == BLACK else BLACK
        if self.my_color == winner_color:
            if self.my_color == BLACK:
                opp_name = getattr(self, "white_name", L("opponent_default"))
            else:
                opp_name = getattr(self, "black_name", L("opponent_default"))
            msg = L("timeout_opponent", opp_name)
        else:
            msg = L("timeout_self")
        # Save game record before closing network
        if self.app:
            result = "白時間切れ勝ち" if winner_color == WHITE else "黒時間切れ勝ち"
            self.app._save_game_record(result)
        self._timeout_disconnect = True
        if self.app and self.app._net_game:
            self.app._net_game.stop()
            self.app._net_game = None
        self.end_network_game()
        def _after_timeout_ok2():
            if self.app:
                self.app._update_elo_after_game(winner_color)
            self.show_nav_bar()
        self._show_centered_msgbox(L("timeout_title"), msg, callback=_after_timeout_ok2)

    def handle_network_resign(self, loser_color):
        """Handle resignation from network opponent."""
        self.game.resign(loser_color)
        self._timer_running = False
        # Determine opponent name
        if self.my_color == BLACK:
            opp_name = getattr(self, "white_name", L("opponent_default"))
        else:
            opp_name = getattr(self, "black_name", L("opponent_default"))
        # Save game record before closing network
        winner_color = BLACK if loser_color == WHITE else WHITE
        if self.app:
            result = "白中押し勝ち" if winner_color == WHITE else "黒中押し勝ち"
            self.app._save_game_record(result)
        # Close network before messagebox to suppress disconnect msg
        self._resign_disconnect = True
        if self.app and self.app._net_game:
            self.app._net_game.stop()
            self.app._net_game = None
        self.end_network_game()
        def _after_resign_ok():
            if self.app:
                self.app._update_elo_after_game(winner_color)
            self.show_nav_bar()
        self._show_centered_msgbox(L("resign_title"),
            L("resign_opponent", opp_name),
            callback=_after_resign_ok)

    def setup_network_game(self, my_color, main_time, byo_time, byo_periods, komi=7.5,
                           time_control="byoyomi", fischer_increment=10, delay_timer=False):
        """Initialize board for network play.

        delay_timer=True のときはタイマーを起動しない（レガシー互換用。通常は承諾直後に起動）。
        """
        self._katago_tune_timer_hold = False
        self.net_mode = True
        self.my_color = my_color
        self._komi = komi
        self._rules = "chinese"
        self._time_control = time_control
        if time_control == "fischer":
            self.timer_black = FischerTimer(main_time, fischer_increment)
            self.timer_white = FischerTimer(main_time, fischer_increment)
        else:
            self.timer_black = ByoyomiTimer(main_time, byo_time, byo_periods)
            self.timer_white = ByoyomiTimer(main_time, byo_time, byo_periods)
        self.game = GoGame()
        self._full_redraw()
        self._update_time_display()
        self._update_komi_label()
        # AI対局時は KataGo 初期化完了まで待ってから _start_timer() を呼ぶ
        if not delay_timer:
            self._start_timer()
        # Enable buttons based on whose turn it is (black goes first)
        is_my_turn = (my_color == BLACK)
        btn_state = "normal" if is_my_turn else "disabled"
        if hasattr(self, "pass_btn"):
            self.pass_btn.config(state=btn_state)
            self.resign_btn.config(state=btn_state)
        if hasattr(self, "score_btn"):
            self.score_btn.config(state="disabled")
        # Cancel any pending delayed score calculation from previous game
        if hasattr(self, '_delayed_score_after_id') and self._delayed_score_after_id:
            self.root.after_cancel(self._delayed_score_after_id)
            self._delayed_score_after_id = None
        # Ensure overlay is cleared and normal click binding is restored
        self._hide_overlay()
        self.canvas.bind("<Button-1>", self.on_click)
        if self.app:
            self.app._sync_game_menu_state()

    def _sync_turn_buttons(self):
        """Enable resign/pass buttons only on my turn during network game."""
        if not self.net_mode or self.game.game_over:
            return
        is_my_turn = self.my_color is not None and self.game.current_player == self.my_color
        state = "normal" if is_my_turn else "disabled"
        if hasattr(self, "pass_btn"):
            self.pass_btn.config(state=state)
        if hasattr(self, "resign_btn"):
            self.resign_btn.config(state=state)
        if self.app:
            self.app._sync_game_menu_state()

    def end_network_game(self):
        """Clean up after network game ends."""
        # Only save color/elo if not already saved (prevent overwrite by duplicate calls)
        if self.my_color is not None:
            self._last_my_color = self.my_color
        if hasattr(self, 'opponent_elo') and self.opponent_elo is not None:
            self._last_opponent_elo = self.opponent_elo
        self.net_mode = False
        self.my_color = None
        self._timer_running = False
        if hasattr(self, "pass_btn"):
            self.pass_btn.config(state="disabled")
            self.resign_btn.config(state="disabled")
        if hasattr(self, "score_btn"):
            self.score_btn.config(state="normal")
        if hasattr(self, "kifu_btn"):
            self.kifu_btn.config(state="normal")
        if self.app:
            self.app._ai_cleanup()
            self.app._sync_game_menu_state()

    def _update_komi_label(self):
        """Update komi display - now shown in title bar, so clear panel label."""
        self.komi_label.config(text="")

    def _calculate_score(self):
        """Calculate territory using KataGo and show result."""
        from tkinter import messagebox as _mb
        # Cancel any pending delayed score callback
        if hasattr(self, '_delayed_score_after_id') and self._delayed_score_after_id:
            self.root.after_cancel(self._delayed_score_after_id)
            self._delayed_score_after_id = None
        # Guard against double calls
        if hasattr(self, '_score_progress') and self._score_progress:
            return
        # Remove pass notification overlay before showing progress dialog
        try:
            self.canvas.delete("_temp_overlay")
        except tk.TclError:
            pass  # overlay already removed
        self.score_btn.config(state="disabled")
        # Show progress centered on main window
        self._score_progress = tk.Toplevel(self.root)
        self._score_progress.title(L("score_title"))
        self._score_progress.resizable(False, False)
        self._score_progress.transient(self.root)
        self._score_progress.grab_set()
        tk.Label(self._score_progress, text=L("score_calculating"),
                 font=("", 12)).pack(expand=True, padx=20, pady=20)
        self._score_progress.update_idletasks()
        pw = self._score_progress.winfo_reqwidth()
        ph = self._score_progress.winfo_reqheight()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = rx + (rw - pw) // 2
        y = ry + (rh - ph) // 2
        self._score_progress.geometry("+{}+{}".format(x, y))
        self._score_progress.update()

        def run_katago():
            try:
                winner, result_text = calculate_territory_chinese(
                    self.game.board, self._komi, self.game.move_history,
                    self._rules)
                self.root.after(0, lambda: self._show_score_result(winner, result_text))
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning("KataGo scoring failed", exc_info=True)
                self.root.after(0, lambda: self._show_score_result(None, str(e)))

        t = threading.Thread(target=run_katago, daemon=True)
        t.start()

    def _show_score_result(self, winner, result_text):
        """Show scoring result (called from main thread)."""
        from tkinter import messagebox as _mb
        if hasattr(self, '_score_progress') and self._score_progress:
            self._score_progress.destroy()
            self._score_progress = None
        if winner is None:
            _mb.showerror(L("msg_error"), L("msg_score_fail", result_text))
            self.score_btn.config(state="normal")
            return
        self.score_btn.config(state="normal")
        if winner == "\u5f15\u304d\u5206\u3051":
            msg = result_text
        else:
            msg = "{}\u306e{}".format(winner, result_text)
        # Save game record (score result)
        if self.app and getattr(self, '_last_my_color', None) is not None:
            self.app._save_game_record(msg)
        # Show result as overlay on board (same as resign/timeout)
        def _after_score_ok():
            # Update Elo if this was a network game result
            if self.app and hasattr(self, '_last_my_color') and self._last_my_color is not None:
                if winner == "\u9ed2":
                    self.app._update_elo_after_game(BLACK)
                elif winner == "\u767d":
                    self.app._update_elo_after_game(WHITE)
                else:
                    self.app._update_elo_after_game(None)
            # Stop match listener after scoring
            if self.app:
                self.app._stop_match_listener()
        self._show_centered_msgbox(L("score_title"), msg, callback=_after_score_ok)
        # Ensure nav bar stays visible
        if not self._reviewing:
            self.show_nav_bar()

    def _open_match_dialog(self):
        if self.app:
            if self.app._current_match_dialog:
                try:
                    self.app._current_match_dialog.win.lift()
                    self.app._last_focused_dialog = self.app._current_match_dialog
                except tk.TclError:
                    pass  # match dialog window destroyed
                return
            # 挑戦状ダイアログが開いていれば、オファーを退避してから閉じる
            _pending_offers = {}
            if self.app._current_offer_dialog:
                try:
                    _pending_offers = self.app._current_offer_dialog.get_offers()
                except (AttributeError, TypeError):
                    logger.debug("Failed to copy pending offers", exc_info=True)
                try:
                    self.app._current_offer_dialog._close()
                except tk.TclError:
                    logger.debug("Failed to close offer dialog", exc_info=True)
            self._prepare_for_new_game()
            self.app._stop_match_listener()
            from igo.match_dialog import MatchDialog as _MD
            self.app._current_match_dialog = _MD(self.root, self.app)
            # 退避したオファーを申請ダイアログに引き継ぐ
            for name, offer in _pending_offers.items():
                self.app._current_match_dialog.add_cloud_offer(offer)

    def _prepare_for_new_game(self):
        """対局開始前の共通処理：棋譜クリア・棋譜選択画面を閉じる・ボタン状態リセット。"""
        # Cancel any pending delayed score calculation
        if hasattr(self, '_delayed_score_after_id') and self._delayed_score_after_id:
            self.root.after_cancel(self._delayed_score_after_id)
            self._delayed_score_after_id = None
        # 棋譜選択画面を閉じる
        if self.app and self.app._current_kifu_dialog:
            try:
                self.app._current_kifu_dialog._close()
            except tk.TclError:
                logger.debug("Failed to close kifu dialog", exc_info=True)
        # 棋譜をクリアして盤面をリセット
        self.hide_nav_bar()
        self._reviewing = False
        self.game = GoGame()
        self._full_redraw()
        # ボタン状態
        if hasattr(self, 'kifu_btn'):
            self.kifu_btn.config(state="disabled")
        if hasattr(self, 'score_btn'):
            self.score_btn.config(state="disabled")

    def _open_kifu_dialog(self):
        if self.app:
            from igo.kifu_dialog import KifuDialog as _KD
            _KD(self.root, self.app, self)

    def _pass_turn(self):
        if not self.net_mode or self.game.game_over:
            return
        if self.game.current_player != self.my_color:
            return
        # Grant Fischer increment (or reset byoyomi) before pass_turn switches the player
        player = self.game.current_player
        if player == BLACK and self.timer_black:
            self.timer_black.on_move()
        if player == WHITE and self.timer_white:
            self.timer_white.on_move()
        self.game.pass_turn()
        self._update_time_display()
        if self.app:
            self.app.send_net_message({"type": "pass"})
        # Sync button state after turn change
        self._sync_turn_buttons()
        if self.game.game_over:
            self._timer_running = False
            self._pass_disconnect = True
            self.end_network_game()
            # Delay score calculation so opponent can see pass notification
            self._delayed_score_after_id = self.root.after(3000, self._calculate_score)

    def _resign(self):
        if not self.net_mode or self.game.game_over:
            return
        self._show_resign_confirm()

    def _show_resign_confirm(self):
        """Show resign confirmation dialog on the board canvas."""
        cx = self.canvas.winfo_width() // 2
        cy = self.canvas.winfo_height() // 2
        # Dark overlay background
        bg_rect = self.canvas.create_rectangle(
            cx - 160, cy - 60, cx + 160, cy + 60,
            fill="#000000", stipple="gray50", outline="")
        border_rect = self.canvas.create_rectangle(
            cx - 160, cy - 60, cx + 160, cy + 60,
            fill="", outline="#ffffff", width=2)
        msg_text = self.canvas.create_text(
            cx, cy - 20,
            text=L("resign_confirm"),
            font=("", 18, "bold"), fill="#ffffff", anchor="center")
        # Yes/No buttons as canvas widgets
        btn_frame = tk.Frame(self.canvas, bg="#333333")
        yes_btn = tk.Button(btn_frame, text=L("resign_yes"),
            font=("", 12, "bold"), bg="#cc4444", fg="#ffffff",
            activebackground="#aa2222", relief="flat", padx=20, pady=4)
        yes_btn.pack(side="left", padx=(0, 12))
        no_btn = tk.Button(btn_frame, text=L("resign_no"),
            font=("", 12, "bold"), bg="#666666", fg="#ffffff",
            activebackground="#444444", relief="flat", padx=20, pady=4)
        no_btn.pack(side="left")
        btn_win = self.canvas.create_window(cx, cy + 25, window=btn_frame)
        confirm_items = [bg_rect, border_rect, msg_text, btn_win]
        def _cleanup():
            for item in confirm_items:
                try:
                    self.canvas.delete(item)
                except tk.TclError:
                    pass  # canvas item already deleted
        def _on_yes():
            _cleanup()
            self.game.resign(self.my_color)
            self._timer_running = False
            if self.app:
                self.app.send_net_message({"type": "resign"})
            loser = self.my_color
            winner_color = BLACK if loser == WHITE else WHITE
            # Save game record
            if self.app:
                result = "白中押し勝ち" if winner_color == WHITE else "黒中押し勝ち"
                self.app._save_game_record(result)
            self.end_network_game()
            if self.app:
                self.app._update_elo_after_game(winner_color)
            self.show_nav_bar()
        def _on_no():
            _cleanup()
        yes_btn.config(command=_on_yes)
        no_btn.config(command=_on_no)


    def _show_centered_msgbox(self, title, message, callback=None):
        """Show overlay message centered on the board canvas."""
        canvas = self.canvas
        canvas.update_idletasks()
        # Remove existing overlay if any
        self._hide_overlay()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        panel_w = 360
        panel_h = 160
        x1 = (w - panel_w) // 2
        y1 = (h - panel_h) // 2
        x2 = x1 + panel_w
        y2 = y1 + panel_h
        overlay_tag = "msg_overlay"
        button_tag = "msg_overlay_button"
        # Dark semi-transparent background
        canvas.create_rectangle(
            0, 0, w, h,
            fill="gray20", stipple="gray50", outline="",
            tags=overlay_tag)
        # Center panel
        canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="white", outline="black", width=2,
            tags=overlay_tag)
        # Title
        canvas.create_text(
            w // 2, y1 + 30,
            text=title,
            font=("Meiryo", 16, "bold"), fill="black",
            tags=overlay_tag)
        # Message lines
        lines = message.split("\n")
        line_y = y1 + 68
        for line in lines:
            canvas.create_text(
                w // 2, line_y,
                text=line,
                font=("Meiryo", 13, "bold"), fill="black",
                tags=overlay_tag)
            line_y += 30
        # OK button
        bx1 = w // 2 - 50
        by1 = y2 - 42
        bx2 = w // 2 + 50
        by2 = y2 - 12
        canvas.create_rectangle(
            bx1, by1, bx2, by2,
            fill="#e8e8e8", outline="black", width=1,
            tags=(overlay_tag, button_tag))
        canvas.create_text(
            w // 2, (by1 + by2) // 2,
            text="OK",
            font=("Meiryo", 11, "bold"), fill="black",
            tags=(overlay_tag, button_tag))
        canvas.tag_raise(overlay_tag)
        self._overlay_tag = overlay_tag
        self._overlay_button_tag = button_tag
        self._overlay_visible = True
        self._overlay_callback = callback
        # Bind click to dismiss overlay
        canvas.bind("<Button-1>", self._on_overlay_click)

    def _on_overlay_click(self, event):
        """Handle click while overlay is visible."""
        if not getattr(self, "_overlay_visible", False):
            return
        # Check if OK button was clicked
        current = self.canvas.find_withtag("current")
        if current:
            tags = self.canvas.gettags(current[0])
            if "msg_overlay_button" in tags:
                self._hide_overlay()
                return
        # Also dismiss if clicking anywhere on the overlay
        if current:
            tags = self.canvas.gettags(current[0])
            if "msg_overlay" in tags:
                return  # Click on panel but not button - ignore
        # Click outside overlay - ignore

    def _hide_overlay(self):
        """Remove the overlay from the canvas."""
        if getattr(self, "_overlay_visible", False):
            self.canvas.delete(self._overlay_tag)
            self._overlay_visible = False
            # Restore normal click binding
            self.canvas.bind("<Button-1>", self.on_click)
            # Execute callback if set
            cb = getattr(self, "_overlay_callback", None)
            self._overlay_callback = None
            if cb:
                cb()

    def show_nav_bar(self):
        """Show the navigation bar and enter review mode."""
        self._reviewing = True
        self._review_mode = False
        self._replay_history = list(self.game.move_history)
        self._replay_index = len(self._replay_history)
        self._nav_inner.pack(anchor="center")
        self._position_nav_bar()
        # リサイズ時にナビバー位置を追従させる
        if not hasattr(self, '_nav_configure_bound'):
            self.canvas.bind("<Configure>", self._on_nav_reposition, add="+")
            self._nav_configure_bound = True
        if self.app:
            self.app._send_status("検討中")
            self.app._sync_game_menu_state()

    def _on_nav_reposition(self, event=None):
        """キャンバスリサイズ時にナビバー位置を更新。"""
        if self._reviewing:
            self.root.after_idle(self._position_nav_bar)

    def hide_nav_bar(self):
        """Hide the navigation bar and exit review mode."""
        if self._auto_playing:
            self._auto_stop()
        self._reviewing = False
        self._replay_index = 0
        self._replay_history = []
        self._nav_inner.pack_forget()
        self.nav_frame.place_forget()
        # Reset status from "検討中" back to "ログイン"
        if self.app:
            self.app._send_status("ログイン")

    def _position_nav_bar(self):
        """Position nav_frame right below the board, following board position."""
        if not self._reviewing:
            return
        # 碁盤の下端を計算（グリッド最下行 + 半マージン）
        grid_bottom_y = self.offset_y + self.margin + (BOARD_SIZE - 1) * self.cell_size
        board_bottom_y = grid_bottom_y + self.margin // 2  # 碁盤に近づける
        # キャンバスの親内での位置
        canvas_y = self.canvas.winfo_y()
        y = canvas_y + board_bottom_y + 10  # 碁盤との間隔
        # ウィンドウ下端からはみ出さないよう制限
        try:
            parent_h = self.canvas.master.winfo_height()
            nav_h = self.nav_frame.winfo_reqheight() or 30
            max_y = parent_h - nav_h - 2
            if y > max_y:
                y = max_y
        except tk.TclError:
            pass  # widget not yet realized
        self.nav_frame.place(relx=0.5, y=y, anchor="n")
        self.nav_frame.lift()

    def _replay_to(self, index):
        """Replay moves from start to the given index and redraw."""
        self._replay_index = max(0, min(index, len(self._replay_history)))
        # Build a fresh game and replay
        g = GoGame()
        for i in range(self._replay_index):
            action, player, x, y = self._replay_history[i]
            if action == "move":
                g.current_player = player
                g.place_stone(x, y)
            elif action == "pass":
                g.current_player = player
                g.pass_turn()
        # Replace current game state for display
        old_history = self._replay_history
        self.game = g
        self._full_redraw()
        self.black_cap_label.config(text="\u2191 {}".format(g.captured_black))
        self.white_cap_label.config(text="\u2191 {}".format(g.captured_white))
        self._replay_history = old_history
        # Update win rate for current position
        self._update_winrate(list(self._replay_history[:self._replay_index]))

    def _update_winrate(self, move_history=None):
        """Update win rate display using KataGo analysis in background."""
        # Check if winrate display is enabled
        if self.app and not getattr(self.app, '_show_winrate', True):
            self.black_winrate_label.config(text="")
            self.white_winrate_label.config(text="")
            return
        # Skip during auto-play to prevent process accumulation
        if getattr(self, '_auto_playing', False):
            return
        # Prevent multiple concurrent KataGo processes
        if getattr(self, '_winrate_running', False):
            return
        if move_history is None:
            move_history = self.game.move_history
        if not move_history:
            self.black_winrate_label.config(text="")
            self.white_winrate_label.config(text="")
            return
        self._winrate_running = True
        komi = getattr(self, '_komi', 7.5)
        def _run():
            try:
                bwr, wwr = _katago_winrate(move_history, komi=komi,
                                                       rules=self._rules)
                if bwr is not None:
                    self.root.after(0, lambda: self._display_winrate(bwr, wwr))
            except (OSError, RuntimeError, ValueError):
                logger.debug("KataGo winrate calculation failed", exc_info=True)
            finally:
                self._winrate_running = False
        threading.Thread(target=_run, daemon=True).start()

    def _display_winrate(self, black_wr, white_wr):
        """Display win rate on the panel labels."""
        if black_wr >= white_wr:
            self.black_winrate_label.config(text="{:.1f}%".format(black_wr), fg="#ff4500")
            self.white_winrate_label.config(text="{:.1f}%".format(white_wr), fg="#008000")
        else:
            self.black_winrate_label.config(text="{:.1f}%".format(black_wr), fg="#008000")
            self.white_winrate_label.config(text="{:.1f}%".format(white_wr), fg="#ff4500")

    def _nav_first(self):
        self._replay_to(0)

    def _nav_prev(self):
        self._replay_to(self._replay_index - 1)

    def _nav_prev20(self):
        self._replay_to(self._replay_index - 20)

    def _nav_next(self):
        self._replay_to(self._replay_index + 1)

    def _nav_next20(self):
        self._replay_to(self._replay_index + 20)

    def _nav_last(self):
        self._replay_to(len(self._replay_history))

    def _auto_toggle(self):
        """Toggle auto-play on/off."""
        if self._auto_playing:
            self._auto_stop()
        else:
            self._auto_play_start()

    def _auto_play_start(self):
        """Start auto-play from current position."""
        if self._auto_playing:
            return
        self._auto_playing = True
        # Disable all nav buttons except Auto (which becomes Stop)
        for i, btn in enumerate(self._nav_buttons):
            if i == self._auto_btn_index:
                # Switch to Stop image
                stop_img = self._nav_images.get("stop")
                if stop_img:
                    btn.config(image=stop_img)
                else:
                    btn.config(text="Stop")
            else:
                btn.config(state="disabled")
        self._auto_play_step()

    def _auto_play_step(self):
        """Advance one move and schedule next."""
        if not self._auto_playing:
            return
        if self._replay_index >= len(self._replay_history):
            self._auto_stop()
            return
        self._replay_to(self._replay_index + 1)
        try:
            delay = int(float(self._auto_speed_var.get()) * 1000)
        except (ValueError, tk.TclError):
            delay = 2000
        if delay < 500:
            delay = 500
        self._auto_play_after_id = self.root.after(delay, self._auto_play_step)

    def _auto_stop(self):
        """Stop auto-play."""
        self._auto_playing = False
        if self._auto_play_after_id:
            self.root.after_cancel(self._auto_play_after_id)
            self._auto_play_after_id = None
        # Re-enable all nav buttons, switch Auto back
        for i, btn in enumerate(self._nav_buttons):
            if i == self._auto_btn_index:
                auto_img = self._nav_images.get("auto")
                if auto_img:
                    btn.config(image=auto_img)
                else:
                    btn.config(text="Auto")
            btn.config(state="normal")

    def load_sgf_to_board(self, moves, metadata):
        """Load SGF data and show on board with nav bar."""
        # Reset
        self.game = GoGame()
        self.net_mode = False
        self.my_color = None
        self._timer_running = False
        if hasattr(self, "pass_btn"):
            self.pass_btn.config(state="disabled")
            self.resign_btn.config(state="disabled")
        # Set player info
        bn = metadata.get("PB", "\u9ed2")
        wn = metadata.get("PW", "\u767d")
        br = metadata.get("BR", "")
        wr = metadata.get("WR", "")
        self.set_players(black_name=bn, black_rank=br,
                         white_name=wn, white_rank=wr)
        # Set komi from SGF metadata
        try:
            self._komi = float(metadata.get("KM", "6.5"))
        except (ValueError, TypeError):
            self._komi = 6.5
        self._update_komi_label()
        # Set rules from SGF metadata (default: japanese)
        ru = metadata.get("RU", "").lower()
        if "chinese" in ru or "china" in ru:
            self._rules = "chinese"
        else:
            self._rules = "japanese"
        if hasattr(self, "score_btn"):
            self.score_btn.config(state="normal")
        # Replay all moves
        for action, player, x, y in moves:
            if action == "move":
                self.game.current_player = player
                self.game.place_stone(x, y)
            elif action == "pass":
                self.game.current_player = player
                self.game.pass_turn()
        self._full_redraw()
        self.black_cap_label.config(text="\u2191 {}".format(self.game.captured_black))
        self.white_cap_label.config(text="\u2191 {}".format(self.game.captured_white))
        self._update_time_display()
        # Show nav bar
        self._replay_history = list(self.game.move_history)
        self._replay_index = len(self._replay_history)
        self._reviewing = True
        self._nav_inner.pack(anchor="center")
        self._position_nav_bar()

    def _show_board_overlay(self, text):
        """Show overlay button on the board. Click to reset and allow new match."""
        cx = self.canvas.winfo_width() // 2
        cy = self.canvas.winfo_height() // 2
        # Dark background rectangle
        bg_rect = self.canvas.create_rectangle(
            cx - 200, cy - 35, cx + 200, cy + 35,
            fill="#000000", stipple="gray50", outline="")
        # Clickable button
        btn = tk.Button(self.canvas, text=text,
            font=("", 20, "bold"), fg="#ffffff", bg="#333333",
            activeforeground="#ffffff", activebackground="#555555",
            relief="flat", padx=24, pady=8, cursor="hand2")
        btn_win = self.canvas.create_window(cx, cy, window=btn)
        def _on_click():
            try:
                self.canvas.delete(bg_rect)
                self.canvas.delete(btn_win)
            except tk.TclError:
                pass  # canvas items already deleted
            self._after_game_end()
        btn.config(command=_on_click)

    def _after_game_end(self):
        """Called after game result overlay is clicked. Keep stones, show nav bar."""
        # Close network connection
        if self.app and self.app._net_game:
            self.app._net_game.stop()
            self.app._net_game = None
        # Disable game controls but keep stones
        self.end_network_game()
        # Show navigation bar for kifu review
        self.show_nav_bar()


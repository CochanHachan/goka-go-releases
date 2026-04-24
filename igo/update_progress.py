# -*- coding: utf-8 -*-
"""碁華 アップデート中アニメーション（独立モジュール）"""
import tkinter as tk


# ── カラーパレット ──────────────────────────────
_BG        = "#000000"
_FG        = "#E0E0E0"
_ACCENT    = "#D4A645"
_LINE_CLR  = "#D4A645"
_RING_BG   = "#1A1A1A"   # リング背景（暗いグレー）
_FONT      = "Yu Gothic UI"
_BTN_PRI   = "#8B2020"
_BTN_PRI_H = "#A52A2A"
_BTN_SEC   = "#1A2A5C"
_BTN_SEC_H = "#253A7A"
_BTN_FG    = "#FFFFFF"

# ── アニメーション設定 ──────────────────────────
_RING_SIZE   = 80         # リングの直径
_RING_WIDTH  = 6          # リングの太さ
_ARC_EXTENT  = 90         # 弧の長さ（度）
_INTERVAL    = 30         # 更新間隔（ms）
_SPEED       = 6          # 回転速度（度/フレーム）
_DOT_INTERVAL = 500       # ドットアニメーション間隔（ms）


def show_update_progress(parent=None):
    """アップデート中のアニメーションダイアログを表示する。

    Parameters
    ----------
    parent : tk.Tk or tk.Toplevel, optional
        親ウィンドウ。None の場合は独立ウィンドウとして表示。

    Returns
    -------
    dict
        win : tk.Toplevel  ダイアログウィンドウ
        set_status(text) : ステータステキストを変更する関数
        close() : ダイアログを閉じる関数
    """
    win = tk.Toplevel(parent)
    win.title("アップデート中")
    win.configure(bg=_BG)
    win.withdraw()
    win.protocol("WM_DELETE_WINDOW", lambda: None)  # 閉じるボタン無効
    win.minsize(250, 0)  # タイトルバー文字が途切れないように最小幅を設定

    outer = tk.Frame(win, bg=_BG, padx=40, pady=30)
    outer.pack(fill="both", expand=True)

    # ── 上ライン ─────────────────────────────────
    tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(0, 20))

    # ── スピナーキャンバス ────────────────────────
    canvas_size = _RING_SIZE + 20
    canvas = tk.Canvas(outer, width=canvas_size, height=canvas_size,
                       bg=_BG, highlightthickness=0, bd=0)
    canvas.pack(pady=(0, 16))

    cx = canvas_size // 2
    cy = canvas_size // 2
    r = _RING_SIZE // 2
    pad = _RING_WIDTH // 2

    # 背景リング（暗いグレーの円）
    canvas.create_oval(cx - r + pad, cy - r + pad,
                       cx + r - pad, cy + r - pad,
                       outline=_RING_BG, width=_RING_WIDTH)

    # 回転する弧
    arc = canvas.create_arc(cx - r + pad, cy - r + pad,
                            cx + r - pad, cy + r - pad,
                            start=0, extent=_ARC_EXTENT,
                            outline=_ACCENT, width=_RING_WIDTH,
                            style="arc")

    # ── テキスト ─────────────────────────────────
    text_label = tk.Label(outer, text="アップデート中です",
                          font=(_FONT, 14, "bold"),
                          fg=_ACCENT, bg=_BG)
    text_label.pack(pady=(0, 6))

    status_label = tk.Label(outer, text="ダウンロード中...",
                            font=(_FONT, 13),
                            fg=_FG, bg=_BG)
    status_label.pack(pady=(0, 4))

    # ── ドットアニメーション用 ────────────────────
    dot_count = [0]
    base_text = ["ダウンロード中"]

    # ── 下ライン ─────────────────────────────────
    tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(16, 0))

    # ── アニメーション制御 ────────────────────────
    angle = [0]
    running = [True]

    def _rotate():
        if not running[0]:
            return
        try:
            angle[0] = (angle[0] + _SPEED) % 360
            canvas.itemconfigure(arc, start=angle[0])
            win.after(_INTERVAL, _rotate)
        except tk.TclError:
            pass  # ウィンドウ破棄後のコールバックを安全に無視

    def _animate_dots():
        if not running[0]:
            return
        try:
            dot_count[0] = (dot_count[0] + 1) % 4
            dots = "." * dot_count[0]
            status_label.config(text="{}{}".format(base_text[0], dots))
            win.after(_DOT_INTERVAL, _animate_dots)
        except tk.TclError:
            pass  # ウィンドウ破棄後のコールバックを安全に無視

    def set_status(text):
        try:
            base_text[0] = text
            dot_count[0] = 0
            status_label.config(text=text)
        except tk.TclError:
            pass

    def show_complete():
        """アニメーションを停止し、完了メッセージを表示する。"""
        running[0] = False
        try:
            win.title("アップデート完了")
            canvas.delete("all")
            # チェックマーク（✓）を描画
            cx2 = canvas_size // 2
            cy2 = canvas_size // 2
            r2 = _RING_SIZE // 2
            canvas.create_oval(cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2,
                               outline=_ACCENT, width=2)
            canvas.create_line(cx2 - 16, cy2 + 2,
                               cx2 - 4, cy2 + 14,
                               cx2 + 20, cy2 - 14,
                               fill=_ACCENT, width=4, smooth=False)
            text_label.config(text="アップデート完了")
            status_label.config(text="アップデートは正常に終了しました。")
        except tk.TclError:
            pass

    def close():
        running[0] = False
        try:
            win.destroy()
        except tk.TclError:
            pass

    # ── 画面中央に表示 ───────────────────────────
    def _finalize():
        try:
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
            _rotate()
            _animate_dots()
        except tk.TclError:
            pass

    win.after(100, _finalize)

    return {"win": win, "set_status": set_status,
            "show_complete": show_complete, "close": close}


def show_update_available_prompt(
    parent,
    current_version,
    new_version,
    release_notes="",
    on_confirm=None,
    on_later=None,
):
    """新バージョン検知時にスピナー付き画面を出し、「はい」で on_confirm、後回しで on_later。

    本番ユーザー向け: 起動直後からアニメーションが回り、はいを押すとダウンロード〜再起動まで進む。
    """
    win = tk.Toplevel(parent)
    win.title("アップデート")
    win.configure(bg=_BG)
    win.withdraw()

    outer = tk.Frame(win, bg=_BG, padx=36, pady=28)
    outer.pack(fill="both", expand=True)

    tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(0, 16))

    tk.Label(
        outer,
        text="新しいバージョンがあります",
        font=(_FONT, 15, "bold"),
        fg=_ACCENT,
        bg=_BG,
    ).pack(anchor="center")
    tk.Label(
        outer,
        text="「はい」でダウンロードとインストールが始まります",
        font=(_FONT, 12),
        fg=_FG,
        bg=_BG,
    ).pack(anchor="center", pady=(6, 16))

    canvas_size = _RING_SIZE + 20
    canvas = tk.Canvas(outer, width=canvas_size, height=canvas_size,
                       bg=_BG, highlightthickness=0, bd=0)
    canvas.pack(pady=(0, 12))

    cx = canvas_size // 2
    cy = canvas_size // 2
    r = _RING_SIZE // 2
    pad = _RING_WIDTH // 2
    canvas.create_oval(
        cx - r + pad, cy - r + pad, cx + r - pad, cy + r - pad,
        outline=_RING_BG, width=_RING_WIDTH,
    )
    arc = canvas.create_arc(
        cx - r + pad, cy - r + pad, cx + r - pad, cy + r - pad,
        start=0, extent=_ARC_EXTENT,
        outline=_ACCENT, width=_RING_WIDTH,
        style="arc",
    )

    tk.Label(
        outer,
        text="現在 : {}  →  最新 : {}".format(current_version, new_version),
        font=(_FONT, 12),
        fg=_FG,
        bg=_BG,
    ).pack(anchor="center", pady=(0, 8))

    notes = (release_notes or "").strip()
    if notes:
        if len(notes) > 280:
            notes = notes[:277] + "..."
        tk.Label(
            outer,
            text=notes,
            font=(_FONT, 10),
            fg=_FG,
            bg=_BG,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

    tk.Frame(outer, bg=_LINE_CLR, height=2).pack(fill="x", pady=(8, 16))

    btn_row = tk.Frame(outer, bg=_BG)
    btn_row.pack()

    angle = [0]
    running = [True]

    def _rotate():
        if not running[0]:
            return
        try:
            angle[0] = (angle[0] + _SPEED) % 360
            canvas.itemconfigure(arc, start=angle[0])
            win.after(_INTERVAL, _rotate)
        except tk.TclError:
            pass

    def _stop_anim():
        running[0] = False

    def _yes():
        _stop_anim()
        try:
            win.destroy()
        except tk.TclError:
            pass
        if on_confirm:
            on_confirm()

    def _later():
        _stop_anim()
        try:
            win.destroy()
        except tk.TclError:
            pass
        if on_later:
            on_later()

    yes_btn = tk.Button(
        btn_row,
        text="はい",
        font=(_FONT, 13, "bold"),
        fg=_BTN_FG,
        bg=_BTN_PRI,
        activeforeground=_BTN_FG,
        activebackground=_BTN_PRI_H,
        highlightthickness=0,
        bd=0,
        padx=28,
        pady=10,
        cursor="hand2",
        command=_yes,
    )
    yes_btn.pack(side="left", padx=(0, 14))

    no_btn = tk.Button(
        btn_row,
        text="後でする",
        font=(_FONT, 12),
        fg=_BTN_FG,
        bg=_BTN_SEC,
        activeforeground=_BTN_FG,
        activebackground=_BTN_SEC_H,
        highlightthickness=0,
        bd=0,
        padx=22,
        pady=10,
        cursor="hand2",
        command=_later,
    )
    no_btn.pack(side="left")

    win.protocol("WM_DELETE_WINDOW", _later)

    def _finalize():
        try:
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
            _rotate()
        except tk.TclError:
            pass

    win.after(100, _finalize)

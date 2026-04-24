#!/usr/bin/env python3
"""碁華 ログイン画面

添付画像を再現した Tkinter ログインフォームです。
glossy_button.py と同じフォルダに置いて実行してください。

使い方:
    python login_form.py
"""
import tkinter as tk
from tkinter import messagebox
from glossy_button import GlossyButton


# =====================================================================
# RoundedEntry — 角丸の入力フィールド（フォーカスで枠線色変化）
# =====================================================================

class RoundedEntry(tk.Canvas):
    """角丸の入力フィールド（Canvas + Entry）。

    Parameters
    ----------
    master : widget
        親ウィジェット。
    width : int
        フィールド全体の幅（ピクセル）。
    height : int
        フィールド全体の高さ（ピクセル）。
    corner_radius : int
        角丸の半径（ピクセル）。
    bg_color : str
        入力欄の背景色。
    border_color : str
        枠線の色。
    font : tuple
        フォント指定。
    show : str
        パスワード用マスク文字（例: "●"）。空文字で通常表示。
    parent_bg : str
        親ウィジェットの背景色（Canvas 背景に使用）。
    """

    def __init__(self, master, width=300, height=40, corner_radius=6,
                 bg_color="white", border_color="#c0c0c0",
                 focus_border_color=None,
                 font=("Yu Gothic UI", 11), show="", parent_bg="white"):
        super().__init__(master, width=width, height=height,
                         bg=parent_bg, highlightthickness=0, borderwidth=0)
        self._width = width
        self._height = height
        self._corner_radius = corner_radius
        self._border_color = border_color
        self._focus_border_color = focus_border_color or border_color
        self._bg_color = bg_color

        # 角丸の背景
        self._rect_id = self._draw_rounded_rect(
            1, 1, width - 1, height - 1, corner_radius,
            outline=border_color, fill=bg_color, width=1)

        # Entry ウィジェットを内部に配置
        self._entry = tk.Entry(self, font=font, relief="flat",
                               bg=bg_color, fg="#333333",
                               insertbackground="#333333",
                               highlightthickness=0, borderwidth=0,
                               show=show if show else "")
        self.create_window(corner_radius + 6, height // 2,
                           window=self._entry, anchor="w",
                           width=width - 2 * corner_radius - 12)

        # フォーカスで枠線色を変える
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Canvas 上に角丸矩形を描画する。"""
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_focus_in(self, event):
        self.itemconfig(self._rect_id, outline=self._focus_border_color)

    def _on_focus_out(self, event):
        self.itemconfig(self._rect_id, outline=self._border_color)

    # --- 公開メソッド ---

    def get(self):
        """入力値を返す。"""
        return self._entry.get()

    def set(self, value):
        """入力値をセットする。"""
        self._entry.delete(0, "end")
        self._entry.insert(0, value)

    def focus_set(self):
        """Entry にフォーカスを当てる。"""
        self._entry.focus_set()

    def bind_entry(self, event, handler):
        """内部の Entry にイベントをバインドする。"""
        self._entry.bind(event, handler)


# =====================================================================
# OutlineButton — 角丸の枠線ボタン（フラット）
# =====================================================================

class OutlineButton(tk.Canvas):
    """角丸の枠線ボタン。ホバー・押下でフィードバックあり。

    Parameters
    ----------
    master : widget
        親ウィジェット。
    text : str
        ボタンのラベル。
    width, height : int
        ボタンのサイズ（ピクセル）。
    corner_radius : int
        角丸の半径。
    bg_color : str
        ボタン背景色。
    border_color : str
        枠線の色。
    text_color : str
        文字色。
    font : tuple
        フォント指定。
    command : callable or None
        クリック時のコールバック。
    parent_bg : str
        親ウィジェットの背景色。
    """

    def __init__(self, master, text="Button", width=150, height=44,
                 corner_radius=10, bg_color="white", border_color="#4a8c4a",
                 text_color="#4a8c4a", font=("Yu Gothic UI", 11),
                 command=None, parent_bg="white"):
        super().__init__(master, width=width, height=height,
                         bg=parent_bg, highlightthickness=0, borderwidth=0)
        self._command = command
        self._width = width
        self._height = height
        self._bg_color = bg_color
        self._hover_color = "#f0f8f0"
        self._press_color = "#e0f0e0"

        self._bg_id = self._draw_rounded_rect(
            1, 1, width - 1, height - 1, corner_radius,
            outline=border_color, fill=bg_color, width=1)
        self._text_id = self.create_text(
            width // 2, height // 2, text=text, font=font, fill=text_color)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_enter(self, event):
        self.itemconfig(self._bg_id, fill=self._hover_color)

    def _on_leave(self, event):
        self.itemconfig(self._bg_id, fill=self._bg_color)

    def _on_press(self, event):
        self.itemconfig(self._bg_id, fill=self._press_color)

    def _on_release(self, event):
        self.itemconfig(self._bg_id, fill=self._bg_color)
        if (self._command
                and 0 <= event.x < self._width
                and 0 <= event.y < self._height):
            self._command()


# =====================================================================
# LoginForm — 碁華ログイン画面
# =====================================================================

class LoginForm(tk.Tk):
    """碁華 ログイン画面。"""

    BG = "white"

    def __init__(self):
        super().__init__()
        self.title("\u7881\u83ef")                 # 碁華
        self.configure(bg=self.BG)
        self.geometry("460x420")
        self.resizable(False, False)
        self._result = None
        self._build_ui()

    def _build_ui(self):
        bg = self.BG
        fg = "#333333"
        green = "#3a7a3a"
        label_font = ("Yu Gothic UI", 10)
        title_font = ("Yu Gothic UI", 20, "bold")

        # --- タイトル ---
        tk.Label(self, text="\u7881\u83ef \u30ed\u30b0\u30a4\u30f3",
                 font=title_font,
                 bg=bg, fg=green).pack(pady=(35, 30))

        # --- フォーム ---
        form = tk.Frame(self, bg=bg)
        form.pack(padx=40, fill="x")

        # ハンドルネーム
        tk.Label(form, text="\u30cf\u30f3\u30c9\u30eb\u30cd\u30fc\u30e0",
                 font=label_font,
                 bg=bg, fg=fg, anchor="w").pack(anchor="w")
        self._name_entry = RoundedEntry(
            form, width=380, height=42,
            border_color="#c0c0c0",
            focus_border_color=green,
            parent_bg=bg)
        self._name_entry.pack(pady=(4, 12), anchor="w")

        # パスワード
        tk.Label(form, text="\u30d1\u30b9\u30ef\u30fc\u30c9",
                 font=label_font,
                 bg=bg, fg=fg, anchor="w").pack(anchor="w")
        self._pw_entry = RoundedEntry(
            form, width=380, height=42,
            border_color="#c0c0c0",
            focus_border_color=green,
            parent_bg=bg)
        self._pw_entry.pack(pady=(4, 25), anchor="w")

        # --- ボタン ---
        btn_frame = tk.Frame(form, bg=bg)
        btn_frame.pack(anchor="w")

        # ログインボタン（GlossyButton: 緑）
        self._login_btn = GlossyButton(
            btn_frame, text="\u30ed\u30b0\u30a4\u30f3",
            width=180, height=46,
            base_color=(55, 130, 55), text_color="white",
            font=("Yu Gothic UI", 13, "bold"),
            depth=0.6,
            command=self._do_login, bg=bg,
        )
        self._login_btn.pack(side="left", padx=(0, 10))

        # アカウント作成ボタン（OutlineButton: 緑枠・緑文字）
        self._register_btn = OutlineButton(
            btn_frame, text="\u30a2\u30ab\u30a6\u30f3\u30c8\u4f5c\u6210",
            width=180, height=46,
            corner_radius=10,
            border_color="#4a8c4a",
            text_color="#3a6a3a",
            font=("Yu Gothic UI", 12),
            command=self._do_register, parent_bg=bg,
        )
        self._register_btn.pack(side="left")

        # --- エラーメッセージ ---
        self._msg_label = tk.Label(self, text="", font=("Yu Gothic UI", 10),
                                   bg=bg, fg="#cc5050")
        self._msg_label.pack(pady=(15, 0))

        # --- フォーカス・キーバインド ---
        self._name_entry.focus_set()
        self._name_entry.bind_entry(
            "<Return>", lambda e: self._pw_entry.focus_set())
        self._pw_entry.bind_entry(
            "<Return>", lambda e: self._do_login())

    # --- コールバック ---

    def _do_login(self):
        name = self._name_entry.get().strip()
        pw = self._pw_entry.get()
        if not name or not pw:
            self._msg_label.configure(
                text="\u30cf\u30f3\u30c9\u30eb\u30cd\u30fc\u30e0\u3068"
                     "\u30d1\u30b9\u30ef\u30fc\u30c9\u3092\u5165\u529b"
                     "\u3057\u3066\u304f\u3060\u3055\u3044",
                fg="#cc5050")
            return
        self._result = ("login", name, pw)
        self._msg_label.configure(
            text="\u30ed\u30b0\u30a4\u30f3\u4e2d\u2026", fg="#50aa50")
        self.after(300, self.destroy)

    def _do_register(self):
        messagebox.showinfo(
            "\u30a2\u30ab\u30a6\u30f3\u30c8\u4f5c\u6210",
            "\u30a2\u30ab\u30a6\u30f3\u30c8\u4f5c\u6210\u753b\u9762\u306f"
            "\u73fe\u5728\u6e96\u5099\u4e2d\u3067\u3059\u3002")

    def get_result(self):
        """ログイン結果を返す。("login", name, pw) or None。"""
        return self._result


# =====================================================================
# エントリーポイント
# =====================================================================

def run_login():
    """ログイン画面を表示し結果を返す。"""
    app = LoginForm()
    app.mainloop()
    return app.get_result()


if __name__ == "__main__":
    result = run_login()
    if result:
        print(f"Action: {result[0]}, Name: {result[1]}")
    else:
        print("Cancelled")

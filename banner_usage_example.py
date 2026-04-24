import tkinter as tk
from teal_banner import TealBanner


def main():
    root = tk.Tk()
    root.title("TealBanner 呼び出しサンプル")
    root.configure(bg="#efe5d2")

    # =================================================================
    # デザイン1: 対局受付画面用バーナー 
    # =================================================================
    banner1 = TealBanner(
        root,
        text="挑戦状が届いています！",     
        width=460,                          # ← 動的な幅に置き換え
        # --- デザインパラメータ（固定値） ---
        font_weight="normal",
        text_color=(255, 0, 0),                  # 赤文字
        text_stroke_color=None,                  # 縁取りなし
        bg_edge=(255, 222, 173),                 # 端: 暖かいベージュ
        bg_center=(250, 240, 230),               # 中央: クリーム色
        border_color=(210, 105, 30),             # 外枠: 茶色
        border_width=3,                          # 外枠太さ: 3px
        bg="#efe5d2",
    )
    banner1.pack(pady=(5, 15))

    # =================================================================
    # デザイン2: 対局申請画面用バーナー
    # =================================================================
    banner2 = TealBanner(
        root,
        text="U2（1級(中)）",              # ← 動的な文字列に置き換え
        width=460,                          # ← 動的な幅に置き換え
        # --- デザインパラメータ（固定値） ---
        font_weight="normal",
        text_color=(40, 45, 38),                 # 暗い緑がかった黒
        text_stroke_color=None,                  # 縁取りなし
        bg_edge=(189, 213, 149),                 # 端: やや濃い黄緑
        bg_center=(217, 242, 208),               # 中央: 明るい黄緑
        border_color=(187, 210, 143),            # 外枠: 濃い黄緑
        border_width=None,                       # 外枠太さ: 自動
        bg="#efe5d2",
    )
    banner2.pack(pady=(5, 15))

    root.mainloop()


if __name__ == "__main__":
    main()

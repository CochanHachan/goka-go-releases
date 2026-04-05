#!/usr/bin/env python3
"""Reusable teal banner widget for Tkinter applications.

Rounded-corner teal gradient banner without outer border,
suitable for player info, status displays, and labels.
All visual parameters are configurable.
"""
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFont
import os


class TealBanner(tk.Canvas):
    """A custom Canvas-based banner with teal gradient background,
    rounded corners, and no outer border.

    All visual properties are configurable via constructor parameters.

    Usage::

        import tkinter as tk
        from teal_banner import TealBanner

        root = tk.Tk()
        banner = TealBanner(root, text="山田太郎（初段(中))")
        banner.pack(pady=10)
        root.mainloop()

    Parameters
    ----------
    master : tk.Widget
        Parent widget.
    text : str
        Text to display on the banner.
    width : int
        Banner width in pixels (default: 460).
    height : int
        Banner height in pixels (default: 48).
    font : str or None
        Font file path or font family name. None = auto-detect.
    font_size : int or None
        Font size in points. None = auto (proportional to height).
    font_weight : str
        Font weight hint: 'bold' or 'normal' (default: 'bold').
    text_color : tuple[int, int, int]
        RGB color for main text (default: bright teal).
    text_stroke_color : tuple[int, int, int]
        RGB color for text outline stroke (default: dark).
    bg_edge : tuple[int, int, int]
        RGB color at the left/right edges of the gradient (default: dark teal).
    bg_center : tuple[int, int, int]
        RGB color at the horizontal center of the gradient (default: bright teal).
    gradient_strength : float
        Gradient intensity 0.0-2.0. Higher = more contrast between
        edge and center (default: 1.0).
    corner_radius : int or None
        Corner radius in pixels. None = auto (proportional to height).
        0 = no rounding.
    border_color : tuple[int, int, int] or None
        RGB color for the outer border of the banner. None = no border.
    border_width : int or None
        Border width in pixels. None = auto (proportional to height).
    line_color : tuple[int, int, int] or None
        RGB color for interior decorative lines. None = no lines (default).
    diamond_color : tuple[int, int, int] or None
        RGB color for diamond decorations. None = no diamonds.
    """

    _FONT_CANDIDATES_BOLD = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        "C:/Windows/Fonts/yugothb.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    ]

    _FONT_CANDIDATES_NORMAL = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "C:/Windows/Fonts/yugothr.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    ]

    def __init__(self, master, text="山田太郎（初段(中))",
                 width=460, height=48,
                 font=None, font_size=None, font_weight="bold",
                 text_color=(210, 255, 255),
                 text_stroke_color=(0, 10, 15),
                 bg_edge=(10, 20, 30),
                 bg_center=(50, 110, 130),
                 gradient_strength=1.0,
                 corner_radius=None,
                 border_color=(90, 190, 190),
                 border_width=None,
                 line_color=None,
                 diamond_color=None,
                 **kwargs):
        super().__init__(master, width=width + 1, height=height + 1,
                         highlightthickness=0, borderwidth=0, **kwargs)
        self._text = text
        self._width = width
        self._height = height
        self._font_spec = font
        self._font_size = font_size
        self._font_weight = font_weight
        self._text_color = text_color
        self._text_stroke_color = text_stroke_color
        self._bg_edge = bg_edge
        self._bg_center = bg_center
        self._gradient_strength = gradient_strength
        self._corner_radius = corner_radius
        self._border_color = border_color
        self._border_width = border_width
        self._line_color = line_color
        self._diamond_color = diamond_color

        self._photo = None
        self._render()

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------

    def _find_font(self, size):
        """Find an available font, preferring user-specified font."""
        if self._font_spec is not None:
            if os.path.isfile(self._font_spec):
                try:
                    return ImageFont.truetype(self._font_spec, size)
                except (OSError, IOError):
                    pass
            try:
                return ImageFont.truetype(self._font_spec, size)
            except (OSError, IOError):
                pass

        candidates = (self._FONT_CANDIDATES_BOLD if self._font_weight == "bold"
                      else self._FONT_CANDIDATES_NORMAL)
        for path in candidates:
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    continue
        # Fallback: try bold candidates even for normal weight
        for path in self._FONT_CANDIDATES_BOLD:
            if os.path.isfile(path):
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    continue
        return ImageFont.load_default()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _smooth(t):
        """Smoothstep for a single float value."""
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _make_rounded_mask(self, w, h, radius):
        """Create a rounded-rectangle alpha mask (L mode)."""
        mask = Image.new("L", (w, h), 255)
        if radius <= 0:
            return mask
        draw = ImageDraw.Draw(mask)
        # Clear corners with black, then draw white rounded rect
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)],
                               radius=radius, fill=255)
        return mask

    # ------------------------------------------------------------------
    # Main render
    # ------------------------------------------------------------------

    def _render(self):
        """Render the banner image and display it on the canvas."""
        scale = 4
        sw, sh = self._width * scale, self._height * scale

        # Corner radius (auto or user-specified)
        if self._corner_radius is not None:
            cr = self._corner_radius * scale
        else:
            cr = max(4, sh // 6)  # auto: moderate rounding

        # --- Background with horizontal gradient (pure Pillow) ---
        gs = max(0.0, self._gradient_strength)
        edge = self._bg_edge
        center = self._bg_center
        sw_max = max(1, sw - 1)
        sh_max = max(1, sh - 1)

        img = Image.new("RGBA", (sw, sh))
        pix = img.load()
        for y in range(sh):
            vy = y / sh_max
            v_factor = (1.0 - vy) * 0.12 * gs
            for x in range(sw):
                hx = x / sw_max
                h_raw = self._smooth(1.0 - abs(hx - 0.5) * 2.0)
                h_factor = max(0.0, min(1.0, h_raw * gs))
                t = max(0.0, min(1.0, h_factor + v_factor))
                r = int(max(0, min(255, edge[0] + (center[0] - edge[0]) * t)))
                g = int(max(0, min(255, edge[1] + (center[1] - edge[1]) * t)))
                b = int(max(0, min(255, edge[2] + (center[2] - edge[2]) * t)))
                pix[x, y] = (r, g, b, 255)

        # --- Outer border (drawn along the edge of the banner) ---
        if self._border_color is not None:
            if self._border_width is not None:
                bw = self._border_width * scale
            else:
                bw = max(2, scale)  # auto: ~1px after downscale
            border_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border_layer)
            border_fill = (*self._border_color, 200)
            # Draw rounded rectangle outline
            border_draw.rounded_rectangle(
                [(0, 0), (sw - 1, sh - 1)],
                radius=cr, outline=border_fill, width=bw)
            img = Image.alpha_composite(img, border_layer)

        # --- Interior decorative lines (optional) ---
        if self._line_color is not None:
            line_alpha = 130
            line_fill = (*self._line_color, line_alpha)
            margin_y = max(3 * scale, sh // 8)
            margin_x = max(4 * scale, sw // 20)
            line_y_top = margin_y
            line_y_bot = sh - margin_y
            line_x_start = margin_x
            line_x_end = sw - margin_x
            lw = max(2, scale)
            line_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            line_draw = ImageDraw.Draw(line_layer)
            # Top
            line_draw.line([(line_x_start, line_y_top), (line_x_end, line_y_top)],
                           fill=line_fill, width=lw)
            # Bottom
            line_draw.line([(line_x_start, line_y_bot), (line_x_end, line_y_bot)],
                           fill=line_fill, width=lw)
            # Left
            line_draw.line([(line_x_start, line_y_top), (line_x_start, line_y_bot)],
                           fill=line_fill, width=lw)
            # Right
            line_draw.line([(line_x_end, line_y_top), (line_x_end, line_y_bot)],
                           fill=line_fill, width=lw)
            img = Image.alpha_composite(img, line_layer)

        # --- Diamond decorations (optional) ---
        if self._diamond_color is not None:
            ds = max(2 * scale, sh // 12)
            diamond_x_left = max(6 * scale, sw // 18)
            diamond_x_right = sw - max(6 * scale, sw // 18)
            cy = sh // 2
            for cx in [diamond_x_left, diamond_x_right]:
                dl = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
                ImageDraw.Draw(dl).polygon(
                    [(cx, cy - ds), (cx + ds, cy),
                     (cx, cy + ds), (cx - ds, cy)],
                    fill=(*self._diamond_color, 200)
                )
                img = Image.alpha_composite(img, dl)

        # --- Text ---
        auto_font_size = (self._font_size * scale if self._font_size
                          else max(14, int(self._height * scale * 0.40)))
        pil_font = self._find_font(auto_font_size)

        txt = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt)
        bbox = td.textbbox((0, 0), self._text, font=pil_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (sw - tw) // 2
        ty = (sh - th) // 2 - bbox[1]

        # Text shadow
        td.text((tx + scale, ty + scale), self._text, font=pil_font,
                fill=(0, 0, 0, 80))

        # Text stroke (skip if None)
        if self._text_stroke_color is not None:
            stroke_color = (*self._text_stroke_color, 200)
            sw2 = max(1, scale)
            for dx in range(-sw2, sw2 + 1):
                for dy in range(-sw2, sw2 + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if dx * dx + dy * dy <= sw2 * sw2:
                        td.text((tx + dx, ty + dy), self._text,
                                font=pil_font, fill=stroke_color)

        # Main text
        td.text((tx, ty), self._text, font=pil_font,
                fill=(*self._text_color, 255))
        img = Image.alpha_composite(img, txt)

        # --- Apply rounded corner mask ---
        mask = self._make_rounded_mask(sw, sh, cr)
        img.putalpha(mask)

        # --- Downscale with antialiasing ---
        final = img.resize((self._width, self._height), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(final)
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_text(self, text):
        """Update the displayed text and re-render."""
        self._text = text
        self._render()

    def update_size(self, width, height):
        """Update the banner size and re-render."""
        self._width = width
        self._height = height
        self.configure(width=width + 1, height=height + 1)
        self._render()

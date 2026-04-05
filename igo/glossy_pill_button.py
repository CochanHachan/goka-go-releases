import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk, ImageFilter


LANGUAGE_OPTIONS = {
    "日本語": "ja",
    "English": "en",
    "中文": "zh",
    "한국어": "ko",
}


# =============================================================
# Colour helper functions
# =============================================================
def _lighten(color, amount=30):
    return tuple(min(255, c + amount) for c in color)


def _darken(color, amount=30):
    return tuple(max(0, c - amount) for c in color)


def _blend(c1, c2, t):
    """Linearly blend two RGB tuples. t=0 gives c1, t=1 gives c2."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))


def _smoothstep(t):
    """Smoothstep interpolation for natural transitions."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# =============================================================
# Render a glossy pill-button image with PIL  (super-sampled)
# =============================================================
def render_button_image(width, height, base_color,
                        gradient=1.0, gloss=1.0, depth=1.0,
                        corner_radius=None,
                        is_pressed=False,
                        focus_border=False,
                        focus_border_color=None, focus_border_width=3,
                        scale=5):
    """
    Render a glossy pill-shaped button background image (no text).

    Text is rendered separately via Canvas create_text (reference approach)
    so the gradient remains fully visible behind/around the text.

    Parameters
    ----------
    width             : button width in pixels
    height            : button height in pixels
    base_color        : (R, G, B) base colour of the button
    gradient          : 0.0 (flat) to 2.0 (strong gradient). Default 1.0.
    gloss             : 0.0 (no gloss) to 2.0 (strong gloss). Default 1.0.
    depth             : 0.0 (flat) to 2.0 (strong 3D). Default 1.0.
    corner_radius     : corner radius in pixels. None = pill (height/2). Default None.
    is_pressed        : True = sunken/pressed state. Default False.
    focus_border      : True = show focus border (colour change). Default False.
    focus_border_color: (R, G, B) focus border colour or None=auto. Default None.
    focus_border_width: focus border thickness in pixels. Default 3.
    scale             : super-sampling factor (default 5)
    """
    gradient = max(0.0, min(2.0, gradient))
    gloss = max(0.0, min(2.0, gloss))
    depth = max(0.0, min(2.0, depth))

    base = base_color
    d = depth
    g = gradient
    gl = gloss

    # Border color: focus colour or simple dark border (reference approach)
    if focus_border:
        border_color = focus_border_color if focus_border_color else (80, 140, 220)
    else:
        border_color = _darken(base, 60)

    # No gradient override for focus — only the border colour changes

    W, H = width * scale, height * scale
    if corner_radius is not None:
        radius = corner_radius * scale
    else:
        radius = H // 2   # pill = semicircle ends

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Margins
    margin = 2 * scale

    # Press offset: body shifts down when pressed (reference approach)
    press_offset = 1 * scale if is_pressed else 0
    top = margin + press_offset
    bottom = H - margin + press_offset
    body_rect = [margin, top, W - margin, bottom]

    # 1. Border (flat colour, reference approach)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(body_rect, radius=radius, fill=border_color)

    # 2. Inner body with smooth gradient (smoothstep interpolation)
    bw = focus_border_width * scale if focus_border else scale
    inner = [body_rect[0] + bw, body_rect[1] + bw,
             body_rect[2] - bw, body_rect[3] - bw]
    inner_radius = max(1, radius - bw)

    # Rounded corner mask for inner body
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(inner, radius=inner_radius, fill=255)

    # Calculate gradient colours (reference _calc_gradient approach)
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    body_draw = ImageDraw.Draw(body)
    body_h = inner[3] - inner[1]
    for y_off in range(max(1, body_h)):
        t = y_off / max(1, body_h - 1)
        st = _smoothstep(t)
        if is_pressed:
            top_color = _darken(base, int(25 * max(d, 0.3)))
            bot_color = _darken(base, int(10 * max(d, 0.3)))
        else:
            top_color = _lighten(base, int(50 * d * g))
            bot_color = _darken(base, int(30 * d * g))
        r, gg, b = _blend(top_color, bot_color, st)
        r = max(0, min(255, r))
        gg = max(0, min(255, gg))
        b = max(0, min(255, b))
        yy = inner[1] + y_off
        body_draw.line([(inner[0], yy), (inner[2], yy)], fill=(r, gg, b, 255))

    # Apply mask and composite
    body_masked = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    body_masked.paste(body, mask=mask)
    img = Image.alpha_composite(img, body_masked)

    # 3. Subtle glossy highlight (reference approach: not when pressed)
    if not is_pressed and d > 0 and gl > 0:
        gloss_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gloss_h = body_h // 3
        gloss_alpha = min(255, int(35 * gl))
        ImageDraw.Draw(gloss_layer).ellipse(
            [inner[0] + 4 * scale, inner[1],
             inner[2] - 4 * scale, inner[1] + gloss_h],
            fill=(255, 255, 255, gloss_alpha)
        )
        gloss_layer = gloss_layer.filter(
            ImageFilter.GaussianBlur(radius=2 * scale))
        img = Image.alpha_composite(img, gloss_layer)

    # 4. Thin top edge highlight
    if d > 0:
        hl_alpha = min(255, int((50 if not is_pressed else 20) * d))
        hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(hl).rounded_rectangle(
            [inner[0] + scale, inner[1], inner[2] - scale, inner[1] + scale],
            radius=max(1, inner_radius // 2),
            fill=(255, 255, 255, hl_alpha)
        )
        img = Image.alpha_composite(img, hl)

    # 5. Downscale with LANCZOS anti-aliasing
    final = img.resize((width, height), Image.LANCZOS)
    return final


def _rgb_to_hex(rgb):
    """Convert (R, G, B) tuple to '#RRGGBB' hex string for Canvas."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _resolve_canvas_font(font_name, text_size):
    """Resolve a Canvas-compatible font tuple from font_name and size."""
    import tkinter.font as tkfont
    import os
    size = text_size
    # If font_name is a file path, try to determine family from filename
    if font_name:
        basename = os.path.basename(font_name).lower()
        font_map = {
            "meiryo": "Meiryo",
            "msgothic": "MS Gothic",
            "yugoth": "Yu Gothic UI",
            "msyh": "Microsoft YaHei",
            "malgun": "Malgun Gothic",
            "segoeui": "Segoe UI",
            "notosanscjk": "Noto Sans CJK JP",
            "dejavu": "DejaVu Sans",
        }
        for key, family in font_map.items():
            if key in basename:
                return (family, size, "bold")
    # Auto-detect: try common CJK-capable fonts
    try:
        families = set(tkfont.families())
        candidates = [
            "Meiryo", "Yu Gothic UI", "MS Gothic", "MS PGothic",
            "Microsoft YaHei", "Malgun Gothic",
            "Noto Sans CJK JP", "Noto Sans CJK",
            "DejaVu Sans", "Helvetica", "Arial",
        ]
        for name in candidates:
            if name in families:
                return (name, size, "bold")
    except Exception:
        pass
    return ("TkDefaultFont", size, "bold")


# =============================================================
# GlossyButton widget (Canvas-based, pre-rendered states)
# =============================================================
class GlossyButton(tk.Canvas):
    """
    A single glossy pill button with focus highlight and pressed effect.

    Pre-renders all visual states (normal, hover, pressed, focused,
    focused_hover) at construction time for instant state transitions.

    Parameters
    ----------
    master              : tk parent widget
    text                : display label (any string)
    base_color          : (R, G, B) base colour  (default (85,165,45) green)
    gradient            : gradient intensity 0.0-2.0 (default 1.0)
    gloss               : gloss intensity 0.0-2.0 (default 1.0)
    depth               : 3D depth 0.0-2.0 (default 1.0)
    corner_radius       : corner radius in px, None=pill (default None)
    font_name           : font file path or None for auto (default None)
    text_color          : (R, G, B) text colour (default (255,255,255) white)
    text_size           : text size in pixels (default 14)
    text_stroke         : True/False enable text outline (default True)
    text_stroke_width   : outline thickness in pixels (default 2)
    text_stroke_color   : (R, G, B) outline colour or None=auto (default None)
    width               : pixel width   (default 120)
    height              : pixel height  (default 36)
    command             : callback on click (default None)
    focus_border_color  : (R, G, B) focus border colour or None=auto (default None)
    focus_border_width  : focus border thickness in pixels (default 3)
    """

    def __init__(self, master, text="", base_color=(85, 165, 45),
                 gradient=1.0, gloss=1.0, depth=1.0,
                 corner_radius=None,
                 font_name=None, text_color=(255, 255, 255),
                 text_size=14, text_stroke=True,
                 text_stroke_width=2, text_stroke_color=None,
                 width=120, height=36, command=None,
                 focus_border_color=None, focus_border_width=3,
                 **kwargs):
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, borderwidth=0, **kwargs)
        self._text = text
        self._base_color = base_color
        self._gradient = gradient
        self._gloss = gloss
        self._depth = depth
        self._corner_radius = corner_radius
        self._font_name = font_name
        self._text_color = text_color
        self._text_size = text_size
        self._text_stroke = text_stroke
        self._text_stroke_width = text_stroke_width
        self._text_stroke_color = text_stroke_color
        self._width = width
        self._height = height
        self._command = command
        self._focus_border_color = focus_border_color
        self._focus_border_width = focus_border_width
        self._state = "normal"

        # Resolve Canvas font tuple
        self._canvas_font = _resolve_canvas_font(font_name, text_size)

        # Pre-render all state images (background only, no text)
        self._images = {}
        self._build_images()

        # Draw initial state
        self._draw("normal")

        # Bind events
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Return>", self._on_key_activate)
        self.bind("<space>", self._on_key_activate)

        # Make focusable
        self.configure(takefocus=True, cursor="hand2")

    # ----- rendering helpers -----

    def _render_state(self, base_color, is_pressed=False, focus_border=False):
        """Render the button background image for a given visual state."""
        return render_button_image(
            self._width, self._height, base_color,
            gradient=self._gradient, gloss=self._gloss, depth=self._depth,
            corner_radius=self._corner_radius,
            is_pressed=is_pressed, focus_border=focus_border,
            focus_border_color=self._focus_border_color,
            focus_border_width=self._focus_border_width)

    def _build_images(self):
        """Pre-render all button state images."""
        base = self._base_color
        hover = _lighten(base, 20)
        pressed = _darken(base, 20)
        self._images["normal"] = ImageTk.PhotoImage(
            self._render_state(base))
        self._images["hover"] = ImageTk.PhotoImage(
            self._render_state(hover))
        self._images["pressed"] = ImageTk.PhotoImage(
            self._render_state(pressed, is_pressed=True))
        self._images["focused"] = ImageTk.PhotoImage(
            self._render_state(base, focus_border=True))
        self._images["focused_hover"] = ImageTk.PhotoImage(
            self._render_state(hover, focus_border=True))

    def _draw(self, state):
        """Display the pre-rendered image and overlay text via Canvas."""
        self.delete("all")
        img_key = state if state in self._images else "normal"
        self.create_image(0, 0, anchor="nw", image=self._images[img_key])

        # Text position (reference approach: Canvas create_text)
        cx, cy = self._width // 2, self._height // 2
        if state == "pressed":
            cy += 1

        # Text shadow for depth
        shadow_color = _rgb_to_hex(_darken(self._base_color, 50))
        self.create_text(cx + 1, cy + 1, text=self._text,
                         font=self._canvas_font, fill=shadow_color,
                         anchor="center")

        # Text stroke (outline) via multi-draw offset
        if self._text_stroke and self._text_stroke_width > 0:
            stroke_rgb = self._text_stroke_color or _darken(self._base_color, 80)
            stroke_hex = _rgb_to_hex(stroke_rgb)
            sw = self._text_stroke_width
            for dx in range(-sw, sw + 1):
                for dy in range(-sw, sw + 1):
                    if dx * dx + dy * dy <= sw * sw and (dx != 0 or dy != 0):
                        self.create_text(cx + dx, cy + dy, text=self._text,
                                         font=self._canvas_font,
                                         fill=stroke_hex, anchor="center")

        # Main text
        text_hex = _rgb_to_hex(self._text_color)
        self.create_text(cx, cy, text=self._text,
                         font=self._canvas_font, fill=text_hex,
                         anchor="center")

    def _rebuild_and_draw(self):
        """Rebuild all state images and redraw current state."""
        self._build_images()
        self._draw(self._state)

    # ----- event handlers (matching reference glossy_button.py) -----

    def _on_enter(self, _e):
        if self._state == "focused":
            self._draw("focused_hover")
        else:
            self._state = "hover"
            self._draw("hover")

    def _on_leave(self, _e):
        if self._state == "focused" or self.focus_get() == self:
            self._state = "focused"
            self._draw("focused")
        else:
            self._state = "normal"
            self._draw("normal")

    def _on_press(self, _e):
        self._state = "pressed"
        self.focus_set()
        self._draw("pressed")

    def _on_release(self, _e):
        self._state = "focused"
        if 0 <= _e.x < self._width and 0 <= _e.y < self._height:
            self._draw("focused_hover")
        else:
            self._draw("focused")
        if self._command and 0 <= _e.x < self._width and 0 <= _e.y < self._height:
            self._command()

    def _on_focus_in(self, _e):
        if self._state == "pressed":
            return
        self._state = "focused"
        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        if 0 <= mx < self._width and 0 <= my < self._height:
            self._draw("focused_hover")
        else:
            self._draw("focused")

    def _on_focus_out(self, _e):
        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        if 0 <= mx < self._width and 0 <= my < self._height:
            self._state = "hover"
            self._draw("hover")
        else:
            self._state = "normal"
            self._draw("normal")

    def _on_key_activate(self, _e):
        """Activate button via Enter or Space key."""
        self._draw("pressed")
        self.after(100, lambda: self._draw("focused"))
        if self._command:
            self._command()

    # ----- public setters (rebuild images on change) -----

    def set_text(self, text):
        self._text = text
        self._draw(self._state)  # text is Canvas-rendered, no image rebuild needed

    def set_base_color(self, base_color):
        self._base_color = base_color
        self._rebuild_and_draw()

    def set_gradient(self, gradient):
        self._gradient = gradient
        self._rebuild_and_draw()

    def set_gloss(self, gloss):
        self._gloss = gloss
        self._rebuild_and_draw()

    def set_depth(self, depth):
        self._depth = depth
        self._rebuild_and_draw()

    def set_font_name(self, font_name):
        self._font_name = font_name
        self._canvas_font = _resolve_canvas_font(font_name, self._text_size)
        self._draw(self._state)

    def set_text_color(self, text_color):
        self._text_color = text_color
        self._draw(self._state)

    def set_text_size(self, text_size):
        self._text_size = text_size
        self._canvas_font = _resolve_canvas_font(self._font_name, text_size)
        self._draw(self._state)

    def set_text_stroke(self, text_stroke):
        self._text_stroke = text_stroke
        self._draw(self._state)

    def set_text_stroke_width(self, text_stroke_width):
        self._text_stroke_width = text_stroke_width
        self._draw(self._state)

    def set_text_stroke_color(self, text_stroke_color):
        self._text_stroke_color = text_stroke_color
        self._draw(self._state)

    def set_corner_radius(self, corner_radius):
        self._corner_radius = corner_radius
        self._rebuild_and_draw()

    def set_focus_border_color(self, focus_border_color):
        self._focus_border_color = focus_border_color
        self._rebuild_and_draw()

    def set_focus_border_width(self, focus_border_width):
        self._focus_border_width = focus_border_width
        self._rebuild_and_draw()


# =============================================================
# App - takes a configurable list of buttons
# =============================================================
class App(tk.Tk):
    """
    Parameters
    ----------
    language : initial language code ("ja","en","zh","ko")
    buttons  : dict of {name: button_def}, each button_def with:
        text              - display text (any string)              [required]
        base_color        - (R, G, B) base colour                 (default (85,165,45))
        gradient          - gradient intensity 0.0-2.0            (default 1.0)
        gloss             - gloss intensity 0.0-2.0               (default 1.0)
        depth             - 3D depth 0.0-2.0                      (default 1.0)
        corner_radius     - corner radius in px, None=pill         (default None)
        font_name         - font file path or None=auto           (default None)
        text_color        - (R, G, B) text colour                 (default (255,255,255))
        text_size         - text size in pixels                   (default 14)
        text_stroke       - True/False enable outline             (default True)
        text_stroke_width - outline thickness in pixels            (default 2)
        text_stroke_color - (R, G, B) outline colour or None=auto (default None)
        width             - button width in pixels                 (default 120)
        height            - button height in pixels                (default 36)
        command           - click callback                         (default None)
        lang_texts        - {lang_code: "translated text", ...}   (default None)
        focus_border_color  - (R, G, B) focus border colour          (default None=auto)
        focus_border_width  - focus border thickness in pixels        (default 3)
    """

    def __init__(self, language="ja", buttons=None):
        super().__init__()
        self._lang = language
        self._button_defs = buttons or {}   # {name: bdef}
        self.title("Button Demo")
        self.configure(bg="#e8e8e8")
        self.resizable(False, False)

        # --- Language selector ---
        lang_frame = tk.Frame(self, bg="#e8e8e8")
        lang_frame.pack(pady=(12, 4))

        self._lang_var = tk.StringVar()
        for display, code in LANGUAGE_OPTIONS.items():
            if code == self._lang:
                self._lang_var.set(display)
                break

        lang_combo = ttk.Combobox(
            lang_frame, textvariable=self._lang_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            state="readonly", width=10)
        lang_combo.pack()
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        # --- Buttons (generated from the dict) ---
        btn_frame = tk.Frame(self, bg="#e8e8e8")
        btn_frame.pack(pady=12, padx=16)

        self._buttons = {}        # {name: GlossyButton}
        self._button_names = []   # ordered list of names
        for i, (name, bdef) in enumerate(self._button_defs.items()):
            display_text = self._resolve_text(bdef)
            btn = GlossyButton(
                btn_frame,
                text=display_text,
                base_color=bdef.get("base_color", (85, 165, 45)),
                gradient=bdef.get("gradient", 1.0),
                gloss=bdef.get("gloss", 1.0),
                depth=bdef.get("depth", 1.0),
                corner_radius=bdef.get("corner_radius"),
                font_name=bdef.get("font_name"),
                text_color=bdef.get("text_color", (255, 255, 255)),
                text_size=bdef.get("text_size", 14),
                text_stroke=bdef.get("text_stroke", True),
                text_stroke_width=bdef.get("text_stroke_width", 2),
                text_stroke_color=bdef.get("text_stroke_color"),
                width=bdef.get("width", 120),
                height=bdef.get("height", 36),
                command=bdef.get("command"),
                focus_border_color=bdef.get("focus_border_color"),
                focus_border_width=bdef.get("focus_border_width", 3),
                bg="#e8e8e8",
            )
            btn.grid(row=0, column=i, padx=6, pady=6)
            self._buttons[name] = btn
            self._button_names.append(name)

    def get_button(self, name):
        """Return the GlossyButton widget by its name."""
        return self._buttons.get(name)

    def set_language(self, lang_code):
        """Change the language programmatically (e.g. 'ja', 'en', 'zh', 'ko')."""
        self._lang = lang_code
        # Update combo box display
        for display, code in LANGUAGE_OPTIONS.items():
            if code == lang_code:
                self._lang_var.set(display)
                break
        # Update all button texts
        for name in self._button_names:
            bdef = self._button_defs[name]
            self._buttons[name].set_text(self._resolve_text(bdef))

    def _resolve_text(self, bdef):
        """Return the button text for the current language."""
        lang_texts = bdef.get("lang_texts")
        if lang_texts and self._lang in lang_texts:
            return lang_texts[self._lang]
        return bdef.get("text", "")

    def _on_language_change(self, _event=None):
        display = self._lang_var.get()
        self._lang = LANGUAGE_OPTIONS[display]
        for name in self._button_names:
            bdef = self._button_defs[name]
            self._buttons[name].set_text(self._resolve_text(bdef))

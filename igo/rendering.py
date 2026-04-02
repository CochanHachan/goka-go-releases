# -*- coding: utf-8 -*-
"""碁華 石・盤面テクスチャ描画"""
import os
import math
import tkinter as tk


def _make_stone_photoimage(root, radius, is_black, bg_rgb):
    """
    Pure-Tkinter stone with radial gradient + specular highlight.
    4x supersampled for smooth anti-aliased edges.
    """
    scale = 4
    hi = radius * 2 * scale
    final = radius * 2

    center = hi / 2.0
    R = radius * scale
    bg_r, bg_g, bg_b = bg_rgb

    diff_x = center - R * 0.28
    diff_y = center - R * 0.32
    spec_x = center - R * 0.40
    spec_y = center - R * 0.45
    spec_sigma = R * 0.28 if is_black else R * 0.32

    hi_pixels = []
    for y in range(hi):
        row = []
        for x in range(hi):
            dx = x - center
            dy = y - center
            dist_c = math.sqrt(dx * dx + dy * dy)

            if dist_c > R + 1.5:
                row.append((bg_r, bg_g, bg_b))
                continue

            if dist_c > R - 1.5:
                alpha = max(0.0, min(1.0, (R + 1.5 - dist_c) / 3.0))
            else:
                alpha = 1.0

            hdx = x - diff_x
            hdy = y - diff_y
            dist_d = math.sqrt(hdx * hdx + hdy * hdy) / (R * 1.4)
            td = min(1.0, dist_d)

            sdx = x - spec_x
            sdy = y - spec_y
            dist_s_sq = sdx * sdx + sdy * sdy
            spec = math.exp(-dist_s_sq / (2.0 * spec_sigma * spec_sigma))

            if is_black:
                td2 = td * td * (3.0 - 2.0 * td)
                base = 45 - 40 * td2
                v = base + 140 * spec
                sr = sg = sb = int(min(255, v))
            else:
                td2 = td * td
                base_r = 250 - 95 * td2
                base_g = 250 - 97 * td2
                base_b = 252 - 90 * td2
                edge_t = (dist_c / R)
                edge_t = max(0.0, edge_t - 0.5) * 2.0
                edge_dark = edge_t * edge_t * 25
                sr = int(min(255, base_r + 30 * spec - edge_dark))
                sg = int(min(255, base_g + 30 * spec - edge_dark))
                sb = int(min(255, base_b + 25 * spec - edge_dark))

            cr = int(sr * alpha + bg_r * (1.0 - alpha))
            cg = int(sg * alpha + bg_g * (1.0 - alpha))
            cb = int(sb * alpha + bg_b * (1.0 - alpha))

            row.append((max(0, min(255, cr)),
                         max(0, min(255, cg)),
                         max(0, min(255, cb))))
        hi_pixels.append(row)

    img = tk.PhotoImage(master=root, width=final, height=final)
    n = scale * scale
    row_data = []
    for fy in range(final):
        row_str_parts = []
        base_y = fy * scale
        for fx in range(final):
            rs = gs = bs = 0
            base_x = fx * scale
            for sy in range(scale):
                prow = hi_pixels[base_y + sy]
                for sx in range(scale):
                    pr, pg, pb = prow[base_x + sx]
                    rs += pr
                    gs += pg
                    bs += pb
            row_str_parts.append(
                "#{:02x}{:02x}{:02x}".format(rs // n, gs // n, bs // n)
            )
        row_data.append("{" + " ".join(row_str_parts) + "}")

    img.put(" ".join(row_data))
    cr = final / 2.0
    for fy in range(final):
        for fx in range(final):
            dx = fx - cr + 0.5
            dy = fy - cr + 0.5
            if dx * dx + dy * dy > (radius + 0.5) * (radius + 0.5):
                img.transparency_set(fx, fy, True)
    return img


_board_texture_original = None
_board_texture_type = "dark"  # "dark" or "light"

def _load_board_texture_original(root, force_reload=False):
    global _board_texture_original, _board_texture_type
    if _board_texture_original is not None and not force_reload:
        return _board_texture_original
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _board_texture_type == "light":
        tex_path = os.path.join(script_dir, "board_texture_light.png")
    else:
        tex_path = os.path.join(script_dir, "board_texture.png")
    if os.path.exists(tex_path):
        try:
            _board_texture_original = tk.PhotoImage(master=root, file=tex_path)
            return _board_texture_original
        except Exception:
            return None
    return None

def _make_board_texture(root, width, height):
    orig = _load_board_texture_original(root)
    if orig is None:
        img = tk.PhotoImage(master=root, width=width, height=height)
        row = "{" + " ".join(["#f4ce78"] * width) + "}"
        img.put(" ".join([row] * height))
        return img

    ow = orig.width()
    oh = orig.height()
    sub = max(1, int(max(ow / width, oh / height)))
    src_w = min(width * sub, ow)
    src_h = min(height * sub, oh)

    img = tk.PhotoImage(master=root, width=width, height=height)
    try:
        img.tk.call(img, 'copy', orig,
                    '-from', 0, 0, src_w, src_h,
                    '-subsample', sub, sub)
    except Exception:
        img = orig.subsample(sub, sub)
    return img

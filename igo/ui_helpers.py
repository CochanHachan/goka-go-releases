# -*- coding: utf-8 -*-
"""碁華 UI ヘルパー関数"""
from tkinter import ttk

from igo.theme import T


# --- IME control (Windows only) ---
def _ime_halfwidth_alphanumeric(widget):
    """Switch IME to half-width alphanumeric mode on FocusIn."""
    try:
        import ctypes
        from ctypes import wintypes
        imm32 = ctypes.WinDLL("imm32", use_last_error=True)
        IME_CMODE_NATIVE = 0x0001
        IME_CMODE_KATAKANA = 0x0002
        IME_CMODE_FULLSHAPE = 0x0008
        imm32.ImmGetContext.argtypes = [wintypes.HWND]
        imm32.ImmGetContext.restype = wintypes.HANDLE
        imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        imm32.ImmReleaseContext.restype = wintypes.BOOL
        imm32.ImmGetConversionStatus.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        imm32.ImmGetConversionStatus.restype = wintypes.BOOL
        imm32.ImmSetConversionStatus.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
        imm32.ImmSetConversionStatus.restype = wintypes.BOOL
        hwnd = widget.winfo_id()
        himc = imm32.ImmGetContext(hwnd)
        if not himc:
            return
        try:
            conv = wintypes.DWORD()
            sent = wintypes.DWORD()
            if not imm32.ImmGetConversionStatus(himc, ctypes.byref(conv), ctypes.byref(sent)):
                return
            new_conv = conv.value & ~(IME_CMODE_NATIVE | IME_CMODE_KATAKANA | IME_CMODE_FULLSHAPE)
            imm32.ImmSetConversionStatus(himc, new_conv, sent.value)
        finally:
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass  # Non-Windows or IME not available


def _entry_cfg():
    return dict(font=("", 13), bg=T("input_bg"), fg=T("text_primary"),
        insertbackground=T("text_primary"), relief="groove", bd=2, highlightthickness=1,
        highlightbackground=T("border"), highlightcolor=T("border"))

def _configure_combo_style(style, style_name):
    """Configure a ttk.Combobox style using current theme."""
    style.theme_use("clam")
    style.configure(style_name,
        fieldbackground=T("combo_field_bg"), background=T("combo_arrow_bg"),
        foreground=T("text_primary"), arrowcolor=T("text_primary"),
        bordercolor=T("border"), lightcolor=T("border"),
        darkcolor=T("border"), selectbackground=T("select_bg"),
        selectforeground=T("select_fg"),
        relief="groove", borderwidth=2, padding=(4, 4))
    style.map(style_name,
        fieldbackground=[("readonly", T("combo_field_bg"))],
        foreground=[("readonly", T("text_primary"))],
        selectbackground=[("readonly", T("combo_field_bg"))],
        selectforeground=[("readonly", T("text_primary"))])

def _apply_combo_listbox_style(widget):
    """Apply theme colors to Combobox dropdown listbox."""
    widget.option_add("*TCombobox*Listbox.background", T("combo_list_bg"))
    widget.option_add("*TCombobox*Listbox.foreground", T("combo_list_fg"))
    widget.option_add("*TCombobox*Listbox.selectBackground", T("combo_list_select_bg"))
    widget.option_add("*TCombobox*Listbox.selectForeground", T("combo_list_select_fg"))
    widget.option_add("*TCombobox*Listbox.font", ("", 11))

def _disable_ime_for(widget):
    """Switch IME to half-width alphanumeric on FocusIn for ASCII-only fields."""
    widget.bind('<FocusIn>', lambda e: _ime_halfwidth_alphanumeric(widget), add='+')

def _validate_ascii(text):
    """Only allow printable ASCII (half-width alphanumeric + symbols)."""
    return all(0x21 <= ord(c) <= 0x7E for c in text) if text else True

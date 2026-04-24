# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — 碁華 管理者画面（タブ付き igo_admin）
# Usage: pyinstaller igo_admin.spec --noconfirm
# 配布 ZIP: py -3 tools/package_igo_admin_zip.py

import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

tksheet_datas, tksheet_binaries, tksheet_hiddenimports = collect_all("tksheet")
pygame_datas, pygame_binaries, pygame_hiddenimports = collect_all("pygame")

# Python 3.13 の python313.dll は VC++ ランタイムに依存する。
# 実行環境にランタイムが無くても起動できるよう、存在する DLL は同梱する。
python_root = os.path.dirname(sys.executable)
python_dll_dir = os.path.join(python_root, "DLLs")
runtime_dll_names = [
    "python313.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "msvcp140_codecvt_ids.dll",
]
runtime_binaries = []
for dll_name in runtime_dll_names:
    for base in (python_root, python_dll_dir):
        dll_path = os.path.join(base, dll_name)
        if os.path.exists(dll_path):
            runtime_binaries.append((dll_path, "."))
            break

a = Analysis(
    ["igo_admin.py"],
    pathex=["."],
    binaries=[] + tksheet_binaries + pygame_binaries + runtime_binaries,
    datas=[
        ("board_texture.png", "."),
        ("board_texture_light.png", "."),
        ("nav_auto.png", "."),
        ("nav_first.png", "."),
        ("nav_last.png", "."),
        ("nav_next.png", "."),
        ("nav_nextX.png", "."),
        ("nav_prev.png", "."),
        ("nav_prevX.png", "."),
        ("nav_stop.png", "."),
        ("image", "image"),
        ("sounds", "sounds"),
        ("lang.py", "."),
        ("igo_cloud_client.py", "."),
        ("glossy_pill_button.py", "."),
        ("teal_banner.py", "."),
        ("glossy_button.py", "."),
    ] + tksheet_datas + pygame_datas,
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "tkinter.simpledialog",
        "tksheet",
        "cryptography",
        "cryptography.fernet",
        "igo_cloud_client",
        "glossy_pill_button",
        "teal_banner",
        "glossy_button",
        "lang",
        "login_form",
        "window_settings",
        "igo",
        "igo.constants_env",
        "igo.constants",
        "igo.config",
        "igo.elo",
        "igo.theme",
        "igo.database",
        "igo.rendering",
        "igo.timer",
        "igo.network",
        "igo.game_logic",
        "igo.katago",
        "igo.ui_helpers",
        "igo.sgf",
        "igo.sound",
        "igo.promotion",
        "igo.login_screen",
        "igo.register_screen",
        "igo.match_dialog",
        "igo.match_offer_dialog",
        "igo.kifu_dialog",
        "igo.go_board",
        "igo.app",
        "igo.glossy_button",
        "igo.glossy_pill_button",
        "igo.lang",
        "igo.login_form",
        "igo.window_settings",
        "igo.teal_banner",
        "igo.igo_cloud_client",
        "igo.byoyomi_sound",
        "igo.update_progress",
        "pygame",
        "pygame.mixer",
        "websockets",
        "websockets.legacy",
        "websockets.legacy.client",
        "websockets.legacy.server",
        "websockets.legacy.protocol",
        "websockets.connection",
        "websockets.client",
        "websockets.server",
        "websockets.protocol",
        "websockets.frames",
        "websockets.http11",
        "websockets.streams",
        "websockets.exceptions",
        "asyncio",
        "sqlite3",
        "json",
        "threading",
        "platform",
    ] + tksheet_hiddenimports + pygame_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="igo_admin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="goka_go.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="igo_admin",
)

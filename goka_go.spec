# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for 碁華 (Goka GO)
# Usage: pyinstaller goka_go.spec

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# tksheet を完全収集
tksheet_datas, tksheet_binaries, tksheet_hiddenimports = collect_all('tksheet')

a = Analysis(
    ['igo_game.py'],
    pathex=['.'],
    binaries=[] + tksheet_binaries,
    datas=[
        # 画像リソース
        ('board_texture.png',       '.'),
        ('board_texture_light.png', '.'),
        ('nav_auto.png',            '.'),
        ('nav_first.png',           '.'),
        ('nav_last.png',            '.'),
        ('nav_next.png',            '.'),
        ('nav_nextX.png',           '.'),
        ('nav_prev.png',            '.'),
        ('nav_prevX.png',           '.'),
        ('nav_stop.png',            '.'),
        # image フォルダ
        ('image',                   'image'),
        # 言語ファイル
        ('lang.py',                 '.'),
        # クラウドクライアント
        ('igo_cloud_client.py',     '.'),
        # ダイアログ用カスタムウィジェット
        ('glossy_pill_button.py',   '.'),
        ('teal_banner.py',          '.'),
        ('glossy_button.py',        '.'),
    ] + tksheet_datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'tksheet',
        'cryptography',
        'cryptography.fernet',
        'igo_cloud_client',
        'glossy_pill_button',
        'teal_banner',
        'glossy_button',
        'lang',
        'login_form',
        'window_settings',
        # igo package modules (igo/ ディレクトリ内のモジュール)
        'igo',
        'igo.constants',
        'igo.config',
        'igo.elo',
        'igo.theme',
        'igo.database',
        'igo.rendering',
        'igo.timer',
        'igo.network',
        'igo.game_logic',
        'igo.katago',
        'igo.ui_helpers',
        'igo.sgf',
        'igo.sound',
        'igo.promotion',
        'igo.login_screen',
        'igo.register_screen',
        'igo.match_dialog',
        'igo.match_offer_dialog',
        'igo.kifu_dialog',
        'igo.go_board',
        'igo.app',
        'igo.glossy_button',
        'igo.glossy_pill_button',
        'igo.lang',
        'igo.login_form',
        'igo.window_settings',
        'igo.teal_banner',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.client',
        'websockets.legacy.server',
        'websockets.legacy.protocol',
        'websockets.connection',
        'websockets.client',
        'websockets.server',
        'websockets.protocol',
        'websockets.frames',
        'websockets.http11',
        'websockets.streams',
        'websockets.exceptions',
        'asyncio',
        'sqlite3',
        'json',
        'threading',
        'platform',
    ] + tksheet_hiddenimports,
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
    name='goka_go',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # コンソールウィンドウを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='goka.ico',      # アイコンファイルがあれば有効化
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='goka_go',         # dist\goka_go\ フォルダが生成される
)

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for 碁華 管理者画面 (Goka GO Admin)
# Usage: pyinstaller igo_admin.spec

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# tksheet を完全収集
tksheet_datas, tksheet_binaries, tksheet_hiddenimports = collect_all('tksheet')

a = Analysis(
    ['igo_admin.py'],
    pathex=['.'],
    binaries=[] + tksheet_binaries,
    datas=[
        # 画像リソース（テーマ用）
        ('board_texture.png',       '.'),
        ('board_texture_light.png', '.'),
        # image フォルダ
        ('image',                   'image'),
        # 言語ファイル
        ('lang.py',                 '.'),
        # カスタムウィジェット
        ('glossy_pill_button.py',   '.'),
        ('teal_banner.py',          '.'),
        ('glossy_button.py',        '.'),
        # クラウドクライアント
        ('igo_cloud_client.py',     '.'),
    ] + tksheet_datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.simpledialog',
        'tksheet',
        'cryptography',
        'cryptography.fernet',
        'glossy_pill_button',
        'teal_banner',
        'glossy_button',
        'lang',
        'login_form',
        'window_settings',
        'igo_cloud_client',
        # igo package modules
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
        'igo.igo_cloud_client',
        'igo.byoyomi_sound',
        'igo.update_progress',
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
    excludes=[
        'pygame',
        'pygame.mixer',
    ],
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
    name='igo_admin',
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
    icon='goka_go.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='igo_admin',
)

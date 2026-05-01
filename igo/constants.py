# -*- coding: utf-8 -*-
"""碁華 定数定義

CLIENT_UPDATE_CHECK_URL が空のときは起動時の更新チェックを行わない（手動配布向け）。
"""

# ---------------------------------------------------------------------------
# 環境切替フラグ（constants_env.py から読み込み）
# ステージングビルド時は constants_env.py の _ENV を "staging" に変更する
# ---------------------------------------------------------------------------
from igo.constants_env import (
    _ENV,
    _APP_EDITION,
    BETA_CHANNEL_VERSION,
    CLIENT_UPDATE_CHECK_URL,
)

IS_BETA_EDITION = (_APP_EDITION == "beta")
# クライアント別データ領域（ローカル SQLite・ui_settings・KataGo キャッシュ等）
APP_DATA_SUBDIR = "GokaGoTest" if IS_BETA_EDITION else "GokaGo"

# ---------------------------------------------------------------------------
# 環境別サーバー設定
# ---------------------------------------------------------------------------
_SERVER_CONFIG = {
    "production": {
        "cloud_server_url": "ws://goka-igo.com:8000",
        "api_base_url":     "http://goka-igo.com:8000",
        "staging_label":    "",
        "app_name":         "碁華 Goka GO",
    },
    "staging": {
        "cloud_server_url": "ws://staging.goka-igo.com:8001",
        "api_base_url":     "http://staging.goka-igo.com:8001",
        "staging_label":    "[STAGING] ",
        "app_name":         "碁華 Goka GO [STAGING]",
    },
}

_cfg = _SERVER_CONFIG.get(_ENV)
if _cfg is None:
    raise RuntimeError("Unknown _ENV={!r}. Must be 'production' or 'staging'.".format(_ENV))

APP_NAME         = _cfg["app_name"]
APP_VERSION      = "1.2.161"
_bv = (BETA_CHANNEL_VERSION or "").strip()
if IS_BETA_EDITION and _bv:
    APP_VERSION = _bv
APP_BUILD        = "20260418"
STAGING_LABEL    = _cfg["staging_label"]
CLOUD_SERVER_URL = _cfg["cloud_server_url"]
API_BASE_URL     = _cfg["api_base_url"]

# バージョンマニフェストは constants_env の CLIENT_UPDATE_CHECK_URL のみ（空 = チェックしない）
UPDATE_CHECK_URL = (CLIENT_UPDATE_CHECK_URL or "").strip()

# ---------------------------------------------------------------------------
# 起動時自己診断: STAGING_LABEL と URL の整合性チェック
# ---------------------------------------------------------------------------
def _validate_env():
    """STAGING_LABEL と接続先URLが矛盾していないか検証する。"""
    if IS_BETA_EDITION and _ENV != "staging":
        raise RuntimeError(
            "ビルド設定エラー: _APP_EDITION が beta のときは _ENV を staging にしてください。"
            "（テスト用クライアントは本番 API/DB に接続しません）")
    _prod_host = "goka-igo.com"
    _staging_host = "staging.goka-igo.com"
    _urls = CLOUD_SERVER_URL + " " + API_BASE_URL

    if STAGING_LABEL and _prod_host in _urls and _staging_host not in _urls:
        raise RuntimeError(
            "環境設定エラー: STAGING_LABEL が設定されていますが、"
            "URLが本番サーバー({})を指しています。".format(_prod_host))
    if not STAGING_LABEL and _staging_host in _urls:
        raise RuntimeError(
            "環境設定エラー: STAGING_LABEL が空ですが、"
            "URLがステージングサーバー({})を指しています。".format(_staging_host))

    # CLOUD_SERVER_URL と API_BASE_URL のホストが一致するか
    import re
    hosts = re.findall(r'//([^:/]+)', _urls)
    if len(set(hosts)) > 1:
        raise RuntimeError(
            "環境設定エラー: CLOUD_SERVER_URL と API_BASE_URL のホストが"
            "異なります: {}".format(hosts))

_validate_env()

BOARD_SIZE = 19
CELL_SIZE = 36
MARGIN = 40
STONE_RADIUS = 18
STAR_RADIUS = 4

# 新規インストール後、ui_settings にゲーム画面の保存が無いときの初期ウィンドウサイズ。
# Windows は作業領域（タスクバー等を除く）のピクセル幅・高さに対する割合（0.0〜1.0）。
# それ以外の OS は画面全体。運用で変える場合はここだけ編集。
GAME_WINDOW_INITIAL_WIDTH_FRACTION = 0.60
GAME_WINDOW_INITIAL_HEIGHT_FRACTION = 0.78

TIME_LIMIT = 10 * 60  # 10 minutes per player

NET_TCP_PORT = 19937
NET_UDP_PORT = 19938
NET_BROADCAST_INTERVAL = 2

EMPTY = 0
BLACK = 1
WHITE = 2

STAR_POINTS = [
    (3, 3), (3, 9), (3, 15),
    (9, 3), (9, 9), (9, 15),
    (15, 3), (15, 9), (15, 15),
]

GO_RANKS = ["{}段".format(i) for i in range(9, 0, -1)] + \
           ["{}級".format(i) for i in range(1, 11)]

# Cloud client is imported lazily in _connect_cloud() to avoid slow startup
HAS_CLOUD = True

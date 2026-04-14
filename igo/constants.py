# -*- coding: utf-8 -*-
"""碁華 定数定義
自動アップデート対応版"""

# ---------------------------------------------------------------------------
# 環境切替フラグ（constants_env.py から読み込み）
# ステージングビルド時は constants_env.py の _ENV を "staging" に変更する
# ---------------------------------------------------------------------------
from igo.constants_env import _ENV

# ---------------------------------------------------------------------------
# 環境別サーバー設定
# ---------------------------------------------------------------------------
_SERVER_CONFIG = {
    "production": {
        "cloud_server_url": "ws://34.85.118.112:8000",
        "api_base_url":     "http://34.85.118.112:8000",
        "staging_label":    "",
        "app_name":         "碁華 Goka GO",
    },
    "staging": {
        "cloud_server_url": "ws://136.110.101.14:8000",
        "api_base_url":     "http://136.110.101.14:8000",
        "staging_label":    "[STAGING] ",
        "app_name":         "碁華 Goka GO [STAGING]",
    },
}

_cfg = _SERVER_CONFIG.get(_ENV)
if _cfg is None:
    raise RuntimeError("Unknown _ENV={!r}. Must be 'production' or 'staging'.".format(_ENV))

APP_NAME         = _cfg["app_name"]
APP_VERSION      = "1.2.103"
APP_BUILD        = "20260414"
STAGING_LABEL    = _cfg["staging_label"]
CLOUD_SERVER_URL = _cfg["cloud_server_url"]
API_BASE_URL     = _cfg["api_base_url"]

UPDATE_CHECK_URL = "https://raw.githubusercontent.com/CochanHachan/goka-go-releases/main/version.json"

# ---------------------------------------------------------------------------
# 起動時自己診断: STAGING_LABEL と URL の整合性チェック
# ---------------------------------------------------------------------------
def _validate_env():
    """STAGING_LABEL と接続先URLが矛盾していないか検証する。"""
    _prod_ip = "34.85.118.112"
    _staging_ip = "136.110.101.14"
    _urls = CLOUD_SERVER_URL + " " + API_BASE_URL

    if STAGING_LABEL and _prod_ip in _urls:
        raise RuntimeError(
            "環境設定エラー: STAGING_LABEL が設定されていますが、"
            "URLが本番サーバー({})を指しています。".format(_prod_ip))
    if not STAGING_LABEL and _staging_ip in _urls:
        raise RuntimeError(
            "環境設定エラー: STAGING_LABEL が空ですが、"
            "URLがステージングサーバー({})を指しています。".format(_staging_ip))

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

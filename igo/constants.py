# -*- coding: utf-8 -*-
"""碁華 定数定義 — _ENV だけで全て決まる"""

from igo.constants_env import _ENV

# ---- 環境別設定（_ENV から自動導出） --------------------------------
_CONFIG = {
    "production": {
        "app_name":          "碁華 Goka GO",
        "staging_label":     "",
        "cloud_server_url":  "ws://34.85.118.112:8000",
        "api_base_url":      "http://34.85.118.112:8000",
        "update_check_url":  "https://goka-igo.com/version.json",
        "data_dir_name":     "GokaGo",
    },
    "staging": {
        "app_name":          "碁華 Goka GO（テスト）",
        "staging_label":     "[テスト] ",
        "cloud_server_url":  "ws://20.48.18.153:8000",
        "api_base_url":      "http://20.48.18.153:8000",
        "update_check_url":  "http://20.48.18.153:8000/api/version-check",
        "data_dir_name":     "GokaGoTest",
    },
}

_c = _CONFIG.get(_ENV)
if _c is None:
    raise RuntimeError("Unknown _ENV={!r}".format(_ENV))

APP_NAME          = _c["app_name"]
APP_VERSION       = "1.2.171"
APP_BUILD         = "20260418"
STAGING_LABEL     = _c["staging_label"]
CLOUD_SERVER_URL  = _c["cloud_server_url"]
API_BASE_URL      = _c["api_base_url"]
UPDATE_CHECK_URL  = _c["update_check_url"]
APP_DATA_DIR_NAME = _c["data_dir_name"]

# ---- 碁盤 -----------------------------------------------------------
BOARD_SIZE = 19
CELL_SIZE = 36
MARGIN = 40
STONE_RADIUS = 18
STAR_RADIUS = 4

GAME_WINDOW_INITIAL_WIDTH_FRACTION = 0.60
GAME_WINDOW_INITIAL_HEIGHT_FRACTION = 0.78

TIME_LIMIT = 10 * 60

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

HAS_CLOUD = True

# -*- coding: utf-8 -*-
"""碁華 定数定義
自動アップデート対応版"""

APP_NAME        = "碁華 Goka GO"
APP_VERSION     = "1.2.57"
APP_BUILD       = "20260411"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/CochanHachan/goka-go-releases/main/version.json"

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
CLOUD_SERVER_URL = "ws://34.24.176.248:8000"
API_BASE_URL     = "http://34.24.176.248:8000"

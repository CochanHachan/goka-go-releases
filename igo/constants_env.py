# -*- coding: utf-8 -*-
"""環境切替フラグ（CI または手元ビルドでこのファイルを書き換えます）

_ENV
  production = 本番 API / 本番表示
  staging    = 検証用 API（ステージングサーバー）

_APP_EDITION
  release = 本番配布クライアント（%APPDATA%\\GokaGo）
  beta    = テスト用別アプリ（%APPDATA%\\GokaGoTest）。必ず _ENV=staging（本番 DB に繋がない）。

BETA_CHANNEL_VERSION
  _APP_EDITION が beta のときだけ有効。埋め込む APP_VERSION 文字列（例 2.0.0）。
  空なら igo/constants.py の APP_VERSION をそのまま使う。

CLIENT_UPDATE_CHECK_URL
  起動時に取得するバージョンマニフェスト（JSON）の HTTPS URL。
  空文字（既定）= 更新チェックしない。URL ありのとき、新バージョン検知で
  スピナー付きの案内を表示し、「はい」でダウンロード〜再起動まで行う。
"""

_ENV = "production"
_APP_EDITION = "release"
BETA_CHANNEL_VERSION = ""
# 既定は自動更新なし（Azure 等で ZIP を手配する運用向け）
CLIENT_UPDATE_CHECK_URL = ""

#!/bin/bash
# ステージングサーバーセットアップスクリプト
# GCE VM上で一度だけ実行する。以降はsystemdで自動起動。
#
# 使い方:
#   chmod +x tools/staging_setup.sh
#   sudo bash tools/staging_setup.sh
#
# 前提条件:
#   - 本番サーバーが /home/user/goka-go-releases で動作中
#   - Python 3 と pip が使える状態

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAGING_PORT=8001
STAGING_DB="${REPO_DIR}/igo_users_staging.db"
STAGING_SETTINGS="${REPO_DIR}/app_settings_staging.json"
SERVICE_NAME="goka-staging"

echo "=== 碁華 ステージングサーバーセットアップ ==="
echo "リポジトリ: ${REPO_DIR}"
echo "ポート: ${STAGING_PORT}"
echo "DB: ${STAGING_DB}"
echo ""

# systemd サービスファイルを作成
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Goka GO Staging Server (port ${STAGING_PORT})
After=network.target

[Service]
Type=simple
User=${SUDO_USER:-$(whoami)}
WorkingDirectory=${REPO_DIR}
Environment=GOKA_PORT=${STAGING_PORT}
Environment=GOKA_DB_PATH=${STAGING_DB}
Environment=GOKA_SETTINGS_PATH=${STAGING_SETTINGS}
Environment=GOKA_ENV=staging
Environment=GOKA_GIT_BRANCH=main
ExecStart=$(which python3) ${REPO_DIR}/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "systemd サービスファイルを作成しました: /etc/systemd/system/${SERVICE_NAME}.service"

# サービスを有効化して起動
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl start ${SERVICE_NAME}

echo ""
echo "=== セットアップ完了 ==="
echo "ステージングサーバーが起動しました。"
echo ""
echo "コマンド一覧:"
echo "  状態確認:  sudo systemctl status ${SERVICE_NAME}"
echo "  ログ確認:  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  再起動:    sudo systemctl restart ${SERVICE_NAME}"
echo "  停止:      sudo systemctl stop ${SERVICE_NAME}"
echo ""
echo "ステージング API: http://localhost:${STAGING_PORT}"
echo "ステージング WS:  ws://localhost:${STAGING_PORT}"
echo ""
echo "GCE ファイアウォールでポート ${STAGING_PORT} を開放してください:"
echo "  gcloud compute firewall-rules create goka-staging \\"
echo "    --allow=tcp:${STAGING_PORT} --target-tags=goka-server"

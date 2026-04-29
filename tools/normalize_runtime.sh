#!/usr/bin/env bash
set -euo pipefail

# 通常運用へ戻すための最小固定化スクリプト
# 目的:
# - systemd の実行実体を確認
# - server.py をディスク上でバックアップ/配置
# - 再起動後ヘルスチェック
#
# 使い方:
#   sudo bash tools/normalize_runtime.sh \
#     --service goka-server.service \
#     --app-dir /home/ubuntu/goka-go-releases \
#     --source /home/ubuntu/goka-go-releases/server_saved_20260430_044952.py \
#     --health-url http://127.0.0.1:8000/api/runtime-info

SERVICE="goka-server.service"
APP_DIR=""
SOURCE_FILE=""
HEALTH_URL="http://127.0.0.1:8000/api/settings"
LOG_DIR="/var/tmp/gokago-normalize"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --app-dir) APP_DIR="$2"; shift 2 ;;
    --source) SOURCE_FILE="$2"; shift 2 ;;
    --health-url) HEALTH_URL="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/normalize_${STAMP}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== normalize_runtime start: $STAMP ==="
echo "service=$SERVICE"

echo "[1/7] systemd 定義確認"
systemctl show "$SERVICE" -p ExecStart -p WorkingDirectory -p User
systemctl cat "$SERVICE" || true

if [[ -z "$APP_DIR" ]]; then
  APP_DIR="$(systemctl show "$SERVICE" -p WorkingDirectory --value | tr -d '\r')"
fi

if [[ -z "$APP_DIR" || ! -d "$APP_DIR" ]]; then
  echo "ERROR: app-dir not found: $APP_DIR" >&2
  exit 1
fi

cd "$APP_DIR"
echo "resolved app_dir=$APP_DIR"

if [[ -z "$SOURCE_FILE" ]]; then
  SOURCE_FILE="$APP_DIR/server.py"
fi
if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "ERROR: source file not found: $SOURCE_FILE" >&2
  exit 1
fi

echo "[2/7] 既存 server.py を退避"
if [[ -f "$APP_DIR/server.py" ]]; then
  cp "$APP_DIR/server.py" "$APP_DIR/server.py.disk_backup.${STAMP}"
fi

echo "[3/7] 新しい server.py を配置"
cp "$SOURCE_FILE" "$APP_DIR/server.py"

echo "[4/7] ハッシュ記録"
sha256sum "$APP_DIR/server.py" | tee "$APP_DIR/server.py.sha256.${STAMP}.txt"
ls -l "$APP_DIR/server.py"

echo "[5/7] サービス再起動"
systemctl daemon-reload
systemctl restart "$SERVICE"
systemctl status "$SERVICE" --no-pager -l || true

echo "[6/7] ポート待受確認"
ss -lntp | grep -E '8000|:80|:443' || true

echo "[7/7] ヘルスチェック: $HEALTH_URL"
curl -fsS -i "$HEALTH_URL"

echo "=== normalize_runtime done ==="
echo "log=$LOG_FILE"

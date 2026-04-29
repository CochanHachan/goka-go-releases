#!/usr/bin/env bash
set -euo pipefail

# 本番稼働の事実確認（証跡採取）スクリプト
# 使い方:
#   sudo bash tools/collect_runtime_facts.sh --service goka-server.service

SERVICE="goka-server.service"
OUT_DIR="/var/tmp/gokago-facts"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$OUT_DIR/runtime_facts_${STAMP}.txt"

{
  echo "=== runtime facts: $STAMP ==="
  echo
  echo "--- whoami ---"
  whoami
  echo
  echo "--- hostname ---"
  hostname
  echo
  echo "--- service show ---"
  systemctl show "$SERVICE" -p ExecStart -p WorkingDirectory -p User -p Environment
  echo
  echo "--- service unit ---"
  systemctl cat "$SERVICE"
  echo
  echo "--- service status ---"
  systemctl status "$SERVICE" --no-pager -l || true
  echo
  echo "--- processes ---"
  ps -eo pid,lstart,cmd | grep -E "server.py|uvicorn|$SERVICE" | grep -v grep || true
  echo
  echo "--- listen ports ---"
  ss -lntp | grep -E '8000|:80|:443' || true
  echo
  APP_DIR="$(systemctl show "$SERVICE" -p WorkingDirectory --value | tr -d '\r')"
  if [[ -n "${APP_DIR}" && -d "${APP_DIR}" ]]; then
    echo "--- app dir listing ---"
    ls -la "$APP_DIR"
    echo
    if [[ -f "$APP_DIR/server.py" ]]; then
      echo "--- server.py stat ---"
      stat "$APP_DIR/server.py"
      echo
      echo "--- server.py sha256 ---"
      sha256sum "$APP_DIR/server.py"
      echo
    fi
  fi
  echo "--- local health checks ---"
  curl -sS -i http://127.0.0.1:8000/api/runtime-info || true
  echo
  curl -sS -i http://127.0.0.1:8000/api/settings || true
} > "$OUT_FILE" 2>&1

echo "$OUT_FILE"

#!/usr/bin/env bash
# 本番 VM 上で実行: git の origin を Azure Repos に切り替え、指定ブランチをディスク上に反映する。
#
# 事前準備（いずれか）:
#   - PAT: echo 'https://{user}:{PAT}@dev.azure.com/...' は ~/.netrc や credential helper で管理
#   - または SSH リモート URL に差し替え
#
# 使い方:
#   export GOKA_AZURE_REPO_URL='https://dev.azure.com/kokimatsuura0812/goka-go/_git/goka-go'
#   export GOKA_GIT_BRANCH=main
#   sudo -u 実行ユーザー bash tools/server_bind_to_azure.sh
#
set -euo pipefail

AZURE_URL="${GOKA_AZURE_REPO_URL:-https://dev.azure.com/kokimatsuura0812/goka-go/_git/goka-go}"
BRANCH="${GOKA_GIT_BRANCH:-main}"

if [[ -n "${GOKA_REPO_DIR:-}" ]]; then
  REPO_ROOT="$GOKA_REPO_DIR"
elif SERVICE="$(systemctl show goka-server.service -p WorkingDirectory --value 2>/dev/null)"; then
  REPO_ROOT="${SERVICE:-}"
fi

if [[ -z "${REPO_ROOT:-}" || ! -d "$REPO_ROOT" ]]; then
  echo "作業ディレクトリを決められません。GOKA_REPO_DIR を設定するか、goka-server.service の WorkingDirectory を確認してください。" >&2
  exit 1
fi

cd "$REPO_ROOT"
echo "[1/5] repo: $REPO_ROOT"
echo "[2/5] git remote set-url origin -> $AZURE_URL"
git remote set-url origin "$AZURE_URL"
git remote -v
echo "[3/5] fetch origin ($BRANCH)"
git fetch origin "$BRANCH"
echo "[4/5] checkout + reset --hard origin/$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
echo "[5/5] verify"
git rev-parse HEAD
test -f server.py && sha256sum server.py || true
echo "完了。systemd 再起動: sudo systemctl restart goka-server.service"

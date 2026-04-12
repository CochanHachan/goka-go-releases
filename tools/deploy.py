"""
碁華 デプロイツール (CLI版)
============================
ブラウザやGUIを一切開かずに、PRマージ＋ワークフロー実行＋サーバーデプロイを行うスクリプト。

使い方:
  python deploy.py                  # 全PRマージ＋ワークフロー実行＋サーバーデプロイ
  python deploy.py --merge-only     # 全PRマージのみ（ビルドなし）
  python deploy.py --merge-select   # PR選択マージのみ（ビルドなし）
  python deploy.py --run-only 1.2.5 # ワークフロー実行のみ（バージョン指定）
  python deploy.py --server-only    # サーバーデプロイのみ

初回実行時にGitHubトークンの入力を求められます（gh_token.txt に自動保存）。
"""

import base64
import urllib.request
import urllib.error
import json
import os
import sys
import time

REPO = "CochanHachan/goka-go-releases"
API_BASE = f"https://api.github.com/repos/{REPO}"
WORKFLOW_NAME = "Build and Deploy"

# サーバーデプロイ設定
SERVER_URL = "http://34.24.176.248:8000"
ADMIN_TOKEN = "goka-deploy-2026"


def get_token():
    """GitHub トークンを取得（環境変数 → gh_token.txt → 入力）"""
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token

    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh_token.txt")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if token:
            return token

    # 対話入力
    print("=" * 50)
    print("GitHub トークンが見つかりません。")
    print("引き継ぎ書に記載のトークンを入力してください。")
    print("=" * 50)
    token = input("GitHub トークン: ").strip()
    if not token:
        print("トークンが入力されませんでした。終了します。")
        sys.exit(1)

    # 保存（owner-only permissions）
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    print(f"トークンを {token_file} に保存しました。次回から自動読み込みされます。")
    return token


def api_request(method, path, token, data=None):
    """GitHub API リクエスト"""
    url = f"{API_BASE}/{path}" if not path.startswith("http") else path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API エラー ({e.code}): {error_body}")


def _fetch_open_prs(token):
    """オープンPR一覧を取得して返す"""
    print("\n--- オープンPR一覧を取得中 ---")
    prs = api_request("GET", "pulls?state=open&sort=created&direction=asc", token)
    if not prs:
        print("オープンPRはありません。")
    return prs or []


def _merge_prs(token, prs):
    """指定されたPRリストをマージして成功件数を返す"""
    merged = 0
    for pr in prs:
        num = pr["number"]
        try:
            print(f"\nPR #{num} をマージ中... ", end="", flush=True)
            api_request("PUT", f"pulls/{num}/merge", token, {
                "merge_method": "merge"
            })
            print("OK")
            # ブランチ削除
            branch = pr["head"]["ref"]
            try:
                api_request("DELETE", f"git/refs/heads/{branch}", token)
            except Exception:
                pass  # ブランチ削除失敗は無視
            merged += 1
        except Exception as e:
            print(f"失敗: {e}")
    return merged


def merge_all_prs(token):
    """全オープンPRをマージ"""
    prs = _fetch_open_prs(token)
    if not prs:
        return 0

    print(f"{len(prs)}件のオープンPRが見つかりました:")
    for pr in prs:
        print(f"  #{pr['number']}: {pr['title']}")

    merged = _merge_prs(token, prs)
    print(f"\n{merged}/{len(prs)}件のPRをマージしました。")
    return merged


def merge_select_prs(token):
    """対話的にPRを選択してマージ"""
    prs = _fetch_open_prs(token)
    if not prs:
        return 0

    print(f"\n{len(prs)}件のオープンPRがあります:")
    for i, pr in enumerate(prs, 1):
        print(f"  [{i}] #{pr['number']}: {pr['title']}")
    print(f"  [a] 全てマージ")
    print(f"  [q] キャンセル")

    print("\nマージするPRの番号を入力 (カンマ区切りで複数可, 例: 1,3,5):")
    choice = input("> ").strip().lower()

    if choice == "q" or not choice:
        print("キャンセルしました。")
        return 0

    if choice == "a":
        selected = prs
    else:
        seen = set()
        indices = []
        for part in choice.replace(" ", "").split(","):
            try:
                idx = int(part)
                if 1 <= idx <= len(prs):
                    if (idx - 1) not in seen:
                        seen.add(idx - 1)
                        indices.append(idx - 1)
                else:
                    print(f"無効な番号: {part} (1〜{len(prs)}を指定してください)")
                    return 0
            except ValueError:
                print(f"無効な入力: {part}")
                return 0
        selected = [prs[i] for i in indices]

    if not selected:
        print("選択されたPRがありません。")
        return 0

    print(f"\n以下の{len(selected)}件をマージします:")
    for pr in selected:
        print(f"  #{pr['number']}: {pr['title']}")

    confirm = input("\n実行しますか？ (y/N): ").strip().lower()
    if confirm != "y":
        print("キャンセルしました。")
        return 0

    merged = _merge_prs(token, selected)
    print(f"\n{merged}/{len(selected)}件のPRをマージしました。")
    return merged


def get_version_from_repo(token):
    """version.json から現在のバージョンを取得"""
    try:
        result = api_request("GET", "contents/version.json", token)
        content = base64.b64decode(result["content"]).decode("utf-8")
        data = json.loads(content)
        return data.get("version", "")
    except Exception:
        return ""


def run_workflow(token, version=None):
    """Build and Deploy ワークフローを実行"""
    print("\n--- ワークフロー実行 ---")

    # ワークフローID取得
    workflows = api_request("GET", "actions/workflows", token)
    wf_id = None
    for wf in workflows.get("workflows", []):
        if wf["name"] == WORKFLOW_NAME:
            wf_id = wf["id"]
            break

    if not wf_id:
        print(f"エラー: ワークフロー '{WORKFLOW_NAME}' が見つかりません。")
        return False

    # バージョン未指定の場合、ワークフローの自動インクリメントに任せる
    if not version:
        current = get_version_from_repo(token)
        if current:
            parts = current.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            next_version = ".".join(parts)
            print(f"現在のバージョン: {current} → 次のバージョン: {next_version}（自動インクリメント）")
        else:
            print("バージョン: 自動インクリメント")

    display_version = version if version else "自動インクリメント"
    print(f"ワークフロー '{WORKFLOW_NAME}' を実行中 (バージョン: {display_version})... ", end="", flush=True)
    try:
        api_request("POST", f"actions/workflows/{wf_id}/dispatches", token, {
            "ref": "main",
            "inputs": {"version": version or ""}
        })
        print("OK")
        print(f"ワークフローが開始されました。完了まで約10〜15分かかります。")
        print(f"進捗確認: https://github.com/{REPO}/actions")
        return True
    except Exception as e:
        print(f"失敗: {e}")
        return False


def wait_for_workflow(token):
    """最新のワークフロー実行の完了を待機"""
    print("\n--- ワークフロー完了を待機中 ---")
    print("(Ctrl+Cで待機をスキップできます)")

    try:
        for i in range(60):  # 最大30分待機
            time.sleep(30)
            runs = api_request("GET", "actions/runs?per_page=1", token)
            if runs.get("workflow_runs"):
                run = runs["workflow_runs"][0]
                status = run["status"]
                conclusion = run.get("conclusion", "")
                elapsed = (i + 1) * 30
                minutes = elapsed // 60
                seconds = elapsed % 60
                print(f"  [{minutes:02d}:{seconds:02d}] 状態: {status}", end="")
                if conclusion:
                    print(f" / 結果: {conclusion}")
                    if conclusion == "success":
                        print("\nワークフローが正常に完了しました!")
                        return True
                    else:
                        print(f"\nワークフローが失敗しました。")
                        print(f"詳細: https://github.com/{REPO}/actions/runs/{run['id']}")
                        return False
                else:
                    print(" (実行中...)", flush=True)
    except KeyboardInterrupt:
        print("\n待機をスキップしました。")
        print(f"進捗確認: https://github.com/{REPO}/actions")
        return None

    print("タイムアウト: 30分以上経過しました。")
    return None


def deploy_server():
    """サーバーに git pull + 再起動を指示"""
    print("\n--- サーバーデプロイ ---")
    print(f"サーバー: {SERVER_URL}")

    # まずステータス確認
    try:
        req = urllib.request.Request(
            f"{SERVER_URL}/admin/status",
            headers={"X-Token": ADMIN_TOKEN},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = json.loads(resp.read().decode("utf-8"))
        online = status.get("online_users", 0)
        pid = status.get("pid", "?")
        print(f"  現在の状態: PID={pid}, オンライン={online}人")
    except Exception as e:
        print(f"  警告: ステータス確認失敗 ({e})")

    # デプロイ実行
    print("  デプロイ中... ", end="", flush=True)
    try:
        req = urllib.request.Request(
            f"{SERVER_URL}/admin/update",
            headers={"X-Token": ADMIN_TOKEN},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        status = result.get("status", "unknown")
        if status == "updating":
            print("OK (サーバー再起動中)")
        elif status == "no_change":
            print("OK (変更なし・再起動不要)")
        elif status == "error":
            print(f"失敗: {result.get('git', result.get('detail', ''))}")
            return False
        else:
            print(f"OK ({status})")
    except Exception as e:
        # サーバー再起動中は接続が切れるのが正常
        print("OK (サーバー再起動中)")

    # 再起動待機
    print("  サーバー再起動を待機中... ", end="", flush=True)
    for i in range(12):  # 最大60秒待機
        time.sleep(5)
        try:
            req = urllib.request.Request(
                f"{SERVER_URL}/admin/status",
                headers={"X-Token": ADMIN_TOKEN},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                new_status = json.loads(resp.read().decode("utf-8"))
            new_pid = new_status.get("pid", "?")
            print(f"OK (PID={new_pid})")
            return True
        except Exception:
            pass
    print("タイムアウト")
    return False


def main():
    args = sys.argv[1:]
    merge_only = "--merge-only" in args
    merge_select = "--merge-select" in args
    run_only = "--run-only" in args
    server_only = "--server-only" in args
    no_wait = "--no-wait" in args
    version = None

    # --run-only の次の引数をバージョンとして取得
    if run_only:
        idx = args.index("--run-only")
        if idx + 1 < len(args) and not args[idx + 1].startswith("--"):
            version = args[idx + 1]

    print("=" * 50)
    print("  碁華 デプロイツール (CLI版)")
    print(f"  リポジトリ: {REPO}")
    print(f"  サーバー: {SERVER_URL}")
    print("=" * 50)

    # サーバーデプロイのみモード
    if server_only:
        deploy_server()
        print("\n完了!")
        return

    token = get_token()

    # PR選択マージモード
    if merge_select:
        merge_select_prs(token)
        deploy_server()
        print("\n完了!")
        return

    # PRマージ
    if not run_only:
        merged = merge_all_prs(token)
        if merged > 0 and not merge_only:
            print("\nマージ完了。3秒後にワークフローを実行します...")
            time.sleep(3)

    # ワークフロー実行
    if not merge_only:
        started = run_workflow(token, version)
        if started and not no_wait:
            wait_for_workflow(token)

    # サーバーデプロイ（マージ後は常に実行）
    if not run_only:
        deploy_server()

    print("\n完了!")


if __name__ == "__main__":
    main()

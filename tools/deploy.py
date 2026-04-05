"""
碁華 デプロイツール (CLI版)
============================
ブラウザやGUIを一切開かずに、PRマージ＋ワークフロー実行を行うスクリプト。

使い方:
  python deploy.py                  # 全PRマージ＋ワークフロー実行
  python deploy.py --merge-only     # PRマージのみ
  python deploy.py --run-only 1.2.5 # ワークフロー実行のみ（バージョン指定）

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


def merge_all_prs(token):
    """全オープンPRをマージ"""
    print("\n--- オープンPR一覧を取得中 ---")
    prs = api_request("GET", "pulls?state=open&sort=created&direction=asc", token)

    if not prs:
        print("オープンPRはありません。")
        return 0

    print(f"{len(prs)}件のオープンPRが見つかりました:")
    for pr in prs:
        print(f"  #{pr['number']}: {pr['title']}")

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

    print(f"\n{merged}/{len(prs)}件のPRをマージしました。")
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


def main():
    args = sys.argv[1:]
    merge_only = "--merge-only" in args
    run_only = "--run-only" in args
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
    print("=" * 50)

    token = get_token()

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

    print("\n完了!")


if __name__ == "__main__":
    main()

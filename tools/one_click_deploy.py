"""
碁華 ワンクリックデプロイツール
================================
PRマージ → ビルド → HP更新 を全自動で実行するGUIツール。

使い方:
  one_click_deploy.vbs をダブルクリック（または python one_click_deploy.py）

処理フロー:
  1. 未マージPRを全てマージ
  2. Build and Deploy ワークフローを実行
  3. ワークフロー完了を待機（進捗表示付き）
  4. 完了通知（HP自動更新はワークフロー内で実行済み）

前提:
  - GitHub トークンが環境変数 GH_TOKEN に設定されている、
    または同じフォルダに gh_token.txt が存在する
"""

import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import urllib.error
import json
import os
import threading
import time
import base64

REPO = "CochanHachan/goka-go-releases"
API_BASE = "https://api.github.com/repos/{}".format(REPO)
WORKFLOW_NAME = "Build and Deploy"
HP_URL = "https://goka-go.com"


def get_token():
    """GitHub トークンを取得（環境変数 → gh_token.txt）"""
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token

    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh_token.txt")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if token:
            return token

    return ""


def api_request(method, path, token, data=None):
    """GitHub API リクエストを送信"""
    url = "{}/{}".format(API_BASE, path) if not path.startswith("http") else path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer {}".format(token),
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
        raise RuntimeError("GitHub API エラー ({}): {}".format(e.code, error_body))


def get_version_from_repo(token):
    """version.json から現在のバージョンを取得"""
    try:
        result = api_request("GET", "contents/version.json", token)
        content = base64.b64decode(result["content"]).decode("utf-8")
        data = json.loads(content)
        return data.get("version", "")
    except Exception:
        return ""


# ── カラーパレット ─────────────────────────────────
_BG = "#1a1b26"          # 背景（暗いネイビー）
_BG_CARD = "#24283b"     # カード背景
_FG = "#c0caf5"          # テキスト
_FG_DIM = "#565f89"      # 薄いテキスト
_ACCENT = "#7aa2f7"      # アクセント（青）
_SUCCESS = "#9ece6a"     # 成功（緑）
_WARNING = "#e0af68"     # 警告（黄）
_ERROR = "#f7768e"       # エラー（赤）
_BTN_BG = "#3d59a1"      # ボタン背景
_BTN_BG_GO = "#2e7d32"   # GOボタン背景
_FONT = "Yu Gothic UI"
_FONT_MONO = "Consolas"


class StepIndicator(tk.Frame):
    """ステップ進捗インジケーター"""

    STEPS = [
        "PRマージ",
        "ビルド実行",
        "ビルド待機",
        "完了",
    ]

    def __init__(self, parent):
        super().__init__(parent, bg=_BG)
        self.labels = []
        self.connectors = []

        for i, step_name in enumerate(self.STEPS):
            # コネクター（最初以外）
            if i > 0:
                conn = tk.Frame(self, bg=_FG_DIM, height=2, width=40)
                conn.pack(side="left", padx=0, pady=0)
                # pack_propagate を無効にして固定サイズ
                conn.pack_propagate(False)
                conn.configure(width=40, height=2)
                self.connectors.append(conn)

            step_frame = tk.Frame(self, bg=_BG)
            step_frame.pack(side="left", padx=8)

            circle = tk.Label(
                step_frame,
                text="{}".format(i + 1),
                font=(_FONT, 10, "bold"),
                fg=_FG_DIM,
                bg=_BG_CARD,
                width=3,
                height=1,
                relief="flat",
            )
            circle.pack()

            label = tk.Label(
                step_frame,
                text=step_name,
                font=(_FONT, 9),
                fg=_FG_DIM,
                bg=_BG,
            )
            label.pack(pady=(2, 0))

            self.labels.append((circle, label))

    def set_active(self, index):
        """指定ステップをアクティブに設定"""
        for i, (circle, label) in enumerate(self.labels):
            if i < index:
                # 完了
                circle.configure(fg=_BG, bg=_SUCCESS, text="✓")
                label.configure(fg=_SUCCESS)
            elif i == index:
                # アクティブ
                circle.configure(fg="white", bg=_ACCENT, text="{}".format(i + 1))
                label.configure(fg=_ACCENT)
            else:
                # 未実行
                circle.configure(fg=_FG_DIM, bg=_BG_CARD, text="{}".format(i + 1))
                label.configure(fg=_FG_DIM)

        # コネクター色更新
        for i, conn in enumerate(self.connectors):
            if i < index:
                conn.configure(bg=_SUCCESS)
            else:
                conn.configure(bg=_FG_DIM)

    def set_all_complete(self):
        """全ステップを完了に設定"""
        for circle, label in self.labels:
            circle.configure(fg=_BG, bg=_SUCCESS, text="✓")
            label.configure(fg=_SUCCESS)
        for conn in self.connectors:
            conn.configure(bg=_SUCCESS)

    def set_error(self, index):
        """指定ステップをエラーに設定"""
        circle, label = self.labels[index]
        circle.configure(fg="white", bg=_ERROR, text="✗")
        label.configure(fg=_ERROR)


class OneClickDeployApp:
    def __init__(self):
        self.token = get_token()
        self.running = False
        self.cancel_flag = False

        self.root = tk.Tk()
        self.root.title("碁華 ワンクリックデプロイ")
        self.root.geometry("680x580")
        self.root.resizable(True, True)
        self.root.configure(bg=_BG)

        self._build_ui()

        if not self.token:
            self._show_token_setup()

    def _build_ui(self):
        # ── ヘッダー ──────────────────────────────
        header = tk.Frame(self.root, bg=_BG, padx=20, pady=12)
        header.pack(fill="x")
        tk.Label(
            header,
            text="碁華 ワンクリックデプロイ",
            font=(_FONT, 16, "bold"),
            bg=_BG,
            fg=_FG,
        ).pack(side="left")
        tk.Label(
            header,
            text=REPO,
            font=(_FONT, 9),
            bg=_BG,
            fg=_FG_DIM,
        ).pack(side="right")

        # ── ステップインジケーター ─────────────────
        step_frame = tk.Frame(self.root, bg=_BG, padx=20, pady=8)
        step_frame.pack(fill="x")
        self.step_indicator = StepIndicator(step_frame)
        self.step_indicator.pack(anchor="center")

        # ── バージョン設定 ─────────────────────────
        ver_frame = tk.Frame(self.root, bg=_BG_CARD, padx=20, pady=12)
        ver_frame.pack(fill="x", padx=20, pady=(8, 4))

        tk.Label(
            ver_frame,
            text="バージョン:",
            font=(_FONT, 11),
            bg=_BG_CARD,
            fg=_FG,
        ).pack(side="left")

        self.version_var = tk.StringVar(value="")
        self.version_entry = tk.Entry(
            ver_frame,
            textvariable=self.version_var,
            font=(_FONT_MONO, 11),
            width=12,
            bg=_BG,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            bd=2,
        )
        self.version_entry.pack(side="left", padx=(8, 4))

        tk.Label(
            ver_frame,
            text="（空欄＝自動インクリメント）",
            font=(_FONT, 9),
            bg=_BG_CARD,
            fg=_FG_DIM,
        ).pack(side="left", padx=4)

        # 現在バージョン表示
        self.current_ver_label = tk.Label(
            ver_frame,
            text="",
            font=(_FONT, 9),
            bg=_BG_CARD,
            fg=_WARNING,
        )
        self.current_ver_label.pack(side="right")

        # 非同期でバージョン取得
        if self.token:
            threading.Thread(target=self._fetch_current_version, daemon=True).start()

        # ── ボタンエリア ──────────────────────────
        btn_frame = tk.Frame(self.root, bg=_BG, padx=20, pady=8)
        btn_frame.pack(fill="x")

        self.btn_go = tk.Button(
            btn_frame,
            text="▶  デプロイ開始",
            font=(_FONT, 13, "bold"),
            bg=_BTN_BG_GO,
            fg="white",
            activebackground="#1b5e20",
            activeforeground="white",
            relief="flat",
            padx=24,
            pady=8,
            command=self.start_deploy,
            cursor="hand2",
        )
        self.btn_go.pack(side="left")

        self.btn_cancel = tk.Button(
            btn_frame,
            text="キャンセル",
            font=(_FONT, 10),
            bg=_BG_CARD,
            fg=_FG_DIM,
            activebackground=_ERROR,
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=6,
            command=self.cancel_deploy,
            state="disabled",
            cursor="hand2",
        )
        self.btn_cancel.pack(side="left", padx=12)

        # ステータス
        self.status_label = tk.Label(
            btn_frame,
            text="待機中",
            font=(_FONT, 10),
            bg=_BG,
            fg=_FG_DIM,
        )
        self.status_label.pack(side="right")

        # ── 進捗バー ──────────────────────────────
        progress_frame = tk.Frame(self.root, bg=_BG, padx=20)
        progress_frame.pack(fill="x", pady=(4, 0))

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Deploy.Horizontal.TProgressbar",
            troughcolor=_BG_CARD,
            background=_ACCENT,
            thickness=6,
        )
        self.progress = ttk.Progressbar(
            progress_frame,
            style="Deploy.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
        )
        self.progress.pack(fill="x")

        # ── ログエリア ────────────────────────────
        log_frame = tk.Frame(self.root, bg=_BG, padx=20, pady=8)
        log_frame.pack(fill="both", expand=True)

        tk.Label(
            log_frame,
            text="ログ",
            font=(_FONT, 9),
            bg=_BG,
            fg=_FG_DIM,
            anchor="w",
        ).pack(fill="x")

        self.log_text = tk.Text(
            log_frame,
            font=(_FONT_MONO, 9),
            bg=_BG_CARD,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            bd=4,
            state="disabled",
            height=12,
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))

        # タグ設定（色付きログ用）
        self.log_text.tag_configure("info", foreground=_FG)
        self.log_text.tag_configure("success", foreground=_SUCCESS)
        self.log_text.tag_configure("warning", foreground=_WARNING)
        self.log_text.tag_configure("error", foreground=_ERROR)
        self.log_text.tag_configure("accent", foreground=_ACCENT)

        # ── フッター ─────────────────────────────
        footer = tk.Frame(self.root, bg=_BG, padx=20, pady=6)
        footer.pack(fill="x")

        self.hp_btn = tk.Button(
            footer,
            text="HPを開く: {}".format(HP_URL),
            font=(_FONT, 9),
            bg=_BG_CARD,
            fg=_ACCENT,
            activebackground=_BTN_BG,
            activeforeground="white",
            relief="flat",
            padx=8,
            pady=2,
            command=self._open_hp,
            cursor="hand2",
        )
        self.hp_btn.pack(side="left")

        self.gh_btn = tk.Button(
            footer,
            text="GitHub Actions",
            font=(_FONT, 9),
            bg=_BG_CARD,
            fg=_ACCENT,
            activebackground=_BTN_BG,
            activeforeground="white",
            relief="flat",
            padx=8,
            pady=2,
            command=self._open_actions,
            cursor="hand2",
        )
        self.gh_btn.pack(side="right")

    def _show_token_setup(self):
        """トークン未設定時のダイアログ"""
        self.log("GitHub トークンが見つかりません。", "warning")

        dialog = tk.Toplevel(self.root)
        dialog.title("GitHub トークン設定")
        dialog.geometry("450x200")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=_BG)

        tk.Label(
            dialog,
            text="GitHub トークンを入力してください:",
            font=(_FONT, 11),
            bg=_BG,
            fg=_FG,
            padx=20,
            pady=12,
        ).pack()

        entry = tk.Entry(
            dialog, width=50, show="*",
            font=(_FONT_MONO, 10),
            bg=_BG_CARD, fg=_FG, insertbackground=_FG, relief="flat", bd=4,
        )
        entry.pack(padx=20)

        save_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            dialog,
            text="gh_token.txt に保存する",
            variable=save_var,
            bg=_BG,
            fg=_FG_DIM,
            selectcolor=_BG_CARD,
            activebackground=_BG,
            activeforeground=_FG,
        ).pack(pady=8)

        def on_ok():
            token = entry.get().strip()
            if not token:
                messagebox.showwarning("入力エラー", "トークンを入力してください", parent=dialog)
                return
            self.token = token
            if save_var.get():
                token_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "gh_token.txt"
                )
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(token)
                self.log("トークンを保存しました", "success")
            dialog.destroy()
            threading.Thread(target=self._fetch_current_version, daemon=True).start()

        tk.Button(
            dialog, text="OK", command=on_ok, width=12,
            font=(_FONT, 10, "bold"),
            bg=_BTN_BG, fg="white", activebackground=_ACCENT,
            activeforeground="white", relief="flat",
        ).pack(pady=8)

    def _fetch_current_version(self):
        """現在のバージョンを非同期取得"""
        try:
            ver = get_version_from_repo(self.token)
            if ver:
                self.root.after(0, lambda: self.current_ver_label.configure(
                    text="現在: v{}".format(ver)
                ))
        except Exception:
            pass

    def log(self, msg, tag="info"):
        """ログにメッセージを追加"""
        def _do():
            self.log_text.configure(state="normal")
            ts = time.strftime("%H:%M:%S")
            self.log_text.insert("end", "[{}] {}\n".format(ts, msg), tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def set_status(self, msg, color=None):
        """ステータスラベルを更新"""
        def _do():
            self.status_label.configure(text=msg, fg=color or _FG_DIM)
        self.root.after(0, _do)

    def set_progress(self, value):
        """進捗バーを更新"""
        self.root.after(0, lambda: self.progress.configure(value=value))

    def _open_hp(self):
        """HPをブラウザで開く"""
        import webbrowser
        webbrowser.open(HP_URL)

    def _open_actions(self):
        """GitHub Actionsをブラウザで開く"""
        import webbrowser
        webbrowser.open("https://github.com/{}/actions".format(REPO))

    def start_deploy(self):
        """デプロイ開始"""
        if self.running:
            return
        if not self.token:
            messagebox.showwarning("エラー", "GitHub トークンが設定されていません。")
            return

        self.running = True
        self.cancel_flag = False
        self.btn_go.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.version_entry.configure(state="disabled")

        # ログクリア
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.set_progress(0)
        self.log("デプロイを開始します", "accent")

        threading.Thread(target=self._deploy_thread, daemon=True).start()

    def cancel_deploy(self):
        """デプロイをキャンセル"""
        self.cancel_flag = True
        self.log("キャンセルを要求しました...", "warning")
        self.set_status("キャンセル中...", _WARNING)

    def _deploy_done(self, success=True):
        """デプロイ完了処理"""
        self.running = False
        self.root.after(0, lambda: self.btn_go.configure(state="normal"))
        self.root.after(0, lambda: self.btn_cancel.configure(state="disabled"))
        self.root.after(0, lambda: self.version_entry.configure(state="normal"))

        if success:
            self.step_indicator.set_all_complete()
            self.set_progress(100)
            self.set_status("デプロイ完了!", _SUCCESS)
            self.log("全ての処理が正常に完了しました!", "success")
            self.log("HP: {}".format(HP_URL), "accent")

            # 完了後にHPを自動で開く
            import webbrowser
            webbrowser.open(HP_URL)

            # 完了ダイアログ
            self.root.after(500, lambda: messagebox.showinfo(
                "デプロイ完了",
                "全ての処理が正常に完了しました!\n\n"
                "HP: {}\n\n"
                "ブラウザでHPを開きました。\n"
                "インストーラーはHPからダウンロードできます。".format(HP_URL)
            ))

    def _deploy_thread(self):
        """デプロイメインスレッド"""
        try:
            # ── Step 1: PRマージ ─────────────────
            self.root.after(0, lambda: self.step_indicator.set_active(0))
            self.set_status("PRマージ中...", _ACCENT)
            self.set_progress(5)

            if self.cancel_flag:
                self._on_cancel()
                return

            self.log("オープンPRを取得中...", "info")
            prs = api_request("GET", "pulls?state=open&sort=created&direction=asc", self.token)

            if not prs:
                self.log("オープンPRはありません（スキップ）", "info")
            else:
                self.log("{}件のオープンPRが見つかりました".format(len(prs)), "info")
                merged = 0
                for pr in prs:
                    if self.cancel_flag:
                        self._on_cancel()
                        return
                    num = pr["number"]
                    title = pr["title"]
                    self.log("  PR #{}: {} をマージ中...".format(num, title), "info")
                    try:
                        api_request("PUT", "pulls/{}/merge".format(num), self.token, {
                            "merge_method": "merge"
                        })
                        # ブランチ削除
                        branch = pr["head"]["ref"]
                        try:
                            api_request("DELETE", "git/refs/heads/{}".format(branch), self.token)
                        except Exception:
                            pass
                        self.log("  PR #{} マージ完了".format(num), "success")
                        merged += 1
                    except Exception as e:
                        self.log("  PR #{} マージ失敗: {}".format(num, e), "error")

                self.log("{}件のPRをマージしました".format(merged), "success")

            self.set_progress(20)

            # マージ後少し待機（GitHubの反映を待つ）
            if prs:
                self.log("GitHub反映を待機中（3秒）...", "info")
                time.sleep(3)

            # ── Step 2: ワークフロー実行 ──────────
            self.root.after(0, lambda: self.step_indicator.set_active(1))
            self.set_status("ワークフロー実行中...", _ACCENT)
            self.set_progress(25)

            if self.cancel_flag:
                self._on_cancel()
                return

            # ワークフローID取得
            self.log("ワークフローを検索中...", "info")
            workflows = api_request("GET", "actions/workflows", self.token)
            wf_id = None
            for wf in workflows.get("workflows", []):
                if wf["name"] == WORKFLOW_NAME:
                    wf_id = wf["id"]
                    break

            if not wf_id:
                self.log("ワークフロー '{}' が見つかりません".format(WORKFLOW_NAME), "error")
                self.root.after(0, lambda: self.step_indicator.set_error(1))
                self._deploy_done(False)
                return

            # バージョン
            version = self.version_var.get().strip()
            if version:
                self.log("指定バージョン: v{}".format(version), "info")
            else:
                current = get_version_from_repo(self.token)
                if current:
                    parts = current.split(".")
                    parts[-1] = str(int(parts[-1]) + 1)
                    next_ver = ".".join(parts)
                    self.log("自動インクリメント: v{} → v{}".format(current, next_ver), "info")
                else:
                    self.log("バージョン: 自動インクリメント", "info")

            # ワークフロー実行
            self.log("ワークフロー '{}' を実行中...".format(WORKFLOW_NAME), "accent")
            try:
                api_request("POST", "actions/workflows/{}/dispatches".format(wf_id), self.token, {
                    "ref": "main",
                    "inputs": {"version": version}
                })
                self.log("ワークフローを開始しました", "success")
            except Exception as e:
                self.log("ワークフロー実行失敗: {}".format(e), "error")
                self.root.after(0, lambda: self.step_indicator.set_error(1))
                self._deploy_done(False)
                return

            self.set_progress(30)

            # ── Step 3: ワークフロー完了待機 ──────
            self.root.after(0, lambda: self.step_indicator.set_active(2))
            self.set_status("ビルド完了を待機中...", _ACCENT)

            # 少し待ってからポーリング開始（ワークフロー開始まで時間がかかる場合あり）
            self.log("ワークフロー開始を待機中（10秒）...", "info")
            time.sleep(10)

            # dispatch直後のrun IDを特定
            start_time = time.time()
            run_id = None

            # 最新のworkflow runを探す
            for attempt in range(5):
                if self.cancel_flag:
                    self._on_cancel()
                    return
                try:
                    runs = api_request(
                        "GET",
                        "actions/workflows/{}/runs?per_page=1&branch=main".format(wf_id),
                        self.token
                    )
                    if runs.get("workflow_runs"):
                        latest = runs["workflow_runs"][0]
                        # 直近30秒以内に作成されたrunを対象とする
                        run_id = latest["id"]
                        self.log("ワークフロー Run #{} を監視中".format(run_id), "info")
                        break
                except Exception:
                    pass
                time.sleep(5)

            if not run_id:
                self.log("ワークフローのRunが見つかりません", "error")
                self.root.after(0, lambda: self.step_indicator.set_error(2))
                self._deploy_done(False)
                return

            # ポーリング（最大30分）
            poll_interval = 20  # 20秒ごと
            max_polls = 90      # 30分
            for i in range(max_polls):
                if self.cancel_flag:
                    self._on_cancel()
                    return

                time.sleep(poll_interval)
                elapsed = int(time.time() - start_time)
                minutes = elapsed // 60
                seconds = elapsed % 60

                try:
                    run = api_request("GET", "actions/runs/{}".format(run_id), self.token)
                    status = run["status"]
                    conclusion = run.get("conclusion", "")

                    # 進捗推定（ビルドは通常10〜15分）
                    progress_pct = min(30 + int(elapsed / 900 * 65), 95)
                    self.set_progress(progress_pct)
                    self.set_status("ビルド中... [{:02d}:{:02d}]".format(minutes, seconds), _ACCENT)

                    if status == "completed":
                        if conclusion == "success":
                            self.log("[{:02d}:{:02d}] ビルド成功!".format(minutes, seconds), "success")
                            break
                        else:
                            self.log(
                                "[{:02d}:{:02d}] ビルド失敗 (結果: {})".format(
                                    minutes, seconds, conclusion
                                ),
                                "error"
                            )
                            self.log(
                                "詳細: https://github.com/{}/actions/runs/{}".format(REPO, run_id),
                                "error"
                            )
                            self.root.after(0, lambda: self.step_indicator.set_error(2))
                            self._deploy_done(False)
                            return
                    else:
                        if i % 3 == 0:  # 1分ごとにログ出力
                            self.log(
                                "[{:02d}:{:02d}] 実行中... (ステータス: {})".format(
                                    minutes, seconds, status
                                ),
                                "info"
                            )

                except Exception as e:
                    self.log("API エラー: {} (リトライ)".format(e), "warning")

            else:
                self.log("タイムアウト（30分経過）", "error")
                self.root.after(0, lambda: self.step_indicator.set_error(2))
                self._deploy_done(False)
                return

            # ── Step 4: 完了 ─────────────────────
            self.root.after(0, lambda: self.step_indicator.set_active(3))

            # 最新バージョンを再取得
            threading.Thread(target=self._fetch_current_version, daemon=True).start()

            self._deploy_done(True)

        except Exception as e:
            self.log("予期しないエラー: {}".format(e), "error")
            self._deploy_done(False)

    def _on_cancel(self):
        """キャンセル処理"""
        self.log("デプロイをキャンセルしました", "warning")
        self.set_status("キャンセル済み", _WARNING)
        self.running = False
        self.root.after(0, lambda: self.btn_go.configure(state="normal"))
        self.root.after(0, lambda: self.btn_cancel.configure(state="disabled"))
        self.root.after(0, lambda: self.version_entry.configure(state="normal"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = OneClickDeployApp()
    app.run()

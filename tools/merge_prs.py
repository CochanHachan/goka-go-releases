"""
碁華 PRマージツール
===================
Devinが作成したPRをワンクリックでマージするGUIツール。

使い方:
  1. merge_prs.vbs をダブルクリック（またはpython merge_prs.py を実行）
  2. 一覧からマージしたいPRを選択
  3.「選択したPRをマージ」または「全てマージ」ボタンをクリック

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

REPO = "CochanHachan/goka-go-releases"
API_BASE = f"https://api.github.com/repos/{REPO}"


def get_token():
    """GitHub トークンを取得する（環境変数 → gh_token.txt → gh CLI config）"""
    # 1. 環境変数
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token

    # 2. 同じフォルダの gh_token.txt
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh_token.txt")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if token:
            return token

    return ""


def api_request(method, path, token, data=None):
    """GitHub API リクエストを送信"""
    url = f"{API_BASE}/{path}" if not path.startswith("http") else path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
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


class MergePRApp:
    def __init__(self):
        self.token = get_token()
        self.prs = []

        self.root = tk.Tk()
        self.root.title("碁華 PRマージツール")
        self.root.geometry("700x450")
        self.root.resizable(True, True)

        self._build_ui()

        if not self.token:
            self._show_token_setup()
        else:
            self.refresh()

    def _build_ui(self):
        # ヘッダー
        header = tk.Frame(self.root, bg="#2d333b", padx=10, pady=8)
        header.pack(fill="x")
        tk.Label(
            header, text="碁華 PRマージツール", font=("", 14, "bold"),
            bg="#2d333b", fg="white"
        ).pack(side="left")
        tk.Label(
            header, text=f"リポジトリ: {REPO}", font=("", 9),
            bg="#2d333b", fg="#8b949e"
        ).pack(side="right")

        # ツールバー
        toolbar = tk.Frame(self.root, padx=10, pady=5)
        toolbar.pack(fill="x")

        self.btn_refresh = tk.Button(
            toolbar, text="更新", command=self.refresh, width=8
        )
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_merge_selected = tk.Button(
            toolbar, text="選択したPRをマージ", command=self.merge_selected,
            bg="#238636", fg="white", width=18
        )
        self.btn_merge_selected.pack(side="left", padx=5)

        self.btn_merge_all = tk.Button(
            toolbar, text="全てマージ", command=self.merge_all,
            bg="#1f6feb", fg="white", width=12
        )
        self.btn_merge_all.pack(side="left", padx=5)

        self.status_label = tk.Label(toolbar, text="", fg="#586069", font=("", 9))
        self.status_label.pack(side="right")

        # PRリスト
        list_frame = tk.Frame(self.root, padx=10, pady=5)
        list_frame.pack(fill="both", expand=True)

        columns = ("number", "title", "author", "status")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", selectmode="extended"
        )
        self.tree.heading("number", text="#")
        self.tree.heading("title", text="タイトル")
        self.tree.heading("author", text="作成者")
        self.tree.heading("status", text="状態")
        self.tree.column("number", width=50, anchor="center")
        self.tree.column("title", width=400)
        self.tree.column("author", width=120)
        self.tree.column("status", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ログエリア
        log_frame = tk.Frame(self.root, padx=10, pady=10)
        log_frame.pack(fill="x")
        self.log_text = tk.Text(log_frame, height=4, font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill="x")

    def _show_token_setup(self):
        """トークン未設定時の案内"""
        self.log("GitHub トークンが見つかりません。")
        self.log("以下のいずれかの方法で設定してください:")
        self.log("  1. 環境変数 GH_TOKEN を設定")
        self.log("  2. tools/gh_token.txt にトークンを記載")

        # トークン入力ダイアログ
        dialog = tk.Toplevel(self.root)
        dialog.title("GitHub トークン設定")
        dialog.geometry("450x180")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="GitHub トークンを入力してください:", padx=10, pady=10).pack()
        entry = tk.Entry(dialog, width=50, show="*")
        entry.pack(padx=10)

        save_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            dialog, text="gh_token.txt に保存する（次回から自動読み込み）",
            variable=save_var
        ).pack(pady=5)

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
                self.log(f"トークンを {token_path} に保存しました")
            dialog.destroy()
            self.refresh()

        tk.Button(dialog, text="OK", command=on_ok, width=10).pack(pady=10)

    def log(self, msg):
        """ログエリアにメッセージを追加"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_status(self, msg):
        self.status_label.configure(text=msg)

    def refresh(self):
        """オープンPR一覧を取得"""
        self.set_status("取得中...")
        self.btn_refresh.configure(state="disabled")

        def _fetch():
            try:
                prs = api_request("GET", "pulls?state=open&sort=created&direction=desc", self.token)
                self.prs = prs
                self.root.after(0, lambda: self._update_list(prs))
            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_list(self, prs):
        self.tree.delete(*self.tree.get_children())
        for pr in prs:
            author = pr["user"]["login"]
            mergeable = "オープン"
            self.tree.insert("", "end", values=(
                f"#{pr['number']}", pr["title"], author, mergeable
            ))
        count = len(prs)
        self.set_status(f"オープンPR: {count}件")
        self.btn_refresh.configure(state="normal")
        if count == 0:
            self.log("オープンPRはありません。")
        else:
            self.log(f"{count}件のオープンPRを取得しました。")

    def _on_error(self, msg):
        self.set_status("エラー")
        self.btn_refresh.configure(state="normal")
        self.log(f"エラー: {msg}")

    def _get_selected_pr_numbers(self):
        """選択されたPR番号のリストを返す"""
        numbers = []
        for item in self.tree.selection():
            vals = self.tree.item(item, "values")
            num = int(vals[0].replace("#", ""))
            numbers.append(num)
        return numbers

    def merge_selected(self):
        """選択したPRをマージ"""
        numbers = self._get_selected_pr_numbers()
        if not numbers:
            messagebox.showinfo("選択なし", "マージするPRを選択してください。")
            return
        self._do_merge(numbers)

    def merge_all(self):
        """全てのオープンPRをマージ"""
        if not self.prs:
            messagebox.showinfo("PRなし", "オープンPRがありません。")
            return
        numbers = [pr["number"] for pr in self.prs]
        if not messagebox.askyesno(
            "確認", f"{len(numbers)}件のPRを全てマージしますか？"
        ):
            return
        self._do_merge(numbers)

    def _do_merge(self, pr_numbers):
        """指定したPR番号をマージ"""
        self.btn_merge_selected.configure(state="disabled")
        self.btn_merge_all.configure(state="disabled")
        self.set_status("マージ中...")

        def _merge():
            success = 0
            failed = 0
            for num in pr_numbers:
                try:
                    self.root.after(0, lambda n=num: self.log(f"PR #{n} をマージ中..."))
                    api_request("PUT", f"pulls/{num}/merge", self.token, {
                        "merge_method": "merge"
                    })
                    self.root.after(0, lambda n=num: self.log(f"PR #{n} をマージしました。"))
                    success += 1
                except Exception as e:
                    self.root.after(0, lambda n=num, err=str(e): self.log(
                        f"PR #{n} のマージに失敗: {err}"
                    ))
                    failed += 1

            def _done():
                self.btn_merge_selected.configure(state="normal")
                self.btn_merge_all.configure(state="normal")
                msg = f"完了: {success}件マージ"
                if failed:
                    msg += f", {failed}件失敗"
                self.set_status(msg)
                self.log(msg)
                self.refresh()

            self.root.after(0, _done)

        threading.Thread(target=_merge, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MergePRApp()
    app.run()

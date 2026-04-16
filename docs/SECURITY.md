# 碁華（Goka Go）セキュリティ対策ガイド（運用者向け）

この文書は、GitHubアカウントやリポジトリが不審に見えたときに **最初の15分でやるべきこと**、さらに **通知やインシデントの“起き方自体”を減らす事前予防**、そして継続的に **事故確率を下げる設定** をまとめたものです。

---

## 0. まず結論（最優先）

不審な Personal Access Token（PAT）作成通知が届いた／覚えのない操作がある場合は、次の順で実施してください。

1. **残存PATを全て確認し、不要なら即 Revoke（無効化）**
2. **Security log（セキュリティログ）で、作成・削除の前後イベントを確認**
3. **セッションを疑い、パスワード変更（必要なら）**
4. **2要素認証（2FA）を有効化（未設定なら最優先）**
5. **OAuth Apps / GitHub Apps の権限を棚卸し（不要は解除）**
6. **Collaborators / Deploy keys / Actions secrets を棚卸し**

---

## 1. 今日やること（チェックリスト）

### 1.1 PAT（classic / fine-grained）の棚卸し

GitHub: `Settings` → `Developer settings` → `Personal access tokens`

- **classic**: 権限が広くなりがち。**不要なら全Revoke**が最速で安全
- **fine-grained**: 可能ならこちらへ移行し、**最小権限 + 短期間 + 単一リポジトリ**に限定

運用ルール（推奨）:

- **PATを頻繁に作り直す運用は避ける**（通知が増えるだけでなく、漏洩面も増える）
- CI/CDは原則 **`GITHUB_TOKEN` / OIDC / Deploy keys** で完結させ、個人PATに依存しない

### 1.2 Security log の確認（「誰が」「何を」したか）

GitHub: `Settings` → `Security log`

確認ポイント:

- `personal_access_token.create` / `personal_access_token.delete`
- `oauth_authorization.*`
- `repo.create_deploy_key` / `public_key.create`
- `user.two_factor_enabled` / `user.password_changed`
- 不審なIP・端末・時刻がないか

### 1.3 セッションと認証の見直し

GitHub: `Settings` → `Sessions`（表示名はUIにより異なる場合あり）

- 未知の端末/地域のセッションがあれば **全サインアウト**
- ブラウザ拡張（特にGitHub連携系）を疑う場合は **無効化して再確認**

### 1.4 OAuth Apps / GitHub Apps

GitHub: `Settings` → `Applications`

- **Authorized OAuth apps**: 不要・不明なものは解除
- **Installed GitHub Apps**（Organizationの場合はOrg設定側も）: 権限が大きいものは見直し

### 1.5 リポジトリ側（このプロジェクト）

GitHub: リポジトリ `Settings`

最低限:

- **Collaborators**: 不要な人を外す
- **Deploy keys**: 不要な鍵を削除（読み取り専用でもリスクは残る）
- **Actions secrets**: 漏洩疑いがあるなら **ローテーション**（APIキー、署名用資格情報など）

---

## 2. 継続的な対策（「勝手に変わる」を減らす）

### 2.1 `main` の保護（最重要）

GitHub: `Settings` → `Branches` → Branch protection rules（`main`）

推奨設定の例:

- **Require a pull request before merging**
- **Require approvals**（最低1）
- **Restrict who can push to matching branches**
- **Do not allow bypassing the above settings**
- **Block force pushes**

目的:

- 第三者・連携ツール・誤操作による **直接push** を止める

### 2.2 変更の可視化

- **CODEOWNERS** を置き、重要ファイルはレビュー必須にする
- 重要変更は **PR本文に理由・影響範囲・ロールバック手順**を書く

### 2.3 リリースと秘密情報

- リリース成果物（ZIP/EXE）に **秘密情報を同梱しない**
- サーバー側の管理トークン等は **GitHub Secrets** に限定し、ローカルやチャットに置かない

### 2.4 事前予防：「不審メールが届く前」にできる安全策（重要）

ここで言う「届かないようにする」は、**セキュリティ上必要な通知まで無効化する**ことではありません。  
現実的には、GitHubはアカウントの重要操作に対して **メール通知を送る設計**があり、特に **PATの作成/削除**は通知が出やすいです。

したがって方針は次の2段です。

- **A. そもそも“通知のトリガー”を減らす（根本対策）**
- **B. 通知は残しつつ、誤認・フィッシングを減らす（運用対策）**

#### A. 通知トリガーを減らす（おすすめ順）

1) **Personal Access Token（PAT）を使わない運用に寄せる**

PATは「作るたびに通知が来やすい」ので、CIやローカル運用を次へ寄せます。

- GitHub Actions: **`GITHUB_TOKEN`**
- クラウド連携: **GitHub App**（最小権限）や **OIDC**（可能なら）
- どうしても必要なら: **Fine-grained token** + **最短有効期限** + **単一リポジトリ** + **read-only寄りの権限**

2) **試行錯誤でPATを量産しない**

`goka-fix2` のように番号が進むのは、多くの場合 **自動化/手元スクリプトのリトライ**です。  
運用ルールとして「失敗したら権限を広げて作り直す」を禁止し、**1本のトークンを設計し直す**方が安全です。

3) **人間のアカウントからの直接変更を減らす**

- `main` は **PR必須 + レビュー必須**
- 連携Botは **専用の最小権限Botアカウント**に寄せる（可能なら）

4) **不要な連携（OAuth/GitHub Apps）を入れない／残さない**

連携が増えるほど、「見覚えのない操作」が起きる表面積が増えます。

#### B. 通知は残しつつ、被害と誤認を減らす

1) **2FAを必須化**（アカウント乗っ取りの入口を塞ぐ）

2) **フィッシング耐性**

- メール本文のリンクを踏まず、毎回 **`github.com` の公式画面**から設定へ入る
- 可能なら **パスキー**や **WebAuthn** を優先

3) **通知の整理（注意：セキュリティ通知まで消すのは非推奨）**

GitHubの通知設定は用途に合わせて調整できますが、**セキュリティ系は残す**のが原則です。  
「迷惑だから全部オフ」は、逆に **侵害に気づくのが遅れる**ので避けてください。

---

## 3. このリポジトリ特有の注意（運用上の落とし穴）

### 3.1 「staging」と「production」の取り違え

クライアントは `igo/constants_env.py` の `_ENV` と `igo/constants.py` の設定で接続先が切り替わります。

- **stagingでないのにstaging扱い**、逆に **本番に接続している**と、ログイン失敗やDB不一致が起きます
- 配布物は **固定URLの staging ZIP** と **本番ZIP** を混同しない運用にする

### 3.2 自動化Bot（例: Devin 連携）がある場合

Bot/連携アプリは「人間の指示なしにPRやコミットを作る」ことがあります。

対策:

- 連携が不要なら **解除**
- 必要なら **最小権限 + 対象リポジトリ限定 + branch protection**

---

## 4. インシデントが疑われる場合の追加対応

次のいずれかが起きたら、上記に加えて実施してください。

- リポジトリに見覚えのないコミットがある
- 秘密情報がコミットされた可能性がある
- PATが大量作成された

追加:

- **GitHub Support に相談**（必要に応じて）
- **漏洩した可能性のある秘密情報は即ローテーション**（APIキー、DB、署名鍵など）
- 影響範囲の調査として **`git log` / GitHubのAudit log**で時系列を固定する

---

## 5. 最小の「安全な日常運用」テンプレ

- **個人PATは原則使わない**
- **変更はPR経由**
- **本番リリースは手動承認**
- **stagingは固定URLで配布**
- **セキュリティ通知は即確認（放置しない）**

---

## 6. 連絡・記録

インシデント対応中は、次を残すと後追いが楽です。

- 発覚時刻（JST）
- 実施した操作（Revokeしたトークン名、解除したApp名）
- Security logで気になったイベント（種類と時刻）

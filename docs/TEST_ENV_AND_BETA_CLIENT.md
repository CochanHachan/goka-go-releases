# テスト用 DB・ステージング API・テスト版クライアント配布

本番と分離した検証用 DB / API と、テスト版（beta）クライアントのビルド・配布手順です。  
**本運用は GitHub に依存せず、ZIP を手動配布する想定です（起動時の自動更新は既定で無効）。**

## 1. テスト用 DB（SQLite）

- 本番と**必ず別ファイル**にする（例: `igo_users.db` と `igo_users_staging.db` / `igo_users_test.db`）。
- サーバーは `GOKA_DB_PATH` で DB ファイルを指定します（`server.py` 先頭付近）。

### 空のテスト DB をローカルで作る

`uvicorn` / `fastapi` は不要です（標準ライブラリのみ）。リポジトリルートで:

```bash
python tools/init_test_db.py
```

別パスを指定する場合:

```bash
python tools/init_test_db.py C:\path\to\igo_users_staging.db
```

### ステージング用プロセスで使う

`/admin/setup-staging` が起動するステージング側では、別ディレクトリの `igo_users_staging.db` と `GOKA_ENV=staging`・ポート `8001` を使う想定です。手動起動する場合の例:

```bash
set GOKA_DB_PATH=C:\goka-staging\igo_users_staging.db
set GOKA_PORT=8001
set GOKA_ENV=staging
python server.py
```

（Linux の場合は `export`。）

## 2. ステージング API の URL（クライアント）

`igo/constants.py` の `_SERVER_CONFIG["staging"]` がテスト版クライアントの接続先です。ステージング VM の IP やドメインが変わったら、**本番と取り違えないよう**ここを更新し、`STAGING_LABEL` と URL の整合チェック（`_validate_env`）が通ることを確認してください。

## 3. 更新チェック（本番ユーザー向け・任意）

`igo/constants_env.py` の **`CLIENT_UPDATE_CHECK_URL`** が空（既定）のとき、起動時のバージョンチェックは行いません。

HTTPS で version 用 JSON（`version` / `download_url` / `release_notes`）を返す URL を設定すると、新バージョン検知時に**スピナー付きの案内**が自動表示され、**「はい」**でダウンロード・解凍・上書き・再起動まで進みます（「後でする」または閉じるでログイン画面へ）。

## 4. テスト版クライアント（beta）のビルド設定

- `igo/constants_env.py` で `_ENV=staging`、`_APP_EDITION=beta`、`BETA_CHANNEL_VERSION` を設定します。
- CI では `tools/patch_constants_for_beta.py` を使います。

```bash
python tools/patch_constants_for_beta.py 2.0.1
```

**注意:** パッチ後の `constants_env.py` を本番リリース用ブランチにそのままマージしないでください。ビルド専用ブランチまたは CI 上の作業ディレクトリでのみ実行する運用を推奨します。

## 5. 配布（Azure Pipelines）

`azure-pipelines-beta-client.yml` を登録し、「実行」時にパラメータ **betaVersion** を指定します。Windows エージェントでテスト版 ZIP をビルドし、**パイプライン成果物（artifact 名 `goka-go-beta`）**からダウンロードして配布してください。

共通の補助スクリプト（手元でも同じ順で実行可能）:

| スクリプト | 役割 |
|------------|------|
| `tools/init_test_db.py` | テスト用 SQLite に `users` スキーマを作成（`server.init_db` と同じ DDL） |
| `tools/patch_constants_for_beta.py` | `constants_env` を staging + beta に変更 |
| `tools/download_katago_for_windows_build.py` | KataGo を `./katago` に展開 |
| `tools/copy_katago_into_dist.py` | `dist/goka_go/katago` へコピー |
| `tools/make_beta_zip.py` | `dist/goka-go-beta.zip` を生成 |

## 6. 本番サーバーからステージング一式を用意する

本番で `POST /admin/setup-staging`（管理者トークン付き）を呼ぶと、別クローン・別 DB パス・ポート `8001` でステージング起動の補助が行われます。初回前に、上記 `init_test_db` 相当でステージング用 DB が存在する／作成されることを確認してください。

## チェックリスト（配布前）

1. ステージング API が `constants.py` の staging URL と一致している。
2. ステージングが参照する DB が本番ファイルと別である。
3. 手動配布のみなら `CLIENT_UPDATE_CHECK_URL` が空である（または意図した URL だけが入っている）。
4. 本番用 `constants_env.py`（`release` + `production`）が誤って beta 用パッチされていない。

# リリース自動化（ZIP + version.json を FTP で配置）

手作業で Xserver に ZIP を上げたり `version.json` を編集したりせず、**Azure Pipelines だけ**でステージング → 本番まで流します。

## 用意するもの

1. **YAML パイプライン**  
   リポジトリの `azure-pipelines-release.yml` を Azure DevOps に登録する（手動実行のみ）。

2. **FTP 変数**（既存の `azure-pipelines.yml` の web デプロイと同じでよい）  
   `FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`, `GOKA_FTP_REMOTE`（例: `public_html`）, `GOKA_FTP_TLS`

3. **本番デプロイ前の「人間の確認」**（推奨）  
   Azure DevOps → **Pipelines → Environments** → 名前 `goka-igo-production` を作成し、  
   **Approvals and checks** で承認者を付ける。  
   パイプラインはステージング FTP まで自動で進み、本番 FTP の直前で待機する。承認後にだけ本番の `version.json` と `releases/` が更新される。

   承認を付けない場合は、ステージング成功後すぐに本番も上書きされる（完全自動）。

## パイプラインの動き

| 順番 | 内容 |
|------|------|
| 1 | Windows エージェントで PyInstaller ビルド → `goka_go_<ver>.zip` / `goka_admin_<ver>.zip` |
| 2 | FTPS で **ステージング**へ: `…/staging/version.json` と `…/staging/releases/*.zip` |
| 3 | （環境の承認があれば待ち）FTPS で **本番**へ: `…/version.json` と `…/releases/*.zip` |

公開 URLは `PUBLIC_BASE`（既定 `https://goka-igo.com`）とパス接頭辞から組み立てる。

## テスト用クライアントの version URL

本番クライアントは `CLIENT_UPDATE_CHECK_URL = https://goka-igo.com/version.json` の想定。

ステージングで更新確認だけ行う場合は、**テスト用ビルド**の `CLIENT_UPDATE_CHECK_URL` を  
`https://goka-igo.com/staging/version.json` にしておく（`stagingPathPrefix` の既定は `staging`）。

## 実行方法

Pipelines で該当パイプラインを **Run pipeline** し、`releaseVersion`（例 `1.2.162`）を指定する。  
`releaseNotes` は任意。

# 碁華 DB定義書ドラフト（PostgreSQL専用）

最終更新: 2026-04-29  
状態: 確定版 v2（レビュー反映）

## 1. 目的と方針

- SQLite を完全廃止し、`PostgreSQL` 専用に一本化する。
- `app_settings.json` などのファイル設定を廃止し、設定値は DB 管理へ移行する。
- `users` 1本集中を解消し、用途別テーブルへ分割する。
- 対局履歴・棋譜を `game_records` 系テーブルで永続化する。
- 運用で直接確認可能なよう、主キー・外部キー・一意制約・インデックスを明示する。

## 2. 現行実装の事実（洗い出し）

- `server.py` は現時点で SQLite/PostgreSQL 両対応（`GOKA_DB_BACKEND` 切替）。
- `init_db()` で自動作成されるのは実質 `users` テーブルのみ。
- グローバル設定（`board_frame_height` など4項目含む）は `app_settings.json` 保存。
- `game_records` は `server.py` では未実装（旧 `igo/database.py` 側に SQLite 実装あり）。
- 画面位置・列幅等は `igo/window_settings.py` の SQLite `ui_settings` で保存。

## 3. 論理データモデル（提案）

### 3.1 アカウント系

1) `users`（基本プロフィール）
- 1ユーザー1行。認証以外の基本属性を保持。

2) `user_auth`
- 認証情報を `users` から分離。

3) `user_stats`
- ログイン回数・対局回数・現在 Elo 等の統計値を分離。

4) `user_preferences`
- 言語等のユーザー選好を保持。

5) `user_ui_settings`
- 画面サイズ/位置、列幅、メニュー設定など「ユーザー別UI設定」を保持。
- ご指摘の「画面を閉じるときに保存し、次回起動で復元する」用途の本体テーブル。
- 現行 `igo/window_settings.py` の `ui_settings`（SQLite）を PostgreSQL に移す受け皿。
- 保存先は「JSONファイル」ではなく、DBテーブルの `setting_value JSONB` 列。

### 3.2 設定系

6) `app_settings`
- 旧 `app_settings.json` の置き換え。グローバル設定を単一テーブルで管理。
- `board_frame_height / match_apply_height / challenge_accept_height / sakura_dialog_height` を含む。

### 3.3 対局系

7) `games`
- 1対局1行。対局メタ情報（開始/終了、結果、勝者、持ち時間方式等）。

8) `game_players`
- 対局参加者（黒/白）を正規化して保持。

9) `game_records`
- SGF本文や手数等、保存対象の棋譜情報。

10) `game_events`（初期導入）
- 主要イベント監査（開始、中断、投了、切断）を保持。

11) `game_spectators`（必須）
- 誰がどの対局をいつ観戦したかを保持。
- 観戦履歴と同時接続制御の基盤。

12) `featured_games`（推奨）
- 注目対局のタイトル/説明/表示順/表示期間を管理。

13) `game_view_stats`（推奨）
- 対局ごとの閲覧統計（総閲覧数、同時観戦ピーク等）を保持。

### 3.4 セッション系（推奨）

14) `auth_sessions`
- 現状メモリ保持の `active_tokens` を永続化し、再起動耐性を持たせる。
- 生トークンではなく `token_hash` を保存する。

## 4. 物理設計（DDL案）

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 共通: updated_at 自動更新トリガー関数
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 1) users
CREATE TABLE IF NOT EXISTS users (
  id                BIGSERIAL PRIMARY KEY,
  handle_name       TEXT NOT NULL UNIQUE
                    CHECK (char_length(handle_name) BETWEEN 3 AND 50),
  real_name         TEXT NOT NULL
                    CHECK (char_length(real_name) BETWEEN 1 AND 100),
  email             TEXT NOT NULL DEFAULT ''
                    CHECK (char_length(email) <= 254),
  status            TEXT NOT NULL DEFAULT 'offline'
                    CHECK (status IN ('offline', 'online', 'matching', 'playing', 'spectating')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

-- email 重複防止（空文字は除外）
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
  ON users(email) WHERE email <> '';

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2) user_auth
CREATE TABLE IF NOT EXISTS user_auth (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash     TEXT NOT NULL,
  salt              TEXT NOT NULL,
  -- password_enc は Defense in Depth のため保持（詳細は本書 8章）
  password_enc      TEXT NOT NULL DEFAULT '',
  password_version  INTEGER NOT NULL DEFAULT 1,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_user_auth_updated_at
BEFORE UPDATE ON user_auth
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 3) user_stats
CREATE TABLE IF NOT EXISTS user_stats (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  elo               NUMERIC(7,2) NOT NULL DEFAULT 0,
  rank              TEXT NOT NULL DEFAULT '30級',
  rank_score        INTEGER NOT NULL DEFAULT -30,
  login_count       INTEGER NOT NULL DEFAULT 0 CHECK (login_count >= 0),
  match_count       INTEGER NOT NULL DEFAULT 0 CHECK (match_count >= 0),
  last_login_at     TIMESTAMPTZ NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_stats_elo ON user_stats(elo DESC);
CREATE INDEX IF NOT EXISTS idx_user_stats_rank_score ON user_stats(rank_score DESC);

CREATE TRIGGER trg_user_stats_updated_at
BEFORE UPDATE ON user_stats
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 4) user_preferences
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  language          TEXT NOT NULL DEFAULT 'ja',
  default_komi      NUMERIC(4,1) NOT NULL DEFAULT 7.5,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_user_preferences_updated_at
BEFORE UPDATE ON user_preferences
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 5) user_ui_settings (旧 ui_settings のDB化後継)
CREATE TABLE IF NOT EXISTS user_ui_settings (
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  screen_name       TEXT NOT NULL,
  setting_key       TEXT NOT NULL,
  setting_value     JSONB NOT NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, screen_name, setting_key)
);

CREATE INDEX IF NOT EXISTS idx_user_ui_settings_screen ON user_ui_settings(screen_name);

CREATE TRIGGER trg_user_ui_settings_updated_at
BEFORE UPDATE ON user_ui_settings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 想定レコード例（キー設計）
-- (user_id=101, screen_name='game',                setting_key='geometry',      setting_value='"1200x900+100+40"')
-- (user_id=101, screen_name='match_dialog_sam',    setting_key='column_widths', setting_value='[120,80,120,70]')
-- (user_id=101, screen_name='admin',               setting_key='column_widths', setting_value='[80,120,100,100,120]')
-- (user_id=101, screen_name='game',                setting_key='menu_state',    setting_value='{"ai_enabled":"on","byoyomi_voice":"off"}')

-- 位置・サイズの保存対象画面（初期）
-- - 碁盤画面:             screen_name='game'
-- - 対局申請画面:         screen_name='match_dialog_{handle}'
-- - 挑戦状受付画面:       screen_name='offer_dialog_{handle}'
-- - 棋譜一覧画面:         screen_name='kifu_dialog'
-- - 管理者画面:           screen_name='admin'
-- 各画面で setting_key='geometry' を保存し、必要に応じて column_widths/menu_state も併用する。

-- 6) app_settings (旧 app_settings.json の置換)
CREATE TABLE IF NOT EXISTS app_settings (
  id                      SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  theme                   TEXT NOT NULL DEFAULT 'light',
  offer_timeout_min       INTEGER NOT NULL DEFAULT 3 CHECK (offer_timeout_min BETWEEN 1 AND 120),
  fischer_main_time       INTEGER NOT NULL DEFAULT 300 CHECK (fischer_main_time BETWEEN 60 AND 7200),
  fischer_increment       INTEGER NOT NULL DEFAULT 10 CHECK (fischer_increment BETWEEN 1 AND 300),
  bot_offer_delay         INTEGER NOT NULL DEFAULT 30 CHECK (bot_offer_delay BETWEEN 10 AND 600),
  board_frame_height      NUMERIC(5,4) NOT NULL DEFAULT 0.78 CHECK (board_frame_height BETWEEN 0.10 AND 1.00),
  match_apply_height      NUMERIC(5,4) NOT NULL DEFAULT 0.40 CHECK (match_apply_height BETWEEN 0.10 AND 1.00),
  challenge_accept_height NUMERIC(5,4) NOT NULL DEFAULT 0.40 CHECK (challenge_accept_height BETWEEN 0.10 AND 1.00),
  sakura_dialog_height    NUMERIC(5,4) NOT NULL DEFAULT 0.36 CHECK (sakura_dialog_height BETWEEN 0.10 AND 1.00),
  session_expire_days     INTEGER NOT NULL DEFAULT 90 CHECK (session_expire_days BETWEEN 1 AND 365),
  session_idle_days       INTEGER NOT NULL DEFAULT 30 CHECK (session_idle_days BETWEEN 1 AND 180),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app_settings(id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TRIGGER trg_app_settings_updated_at
BEFORE UPDATE ON app_settings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 6-2) app_settings_history（設定変更履歴）
CREATE TABLE IF NOT EXISTS app_settings_history (
  id                BIGSERIAL PRIMARY KEY,
  app_settings_id   SMALLINT NOT NULL,
  changed_by_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  old_values        JSONB NOT NULL,
  new_values        JSONB NOT NULL,
  changed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION log_app_settings_history()
RETURNS trigger AS $$
BEGIN
  INSERT INTO app_settings_history(app_settings_id, changed_by_user_id, old_values, new_values, changed_at)
  VALUES (OLD.id, NULL, to_jsonb(OLD), to_jsonb(NEW), NOW());
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_app_settings_history
AFTER UPDATE ON app_settings
FOR EACH ROW EXECUTE FUNCTION log_app_settings_history();

-- 7) games
CREATE TABLE IF NOT EXISTS games (
  id                  BIGSERIAL PRIMARY KEY,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at            TIMESTAMPTZ NULL,
  status              TEXT NOT NULL DEFAULT 'finished',
  result              TEXT NOT NULL DEFAULT '',
  winner_user_id      BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  komi                NUMERIC(4,1) NOT NULL DEFAULT 7.5,
  move_count          INTEGER NOT NULL DEFAULT 0 CHECK (move_count >= 0),
  source              TEXT NOT NULL DEFAULT 'online',
  is_public           BOOLEAN NOT NULL DEFAULT TRUE,
  max_spectators      INTEGER NULL CHECK (max_spectators IS NULL OR max_spectators > 0),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_games_started_at ON games(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
CREATE INDEX IF NOT EXISTS idx_games_public ON games(is_public);

CREATE TRIGGER trg_games_updated_at
BEFORE UPDATE ON games
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 8) game_players
CREATE TABLE IF NOT EXISTS game_players (
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  color               CHAR(1) NOT NULL CHECK (color IN ('B', 'W')),
  rank_at_game        TEXT NOT NULL DEFAULT '',
  elo_at_game         NUMERIC(7,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (game_id, color),
  UNIQUE (game_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_game_players_user_id ON game_players(user_id);

-- 9) game_records (棋譜)
CREATE TABLE IF NOT EXISTS game_records (
  game_id             BIGINT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
  sgf_text            TEXT NOT NULL DEFAULT '',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_game_records_updated_at
BEFORE UPDATE ON game_records
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 10) game_events（初期導入）
CREATE TABLE IF NOT EXISTS game_events (
  id                  BIGSERIAL PRIMARY KEY,
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  event_type          TEXT NOT NULL,
  payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_events_game_id ON game_events(game_id);
CREATE INDEX IF NOT EXISTS idx_game_events_type ON game_events(event_type);

-- 11) auth_sessions（tokenハッシュ保存）
CREATE TABLE IF NOT EXISTS auth_sessions (
  id                  BIGSERIAL PRIMARY KEY,
  token_hash          TEXT NOT NULL UNIQUE,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at          TIMESTAMPTZ NOT NULL,
  last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked             BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);

CREATE TRIGGER trg_auth_sessions_updated_at
BEFORE UPDATE ON auth_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 12) game_spectators（観戦者管理・必須）
CREATE TABLE IF NOT EXISTS game_spectators (
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  left_at             TIMESTAMPTZ NULL,
  PRIMARY KEY (game_id, user_id, joined_at)
);

CREATE INDEX IF NOT EXISTS idx_game_spectators_game_id ON game_spectators(game_id);
CREATE INDEX IF NOT EXISTS idx_game_spectators_user_id ON game_spectators(user_id);

-- 13) featured_games（推奨）
CREATE TABLE IF NOT EXISTS featured_games (
  id                  BIGSERIAL PRIMARY KEY,
  game_id             BIGINT NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,
  title               TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
  description         TEXT NOT NULL DEFAULT '',
  sort_order          INTEGER NOT NULL DEFAULT 100,
  starts_at           TIMESTAMPTZ NULL,
  ends_at             TIMESTAMPTZ NULL,
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_featured_games_active ON featured_games(is_active, sort_order);

CREATE TRIGGER trg_featured_games_updated_at
BEFORE UPDATE ON featured_games
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 14) game_view_stats（推奨）
CREATE TABLE IF NOT EXISTS game_view_stats (
  game_id             BIGINT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
  total_views         BIGINT NOT NULL DEFAULT 0 CHECK (total_views >= 0),
  peak_concurrent     INTEGER NOT NULL DEFAULT 0 CHECK (peak_concurrent >= 0),
  current_concurrent  INTEGER NOT NULL DEFAULT 0 CHECK (current_concurrent >= 0),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_game_view_stats_updated_at
BEFORE UPDATE ON game_view_stats
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

## 5. APIとテーブルの対応（主要）

- `POST /api/register`
  - `users`, `user_auth`, `user_stats`, `user_preferences` へ INSERT。
- `POST /api/login`
  - `user_auth` 参照、`auth_sessions(token_hash)` 発行、`user_stats.login_count` 加算。
- `GET /api/users`
  - `users + user_stats + user_preferences` JOIN で返却。
- `PUT /api/user/{handle_name}/elo`
  - `user_stats.elo/rank/match_count` 更新。
- `PUT /api/settings`, `GET /api/settings`
  - `app_settings` の読書き（JSONファイル廃止）。
  - `UPDATE` 時に `app_settings_history` へ変更履歴を自動記録。
- `WS 対局確定時`
  - `games`, `game_players`, `game_records` へ保存。
- 観戦開始/離脱時
  - `game_spectators` と `game_view_stats` を更新。
- 注目対局管理
  - `featured_games` を管理者画面から更新（次フェーズAPI追加）。
- UI終了時/画面クローズ時の設定保存
  - `user_ui_settings` へ UPSERT（`geometry`, `column_widths`, `menu_state` など）。
- UI起動時/画面再表示時の設定復元
  - `user_ui_settings` から `user_id + screen_name + setting_key` で取得。

## 6. 移行方針（段階）

1) **Phase 0: 定義確定（本ドキュメントレビュー）**  
2) **Phase 1: スキーマ作成**（上記DDL適用）  
3) **Phase 2: データ移行**
- 既存 `users` を `users/user_auth/user_stats/user_preferences` へ分解移行。
- `app_settings.json` を `app_settings` に投入。
- `ui_settings.db` を `user_ui_settings` に移行。
4) **Phase 3: サーバ改修**
- `server.py` から SQLite import/分岐を削除。
- `GOKA_DB_BACKEND` 削除、PostgreSQL専用化。
- `active_tokens` を `auth_sessions` 化。
5) **Phase 4: 機能移行**
- `game_records` 保存APIを実装し、クライアント連携。
- 観戦機能（`game_spectators`, `games.is_public/max_spectators`）を実装。
- 必要最小の `game_events` 記録を実装。
6) **Phase 5: VPSデプロイ**
- `nginx + systemd + uvicorn` で本番化。

## 7. 進捗管理（週次）

- 今週の進捗
  - 本ドラフト作成（PostgreSQL専用方針、全データDB化方針を反映）。
- 今週の課題
  - `server.py` 現行仕様との互換方針決定（セッションTTL、WS保存タイミング）。
- 来週の予定
  - レビュー反映、DDL確定、Migration実装、PostgreSQL専用化開始。

## 8. セキュリティ仕様（確定）

- `password_enc` は保持する（Defense in Depth）。
- 想定暗号方式: `AES-256-GCM`（実装方式はライブラリ依存）。
- 鍵管理: 環境変数または Secrets 管理（例: Azure Key Vault）で配布。
- 復号は管理者機能など必要最小限の画面に限定し、監査ログ対象とする。
- `auth_sessions` は生トークンを保持せず、`token_hash`（SHA-256等）を保存する。
- セッション期限は `app_settings.session_expire_days` / `session_idle_days` で制御する。

## 9. JSONBフォーマット定義（レビュー固定）

本節は `user_ui_settings.setting_value (JSONB)` の保存形式をレビュー用に固定する。  
特記なき限り、読み書きは UPSERT（主キー: `user_id, screen_name, setting_key`）を前提とする。

### 9.1 setting_key ごとの型

- `geometry`
  - 型: `string`
  - 形式: `"WIDTHxHEIGHT+X+Y"`
  - 例: `"1200x900+100+40"`

- `column_widths`
  - 型: `array<number>`
  - 例: `[120, 80, 120, 70]`

- `match_conditions`
  - 型: `object`
  - スキーマ:
    - `main_time: string`（例 `"10分"`）
    - `byo_time: string`（例 `"30秒"`）
    - `byo_periods: string`（例 `"5回"`）
    - `komi: number`（例 `6.5`）
    - `winrate: boolean`（例 `true`）
  - 例:
    ```json
    {
      "main_time": "10分",
      "byo_time": "30秒",
      "byo_periods": "5回",
      "komi": 6.5,
      "winrate": true
    }
    ```

- `menu_state`（統合キー。実装時に導入）
  - 型: `object`
  - スキーマ:
    - `ai_enabled: string`（`"on"` or `"off"`）
    - `byoyomi_voice: string`（`"on"` or `"off"`）
    - `bot_main_time: string`（例 `"10分"`）
    - `bot_byo_time: string`（例 `"30秒"`）
    - `bot_byo_periods: string`（例 `"5回"`）
  - 例:
    ```json
    {
      "ai_enabled": "on",
      "byoyomi_voice": "off",
      "bot_main_time": "10分",
      "bot_byo_time": "30秒",
      "bot_byo_periods": "5回"
    }
    ```

- `admin_config`
  - 型: `object`
  - 例:
    ```json
    {
      "admin_env": "production",
      "theme": "light",
      "offer_timeout_min": 3,
      "bot_offer_delay": 30,
      "fischer_main_time": 300,
      "fischer_increment": 10,
      "default_main_time_min": 10,
      "default_byoyomi_sec": 30,
      "default_byoyomi_count": 5,
      "default_komi": 6.5,
      "board_frame_height": 0.78,
      "match_apply_height": 0.40,
      "challenge_accept_height": 0.40,
      "sakura_dialog_height": 0.36
    }
    ```

- `board_texture_{handle}`
  - 型: `string`
  - 例: `"wood_dark"`

### 9.2 screen_name 命名規約（固定）

- `game` / `game_{handle}`
- `match_dialog_{handle}`
- `offer_dialog_{handle}`
- `kifu_dialog`
- `admin`

### 9.3 バリデーション方針

- `geometry`: 正規表現 `^[0-9]+x[0-9]+\\+[0-9]+\\+[0-9]+$`
- `column_widths`: 要素は正整数、列数は画面定義に依存
- `match_conditions`: 必須キー欠落時は既定値を補完
- `admin_config`: 未知キーを許容（前方互換）

### 9.4 性能方針

- 本用途は `user_id + screen_name + setting_key` の点アクセスが主体のため、初期は PK のみで運用。
- 将来、JSON 内部検索が増える場合のみ `GIN (setting_value)` を追加検討する。

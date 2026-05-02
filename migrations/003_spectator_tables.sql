-- ============================================================
-- 碁華 DB マイグレーション: 003 観戦機能テーブル
-- 対象: PostgreSQL 14+
-- 説明: 観戦機能に必要なテーブルを追加する。
--   - live_game_state: 進行中対局のリアルタイム状態
--   - spectator_sessions: 観戦セッション管理
--   - saved_spectator_records: 観戦棋譜の保存
-- 実行: psql -d goka -f migrations/003_spectator_tables.sql
-- ============================================================

BEGIN;

-- ============================================================
-- 12) live_game_state（進行中対局のリアルタイム状態）
-- 対局開始時に作成、終局時に削除。
-- 観戦一覧画面で表示する手数・勝勢・観戦者数を保持する。
-- ============================================================
CREATE TABLE IF NOT EXISTS live_game_state (
  game_id             BIGINT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
  current_move_count  INTEGER NOT NULL DEFAULT 0 CHECK (current_move_count >= 0),
  black_win_rate      NUMERIC(5,2) NOT NULL DEFAULT 50.00 CHECK (black_win_rate BETWEEN 0 AND 100),
  white_win_rate      NUMERIC(5,2) NOT NULL DEFAULT 50.00 CHECK (white_win_rate BETWEEN 0 AND 100),
  spectator_count     INTEGER NOT NULL DEFAULT 0 CHECK (spectator_count >= 0),
  last_move_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_game_state_spectators ON live_game_state(spectator_count DESC);

-- ============================================================
-- 13) spectator_sessions（観戦セッション管理）
-- どのユーザーがどの対局を観戦中かを管理する。
-- 観戦開始時にINSERT、観戦終了時にDELETEまたはleft_atを設定。
-- ============================================================
CREATE TABLE IF NOT EXISTS spectator_sessions (
  id                  BIGSERIAL PRIMARY KEY,
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  left_at             TIMESTAMPTZ NULL,
  UNIQUE (game_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_spectator_sessions_game_id ON spectator_sessions(game_id);
CREATE INDEX IF NOT EXISTS idx_spectator_sessions_user_id ON spectator_sessions(user_id);

-- ============================================================
-- 14) saved_spectator_records（観戦棋譜の保存）
-- ユーザーが観戦した対局の棋譜を保存する。
-- ============================================================
CREATE TABLE IF NOT EXISTS saved_spectator_records (
  id                  BIGSERIAL PRIMARY KEY,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  sgf_text            TEXT NOT NULL DEFAULT '',
  memo                TEXT NOT NULL DEFAULT '',
  saved_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, game_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_spectator_records_user_id ON saved_spectator_records(user_id);

COMMIT;

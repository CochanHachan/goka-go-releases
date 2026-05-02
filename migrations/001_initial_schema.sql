-- ============================================================
-- 碁華 DB マイグレーション: 001 初期スキーマ
-- 対象: PostgreSQL 14+
-- 説明: SQLite からの移行先となる全 11 テーブルを作成する。
-- 実行: psql -d goka -f migrations/001_initial_schema.sql
-- ============================================================

BEGIN;

-- EXTENSION
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1) users（ユーザー基本プロフィール）
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id                BIGSERIAL PRIMARY KEY,
  handle_name       TEXT NOT NULL UNIQUE,
  real_name         TEXT NOT NULL,
  email             TEXT NOT NULL DEFAULT '',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 2) user_auth（ユーザー認証情報）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_auth (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash     TEXT NOT NULL,
  salt              TEXT NOT NULL,
  password_enc      TEXT NOT NULL DEFAULT '',
  password_version  INTEGER NOT NULL DEFAULT 1,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 3) user_stats（ユーザー統計値）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_stats (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  elo               DOUBLE PRECISION NOT NULL DEFAULT 0,
  rank              TEXT NOT NULL DEFAULT '30級',
  login_count       INTEGER NOT NULL DEFAULT 0 CHECK (login_count >= 0),
  match_count       INTEGER NOT NULL DEFAULT 0 CHECK (match_count >= 0),
  last_login_at     TIMESTAMPTZ NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_stats_elo ON user_stats(elo DESC);

-- ============================================================
-- 4) user_preferences（ユーザー選好）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  language          TEXT NOT NULL DEFAULT 'ja',
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 5) user_ui_settings（ユーザー別UI設定）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_ui_settings (
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  screen_name       TEXT NOT NULL,
  setting_key       TEXT NOT NULL,
  setting_value     JSONB NOT NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, screen_name, setting_key)
);

CREATE INDEX IF NOT EXISTS idx_user_ui_settings_screen ON user_ui_settings(screen_name);

-- ============================================================
-- 6) app_settings（アプリケーショングローバル設定）
-- ============================================================
CREATE TABLE IF NOT EXISTS app_settings (
  id                      SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  theme                   TEXT NOT NULL DEFAULT 'light',
  offer_timeout_min       INTEGER NOT NULL DEFAULT 3 CHECK (offer_timeout_min BETWEEN 1 AND 120),
  fischer_main_time       INTEGER NOT NULL DEFAULT 300 CHECK (fischer_main_time BETWEEN 60 AND 7200),
  fischer_increment       INTEGER NOT NULL DEFAULT 10 CHECK (fischer_increment BETWEEN 1 AND 300),
  bot_offer_delay         INTEGER NOT NULL DEFAULT 60 CHECK (bot_offer_delay BETWEEN 10 AND 600),
  board_frame_height      NUMERIC(5,4) NOT NULL DEFAULT 0.78 CHECK (board_frame_height BETWEEN 0.10 AND 1.00),
  match_apply_height      NUMERIC(5,4) NOT NULL DEFAULT 0.40 CHECK (match_apply_height BETWEEN 0.10 AND 1.00),
  challenge_accept_height NUMERIC(5,4) NOT NULL DEFAULT 0.40 CHECK (challenge_accept_height BETWEEN 0.10 AND 1.00),
  sakura_dialog_height    NUMERIC(5,4) NOT NULL DEFAULT 0.36 CHECK (sakura_dialog_height BETWEEN 0.10 AND 1.00),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- シングルトン行を保証
INSERT INTO app_settings(id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 7) games（対局メタ情報）
-- ============================================================
CREATE TABLE IF NOT EXISTS games (
  id                  BIGSERIAL PRIMARY KEY,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at            TIMESTAMPTZ NULL,
  status              TEXT NOT NULL DEFAULT 'finished',
  result              TEXT NOT NULL DEFAULT '',
  winner_user_id      BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  komi                NUMERIC(4,1) NOT NULL DEFAULT 7.5,
  move_count          INTEGER NOT NULL DEFAULT 0 CHECK (move_count >= 0),
  source              TEXT NOT NULL DEFAULT 'online'
);

CREATE INDEX IF NOT EXISTS idx_games_started_at ON games(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);

-- ============================================================
-- 8) game_players（対局参加者）
-- ============================================================
CREATE TABLE IF NOT EXISTS game_players (
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  color               CHAR(1) NOT NULL CHECK (color IN ('B', 'W')),
  rank_at_game        TEXT NOT NULL DEFAULT '',
  elo_at_game         DOUBLE PRECISION NOT NULL DEFAULT 0,
  PRIMARY KEY (game_id, color),
  UNIQUE (game_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_game_players_user_id ON game_players(user_id);

-- ============================================================
-- 9) game_records（棋譜情報）
-- ============================================================
CREATE TABLE IF NOT EXISTS game_records (
  game_id             BIGINT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
  sgf_text            TEXT NOT NULL DEFAULT '',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 10) game_events（対局イベント監査ログ）
-- ============================================================
CREATE TABLE IF NOT EXISTS game_events (
  id                  BIGSERIAL PRIMARY KEY,
  game_id             BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  event_type          TEXT NOT NULL,
  payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_events_game_id ON game_events(game_id);
CREATE INDEX IF NOT EXISTS idx_game_events_type ON game_events(event_type);

-- ============================================================
-- 11) auth_sessions（認証セッション管理）
-- ============================================================
CREATE TABLE IF NOT EXISTS auth_sessions (
  token               TEXT PRIMARY KEY,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at          TIMESTAMPTZ NOT NULL,
  last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked             BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);

COMMIT;

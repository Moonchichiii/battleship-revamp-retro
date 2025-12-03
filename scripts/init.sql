CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL CHECK (length(username) >= 3),
    email VARCHAR(255) UNIQUE NOT NULL,
    github_id VARCHAR(255) UNIQUE,
    google_id VARCHAR(255) UNIQUE,
    display_name VARCHAR(100),
    avatar_url TEXT,
    password_hash TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_activity TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 0),
    shots_fired INTEGER NOT NULL CHECK (shots_fired > 0),
    accuracy NUMERIC(5,2) NOT NULL,
    board_size INTEGER NOT NULL DEFAULT 8,
    difficulty VARCHAR(20) DEFAULT 'standard',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON user_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_scores_leaderboard ON scores(board_size, score DESC, shots_fired ASC);
CREATE INDEX IF NOT EXISTS idx_scores_user_history ON scores(user_id, created_at DESC);

-- Battleship Revamp 2025 - Production Database Schema
-- Initializes the database schema for all environments
-- Test data is handled separately in init-dev-data.sql

-- Security: Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- USERS TABLE: Stores player info and authentication data
CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    github_id INTEGER UNIQUE,
    display_name VARCHAR(100),
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- GAMES TABLE: Stores game sessions
CREATE TABLE IF NOT EXISTS games (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    player_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ai_difficulty VARCHAR(20) NOT NULL CHECK (ai_difficulty IN ('rookie', 'veteran', 'admiral', 'legendary')),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned', 'paused')),
    player_board JSONB,
    ai_board JSONB,
    game_state JSONB,
    moves_history JSONB DEFAULT '[]'::jsonb,
    winner VARCHAR(10) CHECK (winner IN ('player', 'ai', 'draw')),
    total_moves INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- GAME_STATISTICS TABLE: Aggregated player stats
CREATE TABLE IF NOT EXISTS game_statistics (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    player_id UUID REFERENCES users(id) ON DELETE CASCADE,
    difficulty_level VARCHAR(20) NOT NULL,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0,
    games_lost INTEGER DEFAULT 0,
    games_drawn INTEGER DEFAULT 0,
    total_moves INTEGER DEFAULT 0,
    best_time_seconds INTEGER,
    average_time_seconds DECIMAL(10,2),
    win_rate DECIMAL(5,2) GENERATED ALWAYS AS (
        CASE 
            WHEN games_played > 0 THEN ROUND((games_won::decimal / games_played) * 100, 2)
            ELSE 0 
        END
    ) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(player_id, difficulty_level)
);

-- ACHIEVEMENTS TABLE: Player achievements
CREATE TABLE IF NOT EXISTS achievements (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT NOT NULL,
    icon VARCHAR(50),
    requirement_type VARCHAR(50) NOT NULL,
    requirement_value INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- USER_ACHIEVEMENTS TABLE: Links users to achievements
CREATE TABLE IF NOT EXISTS user_achievements (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    achievement_id UUID REFERENCES achievements(id) ON DELETE CASCADE,
    earned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, achievement_id)
);

-- USER_SESSIONS TABLE: Tracks user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- PERFORMANCE INDEXES: Optimized queries

-- User lookups
CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id) WHERE github_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE is_active = TRUE;

-- Game queries
CREATE INDEX IF NOT EXISTS idx_games_player_id ON games(player_id);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
CREATE INDEX IF NOT EXISTS idx_games_difficulty ON games(ai_difficulty);
CREATE INDEX IF NOT EXISTS idx_games_created_at ON games(created_at);
CREATE INDEX IF NOT EXISTS idx_games_completed_at ON games(completed_at) WHERE completed_at IS NOT NULL;

-- Statistics lookups
CREATE INDEX IF NOT EXISTS idx_game_statistics_player_difficulty ON game_statistics(player_id, difficulty_level);
CREATE INDEX IF NOT EXISTS idx_game_statistics_win_rate ON game_statistics(win_rate DESC);

-- Achievement queries
CREATE INDEX IF NOT EXISTS idx_user_achievements_user_id ON user_achievements(user_id);
CREATE INDEX IF NOT EXISTS idx_user_achievements_earned_at ON user_achievements(earned_at);

-- Session management
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

-- AUTO-UPDATE TRIGGERS: Updates 'updated_at' timestamps

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_games_updated_at 
    BEFORE UPDATE ON games 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_game_statistics_updated_at 
    BEFORE UPDATE ON game_statistics 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- INSERT DEFAULT ACHIEVEMENTS: Pre-populate achievements
INSERT INTO achievements (name, description, icon, requirement_type, requirement_value) VALUES
    ('First Victory', 'Win your first game against any AI opponent', '🏆', 'games_won', 1),
    ('Rookie Slayer', 'Defeat the Rookie AI 5 times', '🎯', 'games_won_rookie', 5),
    ('Veteran Hunter', 'Defeat the Veteran AI 3 times', '⚔️', 'games_won_veteran', 3),
    ('Admiral Conqueror', 'Defeat the Admiral AI once', '🛡️', 'games_won_admiral', 1),
    ('Legend Killer', 'Defeat the Legendary AI', '👑', 'games_won_legendary', 1),
    ('Speed Demon', 'Win a game in under 2 minutes', '⚡', 'win_time_seconds', 120),
    ('Efficiency Expert', 'Win a game with fewer than 20 moves', '🎲', 'win_moves', 20),
    ('Persistent Player', 'Play 10 games', '🔥', 'games_played', 10),
    ('Win Streak', 'Win 5 games in a row', '🔗', 'win_streak', 5),
    ('Dedication', 'Play 50 games total', '💪', 'games_played', 50)
ON CONFLICT (name) DO NOTHING;

-- CLEANUP FUNCTIONS: Remove expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions 
    WHERE expires_at < NOW() - INTERVAL '7 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    INSERT INTO game_statistics (player_id, difficulty_level, games_played) 
    VALUES (NULL, 'system_cleanup', deleted_count)
    ON CONFLICT DO NOTHING;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- STATISTICS HELPER FUNCTIONS: Update player stats
CREATE OR REPLACE FUNCTION update_player_statistics(
    p_player_id UUID,
    p_difficulty VARCHAR(20),
    p_won BOOLEAN,
    p_moves INTEGER,
    p_duration INTEGER
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO game_statistics (
        player_id, 
        difficulty_level, 
        games_played,
        games_won,
        games_lost,
        total_moves,
        best_time_seconds,
        average_time_seconds
    ) VALUES (
        p_player_id,
        p_difficulty,
        1,
        CASE WHEN p_won THEN 1 ELSE 0 END,
        CASE WHEN NOT p_won THEN 1 ELSE 0 END,
        p_moves,
        p_duration,
        p_duration
    )
    ON CONFLICT (player_id, difficulty_level) 
    DO UPDATE SET
        games_played = game_statistics.games_played + 1,
        games_won = game_statistics.games_won + CASE WHEN p_won THEN 1 ELSE 0 END,
        games_lost = game_statistics.games_lost + CASE WHEN NOT p_won THEN 1 ELSE 0 END,
        total_moves = game_statistics.total_moves + p_moves,
        best_time_seconds = CASE 
            WHEN game_statistics.best_time_seconds IS NULL OR p_duration < game_statistics.best_time_seconds 
            THEN p_duration 
            ELSE game_statistics.best_time_seconds 
        END,
        average_time_seconds = (
            (game_statistics.average_time_seconds * game_statistics.games_played) + p_duration
        ) / (game_statistics.games_played + 1),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- SCHEMA VALIDATION: Verify tables were created
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('users', 'games', 'game_statistics', 'achievements', 'user_achievements', 'user_sessions');
    
    IF table_count = 6 THEN
        RAISE NOTICE 'Database schema initialized successfully - % tables created', table_count;
    ELSE
        RAISE WARNING 'Expected 6 tables, found % tables', table_count;
    END IF;
END $$;

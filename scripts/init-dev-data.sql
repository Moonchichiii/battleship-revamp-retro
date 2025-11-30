-- Development Data Initialization
DO $$
BEGIN
    IF current_setting('log_statement', true) IS NOT NULL THEN
        INSERT INTO users (username, email, github_id)
        VALUES ('devuser', 'dev@battleship.local', 99999)
        ON CONFLICT (username) DO NOTHING;

        RAISE NOTICE 'Development test data inserted';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not insert development data: %', SQLERRM;
END $$;

-- Creating table for Config model (per-user)
CREATE TABLE IF NOT EXISTS config (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL CHECK(key <> ''),
    value TEXT,
    PRIMARY KEY (user_id, key)
);

-- Creating index for config queries
CREATE INDEX IF NOT EXISTS idx_config_user_key ON config(user_id, key);

-- Creating table for LLMConfig model (per-user)
CREATE TABLE IF NOT EXISTS llm_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
    model TEXT NOT NULL CHECK(model <> ''),
    api_key TEXT NOT NULL CHECK(api_key <> ''),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, base_url, model)
);

-- Creating index for llm_config queries
CREATE INDEX IF NOT EXISTS idx_llm_config_user ON llm_config(user_id);

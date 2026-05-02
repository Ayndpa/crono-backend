-- Creating table for ArticleState with optimized constraints
CREATE TABLE IF NOT EXISTS article_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT 0,
    tags TEXT,
    ai_summary TEXT,
    ai_translation TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
);

-- Creating index for article_states queries
CREATE INDEX IF NOT EXISTS idx_article_states_article_id ON article_states(article_id);
CREATE INDEX IF NOT EXISTS idx_article_states_is_read ON article_states(is_read);

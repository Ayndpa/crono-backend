-- Creating table for RSS feeds (per-user)
CREATE TABLE IF NOT EXISTS rss_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK(name <> ''),
    url TEXT NOT NULL CHECK(url <> ''),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    UNIQUE(user_id, url)
);

-- Creating index for rss_feeds queries
CREATE INDEX IF NOT EXISTS idx_rss_feeds_user ON rss_feeds(user_id);

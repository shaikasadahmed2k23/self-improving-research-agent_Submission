-- Long-term memory of the research agent (SQLite + FTS5).

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    task        TEXT NOT NULL,
    score       INTEGER,
    verdict     TEXT,
    revisions   INTEGER,
    tokens      INTEGER,          -- total LLM tokens, filled in by the caller after the run
    report_path TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(task, content='runs', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS runs_ai AFTER INSERT ON runs BEGIN
    INSERT INTO runs_fts(rowid, task) VALUES (new.id, new.task);
END;

CREATE TABLE IF NOT EXISTS lessons (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER REFERENCES runs(id),
    text          TEXT NOT NULL,
    category      TEXT,           -- tools | sources | units | constraints | writing
    keywords      TEXT,           -- space-separated terms a similar future task would contain
    times_seen    INTEGER DEFAULT 1,   -- extracted again by a later run (deduplicated)
    times_used    INTEGER DEFAULT 0,   -- injected into a planner prompt
    times_helpful INTEGER DEFAULT 0,   -- injected and the run was accepted with 0 revisions
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(text, keywords, content='lessons', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS lessons_ai AFTER INSERT ON lessons BEGIN
    INSERT INTO lessons_fts(rowid, text, keywords) VALUES (new.id, new.text, new.keywords);
END;

CREATE TABLE IF NOT EXISTS run_lessons (
    run_id    INTEGER REFERENCES runs(id),
    lesson_id INTEGER REFERENCES lessons(id),
    PRIMARY KEY (run_id, lesson_id)
);

-- URL-level source trust, from the deterministic citation checks
CREATE TABLE IF NOT EXISTS sources (
    key       TEXT PRIMARY KEY,   -- canonical URL (host/path, no www/utm/trailing slash)
    url       TEXT NOT NULL,
    domain    TEXT,
    title     TEXT,
    verified  INTEGER DEFAULT 0,  -- citation checks that found the cited number in this page
    failed    INTEGER DEFAULT 0,  -- citation checks that failed against this page
    fetched   INTEGER DEFAULT 0,  -- 1 once the full page has been read (not just a search snippet)
    suggested INTEGER DEFAULT 0,  -- 1 if reflection named it as the page to use (reachable, not yet verified)
    facts     TEXT DEFAULT '[]',  -- JSON list of recently verified numbers, e.g. ["$0.33", "$50"]
    last_used TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_sources (
    run_id   INTEGER REFERENCES runs(id),
    key      TEXT REFERENCES sources(key),
    verified INTEGER,
    failed   INTEGER,
    PRIMARY KEY (run_id, key)
);

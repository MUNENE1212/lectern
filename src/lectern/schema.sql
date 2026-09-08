-- Full schema for all phases. Phase 1 populates a subset; later phases need no migration.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    author          TEXT,
    source_path     TEXT,
    source_hash     TEXT UNIQUE,          -- dedupe: same document never added twice
    format          TEXT,
    printed_offset  INTEGER,              -- printed page + offset = PDF page
    structure_src   TEXT,                 -- outline | toc | headers | regex | chunks
    n_pages         INTEGER,
    word_count      INTEGER,
    confirmed       INTEGER NOT NULL DEFAULT 0,
    added_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    page_start  INTEGER,
    page_end    INTEGER,
    word_count  INTEGER,
    text_path   TEXT,
    audio_path  TEXT,
    duration    REAL,
    body        TEXT,
    UNIQUE (book_id, idx)
);

CREATE TABLE IF NOT EXISTS positions (
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    offset_sec  REAL NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (book_id)
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    page        INTEGER,
    quote       TEXT,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS highlights (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    char_start  INTEGER,
    char_end    INTEGER,
    colour      TEXT,
    created_at  TEXT NOT NULL
);

-- Research sources: the book's "spreadsheet of sources", as a table.
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY,
    kind         TEXT,                    -- book | article | video | podcast | webpage
    title        TEXT NOT NULL,
    author       TEXT,
    publisher    TEXT,
    year         INTEGER,
    url          TEXT,
    identifier   TEXT,                    -- doi / isbn
    course       TEXT,
    topics       TEXT,                    -- JSON array
    citation_key TEXT UNIQUE,
    file_path    TEXT,
    source_hash  TEXT,
    accessed_at  TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_quotes (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    locator        TEXT,                  -- page or timestamp
    quote          TEXT NOT NULL,
    why_it_matters TEXT,
    tags           TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_links (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    target_kind TEXT NOT NULL,            -- book | chapter | note | card | gap
    target_id   INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id                INTEGER PRIMARY KEY,
    book_id           INTEGER REFERENCES books(id) ON DELETE CASCADE,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    seconds_listened  REAL NOT NULL DEFAULT 0,
    chapters_covered  TEXT
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,            -- summary | key_points | outline
    content     TEXT NOT NULL,
    provider    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    front       TEXT NOT NULL,
    back        TEXT NOT NULL,
    ease        REAL NOT NULL DEFAULT 2.5,
    interval    INTEGER NOT NULL DEFAULT 0,
    due_at      TEXT,
    reps        INTEGER NOT NULL DEFAULT 0,
    lapses      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    user_answer TEXT,
    correct     INTEGER,
    feedback    TEXT,
    created_at  TEXT NOT NULL
);

-- "Help me understand where I do not": weak spots accumulate here and drive
-- both flashcards and reminders.
CREATE TABLE IF NOT EXISTS gaps (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    concept     TEXT NOT NULL,
    evidence    TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,
    target_id   INTEGER,
    due_at      TEXT NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'desktop',
    sent_at     TEXT
);

-- Full-text search: retrieval by content, not by remembering a filename.
CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
    title, body, content='chapters', content_rowid='id', tokenize='porter'
);

CREATE TRIGGER IF NOT EXISTS chapters_ai AFTER INSERT ON chapters BEGIN
    INSERT INTO chapters_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS chapters_ad AFTER DELETE ON chapters BEGIN
    INSERT INTO chapters_fts(chapters_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS chapters_au AFTER UPDATE ON chapters BEGIN
    INSERT INTO chapters_fts(chapters_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO chapters_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id, idx);
CREATE INDEX IF NOT EXISTS idx_cards_due     ON cards(due_at);
CREATE INDEX IF NOT EXISTS idx_gaps_status   ON gaps(status);

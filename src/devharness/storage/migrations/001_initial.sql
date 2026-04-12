-- Initial schema for the Development Harness SQLite database.
-- All structured data lives here. No YAML config files needed.

-- Projects (multi-workspace support)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_root TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Credentials (API keys -- stored in DB, never in source code)
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,  -- NULL for global credentials
    provider TEXT NOT NULL,
    key_name TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, provider, key_name)
);

-- Threads
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    config_json TEXT NOT NULL DEFAULT '{}',
    thread_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_threads_project ON threads(project_id);
CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);

-- Events (append-only log)
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    turn_id TEXT,
    kind TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);

CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

-- Observations (from observers)
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    turn_id TEXT,
    observer_name TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL,
    source_file TEXT,
    source_line INTEGER,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_thread ON observations(thread_id);
CREATE INDEX IF NOT EXISTS idx_observations_severity ON observations(severity);

-- Artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    turn_id TEXT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    file_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_thread ON artifacts(thread_id);

-- Checkpoints (thread snapshots for replay/resume)
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id);

-- Turn contexts (saved partial state for approval pause/resume)
CREATE TABLE IF NOT EXISTS turn_contexts (
    thread_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    context_json TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (thread_id, turn_id)
);

-- Settings (global key-value store)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Memory event buffer (for Neo4j graceful degradation)
CREATE TABLE IF NOT EXISTS memory_event_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_memory_buffer_status ON memory_event_buffer(status);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version (version, applied_at)
VALUES (1, datetime('now'));

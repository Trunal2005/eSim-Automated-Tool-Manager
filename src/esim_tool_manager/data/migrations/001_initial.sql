-- Initial database schema for eSim Tool Manager v0.1.0
-- Migration 001: Create all core tables

-- Track which migrations have been applied
CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tool registry: stores tool metadata as JSON for flexibility
-- The seed_registry.yaml is loaded into this table on first run
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'system',
    data_json TEXT NOT NULL,  -- Full Tool dataclass serialized as JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Installation history: every install attempt (success or failure) is recorded
CREATE TABLE IF NOT EXISTS install_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,  -- 0 = false, 1 = true
    dry_run INTEGER NOT NULL DEFAULT 1,  -- 0 = false, 1 = true (dry-run by default)
    log_output TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE
);

-- Update history: tracks update attempts separately from installs
CREATE TABLE IF NOT EXISTS update_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id TEXT NOT NULL,
    from_version TEXT NOT NULL DEFAULT '',
    to_version TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    log_output TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE
);

-- Per-tool configuration: environment variables and paths
CREATE TABLE IF NOT EXISTS tool_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    config_type TEXT NOT NULL DEFAULT 'env_var',  -- 'env_var', 'path', 'setting'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tool_id, key),
    FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE
);

-- Named configuration profiles
CREATE TABLE IF NOT EXISTS config_profiles (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tool_ids_json TEXT NOT NULL DEFAULT '[]',   -- JSON array of tool IDs
    env_overrides_json TEXT NOT NULL DEFAULT '{}',  -- JSON dict of env var overrides
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_install_history_tool_id ON install_history(tool_id);
CREATE INDEX IF NOT EXISTS idx_install_history_timestamp ON install_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_update_history_tool_id ON update_history(tool_id);
CREATE INDEX IF NOT EXISTS idx_update_history_timestamp ON update_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_config_tool_id ON tool_config(tool_id);
CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category);

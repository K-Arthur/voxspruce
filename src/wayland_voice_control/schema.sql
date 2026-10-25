-- Intentional user configuration only. No recognition or execution history.
BEGIN IMMEDIATE;
CREATE TABLE settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    model_path TEXT NOT NULL DEFAULT ''
        CHECK (length(model_path) <= 4096 AND instr(model_path, char(0)) = 0 AND instr(model_path, '://') = 0),
    microphone_consent INTEGER NOT NULL DEFAULT 0 CHECK (microphone_consent IN (0, 1)),
    confirmation_ttl_seconds REAL NOT NULL DEFAULT 30 CHECK (confirmation_ttl_seconds BETWEEN 10 AND 120),
    focus_delay_seconds REAL NOT NULL DEFAULT 3 CHECK (focus_delay_seconds BETWEEN 2 AND 10),
    capture_limit_seconds REAL NOT NULL DEFAULT 30 CHECK (capture_limit_seconds BETWEEN 5 AND 60),
    theme TEXT NOT NULL DEFAULT 'system' CHECK (theme IN ('system', 'light', 'dark'))
) STRICT;
INSERT INTO settings (id) VALUES (1);
CREATE TABLE custom_voice_shortcuts (
    id TEXT PRIMARY KEY NOT NULL
        CHECK (length(id) BETWEEN 1 AND 64 AND id NOT GLOB '*[^A-Za-z0-9_-]*'),
    phrase TEXT NOT NULL UNIQUE CHECK (length(phrase) BETWEEN 1 AND 120),
    key_chord TEXT NOT NULL CHECK (length(key_chord) BETWEEN 1 AND 64),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 240),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
) STRICT;
PRAGMA user_version = 2;
COMMIT;

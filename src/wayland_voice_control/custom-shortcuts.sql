CREATE TABLE custom_voice_shortcuts (
    id TEXT PRIMARY KEY NOT NULL
        CHECK (length(id) BETWEEN 1 AND 64 AND id NOT GLOB '*[^A-Za-z0-9_-]*'),
    phrase TEXT NOT NULL UNIQUE CHECK (length(phrase) BETWEEN 1 AND 120),
    key_chord TEXT NOT NULL CHECK (length(key_chord) BETWEEN 1 AND 64),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 240),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
) STRICT;

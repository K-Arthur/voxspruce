# Data structures and schema

Only intentional user configuration persists. The authoritative SQL is
[`schema.sql`](../src/wayland_voice_control/schema.sql); the matching portable
contracts are [`settings.schema.json`](../schemas/settings.schema.json) and
[`custom-voice-shortcuts.schema.json`](../schemas/custom-voice-shortcuts.schema.json).

## Persistent preferences

The database is `$XDG_CONFIG_HOME/wayland-voice-control/settings.db`, using
`~/.config` when the environment value is absent or not absolute. The application
directory is private (0700) and the database is private (0600). An existing shared
directory is rejected rather than having its permissions changed unexpectedly.

The `STRICT` settings table contains exactly one row (`id = 1`). A separate
`STRICT` custom shortcut table contains only intentional configuration.

| Field | Type | Default | Constraint / meaning |
| --- | --- | --- | --- |
| `id` | INTEGER | 1 | Singleton primary key |
| `schema_version` | INTEGER | 1 | Must equal supported version 1 |
| `model_path` | TEXT | empty | Local directory path, at most 4096 characters; no URI or NUL; Python also rejects surrogates |
| `microphone_consent` | INTEGER / API boolean | false | Stored 0 or 1; does not start capture |
| `confirmation_ttl_seconds` | REAL | 30 | Finite number, 10–120 |
| `focus_delay_seconds` | REAL | 3 | Finite number, 2–10 |
| `capture_limit_seconds` | REAL | 30 | Finite number, 5–60 |
| `theme` | TEXT | `system` | `system`, `light`, or `dark` |

`Settings` is an immutable validated dataclass. Updates reject unknown fields and
incorrect types (including booleans supplied as numeric time limits), then commit
atomically. Reset atomically restores defaults, including microphone consent off, and deletes
all custom shortcuts. Model
directory existence and recognizer validity are checked at loading time, not
mistaken for a valid model simply because a path string was saved.

SQLite `PRAGMA user_version = 2` describes the database layout. The preferences
row and its portable JSON schema deliberately remain `schema_version = 1`: no
preference changed shape. A real v1 database is upgraded in one `BEGIN IMMEDIATE`
transaction: validate/read the legacy settings, create `custom_voice_shortcuts`,
then advance `user_version`. No preferences are rewritten. Any failure rolls back
the migration and leaves the version unchanged. New databases initialize both
tables transactionally. Future versions fail before file changes or chmod.
Connections explicitly enable SQLite foreign keys; neither table needs references.

### Custom voice shortcuts

| Field | Type | Constraint |
| --- | --- | --- |
| `id` | TEXT primary key | 1–64 ASCII letters, digits, `_` or `-`; distinct from built-in IDs |
| `phrase` | TEXT unique | 1–120 characters before and after normalization; casefold and whitespace normalization only; nonblank |
| `key_chord` | TEXT | One canonical validated chord, at most 64 characters |
| `description` | TEXT | At most 240 characters; may be empty |
| `enabled` | INTEGER / API boolean | 0 or 1; API accepts only actual booleans; default true |

At most 100 custom entries are accepted, including disabled entries. Phrases and
descriptions reject controls, formatting characters, surrogates and line/paragraph
separators. Both active and disabled phrases must avoid normalized built-in or
custom phrase collisions. Canonical phrase/chord values are stored; reads validate
every row and the complete catalogue, including corrupted values inserted outside
the application. SQL enforces unique IDs/phrases, field sizes, strict types and the
boolean flag. Runtime semantic validation additionally enforces normalization,
Unicode restrictions, built-in collisions and supported key names; JSON Schema
alone cannot express all those rules. The custom JSON schema describes a list of
configuration objects, separate from the unchanged settings object.

`SettingsStore.load()` returns preferences; `load_custom_shortcuts()` returns a
tuple of frozen `CustomShortcut` entries. `load_configuration()` reads both under
one transaction and returns `(settings, shortcuts)`. `replace_custom_shortcuts`,
`add_custom_shortcut`, `update_custom_shortcut` and `delete_custom_shortcut` validate
and commit atomically. A failed mutation preserves the old list. A missing update
or delete ID is an error; updates preserve list order. Reset repairs invalid values
by replacing both configurations with defaults/empty list. No recognition or
execution history is retained.

## Transient structures

| Structure | Fields / purpose | Lifetime |
| --- | --- | --- |
| `Command` | ID, exact phrase, key chord, description, custom marker, risk | Immutable merged catalogue |
| `PendingAction` | ID, kind, payload, bound chord/phrase/description/custom marker/risk, monotonic creation/expiry times | Current review/confirmation only |
| `Workflow` | Mode, state, current recording identity, pending action, consent gates, error | Current application instance |
| Controller snapshot | Read-only UI state, status, activity, pending action, permission and actual shortcuts | Current UI render |
| Recognition draft | Provisional text, bounded and display-only | Active held speech only |
| Loaded model | Vosk model for the selected local path | Cached in process to avoid repeated cold loads |
| Audio buffers / recognizer | Short PCM blocks and current capture decoder | One capture; never persisted by the app |

A text action stores literal reviewed text in memory. A command action stores its
canonical catalogue ID plus the immutable actual chord/effect shown for review.
Execution uses that bound chord, never a later catalogue lookup for custom actions.
Commands cannot contain scripts, macros, text sequences or shell commands. A fresh identity is
issued after an edit; confirmations bind to that identity and expire using a
monotonic clock. `take_action` consumes it before dispatch so failure cannot
automatically retry it.

Preferences are not an audit log. Application errors are fixed actionable messages
at sensitive worker boundaries, so a recognizer or subprocess exception cannot
accidentally copy speech into logs. Freed Python/native memory and OS swap are not
securely erased; see [privacy.md](privacy.md).

## Resident desktop controls (transient only)

Background availability is session-only and adds no SQLite preference or schema
migration. The application holds the current controller while the window is
hidden; no recognition content or portal grant is persisted. The version 1
Controls1 status dictionary contains enumerated states and booleans only; its
exact field and method contract is in [desktop-controls.md](desktop-controls.md).
The optional D-Bus activation file stores an application executable path, not
settings, permission tokens or transcripts. Installation does not enable login
startup.

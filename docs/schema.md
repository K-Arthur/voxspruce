# Data structures and schema

Only preferences persist. The authoritative SQL is
[`schema.sql`](../src/wayland_voice_control/schema.sql); the matching portable
contract is [`settings.schema.json`](../schemas/settings.schema.json).

## Persistent preferences

The database is `$XDG_CONFIG_HOME/wayland-voice-control/settings.db`, using
`~/.config` when the environment value is absent or not absolute. The application
directory is private (0700) and the database is private (0600). An existing shared
directory is rejected rather than having its permissions changed unexpectedly.

One `STRICT` SQLite table contains exactly one row (`id = 1`).

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
atomically. Reset restores defaults, including microphone consent off. Model
directory existence and recognizer validity are checked at loading time, not
mistaken for a valid model simply because a path string was saved.

SQLite `PRAGMA user_version` and the row version both identify schema version 1.
An empty new database initializes transactionally. A future or unrecognized schema
fails without migration or permission changes; no speculative down-migration is
performed. Future migrations must be explicit and tested with old real databases.

There are no audio, transcript, command payload, clipboard, history, portal-token
or account tables. No backup/export feature for speech content is provided.

## Transient structures

| Structure | Fields / purpose | Lifetime |
| --- | --- | --- |
| `Command` | Fixed ID, exact phrase, key chord, risk | Immutable built-in catalogue |
| `PendingAction` | ID, kind, payload, risk, monotonic creation/expiry times | Current review/confirmation only |
| `Workflow` | Mode, state, current recording identity, pending action, consent gates, error | Current application instance |
| Controller snapshot | Read-only UI state, status, activity, pending action, permission and actual shortcuts | Current UI render |
| Recognition draft | Provisional text, bounded and display-only | Active held speech only |
| Loaded model | Vosk model for the selected local path | Cached in process to avoid repeated cold loads |
| Audio buffers / recognizer | Short PCM blocks and current capture decoder | One capture; never persisted by the app |

A text action stores literal reviewed text in memory. A command action stores its
canonical allowlist ID, never an arbitrary shell command. A fresh identity is
issued after an edit; confirmations bind to that identity and expire using a
monotonic clock. `take_action` consumes it before dispatch so failure cannot
automatically retry it.

Preferences are not an audit log. Application errors are fixed actionable messages
at sensitive worker boundaries, so a recognizer or subprocess exception cannot
accidentally copy speech into logs. Freed Python/native memory and OS swap are not
securely erased; see [privacy.md](privacy.md).

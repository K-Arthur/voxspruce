# Wayland Voice Control

An experimental, offline Linux voice-control tool: hold to speak, review the
result, then explicitly confirm dictation or a small desktop command.

This repository is being built in reviewed milestones. The domain engine,
preferences schema, keyboard/shortcut portal adapters, local streaming speech,
diagnostics and reproducible speech benchmark are implemented. Custom voice
shortcuts and the native GTK4/libadwaita interface are the next milestones.
The default GUI entry point is not ready in this intermediate revision.

GNOME Wayland is the intended first validation target. Real GNOME input,
microphone latency and testing with intended voice-input users remain release
gates; this is not certified assistive technology.

## Inspect the implemented core

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m wayland_voice_control commands
.venv/bin/python -m wayland_voice_control doctor --json
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Normal operation uses local models and no cloud recognition, account, telemetry,
audio storage or automatic model download. Input uses an explicitly granted
keyboard portal session. Every action is reviewed and confirmed, with a separate
second confirmation for risky commands. There is no always-listening mode or
privileged input-helper fallback.

## Design and evidence

- [Architecture and complete workflow](docs/architecture.md)
- [Persistent and transient data structures](docs/schema.md)
- [Privacy and permission model](docs/privacy.md)
- [Measured local speech performance](docs/performance.md)
- [Validation evidence](docs/validation.md) and [compatibility limits](docs/compatibility.md)
- [Real-session kill test](docs/manual-test.md)
- [Competitor research and technical decisions](docs/research.md)
- [Implementation plan](docs/superpowers/plans/2026-10-25-wayland-voice-control.md)

#!/usr/bin/env python3
"""Derive palette variants and desktop icons from the canonical SVG mark."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "launch" / "assets"
mark = (ASSETS / "voxspruce-mark.svg").read_text(encoding="utf-8")
variants = {
    "voxspruce-mark-dark.svg": ("#79e3c4", "#e7fff5"),
    "voxspruce-mark-mono.svg": ("#153f39", "#153f39"),
    "voxspruce-mark-mono-light.svg": ("#ffffff", "#ffffff"),
}
for filename, (teal, evergreen) in variants.items():
    (ASSETS / filename).write_text(
        mark.replace("#0b7166", teal).replace("#103e39", evergreen), encoding="utf-8"
    )
inner = mark.split(">", 1)[1].rsplit("</svg>", 1)[0]
icon = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
    'viewBox="0 0 128 128">\n'
    '  <rect x="4" y="4" width="120" height="120" rx="28" fill="#e9f7f1"/>\n'
    f'  <g transform="translate(14 14) scale(.78)">{inner}  </g>\n</svg>\n'
)
for path in (
    ROOT / "data" / "io.github.wayland_voice_control.svg",
    ROOT / "src" / "wayland_voice_control" / "resources" / "icons" / "io.github.wayland_voice_control.svg",
):
    path.write_text(icon, encoding="utf-8")

#!/usr/bin/env python3
"""Render the GitHub preview from the canonical, light-on-dark SVG mark."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "launch" / "assets"
mark = (ASSETS / "voxspruce-mark-dark.svg").read_text(encoding="utf-8")
mark = mark.split(">", 1)[1].rsplit("</svg>", 1)[0]
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640">
<title>Voxspruce — voice input for Linux</title>
<desc>Experimental, local-first, open-source voice input with the Voxspruce spruce and waveform mark.</desc>
<rect width="1280" height="640" fill="#0b2925"/>
<g fill="none" stroke="#79e3c4" stroke-width="1" opacity=".14">
 <path d="M-30 458 C130 364 250 451 384 510 S661 590 850 512 S1117 445 1310 517"/>
 <path d="M-30 480 C130 386 250 473 384 532 S661 612 850 534 S1117 467 1310 539"/>
 <path d="M-30 502 C130 408 250 495 384 554 S661 634 850 556 S1117 489 1310 561"/>
 <path d="M-30 524 C130 430 250 517 384 576 S661 656 850 578 S1117 511 1310 583"/>
 <path d="M833 -36 C943 78 1036 29 1104 68 S1215 136 1310 81"/>
 <path d="M833 -14 C943 100 1036 51 1104 90 S1215 158 1310 103"/>
 <path d="M833 8 C943 122 1036 73 1104 112 S1215 180 1310 125"/>
</g>
<rect x="82" y="111" width="320" height="320" rx="44" fill="#123e37" stroke="#347568" stroke-width="1"/>
<g transform="translate(124 153) scale(1.84)">{mark}</g>
<g font-family="DejaVu Sans, sans-serif">
 <text x="465" y="175" fill="#79e3c4" font-size="20" font-weight="bold" letter-spacing="3">EXPERIMENTAL  ·  LOCAL-FIRST  ·  OPEN SOURCE</text>
 <text x="459" y="279" fill="#f0faf5" font-size="87" font-weight="bold" letter-spacing="-3">Voxspruce</text>
 <text x="464" y="339" fill="#c3dbd2" font-size="32">Voice input for Linux</text>
 <path d="M465 383 h52" stroke="#79e3c4" stroke-width="3"/>
 <text x="465" y="420" fill="#c3dbd2" font-size="21">Built with accessibility and privacy in mind</text>
</g>
<g fill="#79e3c4" opacity=".32" transform="translate(1005 518)">
 <rect x="0" y="20" width="5" height="12" rx="2.5"/><rect x="12" y="13" width="5" height="26" rx="2.5"/>
 <rect x="24" y="0" width="5" height="52" rx="2.5"/><rect x="36" y="8" width="5" height="36" rx="2.5"/>
 <rect x="48" y="-7" width="5" height="66" rx="2.5"/><rect x="60" y="4" width="5" height="44" rx="2.5"/>
 <rect x="72" y="14" width="5" height="24" rx="2.5"/><rect x="84" y="20" width="5" height="12" rx="2.5"/>
</g>
</svg>'''
source = ASSETS / "social-preview.svg"
source.write_text(svg, encoding="utf-8")
subprocess.run(["rsvg-convert", str(source), "-o", str(ASSETS / "social-preview.png")], check=True)

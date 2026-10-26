#!/usr/bin/env python3
"""Build the Plasma package reproducibly; does not install or activate anything."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=project / "dist/wayland-voice-control.plasmoid"
    )
    args = parser.parse_args()
    source = project / "integrations/plasma/io.github.wayland_voice_control"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(
        args.output, "w", compression=ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                info = ZipInfo(
                    path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0)
                )
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, path.read_bytes(), compresslevel=9)
    print(args.output)


if __name__ == "__main__":
    main()

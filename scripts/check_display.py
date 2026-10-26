#!/usr/bin/env python3
"""Compile/test the actual firmware renderer on the host; export its preview.

Requires a C11 compiler. With --preview, also requires ImageMagick 7.
This checks portable drawing code, not Zephyr/LVGL integration or a UF2 build.
"""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="velvet-display-") as scratch:
        scratch = Path(scratch)
        executable = scratch / "display-test"
        run(os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            "-I", ROOT / "src/display", ROOT / "tests/display_test.c",
            ROOT / "src/display/velvet_display.c", ROOT / "src/display/dragon_assets.c",
            "-o", executable)
        run(executable, scratch)
        if args.preview:
            destination = ROOT / "assets/display"
            for frame in range(4):
                run("magick", scratch / f"left-{frame}.pbm", scratch / f"right-{frame}.pbm",
                    "+append", scratch / f"pair-{frame}.png")
            run("magick", scratch / "pair-0.png", destination / "preview-native.png")
            run("magick", scratch / "pair-0.png", "-filter", "point", "-resize", "400%",
                destination / "preview.png")
            animation = ["magick"]
            for delay, frame in ((280, 0), (20, 1), (60, 0), (60, 2), (60, 3)):
                animation.extend(["-delay", str(delay), str(scratch / f"pair-{frame}.png")])
            run(*animation, "-filter", "point", "-resize", "400%", "-loop", "0",
                destination / "preview.gif")
            run("magick", scratch / "right-scroll.pbm", scratch / "right-precision.pbm",
                scratch / "right-usb.pbm", scratch / "left-disconnected.pbm", "+append",
                "-filter", "point", "-resize", "300%", destination / "status-examples.png")
            print(f"Native firmware-rendered previews: {destination}")


if __name__ == "__main__":
    main()

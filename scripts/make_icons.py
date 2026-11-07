"""Make the app's icons from one PNG: icons/icon.icns (macOS) and icons/icon.ico (Windows) in the app folder.

    uv run python scripts/make_icons.py resources/icon.png

The installer uses them for the app, and the running app for its windows and the Dock
or taskbar (``mainWindowIcon`` in apps/twiliteacq/config.yaml; main.py takes the .icns
on macOS).

The PNG should be square, at least 1024 px, with a transparent background. The
transparent margin is trimmed, then on macOS the shape gets the margin of Apple's
icon grid (824 of 1024 px), so it is as large as the other icons in the Dock; on
Windows it fills the icon. The .icns needs macOS (``iconutil``).
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ICONS = Path(__file__).resolve().parents[1] / "apps" / "twiliteacq" / "icons"
MAC_BODY = 824 / 1024


def square(image, size, body):
    """The image's non-transparent part, scaled to ``body`` of a ``size`` square canvas, centered."""
    shape = image.crop(image.getchannel("A").getbbox())
    scale = size * body / max(shape.size)
    shape = shape.resize((round(shape.width * scale), round(shape.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size))
    canvas.paste(shape, ((size - shape.width) // 2, (size - shape.height) // 2), shape)
    return canvas


def main():
    image = Image.open(sys.argv[1]).convert("RGBA")
    ICONS.mkdir(exist_ok=True)

    square(image, 256, 1.0).save(ICONS / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            square(image, size, MAC_BODY).save(iconset / f"icon_{size}x{size}.png")
            square(image, size * 2, MAC_BODY).save(iconset / f"icon_{size}x{size}@2x.png")
        if shutil.which("iconutil"):
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICONS / "icon.icns")], check=True)
        else:
            print("No iconutil (not macOS): icon.icns not updated")
    print("Icons written to", ICONS)


if __name__ == "__main__":
    main()

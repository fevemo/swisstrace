"""Make the app's icons and splash from the Swisstrace logo (resources/swisstrace-logo.svg).

    uv run python scripts/make_icons.py

Writes, in apps/twiliteacq/icons/:

- ``icon.ico`` (Windows) and ``icon.icns`` (macOS; needs ``iconutil``, so only on a Mac):
  the wordmark stacked (SWISS over TRACE) on a white rounded tile. The installer uses them
  for the app, and the running app for its windows and the Dock or taskbar
  (``mainWindowIcon`` in apps/twiliteacq/config.yaml; main.py takes the .icns on macOS).
  On macOS the tile has the size, corners and shadow of Apple's icon grid (824 of 1024 px),
  so it is as large as the other icons in the Dock; on Windows it fills the icon. Each size
  is drawn from the vectors, not scaled down from a large image.
- ``splash.png`` (``splashImage`` in config.yaml): the wordmark on one line, on a white
  card shaped like EINstudio's default splash. EINstudio paints the version in its
  top-right corner and the status line along its bottom (in black: see ``adaptSplash`` in
  main.py), so both stay clear of the logo. It is 360 px wide because EINstudio scales a
  larger splash image down to 360 px.

The SVG is the logo's vector paths in screen RGB, with the two words as the groups
``swiss`` and ``trace``. Run this again after changing it.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from PIL import Image, ImageFilter
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PyQt6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "resources" / "swisstrace-logo.svg"
APP_DIR = ROOT / "apps" / "twiliteacq"
ICONS = APP_DIR / "icons"

TILE = QColor("#FFFFFF")

# Apple's macOS icon grid: an 824 px tile with 185 px corners on a 1024 px canvas, and a
# drop shadow below it.
MAC_TILE, MAC_RADIUS = 824 / 1024, 185 / 824
MAC_SHADOW_BLUR, MAC_SHADOW_OFFSET, MAC_SHADOW_ALPHA = 10 / 1024, 10 / 1024, 0.30
WIN_RADIUS = 0.18
WIN_OUTLINE = QColor(0, 0, 0, 40)
# The stacked wordmark's width, as a share of the tile, and the gap between the two words,
# as a share of their height.
ICON_WORDMARK_WIDTH = 0.76
STACK_GAP = 0.28

SPLASH_WIDTH, SPLASH_HEIGHT, SPLASH_RADIUS = 360, 188, 12
SPLASH_LOGO_WIDTH = 0.78
SPLASH_BORDER = QColor("#D0D0D0")
SPLASH_TITLE = QColor("#646363")  # the logo's grey


def toPil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (image.width(), image.height()), image.constBits().asstring(image.sizeInBytes()),
                            "raw", "RGBA", image.bytesPerLine(), 1).copy()


def newImage(width, height):
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image


def painterOn(image):
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return painter


def drawWord(painter, logo, word, x, y, scale):
    """Draw one word of the logo with its top-left corner at (x, y), ``scale`` px per SVG unit."""
    bounds = logo.boundsOnElement(word)
    logo.render(painter, word, QRectF(x, y, bounds.width() * scale, bounds.height() * scale))


def drawStacked(painter, logo, centre, width):
    """SWISS over TRACE, each centred, the wider one ``width`` px wide, centred on ``centre``."""
    swiss, trace = logo.boundsOnElement("swiss"), logo.boundsOnElement("trace")
    scale = width / max(swiss.width(), trace.width())
    gap = STACK_GAP * swiss.height() * scale
    height = (swiss.height() + trace.height()) * scale + gap
    top = centre[1] - height / 2
    drawWord(painter, logo, "swiss", centre[0] - swiss.width() * scale / 2, top, scale)
    drawWord(painter, logo, "trace", centre[0] - trace.width() * scale / 2, top + swiss.height() * scale + gap, scale)


def windowsIcon(logo, size):
    """The tile filling a ``size`` px square."""
    image = newImage(size, size)
    painter = painterOn(image)
    # A faint outline, so the white tile keeps its edge on a light taskbar or folder.
    painter.setPen(QPen(WIN_OUTLINE, 1))
    painter.setBrush(TILE)
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), WIN_RADIUS * size, WIN_RADIUS * size)
    drawStacked(painter, logo, (size / 2, size / 2), ICON_WORDMARK_WIDTH * size)
    painter.end()
    return toPil(image)


def macIcon(logo, size):
    """The tile on Apple's icon grid, with its shadow, on a ``size`` px canvas."""
    tile = MAC_TILE * size
    corner = (size - tile) / 2
    image = newImage(size, size)
    painter = painterOn(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(TILE)
    painter.drawRoundedRect(QRectF(corner, corner, tile, tile), MAC_RADIUS * tile, MAC_RADIUS * tile)
    drawStacked(painter, logo, (size / 2, size / 2), ICON_WORDMARK_WIDTH * tile)
    painter.end()
    icon = toPil(image)

    alpha = icon.getchannel("A").point(lambda a: round(a * MAC_SHADOW_ALPHA))
    alpha = alpha.filter(ImageFilter.GaussianBlur(MAC_SHADOW_BLUR * size))
    shadow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (0, round(MAC_SHADOW_OFFSET * size)), alpha)
    return Image.alpha_composite(shadow, icon)


def splash(logo, title):
    """The logo on one line on a white card shaped like EINstudio's default splash, with the
    app's name below it."""
    image = newImage(SPLASH_WIDTH, SPLASH_HEIGHT)
    painter = painterOn(image)
    painter.setPen(QPen(SPLASH_BORDER, 1))
    painter.setBrush(TILE)
    painter.drawRoundedRect(QRectF(0.5, 0.5, SPLASH_WIDTH - 1, SPLASH_HEIGHT - 1), SPLASH_RADIUS, SPLASH_RADIUS)

    swiss, trace = logo.boundsOnElement("swiss"), logo.boundsOnElement("trace")
    scale = SPLASH_LOGO_WIDTH * SPLASH_WIDTH / (trace.right() - swiss.left())
    logoHeight = max(swiss.bottom(), trace.bottom()) - min(swiss.top(), trace.top())
    font = QFont(QGuiApplication.font())
    font.setPixelSize(17)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
    titleHeight, titleGap = 22, 14
    # Centred between the version (top 32 px) and the status line (bottom 30 px).
    top = 32 + (SPLASH_HEIGHT - 32 - 30 - (logoHeight * scale + titleGap + titleHeight)) / 2
    left = (SPLASH_WIDTH - (trace.right() - swiss.left()) * scale) / 2
    originY = top - min(swiss.top(), trace.top()) * scale
    drawWord(painter, logo, "swiss", left, originY + swiss.top() * scale, scale)
    drawWord(painter, logo, "trace", left + (trace.left() - swiss.left()) * scale, originY + trace.top() * scale, scale)

    painter.setFont(font)
    painter.setPen(SPLASH_TITLE)
    painter.drawText(QRectF(0, top + logoHeight * scale + titleGap, SPLASH_WIDTH, titleHeight),
                     Qt.AlignmentFlag.AlignCenter, title.upper())
    painter.end()
    return toPil(image)


def main():
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 (fonts need it)
    logo = QSvgRenderer(str(LOGO))
    if not logo.isValid() or not logo.elementExists("swiss") or not logo.elementExists("trace"):
        sys.exit(f"{LOGO} is not an SVG with the groups 'swiss' and 'trace'")
    ICONS.mkdir(exist_ok=True)

    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [windowsIcon(logo, size) for size in sizes]
    images[-1].save(ICONS / "icon.ico", sizes=[(n, n) for n in sizes], append_images=images[:-1])

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            macIcon(logo, size).save(iconset / f"icon_{size}x{size}.png")
            macIcon(logo, size * 2).save(iconset / f"icon_{size}x{size}@2x.png")
        if shutil.which("iconutil"):
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICONS / "icon.icns")], check=True)
        else:
            print("No iconutil (not macOS): icon.icns not updated")

    title = yaml.safe_load((APP_DIR / "config.yaml").read_text(encoding="utf-8"))["mainWindowTitle"]
    splash(logo, title).save(ICONS / "splash.png")
    print("Icons and splash written to", ICONS)


if __name__ == "__main__":
    main()

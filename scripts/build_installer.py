"""Build the installer for this computer's platform: a .dmg on macOS, an .msi on Windows.

    uv run --group packaging python scripts/build_installer.py
    uv run --group packaging python scripts/build_installer.py --identity "Developer ID Application: ..."

Steps: build the manual (it ships inside the app), write the versions in uv.lock as pip
constraints (so the installer has exactly the tested dependencies), copy the app folder
under the package name Briefcase expects, without a checkout's runtime output, then have
Briefcase create (or update), build and package the app. The configuration is
``[tool.briefcase]`` in ``pyproject.toml``. The installer lands in ``dist/``.

Creating the bundle installs every dependency, twice on macOS (Apple Silicon and Intel),
which is most of the time. So the bundle is kept, and the next build only copies the new
sources into it (``briefcase update``), unless uv.lock, ``[tool.briefcase]`` or the
Briefcase version changed since it was created: then, or with ``--fresh``, it is
created again.

On macOS, the Qt libraries the app does not load are removed from the bundle before it
is signed (see ``remove_unused_qt``): PyQt6 ships all of Qt, and most of it (QML, 3D,
multimedia, ...) is unused here.

Without ``--identity`` the app is only ad-hoc signed: macOS then asks the user to allow
it once (see the installation page of the manual), and Windows shows a SmartScreen
warning. With a Developer ID certificate in the keychain, pass its name to sign and
notarize the .dmg instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "build" / "installer-constraints.txt"
APP_DIR = ROOT / "apps" / "twiliteacq"
# The app's name in [tool.briefcase], which is also the name of its package in the installer.
STAGED_APP_DIR = ROOT / "build" / "installer-src" / "pysample"
BUNDLE_BUILD_DIR = ROOT / "build" / "pysample"
NOT_SHIPPED = ("data", "log.txt", "state.yaml", "__pycache__", "pyproject.toml")
# What the bundle's dependencies were installed from; written once the bundle is created.
FINGERPRINT_FILE = BUNDLE_BUILD_DIR / f"fingerprint-{sys.platform}.txt"
# The PyQt6 modules the app, EINstudio, qfluentwidgets and pyqtgraph import (QtTest by
# pyqtgraph, if present). On macOS the bundle keeps these, the Qt libraries and plugins
# they need, and nothing else of Qt. Importing another one makes the installed app fail
# with an ImportError: add it here.
QT_MODULES = ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtOpenGL", "QtOpenGLWidgets", "QtPrintSupport",
              "QtSvg", "QtXml", "QtTest", "QtWebChannel", "QtWebEngineCore", "QtWebEngineWidgets")


def run(*command: str) -> None:
    print("\n$ " + " ".join(command), flush=True)
    start = time.monotonic()
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"({time.monotonic() - start:.0f} s)", flush=True)


def fingerprint() -> str:
    briefcaseConfig = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["briefcase"]
    digest = hashlib.sha256()
    digest.update((ROOT / "uv.lock").read_bytes())
    digest.update(json.dumps(briefcaseConfig, sort_keys=True).encode())
    digest.update(version("briefcase").encode())
    # A module added back needs its libraries, which only a new bundle has.
    digest.update(" ".join(QT_MODULES).encode())
    return digest.hexdigest()


def linked_qt_libraries(binary: Path) -> set[str]:
    """The Qt frameworks and libraries ``binary`` links to, by name (``QtGui``, ``libavcodec.61.dylib``)."""
    output = subprocess.run(["otool", "-L", str(binary)], capture_output=True, text=True, check=True).stdout
    names = set()
    for line in output.splitlines()[1:]:
        match = re.search(r"(?:@rpath|@loader_path\S*)/(?:(Qt\w+)\.framework|(lib[\w.]+\.dylib))", line)
        if match:
            names.add(match[1] or match[2])
    return names


def remove_unused_qt(app_packages: Path) -> None:
    """Remove from the macOS bundle the PyQt6 modules not in QT_MODULES and the Qt libraries,
    plugins and QML files nothing kept needs.

    What the kept modules and WebEngine's helper process link to, directly or through
    each other, stays; so does every plugin whose libraries all stay.
    """
    pyqt = app_packages / "PyQt6"
    lib = pyqt / "Qt6" / "lib"

    def library_binary(name):
        return lib / name if name.endswith(".dylib") else lib / f"{name}.framework" / "Versions" / "A" / name

    roots = [pyqt / f"{module}.abi3.so" for module in QT_MODULES if (pyqt / f"{module}.abi3.so").exists()]
    roots += lib.glob("QtWebEngineCore.framework/Versions/A/Helpers/*.app/Contents/MacOS/*")
    needed, todo = set(), set().union(*(linked_qt_libraries(root) for root in roots))
    while todo:
        name = todo.pop()
        needed.add(name)
        if library_binary(name).exists():
            todo |= linked_qt_libraries(library_binary(name)) - needed

    removed = []
    for path in sorted(pyqt.glob("Qt*.abi3.so")) + sorted(pyqt.glob("Qt*.pyi")):
        if path.name.split(".")[0] not in QT_MODULES:
            path.unlink()
            removed.append(path)
    for path in sorted(lib.iterdir()):
        name = path.name.removesuffix(".framework")
        if name in needed or path.suffix not in (".framework", ".dylib"):
            continue
        if path.is_dir():
            remove_tree(path)
        else:
            path.unlink()
        removed.append(path)
    for plugin in sorted((pyqt / "Qt6" / "plugins").rglob("*.dylib")):
        if not linked_qt_libraries(plugin) <= needed:
            plugin.unlink()
            removed.append(plugin)
    for folder in (pyqt / "Qt6" / "plugins").iterdir():
        if folder.is_dir() and not any(folder.rglob("*.dylib")):
            remove_tree(folder)
    print(f"\nRemoved {len(removed)} unused Qt modules, libraries and plugins; kept {', '.join(sorted(needed))}.")


def remove_tree(path: Path) -> None:
    """Delete a folder, including the read-only files a bundle contains."""
    def make_writable_and_retry(function, failed_path, _):
        os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        function(failed_path)

    if path.exists():
        shutil.rmtree(path, onexc=make_writable_and_retry)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--identity", help="code-signing identity; default: ad-hoc signing only")
    parser.add_argument("--fresh", action="store_true", help="create the bundle again even if nothing requires it")
    args = parser.parse_args()

    run("uv", "run", "--group", "docs", "sphinx-build", "-q", "-b", "html", "doc/source", "doc/build/html")

    CONSTRAINTS.parent.mkdir(exist_ok=True)
    run("uv", "export", "--package", "twiliteacq", "--no-dev", "--no-hashes", "--no-emit-workspace",
        "--no-header", "--no-annotate", "--frozen", "--output-file", str(CONSTRAINTS.relative_to(ROOT)))

    remove_tree(STAGED_APP_DIR)
    shutil.copytree(APP_DIR, STAGED_APP_DIR, ignore=shutil.ignore_patterns(*NOT_SHIPPED))

    briefcase = [sys.executable, "-m", "briefcase"]
    current = fingerprint()
    if not args.fresh and FINGERPRINT_FILE.exists() and FINGERPRINT_FILE.read_text() == current:
        print("\nDependencies and configuration unchanged: updating the sources of the existing bundle.")
        # With the icon, which `update` alone keeps as it was.
        run(*briefcase, "update", "--update-resources", "--no-input")
    else:
        # From scratch: `briefcase create` refuses to reuse an old bundle without asking.
        remove_tree(BUNDLE_BUILD_DIR)
        run(*briefcase, "create", "--no-input")
        FINGERPRINT_FILE.write_text(current)
    if sys.platform == "darwin":
        for app_packages in BUNDLE_BUILD_DIR.glob("macos/app/*.app/Contents/Resources/app_packages"):
            remove_unused_qt(app_packages)
    run(*briefcase, "build", "--no-input")
    signing = ["--identity", args.identity] if args.identity else ["--adhoc-sign"]
    run(*briefcase, "package", "--no-input", *signing)
    print("\nInstaller in", ROOT / "dist")


if __name__ == "__main__":
    main()

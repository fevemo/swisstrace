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

The Qt libraries the app does not load are removed from the bundle before it is built
and signed (see ``remove_unused_qt``): PyQt6 ships all of Qt, and most of it (QML, 3D,
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
# The app's pyproject.toml ships: it holds the version the splash, the window title and
# the acquisition files show.
NOT_SHIPPED = ("data", "log.txt", "state.yaml", "__pycache__")
# What the bundle's dependencies were installed from; written once the bundle is created.
FINGERPRINT_FILE = BUNDLE_BUILD_DIR / f"fingerprint-{sys.platform}.txt"
# The PyQt6 modules the app, EINstudio, qfluentwidgets and pyqtgraph import (QtTest by
# pyqtgraph, if present). The bundle keeps these, the Qt libraries and plugins they
# need, and nothing else of Qt. Importing another one makes the installed app fail
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


def check_version() -> None:
    """Stop unless ``[tool.briefcase] version`` (the installer's) is the app's version.

    The app's version is ``[project] version`` in apps/twiliteacq/pyproject.toml, which the
    running app shows; Briefcase cannot read it from there, so both are set by hand.
    """
    app = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    installer = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["briefcase"]["version"]
    if app != installer:
        sys.exit(f"The app is version {app} (apps/twiliteacq/pyproject.toml) but the installer {installer} "
                 "([tool.briefcase] version in pyproject.toml): set both to the same version.")


def linked_qt_libraries(binary: Path) -> set[str]:
    """The Qt libraries ``binary`` links to, by name: on macOS the frameworks and dylibs it
    loads from the bundle (``QtGui``, ``libavcodec.61.dylib``), on Windows the DLLs it
    imports, lower-cased (``qt6gui.dll``, ``kernel32.dll``: the caller ignores what PyQt6
    does not ship)."""
    if sys.platform == "win32":
        return dll_imports(binary)
    output = subprocess.run(["otool", "-L", str(binary)], capture_output=True, text=True, check=True).stdout
    names = set()
    for line in output.splitlines()[1:]:
        match = re.search(r"(?:@rpath|@loader_path\S*)/(?:(Qt\w+)\.framework|(lib[\w.]+\.dylib))", line)
        if match:
            names.add(match[1] or match[2])
    return names


def dll_imports(binary: Path) -> set[str]:
    """The DLLs a Windows executable or DLL imports, lower-cased, delay-loaded ones included.

    Reads the import and delay-import tables of the PE file, which is what Windows' loader
    follows (and what ``dumpbin /dependents`` lists).
    """
    data = binary.read_bytes()
    pe = int.from_bytes(data[0x3C:0x40], "little")
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{binary} is not a PE file")
    section_count = int.from_bytes(data[pe + 6:pe + 8], "little")
    optional_size = int.from_bytes(data[pe + 20:pe + 22], "little")
    optional = pe + 24
    # Data directories: 8 bytes (RVA, size) each, after the standard fields, which are
    # longer for 64-bit (PE32+) files.
    directories = optional + (112 if data[optional:optional + 2] == b"\x0b\x02" else 96)
    sections = [(int.from_bytes(data[s + 12:s + 16], "little"),   # virtual address
                 int.from_bytes(data[s + 8:s + 12], "little"),    # virtual size
                 int.from_bytes(data[s + 20:s + 24], "little"))   # file offset
                for s in range(optional + optional_size, optional + optional_size + 40 * section_count, 40)]

    def offset(rva):
        for address, size, raw in sections:
            if address <= rva < address + size:
                return rva - address + raw
        raise ValueError(f"{binary}: address {rva:#x} is in no section")

    names = set()
    # Import directory (1): 20-byte descriptors, the name's address at +12. Delay-import
    # directory (13): 32-byte descriptors, the name's address at +4. Both end with zeros.
    for index, entry_size, name_at in ((1, 20, 12), (13, 32, 4)):
        rva = int.from_bytes(data[directories + 8 * index:directories + 8 * index + 4], "little")
        if not rva:
            continue
        entry = offset(rva)
        while name_rva := int.from_bytes(data[entry + name_at:entry + name_at + 4], "little"):
            start = offset(name_rva)
            names.add(data[start:data.index(b"\0", start)].decode("ascii").lower())
            entry += entry_size
    return names


def remove_unused_qt(app_packages: Path) -> None:
    """Remove from the bundle the PyQt6 modules not in QT_MODULES and the Qt libraries and
    plugins nothing kept needs.

    What the kept modules and WebEngine's helper process link to, directly or through
    each other, stays; so does every plugin whose libraries all stay.

    On Windows, only Qt's own DLLs and FFmpeg's (which Qt Multimedia uses) can go: the
    other DLLs beside them stay, as nothing imports some that Qt loads by name when it
    needs them (``opengl32sw.dll``, software OpenGL without a graphics driver;
    ``d3dcompiler_47.dll``), and the Microsoft C++ runtime is small.
    """
    pyqt = app_packages / "PyQt6"
    if sys.platform == "win32":
        lib = pyqt / "Qt6" / "bin"
        module_suffix, plugin_pattern = ".pyd", "*.dll"
        helpers = [lib / "QtWebEngineProcess.exe"]

        def library_binary(name):
            return lib / name

        def qt_library(name):
            return re.fullmatch(r"qt6\w+\.dll|(avcodec|avformat|avutil|swresample|swscale)-\d+\.dll", name)

        def removable(path):
            return qt_library(library_name(path))

        def library_name(path):
            return path.name.lower()
    else:
        lib = pyqt / "Qt6" / "lib"
        module_suffix, plugin_pattern = ".abi3.so", "*.dylib"
        helpers = list(lib.glob("QtWebEngineCore.framework/Versions/A/Helpers/*.app/Contents/MacOS/*"))

        def library_binary(name):
            return lib / name if name.endswith(".dylib") else lib / f"{name}.framework" / "Versions" / "A" / name

        def qt_library(name):
            return True  # linked_qt_libraries only lists Qt's

        def removable(path):
            return path.suffix in (".framework", ".dylib")

        def library_name(path):
            return path.name.removesuffix(".framework")

    roots = [pyqt / f"{module}{module_suffix}" for module in QT_MODULES if (pyqt / f"{module}{module_suffix}").exists()]
    roots += [helper for helper in helpers if helper.exists()]
    needed, todo = set(), set().union(*(linked_qt_libraries(root) for root in roots))
    while todo:
        name = todo.pop()
        needed.add(name)
        if library_binary(name).exists():
            todo |= linked_qt_libraries(library_binary(name)) - needed

    removed = []
    # Q*: PyQt6's modules are Qt*, plus QAxContainer (ActiveX) on Windows.
    for path in sorted(pyqt.glob(f"Q*{module_suffix}")) + sorted(pyqt.glob("Q*.pyi")):
        if path.name.split(".")[0] not in QT_MODULES:
            path.unlink()
            removed.append(path)
    for path in sorted(lib.iterdir()):
        if library_name(path) in needed or not removable(path):
            continue
        if path.is_dir():
            remove_tree(path)
        else:
            path.unlink()
        removed.append(path)
    plugins = pyqt / "Qt6" / "plugins"
    # A plugin linking a Qt library that is gone, or that PyQt6 never shipped (some do,
    # e.g. Qt 3D's), could not load.
    for plugin in sorted(plugins.rglob(plugin_pattern)):
        if not {name for name in linked_qt_libraries(plugin) if qt_library(name)} <= needed:
            plugin.unlink()
            removed.append(plugin)
    for folder in plugins.iterdir():
        if folder.is_dir() and not any(folder.rglob(plugin_pattern)):
            remove_tree(folder)
    print(f"\nRemoved {len(removed)} unused Qt modules, libraries and plugins; "
          f"kept {', '.join(sorted(name for name in needed if qt_library(name)))}.")


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
    check_version()

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
    bundled_packages = {"darwin": "macos/app/*.app/Contents/Resources/app_packages",
                        "win32": "windows/app/src/app_packages"}
    if sys.platform in bundled_packages:
        for app_packages in BUNDLE_BUILD_DIR.glob(bundled_packages[sys.platform]):
            remove_unused_qt(app_packages)
    run(*briefcase, "build", "--no-input")
    signing = ["--identity", args.identity] if args.identity else ["--adhoc-sign"]
    run(*briefcase, "package", "--no-input", *signing)
    print("\nInstaller in", ROOT / "dist")


if __name__ == "__main__":
    main()

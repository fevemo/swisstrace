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
    return digest.hexdigest()


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
        run(*briefcase, "update", "--no-input")
    else:
        # From scratch: `briefcase create` refuses to reuse an old bundle without asking.
        remove_tree(BUNDLE_BUILD_DIR)
        run(*briefcase, "create", "--no-input")
        FINGERPRINT_FILE.write_text(current)
    run(*briefcase, "build", "--no-input")
    signing = ["--identity", args.identity] if args.identity else ["--adhoc-sign"]
    run(*briefcase, "package", "--no-input", *signing)
    print("\nInstaller in", ROOT / "dist")


if __name__ == "__main__":
    main()

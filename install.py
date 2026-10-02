#!/usr/bin/env python3
"""
install.py — Set up the swisstrace environment.

Prerequisites: Python 3.8+. No other tools required.
Works from any shell: Git Bash, PowerShell, CMD, WSL, macOS/Linux terminal.

Usage:
    python install.py
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


UV_VERSION = "0.11.15"


def _install_uv() -> int:
    system = platform.system()
    if system == "Windows":
        url = f"https://astral.sh/uv/{UV_VERSION}/install.ps1"
        command = ["powershell", "-ExecutionPolicy", "ByPass", "-c", f"irm {url} | iex"]
    else:
        url = f"https://astral.sh/uv/{UV_VERSION}/install.sh"
        command = ["sh", "-c", f"curl -LsSf {url} | sh"]
    return subprocess.call(command)


def _find_uv():
    """Return path to uv, checking PATH and common install locations."""
    found = shutil.which("uv") or shutil.which("uv.exe")
    if found:
        return found
    home = Path.home()
    for candidate in [
        home / ".local" / "bin" / "uv",
        home / ".local" / "bin" / "uv.exe",
        home / ".cargo" / "bin" / "uv",
        home / ".cargo" / "bin" / "uv.exe",
        Path(os.environ.get("USERPROFILE", str(home))) / ".local" / "bin" / "uv.exe",
    ]:
        if candidate.is_file():
            return str(candidate)
    return None


def main():
    uv = _find_uv()
    if not uv:
        print(f"uv not found — installing v{UV_VERSION}...")
        if _install_uv() != 0:
            print("ERROR: uv installation failed.", file=sys.stderr)
            sys.exit(1)
        uv = _find_uv()
        if not uv:
            print(
                "\nERROR: uv not found after installation.\n"
                "Restart your shell and run this script again.",
                file=sys.stderr,
            )
            sys.exit(1)

    here = Path(__file__).parent.resolve()

    print("Installing swisstrace environment ...")
    subprocess.run([uv, "sync", "--python", "3.12"], cwd=str(here), check=True)

    print("\nEnvironment ready.")
    print("Run the app with:  uv run python main.py")


if __name__ == "__main__":
    main()

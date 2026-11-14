"""Where the app keeps its files.

Run from a checkout, everything stays in the app folder, as before. Installed (the
Briefcase build sets ``TWILITEACQ_INSTALLED=1``), the app folder is read-only, so:

=================  ==========================================  ===============================================
                   macOS                                       Windows
=================  ==========================================  ===============================================
data               ``~/Twilite``                               ``%USERPROFILE%\\Twilite``
settings, state    ``~/Library/Application Support/<name>``    ``%LOCALAPPDATA%\\<name>``
log, raw logs      ``~/Library/Logs/<name>``                   ``%LOCALAPPDATA%\\<name>\\Logs``
=================  ==========================================  ===============================================

The data goes straight into the home folder rather than Documents, which iCloud
(macOS) and OneDrive (Windows) often sync and may evict from the disk. The settings
go to the local, not the roaming, application data on Windows: they describe this
computer's device.

Standard library only, so the Model can use it without Qt.
"""
import os
import shutil
import sys
import tomllib
from pathlib import Path

APP_NAME = "Twilite"
INSTALLED_ENV = "TWILITEACQ_INSTALLED"
APP_DIR = Path(__file__).resolve().parent


def installed():
    return os.environ.get(INSTALLED_ENV) == "1"


def defaultDataDir():
    return Path.home() / APP_NAME if installed() else APP_DIR / "data"


def settingsDir():
    if not installed():
        return APP_DIR
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return _localAppData() / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME


def logDir():
    if not installed():
        return APP_DIR
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    if sys.platform == "win32":
        return _localAppData() / APP_NAME / "Logs"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / APP_NAME


def stateFile():
    """The settings saved between sessions; from a checkout, relative to EINstudio's working directory, the app folder."""
    return settingsDir() / "state.yaml" if installed() else Path("state.yaml")


def rawLogDir(dataDir):
    """Every byte exchanged with the device: diagnostics, so with the log once installed."""
    return logDir() / "rawlogs" if installed() else Path(dataDir) / "rawlogs"


def instrumentConfigFile():
    """The device settings this installation uses.

    Installed, the copy in :func:`settingsDir`, made from the one shipped with the app
    on the first launch; an update of the app then never replaces the user's settings.
    """
    shipped = APP_DIR / "instrumentConfig.yaml"
    if not installed():
        return shipped
    userCopy = settingsDir() / "instrumentConfig.yaml"
    if not userCopy.exists():
        userCopy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shipped, userCopy)
    return userCopy


def appVersion():
    """``[project] version`` of the app's ``pyproject.toml``, the one place the version is set.

    EINstudio reads the same file for the splash (``ConfigManager.appVersion``), and the
    installer ships it and checks that ``[tool.briefcase] version`` matches.
    """
    with open(APP_DIR / "pyproject.toml", "rb") as file:
        return tomllib.load(file)["project"]["version"]


def _localAppData():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")

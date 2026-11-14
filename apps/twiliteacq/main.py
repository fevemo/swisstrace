"""Twilite acquisition app: acquisition, correction and calibration for the Swisstrace twilite.

To run from the repository root:
    uv run python apps/twiliteacq/main.py

The installed app starts from ``__main__.py`` instead, which runs this file with
``TWILITEACQ_INSTALLED=1`` (see ``locations.py``).
"""
import importlib
import os
import sys

thisFileDir = os.path.dirname(os.path.realpath(__file__))
# EINstudio imports the app folder as a package named after the folder (`twiliteacq`, or
# `pysample` in the installer); make it importable as one here too, so that this file can
# use its `locations` before EINstudio starts.
sys.path.insert(0, os.path.dirname(thisFileDir))

# Import Qt before einstudio (which imports logging): atexit runs callbacks in reverse,
# so logging.shutdown then runs before PyQt deletes einstudio's log handler (a QObject).
import PyQt6.QtCore  # noqa: F401
from einstudio.tools.configmanager import ConfigManager
from einstudio.tools.einapplication import EINApplication

locations = importlib.import_module(os.path.basename(thisFileDir) + ".locations")


def adaptConfig(installed):
    """Adjust ``config.yaml`` where EINstudio reads it: the icon for this platform and,
    installed, the folders.

    On macOS the icon is the .icns, which has the margin of the other icons in the Dock.
    Installed, the log, the device settings and the manual move out of the read-only app
    folder: EINstudio joins these paths to the app folder, which leaves absolute paths as
    they are.
    """
    mainConfigFile = os.path.join(thisFileDir, "config.yaml")
    loadConfig = ConfigManager.loadConfig

    def loadMainConfig(path):
        config = loadConfig(path)
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(mainConfigFile):
            return config
        if sys.platform == "darwin":
            config.mainWindowIcon = os.path.join(thisFileDir, "icons", "icon.icns")
        if installed:
            locations.logDir().mkdir(parents=True, exist_ok=True)
            config.logFile = str(locations.logDir() / "log.txt")
            config.instrumentConfigFile = str(locations.instrumentConfigFile())
            # The manual built from doc/source, which [tool.briefcase] in pyproject.toml ships beside the app.
            config.docPath = os.path.join(os.path.dirname(thisFileDir), "html")
        return config

    ConfigManager.loadConfig = staticmethod(loadMainConfig)


if __name__ == '__main__':
    adaptConfig(locations.installed())
    EINApplication(appDir=thisFileDir).launch()
    sys.exit(0)

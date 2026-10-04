"""Twilite acquisition app: acquisition, correction and calibration for the Swisstrace twilite.

To run from the repository root:
    uv run python apps/twiliteacq/main.py
"""
import os
import sys

thisFileDir = os.path.dirname(os.path.realpath(__file__))

# Import Qt before einstudio (which imports logging): atexit runs callbacks in reverse,
# so logging.shutdown then runs before PyQt deletes einstudio's log handler (a QObject).
import PyQt6.QtCore  # noqa: F401
from einstudio.tools.einapplication import EINApplication

if __name__ == '__main__':
    EINApplication(appDir=thisFileDir).launch()
    sys.exit(0)

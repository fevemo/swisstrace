"""App — brief description.

To run from the application directory:
    uv run ein run swisstrace
"""
import os
import sys

thisFileDir = os.path.dirname(os.path.realpath(__file__))

from einstudio.tools.einapplication import EINApplication

if __name__ == '__main__':
    EINApplication(appDir=thisFileDir).launch()
    sys.exit(0)

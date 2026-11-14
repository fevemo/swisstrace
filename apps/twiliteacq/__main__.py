"""Entry point of the installed app: Briefcase starts it with ``python -m <app package>``."""
import os
import runpy

from . import locations

os.environ[locations.INSTALLED_ENV] = "1"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), run_name="__main__")

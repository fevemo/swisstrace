"""Fixtures for the app layer: the Model with an in-process simulator, no Qt needed."""

import importlib.util
import logging
import math
import shutil
import sys
import types
from pathlib import Path

import pytest

try:
    # The docs page uses QtWebEngine, which must be imported before pytest-qt creates
    # the QApplication.
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

APP_DIR = Path(__file__).resolve().parents[2] / "apps" / "twiliteacq"


def load_app_module(name):
    """Import ``apps/twiliteacq/<name>.py`` without EINstudio's launcher.

    As in EINstudio, the module is in package ``twiliteacq``, the app folder, so that the
    app's own imports (``from . import locations``) resolve.
    """
    if "twiliteacq" not in sys.modules:
        package = types.ModuleType("twiliteacq")
        package.__path__ = [str(APP_DIR)]
        sys.modules["twiliteacq"] = package
    spec = importlib.util.spec_from_file_location(f"twiliteacq.{name}", APP_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_step_run(directory, start=1_790_000_000.0):
    """Write a calibration run; return its path. Its CF is 50 * 0.967 / 1000 for A_PET 50 at ``start``.

    F-18, background 120 before t = 100 s, then 120 + 1000 * exp(-lambda t); one sample every 5 s
    for 300 s.
    """
    from twilite import Sample, get_isotope
    from twilite.storage import AcquisitionWriter

    lam = math.log(2) / get_isotope("F-18").half_life_s
    writer = AcquisitionWriter(directory, start_wall=start, start_mono=0.0)
    for i in range(60):
        t = i * 5.0
        rate = 120 + (1000 * math.exp(-lam * t) if t >= 100 else 0)
        writer.write_sample(Sample(i, 0, 0, rate, (), "", start + t, t))
    return writer.finish()


def make_instrument_config(data_dir, **overrides):
    config = {
        "host": "127.0.0.1",
        "port": 23,
        "timeout_s": 1.0,
        "reconnectAttempts": 2,
        "dataDir": str(data_dir),
        "rawLog": True,
        "simulate": True,
        "simulator": {"scenario": "bolus", "port": 0},
    }
    config.update(overrides)
    return {"twilite": config}


def copy_instrument_config(directory):
    """A copy of the app's instrumentConfig.yaml for the Settings window to save to; return its path."""
    path = directory / "instrumentConfig.yaml"
    shutil.copyfile(APP_DIR / "instrumentConfig.yaml", path)
    return str(path)


@pytest.fixture
def model_factory(tmp_path):
    Model = load_app_module("model").Model
    models = []

    def factory(**overrides):
        model = Model(logging.getLogger("twiliteacq.test"), make_instrument_config(tmp_path / "data", **overrides))
        model.INSTRUMENT_CONFIG_FILE = copy_instrument_config(tmp_path)
        models.append(model)
        return model

    yield factory
    for model in models:
        model.shutdown()


@pytest.fixture
def model(model_factory):
    return model_factory()

"""Fixtures for the app layer: the Model with an in-process simulator, no Qt needed."""

import importlib.util
import logging
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
    """Import ``apps/twiliteacq/<name>.py`` without EINstudio's launcher."""
    spec = importlib.util.spec_from_file_location(f"twiliteacq_{name}", APP_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


@pytest.fixture
def model_factory(tmp_path):
    Model = load_app_module("model").Model
    models = []

    def factory(**overrides):
        model = Model(logging.getLogger("twiliteacq.test"), make_instrument_config(tmp_path / "data", **overrides))
        models.append(model)
        return model

    yield factory
    for model in models:
        model.shutdown()


@pytest.fixture
def model(model_factory):
    return model_factory()

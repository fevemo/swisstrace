"""Where the app keeps its files, from a checkout and installed."""

import logging
import sys

import pytest

from .conftest import APP_DIR, load_app_module

locations = load_app_module("locations")


@pytest.fixture
def installed(monkeypatch, tmp_path):
    monkeypatch.setenv(locations.INSTALLED_ENV, "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".local" / "state"))
    return tmp_path


def test_a_checkout_keeps_everything_in_the_app_folder(monkeypatch):
    monkeypatch.delenv(locations.INSTALLED_ENV, raising=False)
    assert locations.defaultDataDir() == APP_DIR / "data"
    assert locations.instrumentConfigFile() == APP_DIR / "instrumentConfig.yaml"
    assert locations.logDir() == APP_DIR
    assert str(locations.stateFile()) == "state.yaml"


def test_installed_uses_the_user_folders(installed):
    home = installed
    assert locations.defaultDataDir() == home / "Twilite"
    for path in (locations.settingsDir(), locations.logDir(), locations.stateFile()):
        assert APP_DIR not in path.parents and home in path.parents
    if sys.platform == "darwin":
        assert locations.settingsDir() == home / "Library" / "Application Support" / "Twilite"
        assert locations.logDir() == home / "Library" / "Logs" / "Twilite"
    elif sys.platform == "win32":
        assert locations.logDir() == home / "AppData" / "Local" / "Twilite" / "Logs"


def test_installed_copies_the_device_settings_once(installed):
    userCopy = locations.instrumentConfigFile()
    assert userCopy.parent == locations.settingsDir()
    assert userCopy.read_text() == (APP_DIR / "instrumentConfig.yaml").read_text()
    userCopy.write_text("twilite: {host: 10.0.0.7}\n")
    assert locations.instrumentConfigFile().read_text() == "twilite: {host: 10.0.0.7}\n"  # kept, not replaced


def test_installed_model_writes_outside_the_app_folder(installed):
    Model = load_app_module("model").Model
    model = Model(logging.getLogger("test"), {"twilite": {"host": "x", "port": 1, "dataDir": ""}})
    assert model.dataDir == str(installed / "Twilite")
    model.saveState({"qrate": 5})
    assert model.loadState() == {"qrate": 5}
    assert (locations.settingsDir() / "state.yaml").exists()

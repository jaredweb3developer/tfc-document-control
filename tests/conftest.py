import os
import sys
from pathlib import Path

# Force Qt to run headlessly in tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Ensure "import app" resolves from repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PySide6.QtWidgets import QApplication

import app as app_module


@pytest.fixture(scope="session")
def qapp():
    # Qt widgets require a QApplication; reuse one for the full test session.
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def app_env(tmp_path, monkeypatch, qapp):
    # Isolated paths so tests never touch real user config/data files.
    data_root = tmp_path / "user-data"
    paths = {
        "settings": data_root / "settings.json",
        "projects": data_root / "projects.json",
        "records": data_root / "checkout_records.json",
        "presets": data_root / "filter_presets.json",
        "debug_log": data_root / "debug_events.log",
        "legacy_settings": tmp_path / "legacy-settings.json",
        "legacy_projects": tmp_path / "legacy-projects.json",
        "legacy_records": tmp_path / "legacy-records.json",
        "legacy_presets": tmp_path / "legacy-presets.json",
    }

    monkeypatch.setattr(app_module, "SETTINGS_FILE", paths["settings"], raising=False)
    monkeypatch.setattr(app_module, "LEGACY_SETTINGS_FILE", paths["legacy_settings"], raising=False)
    monkeypatch.setattr(app_module, "LEGACY_PROJECTS_FILE", paths["legacy_projects"], raising=False)
    monkeypatch.setattr(app_module, "LEGACY_RECORDS_FILE", paths["legacy_records"], raising=False)
    monkeypatch.setattr(app_module, "LEGACY_FILTER_PRESETS_FILE", paths["legacy_presets"], raising=False)
    # Override default locations used when creating a fresh app instance.
    monkeypatch.setattr(
        app_module.DocumentControlApp,
        "_default_projects_dir",
        lambda _self: tmp_path / "Projects",
        raising=False,
    )
    monkeypatch.setattr(
        app_module.DocumentControlApp,
        "_default_projects_registry_file",
        lambda _self: paths["projects"],
        raising=False,
    )
    monkeypatch.setattr(
        app_module.DocumentControlApp,
        "_default_filter_presets_file",
        lambda _self: paths["presets"],
        raising=False,
    )
    monkeypatch.setattr(
        app_module.DocumentControlApp,
        "_default_records_file",
        lambda _self: paths["records"],
        raising=False,
    )
    monkeypatch.setattr(
        app_module.DocumentControlApp,
        "_default_debug_events_file",
        lambda _self: paths["debug_log"],
        raising=False,
    )

    def create_app():
        # Build the real window object but silence message boxes during tests.
        win = app_module.DocumentControlApp()
        win._info = lambda _msg: None
        win._error = lambda _msg: None
        return win

    # Return shared handles used by tests.
    win = create_app()
    yield {"app": win, "module": app_module, "paths": paths, "create_app": create_app, "tmp": tmp_path}
    win.close()
    win.deleteLater()

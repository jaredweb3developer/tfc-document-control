from pathlib import Path

from PySide6.QtWidgets import QListWidgetItem, QMessageBox

from app import CheckoutRecord


def test_project_config_stores_metadata_and_compact_source_ids(app_env):
    # Project configs should persist metadata fields and stable compact keys for each source.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_a = tmp / "src-a"
    source_b = tmp / "src-b"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)

    project_dir = tmp / "Projects" / "MetaProject"
    app._write_project_config(
        project_dir,
        "Meta Project",
        [str(source_a), str(source_b)],
        client="Acme",
        year_started="2026",
    )

    cfg = app._read_project_config(project_dir)
    source_ids = cfg.get("source_ids", {})

    assert cfg.get("client") == "Acme"
    assert cfg.get("year_started") == "2026"
    assert isinstance(source_ids, dict)
    assert set(source_ids.keys()) == {str(source_a), str(source_b)}
    assert len({source_ids[str(source_a)], source_ids[str(source_b)]}) == 2

    # Source key should be compact and stable across calls.
    first = app._source_key(project_dir, source_a)
    second = app._source_key(project_dir, source_a)
    assert first == second
    assert 8 <= len(first) <= 12


def test_create_project_switches_current_project(app_env):
    # Creating a project should immediately load/switch to it.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source = tmp / "src"
    source.mkdir(parents=True)
    project_dir = tmp / "Projects" / "Switched"

    app._create_or_update_project(
        "Switched",
        project_dir,
        sources=[str(source)],
        client="ClientX",
        year_started="2025",
    )

    assert app.current_project_dir == str(project_dir)
    assert app.current_project_label.text() == "Current Project: Switched"

    cfg = app._read_project_config(project_dir)
    assert cfg.get("client") == "ClientX"
    assert cfg.get("year_started") == "2025"


def test_project_search_filters_by_name_client_and_year(app_env):
    # Search input in Tracked Projects should match against name/client/year fields.
    app = app_env["app"]

    app.tracked_projects = [
        {"name": "Alpha", "project_dir": "/tmp/a", "client": "Acme", "year_started": "2026"},
        {"name": "Beta", "project_dir": "/tmp/b", "client": "Globex", "year_started": "2024"},
    ]

    app.project_search_edit.setText("acme")
    app._refresh_tracked_projects_list()
    assert app.tracked_projects_list.count() == 1
    assert app.tracked_projects_list.item(0).text() == "Alpha"

    app.project_search_edit.setText("2024")
    app._refresh_tracked_projects_list()
    assert app.tracked_projects_list.count() == 1
    assert app.tracked_projects_list.item(0).text() == "Beta"


def test_source_file_search_filters_file_list(app_env):
    # File search should filter Source Files list by filename substring.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "plan-A.dwg").write_text("a", encoding="utf-8")
    (source_dir / "notes.txt").write_text("b", encoding="utf-8")

    app.current_directory = source_dir
    app.file_filter_mode_combo.setCurrentText("No Filter")
    app.file_search_edit.setText("dwg")
    app._refresh_source_files()

    assert app.files_list.count() == 1
    assert app.files_list.item(0).text() == "plan-A.dwg"


def test_loading_project_without_sources_clears_controlled_files(app_env):
    # Switching to a project with no tracked dirs should clear stale controlled-file UI data.
    app = app_env["app"]
    tmp = app_env["tmp"]

    app.controlled_files_table.setRowCount(1)

    empty_project = tmp / "Projects" / "Empty"
    app._write_project_config(empty_project, "Empty", [])
    app._load_project_from_dir(empty_project)

    assert app.controlled_files_table.rowCount() == 0


def test_untrack_project_with_checked_out_files_stays_tracked(app_env, monkeypatch):
    # If a project still has checked-out records, untrack should be blocked by prompt.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "Active"
    project_dir.mkdir(parents=True)
    app.tracked_projects = [
        {
            "name": "Active",
            "project_dir": str(project_dir),
            "client": "",
            "year_started": "",
        }
    ]
    app.records = [
        CheckoutRecord(
            source_file="/src/file.dwg",
            locked_source_file="/src/file-JH.dwg",
            local_file="/local/file.dwg",
            initials="JH",
            project_name="Active",
            project_dir=str(project_dir),
            source_root="/src",
            checked_out_at="",
        )
    ]

    # Simulate user choosing to keep the project tracked in the warning prompt.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    app._refresh_tracked_projects_list()
    app.tracked_projects_list.setCurrentRow(0)
    app._remove_selected_project()

    assert len(app.tracked_projects) == 1
    assert app.tracked_projects[0]["project_dir"] == str(project_dir)


def test_resolve_new_project_name_uses_source_when_name_blank(app_env, monkeypatch):
    # Blank name should allow using selected source folder name via prompt.
    app = app_env["app"]
    source_dir = "/tmp/ExampleSource"

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    resolved = app._resolve_new_project_name("", source_dir)
    assert resolved == "ExampleSource"


def test_resolve_new_project_name_keeps_entered_on_no_prompt_accept(app_env, monkeypatch):
    # When name differs from source folder and user says no, keep the entered name.
    app = app_env["app"]
    source_dir = "/tmp/ExampleSource"

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
    resolved = app._resolve_new_project_name("Custom Name", source_dir)
    assert resolved == "Custom Name"

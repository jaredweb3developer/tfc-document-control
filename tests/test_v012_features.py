from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from app import CheckoutRecord


def test_tracked_project_item_loads_path_object(app_env, monkeypatch):
    # Double-click/load helper should convert stored list data into a Path before loading.
    app = app_env["app"]
    loaded = []

    monkeypatch.setattr(app, "_load_project_from_dir", lambda project_dir: loaded.append(project_dir))

    item = QListWidgetItem("Sample")
    item.setData(Qt.UserRole, "/tmp/sample-project")
    app._load_tracked_project_item(item)

    assert loaded == [Path("/tmp/sample-project")]


def test_favorite_and_note_item_helpers_route_to_expected_actions(app_env, monkeypatch):
    # Favorites should open directly and notes should route into edit handling.
    app = app_env["app"]
    opened = []
    edited = []

    monkeypatch.setattr(app, "_open_paths", lambda paths: opened.extend(paths))
    monkeypatch.setattr(app, "_edit_selected_note", lambda *_args: edited.append(True))

    favorite_item = QListWidgetItem("alpha.pdf")
    favorite_item.setData(Qt.UserRole, "/tmp/alpha.pdf")
    app._open_favorite_item(favorite_item)

    note_item = QListWidgetItem("Review")
    note_item.setData(Qt.UserRole, "note-1")
    app.notes_list.addItem(note_item)
    app._edit_note_item(note_item)

    assert opened == [Path("/tmp/alpha.pdf")]
    assert edited == [True]
    assert app.notes_list.currentItem() is note_item


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (("current", None), "current"),
        (("other", Path("/tmp/other-project")), "other"),
        (("global", None), "global"),
    ],
)
def test_add_selected_source_files_to_favorites_routes_to_target(app_env, monkeypatch, target, expected):
    # Source-file favorites should be sent to the user-chosen destination.
    app = app_env["app"]
    selected = [Path("/tmp/source/A.dwg"), Path("/tmp/source/B.pdf")]
    called = []

    monkeypatch.setattr(app, "_selected_source_file_paths", lambda: selected)
    monkeypatch.setattr(app, "_choose_favorite_target", lambda _paths: target)
    monkeypatch.setattr(app, "_add_favorite_paths", lambda paths: called.append(("current", paths)))
    monkeypatch.setattr(
        app,
        "_add_favorite_paths_to_project",
        lambda project_dir, paths: called.append(("other", project_dir, paths)),
    )
    monkeypatch.setattr(
        app, "_add_favorite_paths_to_global", lambda paths: called.append(("global", paths))
    )

    app._add_selected_source_files_to_favorites()

    if expected == "current":
        assert called == [("current", selected)]
    elif expected == "other":
        assert called == [("other", Path("/tmp/other-project"), selected)]
    else:
        assert called == [("global", selected)]


def test_record_search_filters_main_tables_and_local_project_lists(app_env):
    # Checked-out/reference search fields should filter both the main tables and the condensed project lists.
    app = app_env["app"]

    app.current_project_dir = "/tmp/project-a"
    app.records = [
        CheckoutRecord(
            source_file="/srv/source/alpha.dwg",
            locked_source_file="/srv/source/alpha-JH.dwg",
            local_file="/tmp/project-a/checked_out/alpha_working_copy.dwg",
            initials="JH",
            project_name="Project A",
            project_dir="/tmp/project-a",
            source_root="/srv/source",
            checked_out_at="2026-03-10T09:15:00-05:00",
        ),
        CheckoutRecord(
            source_file="/srv/source/beta.dwg",
            locked_source_file="/srv/source/beta-AB.dwg",
            local_file="/tmp/project-b/checked_out/beta_working_copy.dwg",
            initials="AB",
            project_name="Project B",
            project_dir="/tmp/project-b",
            source_root="/srv/source",
            checked_out_at="2026-03-10T09:30:00-05:00",
        ),
        CheckoutRecord(
            source_file="/srv/source/ref.pdf",
            locked_source_file="/srv/source/ref.pdf",
            local_file="/tmp/project-a/reference/ref.pdf",
            initials="JH",
            project_name="Project A",
            project_dir="/tmp/project-a",
            source_root="/srv/source",
            checked_out_at="2026-03-10T10:00:00-05:00",
            record_type="reference_copy",
        ),
    ]

    app._render_records_tables()
    assert app.all_records_table.rowCount() == 2
    assert app.project_records_table.rowCount() == 1
    assert app.reference_records_table.rowCount() == 1
    assert app.project_checked_out_list.count() == 1
    assert app.project_reference_list.count() == 1

    app.all_records_search_edit.setText("beta")
    assert app.all_records_table.rowCount() == 1
    assert app.all_records_table.item(0, 0).toolTip().endswith("beta.dwg")

    app.project_records_search_edit.setText("alpha")
    assert app.project_records_table.rowCount() == 1

    app.reference_records_search_edit.setText("ref.pdf")
    assert app.reference_records_table.rowCount() == 1

    app.project_checked_out_search_edit.setText("alpha")
    assert app.project_checked_out_list.count() == 1
    assert app.project_checked_out_list.item(0).text() == "alpha_working_copy.dwg"

    app.project_reference_search_edit.setText("ref")
    assert app.project_reference_list.count() == 1
    assert app.project_reference_list.item(0).text() == "ref.pdf"


def test_checked_out_tab_remove_requires_identity_before_checkin(app_env, monkeypatch):
    # Condensed checked-out tab should not bypass identity validation when acting as check-in.
    app = app_env["app"]
    blocked = []

    app.favorites_tabs.setCurrentIndex(2)
    monkeypatch.setattr(app, "_validate_identity", lambda: False)
    monkeypatch.setattr(app, "_checkin_record_indexes", lambda _indexes: blocked.append("checkin"))

    app._remove_selected_favorites_from_active_tab()

    assert blocked == []

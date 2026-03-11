from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from app import CheckoutRecord


def test_view_selected_file_locations_from_list_opens_parent_directories(app_env, monkeypatch):
    # Favorites/local file lists should open containing folders, not the files themselves.
    app = app_env["app"]
    opened = []

    file_a = Path("/tmp/project/docs/a.pdf")
    file_b = Path("/tmp/project/docs/b.pdf")
    item_a = QListWidgetItem("a.pdf")
    item_a.setData(Qt.UserRole, str(file_a))
    item_b = QListWidgetItem("b.pdf")
    item_b.setData(Qt.UserRole, str(file_b))
    app.favorites_list.addItem(item_a)
    app.favorites_list.addItem(item_b)
    item_a.setSelected(True)
    item_b.setSelected(True)

    monkeypatch.setattr(app, "_open_paths", lambda paths: opened.extend(paths))
    app._view_selected_file_locations_from_list(app.favorites_list)

    assert opened == [file_a.parent]


def test_record_backed_lists_resolve_local_file_paths_for_location_actions(app_env, monkeypatch):
    # Checked-out/reference local lists store record indexes, so location helpers must resolve through records.
    app = app_env["app"]
    opened = []
    loaded = []

    checked_local = Path("/tmp/projects/current/checked_out/a.dwg")
    reference_local = Path("/tmp/projects/current/reference_copies/b.pdf")
    app.records = [
        CheckoutRecord(
            source_file="/srv/source/a.dwg",
            locked_source_file="/srv/source/a-JH.dwg",
            local_file=str(checked_local),
            initials="JH",
            project_name="Current",
            project_dir="/tmp/projects/current",
            source_root="/srv/source",
            checked_out_at="2026-03-11T10:00:00-05:00",
        ),
        CheckoutRecord(
            source_file="/srv/source/b.pdf",
            locked_source_file="",
            local_file=str(reference_local),
            initials="JH",
            project_name="Current",
            project_dir="/tmp/projects/current",
            source_root="/srv/source",
            checked_out_at="2026-03-11T10:05:00-05:00",
            record_type="reference_copy",
        ),
    ]

    checked_item = QListWidgetItem("a.dwg")
    checked_item.setData(Qt.UserRole, 0)
    app.project_checked_out_list.addItem(checked_item)
    checked_item.setSelected(True)

    reference_item = QListWidgetItem("b.pdf")
    reference_item.setData(Qt.UserRole, 1)
    app.project_reference_list.addItem(reference_item)
    reference_item.setSelected(True)

    monkeypatch.setattr(app, "_open_paths", lambda paths: opened.extend(paths))
    monkeypatch.setattr(
        app,
        "_set_current_directory_with_feedback",
        lambda directory, _message: loaded.append(directory),
    )
    monkeypatch.setattr(app, "_set_directory_tree_root", lambda _path: None)

    app._view_selected_file_locations_from_list(app.project_checked_out_list)
    app._load_selected_file_location_from_list(app.project_reference_list)

    assert opened == [checked_local.parent]
    assert loaded == [reference_local.parent]


def test_load_selected_file_location_prefers_matching_tracked_source_root(app_env, monkeypatch):
    # Loading a file location should keep the browser anchored to the nearest tracked source root when possible.
    app = app_env["app"]
    tmp = app_env["tmp"]

    root = tmp / "source-root"
    nested = root / "Area" / "Sub"
    nested.mkdir(parents=True)
    file_path = nested / "drawing.dwg"
    file_path.write_text("x", encoding="utf-8")

    root_item = QListWidgetItem(root.name)
    root_item.setData(Qt.UserRole, str(root))
    app.source_roots_list.addItem(root_item)

    favorite = QListWidgetItem(file_path.name)
    favorite.setData(Qt.UserRole, str(file_path))
    app.favorites_list.addItem(favorite)
    favorite.setSelected(True)

    set_roots = []
    monkeypatch.setattr(app, "_set_directory_tree_root", lambda path: set_roots.append(path))
    monkeypatch.setattr(
        app,
        "_set_current_directory_with_feedback",
        lambda directory, _message: setattr(app, "current_directory", directory),
    )

    app._load_selected_file_location_from_list(app.favorites_list)

    assert app.source_roots_list.currentItem() is root_item
    assert set_roots == [root]
    assert app.current_directory == nested


def test_copy_selected_as_reference_can_target_another_project(app_env):
    # Reference-copy flow should support storing the copy under another tracked project.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_root = tmp / "source-root"
    source_dir = source_root / "working"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "drawing-a.dwg"
    source_file.write_text("dwg-data", encoding="utf-8")

    current_project = tmp / "Projects" / "CurrentProject"
    other_project = tmp / "Projects" / "OtherProject"
    app._write_project_config(current_project, "CurrentProject", [str(source_root)])
    app._write_project_config(other_project, "OtherProject", [str(source_root)])

    app.initials_edit.setText("JH")
    app._load_project_from_dir(current_project)
    app.current_directory = source_dir
    app.records = []

    item = QListWidgetItem(source_file.name)
    item.setData(Qt.UserRole, str(source_file))
    app.files_list.addItem(item)
    item.setSelected(True)

    app._copy_selected_as_reference_to_project(other_project, [source_file])

    assert len(app.records) == 1
    record = app.records[0]
    assert record.record_type == "reference_copy"
    assert record.project_dir == str(other_project)
    assert record.project_name == "OtherProject"
    assert Path(record.local_file).exists()
    assert other_project in Path(record.local_file).parents


def test_copy_selected_as_reference_routes_to_target_project(app_env, monkeypatch):
    # Source-file context flow should honor the chooser target for reference copies.
    app = app_env["app"]
    selected = [Path("/tmp/source/A.dwg")]
    routed = []

    monkeypatch.setattr(app, "_selected_source_file_paths", lambda: selected)
    monkeypatch.setattr(
        app,
        "_choose_project_target",
        lambda **_kwargs: ("other", Path("/tmp/Projects/Elsewhere")),
    )
    monkeypatch.setattr(
        app,
        "_copy_selected_as_reference_to_project",
        lambda project_dir, paths=None: routed.append((project_dir, paths)),
    )

    app._copy_selected_as_reference()

    assert routed == [(Path("/tmp/Projects/Elsewhere"), selected)]

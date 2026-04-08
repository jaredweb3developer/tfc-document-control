from pathlib import Path

import app as app_module
from PySide6.QtWidgets import QInputDialog, QFileDialog, QMessageBox


def test_project_config_persists_local_directories(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "LocalConfig"
    source_root = tmp / "source-root"
    local_root = tmp / "local-root"
    source_root.mkdir(parents=True)
    local_root.mkdir(parents=True)

    app._write_project_config(
        project_dir=project_dir,
        name="LocalConfig",
        sources=[str(source_root)],
        local_directories=[str(local_root)],
        selected_source=str(source_root),
        selected_local_directory=str(local_root),
    )

    cfg = app._read_project_config(project_dir)
    assert cfg.get("local_directories") == [str(local_root)]
    assert cfg.get("selected_local_directory") == str(local_root)


def test_load_project_refreshes_local_roots_and_files(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "LocalLoad"
    source_root = tmp / "source-root"
    local_root = tmp / "local-root"
    source_root.mkdir(parents=True)
    local_root.mkdir(parents=True)
    (local_root / "A.txt").write_text("a", encoding="utf-8")
    (local_root / "B.pdf").write_text("b", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="LocalLoad",
        sources=[str(source_root)],
        local_directories=[str(local_root)],
        selected_source=str(source_root),
        selected_local_directory=str(local_root),
    )

    app._load_project_from_dir(project_dir)

    assert app.local_roots_list.count() == 1
    assert str(app.local_roots_list.item(0).data(app_module.Qt.UserRole)) == str(local_root)
    assert app.local_current_directory == local_root
    assert app.local_files_list.rowCount() == 2


def test_source_files_list_defaults_to_name_ascending(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_root = tmp / "source-root-sort"
    source_root.mkdir(parents=True)
    (source_root / "zeta.pdf").write_text("z", encoding="utf-8")
    (source_root / "alpha.pdf").write_text("a", encoding="utf-8")
    (source_root / "Middle.pdf").write_text("m", encoding="utf-8")

    app._set_directory_tree_root(source_root)
    app._set_current_directory(source_root)

    assert [app.files_list.item(row, 0).text() for row in range(app.files_list.rowCount())] == [
        "alpha.pdf",
        "Middle.pdf",
        "zeta.pdf",
    ]


def test_add_selected_local_files_to_source_copies_to_chosen_destination(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "Transfer"
    source_root = tmp / "source-root"
    source_dir = source_root / "dest"
    local_root = tmp / "local-root"
    source_dir.mkdir(parents=True)
    local_root.mkdir(parents=True)
    local_file = local_root / "from-local.dwg"
    local_file.write_text("dwg", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="Transfer",
        sources=[str(source_root)],
        local_directories=[str(local_root)],
        selected_source=str(source_root),
        selected_local_directory=str(local_root),
    )
    app.initials_edit.setText("JH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._load_project_from_dir(project_dir)
    app._set_local_current_directory(local_root)
    app.local_files_list.selectRow(0)

    monkeypatch.setattr(app, "_choose_source_destination_directory", lambda _start=None: source_dir)
    infos = []
    monkeypatch.setattr(app, "_info", lambda message: infos.append(message))

    app._add_selected_local_files_to_source()

    target_file = source_dir / "from-local.dwg"
    assert target_file.exists()
    rows = app._read_history_rows(source_dir)
    assert rows[-1]["action"] == "ADD_FILE"
    assert rows[-1]["file_name"] == "from-local.dwg"
    assert infos == ["Added 1 local file(s) to source."]


def test_local_files_list_excludes_directories(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    local_root = tmp / "local-root"
    child_dir = local_root / "child"
    child_dir.mkdir(parents=True)
    (local_root / "A.txt").write_text("a", encoding="utf-8")

    app._set_local_directory_tree_root(local_root)
    app._set_local_current_directory(local_root)

    assert app.local_files_list.rowCount() == 1
    assert app.local_files_list.item(0, 0).text() == "A.txt"
    assert all(app.local_files_list.item(row, 0).text() != "child" for row in range(app.local_files_list.rowCount()))


def test_local_files_list_defaults_to_name_ascending(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    local_root = tmp / "local-root-sort"
    local_root.mkdir(parents=True)
    (local_root / "zeta.pdf").write_text("z", encoding="utf-8")
    (local_root / "alpha.pdf").write_text("a", encoding="utf-8")
    (local_root / "Middle.pdf").write_text("m", encoding="utf-8")

    app._set_local_directory_tree_root(local_root)
    app._set_local_current_directory(local_root)

    assert [app.local_files_list.item(row, 0).text() for row in range(app.local_files_list.rowCount())] == [
        "alpha.pdf",
        "Middle.pdf",
        "zeta.pdf",
    ]


def test_local_directory_create_rename_move_and_delete(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    local_root = tmp / "local-root"
    destination = tmp / "destination"
    local_root.mkdir()
    destination.mkdir()
    app._set_local_directory_tree_root(local_root)
    app._set_local_current_directory(local_root)

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("created", True))
    app._create_directory_in_current_local()
    created = local_root / "created"
    assert created.is_dir()

    app._set_local_current_directory(local_root)
    for row in range(app.local_files_list.rowCount()):
        if app.local_files_list.item(row, 0).text() == "created":
            app.local_files_list.selectRow(row)
            break
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("renamed", True))
    app._rename_selected_local_item()
    renamed = local_root / "renamed"
    assert renamed.is_dir()
    assert not created.exists()

    for row in range(app.local_files_list.rowCount()):
        if app.local_files_list.item(row, 0).text() == "renamed":
            app.local_files_list.selectRow(row)
            break
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(destination))
    app._move_selected_local_items()
    moved = destination / "renamed"
    assert moved.is_dir()
    assert not renamed.exists()

    app._set_local_current_directory(destination)
    for row in range(app.local_files_list.rowCount()):
        if app.local_files_list.item(row, 0).text() == "renamed":
            app.local_files_list.selectRow(row)
            break
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    app._delete_selected_local_items()
    assert not moved.exists()


def test_add_selected_local_files_to_favorites_routes_to_target(app_env, monkeypatch):
    app = app_env["app"]
    selected = [Path("/tmp/local/A.dwg"), Path("/tmp/local/B.pdf")]
    called = []

    monkeypatch.setattr(app, "_selected_local_regular_file_paths", lambda: selected)
    monkeypatch.setattr(app, "_choose_favorite_target", lambda _paths: ("global", None))
    monkeypatch.setattr(app, "_add_favorite_paths_to_global", lambda paths: called.append(paths))

    app._add_selected_local_files_to_favorites()

    assert called == [selected]


def test_copy_selected_local_files_as_reference_creates_reference_record_without_tracking_source(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "LocalRef"
    local_root = tmp / "local-root"
    local_root.mkdir(parents=True)
    local_file = local_root / "manual.pdf"
    local_file.write_text("pdf", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="LocalRef",
        sources=[],
        local_directories=[str(local_root)],
        selected_local_directory=str(local_root),
    )
    app.initials_edit.setText("JH")
    app._load_project_from_dir(project_dir)
    app._set_local_current_directory(local_root)

    for row in range(app.local_files_list.rowCount()):
        if app.local_files_list.item(row, 0).text() == "manual.pdf":
            app.local_files_list.selectRow(row)
            break

    monkeypatch.setattr(app, "_choose_project_target", lambda **_kwargs: ("current", None))

    app._copy_selected_local_files_as_reference()

    assert len(app.records) == 1
    assert app.records[0].record_type == "reference_copy"
    assert app.records[0].source_file == str(local_file)
    assert Path(app.records[0].local_file).exists()
    cfg = app._read_project_config(project_dir)
    assert cfg.get("sources") == []

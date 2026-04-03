from pathlib import Path

import app as app_module


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

import json

from PySide6.QtCore import Qt


def test_move_tracked_project_up_updates_order(app_env):
    # Reordering tracked projects should update in-memory order and persisted projects file.
    app = app_env["app"]
    paths = app_env["paths"]
    tmp = app_env["tmp"]

    project_a = tmp / "Projects" / "A"
    project_b = tmp / "Projects" / "B"
    project_a.mkdir(parents=True)
    project_b.mkdir(parents=True)

    app.tracked_projects = [
        {"name": "A", "project_dir": str(project_a), "client": "", "year_started": ""},
        {"name": "B", "project_dir": str(project_b), "client": "", "year_started": ""},
    ]
    app._refresh_tracked_projects_list()

    # Select B and move it up.
    for row in range(app.tracked_projects_list.count()):
        item = app.tracked_projects_list.item(row)
        if item.data(Qt.UserRole) == str(project_b):
            app.tracked_projects_list.setCurrentItem(item)
            break
    app._move_selected_project_up()

    assert app.tracked_projects[0]["project_dir"] == str(project_b)
    payload = json.loads(paths["projects"].read_text(encoding="utf-8"))
    assert payload["tracked_projects"][0]["project_dir"] == str(project_b)


def test_move_favorite_updates_project_config_order(app_env):
    # Favorite move operations should persist order to project config.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavOrder"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)

    app._write_project_config(
        project_dir,
        "FavOrder",
        [str(source_dir)],
        favorites=["/x/one.txt", "/x/two.txt"],
    )
    app._load_project_from_dir(project_dir)

    app.favorites_list.setCurrentRow(1)
    app._move_selected_favorite_up()

    cfg = app._read_project_config(project_dir)
    assert cfg.get("favorites") == ["/x/two.txt", "/x/one.txt"]


def test_move_note_updates_project_config_order(app_env):
    # Notes move operations should persist order by note id in project config.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteOrder"
    source_dir = tmp / "src2"
    source_dir.mkdir(parents=True)

    notes = [
        {"id": "n1", "subject": "One", "body": "1", "created_at": "", "updated_at": ""},
        {"id": "n2", "subject": "Two", "body": "2", "created_at": "", "updated_at": ""},
    ]
    app._write_project_config(project_dir, "NoteOrder", [str(source_dir)], notes=notes)
    app._load_project_from_dir(project_dir)

    app.notes_list.setCurrentRow(1)
    app._move_selected_note_up()

    cfg = app._read_project_config(project_dir)
    note_ids = [note["id"] for note in cfg.get("notes", [])]
    assert note_ids == ["n2", "n1"]


def test_move_tracked_source_updates_project_config_order(app_env):
    # Tracked source directory move operations should persist source order.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_a = tmp / "src-a"
    source_b = tmp / "src-b"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)

    project_dir = tmp / "Projects" / "SourceOrder"
    app._write_project_config(
        project_dir,
        "SourceOrder",
        [str(source_a), str(source_b)],
        selected_source=str(source_b),
    )
    app._load_project_from_dir(project_dir)

    # Move source_b (row 1) up.
    app.source_roots_list.setCurrentRow(1)
    app._move_selected_source_up()

    cfg = app._read_project_config(project_dir)
    assert cfg.get("sources") == [str(source_b), str(source_a)]
    assert cfg.get("selected_source") == str(source_b)


def test_move_to_top_and_bottom_controls_persist(app_env):
    # Move-to-top/bottom should persist list ordering for project, favorites, notes, and sources.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_a = tmp / "Projects" / "A"
    project_b = tmp / "Projects" / "B"
    project_c = tmp / "Projects" / "C"
    project_a.mkdir(parents=True)
    project_b.mkdir(parents=True)
    project_c.mkdir(parents=True)

    app.tracked_projects = [
        {"name": "A", "project_dir": str(project_a), "client": "", "year_started": ""},
        {"name": "B", "project_dir": str(project_b), "client": "", "year_started": ""},
        {"name": "C", "project_dir": str(project_c), "client": "", "year_started": ""},
    ]
    app._refresh_tracked_projects_list()
    app.tracked_projects_list.setCurrentRow(2)
    app._move_selected_project_top()
    assert app.tracked_projects[0]["project_dir"] == str(project_c)

    src_a = tmp / "src-a"
    src_b = tmp / "src-b"
    src_c = tmp / "src-c"
    src_a.mkdir(parents=True)
    src_b.mkdir(parents=True)
    src_c.mkdir(parents=True)
    project_dir = tmp / "Projects" / "OrderTopBottom"
    notes = [
        {"id": "n1", "subject": "One", "body": "1", "created_at": "", "updated_at": ""},
        {"id": "n2", "subject": "Two", "body": "2", "created_at": "", "updated_at": ""},
        {"id": "n3", "subject": "Three", "body": "3", "created_at": "", "updated_at": ""},
    ]
    favorites = ["/x/one.txt", "/x/two.txt", "/x/three.txt"]
    app._write_project_config(
        project_dir,
        "OrderTopBottom",
        [str(src_a), str(src_b), str(src_c)],
        favorites=favorites,
        notes=notes,
        selected_source=str(src_a),
    )
    app._load_project_from_dir(project_dir)

    app.favorites_list.setCurrentRow(0)
    app._move_selected_favorite_bottom()
    cfg = app._read_project_config(project_dir)
    assert cfg.get("favorites") == ["/x/two.txt", "/x/three.txt", "/x/one.txt"]

    app.notes_list.setCurrentRow(0)
    app._move_selected_note_bottom()
    cfg = app._read_project_config(project_dir)
    assert [note["id"] for note in cfg.get("notes", [])] == ["n2", "n3", "n1"]

    app.source_roots_list.setCurrentRow(2)
    app._move_selected_source_top()
    cfg = app._read_project_config(project_dir)
    assert cfg.get("sources") == [str(src_c), str(src_a), str(src_b)]

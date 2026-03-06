from PySide6.QtCore import Qt


def test_selected_source_is_saved_and_loaded(app_env):
    # A project config can persist which tracked source root should be active.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_a = tmp / "src-a"
    source_b = tmp / "src-b"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)

    project_dir = tmp / "Projects" / "P1"
    app._write_project_config(
        project_dir,
        "P1",
        [str(source_a), str(source_b)],
        selected_source=str(source_b),
    )

    app._load_project_from_dir(project_dir)
    assert app._current_source_root_value() == str(source_b)


def test_selected_source_updates_when_user_changes_selection(app_env):
    # Changing the tracked source selection in UI should update project config.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_a = tmp / "src-1"
    source_b = tmp / "src-2"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)

    project_dir = tmp / "Projects" / "P2"
    app._write_project_config(
        project_dir,
        "P2",
        [str(source_a), str(source_b)],
        selected_source=str(source_a),
    )

    app._load_project_from_dir(project_dir)

    # Simulate user selecting source_b in the tracked source list.
    for row in range(app.source_roots_list.count()):
        item = app.source_roots_list.item(row)
        if item.data(Qt.UserRole) == str(source_b):
            app.source_roots_list.setCurrentItem(item)
            break

    # Config should now remember source_b as last-selected source.
    cfg = app._read_project_config(project_dir)
    assert cfg.get("selected_source") == str(source_b)

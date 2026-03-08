def test_tracked_projects_search_matches_customization_groups(app_env):
    # Tracked project search should include assigned customization group names.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_a = tmp / "Projects" / "Alpha"
    project_b = tmp / "Projects" / "Beta"
    project_a.mkdir(parents=True, exist_ok=True)
    project_b.mkdir(parents=True, exist_ok=True)
    app.tracked_projects = [
        {"name": "Alpha", "project_dir": str(project_a), "client": "", "year_started": ""},
        {"name": "Beta", "project_dir": str(project_b), "client": "", "year_started": ""},
    ]
    app._set_item_customization(
        "tracked_projects",
        str(project_a),
        {"groups": ["Urgent Team"]},
    )

    app.project_search_edit.setText("urgent team")
    app._refresh_tracked_projects_list()
    assert app.tracked_projects_list.count() == 1
    assert app.tracked_projects_list.item(0).text() == "Alpha"


def test_project_favorites_search_matches_customization_groups(app_env):
    # Project favorites search should include assigned customization group names.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavSearch"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    fav_a = str(tmp / "alpha.dwg")
    fav_b = str(tmp / "beta.pdf")
    app._write_project_config(project_dir, "FavSearch", [str(source_dir)], favorites=[fav_a, fav_b])
    app._load_project_from_dir(project_dir)
    app._set_item_customization("project_favorites", fav_b, {"groups": ["Vendor Docs"]})

    app.project_favorites_search_edit.setText("vendor docs")
    app._refresh_favorites_list(app._current_project_favorites())
    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "beta.pdf"


def test_global_favorites_search_matches_customization_groups(app_env):
    # Global favorites search should include assigned customization group names.
    app = app_env["app"]
    tmp = app_env["tmp"]

    favorite_a = str(tmp / "a.dwg")
    favorite_b = str(tmp / "b.pdf")
    app.global_favorites = [favorite_a, favorite_b]
    app._set_item_customization("global_favorites", favorite_b, {"groups": ["Outside"]})

    app.global_favorites_search_edit.setText("outside")
    app._refresh_global_favorites_list()
    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "b.pdf"


def test_project_notes_search_matches_customization_groups(app_env):
    # Notes search should include note text and note customization group names.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteSearch"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    notes = [
        {
            "id": "n1",
            "subject": "Pump revision",
            "body": "Coordinate with electrical",
            "created_at": "2026-03-08T10:00:00-05:00",
            "updated_at": "2026-03-08T10:00:00-05:00",
        }
    ]
    app._write_project_config(project_dir, "NoteSearch", [str(source_dir)], notes=notes)
    app._load_project_from_dir(project_dir)
    app._set_item_customization("project_notes", "n1", {"groups": ["QA Review"]})

    app.project_notes_search_edit.setText("qa review")
    app._refresh_notes_list(app._current_project_notes())
    assert app.notes_list.count() == 1
    assert app.notes_list.item(0).text() == "Pump revision"

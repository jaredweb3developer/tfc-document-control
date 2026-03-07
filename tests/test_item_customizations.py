from pathlib import Path


def test_item_customizations_persist_to_config_file(app_env):
    # Persist a customization, then reopen the app and confirm it loads back.
    app = app_env["app"]
    paths = app_env["paths"]
    create_app = app_env["create_app"]

    app.item_customization_groups = ["Priority"]
    app._set_item_customization(
        "tracked_projects",
        "/tmp/project-a",
        {
            "groups": ["Priority"],
            "background": "#102030",
            "auto_contrast": True,
        },
    )

    assert paths["item_customizations"].exists()

    reloaded = create_app()
    try:
        assert "Priority" in reloaded.item_customization_groups
        custom = reloaded._item_customization_for("tracked_projects", "/tmp/project-a")
        assert custom.get("background") == "#102030"
        assert custom.get("groups") == ["Priority"]
    finally:
        reloaded.close()
        reloaded.deleteLater()


def test_tracked_project_list_item_uses_saved_color_and_group(app_env):
    # Styles should be applied when list rows are rebuilt from tracked project data.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "Alpha"
    project_dir.mkdir(parents=True, exist_ok=True)
    app.tracked_projects = [
        {
            "name": "Alpha",
            "project_dir": str(project_dir),
            "client": "",
            "year_started": "",
        }
    ]
    app._set_item_customization(
        "tracked_projects",
        str(project_dir),
        {"groups": ["Client-A"], "background": "#001133", "auto_contrast": True},
    )
    app._refresh_tracked_projects_list()

    item = app.tracked_projects_list.item(0)
    assert item is not None
    assert item.background().color().name().upper() == "#001133"
    # Auto-contrast should select a readable light font on this dark highlight.
    assert item.foreground().color().name().upper() == "#FFFFFF"
    assert "Groups: Client-A" in item.toolTip()


def test_effective_font_color_prefers_manual_and_falls_back_to_contrast(app_env):
    # Manual font wins; otherwise auto-contrast computes black/white from highlight.
    app = app_env["app"]

    assert app._effective_font_color("#111111", "#00FF00", True) == "#00FF00"
    assert app._effective_font_color("#111111", "", True) == "#FFFFFF"
    assert app._effective_font_color("#F0F0F0", "", True) == "#000000"

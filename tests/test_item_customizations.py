import json


def test_item_customizations_persist_to_config_file(app_env):
    # Persist a customization, then reopen the app and confirm it loads back.
    app = app_env["app"]
    paths = app_env["paths"]

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
    assert app.item_customizations == {
        "tracked_projects": {
            "/tmp/project-a": {
                "groups": ["Priority"],
                "background": "#102030",
                "auto_contrast": True,
            }
        }
    }
    assert app._default_item_customizations_file() == paths["item_customizations"]
    payload = json.loads(paths["item_customizations"].read_text(encoding="utf-8"))
    assert payload["scopes"]["tracked_projects"]["/tmp/project-a"]["background"] == "#102030"
    assert app._normalize_item_customization(
        payload["scopes"]["tracked_projects"]["/tmp/project-a"]
    ).get("background") == "#102030"

    assert paths["item_customizations"].exists()
    app.item_customization_groups = []
    app.item_customizations = {}
    app.item_customization_group_styles = {}
    app._load_item_customizations()
    assert "Priority" in app.item_customization_groups
    custom = app._item_customization_for("tracked_projects", "/tmp/project-a")
    assert custom.get("background") == "#102030"
    assert custom.get("groups") == ["Priority"]


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


def test_group_colors_can_drive_item_style_when_enabled(app_env):
    # If use_group_colors is enabled, the first group's colors should style the item.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "GroupStyle"
    project_dir.mkdir(parents=True, exist_ok=True)
    app.tracked_projects = [
        {
            "name": "GroupStyle",
            "project_dir": str(project_dir),
            "client": "",
            "year_started": "",
        }
    ]
    app.item_customization_groups = ["QA"]
    app.item_customization_group_styles["QA"] = {
        "background": "#224466",
        "font": "#F8F8F8",
        "auto_contrast": True,
    }
    app._set_item_customization(
        "tracked_projects",
        str(project_dir),
        {"groups": ["QA"], "use_group_colors": True},
    )
    app._refresh_tracked_projects_list()

    item = app.tracked_projects_list.item(0)
    assert item is not None
    assert item.background().color().name().upper() == "#224466"
    assert item.foreground().color().name().upper() == "#F8F8F8"
    assert "Using Group Colors: QA" in item.toolTip()


def test_first_group_assignment_defaults_to_group_colors(app_env):
    # New group assignment should default use_group_colors on unless user overrides it.
    app = app_env["app"]

    assert app._resolve_use_group_colors({}, ["Alpha"], False, False) is True
    assert app._resolve_use_group_colors({}, ["Alpha"], False, True) is False
    assert app._resolve_use_group_colors({"groups": ["Alpha"]}, ["Alpha"], False, False) is False


def test_auto_enable_group_colors_checkbox_on_first_group_selection(app_env):
    # The dialog checkbox should auto-enable only on first group assignment when untouched.
    app = app_env["app"]

    assert app._should_auto_enable_group_colors_checkbox(False, 0, 1, False) is True
    assert app._should_auto_enable_group_colors_checkbox(False, 1, 2, False) is False
    assert app._should_auto_enable_group_colors_checkbox(True, 0, 1, False) is False
    assert app._should_auto_enable_group_colors_checkbox(False, 0, 1, True) is False

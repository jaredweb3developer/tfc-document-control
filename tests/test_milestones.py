def test_project_config_normalizes_milestones(app_env):
    # Milestone entries in project config should be normalized and invalid ones skipped.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "MilestoneRoundTrip"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)

    app._write_project_config(
        project_dir=project_dir,
        name="MilestoneRoundTrip",
        sources=[str(source_dir)],
        milestones=[
            {
                "id": "m1",
                "name": "Initial Snapshot",
                "description": "baseline",
                "created_at": "2026-03-06T10:00:00-05:00",
                "updated_at": "2026-03-06T10:00:00-05:00",
                "snapshot": {"record_count": 0, "records": []},
            },
            {"id": "bad", "name": "   "},  # Invalid: empty normalized name.
        ],
    )

    cfg = app._read_project_config(project_dir)
    milestones = cfg.get("milestones", [])
    assert isinstance(milestones, list)
    assert len(milestones) == 1
    assert milestones[0]["name"] == "Initial Snapshot"


def test_create_and_remove_milestone_updates_project_config(app_env, monkeypatch):
    # Creating/removing milestones from the UI helpers should persist to dctl.json.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "MilestoneCRUD"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)
    app._write_project_config(project_dir=project_dir, name="MilestoneCRUD", sources=[str(source_dir)])
    app._load_project_from_dir(project_dir)

    monkeypatch.setattr(
        app,
        "_show_milestone_dialog",
        lambda: {
            "id": "m-create",
            "name": "Milestone A",
            "description": "created in test",
            "created_at": "2026-03-06T11:00:00-05:00",
            "updated_at": "2026-03-06T11:00:00-05:00",
            "snapshot": {"record_count": 0, "records": []},
        },
    )

    app._create_milestone()
    cfg = app._read_project_config(project_dir)
    assert len(cfg.get("milestones", [])) == 1
    assert app.milestones_list.count() == 1

    app.milestones_list.setCurrentRow(0)
    app._remove_selected_milestone()
    cfg = app._read_project_config(project_dir)
    assert cfg.get("milestones", []) == []
    assert app.milestones_list.count() == 0

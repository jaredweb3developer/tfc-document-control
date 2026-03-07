from pathlib import Path

from app import CheckoutRecord


def test_global_favorites_and_notes_persist(app_env, monkeypatch):
    # Global favorites/notes should persist to dedicated root-level files.
    app = app_env["app"]
    paths = app_env["paths"]

    fake_file = app_env["tmp"] / "x.txt"
    fake_file.write_text("x", encoding="utf-8")
    app.global_favorites = [str(fake_file)]
    app.global_notes = [
        {
            "id": "n1",
            "subject": "Global note",
            "body": "Body",
            "created_at": "2026-03-06T10:00:00-05:00",
            "updated_at": "2026-03-06T10:00:00-05:00",
        }
    ]
    app._save_global_favorites()
    app._save_global_notes()

    reloaded = app_env["create_app"]()
    try:
        assert str(fake_file) in reloaded.global_favorites
        assert any(note.get("subject") == "Global note" for note in reloaded.global_notes)
        assert paths["global_favorites"].exists()
        assert paths["global_notes"].exists()
    finally:
        reloaded.close()
        reloaded.deleteLater()


def test_transfer_project_files_move_updates_record(app_env):
    # Moving tracked file between projects should move file and retarget record project metadata.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src_project = tmp / "Projects" / "SourceP"
    dst_project = tmp / "Projects" / "TargetP"
    src_project.mkdir(parents=True)
    dst_project.mkdir(parents=True)
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)

    local_file = src_project / "checked_out" / "A.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("A", encoding="utf-8")
    record = CheckoutRecord(
        source_file=str(source_dir / "A.dwg"),
        locked_source_file=str(source_dir / "A-JWH.dwg"),
        local_file=str(local_file),
        initials="JWH",
        project_name="SourceP",
        project_dir=str(src_project),
        source_root=str(source_dir),
        checked_out_at="2026-03-06T10:00:00-05:00",
        record_type="checked_out",
    )
    app.records = [record]
    app.tracked_projects = [
        {"name": "SourceP", "project_dir": str(src_project), "client": "", "year_started": ""},
        {"name": "TargetP", "project_dir": str(dst_project), "client": "", "year_started": ""},
    ]

    rows = [
        {
            "record_idx": 0,
            "record_type": "checked_out",
            "local_file": str(local_file),
            "file_name": "A.dwg",
            "source_file": record.source_file,
            "revisions": 0,
        }
    ]
    errors = app._transfer_project_files(rows, src_project, dst_project, "move")
    assert errors == []
    assert app.records[0].project_dir == str(dst_project)
    assert app.records[0].project_name == "TargetP"
    assert Path(app.records[0].local_file).exists()
    assert not local_file.exists()


def test_favorites_can_be_added_between_project_and_global(app_env):
    # Project favorites should be addable to global and global favorites back to project.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavXfer"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    app._write_project_config(project_dir, "FavXfer", [str(source_dir)], favorites=[str(tmp / "a.dwg")])
    app._load_project_from_dir(project_dir)

    app.favorites_list.setCurrentRow(0)
    app.favorites_list.item(0).setSelected(True)
    app._add_selected_project_favorites_to_global()
    assert str(tmp / "a.dwg") in app.global_favorites

    app.global_favorites = [str(tmp / "b.dwg")]
    app._refresh_global_favorites_list()
    app.global_favorites_list.setCurrentRow(0)
    app.global_favorites_list.item(0).setSelected(True)
    app._add_selected_global_favorites_to_project()
    assert str(tmp / "b.dwg") in app._current_project_favorites()

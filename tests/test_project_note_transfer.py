from pathlib import Path


def test_copy_selected_note_to_project_preserves_content_and_keeps_source(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "src-a"
    source_dir.mkdir(parents=True)
    source_project = tmp / "Projects" / "Source"
    target_project = tmp / "Projects" / "Target"

    source_note = {
        "id": "note-1",
        "subject": "Pump Update",
        "body": "Review pending",
        "created_at": "2026-04-02T09:00:00",
        "updated_at": "2026-04-02T09:01:00",
    }
    app._write_project_config(source_project, "Source", [str(source_dir)], notes=[source_note])
    app._write_project_config(target_project, "Target", [str(source_dir)], notes=[])
    app._register_tracked_project("Source", source_project)
    app._register_tracked_project("Target", target_project)
    app._load_project_from_dir(source_project)
    app.notes_list.setCurrentRow(0)

    monkeypatch.setattr(app, "_choose_project_note_transfer_target", lambda _label: Path(target_project))

    app._copy_selected_note_to_project()

    source_cfg = app._read_project_config(source_project)
    target_cfg = app._read_project_config(target_project)
    assert len(source_cfg.get("notes", [])) == 1
    assert len(target_cfg.get("notes", [])) == 1
    copied = target_cfg["notes"][0]
    assert copied["subject"] == source_note["subject"]
    assert copied["body"] == source_note["body"]
    assert copied["created_at"] == source_note["created_at"]
    assert copied["updated_at"] == source_note["updated_at"]
    assert copied["id"] != source_note["id"]


def test_move_selected_note_to_project_removes_source_after_copy(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "src-b"
    source_dir.mkdir(parents=True)
    source_project = tmp / "Projects" / "SourceMove"
    target_project = tmp / "Projects" / "TargetMove"

    source_note = {
        "id": "note-2",
        "subject": "Valve Note",
        "body": "Transferred",
        "created_at": "2026-04-02T09:10:00",
        "updated_at": "2026-04-02T09:11:00",
    }
    app._write_project_config(source_project, "SourceMove", [str(source_dir)], notes=[source_note])
    app._write_project_config(target_project, "TargetMove", [str(source_dir)], notes=[])
    app._register_tracked_project("SourceMove", source_project)
    app._register_tracked_project("TargetMove", target_project)
    app._load_project_from_dir(source_project)
    app.notes_list.setCurrentRow(0)

    monkeypatch.setattr(app, "_choose_project_note_transfer_target", lambda _label: Path(target_project))

    app._move_selected_note_to_project()

    source_cfg = app._read_project_config(source_project)
    target_cfg = app._read_project_config(target_project)
    assert source_cfg.get("notes", []) == []
    assert len(target_cfg.get("notes", [])) == 1
    moved = target_cfg["notes"][0]
    assert moved["subject"] == source_note["subject"]
    assert moved["body"] == source_note["body"]
    assert moved["created_at"] == source_note["created_at"]
    assert moved["updated_at"] == source_note["updated_at"]
    assert moved["id"] != source_note["id"]

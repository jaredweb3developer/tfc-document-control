import json
from pathlib import Path

from app import CheckoutRecord, PendingCheckinAction


def test_create_revision_snapshot_for_record_writes_registry_and_hash(app_env):
    # A revision snapshot should copy the local file and persist hash/id metadata.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "RevProject"
    project_dir.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "A.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("REV-A", encoding="utf-8")

    record = CheckoutRecord(
        source_file=str(tmp / "src" / "A.dwg"),
        locked_source_file=str(tmp / "src" / "A-JWH.dwg"),
        local_file=str(local_file),
        initials="JWH",
        project_name="RevProject",
        project_dir=str(project_dir),
        source_root=str(tmp / "src"),
        checked_out_at="2026-03-06T12:00:00-05:00",
    )

    revision = app._create_revision_snapshot_for_record(record, note="baseline")
    assert revision is not None
    assert str(revision["id"]).startswith("R")
    assert "sha256" in revision

    registry_path = project_dir / "file_versions.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    assert isinstance(files, dict)
    assert len(files) == 1
    file_entry = next(iter(files.values()))
    revisions = file_entry.get("revisions", [])
    assert len(revisions) == 1
    snapshot_rel = revisions[0]["snapshot_file"]
    assert (project_dir / snapshot_rel).exists()


def test_switch_selected_record_to_revision_replaces_local_contents(app_env, monkeypatch):
    # Switching to an earlier revision should restore that snapshot into the local working file.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "SwitchProject"
    project_dir.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "B.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("ORIGINAL", encoding="utf-8")

    record = CheckoutRecord(
        source_file=str(tmp / "src" / "B.dwg"),
        locked_source_file=str(tmp / "src" / "B-JWH.dwg"),
        local_file=str(local_file),
        initials="JWH",
        project_name="SwitchProject",
        project_dir=str(project_dir),
        source_root=str(tmp / "src"),
        checked_out_at="2026-03-06T12:00:00-05:00",
    )
    app.records = [record]
    app._render_records_tables()
    app.all_records_table.selectRow(0)

    revision = app._create_revision_snapshot_for_record(record, note="baseline")
    assert revision is not None
    local_file.write_text("MODIFIED", encoding="utf-8")

    monkeypatch.setattr(app, "_ensure_saved_state_before_revision_switch", lambda _record: True)
    monkeypatch.setattr(app, "_choose_revision_for_record", lambda _record: revision)
    app._switch_selected_record_to_revision()

    assert local_file.read_text(encoding="utf-8") == "ORIGINAL"


def test_checkin_writes_revision_id_to_history_and_versions(app_env):
    # Check-in should create a stored revision and record its revision id in history csv.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "src-checkin"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "C.dwg"
    locked_file = source_dir / "C-JWH.dwg"
    locked_file.write_text("LOCKED_STATE", encoding="utf-8")

    project_dir = tmp / "Projects" / "CheckinRevision"
    project_dir.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "C.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("LOCAL_STATE", encoding="utf-8")

    record = CheckoutRecord(
        source_file=str(source_file),
        locked_source_file=str(locked_file),
        local_file=str(local_file),
        initials="JWH",
        project_name="CheckinRevision",
        project_dir=str(project_dir),
        source_root=str(source_dir),
        checked_out_at="2026-03-06T12:00:00-05:00",
    )
    app.records = [record]

    action = PendingCheckinAction(
        file_name="C.dwg",
        source_file=str(source_file),
        locked_source_file=str(locked_file),
        action_mode="unchanged",
        local_file="",
        record_idx=0,
        reason="test",
    )
    errors = app._perform_pending_checkin_actions([action], "standard")
    assert errors == []
    assert source_file.exists()
    assert source_file.read_text(encoding="utf-8") == "LOCKED_STATE"

    history_rows = app._read_history_rows(source_dir)
    assert history_rows[-1]["action"] == "CHECK_IN_UNCHANGED"
    revision_id = history_rows[-1].get("revision_id", "")
    assert revision_id

    registry = json.loads((project_dir / "file_versions.json").read_text(encoding="utf-8"))
    file_entry = next(iter(registry["files"].values()))
    revisions = file_entry["revisions"]
    assert revisions[-1]["id"] == revision_id
    assert (project_dir / revisions[-1]["snapshot_file"]).exists()


def test_revision_checkin_lookup_maps_checked_in_revisions(app_env):
    # Revision manager should be able to mark revisions that were checked in.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "src-rev-map"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "D.dwg"
    source_file.write_text("x", encoding="utf-8")

    project_dir = tmp / "Projects" / "RevMap"
    project_dir.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "D.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("local", encoding="utf-8")

    record = CheckoutRecord(
        source_file=str(source_file),
        locked_source_file=str(source_dir / "D-JWH.dwg"),
        local_file=str(local_file),
        initials="JWH",
        project_name="RevMap",
        project_dir=str(project_dir),
        source_root=str(source_dir),
        checked_out_at="2026-03-06T12:00:00-05:00",
    )

    app._append_history(source_dir, "CHECK_OUT", "D.dwg", "")
    app._append_history(source_dir, "CHECK_IN_MODIFIED", "D.dwg", "R260306120000-ABCD")
    app._append_history(source_dir, "ADD_FILE", "Other.dwg", "R999")

    indexed = app._checkin_history_by_revision_id_for_record(record)
    assert "R260306120000-ABCD" in indexed
    assert indexed["R260306120000-ABCD"]["action"] == "CHECK_IN_MODIFIED"
    assert "R999" not in indexed


def test_rename_then_checkout_then_checkin_preserves_file_id_lineage(app_env):
    # A file renamed before checkout should keep one file_id through checkout, revision, and check-in.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "src-rename-checkin"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "A.dwg"
    source_file.write_text("SOURCE", encoding="utf-8")

    project_dir = tmp / "Projects" / "RenameCheckin"
    project_dir.mkdir(parents=True)
    app.current_project_dir = str(project_dir)
    app.current_directory = source_dir
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "ADD_FILE", "A.dwg")
    app._refresh_source_files()

    index_before = app._ensure_source_index(source_dir)
    files_before = index_before.get("files", {})
    assert isinstance(files_before, dict)
    original_file_id = next(iter(files_before.keys()))

    # Rename A.dwg -> B.dwg
    source_file.rename(source_dir / "B.dwg")
    index_entry = dict(files_before[original_file_id])
    index_entry["current_name"] = "B.dwg"
    index_entry["canonical_name"] = "B.dwg"
    index_entry["known_names"] = ["A.dwg", "B.dwg"]
    files_before[original_file_id] = index_entry
    app._save_source_index(source_dir, index_before)
    app._append_history(source_dir, "RENAME", "B.dwg", file_id=original_file_id, previous_file_name="A.dwg")

    app._refresh_source_files()
    item = app.files_list.item(0)
    item.setSelected(True)
    app.files_list.setCurrentItem(item)

    app._checkout_selected()

    assert len(app.records) == 1
    record = app.records[0]
    assert record.file_id == original_file_id

    local_path = Path(record.local_file)
    local_path.write_text("MODIFIED", encoding="utf-8")

    action = PendingCheckinAction(
        file_name="B.dwg",
        source_file=str(source_dir / "B.dwg"),
        locked_source_file=str(source_dir / "B-JWH.dwg"),
        action_mode="modified",
        local_file=str(local_path),
        record_idx=0,
        reason="test",
    )
    errors = app._perform_pending_checkin_actions([action], "standard")
    assert errors == []

    history_rows = app._read_history_rows(source_dir)
    file_ids = [row.get("file_id", "") for row in history_rows]
    assert original_file_id in file_ids
    assert history_rows[-1]["action"] == "CHECK_IN_MODIFIED"
    assert history_rows[-1]["file_id"] == original_file_id

    registry = json.loads((project_dir / "file_versions.json").read_text(encoding="utf-8"))
    files = registry.get("files", {})
    assert original_file_id in files

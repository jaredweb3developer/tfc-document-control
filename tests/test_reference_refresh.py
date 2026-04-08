import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from app import CheckoutRecord


def test_load_records_defaults_reference_refresh_metadata_for_legacy_rows(app_env):
    app = app_env["app"]
    paths = app_env["paths"]

    records_payload = {
        "schema_version": 1,
        "app_version": "0.2.2",
        "records": [
            {
                "source_file": "V:/src/spec.pdf",
                "locked_source_file": "",
                "local_file": "C:/projects/spec.pdf",
                "initials": "JH",
                "project_name": "Legacy",
                "project_dir": "C:/projects/Legacy",
                "source_root": "V:/src",
                "checked_out_at": "2026-04-08T12:00:00-04:00",
                "record_type": "reference_copy",
            }
        ],
    }
    paths["records"].parent.mkdir(parents=True, exist_ok=True)
    paths["records"].write_text(json.dumps(records_payload), encoding="utf-8")

    app._load_records()

    assert len(app.records) == 1
    record = app.records[0]
    assert record.record_type == "reference_copy"
    assert record.source_hash_at_copy == ""
    assert record.local_hash_at_copy == ""
    assert record.source_mtime_at_copy == 0.0
    assert record.local_mtime_at_copy == 0.0
    assert record.source_size_at_copy == 0
    assert record.local_size_at_copy == 0
    assert record.last_refreshed_at == ""


def test_save_and_load_records_round_trip_reference_refresh_metadata(app_env):
    app = app_env["app"]
    create_app = app_env["create_app"]

    app.records = [
        CheckoutRecord(
            source_file="V:/src/spec.pdf",
            locked_source_file="",
            local_file="C:/projects/spec.pdf",
            initials="JH",
            project_name="RoundTrip",
            project_dir="C:/projects/RoundTrip",
            source_root="V:/src",
            checked_out_at="2026-04-08T12:00:00-04:00",
            id="r_roundtrip",
            record_type="reference_copy",
            file_id="file_123",
            source_hash_at_copy="abc123",
            local_hash_at_copy="def456",
            source_mtime_at_copy=101.25,
            local_mtime_at_copy=202.5,
            source_size_at_copy=1234,
            local_size_at_copy=5678,
            last_refreshed_at="2026-04-08T13:30:00-04:00",
        )
    ]

    app._save_records()
    saved = json.loads(app._records_file_path().read_text(encoding="utf-8"))
    saved_row = saved["records"][0]

    assert saved_row["source_hash_at_copy"] == "abc123"
    assert saved_row["local_hash_at_copy"] == "def456"
    assert saved_row["source_mtime_at_copy"] == 101.25
    assert saved_row["local_mtime_at_copy"] == 202.5
    assert saved_row["source_size_at_copy"] == 1234
    assert saved_row["local_size_at_copy"] == 5678
    assert saved_row["last_refreshed_at"] == "2026-04-08T13:30:00-04:00"

    reloaded_app = create_app()
    try:
        reloaded_app._load_records()
        assert len(reloaded_app.records) == 1
        record = reloaded_app.records[0]
        assert record.source_hash_at_copy == "abc123"
        assert record.local_hash_at_copy == "def456"
        assert record.source_mtime_at_copy == 101.25
        assert record.local_mtime_at_copy == 202.5
        assert record.source_size_at_copy == 1234
        assert record.local_size_at_copy == 5678
        assert record.last_refreshed_at == "2026-04-08T13:30:00-04:00"
    finally:
        reloaded_app.close()
        reloaded_app.deleteLater()


def _build_reference_record(tmp_path, **overrides):
    source_file = tmp_path / "src" / "spec.pdf"
    local_file = tmp_path / "project" / "reference_copies" / "spec.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("baseline", encoding="utf-8")
    local_file.write_text("baseline", encoding="utf-8")

    record = CheckoutRecord(
        source_file=str(source_file),
        locked_source_file="",
        local_file=str(local_file),
        initials="JH",
        project_name="ReferenceStatus",
        project_dir=str(tmp_path / "project"),
        source_root=str(source_file.parent),
        checked_out_at="2026-04-08T12:00:00-04:00",
        id="rec_status_1",
        record_type="reference_copy",
    )
    record.source_hash_at_copy = ""
    record.local_hash_at_copy = ""
    record.source_mtime_at_copy = 0.0
    record.local_mtime_at_copy = 0.0
    record.source_size_at_copy = 0
    record.local_size_at_copy = 0
    record.last_refreshed_at = ""

    return record, source_file, local_file


def test_reference_status_up_to_date(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])
    copied_at = "2026-04-08T12:30:00-04:00"

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at=copied_at,
    )

    status = app._reference_status_for_record(record)

    assert status["status"] == "up_to_date"
    assert status["default_action"] == "none"
    assert status["source_changed"] is False
    assert status["local_changed"] is False


def test_reference_status_source_changed_safe(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.write_text("source changed", encoding="utf-8")

    status = app._reference_status_for_record(record)

    assert status["status"] == "source_changed_safe"
    assert status["default_action"] == "replace"
    assert status["source_changed"] is True
    assert status["local_changed"] is False


def test_reference_status_local_changed_only(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    local_file.write_text("local changed", encoding="utf-8")

    status = app._reference_status_for_record(record)

    assert status["status"] == "local_changed_only"
    assert status["default_action"] == "keep"
    assert status["source_changed"] is False
    assert status["local_changed"] is True


def test_reference_status_both_changed_conflict(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.write_text("source changed", encoding="utf-8")
    local_file.write_text("local changed", encoding="utf-8")

    status = app._reference_status_for_record(record)

    assert status["status"] == "both_changed_conflict"
    assert status["default_action"] == "skip"
    assert status["source_changed"] is True
    assert status["local_changed"] is True


def test_reference_status_source_missing(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.unlink()

    status = app._reference_status_for_record(record)

    assert status["status"] == "source_missing"
    assert status["default_action"] == "skip"
    assert status["source_exists"] is False


def test_reference_status_local_missing(app_env):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    local_file.unlink()

    status = app._reference_status_for_record(record)

    assert status["status"] == "local_missing"
    assert status["default_action"] == "skip"
    assert status["local_exists"] is False


def test_reference_status_untracked_state_for_legacy_baseline(app_env):
    app = app_env["app"]
    record, _source_file, _local_file = _build_reference_record(app_env["tmp"])

    status = app._reference_status_for_record(record)

    assert status["status"] == "untracked_state"
    assert status["default_action"] == "skip"


def test_current_project_reference_status_rows_filters_to_current_project(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "ReferenceStatus"
    other_project_dir = tmp / "Projects" / "OtherProject"
    project_dir.mkdir(parents=True, exist_ok=True)
    other_project_dir.mkdir(parents=True, exist_ok=True)

    record_a, source_a, local_a = _build_reference_record(tmp / "a")
    record_a.project_dir = str(project_dir)
    record_a.project_name = "ReferenceStatus"
    record_a.id = "rec_a"
    app._apply_reference_copy_baseline(
        record_a,
        source_path=source_a,
        local_path=local_a,
        copied_at="2026-04-08T12:30:00-04:00",
    )

    record_b, source_b, local_b = _build_reference_record(tmp / "b")
    record_b.project_dir = str(other_project_dir)
    record_b.project_name = "OtherProject"
    record_b.id = "rec_b"
    app._apply_reference_copy_baseline(
        record_b,
        source_path=source_b,
        local_path=local_b,
        copied_at="2026-04-08T12:35:00-04:00",
    )

    app.current_project_dir = str(project_dir)
    app.records = [record_a, record_b]

    rows = app._current_project_reference_status_rows()

    assert len(rows) == 1
    assert rows[0]["record_id"] == "rec_a"
    assert rows[0]["status"]["status"] == "up_to_date"


def test_refresh_selected_project_references_updates_local_copy_and_metadata(app_env, monkeypatch):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.write_text("source changed", encoding="utf-8")

    app.records = [record]
    app.current_project_dir = record.project_dir
    item = QListWidgetItem(local_file.name)
    item.setData(Qt.UserRole, 0)
    app.project_reference_list.addItem(item)
    item.setSelected(True)

    messages = []
    monkeypatch.setattr(app, "_info", lambda msg: messages.append(("info", msg)))
    monkeypatch.setattr(app, "_error", lambda msg: messages.append(("error", msg)))

    app._refresh_selected_project_references(only_if_unchanged=False)

    assert local_file.read_text(encoding="utf-8") == "source changed"
    assert record.source_hash_at_copy
    assert record.local_hash_at_copy == record.source_hash_at_copy
    assert app._reference_status_for_record(record)["status"] == "up_to_date"
    assert messages[-1][0] == "info"
    assert "Updated 1 reference file(s)." in messages[-1][1]


def test_refresh_selected_project_references_if_unchanged_skips_modified_local(app_env, monkeypatch):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.write_text("source changed", encoding="utf-8")
    local_file.write_text("local changed", encoding="utf-8")

    app.records = [record]
    app.current_project_dir = record.project_dir
    item = QListWidgetItem(local_file.name)
    item.setData(Qt.UserRole, 0)
    app.project_reference_list.addItem(item)
    item.setSelected(True)

    messages = []
    monkeypatch.setattr(app, "_info", lambda msg: messages.append(("info", msg)))
    monkeypatch.setattr(app, "_error", lambda msg: messages.append(("error", msg)))

    app._refresh_selected_project_references(only_if_unchanged=True)

    assert local_file.read_text(encoding="utf-8") == "local changed"
    assert app._reference_status_for_record(record)["status"] == "both_changed_conflict"
    assert messages[-1][0] == "info"
    assert "Skipped 1 reference file(s)." in messages[-1][1]


def test_refresh_selected_project_references_allows_untracked_direct_refresh(app_env, monkeypatch):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])
    source_file.write_text("fresh source", encoding="utf-8")

    app.records = [record]
    app.current_project_dir = record.project_dir
    item = QListWidgetItem(local_file.name)
    item.setData(Qt.UserRole, 0)
    app.project_reference_list.addItem(item)
    item.setSelected(True)

    monkeypatch.setattr(app, "_info", lambda _msg: None)
    monkeypatch.setattr(app, "_error", lambda _msg: None)

    app._refresh_selected_project_references(only_if_unchanged=False)

    assert local_file.read_text(encoding="utf-8") == "fresh source"
    assert record.source_hash_at_copy
    assert record.last_refreshed_at
    assert app._reference_status_for_record(record)["status"] == "up_to_date"


def test_check_selected_references_status_from_active_tab_shows_selected_rows(app_env, monkeypatch):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"])

    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    app.records = [record]
    app.current_project_dir = record.project_dir
    app.favorites_tabs.setCurrentIndex(3)

    item = QListWidgetItem(local_file.name)
    item.setData(Qt.UserRole, 0)
    app.project_reference_list.addItem(item)
    item.setSelected(True)

    captured = {}
    monkeypatch.setattr(
        app,
        "_show_reference_status_dialog",
        lambda rows, title: captured.update({"rows": rows, "title": title}),
    )

    app._check_selected_references_status_from_active_tab()

    assert captured["title"] == "Reference Status"
    assert len(captured["rows"]) == 1
    assert captured["rows"][0]["record_id"] == record.id
    assert captured["rows"][0]["status"]["status"] == "up_to_date"


def test_apply_reference_action_to_remaining_updates_expected_rows(app_env):
    app = app_env["app"]
    plan_rows = [
        {"status": {"status": "source_changed_safe"}, "action": "replace"},
        {"status": {"status": "both_changed_conflict"}, "action": "skip"},
        {"status": {"status": "source_changed_safe"}, "action": "replace"},
    ]

    app._apply_reference_action_to_remaining(plan_rows, 1, "keep", same_status_only=False)
    assert [row["action"] for row in plan_rows] == ["replace", "keep", "keep"]

    plan_rows = [
        {"status": {"status": "source_changed_safe"}, "action": "replace"},
        {"status": {"status": "both_changed_conflict"}, "action": "skip"},
        {"status": {"status": "both_changed_conflict"}, "action": "skip"},
        {"status": {"status": "source_changed_safe"}, "action": "replace"},
    ]
    app._apply_reference_action_to_remaining(plan_rows, 1, "keep", same_status_only=True)
    assert [row["action"] for row in plan_rows] == ["replace", "keep", "keep", "replace"]


def test_execute_reference_update_plan_respects_actions_and_updates_records(app_env):
    app = app_env["app"]
    record_a, source_a, local_a = _build_reference_record(app_env["tmp"] / "update-a")
    record_b, source_b, local_b = _build_reference_record(app_env["tmp"] / "update-b")
    record_c, source_c, local_c = _build_reference_record(app_env["tmp"] / "update-c")

    app._apply_reference_copy_baseline(
        record_a,
        source_path=source_a,
        local_path=local_a,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    app._apply_reference_copy_baseline(
        record_b,
        source_path=source_b,
        local_path=local_b,
        copied_at="2026-04-08T12:31:00-04:00",
    )
    app._apply_reference_copy_baseline(
        record_c,
        source_path=source_c,
        local_path=local_c,
        copied_at="2026-04-08T12:32:00-04:00",
    )

    source_a.write_text("updated source", encoding="utf-8")
    source_c.unlink()
    app.records = [record_a, record_b, record_c]

    plan_rows = [
        {"record": record_a, "action": "replace"},
        {"record": record_b, "action": "keep"},
        {"record": record_c, "action": "replace"},
    ]

    summary = app._execute_reference_update_plan(plan_rows)

    assert summary["updated"] == 1
    assert summary["kept"] == 1
    assert summary["skipped"] == 0
    assert len(summary["failed"]) == 1
    assert local_a.read_text(encoding="utf-8") == "updated source"
    assert local_b.read_text(encoding="utf-8") == "baseline"


def test_update_all_references_from_active_tab_dispatches(app_env, monkeypatch):
    app = app_env["app"]
    app.favorites_tabs.setCurrentIndex(3)

    called = []
    monkeypatch.setattr(app, "_update_all_references", lambda: called.append("update_all"))

    app._update_all_references_from_active_tab()

    assert called == ["update_all"]


def test_update_all_references_executes_dialog_plan(app_env, monkeypatch):
    app = app_env["app"]
    record, source_file, local_file = _build_reference_record(app_env["tmp"] / "dialog")
    app._apply_reference_copy_baseline(
        record,
        source_path=source_file,
        local_path=local_file,
        copied_at="2026-04-08T12:30:00-04:00",
    )
    source_file.write_text("dialog source updated", encoding="utf-8")
    app.records = [record]
    app.current_project_dir = record.project_dir

    monkeypatch.setattr(
        app,
        "_show_update_all_references_dialog",
        lambda plan_rows: plan_rows[0].__setitem__("action", "replace") or True,
    )

    messages = []
    monkeypatch.setattr(app, "_info", lambda msg: messages.append(("info", msg)))
    monkeypatch.setattr(app, "_error", lambda msg: messages.append(("error", msg)))

    app._update_all_references()

    assert local_file.read_text(encoding="utf-8") == "dialog source updated"
    assert messages[-1][0] == "info"
    assert "Updated 1 reference file(s)." in messages[-1][1]

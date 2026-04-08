import json
from pathlib import Path

from app import CheckoutRecord


def test_debug_event_writes_line_when_enabled(app_env):
    # Debug events should be written only when the debug toggle is enabled.
    app = app_env["app"]
    debug_log = app_env["paths"]["debug_log"]

    app.debug_enabled_checkbox.setChecked(True)
    app._debug_event("unit_test_event", value=123)

    lines = debug_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    payload = json.loads(lines[-1])
    assert payload["event"] == "unit_test_event"
    assert payload["data"]["value"] == 123


def test_debug_timed_records_duration(app_env):
    # Timed debug helper should emit a duration for measured blocks.
    app = app_env["app"]
    debug_log = app_env["paths"]["debug_log"]

    app.debug_enabled_checkbox.setChecked(True)
    with app._debug_timed("timed_block", marker="abc"):
        _ = sum(range(100))

    payloads = [json.loads(line) for line in debug_log.read_text(encoding="utf-8").splitlines()]
    timed_entries = [entry for entry in payloads if entry.get("event") == "timed_block"]
    assert timed_entries
    last = timed_entries[-1]
    assert "duration_ms" in last["data"]
    assert last["data"]["marker"] == "abc"


def test_record_move_to_folder_emits_debug_events(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]
    debug_log = app_env["paths"]["debug_log"]

    project_dir = tmp / "Projects" / "DebugMove"
    source_root = tmp / "src-debug-move"
    source_root.mkdir(parents=True)
    local_file = project_dir / "reference_copies" / "A.pdf"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="DebugMove",
        sources=[str(source_root)],
        logical_views={
            "project_reference": {
                "folders": [
                    {"id": "ref-folder-1", "name": "Issued", "parent_id": "", "sort_order": 0},
                ],
                "placements": [],
            }
        },
    )
    app.records = [
        CheckoutRecord(
            source_file=str(source_root / "A.pdf"),
            locked_source_file="",
            local_file=str(local_file),
            initials="JH",
            project_name="DebugMove",
            project_dir=str(project_dir),
            source_root=str(source_root),
            id="ref-debug-1",
            record_type="reference_copy",
        )
    ]
    app.debug_enabled_checkbox.setChecked(True)
    app._load_project_from_dir(project_dir)
    app.project_reference_list.item(1).setSelected(True)
    monkeypatch.setattr(app, "_choose_record_target_folder", lambda *args, **kwargs: "ref-folder-1")

    app._move_selected_record_items_to_folder(
        app.project_reference_list,
        "project_reference",
        "Move Reference Items To Folder",
        "Create a reference folder first.",
    )

    payloads = [json.loads(line) for line in debug_log.read_text(encoding="utf-8").splitlines()]
    requested = [entry for entry in payloads if entry.get("event") == "record_items_move_to_folder_requested"]
    saved = [entry for entry in payloads if entry.get("event") == "record_items_move_to_folder_saved"]
    assert requested
    assert saved
    assert requested[-1]["data"]["scope"] == "project_reference"
    assert saved[-1]["data"]["moved_record_ids"] == ["ref-debug-1"]

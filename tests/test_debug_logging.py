import json


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

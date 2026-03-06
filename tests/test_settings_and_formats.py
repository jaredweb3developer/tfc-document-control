import json


def test_settings_payload_contains_config_paths(app_env):
    # Settings payload should include schema metadata and all relocatable file paths.
    app = app_env["app"]
    payload = app._settings_payload()

    assert payload["schema_version"] == 1
    assert payload["tracked_projects_file"].endswith("projects.json")
    assert payload["filter_presets_file"].endswith("filter_presets.json")
    assert payload["records_file"].endswith("checkout_records.json")
    assert payload["debug_events_file"].endswith("debug_events.log")
    assert payload["debug_events_enabled"] is False


def test_load_records_supports_legacy_list_format(app_env):
    # Backward compatibility: older records files were plain JSON lists.
    app = app_env["app"]
    paths = app_env["paths"]

    legacy_records = [
        {
            "source_file": "A",
            "locked_source_file": "A-JH",
            "local_file": "L",
            "initials": "JH",
            "project_name": "P",
            "project_dir": "D",
            "source_root": "S",
            "checked_out_at": "",
        }
    ]
    paths["records"].parent.mkdir(parents=True, exist_ok=True)
    paths["records"].write_text(json.dumps(legacy_records), encoding="utf-8")

    app._load_records()
    assert len(app.records) == 1
    assert app.records[0].source_file == "A"


def test_load_records_supports_schema_dict_format(app_env):
    # Current format: wrapper object with schema/app metadata + "records" list.
    app = app_env["app"]
    paths = app_env["paths"]

    records_payload = {
        "schema_version": 1,
        "app_version": "0.0.4",
        "records": [
            {
                "source_file": "B",
                "locked_source_file": "B-JH",
                "local_file": "LB",
                "initials": "JH",
                "project_name": "P2",
                "project_dir": "D2",
                "source_root": "S2",
                "checked_out_at": "",
            }
        ],
    }
    paths["records"].parent.mkdir(parents=True, exist_ok=True)
    paths["records"].write_text(json.dumps(records_payload), encoding="utf-8")

    app._load_records()
    assert len(app.records) == 1
    assert app.records[0].source_file == "B"

import json


def test_note_presets_persist_and_reload(app_env):
    # Preset notes and groups should round-trip through note_presets.json.
    app = app_env["app"]
    paths = app_env["paths"]

    app.note_presets_notes = [
        {
            "id": "pn1",
            "subject": "Template A",
            "body": "Body A",
            "auto_add_new_projects": True,
        }
    ]
    app.note_preset_groups = [
        {
            "id": "pg1",
            "name": "Startup Pack",
            "note_ids": ["pn1"],
            "auto_add_new_projects": False,
        }
    ]
    app._save_note_presets()
    payload = json.loads(paths["note_presets"].read_text(encoding="utf-8"))
    assert payload["notes"][0]["subject"] == "Template A"
    assert payload["groups"][0]["name"] == "Startup Pack"

    app.note_presets_notes = []
    app.note_preset_groups = []
    app._load_note_presets()
    assert len(app.note_presets_notes) == 1
    assert app.note_presets_notes[0]["id"] == "pn1"
    assert len(app.note_preset_groups) == 1
    assert app.note_preset_groups[0]["note_ids"] == ["pn1"]


def test_default_notes_from_presets_includes_auto_notes_and_auto_groups(app_env):
    # Auto-add notes and auto-add groups should both contribute to new project note defaults.
    app = app_env["app"]
    app.note_presets_notes = [
        {"id": "n1", "subject": "A", "body": "Body A", "auto_add_new_projects": True},
        {"id": "n2", "subject": "B", "body": "Body B", "auto_add_new_projects": False},
        {"id": "n3", "subject": "C", "body": "Body C", "auto_add_new_projects": False},
    ]
    app.note_preset_groups = [
        {
            "id": "g1",
            "name": "Launch",
            "note_ids": ["n2", "n3"],
            "auto_add_new_projects": True,
        }
    ]

    defaults = app._default_notes_from_presets()
    subjects = [note["subject"] for note in defaults]
    assert subjects == ["A", "B", "C"]
    assert all(note["id"] for note in defaults)


def test_add_preset_notes_to_current_project(app_env):
    # Preset notes can be inserted into the currently loaded project.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "PresetTarget"
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    app._write_project_config(project_dir, "PresetTarget", [str(source_dir)], notes=[])
    app._load_project_from_dir(project_dir)

    app.note_presets_notes = [
        {"id": "n1", "subject": "Preset 1", "body": "Body 1", "auto_add_new_projects": False},
        {"id": "n2", "subject": "Preset 2", "body": "Body 2", "auto_add_new_projects": False},
    ]
    app.note_preset_groups = []

    app._add_preset_notes_to_current_project(["n1", "n2"])
    notes = app._current_project_notes()
    assert [note["subject"] for note in notes] == ["Preset 1", "Preset 2"]

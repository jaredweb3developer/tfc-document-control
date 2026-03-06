from PySide6.QtCore import Qt


def test_source_file_context_actions_dispatch(app_env, monkeypatch):
    # Source-file context actions should route to the expected command handlers.
    app = app_env["app"]
    called = []

    monkeypatch.setattr(app, "_open_selected_source_files", lambda: called.append("open"))
    monkeypatch.setattr(app, "_checkout_selected", lambda: called.append("checkout"))
    monkeypatch.setattr(app, "_copy_selected_as_reference", lambda: called.append("reference"))
    monkeypatch.setattr(app, "_show_selected_file_history", lambda: called.append("history"))
    monkeypatch.setattr(app, "_add_selected_source_files_to_favorites", lambda: called.append("favorite"))
    monkeypatch.setattr(app, "_refresh_source_files", lambda: called.append("refresh"))

    for action_id in ["open", "checkout", "reference", "history", "favorite", "refresh"]:
        app._handle_source_file_context_action(action_id)

    assert called == ["open", "checkout", "reference", "history", "favorite", "refresh"]


def test_records_context_actions_dispatch(app_env, monkeypatch):
    # Checked-out/reference context actions should route to open/checkin/remove-ref handlers.
    app = app_env["app"]
    called = []

    monkeypatch.setattr(app, "_open_selected_record_files", lambda: called.append("open"))
    monkeypatch.setattr(app, "_checkin_selected", lambda: called.append("checkin"))
    monkeypatch.setattr(app, "_remove_selected_reference_records", lambda: called.append("remove_ref"))

    app._handle_records_context_action("open")
    app._handle_records_context_action("checkin")
    app._handle_records_context_action("remove_ref")

    assert called == ["open", "checkin", "remove_ref"]


def test_context_menu_policies_are_enabled(app_env):
    # Right-click menus should be enabled for key lists/tables in this feature.
    app = app_env["app"]

    assert app.files_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.tracked_projects_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.favorites_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.notes_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.source_roots_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.controlled_files_list.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.all_records_table.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.project_records_table.contextMenuPolicy() == Qt.CustomContextMenu
    assert app.reference_records_table.contextMenuPolicy() == Qt.CustomContextMenu

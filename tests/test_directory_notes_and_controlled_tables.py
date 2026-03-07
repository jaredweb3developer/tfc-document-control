from PySide6.QtCore import Qt


def test_refresh_controlled_files_populates_table(app_env):
    # Controlled files should render in the Directory > Controlled Files table.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "source"
    src.mkdir(parents=True)
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(src, "CHECK_OUT", "A.dwg")

    app.current_directory = src
    app._refresh_controlled_files()

    assert app.controlled_files_table.rowCount() == 1
    assert app.controlled_files_table.item(0, 0).text() == "A.dwg"
    assert app.controlled_files_table.item(0, 1).text() == "JWH"


def test_directory_notes_summary_groups_by_file(app_env):
    # Directory > File Notes summary should show per-file count and latest update.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "source-notes"
    src.mkdir(parents=True)
    app.current_directory = src
    app._write_directory_notes(
        src,
        [
            {
                "id": "n1",
                "file_name": "A.dwg",
                "parent_id": "",
                "subject": "First",
                "body": "Body1",
                "created_by_initials": "JWH",
                "created_by_name": "Jared Hodgkins",
                "created_at": "2026-03-07T10:00:00-05:00",
                "updated_at": "2026-03-07T10:00:00-05:00",
            },
            {
                "id": "n2",
                "file_name": "A.dwg",
                "parent_id": "n1",
                "subject": "Reply",
                "body": "Body2",
                "created_by_initials": "AB",
                "created_by_name": "Alex Brown",
                "created_at": "2026-03-07T11:00:00-05:00",
                "updated_at": "2026-03-07T11:00:00-05:00",
            },
        ],
    )

    app._refresh_directory_notes_summary()
    assert app.directory_notes_table.rowCount() == 1
    assert app.directory_notes_table.item(0, 0).text() == "A.dwg"
    assert app.directory_notes_table.item(0, 1).text() == "2"


def test_open_notes_from_source_list_uses_original_file_name(app_env, monkeypatch):
    # Opening notes from source list should resolve to original file name (not locked -initials name).
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-open-notes"
    source_dir.mkdir(parents=True)
    app.current_directory = source_dir
    app.files_list.clear()
    item = app.files_list.addItem if False else None
    del item
    from PySide6.QtWidgets import QListWidgetItem
    list_item = QListWidgetItem("A-JWH.dwg")
    list_item.setData(Qt.UserRole, str(source_dir / "A-JWH.dwg"))
    list_item.setData(Qt.UserRole + 1, "A.dwg")
    app.files_list.addItem(list_item)
    app.files_list.setCurrentItem(list_item)
    list_item.setSelected(True)

    opened = {"file_name": ""}
    monkeypatch.setattr(app, "_open_file_notes_window", lambda name: opened.__setitem__("file_name", name))
    app._open_notes_for_selected_source_file()
    assert opened["file_name"] == "A.dwg"

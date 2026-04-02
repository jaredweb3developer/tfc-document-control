from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox


def test_refresh_controlled_files_populates_table(app_env):
    # Controlled files should render in the Directory > Controlled Files table.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "source"
    src.mkdir(parents=True)
    (src / "A-JWH.dwg").write_text("x", encoding="utf-8")
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
    (src / "A.dwg").write_text("x", encoding="utf-8")
    app.current_directory = src
    app._ensure_source_index(src)
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


def test_directory_notes_parent_id_false_is_normalized(app_env):
    # Historical bad parent_id values should normalize to root notes.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "source-notes-normalize"
    src.mkdir(parents=True)
    notes_file = src / ".doc_file_notes.json"
    notes_file.write_text(
        """
{
  "entries": [
    {
      "id": "n1",
      "file_name": "A.dwg",
      "parent_id": false,
      "subject": "Root",
      "body": "x",
      "created_by_initials": "JWH",
      "created_by_name": "Jared",
      "created_at": "2026-03-07T10:00:00-05:00",
      "updated_at": "2026-03-07T10:00:00-05:00"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    rows = app._read_directory_notes(src)
    assert len(rows) == 1
    assert rows[0]["parent_id"] == ""


def test_open_notes_from_source_list_uses_original_file_name(app_env, monkeypatch):
    # Opening notes from source list should resolve through stable file_id, not the locked visible name.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-open-notes"
    source_dir.mkdir(parents=True)
    locked_file = source_dir / "A-JWH.dwg"
    locked_file.write_text("x", encoding="utf-8")
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "CHECK_OUT", "A.dwg")
    app.current_directory = source_dir
    app._refresh_source_files()
    list_item = app.files_list.item(0)
    app.files_list.setCurrentItem(list_item)
    list_item.setSelected(True)

    opened = {"file_name": ""}
    monkeypatch.setattr(app, "_open_file_notes_window", lambda name: opened.__setitem__("file_name", name))
    app._open_notes_for_selected_source_file()
    assert str(opened["file_name"]).startswith("f_")


def test_rename_selected_source_file_updates_history_and_notes(app_env, monkeypatch):
    # Rename should preserve file identity, append a rename event, and update note display names.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-rename"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "A.dwg"
    source_file.write_text("x", encoding="utf-8")
    app.current_directory = source_dir
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "ADD_FILE", "A.dwg")
    app._write_directory_notes(
        source_dir,
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
            }
        ],
    )
    app._refresh_source_files()
    list_item = app.files_list.item(0)
    app.files_list.setCurrentItem(list_item)
    list_item.setSelected(True)
    original_file_id = str(list_item.data(Qt.UserRole + 2))

    infos = []
    monkeypatch.setattr(
        "document_control.mixins.records.QInputDialog.getText",
        lambda *args, **kwargs: ("B.dwg", True),
    )
    monkeypatch.setattr(app, "_info", lambda message: infos.append(message))

    app._rename_selected_source_file()

    renamed = source_dir / "B.dwg"
    assert not source_file.exists()
    assert renamed.exists()
    rows = app._read_history_rows(source_dir)
    assert [row["file_name"] for row in rows] == ["A.dwg", "B.dwg"]
    assert [row["action"] for row in rows] == ["ADD_FILE", "RENAME"]
    assert rows[-1]["previous_file_name"] == "A.dwg"
    assert rows[-1]["file_id"] == original_file_id
    notes = app._read_directory_notes(source_dir)
    assert notes[0]["file_name"] == "B.dwg"
    assert notes[0]["file_id"] == original_file_id
    assert infos == ["Renamed 'A.dwg' to 'B.dwg'."]


def test_rename_selected_source_file_rejects_checked_out_file(app_env, monkeypatch):
    # Checked-out files stay rename-blocked until path-based record/revision identity is replaced.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-rename-blocked"
    source_dir.mkdir(parents=True)
    locked_file = source_dir / "A-JWH.dwg"
    locked_file.write_text("x", encoding="utf-8")
    app.current_directory = source_dir
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "CHECK_OUT", "A.dwg")
    app._refresh_source_files()
    list_item = app.files_list.item(0)
    app.files_list.setCurrentItem(list_item)
    list_item.setSelected(True)

    errors = []
    monkeypatch.setattr(app, "_error", lambda message: errors.append(message))

    app._rename_selected_source_file()

    assert locked_file.exists()
    assert errors == ["Checked-out files cannot be renamed in the current version."]


def test_delete_selected_source_files_removes_files_and_notes_and_appends_history(app_env, monkeypatch):
    # Delete should retire file identities, keep note history, and append delete history rows.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-delete"
    source_dir.mkdir(parents=True)
    file_a = source_dir / "A.dwg"
    file_b = source_dir / "B.dwg"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")
    app.current_directory = source_dir
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "ADD_FILE", "A.dwg")
    app._append_history(source_dir, "ADD_FILE", "B.dwg")
    app._write_directory_notes(
        source_dir,
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
                "file_name": "B.dwg",
                "parent_id": "",
                "subject": "Second",
                "body": "Body2",
                "created_by_initials": "JWH",
                "created_by_name": "Jared Hodgkins",
                "created_at": "2026-03-07T11:00:00-05:00",
                "updated_at": "2026-03-07T11:00:00-05:00",
            },
        ],
    )
    app._refresh_source_files()
    file_ids = []
    for row in range(app.files_list.count()):
        list_item = app.files_list.item(row)
        file_ids.append(str(list_item.data(Qt.UserRole + 2)))
        list_item.setSelected(True)

    infos = []
    monkeypatch.setattr(
        "document_control.mixins.records.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    monkeypatch.setattr(app, "_info", lambda message: infos.append(message))

    app._delete_selected_source_files()

    assert not file_a.exists()
    assert not file_b.exists()
    rows = app._read_history_rows(source_dir)
    assert [row["action"] for row in rows] == ["ADD_FILE", "ADD_FILE", "DELETE_FILE", "DELETE_FILE"]
    assert [row["file_name"] for row in rows] == ["A.dwg", "B.dwg", "A.dwg", "B.dwg"]
    notes = app._read_directory_notes(source_dir)
    assert [note["file_id"] for note in notes] == file_ids
    assert infos == ["Deleted 2 source file(s)."]


def test_delete_selected_source_files_rejects_checked_out_file(app_env, monkeypatch):
    # Checked-out files stay delete-blocked until path-based record/revision identity is replaced.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source-delete-blocked"
    source_dir.mkdir(parents=True)
    locked_file = source_dir / "A-JWH.dwg"
    locked_file.write_text("x", encoding="utf-8")
    app.current_directory = source_dir
    app.initials_edit.setText("JWH")
    app.full_name_edit.setText("Jared Hodgkins")
    app._append_history(source_dir, "CHECK_OUT", "A.dwg")
    app._refresh_source_files()
    list_item = app.files_list.item(0)
    app.files_list.setCurrentItem(list_item)
    list_item.setSelected(True)

    errors = []
    monkeypatch.setattr(app, "_error", lambda message: errors.append(message))

    app._delete_selected_source_files()

    assert locked_file.exists()
    assert errors == ["Checked-out files cannot be deleted in the current version:\nA-JWH.dwg"]

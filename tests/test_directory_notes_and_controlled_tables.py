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

from pathlib import Path
import stat

from app import CheckoutRecord


def test_copy_selected_as_reference_creates_local_copy_without_locking_source(app_env, monkeypatch):
    # Reference copy should not rename/lock source file and should create a tracked reference record.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_root = tmp / "source-root"
    source_root.mkdir(parents=True)
    source_file = source_root / "drawing-a.dwg"
    source_file.write_text("dwg-data", encoding="utf-8")

    project_dir = tmp / "Projects" / "RefProject"
    app._write_project_config(
        project_dir,
        "RefProject",
        [str(source_root)],
        selected_source=str(source_root),
    )

    app.initials_edit.setText("JH")
    app._load_project_from_dir(project_dir)
    app._refresh_source_files()

    # Select the source file in the Files list.
    for row in range(app.files_list.count()):
        item = app.files_list.item(row)
        if item.text() == "drawing-a.dwg":
            item.setSelected(True)
            break

    monkeypatch.setattr(
        app,
        "_choose_project_target",
        lambda **_kwargs: ("current", None),
    )
    app._copy_selected_as_reference()

    assert source_file.exists()
    assert not (source_root / "drawing-a-JH.dwg").exists()

    reference_records = [record for record in app.records if record.record_type == "reference_copy"]
    assert len(reference_records) == 1
    ref_record = reference_records[0]
    assert ref_record.source_file == str(source_file)
    assert ref_record.locked_source_file == ""
    assert Path(ref_record.local_file).exists()
    assert app.reference_records_table.rowCount() == 1


def test_checkin_selected_rejects_reference_copy_rows(app_env, monkeypatch):
    # Check-in should reject pure reference selections without opening check-in mode flow.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "RefOnly"
    project_dir.mkdir(parents=True)
    ref_local = tmp / "Projects" / "RefOnly" / "reference_copies" / "x.dwg"
    ref_local.parent.mkdir(parents=True, exist_ok=True)
    ref_local.write_text("ref", encoding="utf-8")

    app.initials_edit.setText("JH")
    app.current_project_dir = str(project_dir)
    app.records = [
        CheckoutRecord(
            source_file=str(tmp / "src" / "x.dwg"),
            locked_source_file="",
            local_file=str(ref_local),
            initials="JH",
            project_name="RefOnly",
            project_dir=str(project_dir),
            source_root=str(tmp / "src"),
            checked_out_at="",
            record_type="reference_copy",
        )
    ]
    app._render_records_tables()
    # The records tabs now wrap each table in a tab page, so select the reference tab by index.
    app.records_tabs.setCurrentIndex(2)
    app.reference_records_table.selectRow(0)

    captured = {"msg": ""}
    monkeypatch.setattr(app, "_error", lambda msg: captured.__setitem__("msg", msg))

    app._checkin_selected()

    assert "Reference copies cannot be checked in" in captured["msg"]


def test_remove_reference_copy_deletes_local_file_and_clears_read_only(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "RefDelete"
    ref_local = project_dir / "reference_copies" / "src-1" / "nested" / "x.dwg"
    ref_local.parent.mkdir(parents=True, exist_ok=True)
    ref_local.write_text("ref", encoding="utf-8")
    ref_local.chmod(ref_local.stat().st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)

    app.records = [
        CheckoutRecord(
            source_file=str(tmp / "src" / "x.dwg"),
            locked_source_file="",
            local_file=str(ref_local),
            initials="JH",
            project_name="RefDelete",
            project_dir=str(project_dir),
            source_root=str(tmp / "src"),
            checked_out_at="",
            record_type="reference_copy",
        )
    ]

    errors = app._remove_record_indexes([0])

    assert errors == []
    assert app.records == []
    assert not ref_local.exists()
    assert not (project_dir / "reference_copies" / "src-1" / "nested").exists()

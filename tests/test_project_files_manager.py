from app import CheckoutRecord


def test_project_file_manager_rows_include_revision_counts(app_env):
    # Checked-out rows should show local revision count; reference rows should show zero.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "PFM"
    project_dir.mkdir(parents=True)
    source_dir = tmp / "src"
    source_dir.mkdir(parents=True)

    checked_local = project_dir / "checked_out" / "A.dwg"
    checked_local.parent.mkdir(parents=True)
    checked_local.write_text("A", encoding="utf-8")
    ref_local = project_dir / "reference_copies" / "A.pdf"
    ref_local.parent.mkdir(parents=True)
    ref_local.write_text("R", encoding="utf-8")

    checked_record = CheckoutRecord(
        source_file=str(source_dir / "A.dwg"),
        locked_source_file=str(source_dir / "A-JWH.dwg"),
        local_file=str(checked_local),
        initials="JWH",
        project_name="PFM",
        project_dir=str(project_dir),
        source_root=str(source_dir),
        checked_out_at="2026-03-06T12:00:00-05:00",
        record_type="checked_out",
    )
    reference_record = CheckoutRecord(
        source_file=str(source_dir / "A.pdf"),
        locked_source_file="",
        local_file=str(ref_local),
        initials="JWH",
        project_name="PFM",
        project_dir=str(project_dir),
        source_root=str(source_dir),
        checked_out_at="2026-03-06T12:00:00-05:00",
        record_type="reference_copy",
    )
    app.records = [checked_record, reference_record]

    app._create_revision_snapshot_for_record(checked_record, note="baseline")
    rows = app._project_file_manager_rows(project_dir, "all")
    by_type = {row["record_type"]: row for row in rows}
    assert by_type["checked_out"]["revisions"] == 1
    assert by_type["reference_copy"]["revisions"] == 0


def test_project_file_manager_search_filters_rows(app_env):
    # Search term should match file name/path/type text and filter rows accordingly.
    app = app_env["app"]
    rows = [
        {"file_name": "HeatTrace-01.dwg", "local_file": "/x/a", "source_file": "/src/a", "record_type": "checked_out"},
        {"file_name": "spec.pdf", "local_file": "/x/b", "source_file": "/src/b", "record_type": "reference_copy"},
    ]
    filtered = app._apply_project_file_search(rows, "heattrace")
    assert len(filtered) == 1
    assert filtered[0]["file_name"] == "HeatTrace-01.dwg"


def test_project_file_manager_rows_include_untracked_project_files(app_env):
    # All/Untracked views should include local project files that are not tied to a record.
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "PFM-Untracked"
    project_dir.mkdir(parents=True)
    stray_file = project_dir / "checked_out" / "orphan.tmp"
    stray_file.parent.mkdir(parents=True)
    stray_file.write_text("orphan", encoding="utf-8")

    all_rows = app._project_file_manager_rows(project_dir, "all")
    untracked_rows = app._project_file_manager_rows(project_dir, "untracked")
    assert any(row["record_type"] == "untracked" for row in all_rows)
    assert any(str(row.get("local_file", "")) == str(stray_file) for row in untracked_rows)

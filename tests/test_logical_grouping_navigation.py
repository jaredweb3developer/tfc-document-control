from PySide6.QtWidgets import QInputDialog, QMessageBox
from app import CheckoutRecord


def test_project_favorites_render_folder_and_navigate(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavFolders"
    favorite = tmp / "A.pdf"
    favorite.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="FavFolders",
        sources=[],
        favorites=[str(favorite)],
        logical_views={
            "project_favorites": {
                "folders": [
                    {"id": "folder-1", "name": "Submittals", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": str(favorite), "parent_folder_id": "folder-1", "sort_order": 0},
                ],
            }
        },
    )

    app._load_project_from_dir(project_dir)

    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "[Folder] Submittals"

    app._open_favorite_item(app.favorites_list.item(0))

    assert app.project_favorites_folder_label.text() == "Favorites Folder: Root / Submittals"
    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "A.pdf"


def test_create_project_favorites_folder_and_move_item_into_it(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavCreate"
    favorite = tmp / "B.pdf"
    favorite.write_text("b", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="FavCreate",
        sources=[],
        favorites=[str(favorite)],
    )
    app._load_project_from_dir(project_dir)

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Drawings", True))
    app._create_project_favorites_folder()

    assert app.favorites_list.count() == 2
    assert app.favorites_list.item(0).text() == "[Folder] Drawings"

    app.favorites_list.setCurrentRow(1)
    app.favorites_list.item(1).setSelected(True)
    monkeypatch.setattr(app, "_choose_project_favorites_target_folder", lambda: "fld_target")
    logical_view = app._project_logical_view("project_favorites")
    logical_view["folders"] = [
        {"id": "fld_target", "name": "Drawings", "parent_id": "", "sort_order": 0},
    ]
    app._save_project_logical_view("project_favorites", logical_view)
    app._move_selected_favorites_to_folder()

    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "[Folder] Drawings"

    app._open_favorite_item(app.favorites_list.item(0))
    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "B.pdf"


def test_delete_project_favorites_folder_returns_items_to_root(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavDelete"
    favorite = tmp / "C.pdf"
    favorite.write_text("c", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="FavDelete",
        sources=[],
        favorites=[str(favorite)],
        logical_views={
            "project_favorites": {
                "folders": [
                    {"id": "folder-1", "name": "Archive", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": str(favorite), "parent_folder_id": "folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app._load_project_from_dir(project_dir)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    app._delete_project_favorites_folder("folder-1")

    assert app.project_favorites_folder_label.text() == "Favorites Folder: Root"
    assert app.favorites_list.count() == 1
    assert app.favorites_list.item(0).text() == "C.pdf"

    cfg = app._read_project_config(project_dir)
    logical_views = cfg.get("logical_views", {})
    assert logical_views["project_favorites"]["folders"] == []
    assert logical_views["project_favorites"]["placements"] == []


def test_project_notes_render_folder_and_navigate(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteFolders"
    note = {
        "id": "note-1",
        "subject": "Coordination",
        "body": "Review pending",
        "created_at": "2026-04-08T09:00:00",
        "updated_at": "2026-04-08T09:00:00",
    }

    app._write_project_config(
        project_dir=project_dir,
        name="NoteFolders",
        sources=[],
        notes=[note],
        logical_views={
            "project_notes": {
                "folders": [
                    {"id": "note-folder-1", "name": "Meetings", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "note-1", "parent_folder_id": "note-folder-1", "sort_order": 0},
                ],
            }
        },
    )

    app._load_project_from_dir(project_dir)

    assert app.notes_list.count() == 1
    assert app.notes_list.item(0).text() == "[Folder] Meetings"

    app._edit_note_item(app.notes_list.item(0))

    assert app.project_notes_folder_label.text() == "Notes Folder: Root / Meetings"
    assert app.notes_list.count() == 1
    assert app.notes_list.item(0).text() == "Coordination"


def test_create_project_note_inside_current_folder(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteCreate"
    app._write_project_config(
        project_dir=project_dir,
        name="NoteCreate",
        sources=[],
        logical_views={
            "project_notes": {
                "folders": [
                    {"id": "note-folder-1", "name": "RFIs", "parent_id": "", "sort_order": 0},
                ],
                "placements": [],
            }
        },
    )
    app._load_project_from_dir(project_dir)
    app._set_current_logical_folder_id("project_notes", "note-folder-1")
    app._refresh_notes_list(app._current_project_notes())

    monkeypatch.setattr(
        app,
        "_show_note_dialog",
        lambda note=None: {
            "id": "note-created",
            "subject": "Open Question",
            "body": "Need response",
            "created_at": "2026-04-08T10:00:00",
            "updated_at": "2026-04-08T10:00:00",
        },
    )

    app._create_note()

    assert app.notes_list.count() == 1
    assert app.notes_list.item(0).text() == "Open Question"
    cfg = app._read_project_config(project_dir)
    logical_views = cfg.get("logical_views", {})
    assert logical_views["project_notes"]["placements"][0]["item_key"] == "note-created"
    assert logical_views["project_notes"]["placements"][0]["parent_folder_id"] == "note-folder-1"


def test_delete_project_notes_folder_returns_notes_to_root(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteDelete"
    note = {
        "id": "note-2",
        "subject": "Archive Note",
        "body": "Retain",
        "created_at": "2026-04-08T11:00:00",
        "updated_at": "2026-04-08T11:00:00",
    }

    app._write_project_config(
        project_dir=project_dir,
        name="NoteDelete",
        sources=[],
        notes=[note],
        logical_views={
            "project_notes": {
                "folders": [
                    {"id": "note-folder-2", "name": "Archive", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "note-2", "parent_folder_id": "note-folder-2", "sort_order": 0},
                ],
            }
        },
    )
    app._load_project_from_dir(project_dir)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    app._delete_project_notes_folder("note-folder-2")

    assert app.project_notes_folder_label.text() == "Notes Folder: Root"
    assert app.notes_list.count() == 1
    assert app.notes_list.item(0).text() == "Archive Note"
    cfg = app._read_project_config(project_dir)
    logical_views = cfg.get("logical_views", {})
    assert logical_views["project_notes"]["folders"] == []
    assert logical_views["project_notes"]["placements"] == []


def test_global_favorites_render_folder_and_navigate(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    favorite = tmp / "global-a.pdf"
    favorite.write_text("a", encoding="utf-8")
    app.global_favorites = [str(favorite)]
    app.global_favorites_logical_views = {
        "global_favorites": {
            "folders": [
                {"id": "global-folder-1", "name": "Vendors", "parent_id": "", "sort_order": 0},
            ],
            "placements": [
                {"item_key": str(favorite), "parent_folder_id": "global-folder-1", "sort_order": 0},
            ],
        }
    }

    app._refresh_global_favorites_list()

    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "[Folder] Vendors"

    app._open_global_favorite_item(app.global_favorites_list.item(0))

    assert app.global_favorites_folder_label.text() == "Global Favorites Folder: Root / Vendors"
    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "global-a.pdf"


def test_create_global_favorites_folder_and_move_item_into_it(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    favorite = tmp / "global-b.pdf"
    favorite.write_text("b", encoding="utf-8")
    app.global_favorites = [str(favorite)]
    app.global_favorites_logical_views = {"global_favorites": {"folders": [], "placements": []}}
    app._refresh_global_favorites_list()

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Shared", True))
    app._create_global_favorites_folder()

    assert app.global_favorites_list.count() == 2
    assert app.global_favorites_list.item(0).text() == "[Folder] Shared"

    app.global_favorites_list.setCurrentRow(1)
    app.global_favorites_list.item(1).setSelected(True)
    monkeypatch.setattr(app, "_choose_global_favorites_target_folder", lambda: "global-folder-target")
    logical_view = app._global_favorites_logical_view()
    logical_view["folders"] = [
        {"id": "global-folder-target", "name": "Shared", "parent_id": "", "sort_order": 0},
    ]
    app._save_global_favorites_logical_view(logical_view)
    app._move_selected_global_favorites_to_folder()

    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "[Folder] Shared"

    app._open_global_favorite_item(app.global_favorites_list.item(0))
    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "global-b.pdf"


def test_delete_global_favorites_folder_returns_items_to_root(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    favorite = tmp / "global-c.pdf"
    favorite.write_text("c", encoding="utf-8")
    app.global_favorites = [str(favorite)]
    app.global_favorites_logical_views = {
        "global_favorites": {
            "folders": [
                {"id": "global-folder-2", "name": "Archive", "parent_id": "", "sort_order": 0},
            ],
            "placements": [
                {"item_key": str(favorite), "parent_folder_id": "global-folder-2", "sort_order": 0},
            ],
        }
    }
    app._refresh_global_favorites_list()

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    app._delete_global_favorites_folder("global-folder-2")

    assert app.global_favorites_folder_label.text() == "Global Favorites Folder: Root"
    assert app.global_favorites_list.count() == 1
    assert app.global_favorites_list.item(0).text() == "global-c.pdf"
    assert app.global_favorites_logical_views["global_favorites"]["folders"] == []
    assert app.global_favorites_logical_views["global_favorites"]["placements"] == []


def test_project_checked_out_render_folder_and_navigate(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "CheckedFolders"
    source_root = tmp / "src-checked"
    source_root.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "A.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="CheckedFolders",
        sources=[str(source_root)],
        logical_views={
            "project_checked_out": {
                "folders": [
                    {"id": "checked-folder-1", "name": "Active", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "rec-1", "parent_folder_id": "checked-folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app.records = [
        CheckoutRecord(
            source_file=str(source_root / "A.dwg"),
            locked_source_file=str(source_root / "A-JH.dwg"),
            local_file=str(local_file),
            initials="JH",
            project_name="CheckedFolders",
            project_dir=str(project_dir),
            source_root=str(source_root),
            id="rec-1",
            record_type="checked_out",
        )
    ]
    app._load_project_from_dir(project_dir)

    assert app.project_checked_out_list.count() == 1
    assert app.project_checked_out_list.item(0).text() == "[Folder] Active"

    app._open_project_local_checked_out_item(app.project_checked_out_list.item(0))

    assert app.project_checked_out_folder_label.text() == "Checked Out Folder: Root / Active"
    assert app.project_checked_out_list.count() == 1
    assert app.project_checked_out_list.item(0).text() == "A.dwg"


def test_project_reference_render_folder_and_navigate(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "ReferenceFolders"
    source_root = tmp / "src-reference"
    source_root.mkdir(parents=True)
    local_file = project_dir / "reference_copies" / "A.pdf"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="ReferenceFolders",
        sources=[str(source_root)],
        logical_views={
            "project_reference": {
                "folders": [
                    {"id": "reference-folder-1", "name": "Issued", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "rec-ref-1", "parent_folder_id": "reference-folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app.records = [
        CheckoutRecord(
            source_file=str(source_root / "A.pdf"),
            locked_source_file="",
            local_file=str(local_file),
            initials="JH",
            project_name="ReferenceFolders",
            project_dir=str(project_dir),
            source_root=str(source_root),
            id="rec-ref-1",
            record_type="reference_copy",
        )
    ]
    app._load_project_from_dir(project_dir)

    assert app.project_reference_list.count() == 1
    assert app.project_reference_list.item(0).text() == "[Folder] Issued"

    app._open_project_local_reference_item(app.project_reference_list.item(0))

    assert app.project_reference_folder_label.text() == "Reference Folder: Root / Issued"
    assert app.project_reference_list.count() == 1
    assert app.project_reference_list.item(0).text() == "A.pdf"


def test_record_logical_placements_are_pruned_when_record_missing(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "RecordCleanup"
    source_root = tmp / "src-cleanup"
    source_root.mkdir(parents=True)

    app._write_project_config(
        project_dir=project_dir,
        name="RecordCleanup",
        sources=[str(source_root)],
        logical_views={
            "project_checked_out": {
                "folders": [],
                "placements": [
                    {"item_key": "missing-record", "parent_folder_id": "", "sort_order": 0},
                ],
            }
        },
    )
    app.records = []
    app._load_project_from_dir(project_dir)
    app._refresh_project_local_files_lists()

    cfg = app._read_project_config(project_dir)
    logical_views = cfg.get("logical_views", {})
    assert logical_views["project_checked_out"]["placements"] == []


def test_project_favorites_root_search_includes_nested_items(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "FavSearch"
    favorite = tmp / "nested-favorite.pdf"
    favorite.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="FavSearch",
        sources=[],
        favorites=[str(favorite)],
        logical_views={
            "project_favorites": {
                "folders": [
                    {"id": "search-folder-1", "name": "Nested", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": str(favorite), "parent_folder_id": "search-folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app._load_project_from_dir(project_dir)
    app.project_favorites_search_edit.setText("nested-favorite")
    app._refresh_favorites_list(app._current_project_favorites())

    texts = [app.favorites_list.item(row).text() for row in range(app.favorites_list.count())]
    assert "nested-favorite.pdf" in texts


def test_project_notes_root_search_includes_nested_items(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "NoteSearch"
    note = {
        "id": "search-note-1",
        "subject": "Nested Discussion",
        "body": "Body",
        "created_at": "2026-04-08T12:00:00",
        "updated_at": "2026-04-08T12:00:00",
    }

    app._write_project_config(
        project_dir=project_dir,
        name="NoteSearch",
        sources=[],
        notes=[note],
        logical_views={
            "project_notes": {
                "folders": [
                    {"id": "note-search-folder-1", "name": "Meetings", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "search-note-1", "parent_folder_id": "note-search-folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app._load_project_from_dir(project_dir)
    app.project_notes_search_edit.setText("nested discussion")
    app._refresh_notes_list(app._current_project_notes())

    texts = [app.notes_list.item(row).text() for row in range(app.notes_list.count())]
    assert "Nested Discussion" in texts


def test_checked_out_root_search_includes_nested_items(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "CheckedSearch"
    source_root = tmp / "src-checked-search"
    source_root.mkdir(parents=True)
    local_file = project_dir / "checked_out" / "NestedSearch.dwg"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("a", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="CheckedSearch",
        sources=[str(source_root)],
        logical_views={
            "project_checked_out": {
                "folders": [
                    {"id": "checked-search-folder-1", "name": "Active", "parent_id": "", "sort_order": 0},
                ],
                "placements": [
                    {"item_key": "rec-search-1", "parent_folder_id": "checked-search-folder-1", "sort_order": 0},
                ],
            }
        },
    )
    app.records = [
        CheckoutRecord(
            source_file=str(source_root / "NestedSearch.dwg"),
            locked_source_file=str(source_root / "NestedSearch-JH.dwg"),
            local_file=str(local_file),
            initials="JH",
            project_name="CheckedSearch",
            project_dir=str(project_dir),
            source_root=str(source_root),
            id="rec-search-1",
            record_type="checked_out",
        )
    ]
    app._load_project_from_dir(project_dir)
    app.project_checked_out_search_edit.setText("nestedsearch")
    app._refresh_project_local_files_lists()

    texts = [app.project_checked_out_list.item(row).text() for row in range(app.project_checked_out_list.count())]
    assert "NestedSearch.dwg" in texts


def test_search_ignores_current_folder_and_searches_all_logical_folders(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    project_dir = tmp / "Projects" / "GlobalSearchScope"
    favorite_a = tmp / "alpha.pdf"
    favorite_b = tmp / "beta.pdf"
    favorite_a.write_text("a", encoding="utf-8")
    favorite_b.write_text("b", encoding="utf-8")

    app._write_project_config(
        project_dir=project_dir,
        name="GlobalSearchScope",
        sources=[],
        favorites=[str(favorite_a), str(favorite_b)],
        logical_views={
            "project_favorites": {
                "folders": [
                    {"id": "folder-a", "name": "Folder A", "parent_id": "", "sort_order": 0},
                    {"id": "folder-b", "name": "Folder B", "parent_id": "", "sort_order": 1},
                ],
                "placements": [
                    {"item_key": str(favorite_a), "parent_folder_id": "folder-a", "sort_order": 0},
                    {"item_key": str(favorite_b), "parent_folder_id": "folder-b", "sort_order": 0},
                ],
            }
        },
    )
    app._load_project_from_dir(project_dir)
    app._set_current_logical_folder_id("project_favorites", "folder-a")
    app._refresh_favorites_list(app._current_project_favorites())

    app.project_favorites_search_edit.setText("beta")
    app._refresh_favorites_list(app._current_project_favorites())

    texts = [app.favorites_list.item(row).text() for row in range(app.favorites_list.count())]
    assert "beta.pdf" in texts

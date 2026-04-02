from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog


def test_missing_tracked_source_remains_visible(app_env):
    app = app_env["app"]
    tmp = app_env["tmp"]

    missing_source = tmp / "missing-src"
    project_dir = tmp / "Projects" / "RelinkVisible"
    app._write_project_config(project_dir, "RelinkVisible", [str(missing_source)])

    app._load_project_from_dir(project_dir)

    assert app.source_roots_list.count() == 1
    item = app.source_roots_list.item(0)
    assert item.data(Qt.UserRole) == str(missing_source)
    assert "[Missing]" in item.text()


def test_relink_selected_source_directory_updates_path_and_preserves_source_id(app_env, monkeypatch):
    app = app_env["app"]
    tmp = app_env["tmp"]

    old_source = tmp / "old-src"
    new_source = tmp / "new-src"
    old_source.mkdir(parents=True)
    new_source.mkdir(parents=True)
    (new_source / ".doc_control_history.json").write_text('{"entries":[]}', encoding="utf-8")

    project_dir = tmp / "Projects" / "RelinkProject"
    source_id = "src_keep"
    app._write_project_config(
        project_dir,
        "RelinkProject",
        [str(old_source)],
        selected_source=str(old_source),
        source_ids={str(old_source): source_id},
    )

    old_source.rmdir()
    app._load_project_from_dir(project_dir)
    app.source_roots_list.setCurrentRow(0)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(new_source),
    )

    app._relink_selected_source_directory()

    cfg = app._read_project_config(project_dir)
    assert cfg.get("sources") == [str(new_source)]
    assert cfg.get("selected_source") == str(new_source)
    assert cfg.get("source_ids") == {str(new_source): source_id}
    assert app.source_roots_list.item(0).data(Qt.UserRole) == str(new_source)
    assert "[Missing]" not in app.source_roots_list.item(0).text()

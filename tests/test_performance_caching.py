from pathlib import Path


def test_directory_file_cache_uses_ttl_and_invalidation(app_env):
    # Directory listing should reuse cached file entries until invalidated.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "cache-src"
    src.mkdir(parents=True)
    (src / "a.txt").write_text("a", encoding="utf-8")
    (src / ".doc_file_notes.json").write_text("{}", encoding="utf-8")

    app._dir_cache_ttl_seconds = 999.0
    first = app._cached_directory_files(src)
    assert [p.name for p in first] == ["a.txt"]

    (src / "b.txt").write_text("b", encoding="utf-8")
    second = app._cached_directory_files(src)
    assert [p.name for p in second] == ["a.txt"]

    app._invalidate_directory_caches(src)
    third = app._cached_directory_files(src)
    assert [p.name for p in third] == ["a.txt", "b.txt"]


def test_history_cache_invalidation_after_append(app_env):
    # Appending history should invalidate cache so subsequent reads include new rows.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "history-src"
    src.mkdir(parents=True)

    app._append_history(src, "CHECK_OUT", "one.dwg")
    rows1 = app._read_history_rows(src)
    assert len(rows1) == 1

    app._append_history(src, "CHECK_IN_MODIFIED", "one.dwg")
    rows2 = app._read_history_rows(src)
    assert len(rows2) == 2
    assert rows2[-1]["action"] == "CHECK_IN_MODIFIED"


def test_directory_cache_ttl_switches_by_remote_status(app_env, monkeypatch):
    # When no explicit override is set, remote paths should use longer cache TTL.
    app = app_env["app"]
    sample_dir = app_env["tmp"] / "sample"

    app._dir_cache_ttl_seconds = None
    monkeypatch.setattr(app, "_is_probably_remote_directory", lambda _p: True)
    assert app._directory_cache_ttl(sample_dir) == app._remote_dir_cache_ttl_seconds

    monkeypatch.setattr(app, "_is_probably_remote_directory", lambda _p: False)
    assert app._directory_cache_ttl(sample_dir) == app._local_dir_cache_ttl_seconds


def test_file_search_refresh_uses_busy_feedback(app_env, monkeypatch):
    # Search debounce callback should route through feedback wrapper.
    app = app_env["app"]
    called = {"count": 0, "message": ""}

    def fake_refresh(message):
        called["count"] += 1
        called["message"] = message

    monkeypatch.setattr(app, "_refresh_source_files_with_feedback", fake_refresh)
    app._refresh_source_files_from_search()

    assert called["count"] == 1
    assert called["message"] == "Filtering source files..."


def test_set_current_directory_clears_file_search_on_change(app_env):
    # Switching active directories should clear the file-search input.
    app = app_env["app"]
    tmp = app_env["tmp"]

    dir_a = tmp / "dir-a"
    dir_b = tmp / "dir-b"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)

    app.current_directory = dir_a
    app.file_search_edit.setText("abc")
    app._set_current_directory(dir_b)
    assert app.file_search_edit.text() == ""


def test_load_project_clears_file_search(app_env):
    # Project switches should reset file-search so old query does not carry over.
    app = app_env["app"]
    tmp = app_env["tmp"]

    source_dir = tmp / "source"
    source_dir.mkdir(parents=True)
    project_dir = tmp / "Projects" / "SearchReset"
    app._write_project_config(project_dir, "SearchReset", [str(source_dir)])

    app.file_search_edit.setText("leftover query")
    app._load_project_from_dir(project_dir)
    assert app.file_search_edit.text() == ""


def test_set_current_directory_with_feedback_uses_busy_when_idle(app_env, monkeypatch):
    # Directory-switch helper should show busy feedback when not already busy.
    app = app_env["app"]
    tmp = app_env["tmp"]
    directory = tmp / "busy-dir"
    directory.mkdir(parents=True)

    called = {"count": 0}

    @contextmanager
    def fake_busy(_message):
        called["count"] += 1
        yield

    monkeypatch.setattr(app, "_busy_action", fake_busy)
    app._set_current_directory_with_feedback(directory, "Loading directory...")

    assert called["count"] == 1
    assert app.current_directory == directory


def test_set_current_directory_with_feedback_skips_nested_busy(app_env, monkeypatch):
    # If already in a busy action, directory switch should not open another busy modal.
    app = app_env["app"]
    tmp = app_env["tmp"]
    directory = tmp / "nested-busy-dir"
    directory.mkdir(parents=True)

    called = {"count": 0}

    @contextmanager
    def fake_busy(_message):
        called["count"] += 1
        yield

    monkeypatch.setattr(app, "_busy_action", fake_busy)
    app._busy_action_depth = 1
    app._set_current_directory_with_feedback(directory, "Loading directory...")

    assert called["count"] == 0
    assert app.current_directory == directory


def test_track_current_directory_uses_busy_feedback(app_env, monkeypatch):
    # Tracking the currently selected directory should show busy feedback.
    app = app_env["app"]
    tmp = app_env["tmp"]
    project_dir = tmp / "Projects" / "TrackBusy"
    project_dir.mkdir(parents=True)
    source_dir = tmp / "track-me"
    source_dir.mkdir(parents=True)

    app.current_project_dir = str(project_dir)
    app.current_directory = source_dir
    app.source_roots_list.clear()
    app.current_project_label.setText("Current Project: TrackBusy")

    called = {"count": 0}

    @contextmanager
    def fake_busy(_message):
        called["count"] += 1
        yield

    monkeypatch.setattr(app, "_busy_action", fake_busy)
    app._track_current_directory()

    assert called["count"] == 1
from contextlib import contextmanager

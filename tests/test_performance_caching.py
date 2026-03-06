from pathlib import Path


def test_directory_file_cache_uses_ttl_and_invalidation(app_env):
    # Directory listing should reuse cached file entries until invalidated.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "cache-src"
    src.mkdir(parents=True)
    (src / "a.txt").write_text("a", encoding="utf-8")

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

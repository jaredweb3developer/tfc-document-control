import csv
import json


def test_append_history_writes_json_and_preserves_revision_id(app_env):
    # New history storage should be JSON and include revision ids for check-in traces.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "history-json"
    src.mkdir(parents=True)

    app._append_history(src, "CHECK_OUT", "A.dwg", "")
    app._append_history(src, "CHECK_IN_MODIFIED", "A.dwg", "R260306120000-ABCD")

    history_json = src / ".doc_control_history.json"
    assert history_json.exists()
    payload = json.loads(history_json.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    assert len(entries) == 2
    assert entries[-1]["revision_id"] == "R260306120000-ABCD"


def test_read_legacy_csv_shifted_columns_is_corrected(app_env):
    # If legacy CSV rows were written with a new column against old headers, repair field alignment.
    app = app_env["app"]
    tmp = app_env["tmp"]

    src = tmp / "history-legacy"
    src.mkdir(parents=True)
    history_csv = src / ".doc_control_history.csv"
    with history_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "action", "file_name", "user_initials", "user_full_name"])
        writer.writerow(
            [
                "2026-03-06T12:00:00-05:00",
                "CHECK_IN_MODIFIED",
                "B.dwg",
                "R260306120000-ABCD",
                "JWH",
                "Jared Hodgkins",
            ]
        )

    rows = app._read_history_rows(src)
    assert len(rows) == 1
    assert rows[0]["revision_id"] == "R260306120000-ABCD"
    assert rows[0]["user_initials"] == "JWH"
    assert rows[0]["user_full_name"] == "Jared Hodgkins"

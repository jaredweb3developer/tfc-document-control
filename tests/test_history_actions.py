from app import PendingCheckinAction


def test_standard_history_actions(app_env):
    # Standard check-in should log modified/unchanged actions explicitly.
    app = app_env["app"]

    modified = PendingCheckinAction("a", "s", "l", "modified")
    unchanged = PendingCheckinAction("a", "s", "l", "unchanged")

    assert app._history_action_for_checkin(modified, "standard") == "CHECK_IN_MODIFIED"
    assert app._history_action_for_checkin(unchanged, "standard") == "CHECK_IN_UNCHANGED"


def test_force_history_actions(app_env):
    # Force check-in has special rules:
    # - tracked modified file logs like a normal modified check-in
    # - manually selected file logs as force-modified
    app = app_env["app"]

    tracked = PendingCheckinAction("a", "s", "l", "tracked_modified")
    selected = PendingCheckinAction("a", "s", "l", "selected_modified")
    unchanged = PendingCheckinAction("a", "s", "l", "unchanged")

    assert app._history_action_for_checkin(tracked, "force") == "CHECK_IN_MODIFIED"
    assert app._history_action_for_checkin(selected, "force") == "FORCE_CHECK_IN_MODIFIED"
    assert app._history_action_for_checkin(unchanged, "force") == "FORCE_CHECK_IN_UNCHANGED"

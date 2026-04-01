# Working Memory

## Purpose

This file is the session-to-session development ledger for the repository.
Update it at the end of any meaningful change so the next session does not need to rediscover project context.

## Current Snapshot

- Active maintainability milestone: `0.1.4`.
- `app.py` has been reduced to a compatibility entrypoint plus shared constants/dataclasses.
- The application behavior still lives primarily inside `DocumentControlApp`, but the implementation is now split across mixins under `document_control/mixins/`.
- Full local test status after the `0.1.4` structural refactor: `83 passed`.

## What Must Stay Stable

- `import app` should continue to expose the app entrypoint and shared dataclasses used by tests.
- User-facing behavior should not change as part of structural refactors unless explicitly planned.
- Existing on-disk formats must remain backward compatible.

## Known Follow-On Opportunities

- Extract persistence logic from mixins into dedicated services.
- Extract repeated dialogs into reusable widgets/helpers.
- Reduce coupling between UI widgets and persistence operations.
- Add targeted tests for startup lifecycle and any future module/service extraction.

## Session Update Template

Append a short block for each meaningful session:

### YYYY-MM-DD

- Goal:
- Files/areas changed:
- Behavior changed:
- Tests run:
- Risks or follow-up:

### 2026-03-23

- Goal: Refactor the monolithic `app.py` into a modular multi-file structure without changing functionality.
- Files/areas changed: `app.py`, `document_control/window.py`, `document_control/mixins/`, `README.md`, `docs/`.
- Behavior changed: No intended user-facing behavior change; `app.py` remains the compatibility entrypoint.
- Tests run: `.\.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp -p no:cacheprovider` (`83 passed`).
- Risks or follow-up: The app is structurally modular now, but most behavior still lives on one large `DocumentControlApp` type; future work should extract services and reusable widgets incrementally.

### 2026-03-24

- Goal: Add a repeatable Windows packaging flow that produces a colleague-deliverable executable bundle in environments with restrictive temp handling and endpoint protection.
- Files/areas changed: `build.ps1`, `requirements-build.txt`, `.gitignore`, `README.md`, `docs/working-memory.md`.
- Behavior changed: No runtime app behavior change; the repo now includes a PyInstaller `onedir` build path that writes temp/work/config output inside the repository and emits a zipped release artifact.
- Tests run: Not run; `PyInstaller` is not installed in the current virtualenv, and prior pytest runs in this environment were already constrained by temp-directory permissions.
- Risks or follow-up: First real packaging run should verify the built executable launches correctly on a colleague machine with SentinelOne enabled; if Qt plugin resolution fails, add explicit plugin/data collection rules to the build script.

## Maintenance Rule

If a future task changes architecture, persistence formats, feature scope, or test strategy, update this file in the same change.

# Working Memory

## Purpose

This file is the session-to-session development ledger for the repository.
Update it at the end of any meaningful change so the next session does not need to rediscover project context.

## Current Snapshot

- Active maintainability milestone: `0.2.2`.
- `app.py` has been reduced to a compatibility entrypoint plus shared constants/dataclasses.
- The application behavior still lives primarily inside `DocumentControlApp`, but the implementation is now split across mixins under `document_control/mixins/`.
- Automated pytest remains constrained in this environment by Windows temp-directory cleanup permissions; current branch confidence is based on targeted manual testing on copied project/source data.

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

### 2026-04-01

- Goal: Document the future stable-`file_id` migration and add a guarded current-version source-file rename workflow.
- Files/areas changed: `document_control/mixins/records.py`, `document_control/mixins/ui.py`, `tests/test_context_menus.py`, `tests/test_directory_notes_and_controlled_tables.py`, `docs/features.md`, `docs/working-memory.md`, `docs/file-id-migration.md`.
- Behavior changed: Source files can now be renamed from the Files actions/context menu when they are not actively checked out; rename migrates current history rows and file-note ownership to the new name and appends a `RENAME` history event. Non-checked-out source files can also be deleted from the same area; delete appends a `DELETE_FILE` history event and clears file-note ownership for the removed filenames.
- Tests run: Targeted `pytest` invocation attempted for `tests/test_context_menus.py` and `tests/test_directory_notes_and_controlled_tables.py`, but this environment still fails during pytest temp cleanup with `WinError 5`; repo-local runtime sanity checks verified successful rename migration and checked-out rename rejection.
- Risks or follow-up: Checked-out rename/delete remain intentionally blocked because records and revision storage are still keyed from source/locked paths; the migration document captures the longer-term `file_id` design needed to remove that restriction.

### 2026-04-01 (`0.2.0` branch)

- Goal: Start the structural `file_id` migration so filename reuse no longer contaminates document history.
- Files/areas changed: `app.py`, `document_control/mixins/records.py`, `document_control/mixins/sources.py`, `document_control/mixins/projects.py`, `tests/test_directory_notes_and_controlled_tables.py`, `docs/features.md`, `docs/working-memory.md`, `docs/file-id-migration.md`.
- Behavior changed: Source directories now maintain a hidden `.doc_control_index.json` registry. Active files receive stable `file_id` values, history rows can store `file_id` and `previous_file_name`, notes can store `file_id`, revision keys prefer `file_id`, and rename/delete now preserve document identity instead of rewriting filename history. Deleted documents retain their note/history lineage as retired identities.
- Tests run: `pytest` remains blocked in this environment by temp cleanup permissions; repo-local runtime sanity checks verified `file_id`-stable rename, retained delete lineage, and the key collision case where a reused filename no longer inherits a previously deleted document's history.
- Risks or follow-up: Existing pre-`file_id` history remains only partially backfilled; checked-out rename/delete and broader move/copy workflows still need to finish migrating to `file_id`-aware semantics before they can be safely enabled.

### 2026-04-02 (`0.2.0` branch)

- Goal: Stabilize the `file_id` migration on real copied source folders, fix source-index/history/note migration bugs, and establish `0.2.0` as the pinned baseline before moving future changes to `0.2.1`.
- Files/areas changed: `document_control/mixins/records.py`, `document_control/mixins/sources.py`, `tests/test_file_revisions.py`, `docs/0.2.0-file-id-migration-summary.md`, `docs/working-memory.md`.
- Behavior changed: Source-index reconciliation is more conservative and stable; unambiguous legacy history and note rows are backfilled to `file_id`; false history highlighting for unmanaged files was removed; excluded artifacts like `.bak`, `.tmp`, and `plot.log` are filtered from managed source indexing; repeated rename + checkout/checkin flows now preserve one document lineage more reliably on migrated folders.
- Tests run: Manual verification on multiple copied source folders from `0.1.3` / `0.1.4` and CSV-only legacy history, including repeated restart persistence, rename + repeated checkout/checkin, note continuity, revision accessibility after rename, and passive migration inspection of generated `.doc_control_history.json`, `.doc_control_index.json`, and `.doc_file_notes.json`. Automated Python compile/pytest verification remained blocked in this environment by local Python/runtime and temp-permission issues.
- Risks or follow-up: `0.1.5`-damaged metadata remains only partially repairable automatically; `0.2.0` should be treated as the pinned migration baseline for the current small active user group, with new colleague-driven changes continuing on `0.2.1` rather than reopening migration logic unless a real new defect appears.

### 2026-04-02 (`0.2.1` branch)

- Goal: Implement the agreed post-migration functional improvements and pin `0.2.1` as the next working baseline.
- Files/areas changed: `app.py`, `document_control/mixins/ui.py`, `document_control/mixins/sources.py`, `document_control/mixins/notes.py`, `document_control/mixins/records.py`, `tests/test_source_relink.py`, `tests/test_project_note_transfer.py`, `docs/0.2.1-functional-implementation-plan.md`, `docs/working-memory.md`.
- Behavior changed: Missing tracked source directories remain visible and can be manually relinked to a moved folder without replacing the project-level source identity; project notes can be copied or moved between projects using the same searchable project picker pattern used by favorites; the source Files area now uses a table with Explorer-style `Name`, `Date modified`, `Type`, and `Size` columns; file-table columns can be sorted by clicking the header, with date and size sorting using real sortable values rather than plain string order.
- Tests run: Manual validation on copied project and source folders covered source-directory relink with restart persistence, project-note copy/move between projects with metadata inspection in `dctl.json`, source-file detail display, and file-table header sorting by all columns. Targeted pytest attempts for the new tests remained blocked by the same Windows temp cleanup `WinError 5`.
- Risks or follow-up: Individual externally moved source files still do not have identity-preserving relink support; that item remains deferred for `0.2.2`. File-table sorting has only been manually validated so far in this environment.

### 2026-04-02 (`0.2.2` branch)

- Goal: Convert `Source Files` into a generic tabbed `Files` section with `Source` and `Local` browsing, and add local-to-source transfer with destination selection.
- Files/areas changed: `app.py`, `document_control/window.py`, `document_control/mixins/ui.py`, `document_control/mixins/sources.py`, `document_control/mixins/records.py`, `document_control/mixins/config.py`, `document_control/mixins/projects.py`, `tests/test_context_menus.py`, `tests/test_local_files_tab.py`, `docs/features.md`, `docs/working-memory.md`.
- Behavior changed: Main tab section label is now `Files`; the section contains `Source` and `Local` tabs. The Local tab supports tracked local directories, local directory browsing, local file listing with metadata columns, and local file context actions. Users can select local files and run `Add Local File(s) To Source`, which opens a destination chooser dialog defaulting to the most recently loaded source folder while allowing destination override.
- Tests run: `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile app.py document_control/window.py document_control/mixins/config.py document_control/mixins/projects.py document_control/mixins/sources.py document_control/mixins/records.py document_control/mixins/ui.py`; `.venv/bin/python -m pytest -q tests/test_local_files_tab.py tests/test_context_menus.py tests/test_project_selected_source.py tests/test_ordering_controls.py` (`13 passed`).
- Risks or follow-up: Local directory metadata is now persisted in project config (`local_directories`, `selected_local_directory`), so any external tools that strictly validate `dctl.json` keys should tolerate these additive fields; broad full-suite pytest has not been re-run in this slice.

## Maintenance Rule

If a future task changes architecture, persistence formats, feature scope, or test strategy, update this file in the same change.

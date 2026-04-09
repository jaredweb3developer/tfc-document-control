# Working Memory

## Purpose

This file is the session-to-session development ledger for the repository.
Update it at the end of any meaningful change so the next session does not need to rediscover project context.

## Current Snapshot

- Active maintainability milestone: `0.2.4`.
- `app.py` has been reduced to a compatibility entrypoint plus shared constants/dataclasses.
- The application behavior still lives primarily inside `DocumentControlApp`, but the implementation is split across mixins under `document_control/mixins/`.
- The `Main` tab now uses the `0.2.4` 2-column layout with flattened left navigation tabs (`Projects`, `Project Favorites`, `Global Favorites`, `Checked Out`, `Reference Files`, `Notes`), lower `Directories` tabs, a right-side file workspace, an extension-filter dialog, and a modeless directory-details popup.
- `Global Notes` has been retired from runtime and persistence; project notes and file notes remain active features.
- On Windows, verification should be user-run via explicit `pytest` commands that write to `pytest-manual-output.txt`.

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

## Environment Note

- On Windows 11, the user will manually run `pytest` and write the results to `pytest-manual-output.txt`. Future verification steps should reference that file when available instead of assuming local automated pytest execution succeeded in this environment.
- When a change is ready for verification, include the appropriate manual test command in the response so the user can run it on Windows 11 and capture the output in `pytest-manual-output.txt`.

### 2026-04-08

- Goal: Prepare a concrete implementation plan for the `0.2.3` Reference Files refresh and bulk-update feature before coding begins.
- Files/areas changed: `docs/0.2.3/0.2.3-reference-files-refresh-and-update-plan.md`, `docs/working-memory.md`.
- Behavior changed: No application behavior change; the `0.2.3` docs now include a build-ready plan with phased execution, file touch points, test strategy, and an implementation checklist for `Refresh Selected Ref`, `Refresh Selected Ref (If Unchanged)`, `Check Reference Status`, and `Update All References`.
- Tests run: Not run; planning-only change.
- Risks or follow-up: Implementation should start with Phase 1 metadata groundwork so status and refresh behavior can be built on a stable persisted baseline.

### 2026-04-08 (`0.2.3` reference refresh)

- Goal: Implement the `Reference Files` refresh and bulk-update workflow through metadata, status, selected-action, bulk-update, and polish phases.
- Files/areas changed: `app.py`, `document_control/mixins/records.py`, `document_control/mixins/sources.py`, `document_control/mixins/ui.py`, `document_control/mixins/projects.py`, `tests/test_reference_copies.py`, `tests/test_reference_refresh.py`, `docs/0.2.3/0.2.3-reference-files-refresh-and-update-plan.md`, `docs/working-memory.md`.
- Behavior changed: `reference_copy` records now store baseline source/local fingerprint metadata; the app can classify reference status; `Reference Files` now supports `Refresh Selected Ref`, `Refresh Selected Ref (If Unchanged)`, `Check Reference Status`, and `Update All References` with per-row actions plus apply-to-remaining helpers. Dialog and status wording were tightened to be user-facing rather than enum-like. Existing logical-folder placement and search behavior remain intact after refresh operations.
- Tests run: Manual Windows 11 pytest runs recorded in `pytest-manual-output.txt`; targeted runs progressed through `5 passed`, `13 passed`, `33 passed`, and `37 passed` for the final Phase 4+5 targeted set.
- Risks or follow-up: `local_missing` currently remains a skip-only state rather than offering `Recreate`; if users want that later, implement it as an explicit follow-on rather than making overwrite behavior more implicit.

### 2026-04-09 (`0.2.4` planning)

- Goal: Convert the saved `0.2.4` UI restructure request into a build-ready implementation plan before changing the application layout.
- Files/areas changed: `docs/0.2.4/0.2.4-ui-restructure.md`, `docs/0.2.4/0.2.4-ui-restructure-implementation-plan.md`, `docs/development-workflow.md`, `docs/working-memory.md`.
- Behavior changed: No application behavior change; the repo now includes a concrete `0.2.4` plan covering the 2-column layout, left-column navigation tabs, right-column files workspace, extension-filter dialog conversion, and the move of directory details into a popup window.
- Tests run: Not run; planning-only change.
- Risks or follow-up: Follow-up clarification resolved that the directory-details popup should be modeless and that the dormant `Global Notes` feature should be removed entirely rather than carried into the new layout. File notes remain in scope and are not part of that removal.

### 2026-04-09 (`0.2.4` implementation)

- Goal: Deliver the `0.2.4` Main-tab UI restructure, retire `Global Notes`, and finish the corresponding compatibility/documentation cleanup.
- Files/areas changed: `app.py`, `document_control/window.py`, `document_control/mixins/ui.py`, `document_control/mixins/config.py`, `document_control/mixins/sources.py`, `document_control/mixins/notes.py`, `tests/conftest.py`, `tests/test_global_tabs_and_transfer.py`, `tests/test_local_files_tab.py`, `docs/architecture.md`, `docs/development-workflow.md`, `docs/features.md`, `docs/working-memory.md`.
- Behavior changed: The Main tab now uses a 2-column layout with flattened left navigation tabs (`Projects`, `Project Favorites`, `Global Favorites`, `Checked Out`, `Reference Files`, `Notes`), lower `Directories` tabs (`Source`, `Local`), and a right-side file workspace. Source extension filtering moved into a dialog with an inline summary label, and the `Search files` input now uses a wider minimum width in the toolbar. Directory-specific `Controlled Files` and `File Notes` moved into a modeless popup launched from the Files actions menu. Compatibility shims preserve legacy list-style test interactions on the source file table and keep favorites/reference action routing stable. `Global Notes` was removed from runtime and persistence.
- Tests run: User-run manual pytest coverage written to `pytest-manual-output.txt` passed for the targeted `0.2.4` slice, the broader settings/source/directory-notes slice, and the final wide regression command covering reference refresh, reference copies, file revisions, history actions/storage, project file manager, project note transfer, favorites/global-favorites, context menus, local files, logical grouping, project-group search, settings/formats, selected source, relink, ordering controls, and directory notes/tables. Repo virtualenv `py_compile` also passed for the touched Python modules.
- Risks or follow-up: The source file table still carries compatibility behavior (`item(row)` / `count()` / legacy selection handling) to avoid breaking older tests and call sites; if that shim is ever removed, the dependent tests and helper assumptions must be updated in the same change.

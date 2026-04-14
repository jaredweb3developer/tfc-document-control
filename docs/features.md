# Feature Inventory

## Core Application

- Desktop Qt application for document checkout/checkin across tracked projects and tracked source directories.
- User identity stores initials and full name.
- Startup state persists selected project, configured paths, and app section visibility defaults.
- Main window uses a `0.2.4` 2-column `Main` tab layout:
  - left navigation tabs for `Projects`, `Project Favorites`, `Global Favorites`, `Checked Out`, `Reference Files`, and `Notes`
  - lower `Directories` tabs for `Source` and `Local`
  - right-side file workspace

## Project Management

- Tracks multiple projects.
- Supports creating new projects and registering existing ones.
- Stores per-project metadata in `dctl.json`.
- Supports project ordering controls and project search.
- Includes a project file manager for moving project files and updating affected records.

## Source Browsing

- The lower-left `Directories` section includes `Source` and `Local` tabs for tracked roots and directory-tree navigation.
- The right-side file workspace switches between source and local file tables based on the active directories tab.
- The source file toolbar keeps `Extension Filter`, filter summary text, and a widened right-aligned `Search files` input on one row.
- Projects can track multiple source directories.
- Projects can track multiple local directories for filesystem browsing and file selection.
- Source and local browsers include directory tree navigation and per-directory file listing.
- Source file search is debounced.
- Local file search is available in the Local tab.
- Source extension filtering is configured from a dialog launched by the `Extension Filter` button, with a summary label shown inline in the file workspace.
- Controlled files and directory file-note summaries are available in a modeless `Directory Details` popup rather than in the permanent main layout.
- Directory file caching distinguishes local and probable remote paths.
- Local files can be selected and copied to a chosen source destination via `Add Local File(s) To Source`.
- Local item workflows support files and directories for open, rename, move, and delete actions from the local file table.

## Checkout, Checkin, and Records

- Checked-out records store source path, locked source path, local path, identity, project, source root, and timestamp.
- Checked-out and reference records are rendered in tables and local project lists.
- Checkin workflows support pending-action review and force-checkin planning.
- History data records action metadata without depending on the current local file path.

## Revisions and History

- JSON history storage is the primary format.
- Legacy CSV history remains readable for backward compatibility.
- Source directories now maintain a hidden source-index registry for stable `file_id` assignment.
- File revision snapshots are stored in per-project version storage.
- Revision snapshots track hash, revision id, and optional note metadata.
- A checked-out record can be switched to a saved revision after saved-state checks.

## Favorites, Notes, and Milestones

- Supports project favorites and global favorites as separate top-level navigation tabs.
- Supports checked-out project files and project reference files as separate top-level navigation tabs.
- Favorites can be transferred between project and global scopes.
- Supports project notes.
- The `Notes` navigation tab is project-note-only; the retired `Global Notes` feature is no longer part of the app.
- Note presets can generate default notes for projects.
- Milestones are project-scoped and support snapshot-style metadata.

## Customization and Filtering

- Item customizations support grouping and styling.
- Group color settings can drive list/table presentation.
- Extension filter presets can be saved and applied per project.
- Search behavior includes project groups, favorites groups, and note groups where applicable.

## File Notes and Context Actions

- Directory notes support per-file notes and file-note windows.
- Context menus are available across source files, records, projects, favorites, notes, milestones, and source roots.
- Location actions can open files or parent directories for source, local, and reference-backed records.
- Source files are transitioning to stable `file_id` identity while retaining visible on-disk checkout rename behavior.
- Rename now appends `RENAME` history linked by `file_id` instead of rewriting old history rows by filename.
- Delete now retires the file in the source index and appends `DELETE_FILE` history without erasing attached note/history records.
- Checked-out source files still remain rename/delete-blocked in the current slice while checkout and revision path handling finish migrating.
- History-highlighted source-file names use an explicit dark foreground with the existing pastel status backgrounds so the text remains readable in dark mode.

## Persistence Files

- `settings.json`
- `projects.json`
- `checkout_records.json`
- `filter_presets.json`
- `global_favorites.json`
- `note_presets.json`
- `item_customizations.json`
- `Projects/<Project>/dctl.json`
- `<source>/.doc_control_history.json`
- `<project>/file_versions.json`

## Behavioral Invariants

- Existing project and history formats should remain readable after refactors.
- `app.py` remains the stable import and launch target.
- New development should preserve current user-facing behavior unless a change is explicitly planned and documented.
- `Global Notes` is retired and should not be reintroduced accidentally when changing notes-related UI or persistence.

# Feature Inventory

## Core Application

- Desktop Qt application for document checkout/checkin across tracked projects and tracked source directories.
- User identity stores initials and full name.
- Startup state persists selected project, configured paths, and app section visibility defaults.

## Project Management

- Tracks multiple projects.
- Supports creating new projects and registering existing ones.
- Stores per-project metadata in `dctl.json`.
- Supports project ordering controls and project search.
- Includes a project file manager for moving project files and updating affected records.

## Source Browsing

- Projects can track multiple source directories.
- Source browser includes directory tree navigation and per-directory file listing.
- Source file search is debounced.
- Controlled files table reflects the selected directory.
- Directory file caching distinguishes local and probable remote paths.

## Checkout, Checkin, and Records

- Checked-out records store source path, locked source path, local path, identity, project, source root, and timestamp.
- Checked-out and reference records are rendered in tables and local project lists.
- Checkin workflows support pending-action review and force-checkin planning.
- History data records action metadata without depending on the current local file path.

## Revisions and History

- JSON history storage is the primary format.
- Legacy CSV history remains readable for backward compatibility.
- File revision snapshots are stored in per-project version storage.
- Revision snapshots track hash, revision id, and optional note metadata.
- A checked-out record can be switched to a saved revision after saved-state checks.

## Favorites, Notes, and Milestones

- Supports project favorites and global favorites.
- Favorites can be transferred between project and global scopes.
- Supports project notes and global notes.
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

## Persistence Files

- `settings.json`
- `projects.json`
- `checkout_records.json`
- `filter_presets.json`
- `global_favorites.json`
- `global_notes.json`
- `note_presets.json`
- `item_customizations.json`
- `Projects/<Project>/dctl.json`
- `<source>/.doc_control_history.json`
- `<project>/file_versions.json`

## Behavioral Invariants

- Existing project and history formats should remain readable after refactors.
- `app.py` remains the stable import and launch target.
- New development should preserve current user-facing behavior unless a change is explicitly planned and documented.

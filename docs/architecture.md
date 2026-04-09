# Architecture

## Entry Point

- `app.py` is the compatibility entrypoint.
- It owns the shared constants, dataclasses, and top-level imports that the rest of the application depends on.
- Runtime and tests should continue to use `import app` and `python app.py`.

## Application Package

- `document_control/window.py`
  - Defines `DocumentControlApp`.
  - Composes the full window from mixins.
  - Keeps the startup lifecycle, message helpers, and `main()`.
  - Owns the top-level app load/save lifecycle for settings, tracked projects, records, favorites, presets, and item customizations.
- `document_control/mixins/ui.py`
  - UI construction and widget layout.
  - Owns the `0.2.4` main-window structure:
    - left navigation tabs for `Projects`, `Project Favorites`, `Global Favorites`, `Checked Out`, `Reference Files`, and `Notes`
    - lower `Directories` tabs for `Source` and `Local`
    - right-side file workspace
    - extension-filter dialog and summary label
    - modeless directory-details popup
  - Preserves compatibility helper behavior for tests and older call sites that still treat source-file rows like list-style widgets.
- `document_control/mixins/config.py`
  - App settings, path selection, startup flow, and tracked-project registry basics.
  - Owns project config read/write, startup-tab behavior, and current project/source/local selection helpers.
- `document_control/mixins/projects.py`
  - Project creation/editing, tracked project management, and project file manager workflows.
- `document_control/mixins/sources.py`
  - Source directory browsing, local directory browsing, project favorites, and global favorites interactions.
  - Owns the source/local file tables, directory tree refresh, source/local transfer actions, and logical-folder rendering for favorites and record-backed local project lists.
- `document_control/mixins/notes.py`
  - Project notes, note presets, milestones, item customizations, and filter presets.
- `document_control/mixins/records.py`
  - History storage, directory notes, checkout/checkin workflows, revision snapshots, record rendering, and context-menu actions.
  - Owns controlled-files and directory-notes table behavior even though those tables are now hosted in the modeless directory-details popup.

## Current UI Shape

- Main window top-level tabs:
  - `Main`
  - `Checked Out Files`
  - `Configuration`
- `Main` tab:
  - left column:
    - navigation tabs: `Projects`, `Project Favorites`, `Global Favorites`, `Checked Out`, `Reference Files`, `Notes`
    - directories group: `Source`, `Local`
  - right column:
    - file workspace switched by the active directories tab
- The source file toolbar includes an `Extension Filter` button, inline summary text, and a wider right-aligned `Search files` input with a larger minimum width for the `0.2.4` layout.
- Directory-specific `Controlled Files` and `File Notes` no longer consume permanent main-window space; they live in a modeless popup opened from the source-files actions menu.

## Design Rules

- Preserve `app.py` as the stable import surface unless there is a strong reason to change external imports.
- Prefer moving behavior into an existing mixin by responsibility instead of adding more code to `app.py`.
- If a mixin becomes difficult to scan, split it again by concern rather than growing a new monolith inside the package.
- Shared constants and dataclasses should remain centralized so tests and tooling can patch them consistently.

## Refactor Intent

- This structure is deliberately conservative.
- The main goal remains maintainability through file boundaries plus conservative feature delivery.
- `0.2.4` intentionally included a planned UX rewrite of the Main tab layout while keeping persistence formats and most action entrypoints stable.
- Future refactors should focus on extracting service objects and smaller reusable widgets from the mixins without changing public behavior unexpectedly.

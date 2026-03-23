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
- `document_control/mixins/ui.py`
  - UI construction and widget layout.
- `document_control/mixins/config.py`
  - App settings, path selection, startup flow, and tracked-project registry basics.
- `document_control/mixins/projects.py`
  - Project creation/editing, tracked project management, and project file manager workflows.
- `document_control/mixins/sources.py`
  - Source directory browsing, controlled files, project favorites, and global favorites interactions.
- `document_control/mixins/notes.py`
  - Global notes, project notes, note presets, milestones, item customizations, and filter presets.
- `document_control/mixins/records.py`
  - History storage, directory notes, checkout/checkin workflows, revision snapshots, record rendering, and context-menu actions.

## Design Rules

- Preserve `app.py` as the stable import surface unless there is a strong reason to change external imports.
- Prefer moving behavior into an existing mixin by responsibility instead of adding more code to `app.py`.
- If a mixin becomes difficult to scan, split it again by concern rather than growing a new monolith inside the package.
- Shared constants and dataclasses should remain centralized so tests and tooling can patch them consistently.

## Refactor Intent

- This structure is deliberately conservative.
- The main goal of `0.1.4` is maintainability through file boundaries, not a behavior or UX rewrite.
- Future refactors should focus on extracting service objects and smaller reusable widgets from the mixins without changing public behavior unexpectedly.

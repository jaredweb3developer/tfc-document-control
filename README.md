# Document Control App

Python + Qt desktop app for checking source documents in and out across tracked projects and tracked source directories.

## Highlights
- Configuration section is now top-most.
- User initials and full name are stored side-by-side.
- Root application settings are saved to `settings.json`.
- Tracked project registry is saved to `projects.json`.
- Each project stores its own config in `dctl.json` inside that project's folder.
- Default base project directory is `Projects/` under the application root.
- Default project is created automatically if no tracked projects exist.
- Projects can track multiple source directories.
- Source Files view includes:
  - tracked source directories
  - a directory tree browser
  - a file list bound to the selected directory
  - per-file document history view
- Checked Out Files view includes tabs for:
  - all checked out files
  - current project only
- History files do not store the local file path.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python app.py
```

## Build A Windows Executable
Use the PowerShell build script to create a distributable `onedir` package and zip archive.

Why `onedir` instead of `onefile`:
- `onedir` avoids self-extracting to temp at runtime, which is generally friendlier to SentinelOne and similar endpoint protection tools.
- The script pins `TMP`, `TEMP`, and the PyInstaller config directory inside the repo so the build does not depend on restricted user temp folders.

Build steps:

```powershell
.\build.ps1 -InstallBuildDeps -Clean
```

If endpoint protection keeps fresh PyInstaller files open long enough to interfere with archiving, you can either let the script retry longer or skip zip creation and distribute the `dist` folder directly:

```powershell
.\build.ps1 -ArchiveRetryCount 24 -ArchiveRetryDelaySeconds 5
.\build.ps1 -SkipArchive
```

Outputs:
- `dist/TFC Document Control/`: distributable folder containing `TFC Document Control.exe` plus bundled Qt/runtime files
- `release/tfc-document-control-windows.zip`: zipped delivery artifact

If dependencies are already installed, a normal rebuild is:

```powershell
.\build.ps1
```

## Structure
- `app.py`: stable compatibility entrypoint, shared constants, shared dataclasses
- `document_control/window.py`: `DocumentControlApp` assembly and startup lifecycle
- `document_control/mixins/`: functional split of the former monolithic `app.py`
- `docs/architecture.md`: codebase map
- `docs/features.md`: feature inventory and invariants
- `docs/working-memory.md`: session-to-session development ledger
- `docs/development-workflow.md`: how to use and maintain the memory files

## Tests
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

On Windows with restrictive temp permissions, this also works:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp -p no:cacheprovider
```

## Data Layout
- `settings.json`: user identity, base projects directory, last loaded project
- `projects.json`: tracked project list
- `Projects/<ProjectName>/dctl.json`: per-project config
- `.checkout_records.json`: checkout state
- `.doc_control_history.csv`: per-source-folder file history

## Notes
- Saving a new project creates a project directory under the configured local base folder.
- Adding an existing project tracks a user-selected `dctl.json` file.
- Untracking a project only removes it from `projects.json`; it does not delete project files.
- For ongoing development, update `docs/working-memory.md` in the same change whenever architecture, behavior, or testing expectations shift.

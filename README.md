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

## Tests
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
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

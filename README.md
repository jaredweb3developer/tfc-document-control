# Basic Document Control App (Python + Qt)

This is a starter desktop application for checking out and checking in files from a shared source folder.

## Features
- Pick a source folder (shared/network path).
- Pick a local working folder.
- Enter user initials and optional full name.
- Save/load named project configurations (source/local).
- View and load from a recent-projects list.
- Select one or more files and **Check Out**:
  - Copy source file to local folder.
  - Rename source file from `name.ext` to `name-INITIALS.ext`.
  - Persist a checkout record in `.checkout_records.json`.
  - Append a history event in the source folder log.
- Select checked-out rows and **Check In**:
  - Copy local file over the locked source file.
  - Rename locked source file back to original name (remove initials suffix).
  - Remove checkout record.
  - Append a history event in the source folder log.
- Add brand new local file(s) into the source folder with **Add Local File(s) To Source**.
- Open files from list views:
  - Double-click source files or checked-out rows.
  - Use **Open Selected** buttons in each section.

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

## Data Files
- `.checkout_records.json`: checked-out file state.
- `.projects.json`: saved projects and recent-projects metadata.
- `.app_settings.json`: persisted user initials and full name.
- `.doc_control_history.csv` (inside each source folder): file activity history for that folder.
  - Columns: `timestamp, action, file_name, user_initials, user_full_name, local_file`

## Notes
- If two users run separate app instances without a shared backend, collisions are still possible. A shared lock file or database is the natural next step.

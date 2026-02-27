import csv
import json
import shutil
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

RECORDS_FILE = Path(".checkout_records.json")
PROJECTS_FILE = Path(".projects.json")
SETTINGS_FILE = Path(".app_settings.json")
HISTORY_FILE_NAME = ".doc_control_history.csv"
MAX_RECENT_PROJECTS = 10


@dataclass
class CheckoutRecord:
    source_file: str
    locked_source_file: str
    local_file: str
    initials: str


class DocumentControlApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Document Control - Basic Checkout")
        self.resize(1040, 780)

        self.records: List[CheckoutRecord] = []
        self.projects: Dict[str, Dict[str, str]] = {}
        self.recent_projects: List[str] = []
        self.current_project_name: str = ""

        self._build_ui()
        self._load_settings()
        self._load_projects()
        self._load_records()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        projects_group = QGroupBox("Projects")
        projects_layout = QGridLayout(projects_group)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("Project name")
        save_project_btn = QPushButton("Save Project")
        save_project_btn.clicked.connect(self._save_project_from_inputs)

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.itemDoubleClicked.connect(
            lambda item: self._load_project_by_name(item.text())
        )

        load_recent_btn = QPushButton("Load Selected Recent")
        load_recent_btn.clicked.connect(self._load_selected_recent_project)

        projects_layout.addWidget(QLabel("Project Name:"), 0, 0)
        projects_layout.addWidget(self.project_name_edit, 0, 1)
        projects_layout.addWidget(save_project_btn, 0, 2)

        projects_layout.addWidget(QLabel("Recent Projects:"), 1, 0)
        projects_layout.addWidget(self.recent_projects_list, 1, 1, 2, 1)
        projects_layout.addWidget(load_recent_btn, 1, 2)

        layout.addWidget(projects_group)

        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout(config_group)

        self.source_path_edit = QLineEdit()
        self.source_path_edit.setPlaceholderText("Select shared network source folder")
        browse_source_btn = QPushButton("Browse Source")
        browse_source_btn.clicked.connect(self._choose_source_folder)

        self.local_path_edit = QLineEdit()
        self.local_path_edit.setPlaceholderText("Select local checkout folder")
        browse_local_btn = QPushButton("Browse Local")
        browse_local_btn.clicked.connect(self._choose_local_folder)

        self.initials_edit = QLineEdit()
        self.initials_edit.setPlaceholderText("e.g. JH")
        self.initials_edit.setMaxLength(5)

        self.full_name_edit = QLineEdit()
        self.full_name_edit.setPlaceholderText("Optional full name")

        config_layout.addWidget(QLabel("Source Folder:"), 0, 0)
        config_layout.addWidget(self.source_path_edit, 0, 1)
        config_layout.addWidget(browse_source_btn, 0, 2)

        config_layout.addWidget(QLabel("Local Folder:"), 1, 0)
        config_layout.addWidget(self.local_path_edit, 1, 1)
        config_layout.addWidget(browse_local_btn, 1, 2)

        config_layout.addWidget(QLabel("User Initials:"), 2, 0)
        config_layout.addWidget(self.initials_edit, 2, 1)

        config_layout.addWidget(QLabel("User Full Name:"), 3, 0)
        config_layout.addWidget(self.full_name_edit, 3, 1)

        layout.addWidget(config_group)

        files_group = QGroupBox("Available Files In Source")
        files_layout = QVBoxLayout(files_group)
        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.files_list.itemDoubleClicked.connect(self._open_source_item)

        file_button_bar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_source_files)
        checkout_btn = QPushButton("Check Out Selected")
        checkout_btn.clicked.connect(self._checkout_selected)
        open_source_btn = QPushButton("Open Selected")
        open_source_btn.clicked.connect(self._open_selected_source_files)
        add_new_btn = QPushButton("Add Local File(s) To Source")
        add_new_btn.clicked.connect(self._add_new_files_to_source)

        file_button_bar.addWidget(refresh_btn)
        file_button_bar.addWidget(checkout_btn)
        file_button_bar.addWidget(open_source_btn)
        file_button_bar.addWidget(add_new_btn)
        file_button_bar.addStretch()

        files_layout.addWidget(self.files_list)
        files_layout.addLayout(file_button_bar)

        layout.addWidget(files_group)

        records_group = QGroupBox("Checked Out Files")
        records_layout = QVBoxLayout(records_group)

        self.records_table = QTableWidget(0, 4)
        self.records_table.setHorizontalHeaderLabels(
            ["Original Source File", "Locked Source File", "Local File", "Initials"]
        )
        self.records_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.records_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.records_table.horizontalHeader().setStretchLastSection(True)
        self.records_table.cellDoubleClicked.connect(self._open_record_row)

        records_button_bar = QHBoxLayout()
        checkin_btn = QPushButton("Check In Selected")
        checkin_btn.clicked.connect(self._checkin_selected)
        open_local_btn = QPushButton("Open Selected")
        open_local_btn.clicked.connect(self._open_selected_record_files)

        records_button_bar.addWidget(checkin_btn)
        records_button_bar.addWidget(open_local_btn)
        records_button_bar.addStretch()

        records_layout.addWidget(self.records_table)
        records_layout.addLayout(records_button_bar)

        layout.addWidget(records_group)

    def _choose_source_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if path:
            self.source_path_edit.setText(path)
            self._refresh_source_files()

    def _choose_local_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Local Folder")
        if path:
            self.local_path_edit.setText(path)

    def _normalize_initials(self) -> str:
        initials = "".join(ch for ch in self.initials_edit.text().strip().upper() if ch.isalnum())
        self.initials_edit.setText(initials)
        return initials

    def _current_full_name(self) -> str:
        full_name = self.full_name_edit.text().strip()
        self.full_name_edit.setText(full_name)
        return full_name

    def _source_dir(self) -> Path:
        return Path(self.source_path_edit.text().strip())

    def _local_dir(self) -> Path:
        return Path(self.local_path_edit.text().strip())

    def _validate_source_folder(self) -> bool:
        if not self._source_dir().is_dir():
            self._error("Select a valid source folder.")
            return False
        return True

    def _validate_local_folder(self) -> bool:
        if not self._local_dir().is_dir():
            self._error("Select a valid local folder.")
            return False
        return True

    def _validate_identity(self) -> bool:
        if not self._normalize_initials():
            self._error("Enter user initials.")
            return False
        self._current_full_name()
        return True

    def _validate_checkout_inputs(self) -> bool:
        if not self._validate_source_folder():
            return False
        if not self._validate_local_folder():
            return False
        if not self._validate_identity():
            return False
        return True

    def _validate_project_inputs(self) -> bool:
        if not self._validate_source_folder():
            return False
        if not self._validate_local_folder():
            return False
        return True

    def _refresh_source_files(self) -> None:
        self.files_list.clear()
        source = self._source_dir()
        if not source.is_dir():
            return

        for item in sorted(source.iterdir()):
            if item.is_file():
                self.files_list.addItem(QListWidgetItem(item.name))

    def _locked_name_for(self, source_file: Path, initials: str) -> Path:
        return source_file.with_name(f"{source_file.stem}-{initials}{source_file.suffix}")

    def _history_file_for(self, source_dir: Path) -> Path:
        return source_dir / HISTORY_FILE_NAME

    def _append_history(
        self,
        source_dir: Path,
        action: str,
        file_name: str,
        local_file: str = "",
    ) -> None:
        history_file = self._history_file_for(source_dir)
        if not history_file.exists():
            with history_file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "timestamp",
                        "action",
                        "file_name",
                        "user_initials",
                        "user_full_name",
                        "local_file",
                    ]
                )

        with history_file.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    action,
                    file_name,
                    self._normalize_initials(),
                    self._current_full_name(),
                    local_file,
                ]
            )

    def _checkout_selected(self) -> None:
        if not self._validate_checkout_inputs():
            return

        selected_items = self.files_list.selectedItems()
        if not selected_items:
            self._error("Select at least one file to check out.")
            return

        source_dir = self._source_dir()
        local_dir = self._local_dir()
        initials = self._normalize_initials()

        errors: List[str] = []
        for item in selected_items:
            source_file = source_dir / item.text()
            locked_source_file = self._locked_name_for(source_file, initials)
            local_file = local_dir / source_file.name

            if not source_file.exists():
                errors.append(f"Missing source file: {source_file.name}")
                continue
            if locked_source_file.exists():
                errors.append(f"Already checked out: {locked_source_file.name}")
                continue

            try:
                shutil.copy2(source_file, local_file)
                source_file.rename(locked_source_file)
                self.records.append(
                    CheckoutRecord(
                        source_file=str(source_file),
                        locked_source_file=str(locked_source_file),
                        local_file=str(local_file),
                        initials=initials,
                    )
                )
                self._append_history(
                    source_dir,
                    action="CHECK_OUT",
                    file_name=source_file.name,
                    local_file=str(local_file),
                )
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")

        self._save_records()
        self._refresh_source_files()
        self._render_records_table()

        if errors:
            self._error("Some files failed:\n" + "\n".join(errors))
        else:
            self._info("Checkout complete.")

    def _selected_record_rows(self) -> List[int]:
        return sorted({idx.row() for idx in self.records_table.selectedIndexes()})

    def _checkin_selected(self) -> None:
        if not self._validate_identity():
            return

        rows = self._selected_record_rows()
        if not rows:
            self._error("Select at least one checked-out row to check in.")
            return

        errors: List[str] = []
        remaining: List[CheckoutRecord] = []

        row_set = set(rows)
        for row_idx, record in enumerate(self.records):
            if row_idx not in row_set:
                remaining.append(record)
                continue

            source_file = Path(record.source_file)
            locked_source_file = Path(record.locked_source_file)
            local_file = Path(record.local_file)

            if not local_file.exists():
                errors.append(f"Local file missing: {local_file}")
                remaining.append(record)
                continue
            if not locked_source_file.exists():
                errors.append(f"Locked source file missing: {locked_source_file}")
                remaining.append(record)
                continue

            try:
                # Update the locked source copy first, then restore the original file name.
                shutil.copy2(local_file, locked_source_file)
                locked_source_file.replace(source_file)
                self._append_history(
                    source_file.parent,
                    action="CHECK_IN",
                    file_name=source_file.name,
                    local_file=str(local_file),
                )
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")
                remaining.append(record)

        self.records = remaining
        self._save_records()
        self._refresh_source_files()
        self._render_records_table()

        if errors:
            self._error("Some files failed to check in:\n" + "\n".join(errors))
        else:
            self._info("Check-in complete.")

    def _add_new_files_to_source(self) -> None:
        if not self._validate_source_folder():
            return
        if not self._validate_identity():
            return

        source_dir = self._source_dir()
        start_dir = self.local_path_edit.text().strip() or str(Path.home())
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Local File(s) To Add",
            start_dir,
            "All Files (*)",
        )

        if not file_paths:
            return

        errors: List[str] = []
        for file_path in file_paths:
            local_file = Path(file_path)
            target_file = source_dir / local_file.name
            if target_file.exists():
                errors.append(f"Already exists in source: {target_file.name}")
                continue

            try:
                shutil.copy2(local_file, target_file)
                self._append_history(
                    source_dir,
                    action="ADD_FILE",
                    file_name=target_file.name,
                    local_file=str(local_file),
                )
            except OSError as exc:
                errors.append(f"{local_file.name}: {exc}")

        self._refresh_source_files()

        if errors:
            self._error("Some files failed to add:\n" + "\n".join(errors))
        else:
            self._info("File(s) added to source folder.")

    def _open_source_item(self, item: QListWidgetItem) -> None:
        self._open_paths([self._source_dir() / item.text()])

    def _open_selected_source_files(self) -> None:
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            self._error("Select at least one source file to open.")
            return

        paths = [self._source_dir() / item.text() for item in selected_items]
        self._open_paths(paths)

    def _open_record_row(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.records):
            self._open_paths([Path(self.records[row].local_file)])

    def _open_selected_record_files(self) -> None:
        rows = self._selected_record_rows()
        if not rows:
            self._error("Select at least one checked-out file to open.")
            return

        paths = [Path(self.records[row].local_file) for row in rows if 0 <= row < len(self.records)]
        self._open_paths(paths)

    def _open_paths(self, paths: List[Path]) -> None:
        errors: List[str] = []
        for path in paths:
            if not path.exists():
                errors.append(f"Missing file: {path}")
                continue
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            if not ok:
                errors.append(f"Could not open: {path}")

        if errors:
            self._error("Some files could not be opened:\n" + "\n".join(errors))

    def _render_records_table(self) -> None:
        self.records_table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            row_items = [
                QTableWidgetItem(record.source_file),
                QTableWidgetItem(record.locked_source_file),
                QTableWidgetItem(record.local_file),
                QTableWidgetItem(record.initials),
            ]
            for col, cell_item in enumerate(row_items):
                cell_item.setFlags(cell_item.flags() ^ Qt.ItemIsEditable)
                self.records_table.setItem(row, col, cell_item)

        self.records_table.resizeColumnsToContents()

    def _load_records(self) -> None:
        if not RECORDS_FILE.exists():
            return

        try:
            data = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
            self.records = [CheckoutRecord(**entry) for entry in data]
        except (OSError, ValueError, TypeError):
            self.records = []

        self._render_records_table()

    def _save_records(self) -> None:
        payload = [asdict(record) for record in self.records]
        RECORDS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_settings(self) -> None:
        if not SETTINGS_FILE.exists():
            return

        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return

        self.initials_edit.setText(str(data.get("initials", "")).strip())
        self.full_name_edit.setText(str(data.get("full_name", "")).strip())

    def _save_settings(self) -> None:
        payload = {
            "initials": self._normalize_initials(),
            "full_name": self._current_full_name(),
        }
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _save_project_from_inputs(self) -> None:
        if not self._validate_project_inputs():
            return

        name = self.project_name_edit.text().strip()
        if not name:
            name, ok = QInputDialog.getText(self, "Save Project", "Project name:")
            if not ok:
                return
            name = name.strip()

        if not name:
            self._error("Project name is required.")
            return

        self.projects[name] = {
            "source": self.source_path_edit.text().strip(),
            "local": self.local_path_edit.text().strip(),
        }
        self.current_project_name = name
        self.project_name_edit.setText(name)
        self._touch_recent_project(name)
        self._save_projects()
        self._refresh_recent_projects_list()
        self._info(f"Project '{name}' saved.")

    def _load_selected_recent_project(self) -> None:
        item = self.recent_projects_list.currentItem()
        if not item:
            self._error("Select a recent project to load.")
            return
        self._load_project_by_name(item.text())

    def _load_project_by_name(self, name: str) -> None:
        project = self.projects.get(name)
        if not project:
            self._error(f"Project '{name}' not found.")
            return

        self.source_path_edit.setText(project.get("source", ""))
        self.local_path_edit.setText(project.get("local", ""))
        self.current_project_name = name
        self.project_name_edit.setText(name)
        self._touch_recent_project(name)
        self._save_projects()
        self._refresh_recent_projects_list()
        self._refresh_source_files()

    def _touch_recent_project(self, name: str) -> None:
        self.recent_projects = [entry for entry in self.recent_projects if entry != name]
        self.recent_projects.insert(0, name)
        self.recent_projects = self.recent_projects[:MAX_RECENT_PROJECTS]

    def _refresh_recent_projects_list(self) -> None:
        self.recent_projects_list.clear()
        for name in self.recent_projects:
            if name in self.projects:
                self.recent_projects_list.addItem(QListWidgetItem(name))

        for row in range(self.recent_projects_list.count()):
            item = self.recent_projects_list.item(row)
            if item.text() == self.current_project_name:
                self.recent_projects_list.setCurrentItem(item)
                break

    def _load_projects(self) -> None:
        if not PROJECTS_FILE.exists():
            self._refresh_recent_projects_list()
            return

        try:
            data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
            projects = data.get("projects", {})
            recent = data.get("recent_projects", [])
            last_project = data.get("last_project", "")

            if isinstance(projects, dict):
                self.projects = {
                    str(name): {
                        "source": str(cfg.get("source", "")),
                        "local": str(cfg.get("local", "")),
                    }
                    for name, cfg in projects.items()
                    if isinstance(cfg, dict)
                }

            if isinstance(recent, list):
                self.recent_projects = [
                    str(name) for name in recent if str(name) in self.projects
                ][:MAX_RECENT_PROJECTS]

            if isinstance(last_project, str) and last_project in self.projects:
                self._apply_project(last_project, touch_recent=False)
        except (OSError, ValueError, TypeError):
            self.projects = {}
            self.recent_projects = []
            self.current_project_name = ""

        self._refresh_recent_projects_list()

    def _apply_project(self, name: str, touch_recent: bool = True) -> None:
        project = self.projects.get(name, {})
        self.source_path_edit.setText(project.get("source", ""))
        self.local_path_edit.setText(project.get("local", ""))
        self.current_project_name = name
        self.project_name_edit.setText(name)
        if touch_recent:
            self._touch_recent_project(name)
        self._refresh_source_files()

    def _save_projects(self) -> None:
        payload = {
            "projects": self.projects,
            "recent_projects": self.recent_projects,
            "last_project": self.current_project_name,
        }
        PROJECTS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def _info(self, message: str) -> None:
        QMessageBox.information(self, "Info", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        self._save_projects()
        self._save_records()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = DocumentControlApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

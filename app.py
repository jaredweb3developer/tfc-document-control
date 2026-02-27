import csv
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QDir, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileSystemModel,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = APP_ROOT / "settings.json"
PROJECTS_FILE = APP_ROOT / "projects.json"
RECORDS_FILE = APP_ROOT / ".checkout_records.json"
PROJECT_CONFIG_FILE = "dctl.json"
HISTORY_FILE_NAME = ".doc_control_history.csv"
DEFAULT_PROJECT_NAME = "Default"


@dataclass
class CheckoutRecord:
    source_file: str
    locked_source_file: str
    local_file: str
    initials: str
    project_name: str
    project_dir: str
    source_root: str


class DocumentControlApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Document Control")
        self.resize(1360, 860)

        self.records: List[CheckoutRecord] = []
        self.tracked_projects: List[Dict[str, str]] = []
        self.current_project_dir: str = ""
        self.current_directory: Optional[Path] = None

        self._build_ui()
        self._load_settings()
        self._load_tracked_projects()
        self._load_records()
        self._load_last_or_default_project()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        layout.addWidget(self._build_configuration_group())
        layout.addWidget(self._build_projects_group())
        layout.addWidget(self._build_source_files_group(), stretch=1)
        layout.addWidget(self._build_checked_out_group(), stretch=1)

    def _build_configuration_group(self) -> QGroupBox:
        group = QGroupBox("Configuration")
        layout = QGridLayout(group)

        self.local_path_edit = QLineEdit(str(self._default_projects_dir()))
        self.local_path_edit.setPlaceholderText("Base directory for project folders")
        browse_local_btn = QPushButton("Browse")
        browse_local_btn.clicked.connect(self._choose_local_folder)

        identity_bar = QHBoxLayout()
        identity_bar.addWidget(QLabel("Initials"))
        self.initials_edit = QLineEdit()
        self.initials_edit.setPlaceholderText("e.g. JH")
        self.initials_edit.setMaxLength(5)
        identity_bar.addWidget(self.initials_edit)
        identity_bar.addSpacing(12)
        identity_bar.addWidget(QLabel("Full Name"))
        self.full_name_edit = QLineEdit()
        self.full_name_edit.setPlaceholderText("Optional full name")
        identity_bar.addWidget(self.full_name_edit, stretch=1)

        layout.addWidget(QLabel("Local Folder:"), 0, 0)
        layout.addWidget(self.local_path_edit, 0, 1)
        layout.addWidget(browse_local_btn, 0, 2)
        layout.addWidget(QLabel("User:"), 1, 0)
        layout.addLayout(identity_bar, 1, 1, 1, 2)

        return group

    def _build_projects_group(self) -> QGroupBox:
        group = QGroupBox("Projects")
        layout = QGridLayout(group)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("Project name")
        save_project_btn = QPushButton("Save Project")
        save_project_btn.clicked.connect(self._save_project_from_inputs)
        load_project_btn = QPushButton("Load Selected")
        load_project_btn.clicked.connect(self._load_selected_tracked_project)
        add_project_btn = QPushButton("Track Existing")
        add_project_btn.clicked.connect(self._add_existing_project)
        remove_project_btn = QPushButton("Untrack Selected")
        remove_project_btn.clicked.connect(self._remove_selected_project)

        self.tracked_projects_list = QListWidget()
        self.tracked_projects_list.itemDoubleClicked.connect(
            lambda item: self._load_project_from_dir(item.data(Qt.UserRole))
        )

        self.project_path_label = QLabel("Config: -")
        self.project_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        controls_bar = QHBoxLayout()
        controls_bar.addWidget(save_project_btn)
        controls_bar.addWidget(load_project_btn)
        controls_bar.addWidget(add_project_btn)
        controls_bar.addWidget(remove_project_btn)
        controls_bar.addStretch()

        layout.addWidget(QLabel("Project Name:"), 0, 0)
        layout.addWidget(self.project_name_edit, 0, 1)
        layout.addLayout(controls_bar, 0, 2)
        layout.addWidget(QLabel("Tracked Projects:"), 1, 0)
        layout.addWidget(self.tracked_projects_list, 1, 1, 2, 1)
        layout.addWidget(self.project_path_label, 1, 2)

        return group

    def _build_source_files_group(self) -> QGroupBox:
        group = QGroupBox("Source Files")
        layout = QVBoxLayout(group)

        self.current_folder_label = QLabel("Current folder: -")
        self.current_folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.current_folder_label)

        splitter = QSplitter(Qt.Horizontal)

        source_panel = QWidget()
        source_layout = QVBoxLayout(source_panel)
        source_layout.addWidget(QLabel("Tracked Source Directories"))
        self.source_roots_list = QListWidget()
        self.source_roots_list.currentItemChanged.connect(self._on_source_root_changed)
        source_layout.addWidget(self.source_roots_list)

        source_button_bar = QHBoxLayout()
        add_source_btn = QPushButton("Track Dir")
        add_source_btn.clicked.connect(self._add_source_directory)
        remove_source_btn = QPushButton("Untrack Dir")
        remove_source_btn.clicked.connect(self._remove_source_directory)
        source_button_bar.addWidget(add_source_btn)
        source_button_bar.addWidget(remove_source_btn)
        source_layout.addLayout(source_button_bar)

        source_layout.addWidget(QLabel("Directory Browser"))
        self.directory_model = QFileSystemModel()
        self.directory_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.directory_model.setRootPath("")
        self.directory_tree = QTreeView()
        self.directory_tree.setModel(self.directory_model)
        self.directory_tree.clicked.connect(self._on_directory_selected)
        for column in range(1, 4):
            self.directory_tree.hideColumn(column)
        source_layout.addWidget(self.directory_tree, stretch=1)

        files_panel = QWidget()
        files_layout = QVBoxLayout(files_panel)
        files_layout.addWidget(QLabel("Files"))
        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.files_list.itemSelectionChanged.connect(self._refresh_selected_file_history)
        self.files_list.itemDoubleClicked.connect(self._open_source_item)
        files_layout.addWidget(self.files_list, stretch=1)

        file_button_bar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_source_files)
        checkout_btn = QPushButton("Check Out Selected")
        checkout_btn.clicked.connect(self._checkout_selected)
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self._open_selected_source_files)
        add_new_btn = QPushButton("Add Local File(s) To Here")
        add_new_btn.clicked.connect(self._add_new_files_to_source)
        file_button_bar.addWidget(refresh_btn)
        file_button_bar.addWidget(checkout_btn)
        file_button_bar.addWidget(open_btn)
        file_button_bar.addWidget(add_new_btn)
        file_button_bar.addStretch()
        files_layout.addLayout(file_button_bar)

        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        history_layout.addWidget(QLabel("Document History"))
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(
            ["Timestamp", "Action", "Initials", "Full Name"]
        )
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QTableWidget.NoSelection)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        history_layout.addWidget(self.history_table, stretch=1)

        splitter.addWidget(source_panel)
        splitter.addWidget(files_panel)
        splitter.addWidget(history_panel)
        splitter.setSizes([280, 420, 420])

        layout.addWidget(splitter, stretch=1)
        return group

    def _build_checked_out_group(self) -> QGroupBox:
        group = QGroupBox("Checked Out Files")
        layout = QVBoxLayout(group)

        self.records_tabs = QTabWidget()
        self.all_records_table = self._build_records_table()
        self.project_records_table = self._build_records_table()
        self.records_tabs.addTab(self.all_records_table, "All Checked Out")
        self.records_tabs.addTab(self.project_records_table, "Current Project")
        layout.addWidget(self.records_tabs)

        button_bar = QHBoxLayout()
        checkin_btn = QPushButton("Check In Selected")
        checkin_btn.clicked.connect(self._checkin_selected)
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self._open_selected_record_files)
        button_bar.addWidget(checkin_btn)
        button_bar.addWidget(open_btn)
        button_bar.addStretch()
        layout.addLayout(button_bar)

        return group

    def _build_records_table(self) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Source", "Locked", "Local", "Initials"])
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.cellDoubleClicked.connect(self._open_record_row)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _default_projects_dir(self) -> Path:
        return APP_ROOT / "Projects"

    def _base_projects_dir(self) -> Path:
        return Path(self.local_path_edit.text().strip() or self._default_projects_dir())

    def _normalize_initials(self) -> str:
        initials = "".join(ch for ch in self.initials_edit.text().strip().upper() if ch.isalnum())
        self.initials_edit.setText(initials)
        return initials

    def _current_full_name(self) -> str:
        full_name = self.full_name_edit.text().strip()
        self.full_name_edit.setText(full_name)
        return full_name

    def _ensure_base_projects_dir(self) -> Path:
        base_dir = self._base_projects_dir()
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _project_config_path(self, project_dir: Path) -> Path:
        return project_dir / PROJECT_CONFIG_FILE

    def _current_project_path(self) -> Optional[Path]:
        return Path(self.current_project_dir) if self.current_project_dir else None

    def _current_project_name(self) -> str:
        return self.project_name_edit.text().strip() or DEFAULT_PROJECT_NAME

    def _safe_project_dir_name(self, name: str) -> str:
        safe = name.strip().replace("/", "-").replace("\\", "-")
        return safe or DEFAULT_PROJECT_NAME

    def _current_source_root(self) -> Optional[Path]:
        item = self.source_roots_list.currentItem()
        if not item:
            return None
        return Path(item.data(Qt.UserRole))

    def _active_records_table(self) -> QTableWidget:
        return self.records_tabs.currentWidget()  # type: ignore[return-value]

    def _choose_local_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Base Projects Folder",
            str(self._base_projects_dir()),
        )
        if path:
            self.local_path_edit.setText(path)
            self._save_settings()
            if not self.tracked_projects:
                self._ensure_default_project()

    def _validate_identity(self) -> bool:
        if not self._normalize_initials():
            self._error("Enter user initials.")
            return False
        self._current_full_name()
        return True

    def _validate_current_project(self) -> Optional[Path]:
        project_dir = self._current_project_path()
        if not project_dir or not project_dir.is_dir():
            self._error("Load or save a project first.")
            return None
        return project_dir

    def _validate_current_directory(self) -> Optional[Path]:
        if not self.current_directory or not self.current_directory.is_dir():
            self._error("Select a source directory first.")
            return None
        return self.current_directory

    def _settings_payload(self) -> Dict[str, str]:
        return {
            "initials": self._normalize_initials(),
            "full_name": self._current_full_name(),
            "base_projects_dir": str(self._base_projects_dir()),
            "current_project_dir": self.current_project_dir,
        }

    def _load_settings(self) -> None:
        self.local_path_edit.setText(str(self._default_projects_dir()))
        if not SETTINGS_FILE.exists():
            return

        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return

        self.initials_edit.setText(str(data.get("initials", "")).strip())
        self.full_name_edit.setText(str(data.get("full_name", "")).strip())
        base_dir = str(data.get("base_projects_dir", "")).strip()
        if base_dir:
            self.local_path_edit.setText(base_dir)
        self.current_project_dir = str(data.get("current_project_dir", "")).strip()

    def _save_settings(self) -> None:
        SETTINGS_FILE.write_text(
            json.dumps(self._settings_payload(), indent=2), encoding="utf-8"
        )

    def _load_tracked_projects(self) -> None:
        self.tracked_projects = []
        if PROJECTS_FILE.exists():
            try:
                data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
                tracked = data.get("tracked_projects", [])
                if isinstance(tracked, list):
                    for entry in tracked:
                        if not isinstance(entry, dict):
                            continue
                        name = str(entry.get("name", "")).strip()
                        project_dir = str(entry.get("project_dir", "")).strip()
                        if name and project_dir:
                            self.tracked_projects.append(
                                {"name": name, "project_dir": project_dir}
                            )
            except (OSError, ValueError, TypeError):
                self.tracked_projects = []

        if not self.tracked_projects:
            self._ensure_default_project()
        else:
            self._refresh_tracked_projects_list()

    def _save_tracked_projects(self) -> None:
        payload = {"tracked_projects": self.tracked_projects}
        PROJECTS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _project_payload(self, name: str, sources: List[str]) -> Dict[str, object]:
        return {"name": name, "sources": sources}

    def _read_project_config(self, project_dir: Path) -> Dict[str, object]:
        config_path = self._project_config_path(project_dir)
        if not config_path.exists():
            return self._project_payload(project_dir.name, [])

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self._project_payload(project_dir.name, [])

        name = str(data.get("name", project_dir.name)).strip() or project_dir.name
        raw_sources = data.get("sources", [])
        sources = [str(item) for item in raw_sources if str(item).strip()] if isinstance(raw_sources, list) else []
        return self._project_payload(name, sources)

    def _write_project_config(self, project_dir: Path, name: str, sources: List[str]) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._project_config_path(project_dir)
        payload = self._project_payload(name, sources)
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _ensure_default_project(self) -> None:
        base_dir = self._ensure_base_projects_dir()
        default_dir = base_dir / DEFAULT_PROJECT_NAME
        if not self._project_config_path(default_dir).exists():
            self._write_project_config(default_dir, DEFAULT_PROJECT_NAME, [])
        self._register_tracked_project(DEFAULT_PROJECT_NAME, default_dir)
        self._refresh_tracked_projects_list()

    def _register_tracked_project(self, name: str, project_dir: Path) -> None:
        project_dir_str = str(project_dir)
        updated = False
        for entry in self.tracked_projects:
            if entry["project_dir"] == project_dir_str:
                entry["name"] = name
                updated = True
                break

        if not updated:
            self.tracked_projects.append({"name": name, "project_dir": project_dir_str})

        self.tracked_projects.sort(key=lambda item: item["name"].lower())
        self._save_tracked_projects()
        self._refresh_tracked_projects_list()

    def _refresh_tracked_projects_list(self) -> None:
        self.tracked_projects_list.clear()
        current_item = None
        for entry in self.tracked_projects:
            item = QListWidgetItem(entry["name"])
            item.setData(Qt.UserRole, entry["project_dir"])
            item.setToolTip(entry["project_dir"])
            self.tracked_projects_list.addItem(item)
            if entry["project_dir"] == self.current_project_dir:
                current_item = item

        if current_item:
            self.tracked_projects_list.setCurrentItem(current_item)
        elif self.tracked_projects_list.count() > 0:
            self.tracked_projects_list.setCurrentRow(0)

    def _load_last_or_default_project(self) -> None:
        if self.current_project_dir:
            project_dir = Path(self.current_project_dir)
            if project_dir.is_dir():
                self._load_project_from_dir(project_dir)
                return

        item = self.tracked_projects_list.item(0)
        if item:
            self._load_project_from_dir(Path(item.data(Qt.UserRole)))

    def _save_project_from_inputs(self) -> None:
        base_dir = self._ensure_base_projects_dir()
        name = self.project_name_edit.text().strip()
        if not name:
            self._error("Project name is required.")
            return

        current_dir = self._current_project_path()
        if current_dir and current_dir.is_dir() and self._read_project_config(current_dir).get("name") == name:
            project_dir = current_dir
        else:
            project_dir = base_dir / self._safe_project_dir_name(name)

        sources = self._source_roots_from_list()
        self._write_project_config(project_dir, name, sources)
        self.current_project_dir = str(project_dir)
        self.project_path_label.setText(f"Config: {self._project_config_path(project_dir)}")
        self._register_tracked_project(name, project_dir)
        self._save_settings()
        self._info(f"Project '{name}' saved.")

    def _source_roots_from_list(self) -> List[str]:
        roots: List[str] = []
        for row in range(self.source_roots_list.count()):
            item = self.source_roots_list.item(row)
            roots.append(str(item.data(Qt.UserRole)))
        return roots

    def _load_selected_tracked_project(self) -> None:
        item = self.tracked_projects_list.currentItem()
        if not item:
            self._error("Select a tracked project to load.")
            return
        self._load_project_from_dir(Path(item.data(Qt.UserRole)))

    def _add_existing_project(self) -> None:
        start_dir = str(self._base_projects_dir())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Project Config",
            start_dir,
            "Document Control Project (dctl.json)",
        )
        if not file_path:
            return

        config_path = Path(file_path)
        if config_path.name != PROJECT_CONFIG_FILE:
            self._error("Select a dctl.json project file.")
            return

        project_dir = config_path.parent
        config = self._read_project_config(project_dir)
        self._register_tracked_project(str(config.get("name", project_dir.name)), project_dir)
        self._load_project_from_dir(project_dir)

    def _remove_selected_project(self) -> None:
        item = self.tracked_projects_list.currentItem()
        if not item:
            self._error("Select a tracked project to remove.")
            return

        project_dir = str(item.data(Qt.UserRole))
        self.tracked_projects = [
            entry for entry in self.tracked_projects if entry["project_dir"] != project_dir
        ]
        if not self.tracked_projects:
            self.current_project_dir = ""
            self._ensure_default_project()
            self._load_last_or_default_project()
        else:
            if self.current_project_dir == project_dir:
                self.current_project_dir = self.tracked_projects[0]["project_dir"]
                self._load_project_from_dir(Path(self.current_project_dir))
            self._save_tracked_projects()
            self._refresh_tracked_projects_list()
            self._save_settings()

    def _load_project_from_dir(self, project_dir: Path) -> None:
        config = self._read_project_config(project_dir)
        name = str(config.get("name", project_dir.name))
        sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]

        self.current_project_dir = str(project_dir)
        self.project_name_edit.setText(name)
        self.project_path_label.setText(f"Config: {self._project_config_path(project_dir)}")
        self._register_tracked_project(name, project_dir)
        self._refresh_source_roots(sources)
        self._save_settings()
        self._render_records_tables()

    def _refresh_source_roots(self, sources: List[str]) -> None:
        self.source_roots_list.clear()
        valid_sources = [Path(source) for source in sources if Path(source).is_dir()]
        for source in valid_sources:
            item = QListWidgetItem(source.name or str(source))
            item.setData(Qt.UserRole, str(source))
            item.setToolTip(str(source))
            self.source_roots_list.addItem(item)

        if self.source_roots_list.count() > 0:
            self.source_roots_list.setCurrentRow(0)
        else:
            self.current_directory = None
            self.current_folder_label.setText("Current folder: -")
            self.files_list.clear()
            self.history_table.setRowCount(0)
            self.directory_tree.setRootIndex(self.directory_model.index(""))

    def _on_source_root_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        root_path = Path(str(current.data(Qt.UserRole)))
        model_index = self.directory_model.index(str(root_path))
        self.directory_tree.setRootIndex(model_index)
        self.directory_tree.setCurrentIndex(model_index)
        self._set_current_directory(root_path)

    def _set_current_directory(self, directory: Path) -> None:
        self.current_directory = directory
        self.current_folder_label.setText(f"Current folder: {directory}")
        self._refresh_source_files()

    def _on_directory_selected(self, index) -> None:  # type: ignore[no-untyped-def]
        path = Path(self.directory_model.filePath(index))
        if path.is_dir():
            self._set_current_directory(path)

    def _refresh_source_files(self) -> None:
        self.files_list.clear()
        if not self.current_directory or not self.current_directory.is_dir():
            return

        for item in sorted(self.current_directory.iterdir()):
            if item.is_file() and item.name != HISTORY_FILE_NAME:
                list_item = QListWidgetItem(item.name)
                list_item.setData(Qt.UserRole, str(item))
                list_item.setToolTip(str(item))
                self.files_list.addItem(list_item)

        self._refresh_selected_file_history()

    def _add_source_directory(self) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return

        start_dir = str(self._current_source_root() or Path.home())
        path = QFileDialog.getExistingDirectory(self, "Track Source Directory", start_dir)
        if not path:
            return

        source_path = Path(path)
        sources = self._source_roots_from_list()
        if str(source_path) not in sources:
            sources.append(str(source_path))
            self._write_project_config(project_dir, self._current_project_name(), sources)
            self._refresh_source_roots(sources)
            self._save_settings()

    def _remove_source_directory(self) -> None:
        project_dir = self._validate_current_project()
        item = self.source_roots_list.currentItem()
        if not project_dir or not item:
            self._error("Select a tracked source directory to remove.")
            return

        source_path = str(item.data(Qt.UserRole))
        sources = [source for source in self._source_roots_from_list() if source != source_path]
        self._write_project_config(project_dir, self._current_project_name(), sources)
        self._refresh_source_roots(sources)
        self._save_settings()

    def _selected_source_file_paths(self) -> List[Path]:
        return [Path(item.data(Qt.UserRole)) for item in self.files_list.selectedItems()]

    def _source_key(self, source_root: Path) -> str:
        raw = str(source_root.resolve())
        cleaned = raw.replace(":", "").replace("\\", "_").replace("/", "_")
        return cleaned.strip("_") or "source"

    def _locked_name_for(self, source_file: Path, initials: str) -> Path:
        return source_file.with_name(f"{source_file.stem}-{initials}{source_file.suffix}")

    def _append_history(self, source_dir: Path, action: str, file_name: str) -> None:
        history_file = source_dir / HISTORY_FILE_NAME
        if not history_file.exists():
            with history_file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["timestamp", "action", "file_name", "user_initials", "user_full_name"]
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
                ]
            )

    def _checkout_selected(self) -> None:
        if not self._validate_identity():
            return

        project_dir = self._validate_current_project()
        current_directory = self._validate_current_directory()
        source_root = self._current_source_root()
        if not project_dir or not current_directory or not source_root:
            return

        selected_files = self._selected_source_file_paths()
        if not selected_files:
            self._error("Select at least one file to check out.")
            return

        initials = self._normalize_initials()
        project_checkout_dir = project_dir / "checked_out" / self._source_key(source_root)
        errors: List[str] = []

        for source_file in selected_files:
            locked_source_file = self._locked_name_for(source_file, initials)
            try:
                relative_path = source_file.relative_to(source_root)
            except ValueError:
                relative_path = Path(source_file.name)
            local_file = project_checkout_dir / relative_path

            if not source_file.exists():
                errors.append(f"Missing source file: {source_file.name}")
                continue
            if locked_source_file.exists():
                errors.append(f"Already checked out: {locked_source_file.name}")
                continue

            try:
                local_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, local_file)
                source_file.rename(locked_source_file)
                self.records.append(
                    CheckoutRecord(
                        source_file=str(source_file),
                        locked_source_file=str(locked_source_file),
                        local_file=str(local_file),
                        initials=initials,
                        project_name=self._current_project_name(),
                        project_dir=str(project_dir),
                        source_root=str(source_root),
                    )
                )
                self._append_history(source_file.parent, "CHECK_OUT", source_file.name)
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")

        self._save_records()
        self._refresh_source_files()
        self._render_records_tables()

        if errors:
            self._error("Some files failed:\n" + "\n".join(errors))
        else:
            self._info("Checkout complete.")

    def _selected_record_indexes(self) -> List[int]:
        table = self._active_records_table()
        indexes = []
        for row in sorted({idx.row() for idx in table.selectedIndexes()}):
            item = table.item(row, 0)
            if item is None:
                continue
            record_idx = item.data(Qt.UserRole)
            if isinstance(record_idx, int):
                indexes.append(record_idx)
        return indexes

    def _checkin_selected(self) -> None:
        if not self._validate_identity():
            return

        selected_indexes = set(self._selected_record_indexes())
        if not selected_indexes:
            self._error("Select at least one checked-out row to check in.")
            return

        errors: List[str] = []
        remaining: List[CheckoutRecord] = []

        for record_idx, record in enumerate(self.records):
            if record_idx not in selected_indexes:
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
                shutil.copy2(local_file, locked_source_file)
                locked_source_file.replace(source_file)
                self._append_history(source_file.parent, "CHECK_IN", source_file.name)
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")
                remaining.append(record)

        self.records = remaining
        self._save_records()
        self._refresh_source_files()
        self._render_records_tables()

        if errors:
            self._error("Some files failed to check in:\n" + "\n".join(errors))
        else:
            self._info("Check-in complete.")

    def _add_new_files_to_source(self) -> None:
        if not self._validate_identity():
            return

        current_directory = self._validate_current_directory()
        project_dir = self._validate_current_project()
        if not current_directory or not project_dir:
            return

        start_dir = str(project_dir)
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
            target_file = current_directory / local_file.name
            if target_file.exists():
                errors.append(f"Already exists in source: {target_file.name}")
                continue

            try:
                shutil.copy2(local_file, target_file)
                self._append_history(current_directory, "ADD_FILE", target_file.name)
            except OSError as exc:
                errors.append(f"{local_file.name}: {exc}")

        self._refresh_source_files()

        if errors:
            self._error("Some files failed to add:\n" + "\n".join(errors))
        else:
            self._info("File(s) added to source folder.")

    def _open_source_item(self, item: QListWidgetItem) -> None:
        self._open_paths([Path(item.data(Qt.UserRole))])

    def _open_selected_source_files(self) -> None:
        selected_files = self._selected_source_file_paths()
        if not selected_files:
            self._error("Select at least one source file to open.")
            return
        self._open_paths(selected_files)

    def _open_record_row(self, row: int, _column: int) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        item = table.item(row, 0)
        if not item:
            return
        record_idx = item.data(Qt.UserRole)
        if isinstance(record_idx, int) and 0 <= record_idx < len(self.records):
            self._open_paths([Path(self.records[record_idx].local_file)])

    def _open_selected_record_files(self) -> None:
        indexes = self._selected_record_indexes()
        if not indexes:
            self._error("Select at least one checked-out file to open.")
            return
        paths = [Path(self.records[idx].local_file) for idx in indexes if 0 <= idx < len(self.records)]
        self._open_paths(paths)

    def _open_paths(self, paths: List[Path]) -> None:
        errors: List[str] = []
        for path in paths:
            if not path.exists():
                errors.append(f"Missing file: {path}")
                continue
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                errors.append(f"Could not open: {path}")
        if errors:
            self._error("Some files could not be opened:\n" + "\n".join(errors))

    def _refresh_selected_file_history(self) -> None:
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            self.history_table.setRowCount(0)
            return

        file_path = Path(selected_items[0].data(Qt.UserRole))
        history_file = file_path.parent / HISTORY_FILE_NAME
        rows: List[List[str]] = []
        if history_file.exists():
            try:
                with history_file.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        if row.get("file_name") == file_path.name:
                            rows.append(
                                [
                                    row.get("timestamp", ""),
                                    row.get("action", ""),
                                    row.get("user_initials", ""),
                                    row.get("user_full_name", ""),
                                ]
                            )
            except OSError:
                rows = []

        rows.reverse()
        self.history_table.setRowCount(len(rows))
        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                self.history_table.setItem(row_idx, col_idx, QTableWidgetItem(value))

    def _short_path(self, raw_path: str) -> str:
        path = Path(raw_path)
        parts = path.parts
        if len(parts) <= 3:
            return raw_path

        sep = "\\" if "\\" in raw_path else "/"
        anchor = path.anchor.rstrip("\\/")
        if anchor:
            return anchor + sep + ".." + sep + sep.join(parts[-2:])
        return ".." + sep + sep.join(parts[-2:])

    def _render_records_tables(self) -> None:
        self._populate_records_table(self.all_records_table, list(enumerate(self.records)))
        current_project = self.current_project_dir
        filtered = [
            (idx, record)
            for idx, record in enumerate(self.records)
            if record.project_dir == current_project
        ]
        self._populate_records_table(self.project_records_table, filtered)

    def _populate_records_table(
        self, table: QTableWidget, items: List[tuple[int, CheckoutRecord]]
    ) -> None:
        table.setRowCount(len(items))
        for row_idx, (record_idx, record) in enumerate(items):
            values = [
                record.source_file,
                record.locked_source_file,
                record.local_file,
                record.initials,
            ]
            for col_idx, value in enumerate(values):
                display_value = self._short_path(value) if col_idx < 3 else value
                item = QTableWidgetItem(display_value)
                item.setToolTip(value)
                if col_idx == 0:
                    item.setData(Qt.UserRole, record_idx)
                table.setItem(row_idx, col_idx, item)

    def _load_records(self) -> None:
        if not RECORDS_FILE.exists():
            self._render_records_tables()
            return

        try:
            data = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
            self.records = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                self.records.append(
                    CheckoutRecord(
                        source_file=str(entry.get("source_file", "")),
                        locked_source_file=str(entry.get("locked_source_file", "")),
                        local_file=str(entry.get("local_file", "")),
                        initials=str(entry.get("initials", "")),
                        project_name=str(entry.get("project_name", "")),
                        project_dir=str(entry.get("project_dir", "")),
                        source_root=str(entry.get("source_root", "")),
                    )
                )
        except (OSError, ValueError, TypeError):
            self.records = []

        self._render_records_tables()

    def _save_records(self) -> None:
        RECORDS_FILE.write_text(
            json.dumps([asdict(record) for record in self.records], indent=2),
            encoding="utf-8",
        )

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def _info(self, message: str) -> None:
        QMessageBox.information(self, "Info", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        self._save_tracked_projects()
        self._save_records()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = DocumentControlApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

import csv
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from PySide6.QtCore import QDir, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
    QPlainTextEdit,
    QRadioButton,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = APP_ROOT / "settings.json"
PROJECTS_FILE = APP_ROOT / "projects.json"
RECORDS_FILE = APP_ROOT / ".checkout_records.json"
FILTER_PRESETS_FILE = APP_ROOT / "filter_presets.json"
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
    checked_out_at: str = ""


@dataclass
class PendingCheckinAction:
    file_name: str
    source_file: str
    locked_source_file: str
    action_mode: str
    local_file: str = ""
    record_idx: int = -1
    reason: str = ""


class DocumentControlApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Document Control")
        self.resize(1500, 980)

        self.records: List[CheckoutRecord] = []
        self.tracked_projects: List[Dict[str, str]] = []
        self.current_project_dir: str = ""
        self.current_directory: Optional[Path] = None
        self.directory_tree_root: Optional[Path] = None
        self.show_configuration_tab_on_startup = True
        self.filter_presets: List[Dict[str, object]] = []
        self.extension_filter_debounce = QTimer(self)
        self.extension_filter_debounce.setSingleShot(True)
        self.extension_filter_debounce.setInterval(2000)
        self.extension_filter_debounce.timeout.connect(self._apply_debounced_extension_filters)

        self._build_ui()
        self._load_filter_presets()
        self._load_settings()
        self._load_tracked_projects()
        self._load_records()
        self._load_last_or_default_project()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.main_tabs = QTabWidget()

        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        self.projects_section = self._build_collapsible_section("Projects", self._build_projects_group())
        self.source_files_section = self._build_collapsible_section(
            "Source Files", self._build_source_files_group()
        )
        main_layout.addWidget(self.projects_section, stretch=1)
        main_layout.addWidget(self.source_files_section, stretch=1)

        configuration_tab = QWidget()
        configuration_layout = QVBoxLayout(configuration_tab)
        configuration_layout.addWidget(self._build_configuration_group())
        configuration_layout.addStretch()

        checked_out_tab = QWidget()
        checked_out_layout = QVBoxLayout(checked_out_tab)
        checked_out_layout.addWidget(self._build_checked_out_group(), stretch=1)

        self.main_tabs.addTab(main_tab, "Main")
        self.main_tabs.addTab(checked_out_tab, "Checked Out Files")
        self.main_tabs.addTab(configuration_tab, "Configuration")

        layout.addWidget(self.main_tabs)

    def _build_collapsible_section(self, title: str, content: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toggle = QToolButton()
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.DownArrow)
        toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def _toggle_section(checked: bool) -> None:
            content.setVisible(checked)
            toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            if checked:
                content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            else:
                content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            content.updateGeometry()
            container.updateGeometry()

        toggle.toggled.connect(_toggle_section)

        layout.addWidget(toggle)
        layout.addWidget(content, stretch=1)
        return container

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
        layout = QVBoxLayout(group)

        new_project_btn = QPushButton("New Project")
        new_project_btn.clicked.connect(self._show_new_project_dialog)
        load_project_btn = QPushButton("Load Selected")
        load_project_btn.clicked.connect(self._load_selected_tracked_project)
        add_project_btn = QPushButton("Track Existing")
        add_project_btn.clicked.connect(self._add_existing_project)
        remove_project_btn = QPushButton("Untrack Selected")
        remove_project_btn.clicked.connect(self._remove_selected_project)
        open_location_btn = QPushButton("Open Location")
        open_location_btn.clicked.connect(self._open_selected_project_location)

        self.tracked_projects_list = QListWidget()
        self.tracked_projects_list.itemDoubleClicked.connect(
            lambda item: self._load_project_from_dir(Path(str(item.data(Qt.UserRole))))
        )

        self.current_project_label = QLabel("Current Project: -")
        self.current_project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        tracked_panel = QWidget()
        tracked_layout = QVBoxLayout(tracked_panel)
        tracked_layout.addWidget(QLabel("Tracked Projects"))
        tracked_layout.addWidget(self.tracked_projects_list, stretch=1)

        tracked_controls = QGridLayout()
        tracked_controls.addWidget(new_project_btn, 0, 0)
        tracked_controls.addWidget(load_project_btn, 0, 1)
        tracked_controls.addWidget(add_project_btn, 1, 0)
        tracked_controls.addWidget(remove_project_btn, 1, 1)
        tracked_controls.addWidget(open_location_btn, 2, 0, 1, 2)
        tracked_layout.addLayout(tracked_controls)

        favorites_panel = QWidget()
        favorites_layout = QVBoxLayout(favorites_panel)
        favorites_layout.addWidget(QLabel("Favorite Files"))
        self.favorites_list = QListWidget()
        self.favorites_list.itemDoubleClicked.connect(self._open_favorite_item)
        favorites_layout.addWidget(self.favorites_list, stretch=1)
        favorites_controls = QGridLayout()
        add_favorite_btn = QPushButton("Add Favorite")
        add_favorite_btn.clicked.connect(self._browse_and_add_favorites)
        remove_favorite_btn = QPushButton("Remove Favorite")
        remove_favorite_btn.clicked.connect(self._remove_selected_favorites)
        open_favorite_btn = QPushButton("Open Selected")
        open_favorite_btn.clicked.connect(self._open_selected_favorites)
        favorites_controls.addWidget(add_favorite_btn, 0, 0)
        favorites_controls.addWidget(remove_favorite_btn, 0, 1)
        favorites_controls.addWidget(open_favorite_btn, 1, 0, 1, 2)
        favorites_layout.addLayout(favorites_controls)

        notes_panel = QWidget()
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.addWidget(QLabel("Notes"))
        self.notes_list = QListWidget()
        self.notes_list.itemDoubleClicked.connect(self._edit_note_item)
        notes_layout.addWidget(self.notes_list, stretch=1)
        notes_controls = QGridLayout()
        new_note_btn = QPushButton("New Note")
        new_note_btn.clicked.connect(self._create_note)
        edit_note_btn = QPushButton("Edit Note")
        edit_note_btn.clicked.connect(self._edit_selected_note)
        remove_note_btn = QPushButton("Remove Note")
        remove_note_btn.clicked.connect(self._remove_selected_note)
        notes_controls.addWidget(new_note_btn, 0, 0)
        notes_controls.addWidget(edit_note_btn, 0, 1)
        notes_controls.addWidget(remove_note_btn, 1, 0, 1, 2)
        notes_layout.addLayout(notes_controls)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.addWidget(tracked_panel)
        content_splitter.addWidget(favorites_panel)
        content_splitter.addWidget(notes_panel)
        content_splitter.setSizes([280, 320, 320])

        layout.addWidget(self.current_project_label)
        layout.addWidget(content_splitter, stretch=1)

        return group

    def _build_source_files_group(self) -> QGroupBox:
        group = QGroupBox("Source Files")
        layout = QVBoxLayout(group)

        self.current_folder_label = QLabel("Current folder: -")
        self.current_folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.current_folder_label)

        splitter = QSplitter(Qt.Horizontal)

        tracked_panel = QWidget()
        tracked_layout = QVBoxLayout(tracked_panel)
        tracked_layout.addWidget(QLabel("Tracked Source Directories"))
        self.source_roots_list = QListWidget()
        self.source_roots_list.currentItemChanged.connect(self._on_source_root_changed)
        self.source_roots_list.setMinimumWidth(220)
        tracked_layout.addWidget(self.source_roots_list)

        source_button_bar = QHBoxLayout()
        add_source_btn = QPushButton("Track Dir (Browse)")
        add_source_btn.clicked.connect(self._add_source_directory)
        remove_source_btn = QPushButton("Untrack Dir")
        remove_source_btn.clicked.connect(self._remove_source_directory)
        source_button_bar.addWidget(add_source_btn)
        source_button_bar.addWidget(remove_source_btn)
        tracked_layout.addLayout(source_button_bar)

        directory_panel = QWidget()
        directory_layout = QVBoxLayout(directory_panel)
        directory_layout.addWidget(QLabel("Directory Browser"))
        self.directory_tree = QTreeWidget()
        self.directory_tree.setColumnCount(1)
        self.directory_tree.setHeaderHidden(True)
        self.directory_tree.itemExpanded.connect(self._on_tree_item_expanded)
        self.directory_tree.itemClicked.connect(self._on_directory_selected)
        self.directory_tree.setAnimated(False)
        self.directory_tree.setUniformRowHeights(True)
        self.directory_tree.setMinimumWidth(300)
        self.directory_tree.setMinimumHeight(260)
        directory_layout.addWidget(self.directory_tree, stretch=1)
        directory_button_bar = QHBoxLayout()
        browse_directory_btn = QPushButton("Browse")
        browse_directory_btn.clicked.connect(self._browse_directory_tree_root)
        view_directory_btn = QPushButton("View Location")
        view_directory_btn.clicked.connect(self._view_current_directory_location)
        track_current_directory_btn = QPushButton("Track Directory")
        track_current_directory_btn.clicked.connect(self._track_current_directory)
        directory_button_bar.addWidget(browse_directory_btn)
        directory_button_bar.addWidget(view_directory_btn)
        directory_button_bar.addWidget(track_current_directory_btn)
        directory_button_bar.addStretch()
        directory_layout.addLayout(directory_button_bar)

        files_panel = QWidget()
        files_layout = QVBoxLayout(files_panel)
        files_layout.addWidget(QLabel("Files"))

        filter_bar = QHBoxLayout()
        presets_btn = QPushButton("Presets")
        presets_btn.clicked.connect(self._show_filter_presets_dialog)
        self.file_filter_mode_combo = QComboBox()
        self.file_filter_mode_combo.addItems(["No Filter", "Include Only", "Exclude"])
        self.file_filter_mode_combo.currentIndexChanged.connect(self._on_filter_mode_changed)

        self.file_extension_list_edit = QLineEdit()
        self.file_extension_list_edit.setPlaceholderText(".dwg, .pdf, .xlsx")
        self.file_extension_list_edit.textChanged.connect(self._on_extension_list_changed)

        self.file_extension_combo = QComboBox()
        self.file_extension_combo.setEditable(True)
        self.file_extension_combo.addItems(
            [
                ".dwg",
                ".dxf",
                ".pdf",
                ".xlsx",
                ".xls",
                ".doc",
                ".docx",
                ".txt",
                ".csv",
                ".png",
                ".jpg",
                ".jpeg",
                ".zip",
            ]
        )
        self.file_extension_combo.currentTextChanged.connect(self._refresh_source_files)

        add_extension_btn = QPushButton("Add")
        add_extension_btn.clicked.connect(self._add_filter_extension)
        remove_extension_btn = QPushButton("Remove")
        remove_extension_btn.clicked.connect(self._remove_filter_extension)
        clear_extensions_btn = QPushButton("Clear")
        clear_extensions_btn.clicked.connect(self._clear_filter_extensions)

        filter_bar.addWidget(QLabel("Extension Filter"))
        filter_bar.addWidget(presets_btn)
        filter_bar.addWidget(self.file_extension_combo)
        filter_bar.addWidget(add_extension_btn)
        filter_bar.addWidget(remove_extension_btn)
        filter_bar.addWidget(clear_extensions_btn)
        files_layout.addLayout(filter_bar)
        extension_list_bar = QHBoxLayout()
        extension_list_bar.addWidget(QLabel("Filter Mode"))
        extension_list_bar.addWidget(self.file_filter_mode_combo)
        extension_list_bar.addWidget(self.file_extension_list_edit, stretch=1)
        files_layout.addLayout(extension_list_bar)

        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.files_list.itemDoubleClicked.connect(self._open_source_item)
        files_layout.addWidget(self.files_list, stretch=1)

        file_button_bar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_source_files)
        checkout_btn = QPushButton("Check Out Selected")
        checkout_btn.clicked.connect(self._checkout_selected)
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self._open_selected_source_files)
        view_history_btn = QPushButton("View History")
        view_history_btn.clicked.connect(self._show_selected_file_history)
        add_to_favorites_btn = QPushButton("Add Selected To Favorites")
        add_to_favorites_btn.clicked.connect(self._add_selected_source_files_to_favorites)
        add_new_btn = QPushButton("Add Local File(s) To Here")
        add_new_btn.clicked.connect(self._add_new_files_to_source)
        file_button_bar.addWidget(refresh_btn)
        file_button_bar.addWidget(checkout_btn)
        file_button_bar.addWidget(open_btn)
        file_button_bar.addWidget(view_history_btn)
        file_button_bar.addWidget(add_to_favorites_btn)
        file_button_bar.addWidget(add_new_btn)
        file_button_bar.addStretch()
        files_layout.addLayout(file_button_bar)

        controlled_panel = QWidget()
        controlled_layout = QVBoxLayout(controlled_panel)
        controlled_layout.addWidget(QLabel("Directory's Controlled Files"))
        self.controlled_files_list = QListWidget()
        self.controlled_files_list.setSelectionMode(QListWidget.ExtendedSelection)
        controlled_layout.addWidget(self.controlled_files_list, stretch=1)

        controlled_button_bar = QHBoxLayout()
        refresh_controlled_btn = QPushButton("Refresh")
        refresh_controlled_btn.clicked.connect(self._refresh_controlled_files)
        force_checkin_btn = QPushButton("Force Check In")
        force_checkin_btn.clicked.connect(self._force_checkin_selected)
        controlled_button_bar.addWidget(refresh_controlled_btn)
        controlled_button_bar.addWidget(force_checkin_btn)
        controlled_button_bar.addStretch()
        controlled_layout.addLayout(controlled_button_bar)

        splitter.addWidget(tracked_panel)
        splitter.addWidget(directory_panel)
        splitter.addWidget(files_panel)
        splitter.addWidget(controlled_panel)
        splitter.setSizes([220, 320, 420, 300])

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
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ["Source", "Locked", "Local", "Initials", "Project", "Checked Out"]
        )
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.cellDoubleClicked.connect(self._open_record_row)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
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
        project_dir = self._current_project_path()
        if not project_dir or not project_dir.is_dir():
            return DEFAULT_PROJECT_NAME
        return str(self._read_project_config(project_dir).get("name", DEFAULT_PROJECT_NAME)).strip() or DEFAULT_PROJECT_NAME

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

    def _has_user_configuration(self) -> bool:
        initials = self.initials_edit.text().strip()
        full_name = self.full_name_edit.text().strip()
        base_dir = self.local_path_edit.text().strip()
        return bool(
            initials
            or full_name
            or (base_dir and Path(base_dir) != self._default_projects_dir())
        )

    def _apply_startup_tab(self) -> None:
        self.main_tabs.setCurrentIndex(1 if self.show_configuration_tab_on_startup else 0)

    def _load_settings(self) -> None:
        self.local_path_edit.setText(str(self._default_projects_dir()))
        if not SETTINGS_FILE.exists():
            self.show_configuration_tab_on_startup = True
            self._apply_startup_tab()
            return

        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self.show_configuration_tab_on_startup = True
            self._apply_startup_tab()
            return

        self.initials_edit.setText(str(data.get("initials", "")).strip())
        self.full_name_edit.setText(str(data.get("full_name", "")).strip())
        base_dir = str(data.get("base_projects_dir", "")).strip()
        if base_dir:
            self.local_path_edit.setText(base_dir)
        self.current_project_dir = str(data.get("current_project_dir", "")).strip()
        self.show_configuration_tab_on_startup = not self._has_user_configuration()
        self._apply_startup_tab()

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

    def _project_payload(
        self,
        name: str,
        sources: List[str],
        extension_filters: Optional[List[str]] = None,
        filter_mode: str = "No Filter",
        favorites: Optional[List[str]] = None,
        notes: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, object]:
        return {
            "name": name,
            "sources": sources,
            "extension_filters": extension_filters or [],
            "filter_mode": filter_mode,
            "favorites": favorites or [],
            "notes": notes or [],
        }

    def _read_project_config(self, project_dir: Path) -> Dict[str, object]:
        config_path = self._project_config_path(project_dir)
        if not config_path.exists():
            return self._project_payload(project_dir.name, [], [], "No Filter", [], [])

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self._project_payload(project_dir.name, [], [], "No Filter", [], [])

        name = str(data.get("name", project_dir.name)).strip() or project_dir.name
        raw_sources = data.get("sources", [])
        raw_extension_filters = data.get("extension_filters", [])
        filter_mode = str(data.get("filter_mode", "No Filter")).strip() or "No Filter"
        raw_favorites = data.get("favorites", [])
        raw_notes = data.get("notes", [])
        sources = [str(item) for item in raw_sources if str(item).strip()] if isinstance(raw_sources, list) else []
        extension_filters = (
            [str(item) for item in raw_extension_filters if str(item).strip()]
            if isinstance(raw_extension_filters, list)
            else []
        )
        favorites = (
            [str(item) for item in raw_favorites if str(item).strip()]
            if isinstance(raw_favorites, list)
            else []
        )
        notes: List[Dict[str, str]] = []
        if isinstance(raw_notes, list):
            for entry in raw_notes:
                if not isinstance(entry, dict):
                    continue
                subject = str(entry.get("subject", "")).strip()
                body = str(entry.get("body", ""))
                if not subject:
                    continue
                notes.append(
                    {
                        "id": str(entry.get("id", "")).strip() or str(uuid4()),
                        "subject": subject,
                        "body": body,
                        "created_at": str(entry.get("created_at", "")).strip(),
                        "updated_at": str(entry.get("updated_at", "")).strip(),
                    }
                )
        if filter_mode not in {"No Filter", "Include Only", "Exclude"}:
            filter_mode = "No Filter"
        return self._project_payload(
            name,
            sources,
            extension_filters,
            filter_mode,
            favorites,
            notes,
        )

    def _write_project_config(
        self,
        project_dir: Path,
        name: str,
        sources: List[str],
        extension_filters: Optional[List[str]] = None,
        filter_mode: str = "No Filter",
        favorites: Optional[List[str]] = None,
        notes: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._project_config_path(project_dir)
        payload = self._project_payload(
            name,
            sources,
            extension_filters,
            filter_mode,
            favorites,
            notes,
        )
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _save_project_config(
        self,
        project_dir: Path,
        *,
        name: Optional[str] = None,
        sources: Optional[List[str]] = None,
        extension_filters: Optional[List[str]] = None,
        filter_mode: Optional[str] = None,
        favorites: Optional[List[str]] = None,
        notes: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        current = self._read_project_config(project_dir)
        self._write_project_config(
            project_dir,
            name or str(current.get("name", project_dir.name)),
            sources if sources is not None else list(current.get("sources", [])),  # type: ignore[arg-type]
            extension_filters
            if extension_filters is not None
            else list(current.get("extension_filters", [])),  # type: ignore[arg-type]
            filter_mode or str(current.get("filter_mode", "No Filter")),
            favorites if favorites is not None else list(current.get("favorites", [])),  # type: ignore[arg-type]
            notes if notes is not None else list(current.get("notes", [])),  # type: ignore[arg-type]
        )

    def _ensure_default_project(self) -> None:
        base_dir = self._ensure_base_projects_dir()
        default_dir = base_dir / DEFAULT_PROJECT_NAME
        if not self._project_config_path(default_dir).exists():
            self._write_project_config(default_dir, DEFAULT_PROJECT_NAME, [], [], "No Filter", [], [])
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

    def _create_or_update_project(
        self,
        name: str,
        project_dir: Path,
        sources: Optional[List[str]] = None,
        extension_filters: Optional[List[str]] = None,
        filter_mode: str = "No Filter",
        favorites: Optional[List[str]] = None,
        notes: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        base_dir = self._ensure_base_projects_dir()
        _ = base_dir

        self._write_project_config(
            project_dir,
            name,
            sources or [],
            extension_filters or [],
            filter_mode,
            favorites or [],
            notes or [],
        )
        self.current_project_dir = str(project_dir)
        self._register_tracked_project(name, project_dir)
        self._save_settings()
        self._info(f"Project '{name}' saved.")

    def _show_new_project_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("New Project")
        dialog.resize(460, 220)
        layout = QVBoxLayout(dialog)

        form_layout = QGridLayout()
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Project name")
        form_layout.addWidget(QLabel("Project Name:"), 0, 0)
        form_layout.addWidget(name_edit, 0, 1)
        layout.addLayout(form_layout)

        keep_current_radio = QRadioButton("Create without changing the current directory")
        root_radio = QRadioButton("Create starting from the root of the file system")
        root_radio.setChecked(True)
        clone_current_checkbox = QCheckBox("Copy sources and filter settings from current project")
        layout.addWidget(keep_current_radio)
        layout.addWidget(root_radio)
        layout.addWidget(clone_current_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        name = name_edit.text().strip()
        if not name:
            self._error("Project name is required.")
            return

        project_dir = self._ensure_base_projects_dir() / self._safe_project_dir_name(name)
        sources: List[str] = []
        extension_filters: List[str] = []
        filter_mode = "No Filter"
        if clone_current_checkbox.isChecked():
            sources = self._source_roots_from_list()
            extension_filters = self._current_extension_filters()
            filter_mode = self.file_filter_mode_combo.currentText()

        self._create_or_update_project(
            name,
            project_dir,
            sources=sources,
            extension_filters=extension_filters,
            filter_mode=filter_mode,
        )

        if root_radio.isChecked():
            self._set_directory_tree_root(None)

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

        if item.text() == DEFAULT_PROJECT_NAME:
            self._error("The Default project cannot be untracked.")
            return

        project_dir = Path(str(item.data(Qt.UserRole)))
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Untrack Project")
        prompt.setText(f"What would you like to do with '{item.text()}'?")
        prompt.setInformativeText(
            "You can untrack the project only, or also delete its local project files."
        )
        untrack_btn = prompt.addButton("Untrack Only", QMessageBox.AcceptRole)
        delete_btn = prompt.addButton("Untrack && Delete Files", QMessageBox.DestructiveRole)
        prompt.addButton(QMessageBox.Cancel)
        prompt.setDefaultButton(untrack_btn)
        prompt.exec()

        clicked = prompt.clickedButton()
        if clicked is None or clicked.text() == "Cancel":
            return

        delete_project_files = clicked == delete_btn
        self.tracked_projects = [
            entry for entry in self.tracked_projects if entry["project_dir"] != str(project_dir)
        ]
        if not self.tracked_projects:
            self.current_project_dir = ""
            self._ensure_default_project()
            self._load_last_or_default_project()
        else:
            if self.current_project_dir == str(project_dir):
                self.current_project_dir = self.tracked_projects[0]["project_dir"]
                self._load_project_from_dir(Path(self.current_project_dir))
            self._save_tracked_projects()
            self._refresh_tracked_projects_list()
            self._save_settings()

        if delete_project_files and project_dir.exists():
            try:
                shutil.rmtree(project_dir)
            except OSError as exc:
                self._error(f"Project was untracked, but files could not be deleted:\n{exc}")
                return

        self._save_tracked_projects()
        self._refresh_tracked_projects_list()
        self._save_settings()

    def _load_project_from_dir(self, project_dir: Path) -> None:
        config = self._read_project_config(project_dir)
        name = str(config.get("name", project_dir.name))
        sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]
        extension_filters = [
            str(item) for item in config.get("extension_filters", [])
        ]  # type: ignore[arg-type]
        filter_mode = str(config.get("filter_mode", "No Filter"))
        favorites = [str(item) for item in config.get("favorites", [])]  # type: ignore[arg-type]
        notes = [dict(item) for item in config.get("notes", [])]  # type: ignore[arg-type]

        self.current_project_dir = str(project_dir)
        self.file_filter_mode_combo.blockSignals(True)
        self.file_filter_mode_combo.setCurrentText(filter_mode)
        self.file_filter_mode_combo.blockSignals(False)
        self._set_extension_filters(extension_filters)
        self.current_project_label.setText(f"Current Project: {name}")
        self._register_tracked_project(name, project_dir)
        self._refresh_source_roots(sources)
        self._refresh_favorites_list(favorites)
        self._refresh_notes_list(notes)
        self._save_settings()
        self._render_records_tables()

    def _selected_tracked_project_dir(self) -> Optional[Path]:
        item = self.tracked_projects_list.currentItem()
        if not item:
            return None
        return Path(str(item.data(Qt.UserRole)))

    def _open_selected_project_location(self) -> None:
        project_dir = self._selected_tracked_project_dir()
        if not project_dir or not project_dir.is_dir():
            self._error("Select a tracked project to open.")
            return
        self._open_paths([project_dir])

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
            self._set_directory_tree_root(None)

    def _create_directory_item(self, path: Path) -> QTreeWidgetItem:
        label = path.name or str(path)
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.UserRole, str(path))
        item.setToolTip(0, str(path))
        item.addChild(QTreeWidgetItem([""]))
        return item

    def _populate_directory_children(self, item: QTreeWidgetItem) -> None:
        if item.childCount() != 1 or item.child(0).data(0, Qt.UserRole) is not None:
            return

        item.takeChildren()
        path_value = item.data(0, Qt.UserRole)
        if not path_value:
            return

        try:
            children = sorted(
                [entry for entry in Path(path_value).iterdir() if entry.is_dir()],
                key=lambda entry: entry.name.lower(),
            )
        except OSError:
            children = []

        for child_path in children:
            item.addChild(self._create_directory_item(child_path))

    def _populate_system_roots(self) -> None:
        drives = QDir.drives()
        if drives:
            for drive in drives:
                drive_path = Path(drive.absoluteFilePath())
                self.directory_tree.addTopLevelItem(self._create_directory_item(drive_path))
            return

        self.directory_tree.addTopLevelItem(self._create_directory_item(Path("/")))

    def _set_directory_tree_root(self, root_path: Optional[Path]) -> None:
        self.directory_tree.clear()
        self.directory_tree_root = root_path

        if root_path is None:
            self._populate_system_roots()
            return

        root_item = self._create_directory_item(root_path)
        self.directory_tree.addTopLevelItem(root_item)
        self._populate_directory_children(root_item)
        root_item.setExpanded(True)
        self.directory_tree.setCurrentItem(root_item)

    def _browse_directory_tree_root(self) -> None:
        start_dir = str(
            self.current_directory
            or self.directory_tree_root
            or self._current_source_root()
            or Path.home()
        )
        path = QFileDialog.getExistingDirectory(self, "Browse Directory", start_dir)
        if not path:
            return

        selected_path = Path(path)
        self._set_directory_tree_root(selected_path)
        self._set_current_directory(selected_path)

    def _view_current_directory_location(self) -> None:
        current_directory = self._validate_current_directory()
        if not current_directory:
            return
        self._open_paths([current_directory])

    def _on_source_root_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        root_path = Path(str(current.data(Qt.UserRole)))
        self._set_directory_tree_root(root_path)
        self._set_current_directory(root_path)

    def _set_current_directory(self, directory: Path) -> None:
        self.current_directory = directory
        self.current_folder_label.setText(f"Current folder: {directory}")
        self._refresh_source_files()

    def _on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._populate_directory_children(item)

    def _on_directory_selected(self, item: QTreeWidgetItem, _column: int) -> None:
        path_value = item.data(0, Qt.UserRole)
        if not path_value:
            return
        path = Path(path_value)
        if path.is_dir():
            self._set_current_directory(path)

    def _refresh_source_files(self) -> None:
        self.files_list.clear()
        if not self.current_directory or not self.current_directory.is_dir():
            self.controlled_files_list.clear()
            return

        history_lookup = self._history_lookup_for_directory(self.current_directory)
        for item in sorted(self.current_directory.iterdir()):
            if item.is_file() and item.name != HISTORY_FILE_NAME:
                if not self._matches_extension_filter(item):
                    continue
                list_item = QListWidgetItem(item.name)
                list_item.setData(Qt.UserRole, str(item))
                history_row = history_lookup.get(item.name)
                original_name = (
                    history_row.get("original_file_name", item.name) if history_row else item.name
                )
                list_item.setData(Qt.UserRole + 1, original_name)
                self._apply_file_history_style(list_item, item, history_row)
                self.files_list.addItem(list_item)

        self._refresh_controlled_files()

    def _refresh_controlled_files(self) -> None:
        self.controlled_files_list.clear()
        if not self.current_directory or not self.current_directory.is_dir():
            return

        for entry in self._checked_out_files_for_directory(self.current_directory):
            label = entry["file_name"]
            if entry["initials"]:
                label = f"{label} ({entry['initials']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry)
            tooltip = entry["locked_source_file"]
            if entry["full_name"]:
                tooltip = f"{tooltip}\n{entry['full_name']}"
            item.setToolTip(tooltip)
            self.controlled_files_list.addItem(item)

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
            self._save_project_config(
                project_dir,
                name=self._current_project_name(),
                sources=sources,
                extension_filters=self._current_extension_filters(),
                filter_mode=self.file_filter_mode_combo.currentText(),
            )
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
        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=sources,
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
        )
        self._refresh_source_roots(sources)
        self._save_settings()

    def _track_current_directory(self) -> None:
        project_dir = self._validate_current_project()
        current_directory = self._validate_current_directory()
        if not project_dir or not current_directory:
            return

        sources = self._source_roots_from_list()
        current_dir_str = str(current_directory)
        if current_dir_str in sources:
            self._info("The current directory is already tracked.")
            return

        sources.append(current_dir_str)
        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=sources,
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
        )
        self._refresh_source_roots(sources)
        for row in range(self.source_roots_list.count()):
            item = self.source_roots_list.item(row)
            if item.data(Qt.UserRole) == current_dir_str:
                self.source_roots_list.setCurrentItem(item)
                break
        self._save_settings()

    def _selected_source_file_paths(self) -> List[Path]:
        return [Path(item.data(Qt.UserRole)) for item in self.files_list.selectedItems()]

    def _current_project_config(self) -> Optional[Dict[str, object]]:
        project_dir = self._current_project_path()
        if not project_dir or not project_dir.is_dir():
            return None
        return self._read_project_config(project_dir)

    def _current_project_favorites(self) -> List[str]:
        config = self._current_project_config()
        if not config:
            return []
        return [str(item) for item in config.get("favorites", [])]  # type: ignore[arg-type]

    def _current_project_notes(self) -> List[Dict[str, str]]:
        config = self._current_project_config()
        if not config:
            return []
        return [dict(item) for item in config.get("notes", [])]  # type: ignore[arg-type]

    def _favorite_display_name(self, favorite_path: str) -> str:
        return Path(favorite_path).name or favorite_path

    def _refresh_favorites_list(self, favorites: List[str]) -> None:
        self.favorites_list.clear()
        for favorite in favorites:
            item = QListWidgetItem(self._favorite_display_name(favorite))
            item.setData(Qt.UserRole, favorite)
            item.setToolTip(favorite)
            self.favorites_list.addItem(item)

    def _set_project_favorites(self, favorites: List[str]) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        normalized: List[str] = []
        for favorite in favorites:
            raw = str(favorite).strip()
            if raw and raw not in normalized:
                normalized.append(raw)
        self._save_project_config(project_dir, favorites=normalized)
        self._refresh_favorites_list(normalized)

    def _add_favorite_paths(self, paths: List[Path]) -> None:
        if not paths:
            return
        favorites = self._current_project_favorites()
        for path in paths:
            favorite = str(path)
            if favorite not in favorites:
                favorites.append(favorite)
        self._set_project_favorites(favorites)

    def _browse_and_add_favorites(self) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        start_dir = str(self.current_directory or project_dir)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Favorite File(s)",
            start_dir,
            "All Files (*)",
        )
        if not file_paths:
            return
        self._add_favorite_paths([Path(path) for path in file_paths])

    def _add_selected_source_files_to_favorites(self) -> None:
        selected_files = self._selected_source_file_paths()
        if not selected_files:
            self._error("Select at least one source file to favorite.")
            return
        self._add_favorite_paths(selected_files)

    def _remove_selected_favorites(self) -> None:
        selected_items = self.favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one favorite to remove.")
            return
        selected_paths = {str(item.data(Qt.UserRole)) for item in selected_items}
        favorites = [favorite for favorite in self._current_project_favorites() if favorite not in selected_paths]
        self._set_project_favorites(favorites)

    def _open_favorite_item(self, item: QListWidgetItem) -> None:
        self._open_paths([Path(str(item.data(Qt.UserRole)))])

    def _open_selected_favorites(self) -> None:
        selected_items = self.favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one favorite to open.")
            return
        self._open_paths([Path(str(item.data(Qt.UserRole))) for item in selected_items])

    def _note_tooltip(self, note: Dict[str, str]) -> str:
        body = note.get("body", "").strip()
        if len(body) > 240:
            body = body[:237].rstrip() + "..."
        return body or "(No body)"

    def _refresh_notes_list(self, notes: List[Dict[str, str]]) -> None:
        self.notes_list.clear()
        for note in notes:
            item = QListWidgetItem(note.get("subject", "(Untitled)"))
            item.setData(Qt.UserRole, note.get("id", ""))
            item.setToolTip(self._note_tooltip(note))
            self.notes_list.addItem(item)

    def _set_project_notes(self, notes: List[Dict[str, str]]) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        self._save_project_config(project_dir, notes=notes)
        self._refresh_notes_list(notes)

    def _selected_note_id(self) -> str:
        item = self.notes_list.currentItem()
        return str(item.data(Qt.UserRole)).strip() if item else ""

    def _show_note_dialog(self, note: Optional[Dict[str, str]] = None) -> Optional[Dict[str, str]]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Note" if note else "New Note")
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)

        form_layout = QGridLayout()
        subject_edit = QLineEdit(note.get("subject", "") if note else "")
        form_layout.addWidget(QLabel("Subject:"), 0, 0)
        form_layout.addWidget(subject_edit, 0, 1)
        layout.addLayout(form_layout)

        body_edit = QPlainTextEdit(note.get("body", "") if note else "")
        body_edit.setPlaceholderText("Note body")
        layout.addWidget(body_edit, stretch=1)

        if note:
            created_label = QLabel(f"Created: {note.get('created_at', '') or '-'}")
            updated_label = QLabel(f"Last Edited: {note.get('updated_at', '') or '-'}")
            layout.addWidget(created_label)
            layout.addWidget(updated_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None

        subject = subject_edit.text().strip()
        if not subject:
            self._error("Note subject is required.")
            return None

        timestamp = datetime.now().isoformat(timespec="seconds")
        existing = note or {}
        return {
            "id": existing.get("id", "") or str(uuid4()),
            "subject": subject,
            "body": body_edit.toPlainText().strip(),
            "created_at": existing.get("created_at", "") or timestamp,
            "updated_at": timestamp,
        }

    def _create_note(self) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        note = self._show_note_dialog()
        if not note:
            return
        notes = self._current_project_notes()
        notes.append(note)
        self._set_project_notes(notes)

    def _edit_note_item(self, item: QListWidgetItem) -> None:
        self.notes_list.setCurrentItem(item)
        self._edit_selected_note()

    def _edit_selected_note(self, _item: Optional[QListWidgetItem] = None) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        note_id = self._selected_note_id()
        if not note_id:
            self._error("Select a note to edit.")
            return
        notes = self._current_project_notes()
        for idx, note in enumerate(notes):
            if note.get("id", "") != note_id:
                continue
            updated = self._show_note_dialog(note)
            if not updated:
                return
            notes[idx] = updated
            self._set_project_notes(notes)
            return
        self._error("Selected note could not be found.")

    def _remove_selected_note(self) -> None:
        note_id = self._selected_note_id()
        if not note_id:
            self._error("Select a note to remove.")
            return
        notes = [note for note in self._current_project_notes() if note.get("id", "") != note_id]
        self._set_project_notes(notes)

    def _normalize_filter_preset(self, preset: Dict[str, object]) -> Optional[Dict[str, object]]:
        name = str(preset.get("name", "")).strip()
        if not name:
            return None
        filter_mode = str(preset.get("filter_mode", "No Filter")).strip() or "No Filter"
        if filter_mode not in {"No Filter", "Include Only", "Exclude"}:
            filter_mode = "No Filter"
        raw_extensions = preset.get("extensions", [])
        if isinstance(raw_extensions, str):
            raw_extensions = raw_extensions.split(",")
        extensions: List[str] = []
        if isinstance(raw_extensions, list):
            for value in raw_extensions:
                normalized = self._normalize_extension_value(str(value))
                if normalized and normalized not in extensions:
                    extensions.append(normalized)
        return {"name": name, "filter_mode": filter_mode, "extensions": extensions}

    def _load_filter_presets(self) -> None:
        self.filter_presets = []
        if not FILTER_PRESETS_FILE.exists():
            return
        try:
            data = json.loads(FILTER_PRESETS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return

        raw_presets = data.get("presets", [])
        if not isinstance(raw_presets, list):
            return
        for preset in raw_presets:
            if not isinstance(preset, dict):
                continue
            normalized = self._normalize_filter_preset(preset)
            if normalized:
                self.filter_presets.append(normalized)
        self.filter_presets.sort(key=lambda item: str(item["name"]).lower())

    def _save_filter_presets(self) -> None:
        FILTER_PRESETS_FILE.write_text(
            json.dumps({"presets": self.filter_presets}, indent=2),
            encoding="utf-8",
        )

    def _show_filter_preset_editor(
        self, preset: Optional[Dict[str, object]] = None
    ) -> Optional[Dict[str, object]]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Filter Preset" if preset else "New Filter Preset")
        dialog.resize(520, 220)
        layout = QVBoxLayout(dialog)

        form = QGridLayout()
        name_edit = QLineEdit(str(preset.get("name", "")) if preset else "")
        mode_combo = QComboBox()
        mode_combo.addItems(["No Filter", "Include Only", "Exclude"])
        mode_combo.setCurrentText(str(preset.get("filter_mode", "No Filter")) if preset else "No Filter")
        extensions_edit = QLineEdit(
            ", ".join(preset.get("extensions", [])) if preset else ""
        )
        extensions_edit.setPlaceholderText(".dwg, .pdf, .xlsx")
        form.addWidget(QLabel("Preset Name:"), 0, 0)
        form.addWidget(name_edit, 0, 1)
        form.addWidget(QLabel("Filter Mode:"), 1, 0)
        form.addWidget(mode_combo, 1, 1)
        form.addWidget(QLabel("Extensions:"), 2, 0)
        form.addWidget(extensions_edit, 2, 1)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None

        normalized = self._normalize_filter_preset(
            {
                "name": name_edit.text(),
                "filter_mode": mode_combo.currentText(),
                "extensions": extensions_edit.text(),
            }
        )
        if not normalized:
            self._error("Preset name is required.")
            return None
        return normalized

    def _show_filter_presets_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Filter Presets")
        dialog.resize(760, 420)
        layout = QVBoxLayout(dialog)
        preset_list = QListWidget()
        detail_label = QLabel("Select a preset to inspect or apply it.")
        detail_label.setWordWrap(True)

        def refresh_list() -> None:
            preset_list.clear()
            for preset in self.filter_presets:
                item = QListWidgetItem(str(preset["name"]))
                extensions = ", ".join(str(ext) for ext in preset.get("extensions", []))
                tooltip = f"Mode: {preset.get('filter_mode', 'No Filter')}\nExtensions: {extensions or '(none)'}"
                item.setToolTip(tooltip)
                item.setData(Qt.UserRole, str(preset["name"]))
                preset_list.addItem(item)

        def selected_preset() -> Optional[Dict[str, object]]:
            item = preset_list.currentItem()
            if not item:
                return None
            name = str(item.data(Qt.UserRole))
            for preset in self.filter_presets:
                if str(preset["name"]) == name:
                    return preset
            return None

        def update_detail() -> None:
            preset = selected_preset()
            if not preset:
                detail_label.setText("Select a preset to inspect or apply it.")
                return
            extensions = ", ".join(str(ext) for ext in preset.get("extensions", [])) or "(none)"
            detail_label.setText(
                f"Mode: {preset.get('filter_mode', 'No Filter')}\nExtensions: {extensions}"
            )

        def create_preset() -> None:
            preset = self._show_filter_preset_editor()
            if not preset:
                return
            self.filter_presets = [
                existing for existing in self.filter_presets if str(existing["name"]).lower() != str(preset["name"]).lower()
            ]
            self.filter_presets.append(preset)
            self.filter_presets.sort(key=lambda item: str(item["name"]).lower())
            self._save_filter_presets()
            refresh_list()

        def edit_preset() -> None:
            preset = selected_preset()
            if not preset:
                self._error("Select a preset to edit.")
                return
            updated = self._show_filter_preset_editor(preset)
            if not updated:
                return
            self.filter_presets = [
                existing
                for existing in self.filter_presets
                if str(existing["name"]).lower() != str(preset["name"]).lower()
            ]
            self.filter_presets.append(updated)
            self.filter_presets.sort(key=lambda item: str(item["name"]).lower())
            self._save_filter_presets()
            refresh_list()

        def delete_preset() -> None:
            preset = selected_preset()
            if not preset:
                self._error("Select a preset to delete.")
                return
            self.filter_presets = [
                existing
                for existing in self.filter_presets
                if str(existing["name"]).lower() != str(preset["name"]).lower()
            ]
            self._save_filter_presets()
            refresh_list()
            update_detail()

        def apply_preset() -> None:
            preset = selected_preset()
            if not preset:
                self._error("Select a preset to apply.")
                return
            self.file_filter_mode_combo.blockSignals(True)
            self.file_filter_mode_combo.setCurrentText(str(preset.get("filter_mode", "No Filter")))
            self.file_filter_mode_combo.blockSignals(False)
            self._set_extension_filters([str(ext) for ext in preset.get("extensions", [])])
            self._save_current_project_filters()
            dialog.accept()

        preset_list.currentItemChanged.connect(lambda _current, _previous: update_detail())
        preset_list.itemDoubleClicked.connect(lambda _item: apply_preset())
        layout.addWidget(preset_list, stretch=1)
        layout.addWidget(detail_label)

        controls = QHBoxLayout()
        new_btn = QPushButton("New")
        new_btn.clicked.connect(create_preset)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(edit_preset)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(delete_preset)
        apply_btn = QPushButton("Apply Selected To Project")
        apply_btn.clicked.connect(apply_preset)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        controls.addWidget(new_btn)
        controls.addWidget(edit_btn)
        controls.addWidget(delete_btn)
        controls.addStretch()
        controls.addWidget(apply_btn)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        refresh_list()
        if preset_list.count() > 0:
            preset_list.setCurrentRow(0)
        update_detail()
        dialog.exec()

    def _normalize_extension_value(self, value: str) -> str:
        value = value.strip().lower()
        if not value:
            return ""
        if not value.startswith("."):
            value = f".{value}"
        return value

    def _current_extension_filters(self) -> List[str]:
        raw = self.file_extension_list_edit.text().strip()
        if not raw:
            return []

        values: List[str] = []
        for part in raw.split(","):
            normalized = self._normalize_extension_value(part)
            if normalized and normalized not in values:
                values.append(normalized)
        return values

    def _set_extension_filters(self, filters: List[str]) -> None:
        normalized_filters: List[str] = []
        for value in filters:
            normalized = self._normalize_extension_value(value)
            if normalized and normalized not in normalized_filters:
                normalized_filters.append(normalized)
        self.file_extension_list_edit.blockSignals(True)
        self.file_extension_list_edit.setText(", ".join(normalized_filters))
        self.file_extension_list_edit.blockSignals(False)

    def _on_filter_mode_changed(self) -> None:
        self._save_current_project_filters()

    def _on_extension_list_changed(self) -> None:
        self.extension_filter_debounce.start()

    def _apply_debounced_extension_filters(self) -> None:
        self._save_current_project_filters()

    def _save_current_project_filters(self) -> None:
        project_dir = self._current_project_path()
        if not project_dir or not project_dir.is_dir():
            self._refresh_source_files()
            return

        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=self._source_roots_from_list(),
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
        )
        self._refresh_source_files()

    def _add_filter_extension(self) -> None:
        filters = self._current_extension_filters()
        normalized = self._normalize_extension_value(self.file_extension_combo.currentText())
        if normalized and normalized not in filters:
            filters.append(normalized)
            self._set_extension_filters(filters)
        self._save_current_project_filters()

    def _remove_filter_extension(self) -> None:
        normalized = self._normalize_extension_value(self.file_extension_combo.currentText())
        filters = [value for value in self._current_extension_filters() if value != normalized]
        self._set_extension_filters(filters)
        self._save_current_project_filters()

    def _clear_filter_extensions(self) -> None:
        self._set_extension_filters([])
        self._save_current_project_filters()

    def _matches_extension_filter(self, file_path: Path) -> bool:
        mode = self.file_filter_mode_combo.currentText()
        extensions = self._current_extension_filters()
        if mode == "No Filter" or not extensions:
            return True

        suffix = file_path.suffix.lower()
        if mode == "Include Only":
            return suffix in extensions
        if mode == "Exclude":
            return suffix not in extensions
        return True

    def _source_key(self, source_root: Path) -> str:
        raw = str(source_root.resolve())
        cleaned = raw.replace(":", "").replace("\\", "_").replace("/", "_")
        return cleaned.strip("_") or "source"

    def _format_checkout_timestamp(self, raw_timestamp: str) -> str:
        if not raw_timestamp:
            return ""
        try:
            dt = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            return raw_timestamp

        hour = dt.hour % 12 or 12
        minute = f"{dt.minute:02d}"
        meridiem = "AM" if dt.hour < 12 else "PM"
        return f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d} {hour}:{minute} {meridiem}"

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

    def _read_history_rows(self, source_dir: Path) -> List[Dict[str, str]]:
        history_file = source_dir / HISTORY_FILE_NAME
        if not history_file.exists():
            return []

        try:
            with history_file.open("r", encoding="utf-8", newline="") as handle:
                return [
                    {key: str(value) for key, value in row.items()}
                    for row in csv.DictReader(handle)
                ]
        except OSError:
            return []

    def _latest_history_by_file(self, source_dir: Path) -> Dict[str, Dict[str, str]]:
        latest_by_file: Dict[str, Dict[str, str]] = {}
        for row in self._read_history_rows(source_dir):
            file_name = row.get("file_name", "")
            if file_name:
                latest_by_file[file_name] = row
        return latest_by_file

    def _history_lookup_for_directory(self, source_dir: Path) -> Dict[str, Dict[str, str]]:
        lookup: Dict[str, Dict[str, str]] = {}
        for original_name, row in self._latest_history_by_file(source_dir).items():
            mapped_row = dict(row)
            mapped_row["original_file_name"] = original_name
            lookup[original_name] = mapped_row

            if row.get("action") == "CHECK_OUT":
                initials = row.get("user_initials", "")
                if initials:
                    original_path = source_dir / original_name
                    locked_name = self._locked_name_for(original_path, initials).name
                    lookup[locked_name] = mapped_row

        return lookup

    def _format_history_timestamp(self, raw_timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            return raw_timestamp

        day = dt.day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

        hour = dt.hour % 12 or 12
        minute = f"{dt.minute:02d}"
        meridiem = "AM" if dt.hour < 12 else "PM"
        return f"{dt.strftime('%A, %B')} {day}{suffix}, {dt.year} @ {hour}:{minute} {meridiem}"

    def _history_rows_for_file(self, source_dir: Path, file_name: str) -> List[List[str]]:
        rows: List[List[str]] = []
        for row in self._read_history_rows(source_dir):
            if row.get("file_name") == file_name:
                rows.append(
                    [
                        self._format_history_timestamp(row.get("timestamp", "")),
                        row.get("action", ""),
                        row.get("user_initials", ""),
                        row.get("user_full_name", ""),
                    ]
                )
        rows.reverse()
        return rows

    def _apply_file_history_style(
        self, item: QListWidgetItem, source_file: Path, latest_row: Optional[Dict[str, str]]
    ) -> None:
        if not latest_row:
            return

        action = latest_row.get("action", "")
        initials = latest_row.get("user_initials", "")
        full_name = latest_row.get("user_full_name", "")
        tooltip_lines = [str(source_file)]

        if action == "CHECK_OUT":
            if initials == self._normalize_initials():
                item.setBackground(QColor("#dcfce7"))
                tooltip_lines.append(f"Checked out by you ({initials})")
            else:
                item.setBackground(QColor("#fef3c7"))
                who = full_name or initials or "another user"
                tooltip_lines.append(f"Checked out by {who}")
        else:
            item.setBackground(QColor("#dbeafe"))
            tooltip_lines.append("Has document history")

        item.setToolTip("\n".join(tooltip_lines))

    def _checked_out_files_for_directory(self, source_dir: Path) -> List[Dict[str, str]]:
        latest_by_file = self._latest_history_by_file(source_dir)
        active_entries: List[Dict[str, str]] = []
        for file_name, row in latest_by_file.items():
            if row.get("action") != "CHECK_OUT":
                continue

            initials = row.get("user_initials", "")
            source_file = source_dir / file_name
            locked_source_file = (
                self._locked_name_for(source_file, initials) if initials else source_file
            )
            active_entries.append(
                {
                    "file_name": file_name,
                    "initials": initials,
                    "full_name": row.get("user_full_name", ""),
                    "locked_source_file": str(locked_source_file),
                }
            )

        active_entries.sort(key=lambda entry: entry["file_name"].lower())
        return active_entries

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
        checked_out_at = datetime.now().astimezone().isoformat(timespec="seconds")
        # Refresh before checkout so the UI and history reflect any recent activity by other users.
        self._refresh_source_files()
        history_lookup = self._history_lookup_for_directory(current_directory)

        for source_file in selected_files:
            latest_row = history_lookup.get(source_file.name)
            if latest_row and latest_row.get("action") == "CHECK_OUT":
                original_name = latest_row.get("original_file_name", source_file.name)
                checked_out_by = latest_row.get("user_initials", "")
                if checked_out_by == initials:
                    errors.append(f"Already checked out by you: {original_name}")
                else:
                    who = latest_row.get("user_full_name", "") or checked_out_by or "another user"
                    errors.append(f"Already checked out by {who}: {original_name}")
                continue

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
                        checked_out_at=checked_out_at,
                    )
                )
                self._append_history(source_file.parent, "CHECK_OUT", source_file.name)
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")

        self._save_records()
        self._refresh_source_files()
        self._refresh_controlled_files()
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

    def _remove_record_indexes(self, record_indexes: List[int]) -> None:
        selected = set(record_indexes)
        self.records = [
            record for idx, record in enumerate(self.records) if idx not in selected
        ]

    def _record_index_for_controlled_file(self, entry: Dict[str, str]) -> int:
        file_name = str(entry.get("file_name", ""))
        locked_source_file = str(entry.get("locked_source_file", ""))
        for idx, record in enumerate(self.records):
            if Path(record.source_file).name == file_name and record.locked_source_file == locked_source_file:
                return idx
            if record.locked_source_file == locked_source_file:
                return idx
        return -1

    def _show_checkin_mode_dialog(self, title: str, body: str, modified_label: str, unchanged_label: str) -> str:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(body)
        modified_btn = dialog.addButton(modified_label, QMessageBox.AcceptRole)
        unchanged_btn = dialog.addButton(unchanged_label, QMessageBox.ActionRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(modified_btn)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == modified_btn:
            return "modified"
        if clicked == unchanged_btn:
            return "unchanged"
        return "cancel"

    def _show_force_checkin_warning_dialog(self) -> str:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Force Check In")
        dialog.setText("Force check-in can affect another user's document control state.")
        dialog.setInformativeText(
            "Use force check-in only if you are absolutely sure the selected files should be released."
        )
        modified_btn = dialog.addButton("Attempt Modified Check In", QMessageBox.AcceptRole)
        unchanged_btn = dialog.addButton("Force Check In Unmodified", QMessageBox.ActionRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(unchanged_btn)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == modified_btn:
            return "modified"
        if clicked == unchanged_btn:
            return "unchanged"
        return "cancel"

    def _perform_pending_checkin_actions(
        self, actions: List[PendingCheckinAction], history_action: str
    ) -> List[str]:
        errors: List[str] = []
        completed_indexes: List[int] = []
        for action in actions:
            source_file = Path(action.source_file)
            locked_source_file = Path(action.locked_source_file)

            try:
                if action.action_mode in {"modified", "tracked_modified", "selected_modified"}:
                    local_file = Path(action.local_file)
                    if not local_file.exists():
                        errors.append(f"Local file missing: {local_file}")
                        continue
                    if not locked_source_file.exists():
                        errors.append(f"Locked source file missing: {locked_source_file}")
                        continue
                    shutil.copy2(local_file, locked_source_file)
                    locked_source_file.replace(source_file)
                elif action.action_mode == "unchanged":
                    if not locked_source_file.exists():
                        errors.append(f"Missing locked source file: {locked_source_file}")
                        continue
                    locked_source_file.replace(source_file)
                else:
                    continue

                self._append_history(source_file.parent, history_action, source_file.name)
                if action.record_idx >= 0:
                    completed_indexes.append(action.record_idx)
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")

        if completed_indexes:
            self._remove_record_indexes(completed_indexes)
            self._save_records()
        return errors

    def _describe_checkin_action(self, action: PendingCheckinAction) -> str:
        if action.action_mode == "unchanged":
            return "Check in unchanged"
        if action.action_mode == "tracked_modified":
            return "Check in modified from tracked local file"
        if action.action_mode == "selected_modified":
            return "Check in modified from selected file"
        if action.action_mode == "modified":
            return "Check in modified"
        return action.action_mode

    def _show_pending_actions_dialog(
        self, title: str, actions: List[PendingCheckinAction], allow_modify: bool = False
    ) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(1080, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("The following actions will be performed:"))

        table = QTableWidget(len(actions), 4)
        table.setHorizontalHeaderLabels(["File", "Action", "Local File", "Details"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        for row_idx, action in enumerate(actions):
            values = [
                action.file_name,
                self._describe_checkin_action(action),
                action.local_file,
                action.reason,
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                table.setItem(row_idx, col_idx, item)

        layout.addWidget(table)
        buttons = QDialogButtonBox()
        commit_btn = buttons.addButton("Commit Actions", QDialogButtonBox.AcceptRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        modify_btn = None
        selected_action = {"value": "cancel"}

        def set_action(value: str) -> None:
            selected_action["value"] = value

        commit_btn.clicked.connect(lambda: (set_action("commit"), dialog.accept()))
        cancel_btn.clicked.connect(lambda: (set_action("cancel"), dialog.reject()))
        if allow_modify:
            modify_btn = buttons.addButton("Modify Actions", QDialogButtonBox.ActionRole)
            modify_btn.clicked.connect(lambda: (set_action("modify"), dialog.accept()))

        layout.addWidget(buttons)
        dialog.exec()
        if allow_modify and selected_action["value"] == "modify" and modify_btn is not None:
            return "modify"
        if selected_action["value"] == "commit":
            return "commit"
        return "cancel"

    def _show_force_checkin_status_dialog(
        self, tracked_actions: List[PendingCheckinAction], untracked_actions: List[PendingCheckinAction]
    ) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle("Force Check-In Status")
        dialog.resize(1000, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Tracked files available for modified check-in"))
        tracked_table = QTableWidget(len(tracked_actions), 3)
        tracked_table.setHorizontalHeaderLabels(["File", "Tracked Local File", "Details"])
        tracked_table.setEditTriggers(QTableWidget.NoEditTriggers)
        tracked_table.setSelectionMode(QTableWidget.NoSelection)
        tracked_header = tracked_table.horizontalHeader()
        tracked_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tracked_header.setSectionResizeMode(1, QHeaderView.Stretch)
        tracked_header.setSectionResizeMode(2, QHeaderView.Stretch)
        for row_idx, action in enumerate(tracked_actions):
            values = [action.file_name, action.local_file, action.reason]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                tracked_table.setItem(row_idx, col_idx, item)
        layout.addWidget(tracked_table)

        layout.addWidget(QLabel("Files without a tracked modified local file"))
        untracked_table = QTableWidget(len(untracked_actions), 2)
        untracked_table.setHorizontalHeaderLabels(["File", "Details"])
        untracked_table.setEditTriggers(QTableWidget.NoEditTriggers)
        untracked_table.setSelectionMode(QTableWidget.NoSelection)
        untracked_header = untracked_table.horizontalHeader()
        untracked_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        untracked_header.setSectionResizeMode(1, QHeaderView.Stretch)
        for row_idx, action in enumerate(untracked_actions):
            values = [action.file_name, action.reason]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                untracked_table.setItem(row_idx, col_idx, item)
        layout.addWidget(untracked_table)

        buttons = QDialogButtonBox()
        tracked_btn = buttons.addButton("Check In All Tracked", QDialogButtonBox.AcceptRole)
        per_file_btn = buttons.addButton("Continue Per File", QDialogButtonBox.ActionRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        selected_action = {"value": "cancel"}

        tracked_btn.clicked.connect(lambda: (selected_action.__setitem__("value", "tracked"), dialog.accept()))
        per_file_btn.clicked.connect(lambda: (selected_action.__setitem__("value", "per_file"), dialog.accept()))
        cancel_btn.clicked.connect(lambda: (selected_action.__setitem__("value", "cancel"), dialog.reject()))
        layout.addWidget(buttons)
        dialog.exec()
        return selected_action["value"]

    def _select_force_checkin_file_for_action(
        self, action: PendingCheckinAction
    ) -> Optional[PendingCheckinAction]:
        current_local = action.local_file
        while True:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Select Modified File")
            dialog.setText(f"Choose how to handle '{action.file_name}'.")
            if current_local:
                dialog.setInformativeText(f"Current local file: {current_local}")
            browse_btn = dialog.addButton("Browse For File", QMessageBox.AcceptRole)
            skip_process_btn = dialog.addButton("Skip This File", QMessageBox.ActionRole)
            skip_unmodified_btn = dialog.addButton("Check In Unmodified", QMessageBox.ActionRole)
            cancel_btn = dialog.addButton("Cancel Entire Operation", QMessageBox.RejectRole)
            tracked_btn = None
            if current_local and Path(current_local).exists():
                tracked_btn = dialog.addButton("Use Current Tracked File", QMessageBox.ActionRole)
                dialog.setDefaultButton(tracked_btn)
            else:
                dialog.setDefaultButton(browse_btn)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked == cancel_btn:
                return None
            if tracked_btn is not None and clicked == tracked_btn:
                action.local_file = current_local
                action.action_mode = "tracked_modified"
                action.reason = "Using the tracked local checked-out file."
                return action
            if clicked == skip_process_btn:
                action.action_mode = "skip"
                action.local_file = ""
                action.reason = "Removed from the force check-in action list."
                return action
            if clicked == skip_unmodified_btn:
                action.action_mode = "unchanged"
                action.local_file = ""
                action.reason = "Skipping modified source selection; force check in unchanged."
                return action
            if clicked == browse_btn:
                start_dir = str(Path(current_local).parent) if current_local else str(Path.home())
                file_path, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Select Modified File For {action.file_name}",
                    start_dir,
                    "All Files (*)",
                )
                if not file_path:
                    continue
                action.local_file = file_path
                action.action_mode = "selected_modified"
                action.reason = "Using a manually selected local file."
                return action

    def _plan_force_checkin_actions(
        self, entries: List[Dict[str, str]]
    ) -> Optional[List[PendingCheckinAction]]:
        tracked_actions: List[PendingCheckinAction] = []
        untracked_actions: List[PendingCheckinAction] = []
        planned_actions: List[PendingCheckinAction] = []

        for entry in entries:
            file_name = str(entry.get("file_name", ""))
            locked_source_file = str(entry.get("locked_source_file", ""))
            source_file = str(self.current_directory / file_name) if self.current_directory else file_name
            record_idx = self._record_index_for_controlled_file(entry)
            action = PendingCheckinAction(
                file_name=file_name,
                source_file=source_file,
                locked_source_file=locked_source_file,
                action_mode="unchanged",
                record_idx=record_idx,
                reason="No tracked modified file found. Will release the source file unchanged.",
            )
            if record_idx >= 0 and 0 <= record_idx < len(self.records):
                action.local_file = self.records[record_idx].local_file
                action.reason = "Tracked modified local file available."
                tracked_actions.append(action)
            else:
                untracked_actions.append(action)
            planned_actions.append(action)

        choice = self._show_force_checkin_status_dialog(tracked_actions, untracked_actions)
        if choice == "cancel":
            return None
        if choice == "tracked":
            for action in planned_actions:
                if action.local_file and Path(action.local_file).exists():
                    action.action_mode = "tracked_modified"
                    action.reason = "Using the tracked local checked-out file."
                else:
                    action.action_mode = "unchanged"
                    action.local_file = ""
                    action.reason = "No tracked local file; force check in unchanged."
        else:
            updated_actions: List[PendingCheckinAction] = []
            for action in planned_actions:
                updated = self._select_force_checkin_file_for_action(action)
                if updated is None:
                    return None
                if updated.action_mode != "skip":
                    updated_actions.append(updated)
            planned_actions = updated_actions

        while True:
            review = self._show_pending_actions_dialog(
                "Review Force Check-In Actions", planned_actions, allow_modify=True
            )
            if review == "commit":
                return planned_actions
            if review == "cancel":
                return None
            updated_actions = []
            for action in planned_actions:
                updated = self._select_force_checkin_file_for_action(action)
                if updated is None:
                    return None
                if updated.action_mode != "skip":
                    updated_actions.append(updated)
            planned_actions = updated_actions

    def _checkin_selected(self) -> None:
        if not self._validate_identity():
            return

        selected_indexes = set(self._selected_record_indexes())
        if not selected_indexes:
            self._error("Select at least one checked-out row to check in.")
            return

        choice = self._show_checkin_mode_dialog(
            "Check In Files",
            "Choose how the selected files should be checked in.",
            "Check In With Modifications",
            "Check In Unchanged",
        )
        if choice == "cancel":
            return

        actions: List[PendingCheckinAction] = []
        for record_idx in sorted(selected_indexes):
            if not (0 <= record_idx < len(self.records)):
                continue
            record = self.records[record_idx]
            reason = (
                "Copy the local checked-out file back to the locked source file before releasing it."
                if choice == "modified"
                else "Release the locked source file without copying the local file back."
            )
            actions.append(
                PendingCheckinAction(
                    file_name=Path(record.source_file).name,
                    source_file=record.source_file,
                    locked_source_file=record.locked_source_file,
                    action_mode=choice,
                    local_file=record.local_file if choice == "modified" else "",
                    record_idx=record_idx,
                    reason=reason,
                )
            )

        review = self._show_pending_actions_dialog("Review Check-In Actions", actions)
        if review != "commit":
            return

        errors = self._perform_pending_checkin_actions(actions, "CHECK_IN")
        self._refresh_source_files()
        self._refresh_controlled_files()
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
        self._refresh_controlled_files()

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

    def _force_checkin_selected(self) -> None:
        if not self._validate_identity():
            return

        current_directory = self._validate_current_directory()
        if not current_directory:
            return

        selected_items = self.controlled_files_list.selectedItems()
        if not selected_items:
            self._error("Select at least one controlled file to force check in.")
            return

        choice = self._show_force_checkin_warning_dialog()
        if choice == "cancel":
            return

        entries: List[Dict[str, str]] = []
        for item in selected_items:
            entry = item.data(Qt.UserRole)
            if not isinstance(entry, dict):
                continue
            entries.append(entry)

        actions: Optional[List[PendingCheckinAction]]
        if choice == "unchanged":
            actions = []
            for entry in entries:
                file_name = str(entry.get("file_name", ""))
                if not file_name:
                    continue
                actions.append(
                    PendingCheckinAction(
                        file_name=file_name,
                        source_file=str(current_directory / file_name),
                        locked_source_file=str(entry.get("locked_source_file", "")),
                        action_mode="unchanged",
                        record_idx=self._record_index_for_controlled_file(entry),
                        reason="Force release the locked source file without copying a local file.",
                    )
                )
            review = self._show_pending_actions_dialog(
                "Review Force Check-In Actions", actions, allow_modify=False
            )
            if review != "commit":
                return
        else:
            actions = self._plan_force_checkin_actions(entries)
            if actions is None:
                return

        errors = self._perform_pending_checkin_actions(actions, "FORCE_CHECK_IN")
        self._refresh_source_files()
        self._refresh_controlled_files()
        self._render_records_tables()

        if errors:
            self._error("Some files failed to force check in:\n" + "\n".join(errors))
        elif actions:
            self._info("Force check-in complete.")

    def _show_selected_file_history(self) -> None:
        selected_items = self.files_list.selectedItems()
        if not selected_items:
            self._error("Select a file to view history.")
            return

        file_path = Path(selected_items[0].data(Qt.UserRole))
        original_name = str(selected_items[0].data(Qt.UserRole + 1) or file_path.name)
        rows = self._history_rows_for_file(file_path.parent, original_name)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Document History - {original_name}")
        dialog.resize(980, 420)
        layout = QVBoxLayout(dialog)

        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Timestamp", "Action", "Initials", "Full Name"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 320))
        table.setColumnWidth(3, max(table.columnWidth(3), 220))
        layout.addWidget(table)
        dialog.exec()

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

    def _local_display_name(self, local_path: str) -> str:
        return Path(local_path).name

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
                self._local_display_name(record.local_file),
                record.initials,
                record.project_name,
                self._format_checkout_timestamp(record.checked_out_at),
            ]
            for col_idx, value in enumerate(values):
                if col_idx in (0, 1):
                    display_value = self._short_path(value)
                else:
                    display_value = value
                item = QTableWidgetItem(display_value)
                if col_idx == 2:
                    item.setToolTip(record.local_file)
                elif col_idx == 4:
                    item.setToolTip(record.project_dir)
                else:
                    item.setToolTip(value)
                if col_idx == 0:
                    item.setData(Qt.UserRole, record_idx)
                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 260))
        table.setColumnWidth(1, max(table.columnWidth(1), 260))
        table.setColumnWidth(2, max(table.columnWidth(2), 180))
        table.setColumnWidth(3, max(table.columnWidth(3), 72))
        table.setColumnWidth(4, max(table.columnWidth(4), 170))
        table.setColumnWidth(5, max(table.columnWidth(5), 150))

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
                        checked_out_at=str(entry.get("checked_out_at", "")),
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

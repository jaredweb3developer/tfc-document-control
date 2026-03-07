import csv
import hashlib
import json
import os
import stat
import shutil
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QDir, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
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
APP_NAME = "TFC Document Control"
APP_VERSION = "0.1.1"
USER_DATA_DIR_NAME = "TFC Project Control"
SETTINGS_SCHEMA_VERSION = 1
TRACKED_PROJECTS_SCHEMA_VERSION = 1
PROJECT_CONFIG_SCHEMA_VERSION = 1
FILTER_PRESETS_SCHEMA_VERSION = 1
RECORDS_SCHEMA_VERSION = 1
FILE_VERSIONS_SCHEMA_VERSION = 1
USER_DATA_ROOT = Path.home() / "Documents" / USER_DATA_DIR_NAME
SETTINGS_FILE = USER_DATA_ROOT / "settings.json"
LEGACY_SETTINGS_FILE = APP_ROOT / "settings.json"
LEGACY_PROJECTS_FILE = APP_ROOT / "projects.json"
LEGACY_RECORDS_FILE = APP_ROOT / ".checkout_records.json"
LEGACY_FILTER_PRESETS_FILE = APP_ROOT / "filter_presets.json"
PROJECT_CONFIG_FILE = "dctl.json"
HISTORY_FILE_NAME = ".doc_control_history.json"
LEGACY_HISTORY_FILE_NAME = ".doc_control_history.csv"
HISTORY_SCHEMA_VERSION = 1
DIRECTORY_NOTES_FILE = ".doc_file_notes.json"
DIRECTORY_NOTES_SCHEMA_VERSION = 1
DEFAULT_PROJECT_NAME = "Default"
DEBUG_EVENTS_FILE = USER_DATA_ROOT / "debug_events.log"
FILE_VERSIONS_FILE = "file_versions.json"
FILE_VERSIONS_DIR = "file_versions"
GLOBAL_FAVORITES_FILE = USER_DATA_ROOT / "global_favorites.json"
GLOBAL_NOTES_FILE = USER_DATA_ROOT / "global_notes.json"


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
    record_type: str = "checked_out"


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
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1500, 980)

        self.records: List[CheckoutRecord] = []
        self.tracked_projects: List[Dict[str, str]] = []
        self.current_project_dir: str = ""
        self.current_directory: Optional[Path] = None
        self.directory_tree_root: Optional[Path] = None
        self.show_configuration_tab_on_startup = True
        self.filter_presets: List[Dict[str, object]] = []
        self.main_section_toggles: List[QToolButton] = []
        self._dir_files_cache: Dict[str, Tuple[float, List[Path]]] = {}
        self._history_rows_cache: Dict[str, Tuple[int, List[Dict[str, str]]]] = {}
        self._dir_cache_ttl_seconds: Optional[float] = None
        self._remote_dir_cache_ttl_seconds = 60.0
        self._local_dir_cache_ttl_seconds = 5.0
        self._busy_action_depth = 0
        self._startup_splash_dialog: Optional[QDialog] = None
        self._startup_splash_label: Optional[QLabel] = None
        self.global_favorites: List[str] = []
        self.global_notes: List[Dict[str, str]] = []
        self.project_search_debounce = QTimer(self)
        self.project_search_debounce.setSingleShot(True)
        self.project_search_debounce.setInterval(300)
        self.project_search_debounce.timeout.connect(self._refresh_tracked_projects_list)
        self.extension_filter_debounce = QTimer(self)
        self.extension_filter_debounce.setSingleShot(True)
        self.extension_filter_debounce.setInterval(2000)
        self.extension_filter_debounce.timeout.connect(self._apply_debounced_extension_filters)
        self.file_search_debounce = QTimer(self)
        self.file_search_debounce.setSingleShot(True)
        self.file_search_debounce.setInterval(300)
        self.file_search_debounce.timeout.connect(self._refresh_source_files_from_search)

        self._build_ui()
        self._show_startup_splash("Starting TFC Document Control...")
        try:
            self._update_startup_splash("Loading settings...")
            self._load_settings()
            self._update_startup_splash("Loading filter presets...")
            self._load_filter_presets()
            self._update_startup_splash("Loading tracked projects...")
            self._load_tracked_projects()
            self._update_startup_splash("Loading checkout records...")
            self._load_records()
            self._update_startup_splash("Loading global favorites and notes...")
            self._load_global_favorites()
            self._load_global_notes()
            self._update_startup_splash("Loading current project...")
            self._load_last_or_default_project()
            self._update_startup_splash("Finalizing startup...")
        finally:
            self._close_startup_splash()

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
        self.main_section_toggles.append(toggle)

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
            if not checked and self.main_section_toggles and not any(
                section_toggle.isChecked() for section_toggle in self.main_section_toggles
            ):
                self._restore_main_sections_default_state()

        toggle.toggled.connect(_toggle_section)

        layout.addWidget(toggle)
        layout.addWidget(content, stretch=1)
        return container

    def _restore_main_sections_default_state(self) -> None:
        for toggle in self.main_section_toggles:
            toggle.blockSignals(True)
            toggle.setChecked(True)
            toggle.setArrowType(Qt.DownArrow)
            toggle.blockSignals(False)

        for toggle in self.main_section_toggles:
            toggle.toggled.emit(True)

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

        self.projects_file_edit = QLineEdit(str(self._default_projects_registry_file()))
        browse_projects_file_btn = QPushButton("Browse")
        browse_projects_file_btn.clicked.connect(self._choose_projects_registry_file)
        self.filter_presets_file_edit = QLineEdit(str(self._default_filter_presets_file()))
        browse_filter_presets_btn = QPushButton("Browse")
        browse_filter_presets_btn.clicked.connect(self._choose_filter_presets_file)
        self.records_file_edit = QLineEdit(str(self._default_records_file()))
        browse_records_file_btn = QPushButton("Browse")
        browse_records_file_btn.clicked.connect(self._choose_records_file)
        self.debug_log_file_edit = QLineEdit(str(self._default_debug_events_file()))
        browse_debug_log_btn = QPushButton("Browse")
        browse_debug_log_btn.clicked.connect(self._choose_debug_log_file)
        open_debug_log_btn = QPushButton("Open")
        open_debug_log_btn.clicked.connect(self._open_debug_log_file)
        clear_debug_log_btn = QPushButton("Clear")
        clear_debug_log_btn.clicked.connect(self._clear_debug_log_file)
        self.debug_enabled_checkbox = QCheckBox("Enable Debug Event Logging")
        self.debug_enabled_checkbox.toggled.connect(self._on_debug_logging_toggled)
        config_divider = QFrame()
        config_divider.setFrameShape(QFrame.HLine)
        config_divider.setFrameShadow(QFrame.Sunken)
        config_divider_label = QLabel("Application Data File Locations")
        debug_divider = QFrame()
        debug_divider.setFrameShape(QFrame.HLine)
        debug_divider.setFrameShadow(QFrame.Sunken)

        layout.addWidget(QLabel("User:"), 0, 0)
        layout.addLayout(identity_bar, 0, 1, 1, 2)
        layout.addWidget(QLabel("Local Projects Folder:"), 1, 0)
        layout.addWidget(self.local_path_edit, 1, 1)
        layout.addWidget(browse_local_btn, 1, 2)
        layout.addWidget(config_divider, 2, 0, 1, 3)
        layout.addWidget(config_divider_label, 3, 0, 1, 3)
        layout.addWidget(QLabel("Tracked Projects File:"), 4, 0)
        layout.addWidget(self.projects_file_edit, 4, 1)
        layout.addWidget(browse_projects_file_btn, 4, 2)
        layout.addWidget(QLabel("Filter Presets File:"), 5, 0)
        layout.addWidget(self.filter_presets_file_edit, 5, 1)
        layout.addWidget(browse_filter_presets_btn, 5, 2)
        layout.addWidget(QLabel("Checkout Records File:"), 6, 0)
        layout.addWidget(self.records_file_edit, 6, 1)
        layout.addWidget(browse_records_file_btn, 6, 2)
        layout.addWidget(debug_divider, 7, 0, 1, 3)
        layout.addWidget(self.debug_enabled_checkbox, 8, 0, 1, 3)
        layout.addWidget(QLabel("Debug Events Log:"), 9, 0)
        layout.addWidget(self.debug_log_file_edit, 9, 1)
        layout.addWidget(browse_debug_log_btn, 9, 2)
        debug_btn_row = QHBoxLayout()
        debug_btn_row.addWidget(open_debug_log_btn)
        debug_btn_row.addWidget(clear_debug_log_btn)
        debug_btn_row.addStretch()
        layout.addLayout(debug_btn_row, 10, 1, 1, 2)

        return group

    def _build_projects_group(self) -> QGroupBox:
        group = QGroupBox("Projects")
        layout = QVBoxLayout(group)

        self.tracked_projects_list = QListWidget()
        self.tracked_projects_list.itemDoubleClicked.connect(self._show_tracked_projects_context_menu_for_item)
        self.tracked_projects_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tracked_projects_list.customContextMenuRequested.connect(
            self._show_tracked_projects_context_menu
        )

        self.current_project_label = QLabel("Current Project: -")
        self.current_project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.project_search_edit = QLineEdit()
        self.project_search_edit.setPlaceholderText("Search projects by name, client, or year")
        self.project_search_edit.textChanged.connect(self._on_project_search_changed)

        tracked_panel = QWidget()
        tracked_layout = QVBoxLayout(tracked_panel)
        tracked_layout.addWidget(QLabel("Tracked Projects"))
        tracked_layout.addWidget(self.project_search_edit)
        tracked_layout.addWidget(self.tracked_projects_list, stretch=1)
        tracked_controls = QHBoxLayout()
        tracked_controls.addWidget(
            self._build_options_button(
                [
                    ("New Project", self._show_new_project_dialog),
                    ("Load Selected", self._load_selected_tracked_project),
                    ("Project Files Manager", self._open_project_files_manager_for_selected_project),
                    ("Track Existing", self._add_existing_project),
                    ("Edit Selected", self._edit_selected_project),
                    ("Open Location", self._open_selected_project_location),
                    ("Untrack Selected", self._remove_selected_project),
                    ("---", self._load_selected_tracked_project),
                    ("Move Up", self._move_selected_project_up),
                    ("Move Down", self._move_selected_project_down),
                    ("Move to Top", self._move_selected_project_top),
                    ("Move to Bottom", self._move_selected_project_bottom),
                ]
            )
        )
        tracked_controls.addStretch()
        tracked_layout.addLayout(tracked_controls)

        favorites_panel = QWidget()
        favorites_layout = QVBoxLayout(favorites_panel)
        favorites_layout.addWidget(QLabel("Favorite Files"))

        self.favorites_tabs = QTabWidget()
        project_favorites_tab = QWidget()
        project_favorites_layout = QVBoxLayout(project_favorites_tab)
        self.favorites_list = QListWidget()
        self.favorites_list.itemDoubleClicked.connect(self._show_favorites_context_menu_for_item)
        self.favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self._show_favorites_context_menu)
        project_favorites_layout.addWidget(self.favorites_list, stretch=1)
        self.favorites_tabs.addTab(project_favorites_tab, "Project Favorites")

        global_favorites_tab = QWidget()
        global_favorites_layout = QVBoxLayout(global_favorites_tab)
        self.global_favorites_search_edit = QLineEdit()
        self.global_favorites_search_edit.setPlaceholderText("Search global favorites")
        self.global_favorites_search_edit.textChanged.connect(self._refresh_global_favorites_list)
        global_favorites_layout.addWidget(self.global_favorites_search_edit)
        self.global_favorites_list = QListWidget()
        self.global_favorites_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.global_favorites_list.itemDoubleClicked.connect(
            self._show_global_favorites_context_menu_for_item
        )
        self.global_favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.global_favorites_list.customContextMenuRequested.connect(
            self._show_global_favorites_context_menu
        )
        global_favorites_layout.addWidget(self.global_favorites_list, stretch=1)
        self.favorites_tabs.addTab(global_favorites_tab, "Global Favorites")
        favorites_layout.addWidget(self.favorites_tabs, stretch=1)

        favorites_controls = QHBoxLayout()
        favorites_controls.addWidget(
            self._build_options_button(
                [
                    ("Add Project Favorite", self._browse_and_add_favorites),
                    ("Add Global Favorite", self._browse_and_add_global_favorites),
                    ("Add Selected Global -> Project", self._add_selected_global_favorites_to_project),
                    ("Open Selected", self._open_selected_favorites_from_active_tab),
                    ("Remove Selected", self._remove_selected_favorites_from_active_tab),
                    ("---", self._open_selected_favorites_from_active_tab),
                    ("Move Up", self._move_selected_favorite_up),
                    ("Move Down", self._move_selected_favorite_down),
                    ("Move to Top", self._move_selected_favorite_top),
                    ("Move to Bottom", self._move_selected_favorite_bottom),
                ]
            )
        )
        favorites_controls.addStretch()
        favorites_layout.addLayout(favorites_controls)

        notes_panel = QWidget()
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.addWidget(QLabel("Notes"))
        self.notes_list = QListWidget()
        self.notes_list.itemDoubleClicked.connect(self._show_notes_context_menu_for_item)
        self.notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self._show_notes_context_menu)
        notes_layout.addWidget(self.notes_list, stretch=1)
        notes_controls = QHBoxLayout()
        notes_controls.addWidget(
            self._build_options_button(
                [
                    ("New Note", self._create_note),
                    ("Edit Selected", self._edit_selected_note),
                    ("Remove Selected", self._remove_selected_note),
                    ("---", self._create_note),
                    ("Move Up", self._move_selected_note_up),
                    ("Move Down", self._move_selected_note_down),
                    ("Move to Top", self._move_selected_note_top),
                    ("Move to Bottom", self._move_selected_note_bottom),
                ]
            )
        )
        notes_controls.addStretch()
        notes_layout.addLayout(notes_controls)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.addWidget(tracked_panel)
        content_splitter.addWidget(favorites_panel)
        content_splitter.addWidget(notes_panel)
        content_splitter.setSizes([320, 360, 360])

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
        self.source_roots_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.source_roots_list.customContextMenuRequested.connect(self._show_source_roots_context_menu)
        self.source_roots_list.setMinimumWidth(220)
        tracked_layout.addWidget(self.source_roots_list)

        source_button_bar = QHBoxLayout()
        source_button_bar.addWidget(
            self._build_options_button(
                [
                    ("Track Dir (Browse)", self._add_source_directory),
                    ("Track Directory", self._track_current_directory),
                    ("Untrack Dir", self._remove_source_directory),
                    ("---", self._track_current_directory),
                    ("Move Up", self._move_selected_source_up),
                    ("Move Down", self._move_selected_source_down),
                    ("Move to Top", self._move_selected_source_top),
                    ("Move to Bottom", self._move_selected_source_bottom),
                ]
            )
        )
        source_button_bar.addStretch()
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
        directory_button_bar.addWidget(
            self._build_options_button(
                [
                    ("Browse", self._browse_directory_tree_root),
                    ("View Location", self._view_current_directory_location),
                    ("Track Directory", self._track_current_directory),
                ]
            )
        )
        directory_button_bar.addStretch()
        directory_layout.addLayout(directory_button_bar)

        files_panel = QWidget()
        files_layout = QVBoxLayout(files_panel)
        files_layout.addWidget(QLabel("Files"))
        self.file_search_edit = QLineEdit()
        self.file_search_edit.setPlaceholderText("Search files")
        self.file_search_edit.textChanged.connect(self._on_file_search_changed)
        files_layout.addWidget(self.file_search_edit)

        extension_group = QGroupBox("Extension Filter")
        extension_layout = QVBoxLayout(extension_group)
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
        extension_layout.addLayout(filter_bar)
        extension_list_bar = QHBoxLayout()
        extension_list_bar.addWidget(QLabel("Filter Mode"))
        extension_list_bar.addWidget(self.file_filter_mode_combo)
        extension_list_bar.addWidget(self.file_extension_list_edit, stretch=1)
        extension_layout.addLayout(extension_list_bar)
        files_layout.addWidget(extension_group)

        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.files_list.itemDoubleClicked.connect(self._show_source_file_context_menu_for_item)
        self.files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_list.customContextMenuRequested.connect(self._show_source_file_context_menu)
        files_layout.addWidget(self.files_list, stretch=1)

        file_button_bar = QHBoxLayout()
        file_button_bar.addWidget(
            self._build_options_button(
                [
                    ("Refresh", self._refresh_source_files),
                    ("Open Selected", self._open_selected_source_files),
                    ("Check Out Selected", self._checkout_selected),
                    ("Check In Selected (If Mine)", self._checkin_selected_source_files_if_owned),
                    ("View History", self._show_selected_file_history),
                    ("---", self._open_selected_source_files),
                    ("Add Selected To Favorites", self._add_selected_source_files_to_favorites),
                    ("Copy As Reference", self._copy_selected_as_reference),
                    ("Add Local File(s) To Here", self._add_new_files_to_source),
                ]
            )
        )
        file_button_bar.addStretch()
        files_layout.addLayout(file_button_bar)

        controlled_panel = QWidget()
        controlled_layout = QVBoxLayout(controlled_panel)
        controlled_layout.addWidget(QLabel("Directory"))
        self.directory_tabs = QTabWidget()
        self.controlled_files_table = QTableWidget(0, 3)
        self.controlled_files_table.setHorizontalHeaderLabels(["File Name", "Initials", "Checked Out"])
        self.controlled_files_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.controlled_files_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.controlled_files_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.controlled_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.controlled_files_table.customContextMenuRequested.connect(
            self._show_controlled_files_context_menu
        )
        controlled_header = self.controlled_files_table.horizontalHeader()
        controlled_header.setSectionResizeMode(0, QHeaderView.Stretch)
        controlled_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        controlled_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.directory_notes_table = QTableWidget(0, 3)
        self.directory_notes_table.setHorizontalHeaderLabels(["File Name", "Notes", "Last Modified"])
        self.directory_notes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.directory_notes_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.directory_notes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.directory_notes_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.directory_notes_table.customContextMenuRequested.connect(
            self._show_directory_notes_context_menu
        )
        notes_header = self.directory_notes_table.horizontalHeader()
        notes_header.setSectionResizeMode(0, QHeaderView.Stretch)
        notes_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        notes_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.directory_tabs.addTab(self.controlled_files_table, "Controlled Files")
        self.directory_tabs.addTab(self.directory_notes_table, "File Notes")
        controlled_layout.addWidget(self.directory_tabs, stretch=1)

        controlled_button_bar = QHBoxLayout()
        controlled_button_bar.addWidget(
            self._build_options_button(
                [
                    ("Refresh", self._refresh_controlled_files),
                    ("Force Check In", self._force_checkin_selected),
                    ("View File Notes", self._open_notes_for_selected_source_file),
                ]
            )
        )
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
        self.reference_records_table = self._build_reference_records_table()
        self.records_tabs.addTab(self.all_records_table, "All Checked Out")
        self.records_tabs.addTab(self.project_records_table, "Current Project")
        self.records_tabs.addTab(self.reference_records_table, "Reference Copies")
        layout.addWidget(self.records_tabs)

        button_bar = QHBoxLayout()
        button_bar.addWidget(
            self._build_options_button(
                [
                    ("Open Selected", self._open_selected_record_files),
                    ("Check In Selected", self._checkin_selected),
                    ("Create Revision Snapshot", self._create_revision_snapshot_for_selected_records),
                    ("Switch To Revision", self._switch_selected_record_to_revision),
                    ("Remove Selected Ref", self._remove_selected_reference_records),
                ]
            )
        )
        button_bar.addStretch()
        layout.addLayout(button_bar)

        return group

    def _build_global_favorites_group(self) -> QGroupBox:
        group = QGroupBox("Global Favorites")
        layout = QVBoxLayout(group)

        self.global_favorites_search_edit = QLineEdit()
        self.global_favorites_search_edit.setPlaceholderText("Search global favorites")
        self.global_favorites_search_edit.textChanged.connect(self._refresh_global_favorites_list)
        layout.addWidget(self.global_favorites_search_edit)

        self.global_favorites_list = QListWidget()
        self.global_favorites_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.global_favorites_list.itemDoubleClicked.connect(
            self._show_global_favorites_context_menu_for_item
        )
        self.global_favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.global_favorites_list.customContextMenuRequested.connect(
            self._show_global_favorites_context_menu
        )
        layout.addWidget(self.global_favorites_list, stretch=1)

        controls = QHBoxLayout()
        controls.addWidget(
            self._build_options_button(
                [
                    ("Add Favorite", self._browse_and_add_global_favorites),
                    ("Open Selected", self._open_selected_global_favorites),
                    ("Remove Selected", self._remove_selected_global_favorites),
                    ("Refresh", self._refresh_global_favorites_list),
                ]
            )
        )
        controls.addStretch()
        layout.addLayout(controls)
        return group

    def _build_global_notes_group(self) -> QGroupBox:
        group = QGroupBox("Global Notes")
        layout = QVBoxLayout(group)

        self.global_notes_search_edit = QLineEdit()
        self.global_notes_search_edit.setPlaceholderText("Search global notes")
        self.global_notes_search_edit.textChanged.connect(self._refresh_global_notes_list)
        layout.addWidget(self.global_notes_search_edit)

        self.global_notes_list = QListWidget()
        self.global_notes_list.itemDoubleClicked.connect(self._show_global_notes_context_menu_for_item)
        self.global_notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.global_notes_list.customContextMenuRequested.connect(self._show_global_notes_context_menu)
        layout.addWidget(self.global_notes_list, stretch=1)

        controls = QHBoxLayout()
        controls.addWidget(
            self._build_options_button(
                [
                    ("New Note", self._create_global_note),
                    ("Edit Selected", self._edit_selected_global_note),
                    ("Remove Selected", self._remove_selected_global_note),
                    ("Refresh", self._refresh_global_notes_list),
                ]
            )
        )
        controls.addStretch()
        layout.addLayout(controls)
        return group

    def _build_records_table(self) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ["Source", "Locked", "Local", "Initials", "Project", "Checked Out"]
        )
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.cellDoubleClicked.connect(self._show_records_context_menu_for_row)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_records_context_menu)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        return table

    def _build_reference_records_table(self) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Source", "Local", "Project", "Copied"])
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.cellDoubleClicked.connect(self._show_records_context_menu_for_row)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_records_context_menu)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        return table

    def _default_projects_dir(self) -> Path:
        return Path.home() / "Documents" / APP_NAME / "Projects"

    def _default_projects_registry_file(self) -> Path:
        return USER_DATA_ROOT / "projects.json"

    def _default_filter_presets_file(self) -> Path:
        return USER_DATA_ROOT / "filter_presets.json"

    def _default_records_file(self) -> Path:
        return USER_DATA_ROOT / "checkout_records.json"

    def _default_debug_events_file(self) -> Path:
        return DEBUG_EVENTS_FILE

    def _default_global_favorites_file(self) -> Path:
        return GLOBAL_FAVORITES_FILE

    def _default_global_notes_file(self) -> Path:
        return GLOBAL_NOTES_FILE

    def _base_projects_dir(self) -> Path:
        return Path(self.local_path_edit.text().strip() or self._default_projects_dir())

    def _projects_registry_path(self) -> Path:
        return Path(self.projects_file_edit.text().strip() or self._default_projects_registry_file())

    def _filter_presets_path(self) -> Path:
        return Path(
            self.filter_presets_file_edit.text().strip() or self._default_filter_presets_file()
        )

    def _records_file_path(self) -> Path:
        return Path(self.records_file_edit.text().strip() or self._default_records_file())

    def _debug_events_file_path(self) -> Path:
        return Path(self.debug_log_file_edit.text().strip() or self._default_debug_events_file())

    def _ensure_parent_dir(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _read_json_candidates(self, candidates: List[Path]) -> Optional[object]:
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
        return None

    def _choose_json_file_path(self, title: str, current_path: Path) -> Optional[Path]:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(current_path if current_path.name else current_path.parent),
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return None
        return Path(file_path)

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

    def _current_source_root_value(self) -> str:
        source_root = self._current_source_root()
        return str(source_root) if source_root else ""

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

    def _choose_projects_registry_file(self) -> None:
        path = self._choose_json_file_path(
            "Select Tracked Projects File", self._projects_registry_path()
        )
        if not path:
            return
        self.projects_file_edit.setText(str(path))
        self._save_settings()
        self._load_tracked_projects()
        self._load_last_or_default_project()

    def _choose_filter_presets_file(self) -> None:
        path = self._choose_json_file_path(
            "Select Filter Presets File", self._filter_presets_path()
        )
        if not path:
            return
        self.filter_presets_file_edit.setText(str(path))
        self._save_settings()
        self._load_filter_presets()

    def _choose_records_file(self) -> None:
        path = self._choose_json_file_path(
            "Select Checkout Records File", self._records_file_path()
        )
        if not path:
            return
        self.records_file_edit.setText(str(path))
        self._save_settings()
        self._load_records()

    def _choose_debug_log_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Debug Events Log File",
            str(self._debug_events_file_path()),
            "Log Files (*.log *.txt);;All Files (*)",
        )
        if not file_path:
            return
        self.debug_log_file_edit.setText(file_path)
        self._save_settings()
        self._debug_event("debug_log_file_changed", path=file_path)

    def _open_debug_log_file(self) -> None:
        self._open_paths([self._debug_events_file_path()])

    def _clear_debug_log_file(self) -> None:
        log_path = self._debug_events_file_path()
        self._ensure_parent_dir(log_path)
        log_path.write_text("", encoding="utf-8")
        self._debug_event("debug_log_cleared")
        self._info("Debug events log cleared.")

    def _debug_enabled(self) -> bool:
        return bool(self.debug_enabled_checkbox.isChecked())

    def _debug_event(self, event: str, **data: object) -> None:
        if not self._debug_enabled():
            return
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": event,
            "data": data,
        }
        log_path = self._debug_events_file_path()
        self._ensure_parent_dir(log_path)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    @contextmanager
    def _debug_timed(self, event: str, **data: object):
        started = perf_counter()
        try:
            yield
        finally:
            duration_ms = round((perf_counter() - started) * 1000.0, 3)
            self._debug_event(event, duration_ms=duration_ms, **data)

    def _on_debug_logging_toggled(self, enabled: bool) -> None:
        self._save_settings()
        self._debug_event("debug_logging_toggled", enabled=bool(enabled))

    @contextmanager
    def _busy_action(self, message: str):
        self._debug_event("busy_action_start", message=message)
        started = perf_counter()
        self._busy_action_depth += 1
        dialog = QDialog(self)
        dialog.setWindowTitle(APP_NAME)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setMinimumWidth(420)
        dialog.setWindowFlag(Qt.WindowCloseButtonHint, False)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setMinimumWidth(360)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(label)
        layout.addWidget(progress)
        dialog.adjustSize()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.repaint()
        label.repaint()
        progress.repaint()
        QApplication.processEvents()
        try:
            yield
        finally:
            dialog.close()
            dialog.deleteLater()
            QApplication.processEvents()
            self._busy_action_depth = max(0, self._busy_action_depth - 1)
            duration_ms = round((perf_counter() - started) * 1000.0, 3)
            self._debug_event("busy_action_end", message=message, duration_ms=duration_ms)

    def _show_startup_splash(self, message: str) -> None:
        dialog = QDialog(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        dialog.setModal(False)
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        label = QLabel(message)
        label.setWordWrap(True)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(title)
        layout.addWidget(label)
        layout.addWidget(progress)
        dialog.adjustSize()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.repaint()
        QApplication.processEvents()
        self._startup_splash_dialog = dialog
        self._startup_splash_label = label
        self._debug_event("startup_splash_show", message=message)

    def _update_startup_splash(self, message: str) -> None:
        if self._startup_splash_label is None:
            return
        self._startup_splash_label.setText(message)
        if self._startup_splash_dialog is not None:
            self._startup_splash_dialog.repaint()
        self._startup_splash_label.repaint()
        QApplication.processEvents()
        self._debug_event("startup_splash_update", message=message)

    def _close_startup_splash(self) -> None:
        if self._startup_splash_dialog is not None:
            self._startup_splash_dialog.close()
            self._startup_splash_dialog.deleteLater()
        self._startup_splash_dialog = None
        self._startup_splash_label = None
        QApplication.processEvents()
        self._debug_event("startup_splash_closed")

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

    def _settings_payload(self) -> Dict[str, object]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "initials": self._normalize_initials(),
            "full_name": self._current_full_name(),
            "base_projects_dir": str(self._base_projects_dir()),
            "current_project_dir": self.current_project_dir,
            "tracked_projects_file": str(self._projects_registry_path()),
            "filter_presets_file": str(self._filter_presets_path()),
            "records_file": str(self._records_file_path()),
            "debug_events_file": str(self._debug_events_file_path()),
            "debug_events_enabled": self._debug_enabled(),
        }

    def _has_user_configuration(self) -> bool:
        initials = self.initials_edit.text().strip()
        full_name = self.full_name_edit.text().strip()
        base_dir = self.local_path_edit.text().strip()
        projects_file = self.projects_file_edit.text().strip()
        filter_presets_file = self.filter_presets_file_edit.text().strip()
        records_file = self.records_file_edit.text().strip()
        debug_file = self.debug_log_file_edit.text().strip()
        debug_enabled = self._debug_enabled()
        return bool(
            initials
            or full_name
            or (base_dir and Path(base_dir) != self._default_projects_dir())
            or (projects_file and Path(projects_file) != self._default_projects_registry_file())
            or (filter_presets_file and Path(filter_presets_file) != self._default_filter_presets_file())
            or (records_file and Path(records_file) != self._default_records_file())
            or (debug_file and Path(debug_file) != self._default_debug_events_file())
            or debug_enabled
        )

    def _apply_startup_tab(self) -> None:
        self.main_tabs.setCurrentIndex(1 if self.show_configuration_tab_on_startup else 0)

    def _load_settings(self) -> None:
        self.local_path_edit.setText(str(self._default_projects_dir()))
        self.projects_file_edit.setText(str(self._default_projects_registry_file()))
        self.filter_presets_file_edit.setText(str(self._default_filter_presets_file()))
        self.records_file_edit.setText(str(self._default_records_file()))
        self.debug_log_file_edit.setText(str(self._default_debug_events_file()))
        self.debug_enabled_checkbox.blockSignals(True)
        self.debug_enabled_checkbox.setChecked(False)
        self.debug_enabled_checkbox.blockSignals(False)
        data = self._read_json_candidates([SETTINGS_FILE, LEGACY_SETTINGS_FILE])
        if data is None or not isinstance(data, dict):
            self.show_configuration_tab_on_startup = True
            self._apply_startup_tab()
            return

        self.initials_edit.setText(str(data.get("initials", "")).strip())
        self.full_name_edit.setText(str(data.get("full_name", "")).strip())
        base_dir = str(data.get("base_projects_dir", "")).strip()
        if base_dir:
            self.local_path_edit.setText(base_dir)
        tracked_projects_file = str(data.get("tracked_projects_file", "")).strip()
        if tracked_projects_file:
            self.projects_file_edit.setText(tracked_projects_file)
        filter_presets_file = str(data.get("filter_presets_file", "")).strip()
        if filter_presets_file:
            self.filter_presets_file_edit.setText(filter_presets_file)
        records_file = str(data.get("records_file", "")).strip()
        if records_file:
            self.records_file_edit.setText(records_file)
        debug_events_file = str(data.get("debug_events_file", "")).strip()
        if debug_events_file:
            self.debug_log_file_edit.setText(debug_events_file)
        debug_events_enabled = bool(data.get("debug_events_enabled", False))
        self.debug_enabled_checkbox.blockSignals(True)
        self.debug_enabled_checkbox.setChecked(debug_events_enabled)
        self.debug_enabled_checkbox.blockSignals(False)
        self.current_project_dir = str(data.get("current_project_dir", "")).strip()
        self.show_configuration_tab_on_startup = not self._has_user_configuration()
        self._apply_startup_tab()

    def _save_settings(self) -> None:
        self._ensure_parent_dir(SETTINGS_FILE)
        SETTINGS_FILE.write_text(
            json.dumps(self._settings_payload(), indent=2), encoding="utf-8"
        )

    def _load_tracked_projects(self) -> None:
        self.tracked_projects = []
        data = self._read_json_candidates(
            [self._projects_registry_path(), LEGACY_PROJECTS_FILE]
        )
        if isinstance(data, dict):
            tracked = data.get("tracked_projects", [])
        else:
            tracked = data
        if isinstance(tracked, list):
            for entry in tracked:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                project_dir = str(entry.get("project_dir", "")).strip()
                client = str(entry.get("client", "")).strip()
                year_started = str(entry.get("year_started", "")).strip()
                if name and project_dir:
                    self.tracked_projects.append(
                        {
                            "name": name,
                            "project_dir": project_dir,
                            "client": client,
                            "year_started": year_started,
                        }
                    )

        if not self.tracked_projects:
            self._ensure_default_project()
        else:
            self._refresh_tracked_projects_list()

    def _save_tracked_projects(self) -> None:
        payload = {
            "schema_version": TRACKED_PROJECTS_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "tracked_projects": self.tracked_projects,
        }
        projects_path = self._projects_registry_path()
        self._ensure_parent_dir(projects_path)
        projects_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _project_payload(
        self,
        name: str,
        sources: List[str],
        extension_filters: Optional[List[str]] = None,
        filter_mode: str = "No Filter",
        favorites: Optional[List[str]] = None,
        notes: Optional[List[Dict[str, str]]] = None,
        milestones: Optional[List[Dict[str, object]]] = None,
        selected_source: str = "",
        source_ids: Optional[Dict[str, str]] = None,
        client: str = "",
        year_started: str = "",
    ) -> Dict[str, object]:
        normalized_source_ids = self._normalize_source_ids(sources, source_ids)
        return {
            "schema_version": PROJECT_CONFIG_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "name": name,
            "client": client,
            "year_started": year_started,
            "sources": sources,
            "source_ids": normalized_source_ids,
            "selected_source": selected_source,
            "extension_filters": extension_filters or [],
            "filter_mode": filter_mode,
            "favorites": favorites or [],
            "notes": notes or [],
            "milestones": milestones or [],
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
        raw_milestones = data.get("milestones", [])
        selected_source = str(data.get("selected_source", "")).strip()
        client = str(data.get("client", "")).strip()
        year_started = str(data.get("year_started", "")).strip()
        raw_source_ids = data.get("source_ids", {})
        sources = [str(item) for item in raw_sources if str(item).strip()] if isinstance(raw_sources, list) else []
        source_ids = dict(raw_source_ids) if isinstance(raw_source_ids, dict) else {}
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
        milestones: List[Dict[str, object]] = []
        if isinstance(raw_milestones, list):
            for entry in raw_milestones:
                normalized = self._normalize_milestone_entry(entry)
                if normalized:
                    milestones.append(normalized)
        if filter_mode not in {"No Filter", "Include Only", "Exclude"}:
            filter_mode = "No Filter"
        return self._project_payload(
            name,
            sources,
            extension_filters,
            filter_mode,
            favorites,
            notes,
            milestones,
            selected_source,
            source_ids,
            client,
            year_started,
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
        milestones: Optional[List[Dict[str, object]]] = None,
        selected_source: str = "",
        source_ids: Optional[Dict[str, str]] = None,
        client: str = "",
        year_started: str = "",
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
            milestones,
            selected_source,
            source_ids,
            client,
            year_started,
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
        milestones: Optional[List[Dict[str, object]]] = None,
        selected_source: Optional[str] = None,
        source_ids: Optional[Dict[str, str]] = None,
        client: Optional[str] = None,
        year_started: Optional[str] = None,
    ) -> None:
        current = self._read_project_config(project_dir)
        merged_sources = (
            sources if sources is not None else list(current.get("sources", []))  # type: ignore[arg-type]
        )
        self._write_project_config(
            project_dir,
            name or str(current.get("name", project_dir.name)),
            merged_sources,
            extension_filters
            if extension_filters is not None
            else list(current.get("extension_filters", [])),  # type: ignore[arg-type]
            filter_mode or str(current.get("filter_mode", "No Filter")),
            favorites if favorites is not None else list(current.get("favorites", [])),  # type: ignore[arg-type]
            notes if notes is not None else list(current.get("notes", [])),  # type: ignore[arg-type]
            milestones
            if milestones is not None
            else list(current.get("milestones", [])),  # type: ignore[arg-type]
            selected_source
            if selected_source is not None
            else str(current.get("selected_source", "")),
            source_ids
            if source_ids is not None
            else dict(current.get("source_ids", {})),  # type: ignore[arg-type]
            client if client is not None else str(current.get("client", "")),
            year_started
            if year_started is not None
            else str(current.get("year_started", "")),
        )

    def _ensure_default_project(self) -> None:
        base_dir = self._ensure_base_projects_dir()
        default_dir = base_dir / DEFAULT_PROJECT_NAME
        if not self._project_config_path(default_dir).exists():
            self._write_project_config(
                default_dir,
                DEFAULT_PROJECT_NAME,
                [],
                [],
                "No Filter",
                [],
                [],
            )
        self._register_tracked_project(DEFAULT_PROJECT_NAME, default_dir)
        self._refresh_tracked_projects_list()

    def _register_tracked_project(
        self,
        name: str,
        project_dir: Path,
        client: str = "",
        year_started: str = "",
    ) -> None:
        project_dir_str = str(project_dir)
        changed = False
        found = False
        for entry in self.tracked_projects:
            if entry["project_dir"] == project_dir_str:
                found = True
                if (
                    entry.get("name") != name
                    or entry.get("client", "") != client
                    or entry.get("year_started", "") != year_started
                ):
                    entry["name"] = name
                    entry["client"] = client
                    entry["year_started"] = year_started
                    changed = True
                break

        if not found:
            self.tracked_projects.append(
                {
                    "name": name,
                    "project_dir": project_dir_str,
                    "client": client,
                    "year_started": year_started,
                }
            )
            changed = True

        if changed:
            self.tracked_projects.sort(key=lambda item: item["name"].lower())
            self._save_tracked_projects()
        self._refresh_tracked_projects_list()

    def _refresh_tracked_projects_list(self) -> None:
        self.tracked_projects_list.clear()
        current_item = None
        search_term = self.project_search_edit.text().strip().lower()
        for entry in self.tracked_projects:
            if search_term and search_term not in " ".join(
                [
                    str(entry.get("name", "")).lower(),
                    str(entry.get("client", "")).lower(),
                    str(entry.get("year_started", "")).lower(),
                ]
            ):
                continue
            item = QListWidgetItem(entry["name"])
            item.setData(Qt.UserRole, entry["project_dir"])
            tooltip_lines = [entry["project_dir"]]
            if entry.get("client"):
                tooltip_lines.append(f"Client: {entry['client']}")
            if entry.get("year_started"):
                tooltip_lines.append(f"Year Started: {entry['year_started']}")
            item.setToolTip("\n".join(tooltip_lines))
            self.tracked_projects_list.addItem(item)
            if entry["project_dir"] == self.current_project_dir:
                current_item = item

        if current_item:
            self.tracked_projects_list.setCurrentItem(current_item)
        elif self.tracked_projects_list.count() > 0:
            self.tracked_projects_list.setCurrentRow(0)

    def _on_project_search_changed(self, _text: str) -> None:
        self.project_search_debounce.start()

    def _on_file_search_changed(self, _text: str) -> None:
        self.file_search_debounce.start()

    def _move_list_widget_item(self, list_widget: QListWidget, delta: int) -> bool:
        row = list_widget.currentRow()
        if row < 0:
            return False
        new_row = row + delta
        if new_row < 0 or new_row >= list_widget.count():
            return False
        item = list_widget.takeItem(row)
        list_widget.insertItem(new_row, item)
        list_widget.setCurrentRow(new_row)
        item.setSelected(True)
        return True

    def _move_list_widget_item_to(self, list_widget: QListWidget, target_row: int) -> bool:
        row = list_widget.currentRow()
        if row < 0:
            return False
        target_row = max(0, min(target_row, list_widget.count() - 1))
        if row == target_row:
            return False
        item = list_widget.takeItem(row)
        list_widget.insertItem(target_row, item)
        list_widget.setCurrentRow(target_row)
        item.setSelected(True)
        return True

    def _build_options_button(
        self, actions: List[Tuple[str, Callable[[], None]]], label: str = "Options"
    ) -> QToolButton:
        button = QToolButton(self)
        button.setText(label)
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)
        for action_label, callback in actions:
            if action_label == "---":
                menu.addSeparator()
                continue
            action = menu.addAction(action_label)
            action.triggered.connect(callback)
        button.setMenu(menu)
        return button

    def _clear_file_search_filter(self) -> None:
        if not self.file_search_edit.text():
            return
        self.file_search_debounce.stop()
        self.file_search_edit.blockSignals(True)
        self.file_search_edit.clear()
        self.file_search_edit.blockSignals(False)
        self._debug_event("file_search_cleared")

    def _refresh_source_files_with_feedback(self, message: str) -> None:
        if not self.current_directory or not self.current_directory.is_dir():
            self._refresh_source_files()
            return
        with self._busy_action(message):
            self._refresh_source_files()

    def _refresh_source_files_from_search(self) -> None:
        self._refresh_source_files_with_feedback("Filtering source files...")

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
        milestones: Optional[List[Dict[str, object]]] = None,
        client: str = "",
        year_started: str = "",
    ) -> None:
        base_dir = self._ensure_base_projects_dir()
        _ = base_dir

        source_list = sources or []
        with self._debug_timed("create_or_update_project", project_name=name):
            with self._busy_action("Creating project..."):
                self._write_project_config(
                    project_dir=project_dir,
                    name=name,
                    sources=source_list,
                    extension_filters=extension_filters or [],
                    filter_mode=filter_mode,
                    favorites=favorites or [],
                    notes=notes or [],
                    milestones=milestones or [],
                    selected_source=source_list[0] if source_list else "",
                    source_ids=None,
                    client=client,
                    year_started=year_started,
                )
                self._register_tracked_project(name, project_dir, client, year_started)
                self._load_project_from_dir(project_dir)
                self._save_settings()
        self._info(f"Project '{name}' saved.")

    def _resolve_new_project_name(self, entered_name: str, source_dir: str) -> str:
        name = entered_name.strip()
        source_dir_value = source_dir.strip()
        if not source_dir_value:
            return name

        suggested_name = Path(source_dir_value).name.strip()
        if not suggested_name:
            return name

        if not name:
            answer = QMessageBox.question(
                self,
                "Project Name Suggestion",
                f"Use source folder name '{suggested_name}' as the project name?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            return suggested_name if answer == QMessageBox.Yes else ""

        if suggested_name != name:
            answer = QMessageBox.question(
                self,
                "Project Name Suggestion",
                (
                    f"Use source folder name '{suggested_name}' as the project name instead "
                    f"of '{name}'?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                return suggested_name
        return name

    def _show_new_project_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("New Project")
        dialog.resize(640, 280)
        layout = QVBoxLayout(dialog)

        form_layout = QGridLayout()
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Project name")
        if self.current_directory and self.current_directory.name:
            name_edit.setText(self.current_directory.name)
        client_edit = QLineEdit()
        client_edit.setPlaceholderText("Optional client name")
        year_edit = QLineEdit()
        year_edit.setValidator(QIntValidator(1900, 9999, dialog))
        year_edit.setPlaceholderText("YYYY")
        source_dir_edit = QLineEdit(str(self.current_directory) if self.current_directory else "")
        source_dir_edit.setPlaceholderText("Optional source directory")
        browse_source_btn = QPushButton("Browse")

        def choose_source_dir() -> None:
            start_dir = source_dir_edit.text().strip() or str(self.current_directory or Path.home())
            selected = QFileDialog.getExistingDirectory(dialog, "Select Source Directory", start_dir)
            if selected:
                source_dir_edit.setText(selected)
                if not name_edit.text().strip():
                    source_name = Path(selected).name.strip()
                    if source_name:
                        name_edit.setText(source_name)

        browse_source_btn.clicked.connect(choose_source_dir)
        form_layout.addWidget(QLabel("Project Name:"), 0, 0)
        form_layout.addWidget(name_edit, 0, 1)
        form_layout.addWidget(QLabel("Client:"), 1, 0)
        form_layout.addWidget(client_edit, 1, 1)
        form_layout.addWidget(QLabel("Year Started:"), 2, 0)
        form_layout.addWidget(year_edit, 2, 1)
        form_layout.addWidget(QLabel("Source Directory:"), 3, 0)
        form_layout.addWidget(source_dir_edit, 3, 1)
        form_layout.addWidget(browse_source_btn, 3, 2)
        layout.addLayout(form_layout)

        track_source_checkbox = QCheckBox("Track selected source directory on create")
        track_source_checkbox.setChecked(bool(source_dir_edit.text().strip()))
        copy_sources_checkbox = QCheckBox("Copy tracked source directories from current project")
        copy_filter_settings_checkbox = QCheckBox("Copy extension filter settings from current project")
        layout.addWidget(track_source_checkbox)
        layout.addWidget(copy_sources_checkbox)
        layout.addWidget(copy_filter_settings_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        client = client_edit.text().strip()
        year_started = year_edit.text().strip()
        source_dir = source_dir_edit.text().strip()
        if year_started and len(year_started) != 4:
            self._error("Year Started must be a 4-digit year.")
            return

        if source_dir:
            source_path = Path(source_dir)
            if not source_path.is_dir():
                self._error("Selected source directory does not exist.")
                return

        name = self._resolve_new_project_name(name_edit.text(), source_dir)
        if not name:
            self._error("Project name is required.")
            return

        project_dir = self._ensure_base_projects_dir() / self._safe_project_dir_name(name)
        sources: List[str] = []
        extension_filters: List[str] = []
        filter_mode = "No Filter"
        if copy_sources_checkbox.isChecked():
            sources = self._source_roots_from_list()
        if track_source_checkbox.isChecked() and source_dir:
            if source_dir not in sources:
                sources.append(source_dir)
        if copy_filter_settings_checkbox.isChecked():
            extension_filters = self._current_extension_filters()
            filter_mode = self.file_filter_mode_combo.currentText()

        self._create_or_update_project(
            name,
            project_dir,
            sources=sources,
            extension_filters=extension_filters,
            filter_mode=filter_mode,
            client=client,
            year_started=year_started,
        )

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
        with self._busy_action("Loading project..."):
            self._load_project_from_dir(Path(item.data(Qt.UserRole)))

    def _load_tracked_project_item(self, item: QListWidgetItem) -> None:
        with self._busy_action("Loading project..."):
            self._load_project_from_dir(Path(str(item.data(Qt.UserRole))))

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
        self._register_tracked_project(
            str(config.get("name", project_dir.name)),
            project_dir,
            str(config.get("client", "")),
            str(config.get("year_started", "")),
        )
        with self._busy_action("Loading project..."):
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
        active_project_records = [record for record in self.records if record.project_dir == str(project_dir)]
        if active_project_records:
            answer = QMessageBox.question(
                self,
                "Project Has Checked-Out Files",
                (
                    f"'{item.text()}' has {len(active_project_records)} checked-out file(s).\n\n"
                    "Please check those files in before untracking this project.\n\n"
                    "Keep project tracked?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                return

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
        with self._debug_timed("load_project", project_dir=str(project_dir)):
            config = self._read_project_config(project_dir)
            name = str(config.get("name", project_dir.name))
            sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]
            extension_filters = [
                str(item) for item in config.get("extension_filters", [])
            ]  # type: ignore[arg-type]
            filter_mode = str(config.get("filter_mode", "No Filter"))
            favorites = [str(item) for item in config.get("favorites", [])]  # type: ignore[arg-type]
            notes = [dict(item) for item in config.get("notes", [])]  # type: ignore[arg-type]
            selected_source = str(config.get("selected_source", "")).strip()
            client = str(config.get("client", "")).strip()
            year_started = str(config.get("year_started", "")).strip()

            self.current_project_dir = str(project_dir)
            self.file_filter_mode_combo.blockSignals(True)
            self.file_filter_mode_combo.setCurrentText(filter_mode)
            self.file_filter_mode_combo.blockSignals(False)
            self._clear_file_search_filter()
            self._set_extension_filters(extension_filters)
            self.current_project_label.setText(f"Current Project: {name}")
            self._register_tracked_project(name, project_dir, client, year_started)
            self._refresh_source_roots(sources, selected_source)
            self._refresh_favorites_list(favorites)
            self._refresh_notes_list(notes)
            if not sources:
                self._refresh_controlled_files()
            self._save_settings()
            self._render_records_tables()

    def _selected_tracked_project_dir(self) -> Optional[Path]:
        item = self.tracked_projects_list.currentItem()
        if not item:
            return None
        return Path(str(item.data(Qt.UserRole)))

    def _select_tracked_project_by_dir(self, project_dir: str) -> None:
        for row in range(self.tracked_projects_list.count()):
            item = self.tracked_projects_list.item(row)
            if str(item.data(Qt.UserRole)) == project_dir:
                self.tracked_projects_list.setCurrentItem(item)
                return

    def _move_selected_project(self, delta: int) -> None:
        item = self.tracked_projects_list.currentItem()
        if not item:
            self._error("Select a tracked project to move.")
            return

        project_dir = str(item.data(Qt.UserRole))
        index = -1
        for idx, entry in enumerate(self.tracked_projects):
            if entry["project_dir"] == project_dir:
                index = idx
                break
        if index < 0:
            return
        new_index = index + delta
        if new_index < 0 or new_index >= len(self.tracked_projects):
            return
        self.tracked_projects[index], self.tracked_projects[new_index] = (
            self.tracked_projects[new_index],
            self.tracked_projects[index],
        )
        self._save_tracked_projects()
        self._refresh_tracked_projects_list()
        self._select_tracked_project_by_dir(project_dir)

    def _move_selected_project_to(self, target_index: int) -> None:
        item = self.tracked_projects_list.currentItem()
        if not item:
            self._error("Select a tracked project to move.")
            return
        project_dir = str(item.data(Qt.UserRole))
        index = -1
        for idx, entry in enumerate(self.tracked_projects):
            if entry["project_dir"] == project_dir:
                index = idx
                break
        if index < 0:
            return
        target_index = max(0, min(target_index, len(self.tracked_projects) - 1))
        if index == target_index:
            return
        entry = self.tracked_projects.pop(index)
        self.tracked_projects.insert(target_index, entry)
        self._save_tracked_projects()
        self._refresh_tracked_projects_list()
        self._select_tracked_project_by_dir(project_dir)

    def _move_selected_project_up(self) -> None:
        self._move_selected_project(-1)

    def _move_selected_project_down(self) -> None:
        self._move_selected_project(1)

    def _move_selected_project_top(self) -> None:
        self._move_selected_project_to(0)

    def _move_selected_project_bottom(self) -> None:
        self._move_selected_project_to(len(self.tracked_projects) - 1)

    def _update_project_record_paths(
        self, old_project_dir: Path, new_project_dir: Path, new_project_name: str
    ) -> None:
        old_project_dir_str = str(old_project_dir)
        for record in self.records:
            if record.project_dir != old_project_dir_str:
                continue
            record.project_dir = str(new_project_dir)
            record.project_name = new_project_name
            try:
                relative_local = Path(record.local_file).relative_to(old_project_dir)
                record.local_file = str(new_project_dir / relative_local)
            except ValueError:
                pass
        self._save_records()

    def _apply_project_edit(
        self,
        old_project_dir: Path,
        new_project_name: str,
        destination_parent: Optional[Path],
        client: str,
        year_started: str,
    ) -> Optional[Path]:
        config = self._read_project_config(old_project_dir)
        target_parent = destination_parent or old_project_dir.parent
        target_parent = target_parent.resolve()
        target_project_dir = target_parent / self._safe_project_dir_name(new_project_name)
        old_project_dir_resolved = old_project_dir.resolve()

        if target_project_dir == old_project_dir_resolved:
            self._save_project_config(
                old_project_dir,
                name=new_project_name,
                client=client,
                year_started=year_started,
            )
            self._register_tracked_project(new_project_name, old_project_dir, client, year_started)
            self._update_project_record_paths(old_project_dir, old_project_dir, new_project_name)
            return old_project_dir

        if target_project_dir.exists():
            self._error(f"Destination already exists:\n{target_project_dir}")
            return None

        try:
            target_parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_project_dir_resolved), str(target_project_dir))
        except OSError as exc:
            self._error(f"Could not migrate project directory:\n{exc}")
            return None

        self.tracked_projects = [
            entry
            for entry in self.tracked_projects
            if entry["project_dir"] != str(old_project_dir_resolved)
        ]
        self._save_project_config(
            target_project_dir,
            name=new_project_name,
            sources=[str(item) for item in config.get("sources", [])],  # type: ignore[arg-type]
            extension_filters=[
                str(item) for item in config.get("extension_filters", [])
            ],  # type: ignore[arg-type]
            filter_mode=str(config.get("filter_mode", "No Filter")),
            favorites=[str(item) for item in config.get("favorites", [])],  # type: ignore[arg-type]
            notes=[dict(item) for item in config.get("notes", [])],  # type: ignore[arg-type]
            milestones=[dict(item) for item in config.get("milestones", [])],  # type: ignore[arg-type]
            selected_source=str(config.get("selected_source", "")),
            source_ids=(
                dict(config.get("source_ids", {}))
                if isinstance(config.get("source_ids", {}), dict)
                else {}
            ),
            client=client,
            year_started=year_started,
        )
        self._register_tracked_project(new_project_name, target_project_dir, client, year_started)
        self._update_project_record_paths(old_project_dir_resolved, target_project_dir, new_project_name)
        return target_project_dir

    def _edit_selected_project(self) -> None:
        project_dir = self._selected_tracked_project_dir()
        if not project_dir or not project_dir.is_dir():
            self._error("Select a tracked project to edit.")
            return

        config = self._read_project_config(project_dir)
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Project")
        dialog.resize(720, 320)
        layout = QVBoxLayout(dialog)

        form = QGridLayout()
        name_edit = QLineEdit(str(config.get("name", project_dir.name)))
        client_edit = QLineEdit(str(config.get("client", "")))
        year_edit = QLineEdit(str(config.get("year_started", "")))
        year_edit.setValidator(QIntValidator(1900, 9999, dialog))
        year_edit.setPlaceholderText("YYYY")
        current_dir_label = QLineEdit(str(project_dir))
        current_dir_label.setReadOnly(True)
        config_path_label = QLineEdit(str(self._project_config_path(project_dir)))
        config_path_label.setReadOnly(True)
        sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]
        source_count_label = QLineEdit(str(len(sources)))
        source_count_label.setReadOnly(True)
        destination_edit = QLineEdit(str(project_dir.parent))
        browse_destination_btn = QPushButton("Browse")

        def choose_destination() -> None:
            selected = QFileDialog.getExistingDirectory(
                dialog,
                "Select Project Destination Directory",
                destination_edit.text().strip() or str(project_dir.parent),
            )
            if selected:
                destination_edit.setText(selected)

        browse_destination_btn.clicked.connect(choose_destination)

        form.addWidget(QLabel("Project Name:"), 0, 0)
        form.addWidget(name_edit, 0, 1, 1, 2)
        form.addWidget(QLabel("Client:"), 1, 0)
        form.addWidget(client_edit, 1, 1, 1, 2)
        form.addWidget(QLabel("Year Started:"), 2, 0)
        form.addWidget(year_edit, 2, 1, 1, 2)
        form.addWidget(QLabel("Current Directory:"), 3, 0)
        form.addWidget(current_dir_label, 3, 1, 1, 2)
        form.addWidget(QLabel("Project Config:"), 4, 0)
        form.addWidget(config_path_label, 4, 1, 1, 2)
        form.addWidget(QLabel("Tracked Sources:"), 5, 0)
        form.addWidget(source_count_label, 5, 1, 1, 2)
        form.addWidget(QLabel("Destination Parent:"), 6, 0)
        form.addWidget(destination_edit, 6, 1)
        form.addWidget(browse_destination_btn, 6, 2)
        layout.addLayout(form)

        layout.addWidget(
            QLabel(
                "Changing the project name or destination will migrate the project directory "
                "and update tracked-project entries and checkout records."
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        new_project_name = name_edit.text().strip()
        if not new_project_name:
            self._error("Project name is required.")
            return
        client = client_edit.text().strip()
        year_started = year_edit.text().strip()
        if year_started and len(year_started) != 4:
            self._error("Year Started must be a 4-digit year.")
            return

        destination_parent = Path(destination_edit.text().strip() or str(project_dir.parent))
        with self._busy_action("Updating project..."):
            updated_project_dir = self._apply_project_edit(
                project_dir,
                new_project_name,
                destination_parent,
                client,
                year_started,
            )
        if not updated_project_dir:
            return

        if self.current_project_dir == str(project_dir):
            self.current_project_dir = str(updated_project_dir)
            with self._busy_action("Loading project..."):
                self._load_project_from_dir(updated_project_dir)
        else:
            self._refresh_tracked_projects_list()
            self._render_records_tables()
        self._save_settings()
        self._info(f"Project '{new_project_name}' updated.")

    def _open_selected_project_location(self) -> None:
        project_dir = self._selected_tracked_project_dir()
        if not project_dir or not project_dir.is_dir():
            self._error("Select a tracked project to open.")
            return
        self._open_paths([project_dir])

    def _open_project_files_manager_for_selected_project(self) -> None:
        project_dir = self._selected_tracked_project_dir()
        if not project_dir or not project_dir.is_dir():
            self._error("Select a tracked project first.")
            return
        self._show_project_files_manager(project_dir)

    def _project_file_manager_rows(self, project_dir: Path, record_type: str) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        tracked_local_files: set[str] = set()
        for idx, record in enumerate(self.records):
            if record.project_dir != str(project_dir):
                continue
            tracked_local_files.add(str(Path(record.local_file)))
            if record_type not in {"all", record.record_type}:
                continue
            revision_count = len(self._revision_entries_for_record(record)) if record.record_type == "checked_out" else 0
            rows.append(
                {
                    "record_idx": idx,
                    "record_type": record.record_type,
                    "file_name": Path(record.local_file).name or Path(record.source_file).name,
                    "local_file": record.local_file,
                    "source_file": record.source_file,
                    "revisions": revision_count,
                }
            )

        if record_type in {"all", "untracked"}:
            skip_file_names = {PROJECT_CONFIG_FILE, FILE_VERSIONS_FILE}
            for local_path in project_dir.rglob("*"):
                if not local_path.is_file():
                    continue
                if local_path.name in skip_file_names:
                    continue
                if FILE_VERSIONS_DIR in local_path.parts:
                    continue
                local_path_str = str(local_path)
                if local_path_str in tracked_local_files:
                    continue
                rows.append(
                    {
                        "record_idx": -1,
                        "record_type": "untracked",
                        "file_name": local_path.name,
                        "local_file": local_path_str,
                        "source_file": "",
                        "revisions": 0,
                    }
                )
        rows.sort(key=lambda item: str(item["file_name"]).lower())
        return rows

    def _apply_project_file_search(
        self, rows: List[Dict[str, object]], search_term: str
    ) -> List[Dict[str, object]]:
        term = search_term.strip().lower()
        if not term:
            return rows
        filtered: List[Dict[str, object]] = []
        for row in rows:
            haystack = " ".join(
                [
                    str(row.get("file_name", "")),
                    str(row.get("local_file", "")),
                    str(row.get("source_file", "")),
                    str(row.get("record_type", "")),
                ]
            ).lower()
            if term in haystack:
                filtered.append(row)
        return filtered

    def _populate_project_files_manager_table(
        self, table: QTableWidget, rows: List[Dict[str, object]], search_term: str
    ) -> None:
        visible_rows = self._apply_project_file_search(rows, search_term)
        table.setRowCount(len(visible_rows))
        for row_idx, row in enumerate(visible_rows):
            record_type = str(row.get("record_type", ""))
            type_label = "Untracked"
            if record_type == "checked_out":
                type_label = "Checked Out"
            elif record_type == "reference_copy":
                type_label = "Reference Copy"
            values = [
                str(row.get("file_name", "")),
                type_label,
                str(row.get("revisions", 0)),
                self._short_path(str(row.get("local_file", ""))),
                self._short_path(str(row.get("source_file", ""))),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_idx == 0:
                    item.setData(Qt.UserRole, int(row.get("record_idx", -1)))
                    item.setData(Qt.UserRole + 1, dict(row))
                if col_idx == 3:
                    item.setToolTip(str(row.get("local_file", "")))
                elif col_idx == 4:
                    item.setToolTip(str(row.get("source_file", "")))
                else:
                    item.setToolTip(value)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 180))
        table.setColumnWidth(1, max(table.columnWidth(1), 110))
        table.setColumnWidth(2, max(table.columnWidth(2), 80))
        table.setColumnWidth(3, max(table.columnWidth(3), 220))
        table.setColumnWidth(4, max(table.columnWidth(4), 220))

    def _selected_record_indexes_from_manager_table(self, table: QTableWidget) -> List[int]:
        indexes: List[int] = []
        for row in sorted({idx.row() for idx in table.selectedIndexes()}):
            item = table.item(row, 0)
            if not item:
                continue
            record_idx = item.data(Qt.UserRole)
            if isinstance(record_idx, int):
                indexes.append(record_idx)
        return indexes

    def _selected_rows_from_manager_table(self, table: QTableWidget) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for row in sorted({idx.row() for idx in table.selectedIndexes()}):
            item = table.item(row, 0)
            if not item:
                continue
            data = item.data(Qt.UserRole + 1)
            if isinstance(data, dict):
                rows.append(dict(data))
        return rows

    def _choose_project_transfer_target(self, current_project_dir: Path) -> Optional[Path]:
        candidates = [
            entry
            for entry in self.tracked_projects
            if str(entry.get("project_dir", "")) != str(current_project_dir)
            and Path(str(entry.get("project_dir", ""))).is_dir()
        ]
        if not candidates:
            self._error("No other tracked projects are available as transfer targets.")
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Target Project")
        dialog.resize(520, 140)
        layout = QVBoxLayout(dialog)
        combo = QComboBox()
        for entry in candidates:
            label = str(entry.get("name", "")) or Path(str(entry.get("project_dir", ""))).name
            combo.addItem(label, str(entry.get("project_dir", "")))
        layout.addWidget(QLabel("Move/copy selected file(s) to:"))
        layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        return Path(str(combo.currentData()))

    def _ensure_unique_destination_path(self, target_file: Path) -> Path:
        if not target_file.exists():
            return target_file
        stem = target_file.stem
        suffix = target_file.suffix
        parent = target_file.parent
        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _target_transfer_path(self, src_file: Path, src_project_dir: Path, target_project_dir: Path) -> Path:
        try:
            relative = src_file.relative_to(src_project_dir)
        except ValueError:
            relative = Path(src_file.name)
        destination = target_project_dir / "incoming" / src_project_dir.name / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        return self._ensure_unique_destination_path(destination)

    def _transfer_project_files(
        self,
        selected_rows: List[Dict[str, object]],
        source_project_dir: Path,
        target_project_dir: Path,
        mode: str,
    ) -> List[str]:
        errors: List[str] = []
        target_project_name = ""
        for entry in self.tracked_projects:
            if str(entry.get("project_dir", "")) == str(target_project_dir):
                target_project_name = str(entry.get("name", ""))
                break
        if not target_project_name:
            target_project_name = target_project_dir.name

        for row in selected_rows:
            local_file = Path(str(row.get("local_file", "")))
            if not local_file.exists():
                errors.append(f"Missing local file: {local_file.name}")
                continue
            destination = self._target_transfer_path(local_file, source_project_dir, target_project_dir)
            try:
                if mode == "copy":
                    shutil.copy2(local_file, destination)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(local_file), str(destination))
            except OSError as exc:
                errors.append(f"{local_file.name}: {exc}")
                continue

            record_idx = int(row.get("record_idx", -1))
            record_type = str(row.get("record_type", ""))
            if record_idx < 0 or record_idx >= len(self.records):
                continue
            record = self.records[record_idx]
            if mode == "copy":
                self.records.append(
                    CheckoutRecord(
                        source_file=record.source_file,
                        locked_source_file=record.locked_source_file,
                        local_file=str(destination),
                        initials=self._normalize_initials(),
                        project_name=target_project_name,
                        project_dir=str(target_project_dir),
                        source_root=record.source_root,
                        checked_out_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                        record_type="reference_copy" if record_type == "checked_out" else record.record_type,
                    )
                )
            else:
                record.local_file = str(destination)
                record.project_dir = str(target_project_dir)
                record.project_name = target_project_name
        self._save_records()
        return errors

    def _show_project_files_manager(self, project_dir: Path) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Project Files Manager - {project_dir.name}")
        dialog.resize(1180, 680)
        layout = QVBoxLayout(dialog)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search files")
        layout.addWidget(search_edit)

        tabs = QTabWidget()
        all_table = QTableWidget(0, 5)
        checked_table = QTableWidget(0, 5)
        reference_table = QTableWidget(0, 5)
        untracked_table = QTableWidget(0, 5)
        tables = [all_table, checked_table, reference_table, untracked_table]
        for table in tables:
            table.setHorizontalHeaderLabels(["File", "Type", "Revisions", "Local", "Source"])
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.ExtendedSelection)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setContextMenuPolicy(Qt.CustomContextMenu)
        tabs.addTab(all_table, "All Files")
        tabs.addTab(checked_table, "Checked Out Files")
        tabs.addTab(reference_table, "Reference Copies")
        tabs.addTab(untracked_table, "Untracked")
        layout.addWidget(tabs, stretch=1)

        manager_rows: Dict[str, List[Dict[str, object]]] = {}

        def refresh_tables() -> None:
            manager_rows["all"] = self._project_file_manager_rows(project_dir, "all")
            manager_rows["checked_out"] = self._project_file_manager_rows(project_dir, "checked_out")
            manager_rows["reference_copy"] = self._project_file_manager_rows(project_dir, "reference_copy")
            manager_rows["untracked"] = self._project_file_manager_rows(project_dir, "untracked")
            search_term = search_edit.text()
            self._populate_project_files_manager_table(all_table, manager_rows["all"], search_term)
            self._populate_project_files_manager_table(
                checked_table, manager_rows["checked_out"], search_term
            )
            self._populate_project_files_manager_table(
                reference_table, manager_rows["reference_copy"], search_term
            )
            self._populate_project_files_manager_table(
                untracked_table, manager_rows["untracked"], search_term
            )

        def active_table() -> QTableWidget:
            current = tabs.currentWidget()
            return current if isinstance(current, QTableWidget) else all_table

        def selected_rows() -> List[Dict[str, object]]:
            return self._selected_rows_from_manager_table(active_table())

        def selected_indexes() -> List[int]:
            return self._selected_record_indexes_from_manager_table(active_table())

        def open_selected() -> None:
            indexes = selected_indexes()
            if not indexes:
                self._error("Select at least one file.")
                return
            paths = [
                Path(self.records[idx].local_file)
                for idx in indexes
                if 0 <= idx < len(self.records)
            ]
            self._open_paths(paths)

        def create_snapshot() -> None:
            indexes = [
                idx
                for idx in selected_indexes()
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
            ]
            if not indexes:
                self._error("Select at least one checked-out file.")
                return
            accepted, note = self._prompt_revision_note("Create Revision Snapshot")
            if not accepted:
                return
            with self._busy_action("Creating revision snapshot(s)..."):
                for idx in indexes:
                    self._create_revision_snapshot_for_record(self.records[idx], note=note)
            refresh_tables()

        def switch_revision() -> None:
            indexes = [
                idx
                for idx in selected_indexes()
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
            ]
            if len(indexes) != 1:
                self._error("Select exactly one checked-out file.")
                return
            record = self.records[indexes[0]]
            revision = self._choose_revision_for_record(record)
            if not revision:
                return
            with self._busy_action("Switching file revision..."):
                switched = self._switch_record_to_revision(record, revision)
            if switched:
                refresh_tables()
                self._info(f"Switched to revision {revision.get('id', '')}.")

        def checkin_selected() -> None:
            if not self._validate_identity():
                return
            indexes = {
                idx
                for idx in selected_indexes()
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
            }
            if not indexes:
                self._error("Select at least one checked-out file.")
                return
            self._checkin_record_indexes(indexes)
            refresh_tables()

        def remove_reference_selected() -> None:
            indexes = [
                idx
                for idx in selected_indexes()
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "reference_copy"
            ]
            if not indexes:
                self._error("Select at least one reference copy.")
                return
            with self._busy_action("Removing reference copy record(s)..."):
                self._remove_record_indexes(indexes)
                self._save_records()
                self._render_records_tables()
            refresh_tables()

        def delete_untracked_selected() -> None:
            paths = [
                Path(str(row.get("local_file", "")))
                for row in selected_rows()
                if str(row.get("record_type", "")) == "untracked"
            ]
            if not paths:
                self._error("Select at least one untracked file.")
                return
            confirm = QMessageBox.question(
                dialog,
                "Delete Untracked Files",
                f"Delete {len(paths)} untracked file(s)? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
            errors: List[str] = []
            with self._busy_action("Deleting untracked file(s)..."):
                for path in paths:
                    try:
                        if path.exists():
                            path.unlink()
                    except OSError as exc:
                        errors.append(f"{path.name}: {exc}")
            refresh_tables()
            if errors:
                self._error("Some files could not be deleted:\n" + "\n".join(errors))

        def transfer_selected(mode: str) -> None:
            rows = selected_rows()
            if not rows:
                self._error("Select at least one file.")
                return
            target_project_dir = self._choose_project_transfer_target(project_dir)
            if not target_project_dir:
                return
            with self._busy_action(
                "Copying file(s) to project..." if mode == "copy" else "Moving file(s) to project..."
            ):
                errors = self._transfer_project_files(rows, project_dir, target_project_dir, mode)
                self._render_records_tables()
            refresh_tables()
            if errors:
                self._error("Some files could not be transferred:\n" + "\n".join(errors))

        def show_manager_context_menu(table: QTableWidget, pos: QPoint) -> None:
            row = table.rowAt(pos.y())
            if row >= 0 and (not table.item(row, 0) or not table.item(row, 0).isSelected()):
                table.clearSelection()
                table.selectRow(row)
            rows = self._selected_rows_from_manager_table(table)
            menu = QMenu(dialog)
            open_action = menu.addAction("Open Selected")
            snapshot_action = None
            switch_action = None
            checkin_action = None
            remove_ref_action = None
            delete_untracked_action = None

            has_checked_out = any(str(row.get("record_type", "")) == "checked_out" for row in rows)
            has_reference = any(str(row.get("record_type", "")) == "reference_copy" for row in rows)
            has_untracked = any(str(row.get("record_type", "")) == "untracked" for row in rows)
            checked_out_count = sum(
                1 for row in rows if str(row.get("record_type", "")) == "checked_out"
            )

            if has_checked_out:
                snapshot_action = menu.addAction("Create Snapshot")
                checkin_action = menu.addAction("Check In Selected")
                if checked_out_count == 1:
                    switch_action = menu.addAction("Switch Revision")
            if has_reference:
                remove_ref_action = menu.addAction("Remove Reference Copies")
            if has_untracked:
                delete_untracked_action = menu.addAction("Delete Untracked")
            menu.addSeparator()
            copy_action = menu.addAction("Copy To Project")
            move_action = menu.addAction("Move To Project")

            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == open_action:
                open_selected()
            elif snapshot_action is not None and chosen == snapshot_action:
                create_snapshot()
            elif switch_action is not None and chosen == switch_action:
                switch_revision()
            elif checkin_action is not None and chosen == checkin_action:
                checkin_selected()
            elif remove_ref_action is not None and chosen == remove_ref_action:
                remove_reference_selected()
            elif delete_untracked_action is not None and chosen == delete_untracked_action:
                delete_untracked_selected()
            elif chosen == copy_action:
                transfer_selected("copy")
            elif chosen == move_action:
                transfer_selected("move")

        for table in tables:
            table.cellDoubleClicked.connect(lambda _r, _c: open_selected())
            table.customContextMenuRequested.connect(
                lambda pos, table=table: show_manager_context_menu(table, pos)
            )

        search_edit.textChanged.connect(lambda _text: refresh_tables())

        button_bar = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(open_selected)
        checkin_btn = QPushButton("Check In Selected")
        checkin_btn.clicked.connect(checkin_selected)
        remove_ref_btn = QPushButton("Remove Ref Selected")
        remove_ref_btn.clicked.connect(remove_reference_selected)
        delete_untracked_btn = QPushButton("Delete Untracked")
        delete_untracked_btn.clicked.connect(delete_untracked_selected)
        copy_project_btn = QPushButton("Copy To Project")
        copy_project_btn.clicked.connect(lambda: transfer_selected("copy"))
        move_project_btn = QPushButton("Move To Project")
        move_project_btn.clicked.connect(lambda: transfer_selected("move"))
        snapshot_btn = QPushButton("Create Snapshot")
        snapshot_btn.clicked.connect(create_snapshot)
        switch_btn = QPushButton("Switch Revision")
        switch_btn.clicked.connect(switch_revision)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(refresh_tables)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_bar.addWidget(open_btn)
        button_bar.addWidget(checkin_btn)
        button_bar.addWidget(remove_ref_btn)
        button_bar.addWidget(delete_untracked_btn)
        button_bar.addWidget(copy_project_btn)
        button_bar.addWidget(move_project_btn)
        button_bar.addWidget(snapshot_btn)
        button_bar.addWidget(switch_btn)
        button_bar.addWidget(refresh_btn)
        button_bar.addStretch()
        button_bar.addWidget(close_btn)
        layout.addLayout(button_bar)

        refresh_tables()
        dialog.exec()

    def _refresh_source_roots(self, sources: List[str], selected_source: str = "") -> None:
        self.source_roots_list.clear()
        valid_sources = [Path(source) for source in sources if Path(source).is_dir()]
        selected_item: Optional[QListWidgetItem] = None
        for source in valid_sources:
            item = QListWidgetItem(source.name or str(source))
            item.setData(Qt.UserRole, str(source))
            item.setToolTip(str(source))
            self.source_roots_list.addItem(item)
            if str(source) == selected_source:
                selected_item = item

        if selected_item:
            self.source_roots_list.setCurrentItem(selected_item)
        elif self.source_roots_list.count() > 0:
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

        path_value = item.data(0, Qt.UserRole)
        with self._debug_timed("populate_directory_children", directory=str(path_value or "")):
            item.takeChildren()
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
            self._debug_event("directory_children_loaded", directory=str(path_value), count=len(children))

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
        self._set_current_directory_with_feedback(selected_path, "Loading directory...")

    def _view_current_directory_location(self) -> None:
        current_directory = self._validate_current_directory()
        if not current_directory:
            return
        self._open_paths([current_directory])

    def _on_source_root_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        self._debug_event("source_root_changed", source=str(current.data(Qt.UserRole)))
        project_dir = self._current_project_path()
        if project_dir and project_dir.is_dir():
            self._save_project_config(project_dir, selected_source=str(current.data(Qt.UserRole)))
        root_path = Path(str(current.data(Qt.UserRole)))
        self._set_directory_tree_root(root_path)
        self._set_current_directory_with_feedback(root_path, "Loading source directory...")

    def _set_current_directory(self, directory: Path) -> None:
        if self.current_directory is None or self.current_directory != directory:
            self._clear_file_search_filter()
        self.current_directory = directory
        self.current_folder_label.setText(f"Current folder: {directory}")
        self._refresh_source_files()

    def _set_current_directory_with_feedback(self, directory: Path, message: str) -> None:
        if self._busy_action_depth > 0:
            self._set_current_directory(directory)
            return
        if self.current_directory is not None and self.current_directory == directory:
            self._set_current_directory(directory)
            return
        with self._busy_action(message):
            self._set_current_directory(directory)

    def _invalidate_directory_caches(self, directory: Path) -> None:
        key = str(directory)
        self._dir_files_cache.pop(key, None)
        self._history_rows_cache.pop(key, None)

    def _cached_directory_files(self, directory: Path) -> List[Path]:
        key = str(directory)
        now = perf_counter()
        cached = self._dir_files_cache.get(key)
        ttl = self._directory_cache_ttl(directory)
        if cached and (now - cached[0]) <= ttl:
            return cached[1]

        entries: List[Path] = []
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.name not in {
                    HISTORY_FILE_NAME,
                    LEGACY_HISTORY_FILE_NAME,
                }:
                    entries.append(entry)
        except OSError:
            entries = []
        entries.sort(key=lambda item: item.name.lower())
        self._dir_files_cache[key] = (now, entries)
        return entries

    def _is_probably_remote_directory(self, directory: Path) -> bool:
        directory_text = str(directory)
        if directory_text.startswith("\\\\"):
            return True

        home_drive = str(Path.home().drive).upper()
        directory_drive = str(directory.drive).upper()
        if home_drive and directory_drive and directory_drive != home_drive:
            return True

        return False

    def _directory_cache_ttl(self, directory: Path) -> float:
        # Preserve explicit override used by tests and manual tuning.
        explicit_ttl = getattr(self, "_dir_cache_ttl_seconds", None)
        if isinstance(explicit_ttl, (int, float)) and explicit_ttl > 0:
            return float(explicit_ttl)
        if self._is_probably_remote_directory(directory):
            return self._remote_dir_cache_ttl_seconds
        return self._local_dir_cache_ttl_seconds

    def _on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._debug_event("directory_tree_expanded", directory=str(item.data(0, Qt.UserRole) or ""))
        self._populate_directory_children(item)

    def _on_directory_selected(self, item: QTreeWidgetItem, _column: int) -> None:
        path_value = item.data(0, Qt.UserRole)
        if not path_value:
            return
        self._debug_event("directory_selected", directory=str(path_value))
        path = Path(path_value)
        if path.is_dir():
            self._set_current_directory_with_feedback(path, "Loading directory...")

    def _refresh_source_files(self) -> None:
        current_dir = str(self.current_directory) if self.current_directory else ""
        with self._debug_timed("refresh_source_files", directory=current_dir):
            self.files_list.clear()
            if not self.current_directory or not self.current_directory.is_dir():
                self.controlled_files_table.setRowCount(0)
                self.directory_notes_table.setRowCount(0)
                return

            search_term = self.file_search_edit.text().strip().lower()
            history_lookup = self._history_lookup_for_directory(self.current_directory)
            shown_count = 0
            for item in self._cached_directory_files(self.current_directory):
                if not self._matches_extension_filter(item):
                    continue
                if search_term and search_term not in item.name.lower():
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
                shown_count += 1

            self._refresh_controlled_files()
            self._debug_event(
                "source_files_refreshed",
                directory=current_dir,
                search=search_term,
                shown_count=shown_count,
            )

    def _refresh_controlled_files(self) -> None:
        current_dir = str(self.current_directory) if self.current_directory else ""
        with self._debug_timed("refresh_controlled_files", directory=current_dir):
            self.controlled_files_table.setRowCount(0)
            self.directory_notes_table.setRowCount(0)
            if not self.current_directory or not self.current_directory.is_dir():
                return

            count = 0
            for entry in self._checked_out_files_for_directory(self.current_directory):
                row_idx = self.controlled_files_table.rowCount()
                self.controlled_files_table.insertRow(row_idx)
                file_item = QTableWidgetItem(entry["file_name"])
                file_item.setData(Qt.UserRole, entry)
                file_item.setToolTip(entry["locked_source_file"])
                initials_item = QTableWidgetItem(entry["initials"])
                initials_item.setToolTip(entry["full_name"] or entry["initials"])
                checked_out_item = QTableWidgetItem(
                    self._format_checkout_timestamp(str(entry.get("checked_out_at", "")))
                )
                checked_out_item.setToolTip(str(entry.get("checked_out_at", "")))
                self.controlled_files_table.setItem(row_idx, 0, file_item)
                self.controlled_files_table.setItem(row_idx, 1, initials_item)
                self.controlled_files_table.setItem(row_idx, 2, checked_out_item)
                count += 1
            self.controlled_files_table.resizeColumnsToContents()
            self.controlled_files_table.setColumnWidth(
                0, max(self.controlled_files_table.columnWidth(0), 200)
            )
            self._refresh_directory_notes_summary()
            self._debug_event("controlled_files_refreshed", directory=current_dir, count=count)

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
            with self._busy_action("Tracking directory..."):
                sources.append(str(source_path))
                self._save_project_config(
                    project_dir,
                    name=self._current_project_name(),
                    sources=sources,
                    extension_filters=self._current_extension_filters(),
                    filter_mode=self.file_filter_mode_combo.currentText(),
                    selected_source=str(source_path),
                )
                self._refresh_source_roots(sources, str(source_path))
                self._save_settings()

    def _remove_source_directory(self) -> None:
        project_dir = self._validate_current_project()
        item = self.source_roots_list.currentItem()
        if not project_dir or not item:
            self._error("Select a tracked source directory to remove.")
            return

        source_path = str(item.data(Qt.UserRole))
        sources = [source for source in self._source_roots_from_list() if source != source_path]
        selected_source = self._current_source_root_value()
        if selected_source == source_path:
            selected_source = sources[0] if sources else ""
        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=sources,
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
            selected_source=selected_source,
        )
        self._refresh_source_roots(sources, selected_source)
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

        with self._busy_action("Tracking directory..."):
            sources.append(current_dir_str)
            self._save_project_config(
                project_dir,
                name=self._current_project_name(),
                sources=sources,
                extension_filters=self._current_extension_filters(),
                filter_mode=self.file_filter_mode_combo.currentText(),
                selected_source=current_dir_str,
            )
            self._refresh_source_roots(sources, current_dir_str)
            for row in range(self.source_roots_list.count()):
                item = self.source_roots_list.item(row)
                if item.data(Qt.UserRole) == current_dir_str:
                    self.source_roots_list.setCurrentItem(item)
                    break
            self._save_settings()

    def _save_sources_from_ui_order(self) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        sources = self._source_roots_from_list()
        selected_source = self._current_source_root_value()
        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=sources,
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
            selected_source=selected_source,
        )
        self._save_settings()

    def _move_selected_source(self, delta: int) -> None:
        if not self._move_list_widget_item(self.source_roots_list, delta):
            return
        self._save_sources_from_ui_order()

    def _move_selected_source_to(self, target_index: int) -> None:
        if not self._move_list_widget_item_to(self.source_roots_list, target_index):
            return
        self._save_sources_from_ui_order()

    def _move_selected_source_up(self) -> None:
        self._move_selected_source(-1)

    def _move_selected_source_down(self) -> None:
        self._move_selected_source(1)

    def _move_selected_source_top(self) -> None:
        self._move_selected_source_to(0)

    def _move_selected_source_bottom(self) -> None:
        self._move_selected_source_to(self.source_roots_list.count() - 1)

    def _selected_source_file_paths(self) -> List[Path]:
        return [Path(item.data(Qt.UserRole)) for item in self.files_list.selectedItems()]

    def _set_local_reference_read_only(self, path: Path) -> None:
        # Best-effort: mark reference copies read-only on local filesystem.
        try:
            current_mode = path.stat().st_mode
            path.chmod(current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
        except OSError:
            return

    def _copy_selected_as_reference(self) -> None:
        if not self._validate_identity():
            return

        project_dir = self._validate_current_project()
        current_directory = self._validate_current_directory()
        source_root = self._current_source_root()
        if not project_dir or not current_directory or not source_root:
            return

        selected_files = self._selected_source_file_paths()
        if not selected_files:
            self._error("Select at least one source file to copy as reference.")
            return

        reference_root = project_dir / "reference_copies" / self._source_key(project_dir, source_root)
        copied_at = datetime.now().astimezone().isoformat(timespec="seconds")
        errors: List[str] = []

        with self._debug_timed(
            "copy_reference_selected",
            selected_count=len(selected_files),
            directory=str(current_directory),
            source_root=str(source_root),
        ):
            with self._busy_action("Copying reference file(s)..."):
                for source_file in selected_files:
                    if not source_file.exists():
                        errors.append(f"Missing source file: {source_file.name}")
                        continue
                    try:
                        relative_path = source_file.relative_to(source_root)
                    except ValueError:
                        relative_path = Path(source_file.name)
                    local_file = reference_root / relative_path

                    try:
                        local_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, local_file)
                        self._set_local_reference_read_only(local_file)
                        self.records.append(
                            CheckoutRecord(
                                source_file=str(source_file),
                                locked_source_file="",
                                local_file=str(local_file),
                                initials=self._normalize_initials(),
                                project_name=self._current_project_name(),
                                project_dir=str(project_dir),
                                source_root=str(source_root),
                                checked_out_at=copied_at,
                                record_type="reference_copy",
                            )
                        )
                    except OSError as exc:
                        errors.append(f"{source_file.name}: {exc}")

                self._save_records()
                self._render_records_tables()

        if errors:
            self._error("Some reference copies failed:\n" + "\n".join(errors))
        else:
            self._info("Reference copy operation complete.")

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

    def _favorites_from_ui_order(self) -> List[str]:
        ordered: List[str] = []
        for row in range(self.favorites_list.count()):
            item = self.favorites_list.item(row)
            value = str(item.data(Qt.UserRole))
            if value and value not in ordered:
                ordered.append(value)
        return ordered

    def _move_selected_favorite(self, delta: int) -> None:
        if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() != 0:
            self._error("Switch to 'Project Favorites' to reorder favorites.")
            return
        if not self._move_list_widget_item(self.favorites_list, delta):
            return
        self._set_project_favorites(self._favorites_from_ui_order())

    def _move_selected_favorite_to(self, target_index: int) -> None:
        if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() != 0:
            self._error("Switch to 'Project Favorites' to reorder favorites.")
            return
        if not self._move_list_widget_item_to(self.favorites_list, target_index):
            return
        self._set_project_favorites(self._favorites_from_ui_order())

    def _move_selected_favorite_up(self) -> None:
        self._move_selected_favorite(-1)

    def _move_selected_favorite_down(self) -> None:
        self._move_selected_favorite(1)

    def _move_selected_favorite_top(self) -> None:
        self._move_selected_favorite_to(0)

    def _move_selected_favorite_bottom(self) -> None:
        self._move_selected_favorite_to(self.favorites_list.count() - 1)

    def _open_favorite_item(self, item: QListWidgetItem) -> None:
        self._open_paths([Path(str(item.data(Qt.UserRole)))])

    def _open_selected_favorites(self) -> None:
        selected_items = self.favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one favorite to open.")
            return
        self._open_paths([Path(str(item.data(Qt.UserRole))) for item in selected_items])

    def _open_selected_favorites_from_active_tab(self) -> None:
        if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 1:
            self._open_selected_global_favorites()
            return
        self._open_selected_favorites()

    def _remove_selected_favorites_from_active_tab(self) -> None:
        if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 1:
            self._remove_selected_global_favorites()
            return
        self._remove_selected_favorites()

    def _add_selected_global_favorites_to_project(self) -> None:
        selected_items = self.global_favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one global favorite.")
            return
        self._add_favorite_paths([Path(str(item.data(Qt.UserRole))) for item in selected_items])

    def _add_selected_project_favorites_to_global(self) -> None:
        selected_items = self.favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one project favorite.")
            return
        changed = False
        for item in selected_items:
            value = str(item.data(Qt.UserRole)).strip()
            if value and value not in self.global_favorites:
                self.global_favorites.append(value)
                changed = True
        if changed:
            self._save_global_favorites()
            self._refresh_global_favorites_list()

    def _load_global_favorites(self) -> None:
        data = self._read_json_candidates([self._default_global_favorites_file()])
        raw = data.get("favorites", []) if isinstance(data, dict) else data
        self.global_favorites = []
        if isinstance(raw, list):
            for item in raw:
                value = str(item).strip()
                if value and value not in self.global_favorites:
                    self.global_favorites.append(value)
        self._refresh_global_favorites_list()

    def _save_global_favorites(self) -> None:
        path = self._default_global_favorites_file()
        self._ensure_parent_dir(path)
        payload = {
            "schema_version": 1,
            "app_version": APP_VERSION,
            "favorites": self.global_favorites,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _refresh_global_favorites_list(self) -> None:
        if not hasattr(self, "global_favorites_list"):
            return
        self.global_favorites_list.clear()
        search = self.global_favorites_search_edit.text().strip().lower()
        for favorite in self.global_favorites:
            if search and search not in favorite.lower() and search not in Path(favorite).name.lower():
                continue
            item = QListWidgetItem(Path(favorite).name or favorite)
            item.setData(Qt.UserRole, favorite)
            item.setToolTip(favorite)
            self.global_favorites_list.addItem(item)

    def _browse_and_add_global_favorites(self) -> None:
        start_dir = str(self._current_project_path() or Path.home())
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Global Favorite File(s)", start_dir, "All Files (*)"
        )
        if not file_paths:
            return
        changed = False
        for file_path in file_paths:
            value = str(Path(file_path))
            if value not in self.global_favorites:
                self.global_favorites.append(value)
                changed = True
        if changed:
            self._save_global_favorites()
            self._refresh_global_favorites_list()

    def _open_selected_global_favorites(self) -> None:
        selected_items = self.global_favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one global favorite to open.")
            return
        self._open_paths([Path(str(item.data(Qt.UserRole))) for item in selected_items])

    def _remove_selected_global_favorites(self) -> None:
        selected_items = self.global_favorites_list.selectedItems()
        if not selected_items:
            self._error("Select at least one global favorite to remove.")
            return
        selected_paths = {str(item.data(Qt.UserRole)) for item in selected_items}
        self.global_favorites = [
            favorite for favorite in self.global_favorites if favorite not in selected_paths
        ]
        self._save_global_favorites()
        self._refresh_global_favorites_list()

    def _show_global_favorites_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.global_favorites_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.global_favorites_list.visualItemRect(item)
        self._show_global_favorites_context_menu(rect.center())

    def _show_global_favorites_context_menu(self, pos: QPoint) -> None:
        item = self.global_favorites_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.global_favorites_list.clearSelection()
            item.setSelected(True)
            self.global_favorites_list.setCurrentItem(item)
        menu = QMenu(self)
        add_action = menu.addAction("Add Favorite")
        add_project_action = menu.addAction("Add Selected To Project Favorites")
        open_action = menu.addAction("Open Selected")
        remove_action = menu.addAction("Remove Selected")
        chosen = menu.exec(self.global_favorites_list.mapToGlobal(pos))
        if chosen == add_action:
            self._browse_and_add_global_favorites()
        elif chosen == add_project_action:
            self._add_selected_global_favorites_to_project()
        elif chosen == open_action:
            self._open_selected_global_favorites()
        elif chosen == remove_action:
            self._remove_selected_global_favorites()

    def _load_global_notes(self) -> None:
        data = self._read_json_candidates([self._default_global_notes_file()])
        raw = data.get("notes", []) if isinstance(data, dict) else data
        self.global_notes = []
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                subject = str(entry.get("subject", "")).strip()
                if not subject:
                    continue
                self.global_notes.append(
                    {
                        "id": str(entry.get("id", "")).strip() or str(uuid4()),
                        "subject": subject,
                        "body": str(entry.get("body", "")),
                        "created_at": str(entry.get("created_at", "")),
                        "updated_at": str(entry.get("updated_at", "")),
                    }
                )
        self._refresh_global_notes_list()

    def _save_global_notes(self) -> None:
        path = self._default_global_notes_file()
        self._ensure_parent_dir(path)
        payload = {
            "schema_version": 1,
            "app_version": APP_VERSION,
            "notes": self.global_notes,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _refresh_global_notes_list(self) -> None:
        if not hasattr(self, "global_notes_list"):
            return
        self.global_notes_list.clear()
        search = self.global_notes_search_edit.text().strip().lower()
        for note in self.global_notes:
            subject = note.get("subject", "")
            body = note.get("body", "")
            if search and search not in subject.lower() and search not in body.lower():
                continue
            item = QListWidgetItem(subject)
            item.setData(Qt.UserRole, note.get("id", ""))
            item.setToolTip(self._note_tooltip(note))
            self.global_notes_list.addItem(item)

    def _selected_global_note_id(self) -> str:
        item = self.global_notes_list.currentItem()
        return str(item.data(Qt.UserRole)).strip() if item else ""

    def _create_global_note(self) -> None:
        note = self._show_note_dialog()
        if not note:
            return
        self.global_notes.append(note)
        self._save_global_notes()
        self._refresh_global_notes_list()

    def _edit_selected_global_note(self, _item: Optional[QListWidgetItem] = None) -> None:
        note_id = self._selected_global_note_id()
        if not note_id:
            self._error("Select a note to edit.")
            return
        for idx, note in enumerate(self.global_notes):
            if note.get("id", "") != note_id:
                continue
            updated = self._show_note_dialog(note)
            if not updated:
                return
            self.global_notes[idx] = updated
            self._save_global_notes()
            self._refresh_global_notes_list()
            return
        self._error("Selected note could not be found.")

    def _remove_selected_global_note(self) -> None:
        note_id = self._selected_global_note_id()
        if not note_id:
            self._error("Select a note to remove.")
            return
        self.global_notes = [note for note in self.global_notes if note.get("id", "") != note_id]
        self._save_global_notes()
        self._refresh_global_notes_list()

    def _show_global_notes_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.global_notes_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.global_notes_list.visualItemRect(item)
        self._show_global_notes_context_menu(rect.center())

    def _show_global_notes_context_menu(self, pos: QPoint) -> None:
        item = self.global_notes_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.global_notes_list.clearSelection()
            item.setSelected(True)
            self.global_notes_list.setCurrentItem(item)
        menu = QMenu(self)
        new_action = menu.addAction("New Note")
        edit_action = menu.addAction("Edit Selected")
        remove_action = menu.addAction("Remove Selected")
        chosen = menu.exec(self.global_notes_list.mapToGlobal(pos))
        if chosen == new_action:
            self._create_global_note()
        elif chosen == edit_action:
            self._edit_selected_global_note()
        elif chosen == remove_action:
            self._remove_selected_global_note()

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

    def _notes_from_ui_order(self) -> List[Dict[str, str]]:
        by_id = {str(note.get("id", "")): note for note in self._current_project_notes()}
        ordered_notes: List[Dict[str, str]] = []
        for row in range(self.notes_list.count()):
            item = self.notes_list.item(row)
            note_id = str(item.data(Qt.UserRole))
            note = by_id.get(note_id)
            if note:
                ordered_notes.append(note)
        return ordered_notes

    def _move_selected_note(self, delta: int) -> None:
        if not self._move_list_widget_item(self.notes_list, delta):
            return
        self._set_project_notes(self._notes_from_ui_order())

    def _move_selected_note_to(self, target_index: int) -> None:
        if not self._move_list_widget_item_to(self.notes_list, target_index):
            return
        self._set_project_notes(self._notes_from_ui_order())

    def _move_selected_note_up(self) -> None:
        self._move_selected_note(-1)

    def _move_selected_note_down(self) -> None:
        self._move_selected_note(1)

    def _move_selected_note_top(self) -> None:
        self._move_selected_note_to(0)

    def _move_selected_note_bottom(self) -> None:
        self._move_selected_note_to(self.notes_list.count() - 1)

    def _normalize_milestone_entry(self, entry: object) -> Optional[Dict[str, object]]:
        if not isinstance(entry, dict):
            return None
        name = str(entry.get("name", "")).strip()
        if not name:
            return None
        snapshot = entry.get("snapshot", {})
        normalized_snapshot: Dict[str, object] = {}
        if isinstance(snapshot, dict):
            records = snapshot.get("records", [])
            sources = snapshot.get("sources", [])
            extensions = snapshot.get("extension_filters", [])
            normalized_snapshot = {
                "record_count": int(snapshot.get("record_count", len(records) if isinstance(records, list) else 0)),
                "records": [dict(item) for item in records if isinstance(item, dict)]
                if isinstance(records, list)
                else [],
                "sources": [str(item) for item in sources if str(item).strip()]
                if isinstance(sources, list)
                else [],
                "extension_filters": [str(item) for item in extensions if str(item).strip()]
                if isinstance(extensions, list)
                else [],
                "filter_mode": str(snapshot.get("filter_mode", "No Filter")),
            }
        return {
            "id": str(entry.get("id", "")).strip() or str(uuid4()),
            "name": name,
            "description": str(entry.get("description", "")).strip(),
            "created_at": str(entry.get("created_at", "")).strip(),
            "updated_at": str(entry.get("updated_at", "")).strip(),
            "snapshot": normalized_snapshot,
        }

    def _current_project_milestones(self) -> List[Dict[str, object]]:
        config = self._current_project_config()
        if not config:
            return []
        raw = config.get("milestones", [])
        if not isinstance(raw, list):
            return []
        milestones: List[Dict[str, object]] = []
        for entry in raw:
            normalized = self._normalize_milestone_entry(entry)
            if normalized:
                milestones.append(normalized)
        return milestones

    def _milestone_tooltip(self, milestone: Dict[str, object]) -> str:
        snapshot = milestone.get("snapshot", {})
        record_count = 0
        if isinstance(snapshot, dict):
            record_count = int(snapshot.get("record_count", 0) or 0)
        created_at = str(milestone.get("created_at", "")).strip() or "-"
        description = str(milestone.get("description", "")).strip() or "(No description)"
        return f"Created: {created_at}\nChecked-out records tracked: {record_count}\n{description}"

    def _refresh_milestones_list(self, milestones: List[Dict[str, object]]) -> None:
        self.milestones_list.clear()
        for milestone in milestones:
            item = QListWidgetItem(str(milestone.get("name", "(Unnamed Milestone)")))
            item.setData(Qt.UserRole, str(milestone.get("id", "")))
            item.setToolTip(self._milestone_tooltip(milestone))
            self.milestones_list.addItem(item)

    def _set_project_milestones(self, milestones: List[Dict[str, object]]) -> None:
        project_dir = self._validate_current_project()
        if not project_dir:
            return
        normalized: List[Dict[str, object]] = []
        for milestone in milestones:
            clean = self._normalize_milestone_entry(milestone)
            if clean:
                normalized.append(clean)
        self._save_project_config(project_dir, milestones=normalized)
        self._refresh_milestones_list(normalized)

    def _selected_milestone_id(self) -> str:
        item = self.milestones_list.currentItem()
        return str(item.data(Qt.UserRole)).strip() if item else ""

    def _collect_milestone_snapshot(self) -> Dict[str, object]:
        project_dir = self._current_project_path()
        project_dir_str = str(project_dir) if project_dir else ""
        project_records = [
            {
                "source_file": record.source_file,
                "locked_source_file": record.locked_source_file,
                "local_file": record.local_file,
                "initials": record.initials,
                "checked_out_at": record.checked_out_at,
            }
            for record in self.records
            if record.record_type == "checked_out" and record.project_dir == project_dir_str
        ]
        return {
            "record_count": len(project_records),
            "records": project_records,
            "sources": self._source_roots_from_list(),
            "extension_filters": self._current_extension_filters(),
            "filter_mode": self.file_filter_mode_combo.currentText(),
        }

    def _show_milestone_dialog(self) -> Optional[Dict[str, object]]:
        dialog = QDialog(self)
        dialog.setWindowTitle("New Milestone")
        dialog.resize(620, 380)
        layout = QVBoxLayout(dialog)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Milestone name")
        description_edit = QPlainTextEdit()
        description_edit.setPlaceholderText("Milestone notes (optional)")
        include_snapshot_box = QCheckBox("Capture current checked-out file snapshot")
        include_snapshot_box.setChecked(True)

        layout.addWidget(QLabel("Name:"))
        layout.addWidget(name_edit)
        layout.addWidget(QLabel("Description:"))
        layout.addWidget(description_edit, stretch=1)
        layout.addWidget(include_snapshot_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        name = name_edit.text().strip()
        if not name:
            self._error("Milestone name is required.")
            return None
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        return {
            "id": str(uuid4()),
            "name": name,
            "description": description_edit.toPlainText().strip(),
            "created_at": timestamp,
            "updated_at": timestamp,
            "snapshot": self._collect_milestone_snapshot() if include_snapshot_box.isChecked() else {},
        }

    def _create_milestone(self) -> None:
        if not self._validate_current_project():
            return
        milestone = self._show_milestone_dialog()
        if not milestone:
            return
        milestones = self._current_project_milestones()
        milestones.append(milestone)
        self._set_project_milestones(milestones)

    def _view_selected_milestone(self) -> None:
        milestone_id = self._selected_milestone_id()
        if not milestone_id:
            self._error("Select a milestone to view.")
            return
        milestone = None
        for entry in self._current_project_milestones():
            if str(entry.get("id", "")) == milestone_id:
                milestone = entry
                break
        if not milestone:
            self._error("Selected milestone could not be found.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Milestone - {milestone.get('name', '')}")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Name: {milestone.get('name', '')}"))
        layout.addWidget(QLabel(f"Created: {milestone.get('created_at', '') or '-'}"))
        layout.addWidget(QLabel(f"Last Updated: {milestone.get('updated_at', '') or '-'}"))
        description = str(milestone.get("description", "")).strip() or "(No description)"
        layout.addWidget(QLabel(f"Description: {description}"))
        snapshot_text = QPlainTextEdit()
        snapshot_text.setReadOnly(True)
        snapshot_text.setPlainText(
            json.dumps(milestone.get("snapshot", {}), indent=2, ensure_ascii=False)
        )
        layout.addWidget(snapshot_text, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _remove_selected_milestone(self) -> None:
        milestone_id = self._selected_milestone_id()
        if not milestone_id:
            self._error("Select a milestone to remove.")
            return
        milestones = [
            milestone
            for milestone in self._current_project_milestones()
            if str(milestone.get("id", "")) != milestone_id
        ]
        self._set_project_milestones(milestones)

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
        with self._debug_timed("load_filter_presets"):
            self.filter_presets = []
            data = self._read_json_candidates(
                [self._filter_presets_path(), LEGACY_FILTER_PRESETS_FILE]
            )
            if data is None:
                self._debug_event("filter_presets_loaded", count=0)
                return

            raw_presets = data
            if isinstance(data, dict):
                raw_presets = data.get("presets", [])
            if not isinstance(raw_presets, list):
                self._debug_event("filter_presets_loaded", count=0)
                return
            for preset in raw_presets:
                if not isinstance(preset, dict):
                    continue
                normalized = self._normalize_filter_preset(preset)
                if normalized:
                    self.filter_presets.append(normalized)
            self.filter_presets.sort(key=lambda item: str(item["name"]).lower())
            self._debug_event("filter_presets_loaded", count=len(self.filter_presets))

    def _save_filter_presets(self) -> None:
        presets_path = self._filter_presets_path()
        self._ensure_parent_dir(presets_path)
        presets_path.write_text(
            json.dumps(
                {
                    "schema_version": FILTER_PRESETS_SCHEMA_VERSION,
                    "app_version": APP_VERSION,
                    "presets": self.filter_presets,
                },
                indent=2,
            ),
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

        def create_preset_from_current() -> None:
            preset = self._show_filter_preset_editor(
                {
                    "name": "",
                    "filter_mode": self.file_filter_mode_combo.currentText(),
                    "extensions": self._current_extension_filters(),
                }
            )
            if not preset:
                return
            self.filter_presets = [
                existing
                for existing in self.filter_presets
                if str(existing["name"]).lower() != str(preset["name"]).lower()
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
        from_current_btn = QPushButton("New From Current")
        from_current_btn.clicked.connect(create_preset_from_current)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(edit_preset)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(delete_preset)
        apply_btn = QPushButton("Apply Selected To Project")
        apply_btn.clicked.connect(apply_preset)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        controls.addWidget(new_btn)
        controls.addWidget(from_current_btn)
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
        self._save_current_project_filters(show_busy=True)

    def _on_extension_list_changed(self) -> None:
        self.extension_filter_debounce.start()

    def _apply_debounced_extension_filters(self) -> None:
        self._save_current_project_filters(show_busy=True)

    def _save_current_project_filters(self, show_busy: bool = False) -> None:
        project_dir = self._current_project_path()
        if not project_dir or not project_dir.is_dir():
            if show_busy:
                self._refresh_source_files_with_feedback("Filtering source files...")
            else:
                self._refresh_source_files()
            return

        self._save_project_config(
            project_dir,
            name=self._current_project_name(),
            sources=self._source_roots_from_list(),
            extension_filters=self._current_extension_filters(),
            filter_mode=self.file_filter_mode_combo.currentText(),
        )
        if show_busy:
            self._refresh_source_files_with_feedback("Filtering source files...")
        else:
            self._refresh_source_files()

    def _add_filter_extension(self) -> None:
        filters = self._current_extension_filters()
        normalized = self._normalize_extension_value(self.file_extension_combo.currentText())
        if normalized and normalized not in filters:
            filters.append(normalized)
            self._set_extension_filters(filters)
        self._save_current_project_filters(show_busy=True)

    def _remove_filter_extension(self) -> None:
        normalized = self._normalize_extension_value(self.file_extension_combo.currentText())
        filters = [value for value in self._current_extension_filters() if value != normalized]
        self._set_extension_filters(filters)
        self._save_current_project_filters(show_busy=True)

    def _clear_filter_extensions(self) -> None:
        self._set_extension_filters([])
        self._save_current_project_filters(show_busy=True)

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

    def _normalize_source_ids(
        self, sources: List[str], source_ids: Optional[Dict[str, str]]
    ) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        existing = source_ids or {}
        for source in sources:
            source_value = str(source).strip()
            if not source_value:
                continue
            source_id = str(existing.get(source_value, "")).strip()
            if not source_id:
                source_id = str(uuid4())
            normalized[source_value] = source_id
        return normalized

    def _source_key(self, project_dir: Path, source_root: Path) -> str:
        config = self._read_project_config(project_dir)
        sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]
        raw_source_ids = config.get("source_ids", {})
        source_ids = dict(raw_source_ids) if isinstance(raw_source_ids, dict) else {}
        normalized_source_ids = self._normalize_source_ids(sources, source_ids)
        source_key = normalized_source_ids.get(str(source_root))
        if not source_key:
            source_key = str(uuid4())
            normalized_source_ids[str(source_root)] = source_key
            if str(source_root) not in sources:
                sources.append(str(source_root))
        if normalized_source_ids != source_ids or sources != list(config.get("sources", [])):
            self._save_project_config(project_dir, sources=sources, source_ids=normalized_source_ids)
        return source_key

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

    def _history_json_file(self, source_dir: Path) -> Path:
        return source_dir / HISTORY_FILE_NAME

    def _history_legacy_csv_file(self, source_dir: Path) -> Path:
        return source_dir / LEGACY_HISTORY_FILE_NAME

    def _normalize_history_row(self, row: Dict[str, str]) -> Dict[str, str]:
        revision_id = str(row.get("revision_id", "")).strip()
        initials = str(row.get("user_initials", "")).strip()
        full_name = str(row.get("user_full_name", "")).strip()
        extras = row.get("__extras__", "")
        if not revision_id and extras:
            # Legacy CSV rows can become shifted when revision_id was written against old headers.
            revision_id = initials
            initials = full_name
            full_name = extras
        return {
            "timestamp": str(row.get("timestamp", "")).strip(),
            "action": str(row.get("action", "")).strip(),
            "file_name": str(row.get("file_name", "")).strip(),
            "revision_id": revision_id,
            "user_initials": initials,
            "user_full_name": full_name,
        }

    def _write_history_rows_json(self, source_dir: Path, rows: List[Dict[str, str]]) -> None:
        history_file = self._history_json_file(source_dir)
        self._ensure_parent_dir(history_file)
        payload = {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "entries": rows,
        }
        history_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_history(
        self, source_dir: Path, action: str, file_name: str, revision_id: str = ""
    ) -> None:
        rows = self._read_history_rows(source_dir)
        rows.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "action": action,
                "file_name": file_name,
                "revision_id": revision_id,
                "user_initials": self._normalize_initials(),
                "user_full_name": self._current_full_name(),
            }
        )
        self._write_history_rows_json(source_dir, rows)
        self._invalidate_directory_caches(source_dir)

    def _read_history_rows(self, source_dir: Path) -> List[Dict[str, str]]:
        cache_key = str(source_dir)
        history_json = self._history_json_file(source_dir)
        history_csv = self._history_legacy_csv_file(source_dir)
        active_file: Optional[Path] = None
        if history_json.exists():
            active_file = history_json
        elif history_csv.exists():
            active_file = history_csv
        if active_file is None:
            self._history_rows_cache.pop(cache_key, None)
            return []

        try:
            mtime_ns = active_file.stat().st_mtime_ns
        except OSError:
            self._history_rows_cache.pop(cache_key, None)
            return []

        cached = self._history_rows_cache.get(cache_key)
        if cached and cached[0] == mtime_ns:
            return cached[1]

        rows: List[Dict[str, str]] = []
        try:
            if active_file == history_json:
                raw = json.loads(history_json.read_text(encoding="utf-8"))
                entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
                if isinstance(entries, list):
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        raw_row = {key: str(value) for key, value in entry.items()}
                        rows.append(self._normalize_history_row(raw_row))
            else:
                with history_csv.open("r", encoding="utf-8", newline="") as handle:
                    for row in csv.DictReader(handle):
                        extras = row.get(None, [])
                        raw_row = {key: str(value) for key, value in row.items() if key is not None}
                        raw_row["__extras__"] = str(extras[0]) if extras else ""
                        rows.append(self._normalize_history_row(raw_row))
        except (OSError, ValueError, TypeError):
            self._history_rows_cache.pop(cache_key, None)
            return []
        self._history_rows_cache[cache_key] = (mtime_ns, rows)
        return rows

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
                        row.get("revision_id", ""),
                        row.get("user_initials", ""),
                        row.get("user_full_name", ""),
                    ]
                )
        rows.reverse()
        return rows

    def _directory_notes_path(self, source_dir: Path) -> Path:
        return source_dir / DIRECTORY_NOTES_FILE

    def _read_directory_notes(self, source_dir: Path) -> List[Dict[str, str]]:
        notes_file = self._directory_notes_path(source_dir)
        if not notes_file.exists():
            return []
        try:
            raw = json.loads(notes_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return []
        notes: List[Dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            parent_id = str(entry.get("parent_id", "")).strip()
            if parent_id.lower() in {"false", "none", "null"}:
                parent_id = ""
            notes.append(
                {
                    "id": str(entry.get("id", "")).strip() or str(uuid4()),
                    "file_name": str(entry.get("file_name", "")).strip(),
                    "parent_id": parent_id,
                    "subject": str(entry.get("subject", "")).strip(),
                    "body": str(entry.get("body", "")),
                    "created_by_initials": str(entry.get("created_by_initials", "")).strip(),
                    "created_by_name": str(entry.get("created_by_name", "")).strip(),
                    "created_at": str(entry.get("created_at", "")).strip(),
                    "updated_at": str(entry.get("updated_at", "")).strip(),
                }
            )
        return notes

    def _write_directory_notes(self, source_dir: Path, notes: List[Dict[str, str]]) -> None:
        notes_file = self._directory_notes_path(source_dir)
        self._ensure_parent_dir(notes_file)
        payload = {
            "schema_version": DIRECTORY_NOTES_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "entries": notes,
        }
        tmp_file = notes_file.with_suffix(notes_file.suffix + ".tmp")
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp_file, notes_file)

    def _note_preview(self, body: str, limit: int = 80) -> str:
        collapsed = " ".join(body.split())
        if len(collapsed) <= limit:
            return collapsed
        return collapsed[: limit - 3].rstrip() + "..."

    def _refresh_directory_notes_summary(self) -> None:
        self.directory_notes_table.setRowCount(0)
        if not self.current_directory or not self.current_directory.is_dir():
            return
        notes = self._read_directory_notes(self.current_directory)
        by_file: Dict[str, List[Dict[str, str]]] = {}
        for note in notes:
            file_name = note.get("file_name", "").strip()
            if not file_name:
                continue
            by_file.setdefault(file_name, []).append(note)
        for file_name in sorted(by_file.keys(), key=str.lower):
            file_notes = by_file[file_name]
            latest = max(file_notes, key=lambda item: item.get("updated_at", ""))
            row_idx = self.directory_notes_table.rowCount()
            self.directory_notes_table.insertRow(row_idx)
            file_item = QTableWidgetItem(file_name)
            file_item.setData(Qt.UserRole, file_name)
            count_item = QTableWidgetItem(str(len(file_notes)))
            updated_item = QTableWidgetItem(
                self._format_checkout_timestamp(str(latest.get("updated_at", "")))
            )
            updated_item.setToolTip(str(latest.get("updated_at", "")))
            self.directory_notes_table.setItem(row_idx, 0, file_item)
            self.directory_notes_table.setItem(row_idx, 1, count_item)
            self.directory_notes_table.setItem(row_idx, 2, updated_item)
        self.directory_notes_table.resizeColumnsToContents()
        self.directory_notes_table.setColumnWidth(0, max(self.directory_notes_table.columnWidth(0), 220))

    def _open_notes_for_selected_source_file(self) -> None:
        selected = self.files_list.selectedItems()
        if selected:
            original_name = str(selected[0].data(Qt.UserRole + 1) or "").strip()
            if not original_name:
                original_name = Path(str(selected[0].data(Qt.UserRole))).name
            self._open_file_notes_window(original_name)
            return
        controlled_rows = self.controlled_files_table.selectionModel().selectedRows()
        if controlled_rows:
            item = self.controlled_files_table.item(controlled_rows[0].row(), 0)
            if item:
                entry = item.data(Qt.UserRole)
                if isinstance(entry, dict):
                    self._open_file_notes_window(str(entry.get("file_name", item.text())))
                    return
        rows = self.directory_notes_table.selectionModel().selectedRows()
        if rows:
            item = self.directory_notes_table.item(rows[0].row(), 0)
            if item:
                file_name = str(item.data(Qt.UserRole) or item.text())
                self._open_file_notes_window(file_name)
                return
        self._error("Select a file first.")

    def _canonical_note_file_name(self, file_name: str, source_dir: Path) -> str:
        normalized = file_name.strip()
        if not normalized:
            return normalized
        lookup = self._history_lookup_for_directory(source_dir)
        row = lookup.get(normalized)
        if row:
            original = str(row.get("original_file_name", "")).strip()
            if original:
                return original
        return normalized

    def _show_directory_notes_context_menu(self, pos: QPoint) -> None:
        row = self.directory_notes_table.rowAt(pos.y())
        if row >= 0 and (not self.directory_notes_table.item(row, 0) or not self.directory_notes_table.item(row, 0).isSelected()):
            self.directory_notes_table.clearSelection()
            self.directory_notes_table.selectRow(row)
        menu = QMenu(self)
        view_action = menu.addAction("View Notes")
        refresh_action = menu.addAction("Refresh")
        chosen = menu.exec(self.directory_notes_table.viewport().mapToGlobal(pos))
        if chosen == view_action:
            self._open_notes_for_selected_source_file()
        elif chosen == refresh_action:
            self._refresh_directory_notes_summary()

    def _open_file_notes_window(self, file_name: str) -> None:
        current_directory = self._validate_current_directory()
        if not current_directory:
            return
        file_name = self._canonical_note_file_name(file_name, current_directory)
        notes = self._read_directory_notes(current_directory)
        file_notes = [note for note in notes if note.get("file_name", "") == file_name]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"File Notes - {file_name}")
        dialog.resize(1080, 620)
        layout = QVBoxLayout(dialog)

        tree = QTreeWidget()
        tree.setColumnCount(5)
        tree.setHeaderLabels(["Subject", "Preview", "Created By", "Created", "Last Edit"])
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(tree, stretch=1)

        def refresh_tree() -> None:
            tree.clear()
            by_parent: Dict[str, List[Dict[str, str]]] = {}
            for note in file_notes:
                parent_key = str(note.get("parent_id", "")).strip()
                if parent_key.lower() in {"false", "none", "null"}:
                    parent_key = ""
                by_parent.setdefault(parent_key, []).append(note)

            def add_children(parent_item: Optional[QTreeWidgetItem], parent_id: str) -> None:
                children = sorted(
                    by_parent.get(parent_id, []), key=lambda item: item.get("created_at", "")
                )
                for note in children:
                    created_by = note.get("created_by_name", "") or note.get("created_by_initials", "")
                    values = [
                        note.get("subject", ""),
                        self._note_preview(note.get("body", "")),
                        created_by,
                        self._format_checkout_timestamp(note.get("created_at", "")),
                        self._format_checkout_timestamp(note.get("updated_at", "")),
                    ]
                    item = QTreeWidgetItem(values)
                    item.setData(0, Qt.UserRole, note.get("id", ""))
                    item.setToolTip(1, note.get("body", ""))
                    if parent_item is None:
                        tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    add_children(item, note.get("id", ""))

            add_children(None, "")
            tree.expandAll()

        def prompt_note(existing: Optional[Dict[str, str]] = None) -> Optional[Dict[str, str]]:
            note_dialog = QDialog(dialog)
            note_dialog.setWindowTitle("Edit Note" if existing else "New Note")
            note_dialog.resize(620, 360)
            note_layout = QVBoxLayout(note_dialog)
            subject_edit = QLineEdit(existing.get("subject", "") if existing else "")
            body_edit = QPlainTextEdit(existing.get("body", "") if existing else "")
            note_layout.addWidget(QLabel("Subject:"))
            note_layout.addWidget(subject_edit)
            note_layout.addWidget(QLabel("Body:"))
            note_layout.addWidget(body_edit, stretch=1)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(note_dialog.accept)
            buttons.rejected.connect(note_dialog.reject)
            note_layout.addWidget(buttons)
            if note_dialog.exec() != QDialog.Accepted:
                return None
            subject = subject_edit.text().strip()
            if not subject:
                self._error("Subject is required.")
                return None
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            return {
                "id": existing.get("id", "") if existing else str(uuid4()),
                "file_name": file_name,
                "parent_id": existing.get("parent_id", "") if existing else "",
                "subject": subject,
                "body": body_edit.toPlainText().strip(),
                "created_by_initials": existing.get("created_by_initials", "") if existing else self._normalize_initials(),
                "created_by_name": existing.get("created_by_name", "") if existing else self._current_full_name(),
                "created_at": existing.get("created_at", "") if existing else timestamp,
                "updated_at": timestamp,
            }

        def selected_note() -> Optional[Dict[str, str]]:
            current_item = tree.currentItem()
            if not current_item:
                return None
            note_id = str(current_item.data(0, Qt.UserRole))
            for note in file_notes:
                if note.get("id", "") == note_id:
                    return note
            return None

        def add_note(parent_id: str = "") -> None:
            created = prompt_note()
            if not created:
                return
            created["parent_id"] = str(parent_id).strip()
            file_notes.append(created)
            all_notes = [note for note in notes if note.get("file_name", "") != file_name] + file_notes
            self._write_directory_notes(current_directory, all_notes)
            refresh_tree()
            self._refresh_directory_notes_summary()

        def edit_note() -> None:
            selected = selected_note()
            if not selected:
                self._error("Select a note first.")
                return
            updated = prompt_note(selected)
            if not updated:
                return
            for idx, note in enumerate(file_notes):
                if note.get("id", "") == selected.get("id", ""):
                    updated["parent_id"] = note.get("parent_id", "")
                    file_notes[idx] = updated
                    break
            all_notes = [note for note in notes if note.get("file_name", "") != file_name] + file_notes
            self._write_directory_notes(current_directory, all_notes)
            refresh_tree()
            self._refresh_directory_notes_summary()

        def remove_note() -> None:
            selected = selected_note()
            if not selected:
                self._error("Select a note first.")
                return
            selected_id = selected.get("id", "")
            to_remove = {selected_id}
            changed = True
            while changed:
                changed = False
                for note in file_notes:
                    if note.get("parent_id", "") in to_remove and note.get("id", "") not in to_remove:
                        to_remove.add(note.get("id", ""))
                        changed = True
            remaining = [note for note in file_notes if note.get("id", "") not in to_remove]
            file_notes.clear()
            file_notes.extend(remaining)
            all_notes = [note for note in notes if note.get("file_name", "") != file_name] + file_notes
            self._write_directory_notes(current_directory, all_notes)
            refresh_tree()
            self._refresh_directory_notes_summary()

        def reply_note() -> None:
            selected = selected_note()
            if not selected:
                self._error("Select a parent note first.")
                return
            add_note(selected.get("id", ""))

        tree.customContextMenuRequested.connect(
            lambda pos: self._show_file_notes_tree_context_menu(tree, pos, add_note, reply_note, edit_note, remove_note)
        )

        controls = QHBoxLayout()
        new_btn = QPushButton("New Note")
        new_btn.clicked.connect(lambda _checked=False: add_note(""))
        reply_btn = QPushButton("Reply")
        reply_btn.clicked.connect(lambda _checked=False: reply_note())
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(lambda _checked=False: edit_note())
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda _checked=False: remove_note())
        controls.addWidget(new_btn)
        controls.addWidget(reply_btn)
        controls.addWidget(edit_btn)
        controls.addWidget(remove_btn)
        controls.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        refresh_tree()
        dialog.exec()

    def _show_file_notes_tree_context_menu(
        self,
        tree: QTreeWidget,
        pos: QPoint,
        add_note_cb,
        reply_cb,
        edit_cb,
        remove_cb,
    ) -> None:
        item = tree.itemAt(pos)
        if item is not None and not item.isSelected():
            tree.setCurrentItem(item)
        menu = QMenu(self)
        new_action = menu.addAction("New Note")
        reply_action = menu.addAction("Reply")
        edit_action = menu.addAction("Edit")
        remove_action = menu.addAction("Remove")
        chosen = menu.exec(tree.viewport().mapToGlobal(pos))
        if chosen == new_action:
            add_note_cb()
        elif chosen == reply_action:
            reply_cb()
        elif chosen == edit_action:
            edit_cb()
        elif chosen == remove_action:
            remove_cb()

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
                    "checked_out_at": row.get("timestamp", ""),
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
        project_checkout_dir = project_dir / "checked_out" / self._source_key(project_dir, source_root)
        errors: List[str] = []
        checked_out_at = datetime.now().astimezone().isoformat(timespec="seconds")
        history_lookup: Dict[str, Dict[str, str]] = {}

        with self._debug_timed(
            "checkout_selected",
            selected_count=len(selected_files),
            directory=str(current_directory),
            source_root=str(source_root),
        ):
            with self._busy_action("Checking out file(s)..."):
                # Refresh before checkout so UI/history reflect recent activity by other users.
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
                        new_record = CheckoutRecord(
                            source_file=str(source_file),
                            locked_source_file=str(locked_source_file),
                            local_file=str(local_file),
                            initials=initials,
                            project_name=self._current_project_name(),
                            project_dir=str(project_dir),
                            source_root=str(source_root),
                            checked_out_at=checked_out_at,
                        )
                        self.records.append(new_record)
                        self._create_revision_snapshot_for_record(
                            new_record,
                            note="Baseline snapshot captured at checkout.",
                            origin="checkout_baseline",
                        )
                        self._append_history(source_file.parent, "CHECK_OUT", source_file.name)
                        self._invalidate_directory_caches(source_file.parent)
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

    def _selected_checked_out_record_indexes(self) -> List[int]:
        return [
            idx
            for idx in self._selected_record_indexes()
            if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
        ]

    def _file_versions_registry_path(self, project_dir: Path) -> Path:
        return project_dir / FILE_VERSIONS_FILE

    def _file_versions_root(self, project_dir: Path) -> Path:
        return project_dir / FILE_VERSIONS_DIR

    def _record_version_key(self, record: CheckoutRecord) -> str:
        key_source = "|".join([record.project_dir, record.source_file, record.locked_source_file])
        return hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]

    def _load_file_versions_registry(self, project_dir: Path) -> Dict[str, object]:
        registry_path = self._file_versions_registry_path(project_dir)
        if not registry_path.exists():
            return {
                "schema_version": FILE_VERSIONS_SCHEMA_VERSION,
                "app_version": APP_VERSION,
                "files": {},
            }
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raw = {}
        files = raw.get("files", {}) if isinstance(raw, dict) else {}
        if not isinstance(files, dict):
            files = {}
        return {
            "schema_version": FILE_VERSIONS_SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "files": files,
        }

    def _save_file_versions_registry(self, project_dir: Path, registry: Dict[str, object]) -> None:
        registry_path = self._file_versions_registry_path(project_dir)
        self._ensure_parent_dir(registry_path)
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    def _compute_file_sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _next_revision_id(self, existing_entries: List[Dict[str, object]]) -> str:
        existing_ids = {str(entry.get("id", "")) for entry in existing_entries}
        while True:
            stamp = datetime.now().strftime("%y%m%d%H%M%S")
            candidate = f"R{stamp}-{uuid4().hex[:4].upper()}"
            if candidate not in existing_ids:
                return candidate

    def _prompt_revision_note(self, title: str, initial_note: str = "") -> Tuple[bool, str]:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(520, 220)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Optional revision note:"))
        note_edit = QPlainTextEdit(initial_note)
        layout.addWidget(note_edit, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return False, ""
        return True, note_edit.toPlainText().strip()

    def _revision_entries_for_record(self, record: CheckoutRecord) -> List[Dict[str, object]]:
        project_dir = Path(record.project_dir)
        registry = self._load_file_versions_registry(project_dir)
        files = registry.get("files", {})
        if not isinstance(files, dict):
            return []
        file_entry = files.get(self._record_version_key(record), {})
        if not isinstance(file_entry, dict):
            return []
        revisions = file_entry.get("revisions", [])
        if not isinstance(revisions, list):
            return []
        return [dict(item) for item in revisions if isinstance(item, dict)]

    def _create_revision_snapshot_for_record(
        self,
        record: CheckoutRecord,
        note: str = "",
        origin: str = "manual",
        snapshot_source_path: Optional[Path] = None,
    ) -> Optional[Dict[str, object]]:
        source_path = snapshot_source_path or Path(record.local_file)
        if not source_path.exists():
            self._error(f"Missing snapshot source file: {source_path}")
            return None

        project_dir = Path(record.project_dir)
        revisions_root = self._file_versions_root(project_dir)
        registry = self._load_file_versions_registry(project_dir)
        files = registry.setdefault("files", {})
        if not isinstance(files, dict):
            files = {}
            registry["files"] = files

        key = self._record_version_key(record)
        file_entry = files.get(key)
        if not isinstance(file_entry, dict):
            file_entry = {
                "source_file": record.source_file,
                "locked_source_file": record.locked_source_file,
                "local_file": record.local_file,
                "project_name": record.project_name,
                "revisions": [],
            }
            files[key] = file_entry

        revisions = file_entry.get("revisions", [])
        if not isinstance(revisions, list):
            revisions = []
            file_entry["revisions"] = revisions

        file_hash = self._compute_file_sha256(source_path)
        for revision in revisions:
            if str(revision.get("sha256", "")) == file_hash:
                return dict(revision)

        revision_id = self._next_revision_id([dict(item) for item in revisions if isinstance(item, dict)])
        snapshot_dir = revisions_root / key
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_name = f"{revision_id}{source_path.suffix}"
        snapshot_path = snapshot_dir / snapshot_name
        shutil.copy2(source_path, snapshot_path)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        revision_entry: Dict[str, object] = {
            "id": revision_id,
            "created_at": timestamp,
            "note": note,
            "sha256": file_hash,
            "origin": origin,
            "snapshot_file": str(snapshot_path.relative_to(project_dir)),
        }
        revisions.append(revision_entry)
        file_entry["local_file"] = record.local_file
        self._save_file_versions_registry(project_dir, registry)
        return revision_entry

    def _ensure_saved_state_before_revision_switch(self, record: CheckoutRecord) -> bool:
        local_path = Path(record.local_file)
        if not local_path.exists():
            self._error(f"Missing local file: {local_path}")
            return False
        current_hash = self._compute_file_sha256(local_path)
        revisions = self._revision_entries_for_record(record)
        existing_hashes = {str(item.get("sha256", "")) for item in revisions}
        if current_hash in existing_hashes:
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Unsaved Current State")
        dialog.setText("Current local file state does not match any saved revision.")
        dialog.setInformativeText("Create a snapshot of the current state before switching revisions?")
        save_btn = dialog.addButton("Save Snapshot", QMessageBox.AcceptRole)
        continue_btn = dialog.addButton("Continue Without Saving", QMessageBox.ActionRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(save_btn)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == save_btn:
            created = self._create_revision_snapshot_for_record(
                record,
                note="Auto snapshot before switching revision.",
                origin="auto_before_switch",
            )
            return created is not None
        if clicked == continue_btn:
            return True
        return False

    def _choose_revision_for_record(self, record: CheckoutRecord) -> Optional[Dict[str, object]]:
        revisions = self._revision_entries_for_record(record)
        if not revisions:
            self._error("No revisions are available for the selected file.")
            return None
        checkin_by_revision = self._checkin_history_by_revision_id_for_record(record)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Revisions - {Path(record.source_file).name}")
        dialog.resize(900, 420)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(revisions), 5)
        table.setHorizontalHeaderLabels(["Revision", "Timestamp", "Checked In", "Hash", "Note"])
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        for row, entry in enumerate(revisions):
            revision_id = str(entry.get("id", ""))
            checkin_row = checkin_by_revision.get(revision_id)
            checked_in_value = "Yes" if checkin_row else "No"
            checked_in_tooltip = ""
            if checkin_row:
                checked_in_tooltip = (
                    f"Action: {checkin_row.get('action', '')}\n"
                    f"When: {self._format_history_timestamp(str(checkin_row.get('timestamp', '')))}\n"
                    f"By: {checkin_row.get('user_full_name', '') or checkin_row.get('user_initials', '')}"
                )
            values = [
                revision_id,
                self._format_history_timestamp(str(entry.get("created_at", ""))),
                checked_in_value,
                str(entry.get("sha256", ""))[:12],
                str(entry.get("note", "")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, row)
                if col == 2 and checked_in_tooltip:
                    item.setToolTip(checked_in_tooltip)
                elif col == 3:
                    item.setToolTip(str(entry.get("sha256", "")))
                else:
                    item.setToolTip(value)
                table.setItem(row, col, item)
        if table.rowCount() > 0:
            table.setCurrentCell(0, 0)
        layout.addWidget(table)
        buttons = QDialogButtonBox()
        switch_btn = buttons.addButton("Switch To Selected", QDialogButtonBox.AcceptRole)
        cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        selected: Dict[str, int] = {"row": -1}
        switch_btn.clicked.connect(lambda: (selected.__setitem__("row", table.currentRow()), dialog.accept()))
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        row = selected["row"]
        if row < 0 or row >= len(revisions):
            return None
        return revisions[row]

    def _checkin_history_by_revision_id_for_record(
        self, record: CheckoutRecord
    ) -> Dict[str, Dict[str, str]]:
        source_path = Path(record.source_file)
        source_dir = source_path.parent
        source_name = source_path.name
        indexed: Dict[str, Dict[str, str]] = {}
        for row in self._read_history_rows(source_dir):
            revision_id = str(row.get("revision_id", "")).strip()
            if not revision_id:
                continue
            if str(row.get("file_name", "")).strip() != source_name:
                continue
            action = str(row.get("action", "")).strip()
            if "CHECK_IN" not in action:
                continue
            indexed[revision_id] = row
        return indexed

    def _switch_record_to_revision(self, record: CheckoutRecord, revision: Dict[str, object]) -> bool:
        if not self._ensure_saved_state_before_revision_switch(record):
            return False
        project_dir = Path(record.project_dir)
        relative_snapshot = str(revision.get("snapshot_file", "")).strip()
        if not relative_snapshot:
            self._error("Selected revision is missing snapshot data.")
            return False
        snapshot_path = project_dir / relative_snapshot
        local_path = Path(record.local_file)
        if not snapshot_path.exists():
            self._error(f"Revision snapshot file is missing:\n{snapshot_path}")
            return False
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_path, local_path)
        except OSError as exc:
            self._error(f"Could not switch to revision:\n{exc}")
            return False
        return True

    def _create_revision_snapshot_for_selected_records(self) -> None:
        indexes = self._selected_checked_out_record_indexes()
        if not indexes:
            self._error("Select at least one checked-out file to snapshot.")
            return
        accepted, note = self._prompt_revision_note("Create Revision Snapshot")
        if not accepted:
            return
        created_count = 0
        with self._busy_action("Creating revision snapshot(s)..."):
            for idx in indexes:
                if not (0 <= idx < len(self.records)):
                    continue
                created = self._create_revision_snapshot_for_record(self.records[idx], note=note)
                if created:
                    created_count += 1
        if created_count == 0:
            self._info("No new snapshots were created (current states already tracked).")
        else:
            self._info(f"Created {created_count} revision snapshot(s).")

    def _switch_selected_record_to_revision(self) -> None:
        indexes = self._selected_checked_out_record_indexes()
        if len(indexes) != 1:
            self._error("Select exactly one checked-out file to switch revisions.")
            return
        record = self.records[indexes[0]]
        revision = self._choose_revision_for_record(record)
        if not revision:
            return
        with self._busy_action("Switching file revision..."):
            switched = self._switch_record_to_revision(record, revision)
        if switched:
            self._info(f"Switched to revision {revision.get('id', '')}.")

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
        self, actions: List[PendingCheckinAction], workflow: str
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

                revision_id = ""
                if action.record_idx >= 0 and 0 <= action.record_idx < len(self.records):
                    record = self.records[action.record_idx]
                    checkin_revision = self._create_revision_snapshot_for_record(
                        record,
                        note=f"Check-in snapshot ({self._history_action_for_checkin(action, workflow)}).",
                        origin=f"{workflow}_checkin",
                        snapshot_source_path=source_file,
                    )
                    if checkin_revision:
                        revision_id = str(checkin_revision.get("id", ""))

                self._append_history(
                    source_file.parent,
                    self._history_action_for_checkin(action, workflow),
                    source_file.name,
                    revision_id,
                )
                self._invalidate_directory_caches(source_file.parent)
                if action.record_idx >= 0:
                    completed_indexes.append(action.record_idx)
            except OSError as exc:
                errors.append(f"{source_file.name}: {exc}")

        if completed_indexes:
            self._remove_record_indexes(completed_indexes)
            self._save_records()
        return errors

    def _history_action_for_checkin(self, action: PendingCheckinAction, workflow: str) -> str:
        if workflow == "standard":
            if action.action_mode in {"modified", "tracked_modified", "selected_modified"}:
                return "CHECK_IN_MODIFIED"
            return "CHECK_IN_UNCHANGED"

        if workflow == "force":
            if action.action_mode == "tracked_modified":
                return "CHECK_IN_MODIFIED"
            if action.action_mode == "selected_modified":
                return "FORCE_CHECK_IN_MODIFIED"
            return "FORCE_CHECK_IN_UNCHANGED"

        if action.action_mode in {"modified", "tracked_modified", "selected_modified"}:
            return "CHECK_IN_MODIFIED"
        return "CHECK_IN_UNCHANGED"

    def _describe_checkin_action(self, action: PendingCheckinAction) -> str:
        if action.action_mode == "skip":
            return "Skip file"
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
            for action in planned_actions:
                updated = self._select_force_checkin_file_for_action(action)
                if updated is None:
                    return None
            planned_actions = list(planned_actions)

        while True:
            review = self._show_pending_actions_dialog(
                "Review Force Check-In Actions", planned_actions, allow_modify=True
            )
            if review == "commit":
                return planned_actions
            if review == "cancel":
                return None
            updated_plans: List[PendingCheckinAction] = []
            for action in planned_actions:
                updated = self._select_force_checkin_file_for_action(action)
                if updated is None:
                    return None
                updated_plans.append(updated)
            planned_actions = updated_plans

    def _checkin_record_indexes(self, selected_indexes: set[int]) -> None:
        if not selected_indexes:
            self._error("Select at least one checked-out row to check in.")
            return

        selected_checked_out = 0
        selected_reference = 0
        for record_idx in selected_indexes:
            if not (0 <= record_idx < len(self.records)):
                continue
            if self.records[record_idx].record_type == "checked_out":
                selected_checked_out += 1
            elif self.records[record_idx].record_type == "reference_copy":
                selected_reference += 1
        if selected_checked_out == 0 and selected_reference > 0:
            self._error("Reference copies cannot be checked in. Use 'Remove Selected Ref' instead.")
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
            if record.record_type != "checked_out":
                continue
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
        if not actions:
            self._error("Select at least one checked-out row to check in.")
            return

        with self._debug_timed("checkin_selected", selected_count=len(actions)):
            with self._busy_action("Checking in file(s)..."):
                errors = self._perform_pending_checkin_actions(actions, "standard")
                self._refresh_source_files()
                self._render_records_tables()

        if errors:
            self._error("Some files failed to check in:\n" + "\n".join(errors))
        else:
            self._info("Check-in complete.")

    def _checkin_selected(self) -> None:
        if not self._validate_identity():
            return
        self._checkin_record_indexes(set(self._selected_record_indexes()))

    def _checkin_selected_source_files_if_owned(self) -> None:
        if not self._validate_identity():
            return
        selected_files = self._selected_source_file_paths()
        if not selected_files:
            self._error("Select at least one source file to check in.")
            return
        initials = self._normalize_initials()
        selected_paths = {str(path) for path in selected_files}
        selected_record_indexes: set[int] = set()
        for idx, record in enumerate(self.records):
            if record.record_type != "checked_out":
                continue
            if record.initials != initials:
                continue
            if record.source_file in selected_paths or record.locked_source_file in selected_paths:
                selected_record_indexes.add(idx)
        if not selected_record_indexes:
            self._error("No selected files are currently checked out by your initials.")
            return
        self._checkin_record_indexes(selected_record_indexes)

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
        with self._busy_action("Adding file(s) to source..."):
            for file_path in file_paths:
                local_file = Path(file_path)
                target_file = current_directory / local_file.name
                if target_file.exists():
                    errors.append(f"Already exists in source: {target_file.name}")
                    continue

                try:
                    shutil.copy2(local_file, target_file)
                    self._append_history(current_directory, "ADD_FILE", target_file.name)
                    self._invalidate_directory_caches(current_directory)
                except OSError as exc:
                    errors.append(f"{local_file.name}: {exc}")

            self._refresh_source_files()

        if errors:
            self._error("Some files failed to add:\n" + "\n".join(errors))
        else:
            self._info("File(s) added to source folder.")

    def _open_source_item(self, item: QListWidgetItem) -> None:
        self._open_paths([Path(item.data(Qt.UserRole))])

    def _show_source_file_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.files_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.files_list.visualItemRect(item)
        self._show_source_file_context_menu(rect.center())

    def _show_source_file_context_menu(self, pos: QPoint) -> None:
        item = self.files_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.files_list.clearSelection()
            item.setSelected(True)
            self.files_list.setCurrentItem(item)

        menu = QMenu(self)
        actions = [
            ("Open Selected", "open"),
            ("Check Out Selected", "checkout"),
            ("Check In Selected (If Mine)", "checkin_mine"),
            ("Copy As Reference", "reference"),
            ("View History", "history"),
            ("View File Notes", "notes"),
            ("Add Local File(s) To Here", "add_local"),
            ("Add Selected To Favorites", "favorite"),
            ("Refresh", "refresh"),
        ]
        action_map: Dict[QAction, str] = {}
        for label, action_id in actions:
            action = menu.addAction(label)
            action_map[action] = action_id
        chosen = menu.exec(self.files_list.mapToGlobal(pos))
        if chosen in action_map:
            self._handle_source_file_context_action(action_map[chosen])

    def _handle_source_file_context_action(self, action_id: str) -> None:
        if action_id == "open":
            self._open_selected_source_files()
            return
        if action_id == "checkout":
            self._checkout_selected()
            return
        if action_id == "checkin_mine":
            self._checkin_selected_source_files_if_owned()
            return
        if action_id == "reference":
            self._copy_selected_as_reference()
            return
        if action_id == "history":
            self._show_selected_file_history()
            return
        if action_id == "notes":
            self._open_notes_for_selected_source_file()
            return
        if action_id == "add_local":
            self._add_new_files_to_source()
            return
        if action_id == "favorite":
            self._add_selected_source_files_to_favorites()
            return
        if action_id == "refresh":
            self._refresh_source_files()
            return

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

    def _show_records_context_menu_for_row(self, row: int, _column: int) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        if row < 0:
            return
        table.selectRow(row)
        item = table.item(row, 0)
        if not item:
            return
        pos = table.visualItemRect(item).center()
        self._show_records_context_menu(pos)

    def _show_records_context_menu(self, pos: QPoint) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return

        row = table.rowAt(pos.y())
        if row >= 0 and (not table.item(row, 0) or not table.item(row, 0).isSelected()):
            table.clearSelection()
            table.selectRow(row)

        menu = QMenu(self)
        action_map: Dict[QAction, str] = {}
        open_action = menu.addAction("Open Selected")
        action_map[open_action] = "open"
        if table is self.reference_records_table:
            remove_ref_action = menu.addAction("Remove Selected Ref")
            action_map[remove_ref_action] = "remove_ref"
        else:
            checkin_action = menu.addAction("Check In Selected")
            action_map[checkin_action] = "checkin"
            snapshot_action = menu.addAction("Create Revision Snapshot")
            action_map[snapshot_action] = "snapshot"
            switch_action = menu.addAction("Switch To Revision")
            action_map[switch_action] = "switch_revision"
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen in action_map:
            self._handle_records_context_action(action_map[chosen])

    def _handle_records_context_action(self, action_id: str) -> None:
        if action_id == "open":
            self._open_selected_record_files()
            return
        if action_id == "checkin":
            self._checkin_selected()
            return
        if action_id == "snapshot":
            self._create_revision_snapshot_for_selected_records()
            return
        if action_id == "switch_revision":
            self._switch_selected_record_to_revision()
            return
        if action_id == "remove_ref":
            self._remove_selected_reference_records()
            return

    def _open_selected_record_files(self) -> None:
        indexes = self._selected_record_indexes()
        if not indexes:
            self._error("Select at least one checked-out file to open.")
            return
        paths = [Path(self.records[idx].local_file) for idx in indexes if 0 <= idx < len(self.records)]
        self._open_paths(paths)

    def _remove_selected_reference_records(self) -> None:
        indexes = self._selected_record_indexes()
        if not indexes:
            self._error("Select at least one reference copy row to remove.")
            return

        removable_indexes = [
            idx
            for idx in indexes
            if 0 <= idx < len(self.records) and self.records[idx].record_type == "reference_copy"
        ]
        if not removable_indexes:
            self._error("Selected rows do not contain reference copies.")
            return

        with self._busy_action("Removing reference copy record(s)..."):
            self._remove_record_indexes(removable_indexes)
            self._save_records()
            self._render_records_tables()

    def _show_controlled_files_context_menu(self, pos: QPoint) -> None:
        row = self.controlled_files_table.rowAt(pos.y())
        if row >= 0 and (not self.controlled_files_table.item(row, 0) or not self.controlled_files_table.item(row, 0).isSelected()):
            self.controlled_files_table.clearSelection()
            self.controlled_files_table.selectRow(row)

        menu = QMenu(self)
        refresh_action = menu.addAction("Refresh")
        force_action = menu.addAction("Force Check In Selected")
        notes_action = menu.addAction("View File Notes")
        chosen = menu.exec(self.controlled_files_table.viewport().mapToGlobal(pos))
        if chosen == refresh_action:
            self._refresh_controlled_files()
        elif chosen == force_action:
            self._force_checkin_selected()
        elif chosen == notes_action:
            self._open_notes_for_selected_source_file()

    def _show_tracked_projects_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.tracked_projects_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.tracked_projects_list.visualItemRect(item)
        self._show_tracked_projects_context_menu(rect.center())

    def _show_tracked_projects_context_menu(self, pos: QPoint) -> None:
        item = self.tracked_projects_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.tracked_projects_list.clearSelection()
            item.setSelected(True)
            self.tracked_projects_list.setCurrentItem(item)

        menu = QMenu(self)
        load_action = menu.addAction("Load Selected")
        files_action = menu.addAction("Project Files Manager")
        edit_action = menu.addAction("Edit Selected")
        open_loc_action = menu.addAction("Open Location")
        untrack_action = menu.addAction("Untrack Selected")
        move_up_action = menu.addAction("Move Up")
        move_down_action = menu.addAction("Move Down")
        move_top_action = menu.addAction("Move to Top")
        move_bottom_action = menu.addAction("Move to Bottom")
        chosen = menu.exec(self.tracked_projects_list.mapToGlobal(pos))
        if chosen == load_action:
            self._load_selected_tracked_project()
        elif chosen == files_action:
            self._open_project_files_manager_for_selected_project()
        elif chosen == edit_action:
            self._edit_selected_project()
        elif chosen == open_loc_action:
            self._open_selected_project_location()
        elif chosen == untrack_action:
            self._remove_selected_project()
        elif chosen == move_up_action:
            self._move_selected_project_up()
        elif chosen == move_down_action:
            self._move_selected_project_down()
        elif chosen == move_top_action:
            self._move_selected_project_top()
        elif chosen == move_bottom_action:
            self._move_selected_project_bottom()

    def _show_favorites_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.favorites_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.favorites_list.visualItemRect(item)
        self._show_favorites_context_menu(rect.center())

    def _show_favorites_context_menu(self, pos: QPoint) -> None:
        item = self.favorites_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.favorites_list.clearSelection()
            item.setSelected(True)
            self.favorites_list.setCurrentItem(item)

        menu = QMenu(self)
        add_action = menu.addAction("Add Favorite")
        add_global_action = menu.addAction("Add Selected To Global Favorites")
        open_action = menu.addAction("Open Selected")
        remove_action = menu.addAction("Remove Favorite")
        move_up_action = menu.addAction("Move Up")
        move_down_action = menu.addAction("Move Down")
        move_top_action = menu.addAction("Move to Top")
        move_bottom_action = menu.addAction("Move to Bottom")
        chosen = menu.exec(self.favorites_list.mapToGlobal(pos))
        if chosen == add_action:
            self._browse_and_add_favorites()
        elif chosen == add_global_action:
            self._add_selected_project_favorites_to_global()
        elif chosen == open_action:
            self._open_selected_favorites()
        elif chosen == remove_action:
            self._remove_selected_favorites()
        elif chosen == move_up_action:
            self._move_selected_favorite_up()
        elif chosen == move_down_action:
            self._move_selected_favorite_down()
        elif chosen == move_top_action:
            self._move_selected_favorite_top()
        elif chosen == move_bottom_action:
            self._move_selected_favorite_bottom()

    def _show_notes_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.notes_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.notes_list.visualItemRect(item)
        self._show_notes_context_menu(rect.center())

    def _show_notes_context_menu(self, pos: QPoint) -> None:
        item = self.notes_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.notes_list.clearSelection()
            item.setSelected(True)
            self.notes_list.setCurrentItem(item)

        menu = QMenu(self)
        new_action = menu.addAction("New Note")
        edit_action = menu.addAction("Edit Selected")
        remove_action = menu.addAction("Remove Selected")
        move_up_action = menu.addAction("Move Up")
        move_down_action = menu.addAction("Move Down")
        move_top_action = menu.addAction("Move to Top")
        move_bottom_action = menu.addAction("Move to Bottom")
        chosen = menu.exec(self.notes_list.mapToGlobal(pos))
        if chosen == new_action:
            self._create_note()
        elif chosen == edit_action:
            self._edit_selected_note()
        elif chosen == remove_action:
            self._remove_selected_note()
        elif chosen == move_up_action:
            self._move_selected_note_up()
        elif chosen == move_down_action:
            self._move_selected_note_down()
        elif chosen == move_top_action:
            self._move_selected_note_top()
        elif chosen == move_bottom_action:
            self._move_selected_note_bottom()

    def _show_milestones_context_menu_for_item(self, item: QListWidgetItem) -> None:
        self.milestones_list.setCurrentItem(item)
        item.setSelected(True)
        rect = self.milestones_list.visualItemRect(item)
        self._show_milestones_context_menu(rect.center())

    def _show_milestones_context_menu(self, pos: QPoint) -> None:
        item = self.milestones_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.milestones_list.clearSelection()
            item.setSelected(True)
            self.milestones_list.setCurrentItem(item)

        menu = QMenu(self)
        new_action = menu.addAction("New Milestone")
        view_action = menu.addAction("View Selected")
        remove_action = menu.addAction("Remove Selected")
        chosen = menu.exec(self.milestones_list.mapToGlobal(pos))
        if chosen == new_action:
            self._create_milestone()
        elif chosen == view_action:
            self._view_selected_milestone()
        elif chosen == remove_action:
            self._remove_selected_milestone()

    def _show_source_roots_context_menu(self, pos: QPoint) -> None:
        item = self.source_roots_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.source_roots_list.clearSelection()
            item.setSelected(True)
            self.source_roots_list.setCurrentItem(item)

        menu = QMenu(self)
        track_browse_action = menu.addAction("Track Dir (Browse)")
        track_current_action = menu.addAction("Track Directory")
        untrack_action = menu.addAction("Untrack Dir")
        move_up_action = menu.addAction("Move Up")
        move_down_action = menu.addAction("Move Down")
        move_top_action = menu.addAction("Move to Top")
        move_bottom_action = menu.addAction("Move to Bottom")
        chosen = menu.exec(self.source_roots_list.mapToGlobal(pos))
        if chosen == track_browse_action:
            self._add_source_directory()
        elif chosen == track_current_action:
            self._track_current_directory()
        elif chosen == untrack_action:
            self._remove_source_directory()
        elif chosen == move_up_action:
            self._move_selected_source_up()
        elif chosen == move_down_action:
            self._move_selected_source_down()
        elif chosen == move_top_action:
            self._move_selected_source_top()
        elif chosen == move_bottom_action:
            self._move_selected_source_bottom()

    def _open_paths(self, paths: List[Path]) -> None:
        errors: List[str] = []
        with self._debug_timed("open_paths", path_count=len(paths)):
            with self._busy_action("Opening file(s)..."):
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

        selected_rows = self.controlled_files_table.selectionModel().selectedRows()
        if not selected_rows:
            self._error("Select at least one controlled file to force check in.")
            return

        choice = self._show_force_checkin_warning_dialog()
        if choice == "cancel":
            return

        entries: List[Dict[str, str]] = []
        for model_index in selected_rows:
            item = self.controlled_files_table.item(model_index.row(), 0)
            if item is None:
                continue
            entry = item.data(Qt.UserRole)
            if not isinstance(entry, dict):
                continue
            entries.append(entry)

        with self._debug_timed("force_checkin_selected_plan", choice=choice, selected_count=len(entries)):
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

        with self._debug_timed("force_checkin_selected_apply", action_count=len(actions)):
            with self._busy_action("Force checking in file(s)..."):
                errors = self._perform_pending_checkin_actions(actions, "force")
                self._refresh_source_files()
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

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["Timestamp", "Action", "Revision", "Initials", "Full Name"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 320))
        table.setColumnWidth(4, max(table.columnWidth(4), 220))
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
        with self._debug_timed("render_records_tables", record_count=len(self.records)):
            checked_out_items = [
                (idx, record)
                for idx, record in enumerate(self.records)
                if record.record_type == "checked_out"
            ]
            self._populate_records_table(self.all_records_table, checked_out_items)
            current_project = self.current_project_dir
            filtered = [
                (idx, record)
                for idx, record in checked_out_items
                if record.project_dir == current_project
            ]
            self._populate_records_table(self.project_records_table, filtered)
            reference_items = [
                (idx, record)
                for idx, record in enumerate(self.records)
                if record.record_type == "reference_copy"
            ]
            self._populate_reference_records_table(self.reference_records_table, reference_items)

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

    def _populate_reference_records_table(
        self, table: QTableWidget, items: List[tuple[int, CheckoutRecord]]
    ) -> None:
        table.setRowCount(len(items))
        for row_idx, (record_idx, record) in enumerate(items):
            values = [
                self._short_path(record.source_file),
                self._local_display_name(record.local_file),
                record.project_name,
                self._format_checkout_timestamp(record.checked_out_at),
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_idx == 0:
                    item.setData(Qt.UserRole, record_idx)
                    item.setToolTip(record.source_file)
                elif col_idx == 1:
                    item.setToolTip(record.local_file)
                elif col_idx == 2:
                    item.setToolTip(record.project_dir)
                else:
                    item.setToolTip(record.checked_out_at)
                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 280))
        table.setColumnWidth(1, max(table.columnWidth(1), 200))
        table.setColumnWidth(2, max(table.columnWidth(2), 180))
        table.setColumnWidth(3, max(table.columnWidth(3), 150))

    def _load_records(self) -> None:
        with self._debug_timed("load_records"):
            data = self._read_json_candidates(
                [self._records_file_path(), LEGACY_RECORDS_FILE]
            )
            raw_records = data
            if isinstance(data, dict):
                raw_records = data.get("records", [])
            if not isinstance(raw_records, list):
                self._render_records_tables()
                self._debug_event("records_loaded", count=0)
                return

            try:
                self.records = []
                for entry in raw_records:
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
                            record_type=str(entry.get("record_type", "checked_out") or "checked_out"),
                        )
                    )
            except (OSError, ValueError, TypeError):
                self.records = []

            self._render_records_tables()
            self._debug_event("records_loaded", count=len(self.records))

    def _save_records(self) -> None:
        records_path = self._records_file_path()
        self._ensure_parent_dir(records_path)
        records_path.write_text(
            json.dumps(
                {
                    "schema_version": RECORDS_SCHEMA_VERSION,
                    "app_version": APP_VERSION,
                    "records": [asdict(record) for record in self.records],
                },
                indent=2,
            ),
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
        self._save_global_favorites()
        self._save_global_notes()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = DocumentControlApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

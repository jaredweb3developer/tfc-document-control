from __future__ import annotations

import app as app_module
from app import *


class UiMixin:
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
            toggle.setStyleSheet(
                """
                QToolButton {
                    font-weight: 600;
                }
                QToolButton:checked {
                    color: white;
                }
                QToolButton:!checked {
                    color: black;
                }
                """
            )

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
            self.tracked_projects_list.itemDoubleClicked.connect(self._load_tracked_project_item)
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
            tracked_header = QHBoxLayout()
            tracked_header.addWidget(QLabel("Tracked Projects"))
            tracked_header.addStretch()
            tracked_header.addWidget(
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
            tracked_layout.addLayout(tracked_header)
            tracked_layout.addWidget(self.project_search_edit)
            tracked_layout.addWidget(self.tracked_projects_list, stretch=1)

            favorites_panel = QWidget()
            favorites_layout = QVBoxLayout(favorites_panel)
            favorites_header = QHBoxLayout()
            favorites_header.addWidget(QLabel("Favorites & Local Files"))
            favorites_header.addStretch()
            favorites_header.addWidget(
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
            favorites_layout.addLayout(favorites_header)

            self.favorites_tabs = QTabWidget()
            project_favorites_tab = QWidget()
            project_favorites_layout = QVBoxLayout(project_favorites_tab)
            self.project_favorites_search_edit = QLineEdit()
            self.project_favorites_search_edit.setPlaceholderText("Search project favorites")
            self.project_favorites_search_edit.textChanged.connect(
                lambda _text: self._refresh_favorites_list(self._current_project_favorites())
            )
            project_favorites_layout.addWidget(self.project_favorites_search_edit)
            self.favorites_list = QListWidget()
            self.favorites_list.itemDoubleClicked.connect(self._open_favorite_item)
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
            self.global_favorites_list.itemDoubleClicked.connect(self._open_global_favorite_item)
            self.global_favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.global_favorites_list.customContextMenuRequested.connect(
                self._show_global_favorites_context_menu
            )
            global_favorites_layout.addWidget(self.global_favorites_list, stretch=1)
            self.favorites_tabs.addTab(global_favorites_tab, "Global Favorites")

            checked_out_favorites_tab = QWidget()
            checked_out_favorites_layout = QVBoxLayout(checked_out_favorites_tab)
            self.project_checked_out_search_edit = QLineEdit()
            self.project_checked_out_search_edit.setPlaceholderText("Search checked out files")
            self.project_checked_out_search_edit.textChanged.connect(self._refresh_project_local_files_lists)
            checked_out_favorites_layout.addWidget(self.project_checked_out_search_edit)
            self.project_checked_out_list = QListWidget()
            self.project_checked_out_list.setSelectionMode(QListWidget.ExtendedSelection)
            self.project_checked_out_list.itemDoubleClicked.connect(self._open_project_local_checked_out_item)
            self.project_checked_out_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.project_checked_out_list.customContextMenuRequested.connect(
                self._show_project_checked_out_context_menu
            )
            checked_out_favorites_layout.addWidget(self.project_checked_out_list, stretch=1)
            self.favorites_tabs.addTab(checked_out_favorites_tab, "Checked Out")

            reference_favorites_tab = QWidget()
            reference_favorites_layout = QVBoxLayout(reference_favorites_tab)
            self.project_reference_search_edit = QLineEdit()
            self.project_reference_search_edit.setPlaceholderText("Search reference files")
            self.project_reference_search_edit.textChanged.connect(self._refresh_project_local_files_lists)
            reference_favorites_layout.addWidget(self.project_reference_search_edit)
            self.project_reference_list = QListWidget()
            self.project_reference_list.setSelectionMode(QListWidget.ExtendedSelection)
            self.project_reference_list.itemDoubleClicked.connect(self._open_project_local_reference_item)
            self.project_reference_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.project_reference_list.customContextMenuRequested.connect(
                self._show_project_reference_context_menu
            )
            reference_favorites_layout.addWidget(self.project_reference_list, stretch=1)
            self.favorites_tabs.addTab(reference_favorites_tab, "Reference Files")
            favorites_layout.addWidget(self.favorites_tabs, stretch=1)

            notes_panel = QWidget()
            notes_layout = QVBoxLayout(notes_panel)
            notes_header = QHBoxLayout()
            notes_header.addWidget(QLabel("Notes"))
            notes_header.addStretch()
            notes_header.addWidget(
                self._build_options_button(
                    [
                        ("New Note", self._create_note),
                        ("Presets", self._show_note_presets_dialog),
                        ("Edit Selected", self._edit_selected_note),
                        ("Copy Selected To Project", self._copy_selected_note_to_project),
                        ("Move Selected To Project", self._move_selected_note_to_project),
                        ("Remove Selected", self._remove_selected_note),
                        ("---", self._create_note),
                        ("Move Up", self._move_selected_note_up),
                        ("Move Down", self._move_selected_note_down),
                        ("Move to Top", self._move_selected_note_top),
                        ("Move to Bottom", self._move_selected_note_bottom),
                    ]
                )
            )
            notes_layout.addLayout(notes_header)
            self.project_notes_search_edit = QLineEdit()
            self.project_notes_search_edit.setPlaceholderText("Search notes")
            self.project_notes_search_edit.textChanged.connect(
                lambda _text: self._refresh_notes_list(self._current_project_notes())
            )
            notes_layout.addWidget(self.project_notes_search_edit)
            self.notes_list = QListWidget()
            self.notes_list.itemDoubleClicked.connect(self._edit_note_item)
            self.notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.notes_list.customContextMenuRequested.connect(self._show_notes_context_menu)
            notes_layout.addWidget(self.notes_list, stretch=1)

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
            tracked_header = QHBoxLayout()
            tracked_header.addWidget(QLabel("Tracked Source Directories"))
            tracked_header.addStretch()
            tracked_header.addWidget(
                self._build_options_button(
                    [
                        ("Track Dir (Browse)", self._add_source_directory),
                        ("Track Directory", self._track_current_directory),
                        ("Relink Directory", self._relink_selected_source_directory),
                        ("View Location", self._view_selected_source_directory_location),
                        ("Untrack Dir", self._remove_source_directory),
                        ("---", self._track_current_directory),
                        ("Move Up", self._move_selected_source_up),
                        ("Move Down", self._move_selected_source_down),
                        ("Move to Top", self._move_selected_source_top),
                        ("Move to Bottom", self._move_selected_source_bottom),
                    ]
                )
            )
            tracked_layout.addLayout(tracked_header)
            self.source_roots_list = QListWidget()
            self.source_roots_list.currentItemChanged.connect(self._on_source_root_changed)
            self.source_roots_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.source_roots_list.customContextMenuRequested.connect(self._show_source_roots_context_menu)
            self.source_roots_list.setMinimumWidth(220)
            tracked_layout.addWidget(self.source_roots_list)

            directory_panel = QWidget()
            directory_layout = QVBoxLayout(directory_panel)
            directory_header = QHBoxLayout()
            directory_header.addWidget(QLabel("Directory Browser"))
            directory_header.addStretch()
            directory_header.addWidget(
                self._build_options_button(
                    [
                        ("Browse", self._browse_directory_tree_root),
                        ("View Location", self._view_current_directory_location),
                        ("Track Directory", self._track_current_directory),
                    ]
                )
            )
            directory_layout.addLayout(directory_header)
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

            files_panel = QWidget()
            files_layout = QVBoxLayout(files_panel)
            files_header = QHBoxLayout()
            files_header.addWidget(QLabel("Files"))
            files_header.addStretch()
            files_header.addWidget(
                self._build_options_button(
                    [
                        ("Refresh", self._refresh_source_files),
                        ("Open Selected", self._open_selected_source_files),
                        ("Rename Selected", self._rename_selected_source_file),
                        ("Delete Selected", self._delete_selected_source_files),
                        ("Check Out Selected", self._checkout_selected),
                        ("Check In Selected (If Mine)", self._checkin_selected_source_files_if_owned),
                        ("View History", self._show_selected_file_history),
                        ("View File Notes", self._open_notes_for_selected_source_file),
                        ("---", self._open_selected_source_files),
                        ("Add Selected To Favorites", self._add_selected_source_files_to_favorites),
                        ("Copy As Reference", self._copy_selected_as_reference),
                        ("Add Local File(s) To Here", self._add_new_files_to_source),
                    ]
                )
            )
            files_layout.addLayout(files_header)
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

            self.files_list = QTableWidget(0, 4)
            self.files_list.setHorizontalHeaderLabels(["Name", "Date modified", "Type", "Size"])
            self.files_list.setSelectionBehavior(QTableWidget.SelectRows)
            self.files_list.setSelectionMode(QTableWidget.ExtendedSelection)
            self.files_list.setEditTriggers(QTableWidget.NoEditTriggers)
            self.files_list.setSortingEnabled(True)
            self.files_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.files_list.customContextMenuRequested.connect(self._show_source_file_context_menu)
            self.files_list.itemDoubleClicked.connect(self._open_source_item)
            files_header = self.files_list.horizontalHeader()
            files_header.setSortIndicatorShown(True)
            files_header.setSectionResizeMode(0, QHeaderView.Stretch)
            files_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            files_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            files_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            files_layout.addWidget(self.files_list, stretch=1)

            controlled_panel = QWidget()
            controlled_layout = QVBoxLayout(controlled_panel)
            directory_group_header = QHBoxLayout()
            directory_group_header.addWidget(QLabel("Directory"))
            directory_group_header.addStretch()
            directory_group_header.addWidget(
                self._build_options_button(
                    [
                        ("Refresh", self._refresh_controlled_files),
                        ("Force Check In", self._force_checkin_selected),
                        ("View File Notes", self._open_notes_for_selected_source_file),
                    ]
                )
            )
            controlled_layout.addLayout(directory_group_header)
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

            header = QHBoxLayout()
            header.addWidget(QLabel("Records"))
            header.addStretch()
            header.addWidget(
                self._build_options_button(
                    [
                        ("Open Selected", self._open_selected_record_files),
                        ("Check In Selected", self._checkin_selected),
                        ("Create Revision Snapshot", self._create_revision_snapshot_for_selected_records),
                        ("View Revision", self._view_selected_record_revision),
                        ("Switch To Revision", self._switch_selected_record_to_revision),
                        ("Remove Selected Ref", self._remove_selected_reference_records),
                        ("Customize/Organize", self._customize_selected_active_records),
                    ]
                )
            )
            layout.addLayout(header)

            self.records_tabs = QTabWidget()
            self._records_tab_tables: Dict[QWidget, QTableWidget] = {}
            self.all_records_table = self._build_records_table()
            self.project_records_table = self._build_records_table()
            self.reference_records_table = self._build_reference_records_table()
            self.all_records_search_edit = QLineEdit()
            self.all_records_search_edit.setPlaceholderText("Search all checked out files")
            self.all_records_search_edit.textChanged.connect(self._render_records_tables)
            self.project_records_search_edit = QLineEdit()
            self.project_records_search_edit.setPlaceholderText("Search current project files")
            self.project_records_search_edit.textChanged.connect(self._render_records_tables)
            self.reference_records_search_edit = QLineEdit()
            self.reference_records_search_edit.setPlaceholderText("Search reference copies")
            self.reference_records_search_edit.textChanged.connect(self._render_records_tables)
            self.records_tabs.addTab(
                self._build_records_tab_page(self.all_records_search_edit, self.all_records_table),
                "All Checked Out",
            )
            self.records_tabs.addTab(
                self._build_records_tab_page(self.project_records_search_edit, self.project_records_table),
                "Current Project",
            )
            self.records_tabs.addTab(
                self._build_records_tab_page(self.reference_records_search_edit, self.reference_records_table),
                "Reference Copies",
            )
            layout.addWidget(self.records_tabs)

            return group

        def _build_records_tab_page(self, search_edit: QLineEdit, table: QTableWidget) -> QWidget:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.addWidget(search_edit)
            page_layout.addWidget(table, stretch=1)
            self._records_tab_tables[page] = table
            return page

        def _build_global_favorites_group(self) -> QGroupBox:
            group = QGroupBox("Global Favorites")
            layout = QVBoxLayout(group)

            self.global_favorites_search_edit = QLineEdit()
            self.global_favorites_search_edit.setPlaceholderText("Search global favorites")
            self.global_favorites_search_edit.textChanged.connect(self._refresh_global_favorites_list)
            layout.addWidget(self.global_favorites_search_edit)

            self.global_favorites_list = QListWidget()
            self.global_favorites_list.setSelectionMode(QListWidget.ExtendedSelection)
            self.global_favorites_list.itemDoubleClicked.connect(self._open_global_favorite_item)
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

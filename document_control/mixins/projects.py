from __future__ import annotations

import app as app_module
from app import *


class ProjectsMixin:
        def _create_or_update_project(
            self,
            name: str,
            project_dir: Path,
            sources: Optional[List[str]] = None,
            local_directories: Optional[List[str]] = None,
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
                        local_directories=local_directories or [],
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

        def _default_new_project_name(self) -> str:
            return ""

        def _show_new_project_dialog(self) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("New Project")
            dialog.resize(640, 280)
            layout = QVBoxLayout(dialog)

            form_layout = QGridLayout()
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("Project name")
            name_edit.setText(self._default_new_project_name())
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
                notes=self._default_notes_from_presets(),
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
            if config_path.name != app_module.PROJECT_CONFIG_FILE:
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

            if item.text() == app_module.DEFAULT_PROJECT_NAME:
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
                local_directories = [
                    str(item) for item in config.get("local_directories", [])
                ]  # type: ignore[arg-type]
                extension_filters = [
                    str(item) for item in config.get("extension_filters", [])
                ]  # type: ignore[arg-type]
                filter_mode = str(config.get("filter_mode", "No Filter"))
                favorites = [str(item) for item in config.get("favorites", [])]  # type: ignore[arg-type]
                notes = [dict(item) for item in config.get("notes", [])]  # type: ignore[arg-type]
                selected_source = str(config.get("selected_source", "")).strip()
                selected_local_directory = str(config.get("selected_local_directory", "")).strip()
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
                self._refresh_local_roots(local_directories, selected_local_directory)
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
                skip_file_names = {app_module.PROJECT_CONFIG_FILE, app_module.FILE_VERSIONS_FILE}
                for local_path in project_dir.rglob("*"):
                    if not local_path.is_file():
                        continue
                    if local_path.name in skip_file_names:
                        continue
                    if app_module.FILE_VERSIONS_DIR in local_path.parts:
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
                            file_id=record.file_id,
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
                view_revision_action = None
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
                    view_revision_action = menu.addAction("View Revision")
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
                elif view_revision_action is not None and chosen == view_revision_action:
                    self._view_record_revision_from_indexes(selected_indexes())
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
            view_revision_btn = QPushButton("View Revision")
            view_revision_btn.clicked.connect(lambda: self._view_record_revision_from_indexes(selected_indexes()))
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
            button_bar.addWidget(view_revision_btn)
            button_bar.addWidget(switch_btn)
            button_bar.addWidget(refresh_btn)
            button_bar.addStretch()
            button_bar.addWidget(close_btn)
            layout.addLayout(button_bar)

            refresh_tables()
            dialog.exec()

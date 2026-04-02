from __future__ import annotations

import app as app_module
from app import *


class SourcesMixin:
        def _is_source_file_name_candidate(self, file_name: str) -> bool:
            normalized_name = file_name.strip()
            if not normalized_name:
                return False
            if normalized_name in {
                app_module.SOURCE_INDEX_FILE,
                app_module.HISTORY_FILE_NAME,
                app_module.LEGACY_HISTORY_FILE_NAME,
                app_module.DIRECTORY_NOTES_FILE,
            }:
                return False
            suffix = Path(normalized_name).suffix.lower()
            if suffix in {".bak", ".tmp"}:
                return False
            if normalized_name.lower() == "plot.log":
                return False
            return True

        def _is_source_file_candidate(self, entry: Path) -> bool:
            if not entry.is_file():
                return False
            return self._is_source_file_name_candidate(entry.name)

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

        def _view_selected_source_directory_location(self) -> None:
            item = self.source_roots_list.currentItem()
            if not item:
                self._error("Select a tracked source directory.")
                return
            self._open_paths([Path(str(item.data(Qt.UserRole)))])

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
                    if self._is_source_file_candidate(entry):
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
                    list_item.setData(Qt.UserRole + 2, str(history_row.get("file_id", "")) if history_row else "")
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

        def _path_for_list_item(self, list_widget: QListWidget, item: QListWidgetItem) -> Optional[Path]:
            if list_widget in {
                getattr(self, "project_checked_out_list", None),
                getattr(self, "project_reference_list", None),
            }:
                record = self._record_for_list_item(item)
                if not record:
                    return None
                return Path(record.local_file)
            value = item.data(Qt.UserRole)
            if value in (None, ""):
                return None
            return Path(str(value))

        def _selected_file_paths_from_list_widget(self, list_widget: QListWidget) -> List[Path]:
            paths: List[Path] = []
            for item in list_widget.selectedItems():
                path = self._path_for_list_item(list_widget, item)
                if path is not None:
                    paths.append(path)
            return paths

        def _set_local_reference_read_only(self, path: Path) -> None:
            # Best-effort: mark reference copies read-only on local filesystem.
            try:
                current_mode = path.stat().st_mode
                path.chmod(current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
            except OSError:
                return

        def _copy_selected_as_reference(self) -> None:
            selected_files = self._selected_source_file_paths()
            target = self._choose_project_target(
                title="Copy As Reference",
                message=f"Copy {len(selected_files)} file(s) as reference:",
            ) if selected_files else None
            if not selected_files:
                self._error("Select at least one source file to copy as reference.")
                return
            if not target:
                return
            mode, project_dir = target
            if mode == "current":
                self._copy_selected_as_reference_to_project(None, selected_files)
            elif mode == "other" and project_dir is not None:
                self._copy_selected_as_reference_to_project(project_dir, selected_files)

        def _copy_selected_as_reference_to_project(
            self, target_project_dir: Optional[Path], selected_files: Optional[List[Path]] = None
        ) -> None:
            if not self._validate_identity():
                return

            project_dir = target_project_dir or self._validate_current_project()
            current_directory = self._validate_current_directory()
            source_root = self._current_source_root()
            if not project_dir or not current_directory or not source_root:
                return

            selected_files = selected_files or self._selected_source_file_paths()
            if not selected_files:
                self._error("Select at least one source file to copy as reference.")
                return

            config = self._read_project_config(project_dir)
            project_name = str(config.get("name", project_dir.name))

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
                        file_entry = self._source_index_entry_for_current_name(current_directory, source_file.name)
                        file_id = str(file_entry.get("file_id", "")).strip() if file_entry else ""
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
                                    project_name=project_name,
                                    project_dir=str(project_dir),
                                    source_root=str(source_root),
                                    checked_out_at=copied_at,
                                    record_type="reference_copy",
                                    file_id=file_id,
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
            search = self.project_favorites_search_edit.text().strip().lower()
            for favorite in favorites:
                display_name = self._favorite_display_name(favorite)
                custom_groups = self._item_customization_groups("project_favorites", favorite)
                group_search = " ".join(custom_groups).lower()
                if (
                    search
                    and search not in display_name.lower()
                    and search not in favorite.lower()
                    and search not in group_search
                ):
                    continue
                item = QListWidgetItem(display_name)
                item.setData(Qt.UserRole, favorite)
                self._set_projects_item_base_tooltip(item, favorite)
                self._apply_projects_list_item_style(item, "project_favorites", str(favorite))
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

        def _add_favorite_paths_to_project(self, project_dir: Path, paths: List[Path]) -> None:
            config = self._read_project_config(project_dir)
            favorites = [str(item) for item in config.get("favorites", [])]  # type: ignore[arg-type]
            changed = False
            for path in paths:
                favorite = str(path)
                if favorite not in favorites:
                    favorites.append(favorite)
                    changed = True
            if changed:
                self._save_project_config(project_dir, favorites=favorites)
                if self.current_project_dir == str(project_dir):
                    self._refresh_favorites_list(favorites)

        def _add_favorite_paths_to_global(self, paths: List[Path]) -> None:
            changed = False
            for path in paths:
                favorite = str(path)
                if favorite not in self.global_favorites:
                    self.global_favorites.append(favorite)
                    changed = True
            if changed:
                self._save_global_favorites()
                self._refresh_global_favorites_list()

        def _choose_project_target(
            self,
            *,
            title: str,
            message: str,
            include_global: bool = False,
            global_label: str = "Global Favorites",
        ) -> Optional[Tuple[str, Optional[Path]]]:
            dialog = QDialog(self)
            dialog.setWindowTitle(title)
            dialog.resize(640, 360)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(message))

            current_radio = QRadioButton("Current Project")
            other_radio = QRadioButton("Another Project")
            global_radio = QRadioButton(global_label)
            current_radio.setChecked(True)
            target_layout = QVBoxLayout()
            target_layout.addWidget(current_radio)
            target_layout.addWidget(other_radio)
            if include_global:
                target_layout.addWidget(global_radio)
            layout.addLayout(target_layout)

            project_filter = QLineEdit()
            project_filter.setPlaceholderText("Filter tracked projects by name, client, year, or group")
            project_list = QListWidget()
            project_list.setSelectionMode(QListWidget.SingleSelection)
            project_entries = [
                entry for entry in self.tracked_projects if Path(str(entry.get("project_dir", ""))).is_dir()
            ]

            def refresh_project_list() -> None:
                current_value = ""
                current_item = project_list.currentItem()
                if current_item is not None:
                    current_value = str(current_item.data(Qt.UserRole) or "")
                project_list.clear()
                search = project_filter.text().strip().lower()
                for entry in project_entries:
                    label = str(entry.get("name", "")) or Path(str(entry.get("project_dir", ""))).name
                    if search and not self._tracked_project_matches_search(entry, search):
                        continue
                    details = []
                    if entry.get("client"):
                        details.append(f"Client: {entry['client']}")
                    if entry.get("year_started"):
                        details.append(f"Year: {entry['year_started']}")
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, str(entry.get("project_dir", "")))
                    tooltip_lines = [str(entry.get("project_dir", ""))]
                    tooltip_lines.extend(details)
                    item.setToolTip("\n".join(tooltip_lines))
                    project_list.addItem(item)
                if current_value:
                    for idx in range(project_list.count()):
                        item = project_list.item(idx)
                        if str(item.data(Qt.UserRole) or "") == current_value:
                            project_list.setCurrentItem(item)
                            break
                if project_list.currentItem() is None and project_list.count() > 0:
                    project_list.setCurrentRow(0)

            def update_project_controls() -> None:
                visible = other_radio.isChecked()
                project_filter.setVisible(visible)
                project_list.setVisible(visible)

            layout.addWidget(project_filter)
            layout.addWidget(project_list, stretch=1)
            refresh_project_list()
            update_project_controls()
            current_radio.toggled.connect(lambda _checked: update_project_controls())
            other_radio.toggled.connect(lambda _checked: update_project_controls())
            if include_global:
                global_radio.toggled.connect(lambda _checked: update_project_controls())
            project_filter.textChanged.connect(lambda _text: refresh_project_list())

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None

            mode = "current"
            if other_radio.isChecked():
                mode = "other"
            elif include_global and global_radio.isChecked():
                mode = "global"
            if mode == "other":
                current_item = project_list.currentItem()
                project_dir = str(current_item.data(Qt.UserRole) if current_item is not None else "").strip()
                if not project_dir:
                    self._error("Select a target project.")
                    return None
                return mode, Path(project_dir)
            return mode, None

        def _choose_favorite_target(self, paths: List[Path]) -> Optional[Tuple[str, Optional[Path]]]:
            return self._choose_project_target(
                title="Add To Favorites",
                message=f"Add {len(paths)} file(s) to favorites:",
                include_global=True,
                global_label="Global Favorites",
            )

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
            target = self._choose_favorite_target(selected_files)
            if not target:
                return
            mode, project_dir = target
            if mode == "current":
                self._add_favorite_paths(selected_files)
            elif mode == "other" and project_dir is not None:
                self._add_favorite_paths_to_project(project_dir, selected_files)
            elif mode == "global":
                self._add_favorite_paths_to_global(selected_files)

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

        def _view_selected_file_locations_from_list(self, list_widget: QListWidget) -> None:
            paths = self._selected_file_paths_from_list_widget(list_widget)
            if not paths:
                self._error("Select at least one file.")
                return
            directories: List[Path] = []
            seen: set[str] = set()
            for path in paths:
                directory = path.parent
                key = str(directory)
                if key in seen:
                    continue
                seen.add(key)
                directories.append(directory)
            self._open_paths(directories)

        def _select_source_root_item_by_path(self, root_path: Path) -> bool:
            normalized = str(root_path)
            for row in range(self.source_roots_list.count()):
                item = self.source_roots_list.item(row)
                if str(item.data(Qt.UserRole)) != normalized:
                    continue
                self.source_roots_list.setCurrentItem(item)
                return True
            return False

        def _load_selected_file_location_from_list(self, list_widget: QListWidget) -> None:
            paths = self._selected_file_paths_from_list_widget(list_widget)
            if not paths:
                self._error("Select a file.")
                return
            directory = paths[0].parent
            tracked_roots = [
                Path(str(self.source_roots_list.item(row).data(Qt.UserRole)))
                for row in range(self.source_roots_list.count())
            ]
            matching_roots: List[Path] = []
            for root in tracked_roots:
                try:
                    directory.relative_to(root)
                    matching_roots.append(root)
                except ValueError:
                    continue
            if matching_roots:
                root = max(matching_roots, key=lambda item: len(str(item)))
                if not self._select_source_root_item_by_path(root):
                    self._set_directory_tree_root(root)
            else:
                self._set_directory_tree_root(directory)
            self._set_current_directory_with_feedback(directory, "Loading directory...")

        def _record_for_list_item(self, item: QListWidgetItem) -> Optional[CheckoutRecord]:
            record_idx = item.data(Qt.UserRole)
            if not isinstance(record_idx, int):
                return None
            if not (0 <= record_idx < len(self.records)):
                return None
            return self.records[record_idx]

        def _open_project_local_checked_out_item(self, item: QListWidgetItem) -> None:
            record = self._record_for_list_item(item)
            if record:
                self._open_paths([Path(record.local_file)])

        def _open_project_local_reference_item(self, item: QListWidgetItem) -> None:
            record = self._record_for_list_item(item)
            if record:
                self._open_paths([Path(record.local_file)])

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
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 2:
                indexes = self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                self._open_paths([Path(self.records[idx].local_file) for idx in indexes if 0 <= idx < len(self.records)])
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 3:
                indexes = self._selected_record_indexes_from_list_widget(self.project_reference_list)
                self._open_paths([Path(self.records[idx].local_file) for idx in indexes if 0 <= idx < len(self.records)])
                return
            self._open_selected_favorites()

        def _remove_selected_favorites_from_active_tab(self) -> None:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 1:
                self._remove_selected_global_favorites()
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 2:
                if not self._validate_identity():
                    return
                self._checkin_record_indexes(
                    set(self._selected_record_indexes_from_list_widget(self.project_checked_out_list))
                )
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 3:
                self._remove_record_indexes(self._selected_record_indexes_from_list_widget(self.project_reference_list))
                self._save_records()
                self._render_records_tables()
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
                "app_version": app_module.APP_VERSION,
                "favorites": self.global_favorites,
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        def _refresh_global_favorites_list(self) -> None:
            if not hasattr(self, "global_favorites_list"):
                return
            self.global_favorites_list.clear()
            search = self.global_favorites_search_edit.text().strip().lower()
            for favorite in self.global_favorites:
                custom_groups = self._item_customization_groups("global_favorites", favorite)
                group_search = " ".join(custom_groups).lower()
                if (
                    search
                    and search not in favorite.lower()
                    and search not in Path(favorite).name.lower()
                    and search not in group_search
                ):
                    continue
                item = QListWidgetItem(Path(favorite).name or favorite)
                item.setData(Qt.UserRole, favorite)
                self._set_projects_item_base_tooltip(item, favorite)
                self._apply_projects_list_item_style(item, "global_favorites", str(favorite))
                self.global_favorites_list.addItem(item)

        def _refresh_project_local_files_lists(self) -> None:
            if not hasattr(self, "project_checked_out_list") or not hasattr(self, "project_reference_list"):
                return
            self.project_checked_out_list.clear()
            self.project_reference_list.clear()
            current_project = self.current_project_dir
            checked_search = self.project_checked_out_search_edit.text().strip().lower()
            reference_search = self.project_reference_search_edit.text().strip().lower()
            for idx, record in enumerate(self.records):
                if record.project_dir != current_project:
                    continue
                item_key = self._record_customization_key(record)
                scope = self._record_customization_scope(record)
                search_blob = self._record_search_blob(record)
                if record.record_type == "checked_out":
                    if checked_search and checked_search not in search_blob:
                        continue
                    label = self._local_display_name(record.local_file)
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, idx)
                    self._set_projects_item_base_tooltip(item, record.local_file)
                    self._apply_projects_list_item_style(item, scope, item_key)
                    self.project_checked_out_list.addItem(item)
                elif record.record_type == "reference_copy":
                    if reference_search and reference_search not in search_blob:
                        continue
                    label = self._local_display_name(record.local_file)
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, idx)
                    self._set_projects_item_base_tooltip(item, record.local_file)
                    self._apply_projects_list_item_style(item, scope, item_key)
                    self.project_reference_list.addItem(item)

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

        def _open_global_favorite_item(self, item: QListWidgetItem) -> None:
            self._open_paths([Path(str(item.data(Qt.UserRole)))])

        def _show_global_favorites_context_menu(self, pos: QPoint) -> None:
            item = self.global_favorites_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.global_favorites_list.clearSelection()
                item.setSelected(True)
                self.global_favorites_list.setCurrentItem(item)
            menu = QMenu(self)
            open_action = menu.addAction("Open Selected")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            add_action = menu.addAction("Add Favorite")
            add_project_action = menu.addAction("Add Selected To Project Favorites")
            remove_action = menu.addAction("Remove Selected")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.global_favorites_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_selected_global_favorites()
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.global_favorites_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.global_favorites_list)
            elif chosen == add_action:
                self._browse_and_add_global_favorites()
            elif chosen == add_project_action:
                self._add_selected_global_favorites_to_project()
            elif chosen == remove_action:
                self._remove_selected_global_favorites()
            elif chosen == customize_action:
                self._customize_organize_selected(self.global_favorites_list)

        def _selected_record_indexes_from_list_widget(self, list_widget: QListWidget) -> List[int]:
            indexes: List[int] = []
            for item in list_widget.selectedItems():
                record_idx = item.data(Qt.UserRole)
                if isinstance(record_idx, int):
                    indexes.append(record_idx)
            return indexes

        def _show_project_checked_out_context_menu(self, pos: QPoint) -> None:
            item = self.project_checked_out_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.project_checked_out_list.clearSelection()
                item.setSelected(True)
                self.project_checked_out_list.setCurrentItem(item)
            menu = QMenu(self)
            open_action = menu.addAction("Open Selected")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            checkin_action = menu.addAction("Check In Selected")
            view_revision_action = menu.addAction("View Revision")
            snapshot_action = menu.addAction("Create Revision Snapshot")
            switch_action = menu.addAction("Switch To Revision")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.project_checked_out_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_paths(
                    [
                        Path(self.records[idx].local_file)
                        for idx in self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                        if 0 <= idx < len(self.records)
                    ]
                )
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.project_checked_out_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.project_checked_out_list)
            elif chosen == checkin_action:
                if not self._validate_identity():
                    return
                self._checkin_record_indexes(
                    set(self._selected_record_indexes_from_list_widget(self.project_checked_out_list))
                )
            elif chosen == view_revision_action:
                self._view_record_revision_from_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                )
            elif chosen == snapshot_action:
                self._create_revision_snapshot_for_record_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                )
            elif chosen == switch_action:
                self._switch_record_revision_from_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                )
            elif chosen == customize_action:
                self._customize_records_from_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                )

        def _show_project_reference_context_menu(self, pos: QPoint) -> None:
            item = self.project_reference_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.project_reference_list.clearSelection()
                item.setSelected(True)
                self.project_reference_list.setCurrentItem(item)
            menu = QMenu(self)
            open_action = menu.addAction("Open Selected")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            remove_ref_action = menu.addAction("Remove Selected Ref")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.project_reference_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_paths(
                    [
                        Path(self.records[idx].local_file)
                        for idx in self._selected_record_indexes_from_list_widget(self.project_reference_list)
                        if 0 <= idx < len(self.records)
                    ]
                )
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.project_reference_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.project_reference_list)
            elif chosen == remove_ref_action:
                self._remove_record_indexes(self._selected_record_indexes_from_list_widget(self.project_reference_list))
                self._save_records()
                self._render_records_tables()
            elif chosen == customize_action:
                self._customize_records_from_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_reference_list)
                )

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

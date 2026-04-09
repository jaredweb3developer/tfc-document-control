from __future__ import annotations

import app as app_module
from app import *


class SourcesMixin:
        def _format_source_file_size(self, size_bytes: int) -> str:
            size = float(max(size_bytes, 0))
            units = ["B", "KB", "MB", "GB", "TB"]
            unit_index = 0
            while size >= 1024 and unit_index < len(units) - 1:
                size /= 1024.0
                unit_index += 1
            if unit_index == 0:
                return f"{int(size)} {units[unit_index]}"
            return f"{size:.1f} {units[unit_index]}"

        def _source_file_details_text(self, file_path: Path) -> str:
            try:
                stat = file_path.stat()
            except OSError:
                return ""
            modified_at = datetime.fromtimestamp(stat.st_mtime).astimezone()
            modified_text = modified_at.strftime("%Y-%m-%d %I:%M %p")
            size_text = self._format_source_file_size(int(stat.st_size))
            return f"Modified: {modified_text}   Size: {size_text}"

        def _selected_source_file_items(self) -> List[QTableWidgetItem]:
            if not hasattr(self, "files_list"):
                return []
            selection_model = self.files_list.selectionModel()
            items: List[QTableWidgetItem] = []
            seen_rows: set[int] = set()
            if selection_model is not None:
                for index in selection_model.selectedRows():
                    item = self.files_list.item(index.row(), 0)
                    if item is not None:
                        items.append(item)
                        seen_rows.add(index.row())
            for row in range(self.files_list.rowCount()):
                item = self.files_list.item(row, 0)
                if item is not None and item.isSelected() and row not in seen_rows:
                    items.append(item)
            return items

        def _selected_local_file_items(self) -> List[QTableWidgetItem]:
            selection_model = (
                self.local_files_list.selectionModel() if hasattr(self, "local_files_list") else None
            )
            if selection_model is None:
                return []
            items: List[QTableWidgetItem] = []
            for index in selection_model.selectedRows():
                item = self.local_files_list.item(index.row(), 0)
                if item is not None:
                    items.append(item)
            return items

        def _source_root_item_label(self, source_path: Path) -> str:
            label = source_path.name or str(source_path)
            if not source_path.is_dir():
                return f"{label} [Missing]"
            return label

        def _style_source_root_item(self, item: QListWidgetItem, source_path: Path) -> None:
            if source_path.is_dir():
                item.setForeground(QBrush())
                item.setToolTip(str(source_path))
                return
            item.setForeground(QBrush(QColor("#b91c1c")))
            item.setToolTip(f"{source_path}\nTracked source directory is missing. Use relink to reconnect it.")

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
            selected_item: Optional[QListWidgetItem] = None
            for source in [Path(source) for source in sources if str(source).strip()]:
                item = QListWidgetItem(self._source_root_item_label(source))
                item.setData(Qt.UserRole, str(source))
                self._style_source_root_item(item, source)
                self.source_roots_list.addItem(item)
                if str(source) == selected_source:
                    selected_item = item

            if selected_item:
                self.source_roots_list.setCurrentItem(selected_item)
            elif self.source_roots_list.count() > 0:
                self.source_roots_list.setCurrentRow(0)
            else:
                self.current_directory = None
                self.current_folder_label.setText("Current source folder: -")
                self.files_list.setRowCount(0)
                self._set_directory_tree_root(None)

        def _refresh_local_roots(self, roots: List[str], selected_root: str = "") -> None:
            self.local_roots_list.clear()
            selected_item: Optional[QListWidgetItem] = None
            for root in [Path(root) for root in roots if str(root).strip()]:
                item = QListWidgetItem(self._source_root_item_label(root))
                item.setData(Qt.UserRole, str(root))
                self._style_source_root_item(item, root)
                self.local_roots_list.addItem(item)
                if str(root) == selected_root:
                    selected_item = item

            if selected_item:
                self.local_roots_list.setCurrentItem(selected_item)
            elif self.local_roots_list.count() > 0:
                self.local_roots_list.setCurrentRow(0)
            else:
                self.local_current_directory = None
                self.local_current_folder_label.setText("Current local folder: -")
                self.local_files_list.setRowCount(0)
                self._set_local_directory_tree_root(None)

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

        def _set_local_directory_tree_root(self, root_path: Optional[Path]) -> None:
            self.local_directory_tree.clear()
            self.local_directory_tree_root = root_path

            if root_path is None:
                drives = QDir.drives()
                if drives:
                    for drive in drives:
                        drive_path = Path(drive.absoluteFilePath())
                        self.local_directory_tree.addTopLevelItem(self._create_directory_item(drive_path))
                else:
                    self.local_directory_tree.addTopLevelItem(self._create_directory_item(Path("/")))
                return

            root_item = self._create_directory_item(root_path)
            self.local_directory_tree.addTopLevelItem(root_item)
            self._populate_directory_children(root_item)
            root_item.setExpanded(True)
            self.local_directory_tree.setCurrentItem(root_item)

        def _refresh_directory_browser(self) -> None:
            root_path = self.directory_tree_root
            current_directory = self.current_directory
            self._set_directory_tree_root(root_path)
            if current_directory and current_directory.is_dir():
                self._set_current_directory(current_directory)

        def _refresh_local_directory_browser(self) -> None:
            root_path = self.local_directory_tree_root
            current_directory = self.local_current_directory
            self._set_local_directory_tree_root(root_path)
            if current_directory and current_directory.is_dir():
                self._set_local_current_directory(current_directory)

        def _go_to_parent_source_directory(self) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return
            parent = current_directory.parent
            if parent == current_directory:
                self._info("Already at the top-level directory.")
                return
            if self.directory_tree_root and current_directory == self.directory_tree_root:
                self._set_directory_tree_root(parent)
            self._set_current_directory_with_feedback(parent, "Loading parent directory...")

        def _go_to_parent_local_directory(self) -> None:
            current_directory = self.local_current_directory
            if not current_directory or not current_directory.is_dir():
                self._error("Select a local directory.")
                return
            parent = current_directory.parent
            if parent == current_directory:
                self._info("Already at the top-level directory.")
                return
            if self.local_directory_tree_root and current_directory == self.local_directory_tree_root:
                self._set_local_directory_tree_root(parent)
            self._set_local_current_directory_with_feedback(parent, "Loading parent local directory...")

        def _safe_new_directory_name(self, name: str) -> Optional[str]:
            new_name = name.strip()
            if not new_name:
                self._error("Directory name is required.")
                return None
            if Path(new_name).name != new_name or any(sep in new_name for sep in ("\\", "/")):
                self._error("Enter a directory name only, not a path.")
                return None
            return new_name

        def _create_directory_in(self, parent_directory: Optional[Path], *, label: str) -> Optional[Path]:
            if not parent_directory or not parent_directory.is_dir():
                self._error(f"Select a {label} directory.")
                return None
            name, accepted = QInputDialog.getText(
                self,
                "Create Directory",
                "Directory name:",
            )
            if not accepted:
                return None
            new_name = self._safe_new_directory_name(name)
            if not new_name:
                return None
            target = parent_directory / new_name
            if target.exists():
                self._error(f"A directory or file named '{new_name}' already exists.")
                return None
            try:
                target.mkdir()
            except OSError as exc:
                self._error(f"Could not create directory:\n{exc}")
                return None
            return target

        def _create_directory_in_current_source(self) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return
            target = self._create_directory_in(current_directory, label="source")
            if target is None:
                return
            self._refresh_directory_browser()
            self._info(f"Created directory:\n{target}")

        def _create_directory_in_current_local(self) -> None:
            target = self._create_directory_in(self.local_current_directory, label="local")
            if target is None:
                return
            self._refresh_local_directory_browser()
            self._info(f"Created directory:\n{target}")

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

        def _browse_local_directory_tree_root(self) -> None:
            start_dir = str(
                self.local_current_directory
                or self.local_directory_tree_root
                or self._current_local_root()
                or self._current_project_path()
                or Path.home()
            )
            path = QFileDialog.getExistingDirectory(self, "Browse Local Directory", start_dir)
            if not path:
                return

            selected_path = Path(path)
            self._set_local_directory_tree_root(selected_path)
            self._set_local_current_directory_with_feedback(selected_path, "Loading local directory...")

        def _view_current_directory_location(self) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return
            self._open_paths([current_directory])

        def _view_local_current_directory_location(self) -> None:
            current_directory = self.local_current_directory
            if not current_directory or not current_directory.is_dir():
                self._error("Select a local directory.")
                return
            self._open_paths([current_directory])

        def _view_selected_source_directory_location(self) -> None:
            item = self.source_roots_list.currentItem()
            if not item:
                self._error("Select a tracked source directory.")
                return
            path = Path(str(item.data(Qt.UserRole)))
            if not path.is_dir():
                self._error(f"Tracked source directory is missing:\n{path}")
                return
            self._open_paths([path])

        def _view_selected_local_directory_location(self) -> None:
            item = self.local_roots_list.currentItem()
            if not item:
                self._error("Select a tracked local directory.")
                return
            path = Path(str(item.data(Qt.UserRole)))
            if not path.is_dir():
                self._error(f"Tracked local directory is missing:\n{path}")
                return
            self._open_paths([path])

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

        def _on_local_root_changed(
            self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
        ) -> None:
            if not current:
                return
            project_dir = self._current_project_path()
            if project_dir and project_dir.is_dir():
                self._save_project_config(
                    project_dir,
                    selected_local_directory=str(current.data(Qt.UserRole)),
                )
            root_path = Path(str(current.data(Qt.UserRole)))
            self._set_local_directory_tree_root(root_path)
            self._set_local_current_directory_with_feedback(root_path, "Loading local directory...")

        def _set_current_directory(self, directory: Path) -> None:
            if self.current_directory is None or self.current_directory != directory:
                self._clear_file_search_filter()
            self.current_directory = directory
            self.last_loaded_source_directory = directory
            self.current_folder_label.setText(f"Current source folder: {directory}")
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

        def _set_local_current_directory(self, directory: Path) -> None:
            self.local_current_directory = directory
            self.local_current_folder_label.setText(f"Current local folder: {directory}")
            self._refresh_local_files()

        def _set_local_current_directory_with_feedback(self, directory: Path, message: str) -> None:
            if self._busy_action_depth > 0:
                self._set_local_current_directory(directory)
                return
            if self.local_current_directory is not None and self.local_current_directory == directory:
                self._set_local_current_directory(directory)
                return
            with self._busy_action(message):
                self._set_local_current_directory(directory)

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

        def _on_local_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
            self._populate_directory_children(item)

        def _on_directory_selected(self, item: QTreeWidgetItem, _column: int) -> None:
            path_value = item.data(0, Qt.UserRole)
            if not path_value:
                return
            self._debug_event("directory_selected", directory=str(path_value))
            path = Path(path_value)
            if path.is_dir():
                self._set_current_directory_with_feedback(path, "Loading directory...")

        def _on_local_directory_selected(self, item: QTreeWidgetItem, _column: int) -> None:
            path_value = item.data(0, Qt.UserRole)
            if not path_value:
                return
            path = Path(path_value)
            if path.is_dir():
                self._set_local_current_directory_with_feedback(path, "Loading local directory...")

        def _current_local_root(self) -> Optional[Path]:
            item = self.local_roots_list.currentItem() if hasattr(self, "local_roots_list") else None
            if not item:
                return None
            return Path(str(item.data(Qt.UserRole)))

        def _refresh_source_files(self) -> None:
            current_dir = str(self.current_directory) if self.current_directory else ""
            with self._debug_timed("refresh_source_files", directory=current_dir):
                header = self.files_list.horizontalHeader()
                sort_column = header.sortIndicatorSection()
                sort_order = header.sortIndicatorOrder()
                sorting_enabled = self.files_list.isSortingEnabled()
                self.files_list.setSortingEnabled(False)
                self.files_list.setRowCount(0)
                if not self.current_directory or not self.current_directory.is_dir():
                    self.files_list.setSortingEnabled(sorting_enabled)
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
                    try:
                        stat = item.stat()
                    except OSError:
                        stat = None
                    modified_text = ""
                    size_text = ""
                    modified_sort_value = 0.0
                    size_sort_value = -1
                    if stat is not None:
                        modified_sort_value = float(stat.st_mtime)
                        size_sort_value = int(stat.st_size)
                        modified_text = datetime.fromtimestamp(stat.st_mtime).astimezone().strftime(
                            "%Y-%m-%d %I:%M %p"
                        )
                        size_text = self._format_source_file_size(int(stat.st_size))
                    suffix = item.suffix.lower()
                    file_type = f"{suffix[1:].upper()} File" if suffix else "File"
                    row_idx = self.files_list.rowCount()
                    self.files_list.insertRow(row_idx)
                    name_item = SortableTableWidgetItem(item.name, item.name.lower())
                    name_item.setData(Qt.UserRole, str(item))
                    history_row = history_lookup.get(item.name)
                    original_name = (
                        history_row.get("original_file_name", item.name) if history_row else item.name
                    )
                    name_item.setData(Qt.UserRole + 1, original_name)
                    name_item.setData(Qt.UserRole + 2, str(history_row.get("file_id", "")) if history_row else "")
                    tooltip_lines = [str(item)]
                    if modified_text:
                        tooltip_lines.append(f"Modified: {modified_text}")
                    if size_text:
                        tooltip_lines.append(f"Size: {size_text}")
                    tooltip = "\n".join(tooltip_lines)
                    name_item.setToolTip(tooltip)
                    modified_item = SortableTableWidgetItem(modified_text, modified_sort_value)
                    modified_item.setToolTip(tooltip)
                    type_item = SortableTableWidgetItem(file_type, file_type.lower())
                    type_item.setToolTip(tooltip)
                    size_item = SortableTableWidgetItem(size_text, size_sort_value)
                    size_item.setToolTip(tooltip)
                    size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._apply_file_history_style(name_item, item, history_row)
                    self.files_list.setItem(row_idx, 0, name_item)
                    self.files_list.setItem(row_idx, 1, modified_item)
                    self.files_list.setItem(row_idx, 2, type_item)
                    self.files_list.setItem(row_idx, 3, size_item)
                    shown_count += 1

                self.files_list.setSortingEnabled(sorting_enabled)
                if sorting_enabled:
                    self.files_list.sortItems(sort_column, sort_order)
                self.files_list.resizeColumnsToContents()
                self.files_list.setColumnWidth(0, max(self.files_list.columnWidth(0), 220))
                self._refresh_controlled_files()
                self._debug_event(
                    "source_files_refreshed",
                    directory=current_dir,
                    search=search_term,
                    shown_count=shown_count,
                )

        def _refresh_local_files(self) -> None:
            header = self.local_files_list.horizontalHeader()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            sorting_enabled = self.local_files_list.isSortingEnabled()
            self.local_files_list.setSortingEnabled(False)
            self.local_files_list.setRowCount(0)
            if not self.local_current_directory or not self.local_current_directory.is_dir():
                self.local_files_list.setSortingEnabled(sorting_enabled)
                return

            search_term = self.local_file_search_edit.text().strip().lower()
            shown_count = 0
            entries: List[Path] = []
            try:
                entries = [entry for entry in self.local_current_directory.iterdir()]
            except OSError:
                entries = []
            entries.sort(key=lambda item: item.name.lower())

            for item in entries:
                if search_term and search_term not in item.name.lower():
                    continue
                try:
                    stat = item.stat()
                except OSError:
                    stat = None
                modified_text = ""
                size_text = ""
                modified_sort_value = 0.0
                size_sort_value = -1
                if stat is not None and item.is_file():
                    modified_sort_value = float(stat.st_mtime)
                    size_sort_value = int(stat.st_size)
                    modified_text = datetime.fromtimestamp(stat.st_mtime).astimezone().strftime(
                        "%Y-%m-%d %I:%M %p"
                    )
                    size_text = self._format_source_file_size(int(stat.st_size))
                if item.is_dir():
                    file_type = "Directory"
                else:
                    suffix = item.suffix.lower()
                    file_type = f"{suffix[1:].upper()} File" if suffix else "File"
                row_idx = self.local_files_list.rowCount()
                self.local_files_list.insertRow(row_idx)
                name_item = SortableTableWidgetItem(item.name, item.name.lower())
                name_item.setData(Qt.UserRole, str(item))
                name_item.setData(Qt.UserRole + 1, "directory" if item.is_dir() else "file")
                tooltip_lines = [str(item)]
                if modified_text:
                    tooltip_lines.append(f"Modified: {modified_text}")
                if size_text:
                    tooltip_lines.append(f"Size: {size_text}")
                tooltip = "\n".join(tooltip_lines)
                name_item.setToolTip(tooltip)
                modified_item = SortableTableWidgetItem(modified_text, modified_sort_value)
                modified_item.setToolTip(tooltip)
                type_item = SortableTableWidgetItem(file_type, file_type.lower())
                type_item.setToolTip(tooltip)
                size_item = SortableTableWidgetItem(size_text, size_sort_value)
                size_item.setToolTip(tooltip)
                size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.local_files_list.setItem(row_idx, 0, name_item)
                self.local_files_list.setItem(row_idx, 1, modified_item)
                self.local_files_list.setItem(row_idx, 2, type_item)
                self.local_files_list.setItem(row_idx, 3, size_item)
                shown_count += 1

            self.local_files_list.setSortingEnabled(sorting_enabled)
            if sorting_enabled:
                self.local_files_list.sortItems(sort_column, sort_order)
            self.local_files_list.resizeColumnsToContents()
            self.local_files_list.setColumnWidth(0, max(self.local_files_list.columnWidth(0), 220))
            self._debug_event(
                "local_files_refreshed",
                directory=str(self.local_current_directory),
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

        def _relink_selected_source_directory(self) -> None:
            project_dir = self._validate_current_project()
            item = self.source_roots_list.currentItem()
            if not project_dir or not item:
                self._error("Select a tracked source directory to relink.")
                return

            old_source_path = Path(str(item.data(Qt.UserRole)))
            start_dir = str(old_source_path.parent if str(old_source_path.parent).strip() else Path.home())
            selected = QFileDialog.getExistingDirectory(self, "Relink Source Directory", start_dir)
            if not selected:
                return

            new_source_path = Path(selected)
            if not new_source_path.is_dir():
                self._error("Selected replacement directory does not exist.")
                return

            config = self._read_project_config(project_dir)
            sources = [str(source).strip() for source in config.get("sources", []) if str(source).strip()]
            if str(old_source_path) not in sources:
                self._error("Selected source directory is no longer tracked in this project.")
                return
            if str(new_source_path) in sources and str(new_source_path) != str(old_source_path):
                self._error("That directory is already tracked by this project.")
                return

            replacement_index = new_source_path / app_module.SOURCE_INDEX_FILE
            replacement_history = new_source_path / app_module.HISTORY_FILE_NAME
            replacement_history_csv = new_source_path / app_module.LEGACY_HISTORY_FILE_NAME
            if not (replacement_index.exists() or replacement_history.exists() or replacement_history_csv.exists()):
                answer = QMessageBox.question(
                    self,
                    "Relink Source Directory",
                    (
                        "The selected directory does not contain existing document-control metadata.\n\n"
                        "Relink anyway?"
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return

            updated_sources = [str(new_source_path) if source == str(old_source_path) else source for source in sources]
            raw_source_ids = config.get("source_ids", {})
            existing_source_ids = dict(raw_source_ids) if isinstance(raw_source_ids, dict) else {}
            source_key = existing_source_ids.pop(str(old_source_path), "")
            if source_key:
                existing_source_ids[str(new_source_path)] = source_key
            selected_source = str(config.get("selected_source", "")).strip()
            if selected_source == str(old_source_path):
                selected_source = str(new_source_path)

            with self._busy_action("Relinking source directory..."):
                self._save_project_config(
                    project_dir,
                    name=self._current_project_name(),
                    sources=updated_sources,
                    extension_filters=self._current_extension_filters(),
                    filter_mode=self.file_filter_mode_combo.currentText(),
                    selected_source=selected_source,
                    source_ids=existing_source_ids,
                )
                self._refresh_source_roots(updated_sources, selected_source)
                self._save_settings()
            self._info(f"Relinked source directory to:\n{new_source_path}")

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

        def _local_roots_from_list(self) -> List[str]:
            roots: List[str] = []
            for row in range(self.local_roots_list.count()):
                item = self.local_roots_list.item(row)
                roots.append(str(item.data(Qt.UserRole)))
            return roots

        def _add_local_directory(self) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            start_dir = str(self._current_local_root() or self._current_project_path() or Path.home())
            path = QFileDialog.getExistingDirectory(self, "Track Local Directory", start_dir)
            if not path:
                return
            root_path = Path(path)
            roots = self._local_roots_from_list()
            if str(root_path) in roots:
                self._info("That local directory is already tracked.")
                return
            with self._busy_action("Tracking local directory..."):
                roots.append(str(root_path))
                self._save_project_config(
                    project_dir,
                    local_directories=roots,
                    selected_local_directory=str(root_path),
                )
                self._refresh_local_roots(roots, str(root_path))

        def _track_current_local_directory(self) -> None:
            project_dir = self._validate_current_project()
            current_directory = self.local_current_directory
            if not project_dir or not current_directory or not current_directory.is_dir():
                self._error("Select a local directory to track.")
                return
            roots = self._local_roots_from_list()
            current_dir_str = str(current_directory)
            if current_dir_str in roots:
                self._info("The current local directory is already tracked.")
                return
            with self._busy_action("Tracking local directory..."):
                roots.append(current_dir_str)
                self._save_project_config(
                    project_dir,
                    local_directories=roots,
                    selected_local_directory=current_dir_str,
                )
                self._refresh_local_roots(roots, current_dir_str)

        def _remove_local_directory(self) -> None:
            project_dir = self._validate_current_project()
            item = self.local_roots_list.currentItem()
            if not project_dir or not item:
                self._error("Select a tracked local directory to remove.")
                return
            root_path = str(item.data(Qt.UserRole))
            roots = [root for root in self._local_roots_from_list() if root != root_path]
            selected_root = str(self._current_local_root() or "")
            if selected_root == root_path:
                selected_root = roots[0] if roots else ""
            self._save_project_config(
                project_dir,
                local_directories=roots,
                selected_local_directory=selected_root,
            )
            self._refresh_local_roots(roots, selected_root)

        def _save_local_roots_from_ui_order(self) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            self._save_project_config(
                project_dir,
                local_directories=self._local_roots_from_list(),
                selected_local_directory=str(self._current_local_root() or ""),
            )

        def _move_selected_local_root(self, delta: int) -> None:
            if not self._move_list_widget_item(self.local_roots_list, delta):
                return
            self._save_local_roots_from_ui_order()

        def _move_selected_local_root_to(self, target_index: int) -> None:
            if not self._move_list_widget_item_to(self.local_roots_list, target_index):
                return
            self._save_local_roots_from_ui_order()

        def _move_selected_local_root_up(self) -> None:
            self._move_selected_local_root(-1)

        def _move_selected_local_root_down(self) -> None:
            self._move_selected_local_root(1)

        def _move_selected_local_root_top(self) -> None:
            self._move_selected_local_root_to(0)

        def _move_selected_local_root_bottom(self) -> None:
            self._move_selected_local_root_to(self.local_roots_list.count() - 1)

        def _selected_source_file_paths(self) -> List[Path]:
            return [Path(str(item.data(Qt.UserRole))) for item in self._selected_source_file_items()]

        def _selected_local_file_paths(self) -> List[Path]:
            return [Path(str(item.data(Qt.UserRole))) for item in self._selected_local_file_items()]

        def _on_local_file_search_changed(self, _text: str) -> None:
            self._refresh_local_files()

        def _open_local_item(self, item: QTableWidgetItem) -> None:
            path = Path(str(item.data(Qt.UserRole)))
            if path.is_dir():
                self._set_local_current_directory_with_feedback(path, "Loading local directory...")
                return
            self._open_paths([path])

        def _open_selected_local_files(self) -> None:
            selected_files = self._selected_local_file_paths()
            if not selected_files:
                self._error("Select at least one local item to open.")
                return
            if len(selected_files) == 1 and selected_files[0].is_dir():
                self._set_local_current_directory_with_feedback(selected_files[0], "Loading local directory...")
                return
            self._open_paths(selected_files)

        def _choose_source_destination_directory(self, initial_directory: Optional[Path] = None) -> Optional[Path]:
            tracked_roots = [
                Path(str(self.source_roots_list.item(row).data(Qt.UserRole)))
                for row in range(self.source_roots_list.count())
                if str(self.source_roots_list.item(row).data(Qt.UserRole)).strip()
            ]
            start_dir = initial_directory or self.last_loaded_source_directory or self.current_directory
            if start_dir is None and tracked_roots:
                start_dir = tracked_roots[0]
            if start_dir is None:
                start_dir = self._current_project_path() or Path.home()

            dialog = QDialog(self)
            dialog.setWindowTitle("Select Source Destination")
            dialog.resize(560, 160)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("Choose where to add the selected local file(s):"))

            destination_bar = QHBoxLayout()
            destination_combo = QComboBox()
            destination_combo.setEditable(True)
            for root in tracked_roots:
                destination_combo.addItem(str(root))
            if str(start_dir).strip():
                destination_combo.setCurrentText(str(start_dir))
            browse_btn = QPushButton("Browse")
            destination_bar.addWidget(QLabel("Destination"))
            destination_bar.addWidget(destination_combo, stretch=1)
            destination_bar.addWidget(browse_btn)
            layout.addLayout(destination_bar)

            def _browse_destination() -> None:
                selected = QFileDialog.getExistingDirectory(
                    dialog, "Select Source Destination", destination_combo.currentText().strip() or str(start_dir)
                )
                if selected:
                    destination_combo.setCurrentText(selected)

            browse_btn.clicked.connect(_browse_destination)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None

            destination_text = destination_combo.currentText().strip()
            if not destination_text:
                self._error("Destination folder is required.")
                return None
            destination = Path(destination_text)
            if not destination.is_dir():
                self._error("Selected destination folder does not exist.")
                return None
            return destination

        def _add_selected_local_files_to_source(self) -> None:
            selected_files = [path for path in self._selected_local_file_paths() if path.is_file()]
            if not selected_files:
                self._error("Select at least one local file to add to source.")
                return
            destination = self._choose_source_destination_directory(self.last_loaded_source_directory)
            if not destination:
                return
            self._add_local_files_to_source(selected_files, destination)

        def _rename_selected_local_item(self) -> None:
            selected_items = self._selected_local_file_paths()
            if len(selected_items) != 1:
                self._error("Select exactly one local item to rename.")
                return
            source_path = selected_items[0]
            if not source_path.exists():
                self._error("The selected local item no longer exists.")
                self._refresh_local_directory_browser()
                return

            current_name = source_path.name
            new_name, accepted = QInputDialog.getText(
                self,
                "Rename Local Item",
                "New name:",
                text=current_name,
            )
            if not accepted:
                return
            new_name = new_name.strip()
            if not new_name:
                self._error("Name is required.")
                return
            if new_name == current_name:
                return
            if Path(new_name).name != new_name or any(sep in new_name for sep in ("\\", "/")):
                self._error("Enter a name only, not a path.")
                return

            target_path = source_path.with_name(new_name)
            if target_path.exists():
                self._error(f"An item named '{new_name}' already exists in this folder.")
                return
            try:
                source_path.rename(target_path)
            except OSError as exc:
                self._error(f"Could not rename local item:\n{exc}")
                return
            self._refresh_local_directory_browser()
            self._info(f"Renamed '{current_name}' to '{new_name}'.")

        def _move_selected_local_items(self) -> None:
            selected_items = self._selected_local_file_paths()
            if not selected_items:
                self._error("Select at least one local item to move.")
                return
            start_dir = str(self.local_current_directory or self._current_local_root() or Path.home())
            destination_text = QFileDialog.getExistingDirectory(self, "Move Local Item(s) To", start_dir)
            if not destination_text:
                return
            destination = Path(destination_text)
            if not destination.is_dir():
                self._error("Selected destination folder does not exist.")
                return

            errors: List[str] = []
            moved_count = 0
            with self._busy_action("Moving local item(s)..."):
                for source_path in selected_items:
                    target_path = destination / source_path.name
                    try:
                        if not source_path.exists():
                            errors.append(f"{source_path.name}: missing")
                            continue
                        if target_path.exists():
                            errors.append(f"{source_path.name}: destination already exists")
                            continue
                        if source_path.is_dir():
                            try:
                                destination.relative_to(source_path)
                                errors.append(f"{source_path.name}: cannot move a folder into itself")
                                continue
                            except ValueError:
                                pass
                        shutil.move(str(source_path), str(target_path))
                        moved_count += 1
                    except OSError as exc:
                        errors.append(f"{source_path.name}: {exc}")
                self._refresh_local_directory_browser()

            if errors:
                self._error("Some local items could not be moved:\n" + "\n".join(errors))
            if moved_count:
                self._info(f"Moved {moved_count} local item(s).")

        def _delete_selected_local_items(self) -> None:
            selected_items = self._selected_local_file_paths()
            if not selected_items:
                self._error("Select at least one local item to delete.")
                return
            confirm = QMessageBox.question(
                self,
                "Delete Local Item(s)",
                f"Delete {len(selected_items)} selected local item(s)? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            errors: List[str] = []
            deleted_count = 0
            with self._busy_action("Deleting local item(s)..."):
                for item_path in selected_items:
                    try:
                        if not item_path.exists():
                            errors.append(f"{item_path.name}: missing")
                            continue
                        if item_path.is_dir():
                            shutil.rmtree(item_path)
                        else:
                            item_path.unlink()
                        deleted_count += 1
                    except OSError as exc:
                        errors.append(f"{item_path.name}: {exc}")
                self._refresh_local_directory_browser()

            if errors:
                self._error("Some local items could not be deleted:\n" + "\n".join(errors))
            if deleted_count:
                self._info(f"Deleted {deleted_count} local item(s).")

        def _selected_local_regular_file_paths(self) -> List[Path]:
            return [path for path in self._selected_local_file_paths() if path.is_file()]

        def _add_selected_local_files_to_favorites(self) -> None:
            selected_files = self._selected_local_regular_file_paths()
            if not selected_files:
                self._error("Select at least one local file to favorite.")
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

        def _copy_selected_local_files_as_reference(self) -> None:
            selected_files = self._selected_local_regular_file_paths()
            if not selected_files:
                self._error("Select at least one local file to copy as reference.")
                return
            target = self._choose_project_target(
                title="Copy Local As Reference",
                message=f"Copy {len(selected_files)} local file(s) as reference:",
            )
            if not target:
                return
            mode, project_dir = target
            if mode == "current":
                self._copy_local_files_as_reference_to_project(None, selected_files)
            elif mode == "other" and project_dir is not None:
                self._copy_local_files_as_reference_to_project(project_dir, selected_files)

        def _path_for_list_item(self, list_widget: QListWidget, item: QListWidgetItem) -> Optional[Path]:
            if list_widget in {
                getattr(self, "project_checked_out_list", None),
                getattr(self, "project_reference_list", None),
            }:
                record = self._record_for_list_item(item)
                if not record:
                    return None
                return Path(record.local_file)
            if str(item.data(Qt.UserRole + 1)) == "folder":
                return None
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

            self._copy_reference_files_to_project(
                project_dir=project_dir,
                selected_files=selected_files,
                source_root=source_root,
                reference_group=self._source_key(project_dir, source_root),
                operation_directory=current_directory,
                source_lookup_directory=current_directory,
            )

        def _copy_local_files_as_reference_to_project(
            self, target_project_dir: Optional[Path], selected_files: List[Path]
        ) -> None:
            if not self._validate_identity():
                return

            project_dir = target_project_dir or self._validate_current_project()
            current_directory = self.local_current_directory
            source_root = self._current_local_root() or current_directory
            if not project_dir or not current_directory or not source_root:
                return

            self._copy_reference_files_to_project(
                project_dir=project_dir,
                selected_files=selected_files,
                source_root=source_root,
                reference_group=f"local_files_{hashlib.sha1(str(source_root).encode('utf-8')).hexdigest()[:10]}",
                operation_directory=current_directory,
                source_lookup_directory=None,
            )

        def _copy_reference_files_to_project(
            self,
            *,
            project_dir: Path,
            selected_files: List[Path],
            source_root: Path,
            reference_group: str,
            operation_directory: Path,
            source_lookup_directory: Optional[Path],
        ) -> None:
            config = self._read_project_config(project_dir)
            project_name = str(config.get("name", project_dir.name))

            reference_root = project_dir / "reference_copies" / reference_group
            copied_at = datetime.now().astimezone().isoformat(timespec="seconds")
            errors: List[str] = []
            existing_reference_targets = {
                (str(record.project_dir).strip(), str(Path(record.local_file)).strip().lower())
                for record in self.records
                if record.record_type == "reference_copy"
            }

            with self._debug_timed(
                "copy_reference_selected",
                selected_count=len(selected_files),
                directory=str(operation_directory),
                source_root=str(source_root),
            ):
                with self._busy_action("Copying reference file(s)..."):
                    for source_file in selected_files:
                        if not source_file.exists():
                            errors.append(f"Missing source file: {source_file.name}")
                            continue
                        file_entry = (
                            self._source_index_entry_for_current_name(source_lookup_directory, source_file.name)
                            if source_lookup_directory is not None
                            else None
                        )
                        file_id = str(file_entry.get("file_id", "")).strip() if file_entry else ""
                        try:
                            relative_path = source_file.relative_to(source_root)
                        except ValueError:
                            relative_path = Path(source_file.name)
                        local_file = reference_root / relative_path

                        try:
                            local_file.parent.mkdir(parents=True, exist_ok=True)
                            duplicate_key = (str(project_dir).strip(), str(local_file).strip().lower())
                            if duplicate_key in existing_reference_targets:
                                errors.append(f"{source_file.name}: reference copy already exists in this project")
                                continue
                            shutil.copy2(source_file, local_file)
                            new_record = CheckoutRecord(
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
                            self._ensure_record_has_id(new_record)
                            self._apply_reference_copy_baseline(
                                new_record,
                                source_path=source_file,
                                local_path=local_file,
                                copied_at=copied_at,
                            )
                            self.records.append(new_record)
                            existing_reference_targets.add(duplicate_key)
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

        def _empty_logical_view(self) -> Dict[str, List[Dict[str, object]]]:
            return {"folders": [], "placements": []}

        def _project_logical_views(self) -> Dict[str, Dict[str, List[Dict[str, object]]]]:
            config = self._current_project_config()
            if not config:
                return self._normalize_logical_views({}, app_module.PROJECT_LOGICAL_VIEW_SCOPES)
            return self._normalize_logical_views(
                config.get("logical_views", {}),
                app_module.PROJECT_LOGICAL_VIEW_SCOPES,
            )

        def _project_logical_view(self, scope: str) -> Dict[str, List[Dict[str, object]]]:
            return dict(self._project_logical_views().get(scope, self._empty_logical_view()))

        def _save_project_logical_view(self, scope: str, view: Dict[str, List[Dict[str, object]]]) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            logical_views = self._project_logical_views()
            logical_views[scope] = self._normalize_logical_view_entry(view)
            self._save_project_config(project_dir, logical_views=logical_views)

        def _logical_view_folder_map(self, view: Dict[str, List[Dict[str, object]]]) -> Dict[str, Dict[str, object]]:
            folders = view.get("folders", [])
            if not isinstance(folders, list):
                return {}
            return {
                str(folder.get("id", "")).strip(): dict(folder)
                for folder in folders
                if isinstance(folder, dict) and str(folder.get("id", "")).strip()
            }

        def _logical_view_folder_path(self, view: Dict[str, List[Dict[str, object]]], folder_id: str) -> List[str]:
            path_parts: List[str] = []
            folder_map = self._logical_view_folder_map(view)
            current_id = folder_id.strip()
            seen: set[str] = set()
            while current_id and current_id not in seen:
                seen.add(current_id)
                folder = folder_map.get(current_id)
                if not folder:
                    break
                path_parts.append(str(folder.get("name", "")).strip())
                current_id = str(folder.get("parent_id", "")).strip()
            path_parts.reverse()
            return path_parts

        def _logical_descendant_folder_ids(
            self, view: Dict[str, List[Dict[str, object]]], parent_folder_id: str
        ) -> set[str]:
            folder_map = self._logical_view_folder_map(view)
            if not parent_folder_id.strip():
                return set(folder_map.keys())
            descendants: set[str] = set()
            pending = [parent_folder_id.strip()]
            while pending:
                current_id = pending.pop()
                for folder_id, folder in folder_map.items():
                    if folder_id in descendants:
                        continue
                    if str(folder.get("parent_id", "")).strip() != current_id:
                        continue
                    descendants.add(folder_id)
                    pending.append(folder_id)
            return descendants

        def _current_logical_folder_id(self, scope: str) -> str:
            return str(self.logical_view_current_folder_ids.get(scope, "")).strip()

        def _set_current_logical_folder_id(self, scope: str, folder_id: str) -> None:
            normalized = folder_id.strip()
            if normalized:
                self.logical_view_current_folder_ids[scope] = normalized
            else:
                self.logical_view_current_folder_ids.pop(scope, None)

        def _logical_child_folders(
            self, view: Dict[str, List[Dict[str, object]]], parent_id: str
        ) -> List[Dict[str, object]]:
            folders = view.get("folders", [])
            if not isinstance(folders, list):
                return []
            child_folders = [
                dict(folder)
                for folder in folders
                if isinstance(folder, dict) and str(folder.get("parent_id", "")).strip() == parent_id.strip()
            ]
            child_folders.sort(
                key=lambda folder: (int(folder.get("sort_order", 0)), str(folder.get("name", "")).lower())
            )
            return child_folders

        def _logical_item_parent_folder_id(
            self, view: Dict[str, List[Dict[str, object]]], item_key: str
        ) -> str:
            placements = view.get("placements", [])
            if not isinstance(placements, list):
                return ""
            for placement in placements:
                if not isinstance(placement, dict):
                    continue
                if str(placement.get("item_key", "")).strip() != item_key:
                    continue
                return str(placement.get("parent_folder_id", "")).strip()
            return ""

        def _set_logical_item_parent_folder_id(
            self,
            view: Dict[str, List[Dict[str, object]]],
            item_key: str,
            parent_folder_id: str,
        ) -> Dict[str, List[Dict[str, object]]]:
            normalized = self._normalize_logical_view_entry(view)
            placements = [
                dict(entry)
                for entry in normalized.get("placements", [])
                if str(entry.get("item_key", "")).strip() != item_key
            ]
            if parent_folder_id.strip():
                placements.append(
                    {
                        "item_key": item_key,
                        "parent_folder_id": parent_folder_id.strip(),
                        "sort_order": len(placements),
                    }
                )
            normalized["placements"] = placements
            return self._normalize_logical_view_entry(normalized)

        def _delete_logical_folder_tree(
            self, view: Dict[str, List[Dict[str, object]]], folder_id: str
        ) -> Dict[str, List[Dict[str, object]]]:
            normalized = self._normalize_logical_view_entry(view)
            folders = [dict(folder) for folder in normalized.get("folders", [])]
            placements = [dict(entry) for entry in normalized.get("placements", [])]
            descendants: set[str] = set()
            pending = [folder_id.strip()]
            while pending:
                current = pending.pop()
                if not current or current in descendants:
                    continue
                descendants.add(current)
                for folder in folders:
                    if str(folder.get("parent_id", "")).strip() == current:
                        pending.append(str(folder.get("id", "")).strip())
            normalized["folders"] = [
                folder for folder in folders if str(folder.get("id", "")).strip() not in descendants
            ]
            normalized["placements"] = [
                entry
                for entry in placements
                if str(entry.get("parent_folder_id", "")).strip() not in descendants
            ]
            return self._normalize_logical_view_entry(normalized)

        def _prompt_for_project_favorites_folder_name(
            self, title: str, current_name: str = ""
        ) -> Optional[str]:
            name, accepted = QInputDialog.getText(
                self,
                title,
                "Folder name:",
                text=current_name,
            )
            if not accepted:
                return None
            normalized = " ".join(name.strip().split())
            if not normalized:
                self._error("Folder name is required.")
                return None
            return normalized

        def _refresh_project_favorites_navigation(
            self, view: Optional[Dict[str, List[Dict[str, object]]]] = None
        ) -> None:
            if not hasattr(self, "project_favorites_folder_label"):
                return
            current_view = view or self._project_logical_view("project_favorites")
            current_folder_id = self._current_logical_folder_id("project_favorites")
            folder_map = self._logical_view_folder_map(current_view)
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("project_favorites", "")
            path_parts = self._logical_view_folder_path(current_view, current_folder_id)
            path_text = "Root" if not path_parts else "Root / " + " / ".join(path_parts)
            self.project_favorites_folder_label.setText(f"Favorites Folder: {path_text}")
            self.project_favorites_up_btn.setEnabled(bool(current_folder_id))
            self.project_favorites_root_btn.setEnabled(bool(current_folder_id))

        def _refresh_favorites_list(self, favorites: List[str]) -> None:
            self.favorites_list.clear()
            search = self.project_favorites_search_edit.text().strip().lower()
            search_active = bool(search)
            view = self._project_logical_view("project_favorites")
            folder_map = self._logical_view_folder_map(view)
            current_folder_id = self._current_logical_folder_id("project_favorites")
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("project_favorites", "")
            self._refresh_project_favorites_navigation(view)
            if search_active:
                descendant_ids = self._logical_descendant_folder_ids(view, "")
                candidate_folders = [
                    dict(folder_map[folder_id])
                    for folder_id in descendant_ids
                    if folder_id in folder_map
                ]
                candidate_folders.sort(
                    key=lambda folder: " / ".join(
                        self._logical_view_folder_path(view, str(folder.get("id", "")).strip())
                    ).lower()
                )
            else:
                descendant_ids = self._logical_descendant_folder_ids(view, current_folder_id)
                candidate_folders = self._logical_child_folders(view, current_folder_id)
            for folder in candidate_folders:
                folder_name = str(folder.get("name", "")).strip()
                folder_path = self._logical_view_folder_path(view, str(folder.get("id", "")).strip())
                search_blob = " / ".join(folder_path).lower()
                if search and search not in folder_name.lower() and search not in search_blob:
                    continue
                item = QListWidgetItem(f"[Folder] {folder_name}")
                item.setData(Qt.UserRole, str(folder.get("id", "")).strip())
                item.setData(Qt.UserRole + 1, "folder")
                item.setToolTip("Folder\n" + (" / ".join(["Root", *folder_path]) if folder_path else "Root"))
                self.favorites_list.addItem(item)
            for favorite in favorites:
                parent_folder_id = self._logical_item_parent_folder_id(view, favorite)
                if not search_active and parent_folder_id != current_folder_id:
                    continue
                if search_active:
                    if parent_folder_id and parent_folder_id not in descendant_ids:
                        continue
                display_name = self._favorite_display_name(favorite)
                custom_groups = self._item_customization_groups("project_favorites", favorite)
                group_search = " ".join(custom_groups).lower()
                folder_path = self._logical_view_folder_path(view, parent_folder_id)
                folder_search = " / ".join(folder_path).lower()
                if (
                    search
                    and search not in display_name.lower()
                    and search not in favorite.lower()
                    and search not in group_search
                    and search not in folder_search
                ):
                    continue
                item = QListWidgetItem(display_name)
                item.setData(Qt.UserRole, favorite)
                item.setData(Qt.UserRole + 1, "item")
                tooltip = favorite
                if folder_path:
                    tooltip += "\nFolder: " + " / ".join(["Root", *folder_path])
                self._set_projects_item_base_tooltip(item, tooltip)
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
            current_folder_id = self._current_logical_folder_id("project_favorites")
            logical_view = self._project_logical_view("project_favorites")
            changed = False
            for path in paths:
                favorite = str(path)
                if favorite not in favorites:
                    favorites.append(favorite)
                    logical_view = self._set_logical_item_parent_folder_id(logical_view, favorite, current_folder_id)
                    changed = True
            self._set_project_favorites(favorites)
            if changed:
                self._save_project_logical_view("project_favorites", logical_view)
                self._refresh_favorites_list(favorites)

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
                logical_views = self._normalize_logical_views(
                    config.get("logical_views", {}),
                    app_module.PROJECT_LOGICAL_VIEW_SCOPES,
                )
                logical_view = logical_views.get("project_favorites", self._empty_logical_view())
                for path in paths:
                    logical_view = self._set_logical_item_parent_folder_id(logical_view, str(path), "")
                logical_views["project_favorites"] = logical_view
                self._save_project_config(project_dir, favorites=favorites, logical_views=logical_views)
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
            include_current: bool = True,
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
            if include_current:
                current_radio.setChecked(True)
            else:
                other_radio.setChecked(True)
            target_layout = QVBoxLayout()
            if include_current:
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
            if include_current:
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
            if not include_current or other_radio.isChecked():
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
            selected_paths = {
                str(item.data(Qt.UserRole))
                for item in selected_items
                if str(item.data(Qt.UserRole + 1)) != "folder"
            }
            if not selected_paths:
                self._error("Select at least one favorite file to remove.")
                return
            favorites = [favorite for favorite in self._current_project_favorites() if favorite not in selected_paths]
            logical_view = self._project_logical_view("project_favorites")
            for favorite in selected_paths:
                logical_view = self._set_logical_item_parent_folder_id(logical_view, favorite, "")
            self._save_project_logical_view("project_favorites", logical_view)
            self._set_project_favorites(favorites)

        def _favorites_from_ui_order(self) -> List[str]:
            ordered: List[str] = []
            for row in range(self.favorites_list.count()):
                item = self.favorites_list.item(row)
                if str(item.data(Qt.UserRole + 1)) == "folder":
                    continue
                value = str(item.data(Qt.UserRole))
                if value and value not in ordered:
                    ordered.append(value)
            return ordered

        def _move_selected_favorite(self, delta: int) -> None:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() != 0:
                self._error("Switch to 'Project Favorites' to reorder favorites.")
                return
            logical_view = self._project_logical_view("project_favorites")
            if logical_view.get("folders") or logical_view.get("placements"):
                self._error("Reordering project favorites is not available while logical folders are in use.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in self.favorites_list.selectedItems()):
                self._error("Folder rows cannot be reordered yet.")
                return
            if not self._move_list_widget_item(self.favorites_list, delta):
                return
            self._set_project_favorites(self._favorites_from_ui_order())

        def _move_selected_favorite_to(self, target_index: int) -> None:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() != 0:
                self._error("Switch to 'Project Favorites' to reorder favorites.")
                return
            logical_view = self._project_logical_view("project_favorites")
            if logical_view.get("folders") or logical_view.get("placements"):
                self._error("Reordering project favorites is not available while logical folders are in use.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in self.favorites_list.selectedItems()):
                self._error("Folder rows cannot be reordered yet.")
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

        def _go_up_project_favorites_folder(self) -> None:
            view = self._project_logical_view("project_favorites")
            current_folder_id = self._current_logical_folder_id("project_favorites")
            if not current_folder_id:
                return
            folder = self._logical_view_folder_map(view).get(current_folder_id, {})
            self._set_current_logical_folder_id("project_favorites", str(folder.get("parent_id", "")).strip())
            self._refresh_favorites_list(self._current_project_favorites())

        def _go_root_project_favorites_folder(self) -> None:
            self._set_current_logical_folder_id("project_favorites", "")
            self._refresh_favorites_list(self._current_project_favorites())

        def _create_project_favorites_folder(self) -> None:
            name = self._prompt_for_project_favorites_folder_name("New Favorites Folder")
            if not name:
                return
            view = self._project_logical_view("project_favorites")
            current_folder_id = self._current_logical_folder_id("project_favorites")
            siblings = self._logical_child_folders(view, current_folder_id)
            for sibling in siblings:
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(folder) for folder in view.get("folders", [])]
            folders.append(
                {
                    "id": f"fld_{uuid4().hex[:12]}",
                    "name": name,
                    "parent_id": current_folder_id,
                    "sort_order": len(siblings),
                }
            )
            view["folders"] = folders
            self._save_project_logical_view("project_favorites", view)
            self._refresh_favorites_list(self._current_project_favorites())

        def _rename_project_favorites_folder(self, folder_id: str) -> None:
            view = self._project_logical_view("project_favorites")
            folder_map = self._logical_view_folder_map(view)
            folder = folder_map.get(folder_id.strip())
            if not folder:
                self._error("Selected folder could not be found.")
                return
            name = self._prompt_for_project_favorites_folder_name(
                "Rename Favorites Folder",
                str(folder.get("name", "")),
            )
            if not name:
                return
            siblings = self._logical_child_folders(view, str(folder.get("parent_id", "")).strip())
            for sibling in siblings:
                if str(sibling.get("id", "")).strip() == folder_id.strip():
                    continue
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(entry) for entry in view.get("folders", [])]
            for entry in folders:
                if str(entry.get("id", "")).strip() == folder_id.strip():
                    entry["name"] = name
                    break
            view["folders"] = folders
            self._save_project_logical_view("project_favorites", view)
            self._refresh_favorites_list(self._current_project_favorites())

        def _delete_project_favorites_folder(self, folder_id: str) -> None:
            confirm = QMessageBox.question(
                self,
                "Delete Favorites Folder",
                "Delete this folder and its subfolders? Items inside will return to the root list.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
            view = self._delete_logical_folder_tree(self._project_logical_view("project_favorites"), folder_id)
            if self._current_logical_folder_id("project_favorites") == folder_id.strip():
                self._set_current_logical_folder_id("project_favorites", "")
            self._save_project_logical_view("project_favorites", view)
            self._refresh_favorites_list(self._current_project_favorites())

        def _choose_project_favorites_target_folder(self) -> Optional[str]:
            view = self._project_logical_view("project_favorites")
            folders = [dict(folder) for folder in view.get("folders", [])]
            if not folders:
                self._error("Create a favorites folder first.")
                return None
            dialog = QDialog(self)
            dialog.setWindowTitle("Move Favorites To Folder")
            dialog.resize(420, 360)
            layout = QVBoxLayout(dialog)
            folder_list = QListWidget()
            root_item = QListWidgetItem("Root")
            root_item.setData(Qt.UserRole, "")
            folder_list.addItem(root_item)
            ordered_folders = sorted(
                folders,
                key=lambda entry: " / ".join(
                    self._logical_view_folder_path(view, str(entry.get("id", "")).strip())
                ).lower(),
            )
            for folder in ordered_folders:
                folder_id = str(folder.get("id", "")).strip()
                path_text = " / ".join(self._logical_view_folder_path(view, folder_id))
                item = QListWidgetItem(path_text or str(folder.get("name", "")))
                item.setData(Qt.UserRole, folder_id)
                folder_list.addItem(item)
            folder_list.setCurrentRow(0)
            layout.addWidget(folder_list, stretch=1)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None
            current_item = folder_list.currentItem()
            return str(current_item.data(Qt.UserRole)).strip() if current_item is not None else ""

        def _move_selected_favorites_to_folder(self) -> None:
            selected_items = self.favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one favorite.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select favorite files only.")
                return
            target_folder_id = self._choose_project_favorites_target_folder()
            if target_folder_id is None:
                return
            view = self._project_logical_view("project_favorites")
            for item in selected_items:
                favorite = str(item.data(Qt.UserRole)).strip()
                if favorite:
                    view = self._set_logical_item_parent_folder_id(view, favorite, target_folder_id)
            self._save_project_logical_view("project_favorites", view)
            self._refresh_favorites_list(self._current_project_favorites())

        def _move_selected_favorites_to_root(self) -> None:
            selected_items = self.favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one favorite.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select favorite files only.")
                return
            view = self._project_logical_view("project_favorites")
            for item in selected_items:
                favorite = str(item.data(Qt.UserRole)).strip()
                if favorite:
                    view = self._set_logical_item_parent_folder_id(view, favorite, "")
            self._save_project_logical_view("project_favorites", view)
            self._refresh_favorites_list(self._current_project_favorites())

        def _move_selected_items_to_folder_from_active_tab(self) -> None:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 1:
                self._move_selected_global_favorites_to_folder()
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 2:
                self._move_selected_record_items_to_folder(
                    self.project_checked_out_list,
                    "project_checked_out",
                    "Move Checked Out Items To Folder",
                    "Create a checked-out folder first.",
                )
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 3:
                self._move_selected_record_items_to_folder(
                    self.project_reference_list,
                    "project_reference",
                    "Move Reference Items To Folder",
                    "Create a reference folder first.",
                )
                return
            self._move_selected_favorites_to_folder()

        def _move_selected_items_to_root_from_active_tab(self) -> None:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 1:
                self._move_selected_global_favorites_to_root()
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 2:
                self._move_selected_record_items_to_root(self.project_checked_out_list, "project_checked_out")
                return
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 3:
                self._move_selected_record_items_to_root(self.project_reference_list, "project_reference")
                return
            self._move_selected_favorites_to_root()

        def _open_favorite_item(self, item: QListWidgetItem) -> None:
            if str(item.data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("project_favorites", str(item.data(Qt.UserRole)).strip())
                self._refresh_favorites_list(self._current_project_favorites())
                return
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
            if str(item.data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("project_checked_out", str(item.data(Qt.UserRole)).strip())
                self._refresh_project_local_files_lists()
                return
            record = self._record_for_list_item(item)
            if record:
                self._open_paths([Path(record.local_file)])

        def _open_project_local_reference_item(self, item: QListWidgetItem) -> None:
            if str(item.data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("project_reference", str(item.data(Qt.UserRole)).strip())
                self._refresh_project_local_files_lists()
                return
            record = self._record_for_list_item(item)
            if record:
                self._open_paths([Path(record.local_file)])

        def _open_selected_favorites(self) -> None:
            selected_items = self.favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one favorite to open.")
                return
            if len(selected_items) == 1 and str(selected_items[0].data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("project_favorites", str(selected_items[0].data(Qt.UserRole)).strip())
                self._refresh_favorites_list(self._current_project_favorites())
                return
            selected_paths = [
                Path(str(item.data(Qt.UserRole)))
                for item in selected_items
                if str(item.data(Qt.UserRole + 1)) != "folder"
            ]
            if not selected_paths:
                self._error("Select at least one favorite file to open.")
                return
            self._open_paths(selected_paths)

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
                errors = self._remove_record_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_reference_list)
                )
                self._save_records()
                self._render_records_tables()
                if errors:
                    self._error("Some reference copies could not be removed:\n" + "\n".join(errors))
                return
            self._remove_selected_favorites()

        def _ensure_reference_files_tab_active(self) -> bool:
            if hasattr(self, "favorites_tabs") and self.favorites_tabs.currentIndex() == 3:
                return True
            self._error("Switch to 'Reference Files' to use this action.")
            return False

        def _selected_project_reference_record_indexes(self) -> List[int]:
            return self._selected_record_indexes_from_list_widget(self.project_reference_list)

        def _refresh_selected_project_references(self, *, only_if_unchanged: bool = False) -> None:
            indexes = self._selected_project_reference_record_indexes()
            if not indexes:
                self._error("Select at least one reference file.")
                return

            updated = 0
            skipped: List[str] = []
            failed: List[str] = []
            with self._busy_action("Refreshing reference file(s)..."):
                for idx in indexes:
                    if idx < 0 or idx >= len(self.records):
                        continue
                    record = self.records[idx]
                    success, message = self._refresh_reference_record(
                        record,
                        only_if_unchanged=only_if_unchanged,
                    )
                    if success:
                        updated += 1
                    else:
                        label = Path(record.local_file).name or Path(record.source_file).name or record.id
                        if message.startswith("Skipped") or message == "Already up to date.":
                            skipped.append(f"{label}: {message}")
                        else:
                            failed.append(f"{label}: {message}")

            self._save_records()
            self._render_records_tables()

            summary_lines = [f"Updated {updated} reference file(s)."]
            if skipped:
                summary_lines.append(f"Skipped {len(skipped)} reference file(s).")
                summary_lines.extend(skipped[:10])
            if failed:
                summary_lines.append(f"Failed {len(failed)} reference file(s).")
                summary_lines.extend(failed[:10])

            if failed:
                self._error("\n".join(summary_lines))
            else:
                self._info("\n".join(summary_lines))

        def _refresh_selected_references_from_active_tab(self) -> None:
            if not self._ensure_reference_files_tab_active():
                return
            self._refresh_selected_project_references(only_if_unchanged=False)

        def _refresh_selected_references_if_unchanged_from_active_tab(self) -> None:
            if not self._ensure_reference_files_tab_active():
                return
            self._refresh_selected_project_references(only_if_unchanged=True)

        def _check_selected_references_status_from_active_tab(self) -> None:
            if not self._ensure_reference_files_tab_active():
                return
            indexes = self._selected_project_reference_record_indexes()
            if not indexes:
                self._error("Select at least one reference file.")
                return
            rows = self._reference_status_rows_for_indexes(indexes)
            if not rows:
                self._error("Select at least one reference file.")
                return
            self._show_reference_status_dialog(rows, "Reference Status")

        def _update_all_references_from_active_tab(self) -> None:
            if not self._ensure_reference_files_tab_active():
                return
            self._update_all_references()

        def _add_selected_global_favorites_to_project(self) -> None:
            selected_items = self.global_favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one global favorite.")
                return
            selected_paths = [
                Path(str(item.data(Qt.UserRole)))
                for item in selected_items
                if str(item.data(Qt.UserRole + 1)) != "folder"
            ]
            if not selected_paths:
                self._error("Select at least one global favorite file.")
                return
            self._add_favorite_paths(selected_paths)

        def _add_selected_project_favorites_to_global(self) -> None:
            selected_items = self.favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one project favorite.")
                return
            changed = False
            for item in selected_items:
                if str(item.data(Qt.UserRole + 1)) == "folder":
                    continue
                value = str(item.data(Qt.UserRole)).strip()
                if value and value not in self.global_favorites:
                    self.global_favorites.append(value)
                    changed = True
            if changed:
                self._save_global_favorites()
                self._refresh_global_favorites_list()

        def _global_favorites_logical_view(self) -> Dict[str, List[Dict[str, object]]]:
            return dict(
                self._normalize_logical_views(
                    self.global_favorites_logical_views,
                    app_module.GLOBAL_LOGICAL_VIEW_SCOPES,
                ).get("global_favorites", self._empty_logical_view())
            )

        def _save_global_favorites_logical_view(self, view: Dict[str, List[Dict[str, object]]]) -> None:
            normalized = self._normalize_logical_views(
                self.global_favorites_logical_views,
                app_module.GLOBAL_LOGICAL_VIEW_SCOPES,
            )
            normalized["global_favorites"] = self._normalize_logical_view_entry(view)
            self.global_favorites_logical_views = normalized
            self._save_global_favorites()

        def _prompt_for_global_favorites_folder_name(
            self, title: str, current_name: str = ""
        ) -> Optional[str]:
            name, accepted = QInputDialog.getText(
                self,
                title,
                "Folder name:",
                text=current_name,
            )
            if not accepted:
                return None
            normalized = " ".join(name.strip().split())
            if not normalized:
                self._error("Folder name is required.")
                return None
            return normalized

        def _refresh_global_favorites_navigation(
            self, view: Optional[Dict[str, List[Dict[str, object]]]] = None
        ) -> None:
            if not hasattr(self, "global_favorites_folder_label"):
                return
            current_view = view or self._global_favorites_logical_view()
            current_folder_id = self._current_logical_folder_id("global_favorites")
            folder_map = self._logical_view_folder_map(current_view)
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("global_favorites", "")
            path_parts = self._logical_view_folder_path(current_view, current_folder_id)
            path_text = "Root" if not path_parts else "Root / " + " / ".join(path_parts)
            self.global_favorites_folder_label.setText(f"Global Favorites Folder: {path_text}")
            self.global_favorites_up_btn.setEnabled(bool(current_folder_id))
            self.global_favorites_root_btn.setEnabled(bool(current_folder_id))

        def _load_global_favorites(self) -> None:
            data = self._read_json_candidates([self._default_global_favorites_file()])
            raw = data.get("favorites", []) if isinstance(data, dict) else data
            self.global_favorites_logical_views = self._normalize_logical_views(
                data.get("logical_views", {}) if isinstance(data, dict) else {},
                app_module.GLOBAL_LOGICAL_VIEW_SCOPES,
            )
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
                "logical_views": self._normalize_logical_views(
                    self.global_favorites_logical_views,
                    app_module.GLOBAL_LOGICAL_VIEW_SCOPES,
                ),
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        def _refresh_global_favorites_list(self) -> None:
            if not hasattr(self, "global_favorites_list"):
                return
            self.global_favorites_list.clear()
            search = self.global_favorites_search_edit.text().strip().lower()
            search_active = bool(search)
            view = self._global_favorites_logical_view()
            folder_map = self._logical_view_folder_map(view)
            current_folder_id = self._current_logical_folder_id("global_favorites")
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("global_favorites", "")
            self._refresh_global_favorites_navigation(view)
            if search_active:
                descendant_ids = self._logical_descendant_folder_ids(view, "")
                candidate_folders = [
                    dict(folder_map[folder_id])
                    for folder_id in descendant_ids
                    if folder_id in folder_map
                ]
                candidate_folders.sort(
                    key=lambda folder: " / ".join(
                        self._logical_view_folder_path(view, str(folder.get("id", "")).strip())
                    ).lower()
                )
            else:
                descendant_ids = self._logical_descendant_folder_ids(view, current_folder_id)
                candidate_folders = self._logical_child_folders(view, current_folder_id)
            for folder in candidate_folders:
                folder_name = str(folder.get("name", "")).strip()
                folder_path = self._logical_view_folder_path(view, str(folder.get("id", "")).strip())
                search_blob = " / ".join(folder_path).lower()
                if search and search not in folder_name.lower() and search not in search_blob:
                    continue
                item = QListWidgetItem(f"[Folder] {folder_name}")
                item.setData(Qt.UserRole, str(folder.get("id", "")).strip())
                item.setData(Qt.UserRole + 1, "folder")
                item.setToolTip("Folder\n" + (" / ".join(["Root", *folder_path]) if folder_path else "Root"))
                self.global_favorites_list.addItem(item)
            for favorite in self.global_favorites:
                parent_folder_id = self._logical_item_parent_folder_id(view, favorite)
                if not search_active and parent_folder_id != current_folder_id:
                    continue
                if search_active:
                    if parent_folder_id and parent_folder_id not in descendant_ids:
                        continue
                custom_groups = self._item_customization_groups("global_favorites", favorite)
                group_search = " ".join(custom_groups).lower()
                folder_path = self._logical_view_folder_path(view, parent_folder_id)
                folder_search = " / ".join(folder_path).lower()
                if (
                    search
                    and search not in favorite.lower()
                    and search not in Path(favorite).name.lower()
                    and search not in group_search
                    and search not in folder_search
                ):
                    continue
                item = QListWidgetItem(Path(favorite).name or favorite)
                item.setData(Qt.UserRole, favorite)
                item.setData(Qt.UserRole + 1, "item")
                tooltip = favorite
                if folder_path:
                    tooltip += "\nFolder: " + " / ".join(["Root", *folder_path])
                self._set_projects_item_base_tooltip(item, tooltip)
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
            checked_search_active = bool(checked_search)
            reference_search_active = bool(reference_search)
            logical_views = self._project_logical_views()
            checked_view = self._normalize_logical_view_entry(
                logical_views.get("project_checked_out", self._empty_logical_view())
            )
            reference_view = self._normalize_logical_view_entry(
                logical_views.get("project_reference", self._empty_logical_view())
            )
            valid_checked_ids = {
                record.id
                for record in self.records
                if record.project_dir == current_project and record.record_type == "checked_out" and record.id
            }
            valid_reference_ids = {
                record.id
                for record in self.records
                if record.project_dir == current_project and record.record_type == "reference_copy" and record.id
            }
            checked_view["placements"] = [
                dict(entry)
                for entry in checked_view.get("placements", [])
                if str(entry.get("item_key", "")).strip() in valid_checked_ids
            ]
            reference_view["placements"] = [
                dict(entry)
                for entry in reference_view.get("placements", [])
                if str(entry.get("item_key", "")).strip() in valid_reference_ids
            ]
            logical_views_changed = (
                checked_view != logical_views.get("project_checked_out", self._empty_logical_view())
                or reference_view != logical_views.get("project_reference", self._empty_logical_view())
            )
            if logical_views_changed and self._current_project_path() is not None:
                logical_views["project_checked_out"] = checked_view
                logical_views["project_reference"] = reference_view
                self._save_project_config(self._current_project_path(), logical_views=logical_views)
            checked_folder_map = self._logical_view_folder_map(checked_view)
            reference_folder_map = self._logical_view_folder_map(reference_view)
            current_checked_folder_id = self._current_logical_folder_id("project_checked_out")
            current_reference_folder_id = self._current_logical_folder_id("project_reference")
            if current_checked_folder_id and current_checked_folder_id not in checked_folder_map:
                current_checked_folder_id = ""
                self._set_current_logical_folder_id("project_checked_out", "")
            if current_reference_folder_id and current_reference_folder_id not in reference_folder_map:
                current_reference_folder_id = ""
                self._set_current_logical_folder_id("project_reference", "")
            if hasattr(self, "project_checked_out_folder_label"):
                checked_path = self._logical_view_folder_path(checked_view, current_checked_folder_id)
                checked_text = "Root" if not checked_path else "Root / " + " / ".join(checked_path)
                self.project_checked_out_folder_label.setText(f"Checked Out Folder: {checked_text}")
                self.project_checked_out_up_btn.setEnabled(bool(current_checked_folder_id))
                self.project_checked_out_root_btn.setEnabled(bool(current_checked_folder_id))
            if hasattr(self, "project_reference_folder_label"):
                reference_path = self._logical_view_folder_path(reference_view, current_reference_folder_id)
                reference_text = "Root" if not reference_path else "Root / " + " / ".join(reference_path)
                self.project_reference_folder_label.setText(f"Reference Folder: {reference_text}")
                self.project_reference_up_btn.setEnabled(bool(current_reference_folder_id))
                self.project_reference_root_btn.setEnabled(bool(current_reference_folder_id))
            if checked_search_active:
                checked_descendant_ids = self._logical_descendant_folder_ids(checked_view, "")
                checked_candidate_folders = [
                    dict(checked_folder_map[folder_id])
                    for folder_id in checked_descendant_ids
                    if folder_id in checked_folder_map
                ]
                checked_candidate_folders.sort(
                    key=lambda folder: " / ".join(
                        self._logical_view_folder_path(checked_view, str(folder.get("id", "")).strip())
                    ).lower()
                )
            else:
                checked_descendant_ids = self._logical_descendant_folder_ids(checked_view, current_checked_folder_id)
                checked_candidate_folders = self._logical_child_folders(checked_view, current_checked_folder_id)
            if reference_search_active:
                reference_descendant_ids = self._logical_descendant_folder_ids(reference_view, "")
                reference_candidate_folders = [
                    dict(reference_folder_map[folder_id])
                    for folder_id in reference_descendant_ids
                    if folder_id in reference_folder_map
                ]
                reference_candidate_folders.sort(
                    key=lambda folder: " / ".join(
                        self._logical_view_folder_path(reference_view, str(folder.get("id", "")).strip())
                    ).lower()
                )
            else:
                reference_descendant_ids = self._logical_descendant_folder_ids(reference_view, current_reference_folder_id)
                reference_candidate_folders = self._logical_child_folders(reference_view, current_reference_folder_id)
                reference_candidate_folders.sort(
                    key=lambda folder: str(folder.get("name", "")).strip().lower()
                )
            for folder in checked_candidate_folders:
                folder_name = str(folder.get("name", "")).strip()
                folder_path = self._logical_view_folder_path(checked_view, str(folder.get("id", "")).strip())
                search_blob = " / ".join(folder_path).lower()
                if checked_search and checked_search not in folder_name.lower() and checked_search not in search_blob:
                    continue
                item = QListWidgetItem(f"[Folder] {folder_name}")
                item.setData(Qt.UserRole, str(folder.get("id", "")).strip())
                item.setData(Qt.UserRole + 1, "folder")
                item.setToolTip("Folder\n" + (" / ".join(["Root", *folder_path]) if folder_path else "Root"))
                self.project_checked_out_list.addItem(item)
            for folder in reference_candidate_folders:
                folder_name = str(folder.get("name", "")).strip()
                folder_path = self._logical_view_folder_path(reference_view, str(folder.get("id", "")).strip())
                search_blob = " / ".join(folder_path).lower()
                if reference_search and reference_search not in folder_name.lower() and reference_search not in search_blob:
                    continue
                item = QListWidgetItem(f"[Folder] {folder_name}")
                item.setData(Qt.UserRole, str(folder.get("id", "")).strip())
                item.setData(Qt.UserRole + 1, "folder")
                item.setToolTip("Folder\n" + (" / ".join(["Root", *folder_path]) if folder_path else "Root"))
                self.project_reference_list.addItem(item)
            reference_items: List[tuple[int, CheckoutRecord, str]] = []
            for idx, record in enumerate(self.records):
                if record.project_dir != current_project:
                    continue
                item_key = self._record_customization_key(record)
                scope = self._record_customization_scope(record)
                search_blob = self._record_search_blob(record)
                if record.record_type == "checked_out":
                    parent_folder_id = self._logical_item_parent_folder_id(checked_view, record.id)
                    if not checked_search_active and parent_folder_id != current_checked_folder_id:
                        continue
                    if checked_search_active:
                        if parent_folder_id and parent_folder_id not in checked_descendant_ids:
                            continue
                    folder_search = " / ".join(self._logical_view_folder_path(checked_view, parent_folder_id)).lower()
                    if checked_search and checked_search not in search_blob and checked_search not in folder_search:
                        continue
                    label = self._local_display_name(record.local_file)
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, idx)
                    item.setData(Qt.UserRole + 1, "item")
                    tooltip = record.local_file
                    folder_path = self._logical_view_folder_path(checked_view, parent_folder_id)
                    if folder_path:
                        tooltip += "\nFolder: " + " / ".join(["Root", *folder_path])
                    self._set_projects_item_base_tooltip(item, tooltip)
                    self._apply_projects_list_item_style(item, scope, item_key)
                    self.project_checked_out_list.addItem(item)
                elif record.record_type == "reference_copy":
                    parent_folder_id = self._logical_item_parent_folder_id(reference_view, record.id)
                    if not reference_search_active and parent_folder_id != current_reference_folder_id:
                        continue
                    if reference_search_active:
                        if parent_folder_id and parent_folder_id not in reference_descendant_ids:
                            continue
                    folder_search = " / ".join(self._logical_view_folder_path(reference_view, parent_folder_id)).lower()
                    if reference_search and reference_search not in search_blob and reference_search not in folder_search:
                        continue
                    label = self._local_display_name(record.local_file)
                    reference_items.append((idx, record, label))
            reference_items.sort(key=lambda entry: (entry[2].lower(), str(entry[1].local_file).lower()))
            for idx, record, label in reference_items:
                item_key = self._record_customization_key(record)
                scope = self._record_customization_scope(record)
                parent_folder_id = self._logical_item_parent_folder_id(reference_view, record.id)
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, idx)
                item.setData(Qt.UserRole + 1, "item")
                tooltip = record.local_file
                folder_path = self._logical_view_folder_path(reference_view, parent_folder_id)
                if folder_path:
                    tooltip += "\nFolder: " + " / ".join(["Root", *folder_path])
                self._set_projects_item_base_tooltip(item, tooltip)
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
            current_folder_id = self._current_logical_folder_id("global_favorites")
            logical_view = self._global_favorites_logical_view()
            for file_path in file_paths:
                value = str(Path(file_path))
                if value not in self.global_favorites:
                    self.global_favorites.append(value)
                    changed = True
                    logical_view = self._set_logical_item_parent_folder_id(logical_view, value, current_folder_id)
            if changed:
                self.global_favorites_logical_views["global_favorites"] = logical_view
                self._save_global_favorites()
                self._refresh_global_favorites_list()

        def _open_selected_global_favorites(self) -> None:
            selected_items = self.global_favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one global favorite to open.")
                return
            if len(selected_items) == 1 and str(selected_items[0].data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("global_favorites", str(selected_items[0].data(Qt.UserRole)).strip())
                self._refresh_global_favorites_list()
                return
            selected_paths = [
                Path(str(item.data(Qt.UserRole)))
                for item in selected_items
                if str(item.data(Qt.UserRole + 1)) != "folder"
            ]
            if not selected_paths:
                self._error("Select at least one global favorite file to open.")
                return
            self._open_paths(selected_paths)

        def _remove_selected_global_favorites(self) -> None:
            selected_items = self.global_favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one global favorite to remove.")
                return
            selected_paths = {
                str(item.data(Qt.UserRole))
                for item in selected_items
                if str(item.data(Qt.UserRole + 1)) != "folder"
            }
            if not selected_paths:
                self._error("Select at least one global favorite file to remove.")
                return
            self.global_favorites = [
                favorite for favorite in self.global_favorites if favorite not in selected_paths
            ]
            logical_view = self._global_favorites_logical_view()
            for favorite in selected_paths:
                logical_view = self._set_logical_item_parent_folder_id(logical_view, favorite, "")
            self.global_favorites_logical_views["global_favorites"] = logical_view
            self._save_global_favorites()
            self._refresh_global_favorites_list()

        def _show_global_favorites_context_menu_for_item(self, item: QListWidgetItem) -> None:
            self.global_favorites_list.setCurrentItem(item)
            item.setSelected(True)
            rect = self.global_favorites_list.visualItemRect(item)
            self._show_global_favorites_context_menu(rect.center())

        def _open_global_favorite_item(self, item: QListWidgetItem) -> None:
            if str(item.data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("global_favorites", str(item.data(Qt.UserRole)).strip())
                self._refresh_global_favorites_list()
                return
            self._open_paths([Path(str(item.data(Qt.UserRole)))])

        def _go_up_global_favorites_folder(self) -> None:
            view = self._global_favorites_logical_view()
            current_folder_id = self._current_logical_folder_id("global_favorites")
            if not current_folder_id:
                return
            folder = self._logical_view_folder_map(view).get(current_folder_id, {})
            self._set_current_logical_folder_id("global_favorites", str(folder.get("parent_id", "")).strip())
            self._refresh_global_favorites_list()

        def _go_root_global_favorites_folder(self) -> None:
            self._set_current_logical_folder_id("global_favorites", "")
            self._refresh_global_favorites_list()

        def _create_global_favorites_folder(self) -> None:
            name = self._prompt_for_global_favorites_folder_name("New Global Favorites Folder")
            if not name:
                return
            view = self._global_favorites_logical_view()
            current_folder_id = self._current_logical_folder_id("global_favorites")
            siblings = self._logical_child_folders(view, current_folder_id)
            for sibling in siblings:
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(folder) for folder in view.get("folders", [])]
            folders.append(
                {
                    "id": f"fld_{uuid4().hex[:12]}",
                    "name": name,
                    "parent_id": current_folder_id,
                    "sort_order": len(siblings),
                }
            )
            view["folders"] = folders
            self._save_global_favorites_logical_view(view)
            self._refresh_global_favorites_list()

        def _rename_global_favorites_folder(self, folder_id: str) -> None:
            view = self._global_favorites_logical_view()
            folder_map = self._logical_view_folder_map(view)
            folder = folder_map.get(folder_id.strip())
            if not folder:
                self._error("Selected folder could not be found.")
                return
            name = self._prompt_for_global_favorites_folder_name(
                "Rename Global Favorites Folder",
                str(folder.get("name", "")),
            )
            if not name:
                return
            siblings = self._logical_child_folders(view, str(folder.get("parent_id", "")).strip())
            for sibling in siblings:
                if str(sibling.get("id", "")).strip() == folder_id.strip():
                    continue
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(entry) for entry in view.get("folders", [])]
            for entry in folders:
                if str(entry.get("id", "")).strip() == folder_id.strip():
                    entry["name"] = name
                    break
            view["folders"] = folders
            self._save_global_favorites_logical_view(view)
            self._refresh_global_favorites_list()

        def _delete_global_favorites_folder(self, folder_id: str) -> None:
            confirm = QMessageBox.question(
                self,
                "Delete Global Favorites Folder",
                "Delete this folder and its subfolders? Items inside will return to the root list.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
            view = self._delete_logical_folder_tree(self._global_favorites_logical_view(), folder_id)
            if self._current_logical_folder_id("global_favorites") == folder_id.strip():
                self._set_current_logical_folder_id("global_favorites", "")
            self._save_global_favorites_logical_view(view)
            self._refresh_global_favorites_list()

        def _choose_global_favorites_target_folder(self) -> Optional[str]:
            view = self._global_favorites_logical_view()
            folders = [dict(folder) for folder in view.get("folders", [])]
            if not folders:
                self._error("Create a global favorites folder first.")
                return None
            dialog = QDialog(self)
            dialog.setWindowTitle("Move Global Favorites To Folder")
            dialog.resize(420, 360)
            layout = QVBoxLayout(dialog)
            folder_list = QListWidget()
            root_item = QListWidgetItem("Root")
            root_item.setData(Qt.UserRole, "")
            folder_list.addItem(root_item)
            ordered_folders = sorted(
                folders,
                key=lambda entry: " / ".join(
                    self._logical_view_folder_path(view, str(entry.get("id", "")).strip())
                ).lower(),
            )
            for folder in ordered_folders:
                folder_id = str(folder.get("id", "")).strip()
                path_text = " / ".join(self._logical_view_folder_path(view, folder_id))
                item = QListWidgetItem(path_text or str(folder.get("name", "")))
                item.setData(Qt.UserRole, folder_id)
                folder_list.addItem(item)
            folder_list.setCurrentRow(0)
            layout.addWidget(folder_list, stretch=1)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None
            current_item = folder_list.currentItem()
            return str(current_item.data(Qt.UserRole)).strip() if current_item is not None else ""

        def _move_selected_global_favorites_to_folder(self) -> None:
            selected_items = self.global_favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one global favorite.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select global favorite files only.")
                return
            target_folder_id = self._choose_global_favorites_target_folder()
            if target_folder_id is None:
                return
            view = self._global_favorites_logical_view()
            for item in selected_items:
                favorite = str(item.data(Qt.UserRole)).strip()
                if favorite:
                    view = self._set_logical_item_parent_folder_id(view, favorite, target_folder_id)
            self._save_global_favorites_logical_view(view)
            self._refresh_global_favorites_list()

        def _move_selected_global_favorites_to_root(self) -> None:
            selected_items = self.global_favorites_list.selectedItems()
            if not selected_items:
                self._error("Select at least one global favorite.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select global favorite files only.")
                return
            view = self._global_favorites_logical_view()
            for item in selected_items:
                favorite = str(item.data(Qt.UserRole)).strip()
                if favorite:
                    view = self._set_logical_item_parent_folder_id(view, favorite, "")
            self._save_global_favorites_logical_view(view)
            self._refresh_global_favorites_list()

        def _show_global_favorites_context_menu(self, pos: QPoint) -> None:
            item = self.global_favorites_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.global_favorites_list.clearSelection()
                item.setSelected(True)
                self.global_favorites_list.setCurrentItem(item)
            current_item = self.global_favorites_list.currentItem()
            is_folder = current_item is not None and str(current_item.data(Qt.UserRole + 1)) == "folder"
            menu = QMenu(self)
            open_action = menu.addAction("Open Folder" if is_folder else "Open Selected")
            new_folder_action = menu.addAction("New Folder")
            up_folder_action = menu.addAction("Up Folder")
            root_action = menu.addAction("Go Root")
            rename_folder_action = menu.addAction("Rename Folder")
            delete_folder_action = menu.addAction("Delete Folder")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            add_action = menu.addAction("Add Favorite")
            add_project_action = menu.addAction("Add Selected To Project Favorites")
            move_to_folder_action = menu.addAction("Move Selected To Folder")
            move_to_root_action = menu.addAction("Move Selected To Root")
            remove_action = menu.addAction("Remove Selected")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.global_favorites_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_selected_global_favorites()
            elif chosen == new_folder_action:
                self._create_global_favorites_folder()
            elif chosen == up_folder_action:
                self._go_up_global_favorites_folder()
            elif chosen == root_action:
                self._go_root_global_favorites_folder()
            elif chosen == rename_folder_action and current_item is not None:
                self._rename_global_favorites_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == delete_folder_action and current_item is not None:
                self._delete_global_favorites_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.global_favorites_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.global_favorites_list)
            elif chosen == add_action:
                self._browse_and_add_global_favorites()
            elif chosen == add_project_action:
                self._add_selected_global_favorites_to_project()
            elif chosen == move_to_folder_action:
                self._move_selected_global_favorites_to_folder()
            elif chosen == move_to_root_action:
                self._move_selected_global_favorites_to_root()
            elif chosen == remove_action:
                self._remove_selected_global_favorites()
            elif chosen == customize_action:
                self._customize_organize_selected(self.global_favorites_list)

        def _record_logical_view(self, scope: str) -> Dict[str, List[Dict[str, object]]]:
            return self._project_logical_view(scope)

        def _save_record_logical_view(self, scope: str, view: Dict[str, List[Dict[str, object]]]) -> None:
            self._save_project_logical_view(scope, view)

        def _prompt_for_record_folder_name(self, title: str, current_name: str = "") -> Optional[str]:
            name, accepted = QInputDialog.getText(self, title, "Folder name:", text=current_name)
            if not accepted:
                return None
            normalized = " ".join(name.strip().split())
            if not normalized:
                self._error("Folder name is required.")
                return None
            return normalized

        def _create_record_folder(self, scope: str, title: str) -> None:
            name = self._prompt_for_record_folder_name(title)
            if not name:
                return
            view = self._record_logical_view(scope)
            current_folder_id = self._current_logical_folder_id(scope)
            siblings = self._logical_child_folders(view, current_folder_id)
            for sibling in siblings:
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(folder) for folder in view.get("folders", [])]
            folders.append(
                {
                    "id": f"fld_{uuid4().hex[:12]}",
                    "name": name,
                    "parent_id": current_folder_id,
                    "sort_order": len(siblings),
                }
            )
            view["folders"] = folders
            self._save_record_logical_view(scope, view)
            self._refresh_project_local_files_lists()

        def _rename_record_folder(self, scope: str, folder_id: str, title: str) -> None:
            view = self._record_logical_view(scope)
            folder_map = self._logical_view_folder_map(view)
            folder = folder_map.get(folder_id.strip())
            if not folder:
                self._error("Selected folder could not be found.")
                return
            name = self._prompt_for_record_folder_name(title, str(folder.get("name", "")))
            if not name:
                return
            siblings = self._logical_child_folders(view, str(folder.get("parent_id", "")).strip())
            for sibling in siblings:
                if str(sibling.get("id", "")).strip() == folder_id.strip():
                    continue
                if str(sibling.get("name", "")).strip().lower() == name.lower():
                    self._error("A folder with that name already exists here.")
                    return
            folders = [dict(entry) for entry in view.get("folders", [])]
            for entry in folders:
                if str(entry.get("id", "")).strip() == folder_id.strip():
                    entry["name"] = name
                    break
            view["folders"] = folders
            self._save_record_logical_view(scope, view)
            self._refresh_project_local_files_lists()

        def _delete_record_folder(self, scope: str, folder_id: str, title: str, item_label: str) -> None:
            confirm = QMessageBox.question(
                self,
                title,
                f"Delete this folder and its subfolders? {item_label} inside will return to the root list.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
            view = self._delete_logical_folder_tree(self._record_logical_view(scope), folder_id)
            if self._current_logical_folder_id(scope) == folder_id.strip():
                self._set_current_logical_folder_id(scope, "")
            self._save_record_logical_view(scope, view)
            self._refresh_project_local_files_lists()

        def _choose_record_target_folder(self, scope: str, title: str, missing_message: str) -> Optional[str]:
            view = self._record_logical_view(scope)
            folders = [dict(folder) for folder in view.get("folders", [])]
            if not folders:
                self._error(missing_message)
                return None
            dialog = QDialog(self)
            dialog.setWindowTitle(title)
            dialog.resize(420, 360)
            layout = QVBoxLayout(dialog)
            folder_list = QListWidget()
            root_item = QListWidgetItem("Root")
            root_item.setData(Qt.UserRole, "")
            folder_list.addItem(root_item)
            ordered_folders = sorted(
                folders,
                key=lambda entry: " / ".join(
                    self._logical_view_folder_path(view, str(entry.get("id", "")).strip())
                ).lower(),
            )
            for folder in ordered_folders:
                folder_id = str(folder.get("id", "")).strip()
                path_text = " / ".join(self._logical_view_folder_path(view, folder_id))
                item = QListWidgetItem(path_text or str(folder.get("name", "")))
                item.setData(Qt.UserRole, folder_id)
                folder_list.addItem(item)
            folder_list.setCurrentRow(0)
            layout.addWidget(folder_list, stretch=1)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None
            current_item = folder_list.currentItem()
            return str(current_item.data(Qt.UserRole)).strip() if current_item is not None else ""

        def _move_selected_record_items_to_folder(
            self, list_widget: QListWidget, scope: str, title: str, missing_message: str
        ) -> None:
            selected_items = list_widget.selectedItems()
            self._debug_event(
                "record_items_move_to_folder_requested",
                scope=scope,
                selected_count=len(selected_items),
                selected_labels=[item.text() for item in selected_items],
            )
            if not selected_items:
                self._error("Select at least one item.")
                self._debug_event("record_items_move_to_folder_aborted", scope=scope, reason="no_selection")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select file rows only.")
                self._debug_event("record_items_move_to_folder_aborted", scope=scope, reason="folder_selected")
                return
            target_folder_id = self._choose_record_target_folder(scope, title, missing_message)
            if target_folder_id is None:
                self._debug_event("record_items_move_to_folder_aborted", scope=scope, reason="no_target_folder")
                return
            view = self._record_logical_view(scope)
            moved_record_ids: List[str] = []
            for item in selected_items:
                record = self._record_for_list_item(item)
                if record and record.id:
                    view = self._set_logical_item_parent_folder_id(view, record.id, target_folder_id)
                    moved_record_ids.append(record.id)
                else:
                    self._debug_event(
                        "record_items_move_to_folder_skipped_item",
                        scope=scope,
                        item_label=item.text(),
                        record_index=item.data(Qt.UserRole),
                        record_id=str(record.id).strip() if record else "",
                        reason="missing_record_id" if record else "missing_record",
                    )
            self._save_record_logical_view(scope, view)
            self._debug_event(
                "record_items_move_to_folder_saved",
                scope=scope,
                target_folder_id=target_folder_id,
                moved_record_ids=moved_record_ids,
                placement_count=len(view.get("placements", [])),
                placements=[
                    {
                        "item_key": str(entry.get("item_key", "")).strip(),
                        "parent_folder_id": str(entry.get("parent_folder_id", "")).strip(),
                    }
                    for entry in view.get("placements", [])
                    if isinstance(entry, dict)
                ],
            )
            self._refresh_project_local_files_lists()

        def _move_selected_record_items_to_root(self, list_widget: QListWidget, scope: str) -> None:
            selected_items = list_widget.selectedItems()
            self._debug_event(
                "record_items_move_to_root_requested",
                scope=scope,
                selected_count=len(selected_items),
                selected_labels=[item.text() for item in selected_items],
            )
            if not selected_items:
                self._error("Select at least one item.")
                self._debug_event("record_items_move_to_root_aborted", scope=scope, reason="no_selection")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select file rows only.")
                self._debug_event("record_items_move_to_root_aborted", scope=scope, reason="folder_selected")
                return
            view = self._record_logical_view(scope)
            moved_record_ids: List[str] = []
            for item in selected_items:
                record = self._record_for_list_item(item)
                if record and record.id:
                    view = self._set_logical_item_parent_folder_id(view, record.id, "")
                    moved_record_ids.append(record.id)
                else:
                    self._debug_event(
                        "record_items_move_to_root_skipped_item",
                        scope=scope,
                        item_label=item.text(),
                        record_index=item.data(Qt.UserRole),
                        record_id=str(record.id).strip() if record else "",
                        reason="missing_record_id" if record else "missing_record",
                    )
            self._save_record_logical_view(scope, view)
            self._debug_event(
                "record_items_move_to_root_saved",
                scope=scope,
                moved_record_ids=moved_record_ids,
                placement_count=len(view.get("placements", [])),
                placements=[
                    {
                        "item_key": str(entry.get("item_key", "")).strip(),
                        "parent_folder_id": str(entry.get("parent_folder_id", "")).strip(),
                    }
                    for entry in view.get("placements", [])
                    if isinstance(entry, dict)
                ],
            )
            self._refresh_project_local_files_lists()

        def _go_up_project_checked_out_folder(self) -> None:
            view = self._record_logical_view("project_checked_out")
            current_folder_id = self._current_logical_folder_id("project_checked_out")
            if not current_folder_id:
                return
            folder = self._logical_view_folder_map(view).get(current_folder_id, {})
            self._set_current_logical_folder_id("project_checked_out", str(folder.get("parent_id", "")).strip())
            self._refresh_project_local_files_lists()

        def _go_root_project_checked_out_folder(self) -> None:
            self._set_current_logical_folder_id("project_checked_out", "")
            self._refresh_project_local_files_lists()

        def _create_project_checked_out_folder(self) -> None:
            self._create_record_folder("project_checked_out", "New Checked Out Folder")

        def _go_up_project_reference_folder(self) -> None:
            view = self._record_logical_view("project_reference")
            current_folder_id = self._current_logical_folder_id("project_reference")
            if not current_folder_id:
                return
            folder = self._logical_view_folder_map(view).get(current_folder_id, {})
            self._set_current_logical_folder_id("project_reference", str(folder.get("parent_id", "")).strip())
            self._refresh_project_local_files_lists()

        def _go_root_project_reference_folder(self) -> None:
            self._set_current_logical_folder_id("project_reference", "")
            self._refresh_project_local_files_lists()

        def _create_project_reference_folder(self) -> None:
            self._create_record_folder("project_reference", "New Reference Folder")

        def _selected_record_indexes_from_list_widget(self, list_widget: QListWidget) -> List[int]:
            indexes: List[int] = []
            for item in list_widget.selectedItems():
                if str(item.data(Qt.UserRole + 1)) == "folder":
                    continue
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
            current_item = self.project_checked_out_list.currentItem()
            is_folder = current_item is not None and str(current_item.data(Qt.UserRole + 1)) == "folder"
            menu = QMenu(self)
            open_action = menu.addAction("Open Folder" if is_folder else "Open Selected")
            new_folder_action = menu.addAction("New Folder")
            up_folder_action = menu.addAction("Up Folder")
            root_action = menu.addAction("Go Root")
            rename_folder_action = menu.addAction("Rename Folder")
            delete_folder_action = menu.addAction("Delete Folder")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            move_to_folder_action = menu.addAction("Move Selected To Folder")
            move_to_root_action = menu.addAction("Move Selected To Root")
            checkin_action = menu.addAction("Check In Selected")
            view_revision_action = menu.addAction("View Revision")
            snapshot_action = menu.addAction("Create Revision Snapshot")
            switch_action = menu.addAction("Switch To Revision")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.project_checked_out_list.mapToGlobal(pos))
            if chosen == open_action:
                if is_folder and current_item is not None:
                    self._open_project_local_checked_out_item(current_item)
                else:
                    self._open_paths(
                        [
                            Path(self.records[idx].local_file)
                            for idx in self._selected_record_indexes_from_list_widget(self.project_checked_out_list)
                            if 0 <= idx < len(self.records)
                        ]
                    )
            elif chosen == new_folder_action:
                self._create_project_checked_out_folder()
            elif chosen == up_folder_action:
                self._go_up_project_checked_out_folder()
            elif chosen == root_action:
                self._go_root_project_checked_out_folder()
            elif chosen == rename_folder_action and current_item is not None:
                self._rename_record_folder("project_checked_out", str(current_item.data(Qt.UserRole)).strip(), "Rename Checked Out Folder")
            elif chosen == delete_folder_action and current_item is not None:
                self._delete_record_folder("project_checked_out", str(current_item.data(Qt.UserRole)).strip(), "Delete Checked Out Folder", "Checked-out files")
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.project_checked_out_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.project_checked_out_list)
            elif chosen == move_to_folder_action:
                self._move_selected_record_items_to_folder(
                    self.project_checked_out_list,
                    "project_checked_out",
                    "Move Checked Out Items To Folder",
                    "Create a checked-out folder first.",
                )
            elif chosen == move_to_root_action:
                self._move_selected_record_items_to_root(self.project_checked_out_list, "project_checked_out")
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
            current_item = self.project_reference_list.currentItem()
            is_folder = current_item is not None and str(current_item.data(Qt.UserRole + 1)) == "folder"
            menu = QMenu(self)
            open_action = menu.addAction("Open Folder" if is_folder else "Open Selected")
            new_folder_action = menu.addAction("New Folder")
            up_folder_action = menu.addAction("Up Folder")
            root_action = menu.addAction("Go Root")
            rename_folder_action = menu.addAction("Rename Folder")
            delete_folder_action = menu.addAction("Delete Folder")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            move_to_folder_action = menu.addAction("Move Selected To Folder")
            move_to_root_action = menu.addAction("Move Selected To Root")
            refresh_action = menu.addAction("Refresh Selected Ref")
            refresh_safe_action = menu.addAction("Refresh Selected Ref (If Unchanged)")
            status_action = menu.addAction("Check Reference Status")
            update_all_action = menu.addAction("Update All References")
            remove_ref_action = menu.addAction("Remove Selected Ref")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.project_reference_list.mapToGlobal(pos))
            if chosen == open_action:
                if is_folder and current_item is not None:
                    self._open_project_local_reference_item(current_item)
                else:
                    self._open_paths(
                        [
                            Path(self.records[idx].local_file)
                            for idx in self._selected_record_indexes_from_list_widget(self.project_reference_list)
                            if 0 <= idx < len(self.records)
                        ]
                    )
            elif chosen == new_folder_action:
                self._create_project_reference_folder()
            elif chosen == up_folder_action:
                self._go_up_project_reference_folder()
            elif chosen == root_action:
                self._go_root_project_reference_folder()
            elif chosen == rename_folder_action and current_item is not None:
                self._rename_record_folder("project_reference", str(current_item.data(Qt.UserRole)).strip(), "Rename Reference Folder")
            elif chosen == delete_folder_action and current_item is not None:
                self._delete_record_folder("project_reference", str(current_item.data(Qt.UserRole)).strip(), "Delete Reference Folder", "Reference files")
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.project_reference_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.project_reference_list)
            elif chosen == move_to_folder_action:
                self._move_selected_record_items_to_folder(
                    self.project_reference_list,
                    "project_reference",
                    "Move Reference Items To Folder",
                    "Create a reference folder first.",
                )
            elif chosen == move_to_root_action:
                self._move_selected_record_items_to_root(self.project_reference_list, "project_reference")
            elif chosen == refresh_action:
                self._refresh_selected_project_references(only_if_unchanged=False)
            elif chosen == refresh_safe_action:
                self._refresh_selected_project_references(only_if_unchanged=True)
            elif chosen == status_action:
                rows = self._reference_status_rows_for_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_reference_list)
                )
                if not rows:
                    self._error("Select at least one reference file.")
                    return
                self._show_reference_status_dialog(rows, "Reference Status")
            elif chosen == update_all_action:
                self._update_all_references()
            elif chosen == remove_ref_action:
                errors = self._remove_record_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_reference_list)
                )
                self._save_records()
                self._render_records_tables()
                if errors:
                    self._error("Some reference copies could not be removed:\n" + "\n".join(errors))
            elif chosen == customize_action:
                self._customize_records_from_indexes(
                    self._selected_record_indexes_from_list_widget(self.project_reference_list)
                )


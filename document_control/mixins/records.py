from __future__ import annotations

import app as app_module
from app import *


class RecordsMixin:
        def _new_compact_id(self, existing_ids: set[str], size: int = 10) -> str:
            while True:
                candidate = uuid4().hex[:size]
                if candidate not in existing_ids:
                    return candidate

        def _source_key(self, project_dir: Path, source_root: Path) -> str:
            config = self._read_project_config(project_dir)
            sources = [str(item) for item in config.get("sources", [])]  # type: ignore[arg-type]
            raw_source_ids = config.get("source_ids", {})
            source_ids = dict(raw_source_ids) if isinstance(raw_source_ids, dict) else {}
            normalized_source_ids = self._normalize_source_ids(sources, source_ids)
            source_key = normalized_source_ids.get(str(source_root))
            if not source_key:
                source_key = self._new_compact_id(set(normalized_source_ids.values()))
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
            return source_dir / app_module.HISTORY_FILE_NAME

        def _history_legacy_csv_file(self, source_dir: Path) -> Path:
            return source_dir / app_module.LEGACY_HISTORY_FILE_NAME

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
                "schema_version": app_module.HISTORY_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
            return source_dir / app_module.DIRECTORY_NOTES_FILE

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
                "schema_version": app_module.DIRECTORY_NOTES_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
            return project_dir / app_module.FILE_VERSIONS_FILE

        def _file_versions_root(self, project_dir: Path) -> Path:
            return project_dir / app_module.FILE_VERSIONS_DIR

        def _record_version_key(self, record: CheckoutRecord) -> str:
            key_source = "|".join([record.project_dir, record.source_file, record.locked_source_file])
            return hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]

        def _load_file_versions_registry(self, project_dir: Path) -> Dict[str, object]:
            registry_path = self._file_versions_registry_path(project_dir)
            if not registry_path.exists():
                return {
                    "schema_version": app_module.FILE_VERSIONS_SCHEMA_VERSION,
                    "app_version": app_module.APP_VERSION,
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
                "schema_version": app_module.FILE_VERSIONS_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
            return self._choose_revision_for_record_action(record, "Switch To Selected")

        def _choose_revision_for_record_action(
            self, record: CheckoutRecord, accept_label: str
        ) -> Optional[Dict[str, object]]:
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
            switch_btn = buttons.addButton(accept_label, QDialogButtonBox.AcceptRole)
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
            self._create_revision_snapshot_for_record_indexes(self._selected_checked_out_record_indexes())

        def _switch_selected_record_to_revision(self) -> None:
            indexes = self._selected_checked_out_record_indexes()
            self._switch_record_revision_from_indexes(indexes)

        def _view_record_revision_from_indexes(self, indexes: List[int]) -> None:
            if len(indexes) != 1:
                self._error("Select exactly one checked-out file to view a revision.")
                return
            record = self.records[indexes[0]]
            revision = self._choose_revision_for_record_action(record, "View Selected")
            if not revision:
                return
            relative_snapshot = str(revision.get("snapshot_file", "")).strip()
            if not relative_snapshot:
                self._error("Selected revision is missing snapshot data.")
                return
            snapshot_path = Path(record.project_dir) / relative_snapshot
            if not snapshot_path.exists():
                self._error(f"Revision snapshot file is missing:\n{snapshot_path}")
                return
            self._open_paths([snapshot_path])

        def _view_selected_record_revision(self) -> None:
            self._view_record_revision_from_indexes(self._selected_checked_out_record_indexes())

        def _create_revision_snapshot_for_record_indexes(self, indexes: List[int]) -> None:
            valid_indexes = [
                idx
                for idx in indexes
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
            ]
            if not valid_indexes:
                self._error("Select at least one checked-out file to snapshot.")
                return
            accepted, note = self._prompt_revision_note("Create Revision Snapshot")
            if not accepted:
                return
            created_count = 0
            with self._busy_action("Creating revision snapshot(s)..."):
                for idx in valid_indexes:
                    created = self._create_revision_snapshot_for_record(self.records[idx], note=note)
                    if created:
                        created_count += 1
            if created_count == 0:
                self._info("No new snapshots were created (current states already tracked).")
            else:
                self._info(f"Created {created_count} revision snapshot(s).")

        def _switch_record_revision_from_indexes(self, indexes: List[int]) -> None:
            valid_indexes = [
                idx
                for idx in indexes
                if 0 <= idx < len(self.records) and self.records[idx].record_type == "checked_out"
            ]
            if len(valid_indexes) != 1:
                self._error("Select exactly one checked-out file to switch revisions.")
                return
            record = self.records[valid_indexes[0]]
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
                customize_action = menu.addAction("Customize/Organize")
                action_map[customize_action] = "customize"
            else:
                checkin_action = menu.addAction("Check In Selected")
                action_map[checkin_action] = "checkin"
                snapshot_action = menu.addAction("Create Revision Snapshot")
                action_map[snapshot_action] = "snapshot"
                view_revision_action = menu.addAction("View Revision")
                action_map[view_revision_action] = "view_revision"
                switch_action = menu.addAction("Switch To Revision")
                action_map[switch_action] = "switch_revision"
                customize_action = menu.addAction("Customize/Organize")
                action_map[customize_action] = "customize"
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
            if action_id == "view_revision":
                self._view_selected_record_revision()
                return
            if action_id == "switch_revision":
                self._switch_selected_record_to_revision()
                return
            if action_id == "remove_ref":
                self._remove_selected_reference_records()
                return
            if action_id == "customize":
                self._customize_selected_active_records()
                return

        def _customize_records_from_indexes(self, indexes: List[int]) -> None:
            targets: List[Tuple[str, str]] = []
            scope = ""
            for idx in indexes:
                if not (0 <= idx < len(self.records)):
                    continue
                record = self.records[idx]
                current_scope = self._record_customization_scope(record)
                if not scope:
                    scope = current_scope
                if current_scope != scope:
                    self._error("Select only checked-out files or only reference files to customize.")
                    return
                targets.append((self._record_customization_key(record), self._local_display_name(record.local_file)))
            if not targets or not scope:
                self._error("Select at least one file to customize.")
                return
            self._show_customize_organize_dialog(scope, targets)

        def _customize_selected_active_records(self) -> None:
            self._customize_records_from_indexes(self._selected_record_indexes())

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
            new_project_action = menu.addAction("New Project")
            load_action = menu.addAction("Load Selected")
            files_action = menu.addAction("Project Files Manager")
            edit_action = menu.addAction("Edit Selected")
            open_loc_action = menu.addAction("Open Location")
            untrack_action = menu.addAction("Untrack Selected")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.tracked_projects_list.mapToGlobal(pos))
            if chosen == new_project_action:
                self._show_new_project_dialog()
            elif chosen == load_action:
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
            elif chosen == customize_action:
                self._customize_organize_selected(self.tracked_projects_list)

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
            open_action = menu.addAction("Open Selected")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            add_action = menu.addAction("Add Favorite")
            add_global_action = menu.addAction("Add Selected To Global Favorites")
            remove_action = menu.addAction("Remove Favorite")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.favorites_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_selected_favorites()
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.favorites_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.favorites_list)
            elif chosen == add_action:
                self._browse_and_add_favorites()
            elif chosen == add_global_action:
                self._add_selected_project_favorites_to_global()
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
            elif chosen == customize_action:
                self._customize_organize_selected(self.favorites_list)

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
            edit_action = menu.addAction("Edit Selected")
            new_action = menu.addAction("New Note")
            presets_action = menu.addAction("Presets")
            remove_action = menu.addAction("Remove Selected")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.notes_list.mapToGlobal(pos))
            if chosen == new_action:
                self._create_note()
            elif chosen == presets_action:
                self._show_note_presets_dialog()
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
            elif chosen == customize_action:
                self._customize_organize_selected(self.notes_list)

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
            view_location_action = menu.addAction("View Location")
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
            elif chosen == view_location_action:
                self._view_selected_source_directory_location()
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
                self._populate_records_table(
                    self.all_records_table,
                    checked_out_items,
                    self.all_records_search_edit.text().strip().lower(),
                )
                current_project = self.current_project_dir
                filtered = [
                    (idx, record)
                    for idx, record in checked_out_items
                    if record.project_dir == current_project
                ]
                self._populate_records_table(
                    self.project_records_table,
                    filtered,
                    self.project_records_search_edit.text().strip().lower(),
                )
                reference_items = [
                    (idx, record)
                    for idx, record in enumerate(self.records)
                    if record.record_type == "reference_copy"
                ]
                self._populate_reference_records_table(
                    self.reference_records_table,
                    reference_items,
                    self.reference_records_search_edit.text().strip().lower(),
                )
                self._refresh_project_local_files_lists()

        def _populate_records_table(
            self, table: QTableWidget, items: List[tuple[int, CheckoutRecord]], search: str = ""
        ) -> None:
            filtered_items = [
                (record_idx, record)
                for record_idx, record in items
                if not search or search in self._record_search_blob(record)
            ]
            table.setRowCount(len(filtered_items))
            for row_idx, (record_idx, record) in enumerate(filtered_items):
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
                self._apply_record_table_row_style(table, row_idx, record)

            table.resizeColumnsToContents()
            table.setColumnWidth(0, max(table.columnWidth(0), 260))
            table.setColumnWidth(1, max(table.columnWidth(1), 260))
            table.setColumnWidth(2, max(table.columnWidth(2), 180))
            table.setColumnWidth(3, max(table.columnWidth(3), 72))
            table.setColumnWidth(4, max(table.columnWidth(4), 170))
            table.setColumnWidth(5, max(table.columnWidth(5), 150))

        def _populate_reference_records_table(
            self, table: QTableWidget, items: List[tuple[int, CheckoutRecord]], search: str = ""
        ) -> None:
            filtered_items = [
                (record_idx, record)
                for record_idx, record in items
                if not search or search in self._record_search_blob(record)
            ]
            table.setRowCount(len(filtered_items))
            for row_idx, (record_idx, record) in enumerate(filtered_items):
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
                self._apply_record_table_row_style(table, row_idx, record)

            table.resizeColumnsToContents()
            table.setColumnWidth(0, max(table.columnWidth(0), 280))
            table.setColumnWidth(1, max(table.columnWidth(1), 200))
            table.setColumnWidth(2, max(table.columnWidth(2), 180))
            table.setColumnWidth(3, max(table.columnWidth(3), 150))

        def _load_records(self) -> None:
            with self._debug_timed("load_records"):
                data = self._read_json_candidates(
                    [self._records_file_path(), app_module.LEGACY_RECORDS_FILE]
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
                        "schema_version": app_module.RECORDS_SCHEMA_VERSION,
                        "app_version": app_module.APP_VERSION,
                        "records": [asdict(record) for record in self.records],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

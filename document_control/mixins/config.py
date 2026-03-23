from __future__ import annotations

import app as app_module
from app import *


class ConfigMixin:
        def _default_projects_dir(self) -> Path:
            return Path.home() / "Documents" / app_module.APP_NAME / "Projects"

        def _default_projects_registry_file(self) -> Path:
            return app_module.USER_DATA_ROOT / "projects.json"

        def _default_filter_presets_file(self) -> Path:
            return app_module.USER_DATA_ROOT / "filter_presets.json"

        def _default_records_file(self) -> Path:
            return app_module.USER_DATA_ROOT / "checkout_records.json"

        def _default_debug_events_file(self) -> Path:
            return app_module.DEBUG_EVENTS_FILE

        def _default_global_favorites_file(self) -> Path:
            return app_module.GLOBAL_FAVORITES_FILE

        def _default_global_notes_file(self) -> Path:
            return app_module.GLOBAL_NOTES_FILE

        def _default_note_presets_file(self) -> Path:
            return app_module.NOTE_PRESETS_FILE

        def _default_item_customizations_file(self) -> Path:
            return app_module.ITEM_CUSTOMIZATIONS_FILE

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
            return project_dir / app_module.PROJECT_CONFIG_FILE

        def _current_project_path(self) -> Optional[Path]:
            return Path(self.current_project_dir) if self.current_project_dir else None

        def _current_project_name(self) -> str:
            project_dir = self._current_project_path()
            if not project_dir or not project_dir.is_dir():
                return app_module.DEFAULT_PROJECT_NAME
            return str(self._read_project_config(project_dir).get("name", app_module.DEFAULT_PROJECT_NAME)).strip() or app_module.DEFAULT_PROJECT_NAME

        def _safe_project_dir_name(self, name: str) -> str:
            safe = name.strip().replace("/", "-").replace("\\", "-")
            return safe or app_module.DEFAULT_PROJECT_NAME

        def _current_source_root(self) -> Optional[Path]:
            item = self.source_roots_list.currentItem()
            if not item:
                return None
            return Path(item.data(Qt.UserRole))

        def _current_source_root_value(self) -> str:
            source_root = self._current_source_root()
            return str(source_root) if source_root else ""

        def _active_records_table(self) -> QTableWidget:
            current = self.records_tabs.currentWidget()
            if current in self._records_tab_tables:
                return self._records_tab_tables[current]  # type: ignore[index]
            return self.all_records_table

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
            dialog.setWindowTitle(app_module.APP_NAME)
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
            title = QLabel(app_module.APP_NAME)
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
                "schema_version": app_module.SETTINGS_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
            data = self._read_json_candidates([app_module.SETTINGS_FILE, app_module.LEGACY_SETTINGS_FILE])
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
            self._ensure_parent_dir(app_module.SETTINGS_FILE)
            app_module.SETTINGS_FILE.write_text(
                json.dumps(self._settings_payload(), indent=2), encoding="utf-8"
            )

        def _load_tracked_projects(self) -> None:
            self.tracked_projects = []
            data = self._read_json_candidates(
                [self._projects_registry_path(), app_module.LEGACY_PROJECTS_FILE]
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
                "schema_version": app_module.TRACKED_PROJECTS_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
                "schema_version": app_module.PROJECT_CONFIG_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
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
            default_dir = base_dir / app_module.DEFAULT_PROJECT_NAME
            if not self._project_config_path(default_dir).exists():
                self._write_project_config(
                    default_dir,
                    app_module.DEFAULT_PROJECT_NAME,
                    [],
                    [],
                    "No Filter",
                    [],
                    [],
                )
            self._register_tracked_project(app_module.DEFAULT_PROJECT_NAME, default_dir)
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
                project_dir = str(entry["project_dir"])
                if search_term and not self._tracked_project_matches_search(entry, search_term):
                    continue
                item = QListWidgetItem(entry["name"])
                item.setData(Qt.UserRole, project_dir)
                tooltip_lines = [project_dir]
                if entry.get("client"):
                    tooltip_lines.append(f"Client: {entry['client']}")
                if entry.get("year_started"):
                    tooltip_lines.append(f"Year Started: {entry['year_started']}")
                self._set_projects_item_base_tooltip(item, "\n".join(tooltip_lines))
                self._apply_projects_list_item_style(item, "tracked_projects", project_dir)
                self.tracked_projects_list.addItem(item)
                if project_dir == self.current_project_dir:
                    current_item = item

            if current_item:
                self.tracked_projects_list.setCurrentItem(current_item)
            elif self.tracked_projects_list.count() > 0:
                self.tracked_projects_list.setCurrentRow(0)

        def _on_project_search_changed(self, _text: str) -> None:
            self.project_search_debounce.start()

        def _tracked_project_search_blob(self, entry: Dict[str, object]) -> str:
            project_dir = str(entry.get("project_dir", ""))
            custom_groups = self._item_customization_groups("tracked_projects", project_dir)
            return " ".join(
                [
                    str(entry.get("name", "")).lower(),
                    str(entry.get("client", "")).lower(),
                    str(entry.get("year_started", "")).lower(),
                    " ".join(custom_groups).lower(),
                ]
            )

        def _tracked_project_matches_search(self, entry: Dict[str, object], search_term: str) -> bool:
            normalized = str(search_term).strip().lower()
            if not normalized:
                return True
            return normalized in self._tracked_project_search_blob(entry)

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
            self, actions: List[Tuple[str, Callable[[], None]]], label: str = "Menu"
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

from __future__ import annotations

import app as app_module
from app import *


class NotesMixin:
        def _normalize_note_preset_note(self, entry: object) -> Optional[Dict[str, object]]:
            if not isinstance(entry, dict):
                return None
            subject = str(entry.get("subject", "")).strip()
            if not subject:
                return None
            return {
                "id": str(entry.get("id", "")).strip() or str(uuid4()),
                "subject": subject,
                "body": str(entry.get("body", "")).strip(),
                "auto_add_new_projects": bool(entry.get("auto_add_new_projects", False)),
            }

        def _normalize_note_preset_group(self, entry: object) -> Optional[Dict[str, object]]:
            if not isinstance(entry, dict):
                return None
            name = str(entry.get("name", "")).strip()
            if not name:
                return None
            note_ids: List[str] = []
            raw_ids = entry.get("note_ids", [])
            if isinstance(raw_ids, list):
                for note_id in raw_ids:
                    value = str(note_id).strip()
                    if value and value not in note_ids:
                        note_ids.append(value)
            return {
                "id": str(entry.get("id", "")).strip() or str(uuid4()),
                "name": name,
                "note_ids": note_ids,
                "auto_add_new_projects": bool(entry.get("auto_add_new_projects", False)),
            }

        def _load_note_presets(self) -> None:
            data = self._read_json_candidates([self._default_note_presets_file()])
            self.note_presets_notes = []
            self.note_preset_groups = []
            if not isinstance(data, dict):
                return

            raw_notes = data.get("notes", [])
            if isinstance(raw_notes, list):
                for entry in raw_notes:
                    normalized = self._normalize_note_preset_note(entry)
                    if normalized:
                        self.note_presets_notes.append(normalized)

            valid_note_ids = {str(note["id"]) for note in self.note_presets_notes}
            raw_groups = data.get("groups", [])
            if isinstance(raw_groups, list):
                for entry in raw_groups:
                    normalized_group = self._normalize_note_preset_group(entry)
                    if not normalized_group:
                        continue
                    normalized_group["note_ids"] = [
                        note_id
                        for note_id in normalized_group.get("note_ids", [])
                        if str(note_id) in valid_note_ids
                    ]
                    self.note_preset_groups.append(normalized_group)

        def _save_note_presets(self) -> None:
            path = self._default_note_presets_file()
            self._ensure_parent_dir(path)
            payload = {
                "schema_version": app_module.NOTE_PRESETS_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
                "notes": self.note_presets_notes,
                "groups": self.note_preset_groups,
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        def _project_note_from_preset(self, preset_note: Dict[str, object]) -> Dict[str, str]:
            timestamp = datetime.now().isoformat(timespec="seconds")
            return {
                "id": str(uuid4()),
                "subject": str(preset_note.get("subject", "")).strip(),
                "body": str(preset_note.get("body", "")).strip(),
                "created_at": timestamp,
                "updated_at": timestamp,
            }

        def _default_notes_from_presets(self) -> List[Dict[str, str]]:
            by_note_id = {
                str(note.get("id", "")): note
                for note in self.note_presets_notes
                if str(note.get("id", "")).strip()
            }
            selected_note_ids: List[str] = []
            for note in self.note_presets_notes:
                note_id = str(note.get("id", "")).strip()
                if note_id and bool(note.get("auto_add_new_projects", False)) and note_id not in selected_note_ids:
                    selected_note_ids.append(note_id)
            for group in self.note_preset_groups:
                if not bool(group.get("auto_add_new_projects", False)):
                    continue
                for note_id in group.get("note_ids", []):
                    value = str(note_id).strip()
                    if value and value not in selected_note_ids and value in by_note_id:
                        selected_note_ids.append(value)
            notes: List[Dict[str, str]] = []
            for note_id in selected_note_ids:
                preset = by_note_id.get(note_id)
                if preset:
                    notes.append(self._project_note_from_preset(preset))
            return notes

        def _add_preset_notes_to_current_project(self, note_ids: List[str]) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            notes = self._current_project_notes()
            by_note_id = {
                str(note.get("id", "")): note
                for note in self.note_presets_notes
                if str(note.get("id", "")).strip()
            }
            added = 0
            for note_id in note_ids:
                preset = by_note_id.get(note_id)
                if not preset:
                    continue
                notes.append(self._project_note_from_preset(preset))
                added += 1
            self._set_project_notes(notes)
            if added:
                self._info(f"Added {added} preset note(s) to current project.")

        def _normalize_group_name(self, value: object) -> str:
            return " ".join(str(value or "").strip().split())

        def _normalize_hex_color(self, value: object) -> str:
            text = str(value or "").strip()
            color = QColor(text)
            if not color.isValid():
                return ""
            return color.name().upper()

        def _best_contrast_font_color(self, background_hex: str) -> str:
            color = QColor(background_hex)
            if not color.isValid():
                return "#000000"
            luminance = (
                (0.299 * color.red()) + (0.587 * color.green()) + (0.114 * color.blue())
            ) / 255.0
            return "#000000" if luminance >= 0.5 else "#FFFFFF"

        def _effective_font_color(
            self,
            background_hex: str,
            configured_font_hex: str,
            auto_contrast: bool,
        ) -> str:
            bg = self._normalize_hex_color(background_hex)
            fg = self._normalize_hex_color(configured_font_hex)
            if fg:
                return fg
            if auto_contrast and bg:
                return self._best_contrast_font_color(bg)
            return ""

        def _normalize_group_style(self, value: object) -> Dict[str, object]:
            if not isinstance(value, dict):
                return {}
            background = self._normalize_hex_color(value.get("background", ""))
            font = self._normalize_hex_color(value.get("font", ""))
            auto_contrast = bool(value.get("auto_contrast", True))
            normalized: Dict[str, object] = {}
            if background:
                normalized["background"] = background
                normalized["auto_contrast"] = auto_contrast
            if font:
                normalized["font"] = font
            return normalized

        def _normalize_item_customization(self, value: object) -> Dict[str, object]:
            if not isinstance(value, dict):
                return {}
            groups: List[str] = []
            for group in value.get("groups", []) if isinstance(value.get("groups", []), list) else []:
                group_name = self._normalize_group_name(group)
                if group_name and group_name not in groups:
                    groups.append(group_name)
            background = self._normalize_hex_color(value.get("background", ""))
            font = self._normalize_hex_color(value.get("font", ""))
            auto_contrast = bool(value.get("auto_contrast", True))
            normalized: Dict[str, object] = {}
            if groups:
                normalized["groups"] = groups
            if background:
                normalized["background"] = background
            if font:
                normalized["font"] = font
            if background:
                normalized["auto_contrast"] = auto_contrast
            if bool(value.get("use_group_colors", False)):
                normalized["use_group_colors"] = True
            group_color_source = self._normalize_group_name(value.get("group_color_source", ""))
            if group_color_source and group_color_source in groups:
                normalized["group_color_source"] = group_color_source
            return normalized

        def _load_item_customizations(self) -> None:
            path = self._default_item_customizations_file()
            data = self._read_json_candidates([path])
            self.item_customization_groups = []
            self.item_customizations = {}
            self.item_customization_group_styles = {}
            if not isinstance(data, dict):
                return

            raw_groups = data.get("groups", [])
            if isinstance(raw_groups, list):
                for group in raw_groups:
                    group_name = ""
                    group_style: Dict[str, object] = {}
                    if isinstance(group, dict):
                        group_name = self._normalize_group_name(group.get("name", ""))
                        group_style = self._normalize_group_style(group)
                    else:
                        group_name = self._normalize_group_name(group)
                    if group_name and group_name not in self.item_customization_groups:
                        self.item_customization_groups.append(group_name)
                    if group_name and group_style:
                        self.item_customization_group_styles[group_name] = group_style

            raw_scopes = data.get("scopes", {})
            if isinstance(raw_scopes, dict):
                for scope, scope_value in raw_scopes.items():
                    if not isinstance(scope_value, dict):
                        continue
                    normalized_scope: Dict[str, Dict[str, object]] = {}
                    for item_key, item_value in scope_value.items():
                        key = str(item_key).strip()
                        if not key:
                            continue
                        normalized = self._normalize_item_customization(item_value)
                        if normalized:
                            normalized_scope[key] = normalized
                            for group in normalized.get("groups", []):
                                group_name = self._normalize_group_name(group)
                                if group_name and group_name not in self.item_customization_groups:
                                    self.item_customization_groups.append(group_name)
                    if normalized_scope:
                        self.item_customizations[str(scope)] = normalized_scope

        def _save_item_customizations(self) -> None:
            path = self._default_item_customizations_file()
            self._ensure_parent_dir(path)
            groups_payload: List[Dict[str, object]] = []
            for group_name in self.item_customization_groups:
                payload: Dict[str, object] = {"name": group_name}
                payload.update(self._normalize_group_style(self.item_customization_group_styles.get(group_name, {})))
                groups_payload.append(payload)
            payload = {
                "schema_version": app_module.ITEM_CUSTOMIZATIONS_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
                "groups": groups_payload,
                "scopes": self.item_customizations,
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        def _projects_customization_scope(self, list_widget: QListWidget) -> str:
            if list_widget is self.tracked_projects_list:
                return "tracked_projects"
            if list_widget is self.favorites_list:
                return "project_favorites"
            if list_widget is self.global_favorites_list:
                return "global_favorites"
            if list_widget is self.notes_list:
                return "project_notes"
            if hasattr(self, "project_checked_out_list") and list_widget is self.project_checked_out_list:
                return "checked_out_records"
            if hasattr(self, "project_reference_list") and list_widget is self.project_reference_list:
                return "reference_records"
            return ""

        def _item_customization_for(self, scope: str, item_key: str) -> Dict[str, object]:
            if not scope or not item_key:
                return {}
            raw = self.item_customizations.get(scope, {}).get(item_key, {})
            return self._normalize_item_customization(raw)

        def _item_customization_groups(self, scope: str, item_key: str) -> List[str]:
            custom = self._item_customization_for(scope, item_key)
            groups = custom.get("groups", [])
            if not isinstance(groups, list):
                return []
            normalized: List[str] = []
            for group in groups:
                group_name = self._normalize_group_name(group)
                if group_name:
                    normalized.append(group_name)
            return normalized

        def _record_customization_scope(self, record: CheckoutRecord) -> str:
            return "reference_records" if record.record_type == "reference_copy" else "checked_out_records"

        def _record_customization_key(self, record: CheckoutRecord) -> str:
            return "|".join(
                [
                    record.record_type,
                    record.project_dir,
                    record.source_file,
                    record.local_file,
                ]
            )

        def _record_search_blob(self, record: CheckoutRecord) -> str:
            groups = " ".join(
                self._item_customization_groups(
                    self._record_customization_scope(record),
                    self._record_customization_key(record),
                )
            )
            return " ".join(
                [
                    record.source_file.lower(),
                    record.locked_source_file.lower(),
                    record.local_file.lower(),
                    record.initials.lower(),
                    record.project_name.lower(),
                    record.project_dir.lower(),
                    self._format_checkout_timestamp(record.checked_out_at).lower(),
                    groups.lower(),
                ]
            )

        def _group_style_for_name(self, group_name: str) -> Dict[str, object]:
            return self._normalize_group_style(self.item_customization_group_styles.get(group_name, {}))

        def _resolve_group_color_source(
            self, custom: Dict[str, object], groups: List[str]
        ) -> str:
            source = self._normalize_group_name(custom.get("group_color_source", ""))
            if source and source in groups:
                return source
            return groups[0] if groups else ""

        def _set_item_customization(self, scope: str, item_key: str, value: Dict[str, object]) -> None:
            if not scope or not item_key:
                return
            normalized = self._normalize_item_customization(value)
            if normalized:
                self.item_customizations.setdefault(scope, {})[item_key] = normalized
                for group in normalized.get("groups", []):
                    group_name = self._normalize_group_name(group)
                    if group_name and group_name not in self.item_customization_groups:
                        self.item_customization_groups.append(group_name)
            else:
                scope_map = self.item_customizations.get(scope, {})
                scope_map.pop(item_key, None)
                if not scope_map and scope in self.item_customizations:
                    self.item_customizations.pop(scope, None)
            self._save_item_customizations()

        def _set_projects_item_base_tooltip(self, item: QListWidgetItem, tooltip: str) -> None:
            item.setData(Qt.UserRole + 40, tooltip)
            item.setToolTip(tooltip)

        def _apply_record_table_row_style(
            self, table: QTableWidget, row_idx: int, record: CheckoutRecord
        ) -> None:
            scope = self._record_customization_scope(record)
            item_key = self._record_customization_key(record)
            custom = self._item_customization_for(scope, item_key)
            background = self._normalize_hex_color(custom.get("background", ""))
            configured_font = self._normalize_hex_color(custom.get("font", ""))
            auto_contrast = bool(custom.get("auto_contrast", True))
            groups = [str(group) for group in custom.get("groups", []) if str(group).strip()]
            group_used = ""
            if bool(custom.get("use_group_colors", False)) and groups:
                group_used = self._resolve_group_color_source(custom, groups)
                group_style = self._group_style_for_name(group_used)
                background = self._normalize_hex_color(group_style.get("background", background))
                configured_font = self._normalize_hex_color(group_style.get("font", configured_font))
                auto_contrast = bool(group_style.get("auto_contrast", auto_contrast))
            foreground = (
                self._effective_font_color(background, configured_font, auto_contrast)
                if background
                else configured_font
            )
            for col_idx in range(table.columnCount()):
                item = table.item(row_idx, col_idx)
                if item is None:
                    continue
                item.setBackground(QBrush())
                item.setForeground(QBrush())
                if background:
                    item.setBackground(QBrush(QColor(background)))
                if foreground:
                    item.setForeground(QBrush(QColor(foreground)))
                if groups:
                    tooltip = item.toolTip()
                    extra = f"\nGroups: {', '.join(groups)}"
                    if group_used:
                        extra += f"\nUsing Group Colors: {group_used}"
                    item.setToolTip((tooltip + extra).strip())

        def _apply_projects_list_item_style(
            self, item: QListWidgetItem, scope: str, item_key: str
        ) -> None:
            item.setBackground(QBrush())
            item.setForeground(QBrush())
            base_tooltip = str(item.data(Qt.UserRole + 40) or item.toolTip() or "")
            custom = self._item_customization_for(scope, item_key)
            if not custom:
                item.setToolTip(base_tooltip)
                return

            groups = [str(group) for group in custom.get("groups", []) if str(group).strip()]
            use_group_colors = bool(custom.get("use_group_colors", False))
            background = self._normalize_hex_color(custom.get("background", ""))
            configured_font = self._normalize_hex_color(custom.get("font", ""))
            auto_contrast = bool(custom.get("auto_contrast", True))
            group_used = ""
            if use_group_colors and groups:
                group_used = self._resolve_group_color_source(custom, groups)
                group_style = self._group_style_for_name(group_used)
                background = self._normalize_hex_color(group_style.get("background", background))
                configured_font = self._normalize_hex_color(group_style.get("font", configured_font))
                auto_contrast = bool(group_style.get("auto_contrast", auto_contrast))
            if background:
                item.setBackground(QBrush(QColor(background)))
                effective_font = self._effective_font_color(background, configured_font, auto_contrast)
                if effective_font:
                    item.setForeground(QBrush(QColor(effective_font)))
            elif configured_font:
                item.setForeground(QBrush(QColor(configured_font)))

            tooltip_lines = [line for line in [base_tooltip.strip()] if line]
            if groups:
                tooltip_lines.append(f"Groups: {', '.join(groups)}")
            if group_used:
                tooltip_lines.append(f"Using Group Colors: {group_used}")
            item.setToolTip("\n".join(tooltip_lines))

        def _refresh_projects_customization_scope(self, scope: str) -> None:
            if scope == "tracked_projects":
                self._refresh_tracked_projects_list()
                return
            if scope == "project_favorites":
                self._refresh_favorites_list(self._current_project_favorites())
                return
            if scope == "global_favorites":
                self._refresh_global_favorites_list()
                return
            if scope == "project_notes":
                self._refresh_notes_list(self._current_project_notes())
                return
            if scope in {"checked_out_records", "reference_records"}:
                self._refresh_project_local_files_lists()
                self._render_records_tables()

        def _customize_organize_selected(self, list_widget: QListWidget) -> None:
            scope = self._projects_customization_scope(list_widget)
            if not scope:
                return
            selected_items = list_widget.selectedItems()
            if not selected_items:
                current = list_widget.currentItem()
                if current:
                    selected_items = [current]
            if not selected_items:
                self._error("Select at least one item to customize.")
                return

            targets: List[Tuple[str, str]] = []
            for selected in selected_items:
                key = str(selected.data(Qt.UserRole)).strip()
                if not key:
                    continue
                targets.append((key, selected.text().strip() or key))
            if not targets:
                self._error("Selected item does not support customization.")
                return
            self._show_customize_organize_dialog(scope, targets)

        def _resolve_use_group_colors(
            self,
            existing: Dict[str, object],
            chosen_groups: List[str],
            requested_use_group_colors: bool,
            user_toggled_use_group_colors: bool,
        ) -> bool:
            if user_toggled_use_group_colors:
                return requested_use_group_colors
            had_groups = bool(existing.get("groups", []))
            if (not had_groups) and chosen_groups:
                return True
            return bool(existing.get("use_group_colors", False))

        def _should_auto_enable_group_colors_checkbox(
            self,
            had_groups_initially: bool,
            previous_selected_count: int,
            new_selected_count: int,
            user_touched_checkbox: bool,
        ) -> bool:
            if user_touched_checkbox:
                return False
            if had_groups_initially:
                return False
            return previous_selected_count == 0 and new_selected_count > 0

        def _show_customize_organize_dialog(self, scope: str, targets: List[Tuple[str, str]]) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Customize / Organize")
            dialog.resize(700, 680)
            layout = QVBoxLayout(dialog)

            target_label = QLabel(
                targets[0][1] if len(targets) == 1 else f"{len(targets)} selected items"
            )
            target_label.setWordWrap(True)
            layout.addWidget(target_label)

            group_frame = QGroupBox("Groups")
            group_layout = QVBoxLayout(group_frame)
            group_search_edit = QLineEdit()
            group_search_edit.setPlaceholderText("Search groups")
            group_layout.addWidget(group_search_edit)
            groups_list = QListWidget()
            groups_list.setContextMenuPolicy(Qt.CustomContextMenu)
            group_layout.addWidget(groups_list, stretch=1)
            group_buttons = QHBoxLayout()
            add_group_btn = QPushButton("Add Group")
            rename_group_btn = QPushButton("Rename Group")
            remove_group_btn = QPushButton("Remove Group")
            apply_group_color_btn = QPushButton("Apply Group Color")
            group_buttons.addWidget(add_group_btn)
            group_buttons.addWidget(rename_group_btn)
            group_buttons.addWidget(remove_group_btn)
            group_buttons.addWidget(apply_group_color_btn)
            group_layout.addLayout(group_buttons)

            group_color_layout = QGridLayout()
            group_bg_edit = QLineEdit()
            group_bg_edit.setReadOnly(True)
            pick_group_bg_btn = QPushButton("Group Highlight")
            clear_group_bg_btn = QPushButton("Clear")
            group_font_edit = QLineEdit()
            group_font_edit.setReadOnly(True)
            pick_group_font_btn = QPushButton("Group Font")
            clear_group_font_btn = QPushButton("Clear")
            group_auto_checkbox = QCheckBox("Group auto-contrast font")
            group_auto_checkbox.setChecked(True)
            group_color_layout.addWidget(QLabel("Selected Group Colors:"), 0, 0)
            group_color_layout.addWidget(group_bg_edit, 0, 1)
            group_color_layout.addWidget(pick_group_bg_btn, 0, 2)
            group_color_layout.addWidget(clear_group_bg_btn, 0, 3)
            group_color_layout.addWidget(QLabel(""), 1, 0)
            group_color_layout.addWidget(group_font_edit, 1, 1)
            group_color_layout.addWidget(pick_group_font_btn, 1, 2)
            group_color_layout.addWidget(clear_group_font_btn, 1, 3)
            group_color_layout.addWidget(group_auto_checkbox, 2, 0, 1, 4)
            group_layout.addLayout(group_color_layout)
            layout.addWidget(group_frame, stretch=1)

            color_frame = QGroupBox("Color Highlighting")
            color_layout = QGridLayout(color_frame)
            background_edit = QLineEdit()
            background_edit.setReadOnly(True)
            pick_background_btn = QPushButton("Pick Highlight")
            clear_background_btn = QPushButton("Clear")
            font_edit = QLineEdit()
            font_edit.setReadOnly(True)
            pick_font_btn = QPushButton("Pick Font Color")
            clear_font_btn = QPushButton("Clear")
            auto_contrast_checkbox = QCheckBox("Auto-contrast font color")
            auto_contrast_checkbox.setChecked(True)
            group_color_source_label = QLabel("Group colors source: None")
            preview = QLabel("Preview")
            preview.setFrameShape(QFrame.StyledPanel)
            preview.setAlignment(Qt.AlignCenter)
            preview.setMinimumHeight(44)
            color_layout.addWidget(QLabel("Highlight:"), 0, 0)
            color_layout.addWidget(background_edit, 0, 1)
            color_layout.addWidget(pick_background_btn, 0, 2)
            color_layout.addWidget(clear_background_btn, 0, 3)
            color_layout.addWidget(QLabel("Font:"), 1, 0)
            color_layout.addWidget(font_edit, 1, 1)
            color_layout.addWidget(pick_font_btn, 1, 2)
            color_layout.addWidget(clear_font_btn, 1, 3)
            color_layout.addWidget(auto_contrast_checkbox, 2, 0, 1, 4)
            color_layout.addWidget(group_color_source_label, 3, 0, 1, 4)
            color_layout.addWidget(preview, 4, 0, 1, 4)
            layout.addWidget(color_frame)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(buttons)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)

            existing_by_key: Dict[str, Dict[str, object]] = {
                item_key: self._item_customization_for(scope, item_key) for item_key, _ in targets
            }
            existing = list(existing_by_key.values())
            selected_group_names = set()
            if existing:
                group_candidates = [
                    set(str(group) for group in custom.get("groups", []))
                    for custom in existing
                ]
                selected_group_names = set.intersection(*group_candidates) if group_candidates else set()
            common_background = ""
            common_font = ""
            common_auto = True
            common_use_group_colors = False
            common_group_color_source = ""
            if existing:
                background_values = {str(custom.get("background", "")).strip() for custom in existing}
                font_values = {str(custom.get("font", "")).strip() for custom in existing}
                auto_values = {bool(custom.get("auto_contrast", True)) for custom in existing}
                use_group_values = {bool(custom.get("use_group_colors", False)) for custom in existing}
                group_source_values = {
                    self._normalize_group_name(custom.get("group_color_source", ""))
                    for custom in existing
                    if bool(custom.get("use_group_colors", False))
                }
                common_background = next(iter(background_values)) if len(background_values) == 1 else ""
                common_font = next(iter(font_values)) if len(font_values) == 1 else ""
                common_auto = auto_values == {True}
                common_use_group_colors = use_group_values == {True}
                if len(group_source_values) == 1:
                    common_group_color_source = next(iter(group_source_values))

            had_groups_initially = any(bool(custom.get("groups", [])) for custom in existing)
            manual_font_selected = bool(common_font)
            use_group_colors_touched = False
            requested_use_group_colors = common_use_group_colors
            selected_group_for_colors = common_group_color_source

            def refresh_groups_widget(selected_groups: Optional[set] = None) -> None:
                current_name = current_group_name()
                groups_list.clear()
                selected_lookup = selected_groups if selected_groups is not None else set()
                search_text = group_search_edit.text().strip().lower()
                for group_name in self.item_customization_groups:
                    if search_text and search_text not in group_name.lower():
                        continue
                    item = QListWidgetItem(group_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.Checked if group_name in selected_lookup else Qt.Unchecked
                    )
                    groups_list.addItem(item)
                if current_name:
                    for row in range(groups_list.count()):
                        if self._normalize_group_name(groups_list.item(row).text()) == current_name:
                            groups_list.setCurrentRow(row)
                            break
                elif groups_list.count() > 0:
                    groups_list.setCurrentRow(0)

            def current_group_name() -> str:
                current = groups_list.currentItem()
                return self._normalize_group_name(current.text()) if current else ""

            def refresh_selected_group_style() -> None:
                group_name = current_group_name()
                style = self._group_style_for_name(group_name)
                group_bg_edit.setText(str(style.get("background", "")))
                group_font_edit.setText(str(style.get("font", "")))
                group_auto_checkbox.setChecked(bool(style.get("auto_contrast", True)))

            def resolved_group_for_preview() -> str:
                if selected_group_for_colors and selected_group_for_colors in selected_group_names:
                    return selected_group_for_colors
                current_name = current_group_name()
                if current_name and current_name in selected_group_names:
                    return current_name
                for group_name_candidate in self.item_customization_groups:
                    if group_name_candidate in selected_group_names:
                        return group_name_candidate
                return ""

            def refresh_group_color_source_label() -> None:
                group_name = resolved_group_for_preview() if requested_use_group_colors else ""
                group_color_source_label.setText(
                    f"Group colors source: {group_name or 'None'}"
                )

            def update_preview() -> None:
                background = self._normalize_hex_color(background_edit.text())
                font = self._normalize_hex_color(font_edit.text())
                auto_for_preview = auto_contrast_checkbox.isChecked()
                if requested_use_group_colors:
                    group_name = resolved_group_for_preview()
                    if group_name:
                        group_style = self._group_style_for_name(group_name)
                        background = self._normalize_hex_color(group_style.get("background", background))
                        if not manual_font_selected:
                            font = self._normalize_hex_color(group_style.get("font", font))
                        auto_for_preview = bool(group_style.get("auto_contrast", auto_for_preview))
                effective_font = self._effective_font_color(
                    background,
                    font if manual_font_selected else "",
                    auto_for_preview,
                )
                background_css = f"background-color: {background};" if background else ""
                foreground_css = f"color: {effective_font};" if effective_font else ""
                preview.setStyleSheet(f"padding: 8px; {background_css} {foreground_css}")
                preview.setText("Preview")
                refresh_group_color_source_label()

            refresh_groups_widget(selected_group_names)
            background_edit.setText(common_background)
            font_edit.setText(common_font)
            auto_contrast_checkbox.setChecked(common_auto)
            if not selected_group_for_colors and common_use_group_colors:
                selected_group_for_colors = resolved_group_for_preview()
            refresh_selected_group_style()
            update_preview()

            def apply_selected_group_color(mark_touched: bool = True) -> None:
                nonlocal selected_group_for_colors, requested_use_group_colors, use_group_colors_touched
                group_name = current_group_name()
                if not group_name or group_name not in selected_group_names:
                    group_name = resolved_group_for_preview()
                if not group_name:
                    self._error("Select and check a group first.")
                    return
                selected_group_for_colors = group_name
                requested_use_group_colors = True
                if mark_touched:
                    use_group_colors_touched = True
                update_preview()

            def on_add_group() -> None:
                name, accepted = QInputDialog.getText(dialog, "Add Group", "Group name:")
                if not accepted:
                    return
                group_name = self._normalize_group_name(name)
                if not group_name:
                    return
                if group_name not in self.item_customization_groups:
                    self.item_customization_groups.append(group_name)
                selected_group_names.add(group_name)
                refresh_groups_widget(selected_group_names)
                for row in range(groups_list.count()):
                    item = groups_list.item(row)
                    if item.text() == group_name:
                        groups_list.setCurrentRow(row)
                        break
                refresh_selected_group_style()

            def on_rename_group() -> None:
                current_item = groups_list.currentItem()
                if current_item is None:
                    self._error("Select a group to rename.")
                    return
                current_name = current_item.text().strip()
                new_name, accepted = QInputDialog.getText(
                    dialog, "Rename Group", "New group name:", text=current_name
                )
                if not accepted:
                    return
                normalized_new = self._normalize_group_name(new_name)
                if not normalized_new:
                    return
                if normalized_new != current_name and normalized_new in self.item_customization_groups:
                    self._error("A group with this name already exists.")
                    return
                for idx, group_name in enumerate(self.item_customization_groups):
                    if group_name == current_name:
                        self.item_customization_groups[idx] = normalized_new
                if current_name in self.item_customization_group_styles:
                    self.item_customization_group_styles[normalized_new] = self.item_customization_group_styles.pop(
                        current_name
                    )
                for scope_items in self.item_customizations.values():
                    for custom in scope_items.values():
                        groups = custom.get("groups", [])
                        if not isinstance(groups, list):
                            continue
                        updated = [
                            normalized_new if str(group) == current_name else str(group)
                            for group in groups
                        ]
                        deduped: List[str] = []
                        for group in updated:
                            if group and group not in deduped:
                                deduped.append(group)
                        custom["groups"] = deduped
                        if self._normalize_group_name(custom.get("group_color_source", "")) == current_name:
                            custom["group_color_source"] = normalized_new
                if current_name in selected_group_names:
                    selected_group_names.remove(current_name)
                    selected_group_names.add(normalized_new)
                refresh_groups_widget(selected_group_names)
                refresh_selected_group_style()

            def on_remove_group() -> None:
                current_item = groups_list.currentItem()
                if current_item is None:
                    self._error("Select a group to remove.")
                    return
                group_name = current_item.text().strip()
                self.item_customization_groups = [
                    name for name in self.item_customization_groups if name != group_name
                ]
                self.item_customization_group_styles.pop(group_name, None)
                selected_group_names.discard(group_name)
                for scope_items in self.item_customizations.values():
                    for custom in scope_items.values():
                        groups = custom.get("groups", [])
                        if not isinstance(groups, list):
                            continue
                        custom["groups"] = [
                            str(group) for group in groups if str(group).strip() and str(group) != group_name
                        ]
                        if self._normalize_group_name(custom.get("group_color_source", "")) == group_name:
                            custom.pop("group_color_source", None)
                refresh_groups_widget(selected_group_names)
                if groups_list.count() > 0:
                    groups_list.setCurrentRow(0)
                refresh_selected_group_style()

            def on_pick_group_background() -> None:
                group_name = current_group_name()
                if not group_name:
                    self._error("Select a group to set colors.")
                    return
                current = QColor(group_bg_edit.text()) if group_bg_edit.text().strip() else QColor()
                chosen = QColorDialog.getColor(current, dialog, "Select Group Highlight Color")
                if not chosen.isValid():
                    return
                style = self._group_style_for_name(group_name)
                style["background"] = chosen.name().upper()
                style["auto_contrast"] = bool(group_auto_checkbox.isChecked())
                self.item_customization_group_styles[group_name] = style
                refresh_selected_group_style()
                update_preview()

            def on_clear_group_background() -> None:
                group_name = current_group_name()
                if not group_name:
                    return
                style = self._group_style_for_name(group_name)
                style.pop("background", None)
                style.pop("auto_contrast", None)
                if style:
                    self.item_customization_group_styles[group_name] = style
                else:
                    self.item_customization_group_styles.pop(group_name, None)
                refresh_selected_group_style()
                update_preview()

            def on_pick_group_font() -> None:
                group_name = current_group_name()
                if not group_name:
                    self._error("Select a group to set colors.")
                    return
                current = QColor(group_font_edit.text()) if group_font_edit.text().strip() else QColor()
                chosen = QColorDialog.getColor(current, dialog, "Select Group Font Color")
                if not chosen.isValid():
                    return
                style = self._group_style_for_name(group_name)
                style["font"] = chosen.name().upper()
                if "background" in style:
                    style["auto_contrast"] = bool(group_auto_checkbox.isChecked())
                self.item_customization_group_styles[group_name] = style
                refresh_selected_group_style()
                update_preview()

            def on_clear_group_font() -> None:
                group_name = current_group_name()
                if not group_name:
                    return
                style = self._group_style_for_name(group_name)
                style.pop("font", None)
                if not style:
                    self.item_customization_group_styles.pop(group_name, None)
                else:
                    self.item_customization_group_styles[group_name] = style
                refresh_selected_group_style()
                update_preview()

            def on_group_auto_toggled(checked: bool) -> None:
                group_name = current_group_name()
                if not group_name:
                    return
                style = self._group_style_for_name(group_name)
                if "background" in style:
                    style["auto_contrast"] = bool(checked)
                    self.item_customization_group_styles[group_name] = style
                    update_preview()

            def on_pick_background() -> None:
                current = QColor(background_edit.text()) if background_edit.text().strip() else QColor()
                chosen = QColorDialog.getColor(current, dialog, "Select Highlight Color")
                if not chosen.isValid():
                    return
                background_edit.setText(chosen.name().upper())
                update_preview()

            def on_clear_background() -> None:
                background_edit.clear()
                update_preview()

            def on_pick_font() -> None:
                nonlocal manual_font_selected
                current = QColor(font_edit.text()) if font_edit.text().strip() else QColor()
                chosen = QColorDialog.getColor(current, dialog, "Select Font Color")
                if not chosen.isValid():
                    return
                manual_font_selected = True
                font_edit.setText(chosen.name().upper())
                update_preview()

            def on_clear_font() -> None:
                nonlocal manual_font_selected
                manual_font_selected = False
                font_edit.clear()
                update_preview()

            add_group_btn.clicked.connect(on_add_group)
            rename_group_btn.clicked.connect(on_rename_group)
            remove_group_btn.clicked.connect(on_remove_group)
            pick_group_bg_btn.clicked.connect(on_pick_group_background)
            clear_group_bg_btn.clicked.connect(on_clear_group_background)
            pick_group_font_btn.clicked.connect(on_pick_group_font)
            clear_group_font_btn.clicked.connect(on_clear_group_font)
            group_auto_checkbox.toggled.connect(on_group_auto_toggled)
            def on_groups_item_changed(_item: QListWidgetItem) -> None:
                nonlocal selected_group_for_colors
                group_name = self._normalize_group_name(_item.text())
                previous_count = len(selected_group_names)
                if _item.checkState() == Qt.Checked and group_name:
                    selected_group_names.add(group_name)
                else:
                    selected_group_names.discard(group_name)
                    if selected_group_for_colors == group_name:
                        selected_group_for_colors = ""
                new_count = len(selected_group_names)
                if self._should_auto_enable_group_colors_checkbox(
                    had_groups_initially,
                    previous_count,
                    new_count,
                    use_group_colors_touched,
                ):
                    apply_selected_group_color(mark_touched=False)
                update_preview()

            groups_list.itemChanged.connect(on_groups_item_changed)
            groups_list.currentItemChanged.connect(
                lambda _current, _prev: (refresh_selected_group_style(), update_preview())
            )
            group_search_edit.textChanged.connect(
                lambda _text: refresh_groups_widget(set(selected_group_names))
            )

            def show_groups_context_menu(pos: QPoint) -> None:
                item = groups_list.itemAt(pos)
                if item is not None:
                    groups_list.setCurrentItem(item)
                menu = QMenu(dialog)
                apply_action = menu.addAction("Apply Selected Group Color To Item(s)")
                chosen = menu.exec(groups_list.mapToGlobal(pos))
                if chosen == apply_action:
                    apply_selected_group_color(mark_touched=True)

            groups_list.customContextMenuRequested.connect(show_groups_context_menu)
            pick_background_btn.clicked.connect(on_pick_background)
            clear_background_btn.clicked.connect(on_clear_background)
            pick_font_btn.clicked.connect(on_pick_font)
            clear_font_btn.clicked.connect(on_clear_font)
            auto_contrast_checkbox.toggled.connect(lambda _checked: update_preview())
            apply_group_color_btn.clicked.connect(lambda: apply_selected_group_color(mark_touched=True))

            if dialog.exec() != QDialog.Accepted:
                return

            chosen_groups: List[str] = [
                group_name
                for group_name in self.item_customization_groups
                if group_name in selected_group_names
            ]

            background = self._normalize_hex_color(background_edit.text())
            font = self._normalize_hex_color(font_edit.text()) if manual_font_selected else ""
            auto_contrast = bool(auto_contrast_checkbox.isChecked())
            for item_key, _label in targets:
                existing_item = existing_by_key.get(item_key, {})
                payload: Dict[str, object] = {}
                if chosen_groups:
                    payload["groups"] = list(chosen_groups)
                use_group_colors = self._resolve_use_group_colors(
                    existing_item,
                    chosen_groups,
                    requested_use_group_colors,
                    use_group_colors_touched,
                )
                if use_group_colors and chosen_groups:
                    payload["use_group_colors"] = True
                    if selected_group_for_colors and selected_group_for_colors in chosen_groups:
                        payload["group_color_source"] = selected_group_for_colors
                    else:
                        payload["group_color_source"] = chosen_groups[0]
                if background:
                    payload["background"] = background
                    payload["auto_contrast"] = auto_contrast
                    if font:
                        payload["font"] = font
                elif font:
                    payload["font"] = font
                self._set_item_customization(scope, item_key, payload)

            self._save_item_customizations()
            self._refresh_projects_customization_scope(scope)

        def _note_tooltip(self, note: Dict[str, str]) -> str:
            body = note.get("body", "").strip()
            if len(body) > 240:
                body = body[:237].rstrip() + "..."
            return body or "(No body)"

        def _project_notes_logical_view(self) -> Dict[str, List[Dict[str, object]]]:
            return self._project_logical_view("project_notes")

        def _save_project_notes_logical_view(self, view: Dict[str, List[Dict[str, object]]]) -> None:
            self._save_project_logical_view("project_notes", view)

        def _refresh_project_notes_navigation(
            self, view: Optional[Dict[str, List[Dict[str, object]]]] = None
        ) -> None:
            if not hasattr(self, "project_notes_folder_label"):
                return
            current_view = view or self._project_notes_logical_view()
            current_folder_id = self._current_logical_folder_id("project_notes")
            folder_map = self._logical_view_folder_map(current_view)
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("project_notes", "")
            path_parts = self._logical_view_folder_path(current_view, current_folder_id)
            path_text = "Root" if not path_parts else "Root / " + " / ".join(path_parts)
            self.project_notes_folder_label.setText(f"Notes Folder: {path_text}")
            self.project_notes_up_btn.setEnabled(bool(current_folder_id))
            self.project_notes_root_btn.setEnabled(bool(current_folder_id))

        def _prompt_for_project_notes_folder_name(
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

        def _refresh_notes_list(self, notes: List[Dict[str, str]]) -> None:
            self.notes_list.clear()
            search = self.project_notes_search_edit.text().strip().lower()
            search_active = bool(search)
            view = self._project_notes_logical_view()
            folder_map = self._logical_view_folder_map(view)
            current_folder_id = self._current_logical_folder_id("project_notes")
            if current_folder_id and current_folder_id not in folder_map:
                current_folder_id = ""
                self._set_current_logical_folder_id("project_notes", "")
            self._refresh_project_notes_navigation(view)
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
                self.notes_list.addItem(item)
            for note in notes:
                note_id = str(note.get("id", ""))
                parent_folder_id = self._logical_item_parent_folder_id(view, note_id)
                if not search_active and parent_folder_id != current_folder_id:
                    continue
                if search_active:
                    if parent_folder_id and parent_folder_id not in descendant_ids:
                        continue
                subject = note.get("subject", "(Untitled)")
                body = str(note.get("body", ""))
                custom_groups = self._item_customization_groups("project_notes", note_id)
                group_search = " ".join(custom_groups).lower()
                folder_path = self._logical_view_folder_path(view, parent_folder_id)
                folder_search = " / ".join(folder_path).lower()
                if (
                    search
                    and search not in subject.lower()
                    and search not in body.lower()
                    and search not in group_search
                    and search not in folder_search
                ):
                    continue
                item = QListWidgetItem(subject)
                item.setData(Qt.UserRole, note_id)
                item.setData(Qt.UserRole + 1, "item")
                tooltip = self._note_tooltip(note)
                if folder_path:
                    tooltip += "\nFolder: " + " / ".join(["Root", *folder_path])
                self._set_projects_item_base_tooltip(item, tooltip)
                self._apply_projects_list_item_style(item, "project_notes", note_id)
                self.notes_list.addItem(item)

        def _set_project_notes(self, notes: List[Dict[str, str]]) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            self._save_project_config(project_dir, notes=notes)
            self._refresh_notes_list(notes)

        def _selected_note_id(self) -> str:
            item = self.notes_list.currentItem()
            if not item or str(item.data(Qt.UserRole + 1)) == "folder":
                return ""
            return str(item.data(Qt.UserRole)).strip()

        def _selected_project_note(self) -> Optional[Dict[str, str]]:
            note_id = self._selected_note_id()
            if not note_id:
                return None
            for note in self._current_project_notes():
                if str(note.get("id", "")).strip() == note_id:
                    return dict(note)
            return None

        def _project_note_transfer_targets(self) -> List[Dict[str, str]]:
            current_project_dir = str(self._current_project_path() or "")
            targets: List[Dict[str, str]] = []
            for entry in getattr(self, "tracked_projects", []):
                if not isinstance(entry, dict):
                    continue
                project_dir = str(entry.get("project_dir", "")).strip()
                if not project_dir or project_dir == current_project_dir:
                    continue
                targets.append(
                    {
                        "name": str(entry.get("name", "")).strip() or Path(project_dir).name,
                        "project_dir": project_dir,
                    }
                )
            targets.sort(key=lambda item: item["name"].lower())
            return targets

        def _choose_project_note_transfer_target(self, action_label: str) -> Optional[Path]:
            if not self._project_note_transfer_targets():
                self._error("No other tracked projects are available.")
                return None
            target = self._choose_project_target(
                title=f"{action_label} Project Note",
                message="Select a target project:",
                include_current=False,
                include_global=False,
            )
            if not target:
                return None
            _mode, project_dir = target
            return project_dir

        def _clone_project_note_for_transfer(self, note: Dict[str, str]) -> Dict[str, str]:
            return {
                "id": str(uuid4()),
                "subject": str(note.get("subject", "")).strip(),
                "body": str(note.get("body", "")),
                "created_at": str(note.get("created_at", "")).strip(),
                "updated_at": str(note.get("updated_at", "")).strip(),
            }

        def _copy_selected_note_to_project(self) -> None:
            note = self._selected_project_note()
            if not note:
                self._error("Select a note to copy.")
                return
            target_project_dir = self._choose_project_note_transfer_target("Copy")
            if not target_project_dir:
                return
            target_config = self._read_project_config(target_project_dir)
            target_notes = [dict(item) for item in target_config.get("notes", []) if isinstance(item, dict)]
            target_notes.append(self._clone_project_note_for_transfer(note))
            self._save_project_config(target_project_dir, notes=target_notes)
            self._info(f"Copied note to project '{str(target_config.get('name', target_project_dir.name)).strip() or target_project_dir.name}'.")

        def _move_selected_note_to_project(self) -> None:
            note = self._selected_project_note()
            if not note:
                self._error("Select a note to move.")
                return
            target_project_dir = self._choose_project_note_transfer_target("Move")
            if not target_project_dir:
                return
            target_config = self._read_project_config(target_project_dir)
            target_notes = [dict(item) for item in target_config.get("notes", []) if isinstance(item, dict)]
            target_notes.append(self._clone_project_note_for_transfer(note))
            self._save_project_config(target_project_dir, notes=target_notes)
            remaining_notes = [
                existing_note
                for existing_note in self._current_project_notes()
                if str(existing_note.get("id", "")).strip() != str(note.get("id", "")).strip()
            ]
            self._set_project_notes(remaining_notes)
            self._info(f"Moved note to project '{str(target_config.get('name', target_project_dir.name)).strip() or target_project_dir.name}'.")

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

        def _show_note_preset_note_dialog(
            self, note: Optional[Dict[str, object]] = None
        ) -> Optional[Dict[str, object]]:
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Preset Note" if note else "New Preset Note")
            dialog.resize(640, 420)
            layout = QVBoxLayout(dialog)

            form_layout = QGridLayout()
            subject_edit = QLineEdit(str(note.get("subject", "")) if note else "")
            form_layout.addWidget(QLabel("Subject:"), 0, 0)
            form_layout.addWidget(subject_edit, 0, 1)
            layout.addLayout(form_layout)

            body_edit = QPlainTextEdit(str(note.get("body", "")) if note else "")
            body_edit.setPlaceholderText("Note body")
            layout.addWidget(body_edit, stretch=1)

            auto_add_checkbox = QCheckBox("Automatically add to new projects")
            auto_add_checkbox.setChecked(bool(note.get("auto_add_new_projects", False)) if note else False)
            layout.addWidget(auto_add_checkbox)

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

            return {
                "id": str(note.get("id", "")) if note else str(uuid4()),
                "subject": subject,
                "body": body_edit.toPlainText().strip(),
                "auto_add_new_projects": bool(auto_add_checkbox.isChecked()),
            }

        def _show_note_preset_group_dialog(
            self, group: Optional[Dict[str, object]] = None
        ) -> Optional[Dict[str, object]]:
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Note Group" if group else "New Note Group")
            dialog.resize(640, 460)
            layout = QVBoxLayout(dialog)

            form_layout = QGridLayout()
            name_edit = QLineEdit(str(group.get("name", "")) if group else "")
            form_layout.addWidget(QLabel("Group Name:"), 0, 0)
            form_layout.addWidget(name_edit, 0, 1)
            layout.addLayout(form_layout)

            notes_list = QListWidget()
            selected_note_ids = {
                str(note_id).strip()
                for note_id in (group.get("note_ids", []) if group else [])
                if str(note_id).strip()
            }
            for preset_note in self.note_presets_notes:
                note_id = str(preset_note.get("id", "")).strip()
                if not note_id:
                    continue
                item = QListWidgetItem(str(preset_note.get("subject", "(Untitled)")))
                item.setData(Qt.UserRole, note_id)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if note_id in selected_note_ids else Qt.Unchecked)
                notes_list.addItem(item)
            layout.addWidget(QLabel("Include Notes:"))
            layout.addWidget(notes_list, stretch=1)

            auto_add_checkbox = QCheckBox("Automatically add to new projects")
            auto_add_checkbox.setChecked(bool(group.get("auto_add_new_projects", False)) if group else False)
            layout.addWidget(auto_add_checkbox)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)

            if dialog.exec() != QDialog.Accepted:
                return None

            name = name_edit.text().strip()
            if not name:
                self._error("Group name is required.")
                return None
            note_ids: List[str] = []
            for row in range(notes_list.count()):
                item = notes_list.item(row)
                if item.checkState() != Qt.Checked:
                    continue
                note_id = str(item.data(Qt.UserRole)).strip()
                if note_id and note_id not in note_ids:
                    note_ids.append(note_id)
            if not note_ids:
                self._error("Select at least one preset note for the group.")
                return None

            return {
                "id": str(group.get("id", "")) if group else str(uuid4()),
                "name": name,
                "note_ids": note_ids,
                "auto_add_new_projects": bool(auto_add_checkbox.isChecked()),
            }

        def _show_note_presets_dialog(self) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Note Presets")
            dialog.resize(980, 640)
            layout = QVBoxLayout(dialog)

            splitter = QSplitter(Qt.Horizontal)
            notes_panel = QWidget()
            notes_layout = QVBoxLayout(notes_panel)
            notes_layout.addWidget(QLabel("Preset Notes"))
            notes_search = QLineEdit()
            notes_search.setPlaceholderText("Search preset notes")
            notes_layout.addWidget(notes_search)
            notes_list = QListWidget()
            notes_list.setSelectionMode(QListWidget.ExtendedSelection)
            notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
            notes_layout.addWidget(notes_list, stretch=1)

            groups_panel = QWidget()
            groups_layout = QVBoxLayout(groups_panel)
            groups_layout.addWidget(QLabel("Note Groups"))
            groups_search = QLineEdit()
            groups_search.setPlaceholderText("Search note groups")
            groups_layout.addWidget(groups_search)
            groups_list = QListWidget()
            groups_list.setSelectionMode(QListWidget.ExtendedSelection)
            groups_list.setContextMenuPolicy(Qt.CustomContextMenu)
            groups_layout.addWidget(groups_list, stretch=1)

            splitter.addWidget(notes_panel)
            splitter.addWidget(groups_panel)
            splitter.setSizes([520, 460])
            layout.addWidget(splitter, stretch=1)

            notes_buttons = QHBoxLayout()
            new_note_btn = QPushButton("New Note")
            edit_note_btn = QPushButton("Edit")
            remove_note_btn = QPushButton("Remove")
            add_note_to_project_btn = QPushButton("Add To Current Project")
            toggle_note_auto_btn = QPushButton("Toggle Auto-Add")
            notes_buttons.addWidget(new_note_btn)
            notes_buttons.addWidget(edit_note_btn)
            notes_buttons.addWidget(remove_note_btn)
            notes_buttons.addWidget(add_note_to_project_btn)
            notes_buttons.addWidget(toggle_note_auto_btn)
            notes_buttons.addStretch()
            layout.addLayout(notes_buttons)

            groups_buttons = QHBoxLayout()
            new_group_btn = QPushButton("New Group")
            edit_group_btn = QPushButton("Edit")
            remove_group_btn = QPushButton("Remove")
            add_group_to_project_btn = QPushButton("Add Group To Current Project")
            toggle_group_auto_btn = QPushButton("Toggle Auto-Add")
            groups_buttons.addWidget(new_group_btn)
            groups_buttons.addWidget(edit_group_btn)
            groups_buttons.addWidget(remove_group_btn)
            groups_buttons.addWidget(add_group_to_project_btn)
            groups_buttons.addWidget(toggle_group_auto_btn)
            groups_buttons.addStretch()
            layout.addLayout(groups_buttons)

            close_btn_row = QHBoxLayout()
            close_btn_row.addStretch()
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            close_btn_row.addWidget(close_btn)
            layout.addLayout(close_btn_row)

            def refresh_lists() -> None:
                notes_list.clear()
                groups_list.clear()
                note_search_text = notes_search.text().strip().lower()
                for preset_note in self.note_presets_notes:
                    subject = str(preset_note.get("subject", "(Untitled)"))
                    body = str(preset_note.get("body", ""))
                    if note_search_text and note_search_text not in subject.lower() and note_search_text not in body.lower():
                        continue
                    label = subject
                    if bool(preset_note.get("auto_add_new_projects", False)):
                        label += " [Auto]"
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, str(preset_note.get("id", "")))
                    item.setToolTip(body or "(No body)")
                    notes_list.addItem(item)

                group_search_text = groups_search.text().strip().lower()
                note_by_id = {
                    str(note.get("id", "")): str(note.get("subject", "(Untitled)"))
                    for note in self.note_presets_notes
                }
                for group in self.note_preset_groups:
                    name = str(group.get("name", "(Unnamed Group)"))
                    note_ids = [str(note_id).strip() for note_id in group.get("note_ids", []) if str(note_id).strip()]
                    note_subjects = [note_by_id.get(note_id, note_id) for note_id in note_ids]
                    searchable = f"{name} {' '.join(note_subjects)}".lower()
                    if group_search_text and group_search_text not in searchable:
                        continue
                    label = f"{name} ({len(note_ids)} notes)"
                    if bool(group.get("auto_add_new_projects", False)):
                        label += " [Auto]"
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, str(group.get("id", "")))
                    item.setToolTip("\n".join(note_subjects) or "(No notes)")
                    groups_list.addItem(item)

            def selected_note_ids() -> List[str]:
                ids: List[str] = []
                for item in notes_list.selectedItems():
                    note_id = str(item.data(Qt.UserRole)).strip()
                    if note_id and note_id not in ids:
                        ids.append(note_id)
                return ids

            def selected_group_ids() -> List[str]:
                ids: List[str] = []
                for item in groups_list.selectedItems():
                    group_id = str(item.data(Qt.UserRole)).strip()
                    if group_id and group_id not in ids:
                        ids.append(group_id)
                return ids

            def create_note_preset() -> None:
                created = self._show_note_preset_note_dialog()
                if not created:
                    return
                self.note_presets_notes.append(created)
                self._save_note_presets()
                refresh_lists()

            def edit_note_preset() -> None:
                note_ids = selected_note_ids()
                if len(note_ids) != 1:
                    self._error("Select one preset note to edit.")
                    return
                note_id = note_ids[0]
                for idx, note in enumerate(self.note_presets_notes):
                    if str(note.get("id", "")) != note_id:
                        continue
                    updated = self._show_note_preset_note_dialog(note)
                    if not updated:
                        return
                    self.note_presets_notes[idx] = updated
                    self._save_note_presets()
                    refresh_lists()
                    return
                self._error("Selected preset note could not be found.")

            def remove_note_preset() -> None:
                note_ids = selected_note_ids()
                if not note_ids:
                    self._error("Select at least one preset note to remove.")
                    return
                self.note_presets_notes = [
                    note for note in self.note_presets_notes if str(note.get("id", "")) not in note_ids
                ]
                valid_ids = {str(note.get("id", "")) for note in self.note_presets_notes}
                for group in self.note_preset_groups:
                    group["note_ids"] = [
                        str(note_id)
                        for note_id in group.get("note_ids", [])
                        if str(note_id) in valid_ids
                    ]
                self._save_note_presets()
                refresh_lists()

            def toggle_note_auto_add() -> None:
                note_ids = selected_note_ids()
                if not note_ids:
                    self._error("Select at least one preset note.")
                    return
                selected = [note for note in self.note_presets_notes if str(note.get("id", "")) in note_ids]
                if not selected:
                    return
                enable = not all(bool(note.get("auto_add_new_projects", False)) for note in selected)
                for note in self.note_presets_notes:
                    if str(note.get("id", "")) in note_ids:
                        note["auto_add_new_projects"] = enable
                self._save_note_presets()
                refresh_lists()

            def add_selected_notes_to_project() -> None:
                note_ids = selected_note_ids()
                if not note_ids:
                    self._error("Select at least one preset note.")
                    return
                self._add_preset_notes_to_current_project(note_ids)

            def create_note_group() -> None:
                created = self._show_note_preset_group_dialog()
                if not created:
                    return
                self.note_preset_groups.append(created)
                self._save_note_presets()
                refresh_lists()

            def edit_note_group() -> None:
                group_ids = selected_group_ids()
                if len(group_ids) != 1:
                    self._error("Select one note group to edit.")
                    return
                group_id = group_ids[0]
                for idx, group in enumerate(self.note_preset_groups):
                    if str(group.get("id", "")) != group_id:
                        continue
                    updated = self._show_note_preset_group_dialog(group)
                    if not updated:
                        return
                    self.note_preset_groups[idx] = updated
                    self._save_note_presets()
                    refresh_lists()
                    return
                self._error("Selected note group could not be found.")

            def remove_note_group() -> None:
                group_ids = selected_group_ids()
                if not group_ids:
                    self._error("Select at least one note group to remove.")
                    return
                self.note_preset_groups = [
                    group for group in self.note_preset_groups if str(group.get("id", "")) not in group_ids
                ]
                self._save_note_presets()
                refresh_lists()

            def toggle_group_auto_add() -> None:
                group_ids = selected_group_ids()
                if not group_ids:
                    self._error("Select at least one note group.")
                    return
                selected = [group for group in self.note_preset_groups if str(group.get("id", "")) in group_ids]
                if not selected:
                    return
                enable = not all(bool(group.get("auto_add_new_projects", False)) for group in selected)
                for group in self.note_preset_groups:
                    if str(group.get("id", "")) in group_ids:
                        group["auto_add_new_projects"] = enable
                self._save_note_presets()
                refresh_lists()

            def add_selected_groups_to_project() -> None:
                group_ids = selected_group_ids()
                if not group_ids:
                    self._error("Select at least one note group.")
                    return
                note_ids: List[str] = []
                for group in self.note_preset_groups:
                    if str(group.get("id", "")) not in group_ids:
                        continue
                    for note_id in group.get("note_ids", []):
                        value = str(note_id).strip()
                        if value and value not in note_ids:
                            note_ids.append(value)
                self._add_preset_notes_to_current_project(note_ids)

            def show_notes_context_menu(pos: QPoint) -> None:
                item = notes_list.itemAt(pos)
                if item is not None and not item.isSelected():
                    notes_list.clearSelection()
                    item.setSelected(True)
                    notes_list.setCurrentItem(item)
                menu = QMenu(dialog)
                add_action = menu.addAction("Add To Current Project")
                toggle_auto_action = menu.addAction("Toggle Auto-Add To New Projects")
                chosen = menu.exec(notes_list.mapToGlobal(pos))
                if chosen == add_action:
                    add_selected_notes_to_project()
                elif chosen == toggle_auto_action:
                    toggle_note_auto_add()

            def show_groups_context_menu(pos: QPoint) -> None:
                item = groups_list.itemAt(pos)
                if item is not None and not item.isSelected():
                    groups_list.clearSelection()
                    item.setSelected(True)
                    groups_list.setCurrentItem(item)
                menu = QMenu(dialog)
                add_action = menu.addAction("Add Group To Current Project")
                toggle_auto_action = menu.addAction("Toggle Auto-Add To New Projects")
                chosen = menu.exec(groups_list.mapToGlobal(pos))
                if chosen == add_action:
                    add_selected_groups_to_project()
                elif chosen == toggle_auto_action:
                    toggle_group_auto_add()

            notes_search.textChanged.connect(lambda _text: refresh_lists())
            groups_search.textChanged.connect(lambda _text: refresh_lists())
            notes_list.customContextMenuRequested.connect(show_notes_context_menu)
            groups_list.customContextMenuRequested.connect(show_groups_context_menu)
            new_note_btn.clicked.connect(create_note_preset)
            edit_note_btn.clicked.connect(edit_note_preset)
            remove_note_btn.clicked.connect(remove_note_preset)
            add_note_to_project_btn.clicked.connect(add_selected_notes_to_project)
            toggle_note_auto_btn.clicked.connect(toggle_note_auto_add)
            new_group_btn.clicked.connect(create_note_group)
            edit_group_btn.clicked.connect(edit_note_group)
            remove_group_btn.clicked.connect(remove_note_group)
            add_group_to_project_btn.clicked.connect(add_selected_groups_to_project)
            toggle_group_auto_btn.clicked.connect(toggle_group_auto_add)
            notes_list.itemDoubleClicked.connect(lambda _item: add_selected_notes_to_project())
            groups_list.itemDoubleClicked.connect(lambda _item: add_selected_groups_to_project())

            refresh_lists()
            dialog.exec()

        def _create_note(self) -> None:
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            note = self._show_note_dialog()
            if not note:
                return
            notes = self._current_project_notes()
            notes.append(note)
            logical_view = self._project_notes_logical_view()
            current_folder_id = self._current_logical_folder_id("project_notes")
            logical_view = self._set_logical_item_parent_folder_id(logical_view, str(note.get("id", "")).strip(), current_folder_id)
            self._save_project_notes_logical_view(logical_view)
            self._set_project_notes(notes)

        def _edit_note_item(self, item: QListWidgetItem) -> None:
            self.notes_list.setCurrentItem(item)
            if str(item.data(Qt.UserRole + 1)) == "folder":
                self._set_current_logical_folder_id("project_notes", str(item.data(Qt.UserRole)).strip())
                self._refresh_notes_list(self._current_project_notes())
                return
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
            logical_view = self._project_notes_logical_view()
            logical_view = self._set_logical_item_parent_folder_id(logical_view, note_id, "")
            self._save_project_notes_logical_view(logical_view)
            self._set_project_notes(notes)

        def _notes_from_ui_order(self) -> List[Dict[str, str]]:
            by_id = {str(note.get("id", "")): note for note in self._current_project_notes()}
            ordered_notes: List[Dict[str, str]] = []
            for row in range(self.notes_list.count()):
                item = self.notes_list.item(row)
                if str(item.data(Qt.UserRole + 1)) == "folder":
                    continue
                note_id = str(item.data(Qt.UserRole))
                note = by_id.get(note_id)
                if note:
                    ordered_notes.append(note)
            return ordered_notes

        def _move_selected_note(self, delta: int) -> None:
            logical_view = self._project_notes_logical_view()
            if logical_view.get("folders") or logical_view.get("placements"):
                self._error("Reordering project notes is not available while logical folders are in use.")
                return
            if not self._move_list_widget_item(self.notes_list, delta):
                return
            self._set_project_notes(self._notes_from_ui_order())

        def _move_selected_note_to(self, target_index: int) -> None:
            logical_view = self._project_notes_logical_view()
            if logical_view.get("folders") or logical_view.get("placements"):
                self._error("Reordering project notes is not available while logical folders are in use.")
                return
            if not self._move_list_widget_item_to(self.notes_list, target_index):
                return
            self._set_project_notes(self._notes_from_ui_order())

        def _go_up_project_notes_folder(self) -> None:
            view = self._project_notes_logical_view()
            current_folder_id = self._current_logical_folder_id("project_notes")
            if not current_folder_id:
                return
            folder = self._logical_view_folder_map(view).get(current_folder_id, {})
            self._set_current_logical_folder_id("project_notes", str(folder.get("parent_id", "")).strip())
            self._refresh_notes_list(self._current_project_notes())

        def _go_root_project_notes_folder(self) -> None:
            self._set_current_logical_folder_id("project_notes", "")
            self._refresh_notes_list(self._current_project_notes())

        def _create_project_notes_folder(self) -> None:
            name = self._prompt_for_project_notes_folder_name("New Notes Folder")
            if not name:
                return
            view = self._project_notes_logical_view()
            current_folder_id = self._current_logical_folder_id("project_notes")
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
            self._save_project_notes_logical_view(view)
            self._refresh_notes_list(self._current_project_notes())

        def _rename_project_notes_folder(self, folder_id: str) -> None:
            view = self._project_notes_logical_view()
            folder_map = self._logical_view_folder_map(view)
            folder = folder_map.get(folder_id.strip())
            if not folder:
                self._error("Selected folder could not be found.")
                return
            name = self._prompt_for_project_notes_folder_name(
                "Rename Notes Folder",
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
            self._save_project_notes_logical_view(view)
            self._refresh_notes_list(self._current_project_notes())

        def _delete_project_notes_folder(self, folder_id: str) -> None:
            confirm = QMessageBox.question(
                self,
                "Delete Notes Folder",
                "Delete this folder and its subfolders? Notes inside will return to the root list.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
            view = self._delete_logical_folder_tree(self._project_notes_logical_view(), folder_id)
            if self._current_logical_folder_id("project_notes") == folder_id.strip():
                self._set_current_logical_folder_id("project_notes", "")
            self._save_project_notes_logical_view(view)
            self._refresh_notes_list(self._current_project_notes())

        def _choose_project_notes_target_folder(self) -> Optional[str]:
            view = self._project_notes_logical_view()
            folders = [dict(folder) for folder in view.get("folders", [])]
            if not folders:
                self._error("Create a notes folder first.")
                return None
            dialog = QDialog(self)
            dialog.setWindowTitle("Move Notes To Folder")
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

        def _move_selected_notes_to_folder(self) -> None:
            selected_items = self.notes_list.selectedItems()
            if not selected_items:
                self._error("Select at least one note.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select notes only.")
                return
            target_folder_id = self._choose_project_notes_target_folder()
            if target_folder_id is None:
                return
            view = self._project_notes_logical_view()
            for item in selected_items:
                note_id = str(item.data(Qt.UserRole)).strip()
                if note_id:
                    view = self._set_logical_item_parent_folder_id(view, note_id, target_folder_id)
            self._save_project_notes_logical_view(view)
            self._refresh_notes_list(self._current_project_notes())

        def _move_selected_notes_to_root(self) -> None:
            selected_items = self.notes_list.selectedItems()
            if not selected_items:
                self._error("Select at least one note.")
                return
            if any(str(item.data(Qt.UserRole + 1)) == "folder" for item in selected_items):
                self._error("Select notes only.")
                return
            view = self._project_notes_logical_view()
            for item in selected_items:
                note_id = str(item.data(Qt.UserRole)).strip()
                if note_id:
                    view = self._set_logical_item_parent_folder_id(view, note_id, "")
            self._save_project_notes_logical_view(view)
            self._refresh_notes_list(self._current_project_notes())

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
                    [self._filter_presets_path(), app_module.LEGACY_FILTER_PRESETS_FILE]
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
                        "schema_version": app_module.FILTER_PRESETS_SCHEMA_VERSION,
                        "app_version": app_module.APP_VERSION,
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
            if hasattr(self, "_update_extension_filter_summary_label"):
                self._update_extension_filter_summary_label()

        def _on_filter_mode_changed(self) -> None:
            if hasattr(self, "_update_extension_filter_summary_label"):
                self._update_extension_filter_summary_label()
            self._save_current_project_filters(show_busy=True)

        def _on_extension_list_changed(self) -> None:
            if hasattr(self, "_update_extension_filter_summary_label"):
                self._update_extension_filter_summary_label()
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
            used_ids = {str(value).strip() for value in existing.values() if str(value).strip()}
            for source in sources:
                source_value = str(source).strip()
                if not source_value:
                    continue
                source_id = str(existing.get(source_value, "")).strip()
                if not source_id:
                    source_id = self._new_compact_id(used_ids)
                used_ids.add(source_id)
                normalized[source_value] = source_id
            return normalized

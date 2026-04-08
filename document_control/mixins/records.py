from __future__ import annotations

import app as app_module
from app import *


class RecordsMixin:
        def _new_record_id(self, existing_ids: set[str]) -> str:
            while True:
                candidate = f"r_{uuid4().hex[:12]}"
                if candidate not in existing_ids:
                    return candidate

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

        def _source_index_file(self, source_dir: Path) -> Path:
            return source_dir / app_module.SOURCE_INDEX_FILE

        def _new_file_id(self, existing_ids: set[str]) -> str:
            while True:
                candidate = f"f_{uuid4().hex[:12]}"
                if candidate not in existing_ids:
                    return candidate

        def _normalize_source_index_entry(
            self, source_dir: Path, entry: Dict[str, object], fallback_name: str = ""
        ) -> Dict[str, object]:
            file_id = str(entry.get("file_id", "")).strip()
            current_name = str(entry.get("current_name", "")).strip()
            canonical_name = str(entry.get("canonical_name", "")).strip()
            status = str(entry.get("status", "active") or "active").strip() or "active"
            if not canonical_name:
                canonical_name = current_name or fallback_name
            known_names_raw = entry.get("known_names", [])
            legacy_bound_names_raw = entry.get("legacy_bound_names", [])
            known_names = []
            if isinstance(known_names_raw, list):
                known_names = [
                    str(name).strip()
                    for name in known_names_raw
                    if str(name).strip()
                ]
            legacy_bound_names = []
            if isinstance(legacy_bound_names_raw, list):
                legacy_bound_names = [
                    str(name).strip()
                    for name in legacy_bound_names_raw
                    if str(name).strip()
                ]
            for candidate in (current_name, canonical_name, fallback_name):
                candidate = str(candidate).strip()
                if candidate and candidate not in known_names:
                    known_names.append(candidate)
            return {
                "file_id": file_id,
                "current_name": current_name,
                "canonical_name": canonical_name,
                "status": status,
                "known_names": known_names,
                "legacy_bound_names": legacy_bound_names,
                "checked_out_by": str(entry.get("checked_out_by", "")).strip(),
                "checked_out_at": str(entry.get("checked_out_at", "")).strip(),
                "created_at": str(entry.get("created_at", "")).strip(),
            }

        def _load_source_index(self, source_dir: Path) -> Dict[str, object]:
            index_file = self._source_index_file(source_dir)
            if not index_file.exists():
                return {
                    "schema_version": app_module.SOURCE_INDEX_SCHEMA_VERSION,
                    "app_version": app_module.APP_VERSION,
                    "files": {},
                }
            try:
                raw = json.loads(index_file.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                raw = {}
            files = raw.get("files", {}) if isinstance(raw, dict) else {}
            normalized: Dict[str, object] = {}
            if isinstance(files, dict):
                for key, value in files.items():
                    if not isinstance(value, dict):
                        continue
                    entry = self._normalize_source_index_entry(source_dir, value)
                    file_id = str(entry.get("file_id", "")).strip() or str(key).strip()
                    if not file_id:
                        continue
                    entry["file_id"] = file_id
                    normalized[file_id] = entry
            return {
                "schema_version": app_module.SOURCE_INDEX_SCHEMA_VERSION,
                "app_version": app_module.APP_VERSION,
                "files": normalized,
            }

        def _save_source_index(self, source_dir: Path, index: Dict[str, object]) -> None:
            index_file = self._source_index_file(source_dir)
            self._ensure_parent_dir(index_file)
            index_file.write_text(json.dumps(index, indent=2), encoding="utf-8")

        def _latest_history_by_name_raw(self, source_dir: Path) -> Dict[str, Dict[str, str]]:
            latest_by_name: Dict[str, Dict[str, str]] = {}
            for row in self._read_history_rows(source_dir):
                file_name = str(row.get("file_name", "")).strip()
                if file_name:
                    latest_by_name[file_name] = row
            return latest_by_name

        def _ensure_source_index(self, source_dir: Path) -> Dict[str, object]:
            index = self._load_source_index(source_dir)
            files = index.get("files", {})
            if not isinstance(files, dict):
                files = {}
                index["files"] = files

            existing_ids = {str(file_id).strip() for file_id in files.keys() if str(file_id).strip()}
            current_names = {entry.name for entry in self._cached_directory_files(source_dir)}
            latest_by_name = self._latest_history_by_name_raw(source_dir)
            latest_by_id = self._latest_history_by_file_id(source_dir)
            locked_aliases: Dict[str, Tuple[str, Dict[str, str]]] = {}
            for original_name, row in latest_by_name.items():
                if str(row.get("action", "")).strip() != "CHECK_OUT":
                    continue
                initials = str(row.get("user_initials", "")).strip()
                if not initials:
                    continue
                locked_name = self._locked_name_for(source_dir / original_name, initials).name
                locked_aliases[locked_name] = (original_name, row)
            changed = False

            active_by_name: Dict[str, str] = {}
            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                entry = self._normalize_source_index_entry(source_dir, raw_entry)
                original_entry = dict(entry)
                if not str(entry.get("file_id", "")).strip():
                    entry["file_id"] = str(file_id)
                latest_row = latest_by_id.get(str(entry["file_id"]))
                if latest_row:
                    latest_action = str(latest_row.get("action", "")).strip()
                    latest_name = str(latest_row.get("file_name", "")).strip()
                    known_names = [
                        str(name).strip()
                        for name in entry.get("known_names", [])
                        if str(name).strip()
                    ]
                    if latest_name and latest_name not in known_names:
                        known_names.append(latest_name)
                    previous_name = str(latest_row.get("previous_file_name", "")).strip()
                    if previous_name and previous_name not in known_names:
                        known_names.append(previous_name)
                    entry["known_names"] = known_names
                    if latest_action == "DELETE_FILE":
                        entry["current_name"] = ""
                        entry["status"] = "deleted"
                        entry["canonical_name"] = latest_name or str(entry.get("canonical_name", "")).strip()
                    elif latest_action == "CHECK_OUT":
                        initials = str(latest_row.get("user_initials", "")).strip()
                        canonical_name = latest_name or str(entry.get("canonical_name", "")).strip()
                        current_name = latest_name
                        if canonical_name and initials:
                            current_name = self._locked_name_for(source_dir / canonical_name, initials).name
                        entry["current_name"] = current_name
                        entry["canonical_name"] = canonical_name or current_name
                        entry["status"] = "checked_out"
                        entry["checked_out_by"] = initials
                        entry["checked_out_at"] = str(latest_row.get("timestamp", "")).strip()
                    else:
                        entry["current_name"] = latest_name or str(entry.get("current_name", "")).strip()
                        entry["canonical_name"] = latest_name or str(entry.get("canonical_name", "")).strip()
                        entry["status"] = "active"
                        if latest_action.startswith("CHECK_IN"):
                            entry["checked_out_by"] = ""
                            entry["checked_out_at"] = ""
                current_name = str(entry.get("current_name", "")).strip()
                if current_name and current_name in current_names:
                    active_by_name[current_name] = str(entry["file_id"])
                files[str(entry["file_id"])] = entry
                if entry != original_entry:
                    changed = True

            preferred_by_current_name: Dict[str, str] = {}
            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                current_name = str(raw_entry.get("current_name", "")).strip()
                if not current_name:
                    continue
                preferred = preferred_by_current_name.get(current_name, "")
                if not preferred:
                    preferred_by_current_name[current_name] = str(file_id)
                    continue
                preferred_has_history = preferred in latest_by_id
                candidate_has_history = str(file_id) in latest_by_id
                if candidate_has_history and not preferred_has_history:
                    preferred_by_current_name[current_name] = str(file_id)

            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                current_name = str(raw_entry.get("current_name", "")).strip()
                if not current_name:
                    continue
                preferred = preferred_by_current_name.get(current_name, "")
                if preferred and preferred != str(file_id):
                    entry = self._normalize_source_index_entry(source_dir, raw_entry)
                    entry["current_name"] = ""
                    entry["status"] = "deleted"
                    files[str(file_id)] = entry
                    changed = True

            active_by_name = {}
            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                current_name = str(raw_entry.get("current_name", "")).strip()
                if current_name and current_name in current_names:
                    active_by_name[current_name] = str(file_id)

            deleted_groups: Dict[str, List[str]] = {}
            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                if str(raw_entry.get("status", "")).strip() != "deleted":
                    continue
                canonical_name = str(raw_entry.get("canonical_name", "")).strip()
                if not canonical_name:
                    continue
                deleted_groups.setdefault(canonical_name, []).append(str(file_id))

            for canonical_name, group in deleted_groups.items():
                if len(group) <= 1:
                    continue
                preferred_deleted = ""
                for candidate in group:
                    if candidate in latest_by_id:
                        preferred_deleted = candidate
                        break
                if not preferred_deleted:
                    preferred_deleted = group[0]
                for candidate in group:
                    if candidate == preferred_deleted:
                        continue
                    files.pop(candidate, None)
                    changed = True

            active_by_canonical_name: Dict[str, str] = {}
            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                if str(raw_entry.get("status", "")).strip() == "deleted":
                    continue
                canonical_name = str(raw_entry.get("canonical_name", "")).strip()
                if canonical_name:
                    active_by_canonical_name[canonical_name] = str(file_id)

            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                if str(raw_entry.get("status", "")).strip() != "deleted":
                    continue
                canonical_name = str(raw_entry.get("canonical_name", "")).strip()
                if not canonical_name or canonical_name not in active_by_canonical_name:
                    continue
                if str(file_id) in latest_by_id:
                    continue
                files.pop(str(file_id), None)
                changed = True

            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                entry = self._normalize_source_index_entry(source_dir, raw_entry)
                names_to_check = [
                    str(entry.get("current_name", "")).strip(),
                    str(entry.get("canonical_name", "")).strip(),
                ]
                names_to_check.extend(
                    str(name).strip()
                    for name in entry.get("known_names", [])
                    if str(name).strip()
                )
                if not names_to_check:
                    continue
                if any(self._is_source_file_name_candidate(name) for name in names_to_check):
                    continue
                files.pop(str(file_id), None)
                changed = True

            for current_name in sorted(current_names, key=str.lower):
                if current_name in active_by_name:
                    continue
                latest_row = latest_by_name.get(current_name)
                canonical_name = current_name
                status = "active"
                checked_out_by = ""
                checked_out_at = ""
                if current_name in locked_aliases:
                    canonical_name, latest_row = locked_aliases[current_name]
                    status = "checked_out"
                    checked_out_by = str(latest_row.get("user_initials", "")).strip()
                    checked_out_at = str(latest_row.get("timestamp", "")).strip()
                elif latest_row and str(latest_row.get("action", "")).strip() == "CHECK_OUT":
                    canonical_name = current_name
                    status = "checked_out"
                    checked_out_by = str(latest_row.get("user_initials", "")).strip()
                    checked_out_at = str(latest_row.get("timestamp", "")).strip()

                file_id = self._new_file_id(existing_ids)
                existing_ids.add(file_id)
                entry = self._normalize_source_index_entry(
                    source_dir,
                    {
                        "file_id": file_id,
                        "current_name": current_name,
                        "canonical_name": canonical_name,
                        "status": status,
                        "known_names": [current_name, canonical_name],
                        "legacy_bound_names": [],
                        "checked_out_by": checked_out_by,
                        "checked_out_at": checked_out_at,
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    },
                )
                files[file_id] = entry
                active_by_name[current_name] = file_id
                changed = True

                latest_row = latest_by_name.get(canonical_name)
                latest_action = str(latest_row.get("action", "")).strip() if latest_row else ""
                if latest_row and latest_action not in {"DELETE_FILE"}:
                    if not str(latest_row.get("file_id", "")).strip():
                        bound_names = [
                            str(name).strip()
                            for name in entry.get("legacy_bound_names", [])
                            if str(name).strip()
                        ]
                        if canonical_name not in bound_names:
                            bound_names.append(canonical_name)
                            entry["legacy_bound_names"] = bound_names
                            files[file_id] = entry
                            changed = True
                        latest_by_name = self._latest_history_by_name_raw(source_dir)

            for file_id, raw_entry in list(files.items()):
                if not isinstance(raw_entry, dict):
                    continue
                entry = self._normalize_source_index_entry(source_dir, raw_entry)
                current_name = str(entry.get("current_name", "")).strip()
                if current_name and current_name not in current_names and str(entry.get("status", "")) != "deleted":
                    entry["current_name"] = ""
                    entry["status"] = "deleted"
                    files[file_id] = entry
                    changed = True

            rename_names_backfilled = self._backfill_rename_previous_names_unambiguous(source_dir)
            history_backfilled = self._backfill_history_file_ids_unambiguous(source_dir, index)
            notes_backfilled = self._backfill_note_file_ids_unambiguous(source_dir, index)
            if rename_names_backfilled or history_backfilled or notes_backfilled:
                changed = True

            if changed:
                self._save_source_index(source_dir, index)
            return index

        def _source_index_entry_for_file_id(
            self, source_dir: Path, file_id: str
        ) -> Optional[Dict[str, object]]:
            file_id = file_id.strip()
            if not file_id:
                return None
            index = self._ensure_source_index(source_dir)
            files = index.get("files", {})
            if not isinstance(files, dict):
                return None
            entry = files.get(file_id)
            if isinstance(entry, dict):
                return entry
            return None

        def _source_index_entry_for_current_name(
            self, source_dir: Path, current_name: str
        ) -> Optional[Dict[str, object]]:
            index = self._ensure_source_index(source_dir)
            files = index.get("files", {})
            if not isinstance(files, dict):
                return None
            normalized_name = current_name.strip()
            for entry in files.values():
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("current_name", "")).strip() == normalized_name:
                    return entry
            return None

        def _history_json_file(self, source_dir: Path) -> Path:
            return source_dir / app_module.HISTORY_FILE_NAME

        def _history_legacy_csv_file(self, source_dir: Path) -> Path:
            return source_dir / app_module.LEGACY_HISTORY_FILE_NAME

        def _normalize_history_row(self, row: Dict[str, str]) -> Dict[str, str]:
            file_id = str(row.get("file_id", "")).strip()
            revision_id = str(row.get("revision_id", "")).strip()
            initials = str(row.get("user_initials", "")).strip()
            full_name = str(row.get("user_full_name", "")).strip()
            previous_file_name = str(row.get("previous_file_name", "")).strip()
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
                "previous_file_name": previous_file_name,
                "file_id": file_id,
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
            self,
            source_dir: Path,
            action: str,
            file_name: str,
            revision_id: str = "",
            file_id: str = "",
            previous_file_name: str = "",
        ) -> None:
            rows = self._read_history_rows(source_dir)
            rows.append(
                {
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "action": action,
                    "file_name": file_name,
                    "previous_file_name": previous_file_name,
                    "file_id": file_id,
                    "revision_id": revision_id,
                    "user_initials": self._normalize_initials(),
                    "user_full_name": self._current_full_name(),
                }
            )
            self._write_history_rows_json(source_dir, rows)
            self._invalidate_directory_caches(source_dir)

        def _bind_history_name_to_file_id(self, source_dir: Path, file_name: str, file_id: str) -> None:
            rows = self._read_history_rows(source_dir)
            updated = False
            for row in rows:
                if (
                    str(row.get("file_name", "")).strip() == file_name
                    and not str(row.get("file_id", "")).strip()
                ):
                    row["file_id"] = file_id
                    updated = True
            if updated:
                self._write_history_rows_json(source_dir, rows)
                self._invalidate_directory_caches(source_dir)

        def _candidate_file_ids_for_name(
            self,
            source_dir: Path,
            file_name: str,
            index: Optional[Dict[str, object]] = None,
        ) -> List[str]:
            normalized_name = file_name.strip()
            if not normalized_name:
                return []
            index = index or self._ensure_source_index(source_dir)
            files = index.get("files", {})
            if not isinstance(files, dict):
                return []

            def unique(values: List[str]) -> List[str]:
                seen: set[str] = set()
                ordered: List[str] = []
                for value in values:
                    if not value or value in seen:
                        continue
                    seen.add(value)
                    ordered.append(value)
                return ordered

            rows = self._read_history_rows(source_dir)
            history_same_name = unique(
                [
                    str(row.get("file_id", "")).strip()
                    for row in rows
                    if str(row.get("file_name", "")).strip() == normalized_name
                    and str(row.get("file_id", "")).strip()
                ]
            )
            history_previous_name = unique(
                [
                    str(row.get("file_id", "")).strip()
                    for row in rows
                    if str(row.get("previous_file_name", "")).strip() == normalized_name
                    and str(row.get("file_id", "")).strip()
                ]
            )
            current_matches = unique(
                [
                    str(file_id).strip()
                    for file_id, entry in files.items()
                    if isinstance(entry, dict)
                    and str(entry.get("current_name", "")).strip() == normalized_name
                ]
            )
            canonical_matches = unique(
                [
                    str(file_id).strip()
                    for file_id, entry in files.items()
                    if isinstance(entry, dict)
                    and str(entry.get("canonical_name", "")).strip() == normalized_name
                ]
            )
            legacy_matches = unique(
                [
                    str(file_id).strip()
                    for file_id, entry in files.items()
                    if isinstance(entry, dict)
                    and normalized_name in [
                        str(name).strip()
                        for name in entry.get("legacy_bound_names", [])
                        if str(name).strip()
                    ]
                ]
            )
            known_matches = unique(
                [
                    str(file_id).strip()
                    for file_id, entry in files.items()
                    if isinstance(entry, dict)
                    and normalized_name in [
                        str(name).strip()
                        for name in entry.get("known_names", [])
                        if str(name).strip()
                    ]
                ]
            )

            for group in (
                history_same_name,
                history_previous_name,
                current_matches,
                canonical_matches,
                legacy_matches,
                known_matches,
            ):
                if len(group) == 1:
                    return group

            combined = unique(
                history_same_name
                + history_previous_name
                + current_matches
                + canonical_matches
                + legacy_matches
                + known_matches
            )
            if len(combined) == 1:
                return combined
            return []

        def _resolve_history_row_file_id(
            self, source_dir: Path, row: Dict[str, str], index: Optional[Dict[str, object]] = None
        ) -> str:
            file_id = str(row.get("file_id", "")).strip()
            if file_id:
                return file_id
            file_name = str(row.get("file_name", "")).strip()
            if not file_name:
                return ""
            candidates = self._candidate_file_ids_for_name(source_dir, file_name, index)
            if len(candidates) == 1:
                return candidates[0]
            previous_file_name = str(row.get("previous_file_name", "")).strip()
            if previous_file_name:
                candidates = self._candidate_file_ids_for_name(source_dir, previous_file_name, index)
                if len(candidates) == 1:
                    return candidates[0]
            return ""

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

        def _latest_history_by_file_id(self, source_dir: Path) -> Dict[str, Dict[str, str]]:
            latest_by_id: Dict[str, Dict[str, str]] = {}
            for row in self._read_history_rows(source_dir):
                file_id = str(row.get("file_id", "")).strip()
                if file_id:
                    latest_by_id[file_id] = row
            return latest_by_id

        def _history_lookup_for_directory(self, source_dir: Path) -> Dict[str, Dict[str, str]]:
            lookup: Dict[str, Dict[str, str]] = {}
            index = self._ensure_source_index(source_dir)
            files = index.get("files", {})
            latest_by_id: Dict[str, Dict[str, str]] = {}
            for row in self._read_history_rows(source_dir):
                file_id = self._resolve_history_row_file_id(source_dir, row, index)
                if file_id:
                    latest_by_id[file_id] = row
            if not isinstance(files, dict):
                return lookup
            for file_id, entry in files.items():
                if not isinstance(entry, dict):
                    continue
                current_name = str(entry.get("current_name", "")).strip()
                if not current_name:
                    continue
                latest_row = latest_by_id.get(str(file_id))
                if not isinstance(latest_row, dict) or not str(latest_row.get("action", "")).strip():
                    continue
                mapped_row = dict(latest_row)
                mapped_row["file_id"] = str(file_id)
                mapped_row["original_file_name"] = str(
                    entry.get("canonical_name", current_name) or current_name
                )
                lookup[current_name] = mapped_row
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

        def _history_rows_for_file_id(self, source_dir: Path, file_id: str) -> List[List[str]]:
            rows: List[List[str]] = []
            index = self._ensure_source_index(source_dir)
            for row in self._read_history_rows(source_dir):
                resolved_file_id = self._resolve_history_row_file_id(source_dir, row, index)
                if resolved_file_id != file_id:
                    continue
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

        def _history_rows_for_file_name_legacy(self, source_dir: Path, file_name: str) -> List[List[str]]:
            rows: List[List[str]] = []
            for row in self._read_history_rows(source_dir):
                if str(row.get("file_name", "")).strip() != file_name:
                    continue
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
                        "file_id": str(entry.get("file_id", "")).strip(),
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

        def _rename_directory_note_entries(self, source_dir: Path, old_name: str, new_name: str) -> None:
            notes = self._read_directory_notes(source_dir)
            updated = False
            for note in notes:
                if str(note.get("file_name", "")).strip() == old_name:
                    note["file_name"] = new_name
                    updated = True
            if updated:
                self._write_directory_notes(source_dir, notes)

        def _remove_directory_note_entries(self, source_dir: Path, file_names: List[str]) -> None:
            names = {name.strip() for name in file_names if name.strip()}
            if not names:
                return
            notes = self._read_directory_notes(source_dir)
            filtered = [note for note in notes if str(note.get("file_name", "")).strip() not in names]
            if len(filtered) != len(notes):
                self._write_directory_notes(source_dir, filtered)

        def _bind_notes_name_to_file_id(self, source_dir: Path, file_name: str, file_id: str) -> None:
            notes = self._read_directory_notes(source_dir)
            updated = False
            for note in notes:
                if (
                    str(note.get("file_name", "")).strip() == file_name
                    and not str(note.get("file_id", "")).strip()
                ):
                    note["file_id"] = file_id
                    updated = True
            if updated:
                self._write_directory_notes(source_dir, notes)

        def _backfill_history_file_ids_unambiguous(
            self, source_dir: Path, index: Optional[Dict[str, object]] = None
        ) -> bool:
            rows = self._read_history_rows(source_dir)
            updated = False
            for row in rows:
                if str(row.get("file_id", "")).strip():
                    continue
                resolved_file_id = self._resolve_history_row_file_id(source_dir, row, index)
                if not resolved_file_id:
                    continue
                row["file_id"] = resolved_file_id
                updated = True
            if updated:
                self._write_history_rows_json(source_dir, rows)
                self._invalidate_directory_caches(source_dir)
            return updated

        def _backfill_rename_previous_names_unambiguous(self, source_dir: Path) -> bool:
            rows = self._read_history_rows(source_dir)
            last_name_by_file_id: Dict[str, str] = {}
            updated = False
            for row in rows:
                file_id = str(row.get("file_id", "")).strip()
                file_name = str(row.get("file_name", "")).strip()
                if not file_id or not file_name:
                    continue
                action = str(row.get("action", "")).strip()
                if action == "RENAME" and not str(row.get("previous_file_name", "")).strip():
                    previous_name = last_name_by_file_id.get(file_id, "").strip()
                    if previous_name and previous_name != file_name:
                        row["previous_file_name"] = previous_name
                        updated = True
                last_name_by_file_id[file_id] = file_name
            if updated:
                self._write_history_rows_json(source_dir, rows)
                self._invalidate_directory_caches(source_dir)
            return updated

        def _backfill_note_file_ids_unambiguous(
            self, source_dir: Path, index: Optional[Dict[str, object]] = None
        ) -> bool:
            notes = self._read_directory_notes(source_dir)
            if not notes:
                return False
            index = index or self._ensure_source_index(source_dir)
            files = index.get("files", {})
            valid_file_ids = set(files.keys()) if isinstance(files, dict) else set()
            updated = False
            for note in notes:
                current_file_id = str(note.get("file_id", "")).strip()
                file_name = str(note.get("file_name", "")).strip()
                if current_file_id and current_file_id in valid_file_ids:
                    continue
                candidates = self._candidate_file_ids_for_name(source_dir, file_name, index)
                if len(candidates) != 1:
                    continue
                resolved_file_id = candidates[0]
                if current_file_id != resolved_file_id:
                    note["file_id"] = resolved_file_id
                    updated = True
            if updated:
                self._write_directory_notes(source_dir, notes)
            return updated

        def _sync_note_file_name(self, source_dir: Path, file_id: str, file_name: str) -> None:
            notes = self._read_directory_notes(source_dir)
            updated = False
            for note in notes:
                if str(note.get("file_id", "")).strip() == file_id and str(note.get("file_name", "")).strip() != file_name:
                    note["file_name"] = file_name
                    updated = True
            if updated:
                self._write_directory_notes(source_dir, notes)

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
            index = self._ensure_source_index(self.current_directory)
            notes_changed = False
            for note in notes:
                file_id = str(note.get("file_id", "")).strip()
                if not file_id:
                    file_id = self._resolve_history_row_file_id(
                        self.current_directory,
                        {"file_name": str(note.get("file_name", "")).strip(), "file_id": ""},
                        index,
                    )
                    if file_id:
                        note["file_id"] = file_id
                        notes_changed = True
                if not file_id:
                    continue
                by_file.setdefault(file_id, []).append(note)
            if notes_changed:
                self._write_directory_notes(self.current_directory, notes)
            for file_id in sorted(
                by_file.keys(),
                key=lambda current_file_id: str(
                    (
                        self._source_index_entry_for_file_id(self.current_directory, current_file_id) or {}
                    ).get("canonical_name", current_file_id)
                ).lower(),
            ):
                file_notes = by_file[file_id]
                latest = max(file_notes, key=lambda item: item.get("updated_at", ""))
                entry = self._source_index_entry_for_file_id(self.current_directory, file_id)
                file_name = ""
                if entry:
                    file_name = str(entry.get("canonical_name", "")).strip()
                if not file_name:
                    file_name = str(latest.get("file_name", "")).strip()
                row_idx = self.directory_notes_table.rowCount()
                self.directory_notes_table.insertRow(row_idx)
                file_item = QTableWidgetItem(file_name)
                file_item.setData(Qt.UserRole, file_id)
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
            selected = self._selected_source_file_items()
            if selected:
                file_id = str(selected[0].data(Qt.UserRole + 2) or "").strip()
                if not file_id:
                    path = Path(str(selected[0].data(Qt.UserRole)))
                    entry = self._source_index_entry_for_current_name(path.parent, path.name)
                    if entry:
                        file_id = str(entry.get("file_id", "")).strip()
                self._open_file_notes_window(file_id)
                return
            controlled_rows = self.controlled_files_table.selectionModel().selectedRows()
            if controlled_rows:
                item = self.controlled_files_table.item(controlled_rows[0].row(), 0)
                if item:
                    entry = item.data(Qt.UserRole)
                    if isinstance(entry, dict):
                        self._open_file_notes_window(str(entry.get("file_id", "")))
                        return
            rows = self.directory_notes_table.selectionModel().selectedRows()
            if rows:
                item = self.directory_notes_table.item(rows[0].row(), 0)
                if item:
                    self._open_file_notes_window(str(item.data(Qt.UserRole) or ""))
                    return
            self._error("Select a file first.")

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

        def _open_file_notes_window(self, file_id: str) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return
            file_id = file_id.strip()
            if not file_id:
                self._error("Select a file first.")
                return
            entry = self._source_index_entry_for_file_id(current_directory, file_id)
            file_name = (
                str(entry.get("canonical_name", "")).strip()
                if entry
                else ""
            ) or file_id
            notes = self._read_directory_notes(current_directory)
            notes_changed = False
            for note in notes:
                if str(note.get("file_id", "")).strip():
                    continue
                resolved_file_id = self._resolve_history_row_file_id(
                    current_directory,
                    {"file_name": str(note.get("file_name", "")).strip(), "file_id": ""},
                )
                if resolved_file_id:
                    note["file_id"] = resolved_file_id
                    notes_changed = True
            if notes_changed:
                self._write_directory_notes(current_directory, notes)
            file_notes = [note for note in notes if str(note.get("file_id", "")).strip() == file_id]

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
                    "file_id": file_id,
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
                all_notes = [note for note in notes if str(note.get("file_id", "")).strip() != file_id] + file_notes
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
                all_notes = [note for note in notes if str(note.get("file_id", "")).strip() != file_id] + file_notes
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
                all_notes = [note for note in notes if str(note.get("file_id", "")).strip() != file_id] + file_notes
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

            action = str(latest_row.get("action", "")).strip()
            if not action:
                return
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
            active_entries: List[Dict[str, str]] = []
            index = self._ensure_source_index(source_dir)
            files = index.get("files", {})
            latest_by_id = self._latest_history_by_file_id(source_dir)
            if not isinstance(files, dict):
                return active_entries
            for file_id, entry in files.items():
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("status", "")).strip() != "checked_out":
                    continue
                file_name = str(entry.get("canonical_name", "")).strip()
                locked_name = str(entry.get("current_name", "")).strip()
                if not file_name or not locked_name:
                    continue
                latest_row = latest_by_id.get(str(file_id), {})
                active_entries.append(
                    {
                        "file_name": file_name,
                        "file_id": str(file_id),
                        "initials": str(entry.get("checked_out_by", "")).strip(),
                        "full_name": str(latest_row.get("user_full_name", "")).strip(),
                        "locked_source_file": str(source_dir / locked_name),
                        "checked_out_at": str(entry.get("checked_out_at", "")).strip(),
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
                        file_entry = self._source_index_entry_for_current_name(
                            current_directory, source_file.name
                        )
                        file_id = (
                            str(file_entry.get("file_id", "")).strip()
                            if file_entry
                            else ""
                        )
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
                                file_id=file_id,
                            )
                            self.records.append(new_record)
                            self._create_revision_snapshot_for_record(
                                new_record,
                                note="Baseline snapshot captured at checkout.",
                                origin="checkout_baseline",
                            )
                            index = self._ensure_source_index(source_file.parent)
                            files = index.get("files", {})
                            if isinstance(files, dict) and file_id and isinstance(files.get(file_id), dict):
                                entry = dict(files[file_id])  # type: ignore[index]
                                known_names = [
                                    str(name).strip()
                                    for name in entry.get("known_names", [])
                                    if str(name).strip()
                                ]
                                for candidate in (source_file.name, locked_source_file.name):
                                    if candidate not in known_names:
                                        known_names.append(candidate)
                                entry["file_id"] = file_id
                                entry["current_name"] = locked_source_file.name
                                entry["canonical_name"] = source_file.name
                                entry["status"] = "checked_out"
                                entry["checked_out_by"] = initials
                                entry["checked_out_at"] = checked_out_at
                                entry["known_names"] = known_names
                                files[file_id] = entry
                                self._save_source_index(source_file.parent, index)
                            new_record.file_id = file_id
                            self._append_history(
                                source_file.parent,
                                "CHECK_OUT",
                                source_file.name,
                                file_id=file_id,
                            )
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

        def _legacy_record_version_key(self, record: CheckoutRecord) -> str:
            key_source = "|".join([record.project_dir, record.source_file, record.locked_source_file])
            return hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]

        def _record_version_key(self, record: CheckoutRecord) -> str:
            if record.file_id:
                return record.file_id
            return self._legacy_record_version_key(record)

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

        def _file_fingerprint(self, file_path: Path) -> Dict[str, object]:
            stat_result = file_path.stat()
            return {
                "hash": self._compute_file_sha256(file_path),
                "mtime": float(stat_result.st_mtime),
                "size": int(stat_result.st_size),
            }

        def _apply_reference_copy_baseline(
            self,
            record: CheckoutRecord,
            *,
            source_path: Path,
            local_path: Path,
            copied_at: str,
        ) -> None:
            source_fingerprint = self._file_fingerprint(source_path)
            local_fingerprint = self._file_fingerprint(local_path)
            record.source_hash_at_copy = str(source_fingerprint.get("hash", ""))
            record.local_hash_at_copy = str(local_fingerprint.get("hash", ""))
            record.source_mtime_at_copy = float(source_fingerprint.get("mtime", 0.0) or 0.0)
            record.local_mtime_at_copy = float(local_fingerprint.get("mtime", 0.0) or 0.0)
            record.source_size_at_copy = int(source_fingerprint.get("size", 0) or 0)
            record.local_size_at_copy = int(local_fingerprint.get("size", 0) or 0)
            record.last_refreshed_at = copied_at

        def _coerce_float(self, value: object, default: float = 0.0) -> float:
            try:
                return float(value or default)
            except (TypeError, ValueError):
                return default

        def _coerce_int(self, value: object, default: int = 0) -> int:
            try:
                return int(value or default)
            except (TypeError, ValueError):
                return default

        def _reference_default_action_for_status(self, status: str) -> str:
            return {
                "up_to_date": "none",
                "source_changed_safe": "replace",
                "local_changed_only": "keep",
                "both_changed_conflict": "skip",
                "source_missing": "skip",
                "local_missing": "skip",
                "untracked_state": "skip",
            }.get(status, "skip")

        def _reference_status_label(self, status: str) -> str:
            return {
                "up_to_date": "Up To Date",
                "source_changed_safe": "Source Changed, Safe To Replace",
                "local_changed_only": "Local Changed Only",
                "both_changed_conflict": "Conflict: Source And Local Changed",
                "source_missing": "Source Missing",
                "local_missing": "Local Copy Missing",
                "untracked_state": "Legacy Reference State",
            }.get(status, status.replace("_", " ").title())

        def _reference_action_label(self, action: str) -> str:
            return {
                "none": "No Action",
                "replace": "Replace",
                "keep": "Keep Local",
                "skip": "Skip",
            }.get(action, action.replace("_", " ").title())

        def _reference_baseline_is_tracked(self, record: CheckoutRecord) -> bool:
            return bool(
                record.source_hash_at_copy
                and record.local_hash_at_copy
                and record.source_size_at_copy >= 0
                and record.local_size_at_copy >= 0
            )

        def _current_reference_file_fingerprint(self, file_path: Path) -> Dict[str, object]:
            if not file_path.exists() or not file_path.is_file():
                return {
                    "exists": False,
                    "hash": "",
                    "mtime": 0.0,
                    "size": 0,
                }
            fingerprint = self._file_fingerprint(file_path)
            return {
                "exists": True,
                "hash": str(fingerprint.get("hash", "")),
                "mtime": float(fingerprint.get("mtime", 0.0) or 0.0),
                "size": int(fingerprint.get("size", 0) or 0),
            }

        def _reference_fingerprint_changed(
            self,
            current: Dict[str, object],
            *,
            baseline_hash: str,
            baseline_mtime: float,
            baseline_size: int,
        ) -> bool:
            if not bool(current.get("exists")):
                return True
            current_hash = str(current.get("hash", "")).strip()
            if baseline_hash and current_hash:
                return current_hash != baseline_hash
            return (
                self._coerce_int(current.get("size", 0)) != baseline_size
                or self._coerce_float(current.get("mtime", 0.0)) != baseline_mtime
            )

        def _reference_status_for_record(self, record: CheckoutRecord) -> Dict[str, object]:
            source_fingerprint = self._current_reference_file_fingerprint(Path(record.source_file))
            local_fingerprint = self._current_reference_file_fingerprint(Path(record.local_file))
            source_exists = bool(source_fingerprint.get("exists"))
            local_exists = bool(local_fingerprint.get("exists"))

            if not self._reference_baseline_is_tracked(record):
                status = "untracked_state"
                details = "This reference predates baseline tracking and cannot be classified safely."
                return {
                    "status": status,
                    "default_action": self._reference_default_action_for_status(status),
                    "source_exists": source_exists,
                    "local_exists": local_exists,
                    "source_changed": False,
                    "local_changed": False,
                    "details": details,
                }

            if not source_exists:
                status = "source_missing"
                details = "The tracked source file could not be found."
                return {
                    "status": status,
                    "default_action": self._reference_default_action_for_status(status),
                    "source_exists": source_exists,
                    "local_exists": local_exists,
                    "source_changed": False,
                    "local_changed": False,
                    "details": details,
                }

            if not local_exists:
                status = "local_missing"
                details = "The local reference copy could not be found."
                return {
                    "status": status,
                    "default_action": self._reference_default_action_for_status(status),
                    "source_exists": source_exists,
                    "local_exists": local_exists,
                    "source_changed": False,
                    "local_changed": False,
                    "details": details,
                }

            source_changed = self._reference_fingerprint_changed(
                source_fingerprint,
                baseline_hash=record.source_hash_at_copy,
                baseline_mtime=record.source_mtime_at_copy,
                baseline_size=record.source_size_at_copy,
            )
            local_changed = self._reference_fingerprint_changed(
                local_fingerprint,
                baseline_hash=record.local_hash_at_copy,
                baseline_mtime=record.local_mtime_at_copy,
                baseline_size=record.local_size_at_copy,
            )

            if source_changed and local_changed:
                status = "both_changed_conflict"
                details = "Both the source and the local reference changed since the last baseline."
            elif source_changed:
                status = "source_changed_safe"
                details = "The source changed since the last baseline and the local reference is unchanged."
            elif local_changed:
                status = "local_changed_only"
                details = "The local reference changed since the last baseline while the source is unchanged."
            else:
                status = "up_to_date"
                details = "The source and local reference still match the last baseline."

            return {
                "status": status,
                "default_action": self._reference_default_action_for_status(status),
                "source_exists": source_exists,
                "local_exists": local_exists,
                "source_changed": source_changed,
                "local_changed": local_changed,
                "details": details,
            }

        def _current_project_reference_status_rows(self) -> List[Dict[str, object]]:
            current_project = str(self.current_project_dir or "").strip()
            rows: List[Dict[str, object]] = []
            for record in self.records:
                if record.record_type != "reference_copy":
                    continue
                if current_project and str(record.project_dir) != current_project:
                    continue
                rows.append(
                    {
                        "record": record,
                        "record_id": record.id,
                        "status": self._reference_status_for_record(record),
                    }
                )
            return rows

        def _current_project_reference_update_plan_rows(self) -> List[Dict[str, object]]:
            rows: List[Dict[str, object]] = []
            for row in self._current_project_reference_status_rows():
                status = row.get("status", {})
                if not isinstance(status, dict):
                    continue
                plan_row = dict(row)
                plan_row["action"] = str(status.get("default_action", "skip"))
                rows.append(plan_row)
            return rows

        def _apply_reference_action_to_remaining(
            self,
            plan_rows: List[Dict[str, object]],
            start_index: int,
            action: str,
            *,
            same_status_only: bool = False,
        ) -> None:
            if start_index < 0 or start_index >= len(plan_rows):
                return
            target_status = ""
            current_status = plan_rows[start_index].get("status", {})
            if isinstance(current_status, dict):
                target_status = str(current_status.get("status", "")).strip()
            for row_idx in range(start_index, len(plan_rows)):
                if same_status_only:
                    row_status = plan_rows[row_idx].get("status", {})
                    row_status_name = (
                        str(row_status.get("status", "")).strip()
                        if isinstance(row_status, dict)
                        else ""
                    )
                    if row_status_name != target_status:
                        continue
                plan_rows[row_idx]["action"] = action

        def _execute_reference_update_plan(self, plan_rows: List[Dict[str, object]]) -> Dict[str, object]:
            updated = 0
            kept = 0
            skipped = 0
            failed: List[str] = []

            for row in plan_rows:
                action = str(row.get("action", "skip")).strip().lower()
                record = row.get("record")
                if not isinstance(record, CheckoutRecord):
                    continue

                if action == "replace":
                    success, message = self._refresh_reference_record(record, only_if_unchanged=False)
                    if success:
                        updated += 1
                    else:
                        label = Path(record.local_file).name or Path(record.source_file).name or record.id
                        if message == "Already up to date." or message.startswith("Skipped"):
                            skipped += 1
                        else:
                            failed.append(f"{label}: {message}")
                elif action == "keep":
                    kept += 1
                else:
                    skipped += 1

            self._save_records()
            self._render_records_tables()
            return {
                "updated": updated,
                "kept": kept,
                "skipped": skipped,
                "failed": failed,
            }

        def _show_update_all_references_dialog(self, plan_rows: List[Dict[str, object]]) -> bool:
            dialog = QDialog(self)
            dialog.setWindowTitle("Update All References")
            dialog.resize(1080, 460)
            layout = QVBoxLayout(dialog)

            table = QTableWidget(len(plan_rows), 5)
            table.setHorizontalHeaderLabels(["Reference File", "Source File", "Status", "Action", "Details"])
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.SingleSelection)

            action_widgets: List[QComboBox] = []
            action_options = [
                ("No Action", "none"),
                ("Replace", "replace"),
                ("Keep Local", "keep"),
                ("Skip", "skip"),
            ]
            for row_idx, row in enumerate(plan_rows):
                record = row.get("record")
                status = row.get("status", {})
                if not isinstance(record, CheckoutRecord) or not isinstance(status, dict):
                    continue
                values = [
                    Path(record.local_file).name,
                    Path(record.source_file).name,
                    self._reference_status_label(str(status.get("status", ""))),
                    "",
                    str(status.get("details", "")),
                ]
                tooltips = [
                    record.local_file,
                    record.source_file,
                    self._reference_status_label(str(status.get("status", ""))),
                    "",
                    str(status.get("details", "")),
                ]
                for col_idx, value in enumerate(values):
                    if col_idx == 3:
                        continue
                    item = QTableWidgetItem(value)
                    item.setToolTip(tooltips[col_idx])
                    table.setItem(row_idx, col_idx, item)
                combo = QComboBox()
                for label, stored_value in action_options:
                    combo.addItem(label, stored_value)
                selected_action = str(row.get("action", "skip")).strip().lower()
                selected_idx = next(
                    (idx for idx, (_label, stored_value) in enumerate(action_options) if stored_value == selected_action),
                    3,
                )
                combo.setCurrentIndex(selected_idx)
                combo.currentIndexChanged.connect(
                    lambda _idx, target_row=row_idx, widget=combo: plan_rows.__setitem__(
                        target_row,
                        dict(plan_rows[target_row], action=str(widget.currentData() or "skip")),
                    )
                )
                table.setCellWidget(row_idx, 3, combo)
                action_widgets.append(combo)

            table.resizeColumnsToContents()
            table.setColumnWidth(0, max(table.columnWidth(0), 180))
            table.setColumnWidth(1, max(table.columnWidth(1), 220))
            table.setColumnWidth(2, max(table.columnWidth(2), 150))
            table.setColumnWidth(3, max(table.columnWidth(3), 120))
            table.setColumnWidth(4, max(table.columnWidth(4), 320))
            layout.addWidget(table)

            buttons = QDialogButtonBox()
            replace_safe_btn = buttons.addButton("Replace All Safe", QDialogButtonBox.ActionRole)
            skip_conflicts_btn = buttons.addButton("Skip All Conflicts", QDialogButtonBox.ActionRole)
            apply_remaining_btn = buttons.addButton("Apply Choice To Remaining", QDialogButtonBox.ActionRole)
            apply_same_status_btn = buttons.addButton("Apply Choice To Same Status", QDialogButtonBox.ActionRole)
            run_btn = buttons.addButton("Run Update", QDialogButtonBox.AcceptRole)
            cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)

            def sync_combo_widgets() -> None:
                for row_idx, combo in enumerate(action_widgets):
                    action = str(plan_rows[row_idx].get("action", "skip")).strip().lower()
                    for option_idx in range(combo.count()):
                        if str(combo.itemData(option_idx)) == action:
                            combo.blockSignals(True)
                            combo.setCurrentIndex(option_idx)
                            combo.blockSignals(False)
                            break

            def selected_row_index() -> int:
                current_row = table.currentRow()
                if current_row >= 0:
                    return current_row
                selected_rows = table.selectionModel().selectedRows()
                if selected_rows:
                    return selected_rows[0].row()
                return -1

            def set_safe_defaults() -> None:
                for row in plan_rows:
                    status = row.get("status", {})
                    status_name = str(status.get("status", "")).strip() if isinstance(status, dict) else ""
                    if status_name == "source_changed_safe":
                        row["action"] = "replace"
                sync_combo_widgets()

            def skip_conflicts() -> None:
                for row in plan_rows:
                    status = row.get("status", {})
                    status_name = str(status.get("status", "")).strip() if isinstance(status, dict) else ""
                    if status_name in {"both_changed_conflict", "source_missing", "local_missing", "untracked_state"}:
                        row["action"] = "skip"
                sync_combo_widgets()

            def apply_remaining(same_status_only: bool) -> None:
                row_idx = selected_row_index()
                if row_idx < 0:
                    self._error("Select a row first.")
                    return
                action = str(plan_rows[row_idx].get("action", "skip")).strip().lower()
                self._apply_reference_action_to_remaining(
                    plan_rows,
                    row_idx,
                    action,
                    same_status_only=same_status_only,
                )
                sync_combo_widgets()

            replace_safe_btn.clicked.connect(set_safe_defaults)
            skip_conflicts_btn.clicked.connect(skip_conflicts)
            apply_remaining_btn.clicked.connect(lambda: apply_remaining(False))
            apply_same_status_btn.clicked.connect(lambda: apply_remaining(True))
            run_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)
            layout.addWidget(buttons)

            return dialog.exec() == QDialog.Accepted

        def _update_all_references(self) -> None:
            plan_rows = self._current_project_reference_update_plan_rows()
            if not plan_rows:
                self._error("No reference files are available for the current project.")
                return
            if not self._show_update_all_references_dialog(plan_rows):
                return
            with self._busy_action("Updating reference file(s)..."):
                summary = self._execute_reference_update_plan(plan_rows)
            failed = summary.get("failed", [])
            failed_rows = failed if isinstance(failed, list) else []
            summary_lines = [
                f"Updated {int(summary.get('updated', 0) or 0)} reference file(s).",
                f"Kept {int(summary.get('kept', 0) or 0)} reference file(s).",
                f"Skipped {int(summary.get('skipped', 0) or 0)} reference file(s).",
            ]
            if failed_rows:
                summary_lines.append(f"Failed {len(failed_rows)} reference file(s).")
                summary_lines.extend(str(row) for row in failed_rows[:10])
                self._error("\n".join(summary_lines))
                return
            self._info("\n".join(summary_lines))

        def _reference_status_rows_for_indexes(self, indexes: List[int]) -> List[Dict[str, object]]:
            rows: List[Dict[str, object]] = []
            for idx in indexes:
                if idx < 0 or idx >= len(self.records):
                    continue
                record = self.records[idx]
                if record.record_type != "reference_copy":
                    continue
                rows.append(
                    {
                        "record": record,
                        "record_id": record.id,
                        "record_index": idx,
                        "status": self._reference_status_for_record(record),
                    }
                )
            return rows

        def _show_reference_status_dialog(self, status_rows: List[Dict[str, object]], title: str) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle(title)
            dialog.resize(980, 420)
            layout = QVBoxLayout(dialog)

            table = QTableWidget(len(status_rows), 5)
            table.setHorizontalHeaderLabels(["Reference File", "Source File", "Status", "Action", "Details"])
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.SingleSelection)

            for row_idx, row in enumerate(status_rows):
                record = row.get("record")
                status = row.get("status", {})
                if not isinstance(record, CheckoutRecord) or not isinstance(status, dict):
                    continue
                values = [
                    Path(record.local_file).name,
                    Path(record.source_file).name,
                    self._reference_status_label(str(status.get("status", ""))),
                    self._reference_action_label(str(status.get("default_action", ""))),
                    str(status.get("details", "")),
                ]
                tooltips = [
                    record.local_file,
                    record.source_file,
                    self._reference_status_label(str(status.get("status", ""))),
                    self._reference_action_label(str(status.get("default_action", ""))),
                    str(status.get("details", "")),
                ]
                for col_idx, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(tooltips[col_idx])
                    table.setItem(row_idx, col_idx, item)

            table.resizeColumnsToContents()
            table.setColumnWidth(0, max(table.columnWidth(0), 180))
            table.setColumnWidth(1, max(table.columnWidth(1), 220))
            table.setColumnWidth(2, max(table.columnWidth(2), 140))
            table.setColumnWidth(3, max(table.columnWidth(3), 120))
            table.setColumnWidth(4, max(table.columnWidth(4), 280))
            layout.addWidget(table)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            dialog.exec()

        def _refresh_reference_record(self, record: CheckoutRecord, *, only_if_unchanged: bool = False) -> Tuple[bool, str]:
            if record.record_type != "reference_copy":
                return False, "Not a reference copy."

            source_path = Path(record.source_file)
            local_path = Path(record.local_file)
            status = self._reference_status_for_record(record)
            status_name = str(status.get("status", "")).strip()

            if not source_path.exists():
                return False, "Source file is missing."
            if not local_path.exists():
                return False, "Local reference copy is missing."

            if only_if_unchanged:
                if status_name == "up_to_date":
                    return False, "Already up to date."
                if status_name != "source_changed_safe":
                    return False, f"Skipped because status is '{status_name or 'unknown'}'."
            elif status_name == "up_to_date":
                return False, "Already up to date."

            copied_at = datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                self._clear_local_file_read_only(local_path)
                shutil.copy2(source_path, local_path)
                self._apply_reference_copy_baseline(
                    record,
                    source_path=source_path,
                    local_path=local_path,
                    copied_at=copied_at,
                )
                return True, "Updated from source."
            except OSError as exc:
                return False, str(exc)

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
            key = self._record_version_key(record)
            file_entry = files.get(key)
            if file_entry is None and record.file_id:
                file_entry = files.get(self._legacy_record_version_key(record), {})
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
            if not isinstance(file_entry, dict) and record.file_id:
                legacy_key = self._legacy_record_version_key(record)
                legacy_entry = files.get(legacy_key)
                if isinstance(legacy_entry, dict):
                    file_entry = dict(legacy_entry)
                    files[key] = file_entry
                    files.pop(legacy_key, None)
            if not isinstance(file_entry, dict):
                file_entry = {
                    "file_id": record.file_id,
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
            index = self._ensure_source_index(source_dir)
            for row in self._read_history_rows(source_dir):
                revision_id = str(row.get("revision_id", "")).strip()
                if not revision_id:
                    continue
                if record.file_id:
                    if self._resolve_history_row_file_id(source_dir, row, index) != record.file_id:
                        continue
                elif str(row.get("file_name", "")).strip() != source_name:
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

        def _clear_local_file_read_only(self, path: Path) -> None:
            try:
                current_mode = path.stat().st_mode
                path.chmod(current_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            except OSError:
                return

        def _prune_empty_reference_directories(self, record: CheckoutRecord) -> None:
            project_dir = Path(record.project_dir)
            reference_root = project_dir / "reference_copies"
            current = Path(record.local_file).parent
            try:
                while current != reference_root and reference_root in current.parents:
                    current.rmdir()
                    current = current.parent
            except OSError:
                return
            try:
                if current == reference_root:
                    current.rmdir()
            except OSError:
                return

        def _remove_record_indexes(self, record_indexes: List[int]) -> List[str]:
            selected = {idx for idx in record_indexes if 0 <= idx < len(self.records)}
            if not selected:
                return []

            errors: List[str] = []
            remaining: List[CheckoutRecord] = []
            for idx, record in enumerate(self.records):
                if idx not in selected:
                    remaining.append(record)
                    continue
                if record.record_type != "reference_copy":
                    continue

                local_path = Path(record.local_file)
                try:
                    if local_path.exists():
                        self._clear_local_file_read_only(local_path)
                        local_path.unlink()
                    self._prune_empty_reference_directories(record)
                except OSError as exc:
                    remaining.append(record)
                    errors.append(f"{local_path.name}: {exc}")

            self.records = remaining
            return errors

        def _record_index_for_controlled_file(self, entry: Dict[str, str]) -> int:
            file_id = str(entry.get("file_id", "")).strip()
            file_name = str(entry.get("file_name", ""))
            locked_source_file = str(entry.get("locked_source_file", ""))
            for idx, record in enumerate(self.records):
                if file_id and record.file_id == file_id:
                    return idx
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
                    file_id = ""
                    if action.record_idx >= 0 and 0 <= action.record_idx < len(self.records):
                        record = self.records[action.record_idx]
                        file_id = record.file_id
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
                        file_id=file_id,
                    )
                    if file_id:
                        index = self._ensure_source_index(source_file.parent)
                        files = index.get("files", {})
                        if isinstance(files, dict) and isinstance(files.get(file_id), dict):
                            entry = dict(files[file_id])  # type: ignore[index]
                            known_names = [
                                str(name).strip()
                                for name in entry.get("known_names", [])
                                if str(name).strip()
                            ]
                            if source_file.name not in known_names:
                                known_names.append(source_file.name)
                            entry["file_id"] = file_id
                            entry["current_name"] = source_file.name
                            entry["canonical_name"] = source_file.name
                            entry["status"] = "active"
                            entry["checked_out_by"] = ""
                            entry["checked_out_at"] = ""
                            entry["known_names"] = known_names
                            files[file_id] = entry
                            self._save_source_index(source_file.parent, index)
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

        def _selected_source_file_ids(self) -> set[str]:
            file_ids: set[str] = set()
            for item in self._selected_source_file_items():
                file_id = str(item.data(Qt.UserRole + 2) or "").strip()
                if file_id:
                    file_ids.add(file_id)
            return file_ids

        def _checkin_selected_source_files_if_owned(self) -> None:
            if not self._validate_identity():
                return
            selected_files = self._selected_source_file_paths()
            if not selected_files:
                self._error("Select at least one source file to check in.")
                return
            initials = self._normalize_initials()
            selected_paths = {str(path) for path in selected_files}
            selected_file_ids = self._selected_source_file_ids()
            selected_record_indexes: set[int] = set()
            for idx, record in enumerate(self.records):
                if record.record_type != "checked_out":
                    continue
                if record.initials != initials:
                    continue
                if record.file_id and record.file_id in selected_file_ids:
                    selected_record_indexes.add(idx)
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
            if not current_directory:
                return

            project_dir = self._current_project_path() or Path.home()
            start_dir = str(project_dir)
            file_paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Select Local File(s) To Add",
                start_dir,
                "All Files (*)",
            )
            if not file_paths:
                return

            self._add_local_files_to_source([Path(path) for path in file_paths], current_directory)

        def _add_local_files_to_source(self, file_paths: List[Path], destination_directory: Path) -> None:
            if not self._validate_identity():
                return
            project_dir = self._validate_current_project()
            if not project_dir:
                return
            if not destination_directory.is_dir():
                self._error("Selected destination source folder does not exist.")
                return
            if not file_paths:
                self._error("Select at least one local file to add.")
                return

            errors: List[str] = []
            success_count = 0
            with self._busy_action("Adding file(s) to source..."):
                for local_file in file_paths:
                    target_file = destination_directory / local_file.name
                    if target_file.exists():
                        errors.append(f"Already exists in source: {target_file.name}")
                        continue

                    try:
                        shutil.copy2(local_file, target_file)
                        index = self._ensure_source_index(destination_directory)
                        files = index.get("files", {})
                        file_id = ""
                        if isinstance(files, dict):
                            file_id = self._new_file_id({str(key).strip() for key in files.keys()})
                            files[file_id] = self._normalize_source_index_entry(
                                destination_directory,
                                {
                                    "file_id": file_id,
                                    "current_name": target_file.name,
                                    "canonical_name": target_file.name,
                                    "status": "active",
                                    "known_names": [target_file.name],
                                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                },
                            )
                            self._save_source_index(destination_directory, index)
                        self._append_history(
                            destination_directory,
                            "ADD_FILE",
                            target_file.name,
                            file_id=file_id,
                        )
                        self._invalidate_directory_caches(destination_directory)
                        success_count += 1
                    except OSError as exc:
                        errors.append(f"{local_file.name}: {exc}")

                if self.current_directory == destination_directory:
                    self._refresh_source_files()

            if errors:
                self._error("Some files failed to add:\n" + "\n".join(errors))
            if success_count > 0:
                self._info(f"Added {success_count} local file(s) to source.")

        def _open_source_item(self, item: QTableWidgetItem) -> None:
            self._open_paths([Path(str(item.data(Qt.UserRole)))])

        def _show_source_file_context_menu_for_item(self, item: QTableWidgetItem) -> None:
            row = item.row()
            self.files_list.clearSelection()
            self.files_list.selectRow(row)
            self.files_list.setCurrentCell(row, 0)
            rect = self.files_list.visualRect(self.files_list.model().index(row, 0))
            self._show_source_file_context_menu(rect.center())

        def _show_source_file_context_menu(self, pos: QPoint) -> None:
            row = self.files_list.rowAt(pos.y())
            if row >= 0 and self.files_list.item(row, 0) is not None and not self.files_list.item(row, 0).isSelected():
                self.files_list.clearSelection()
                self.files_list.selectRow(row)
                self.files_list.setCurrentCell(row, 0)

            menu = QMenu(self)
            actions = [
                ("Open Selected", "open"),
                ("Rename Selected", "rename"),
                ("Delete Selected", "delete"),
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
            chosen = menu.exec(self.files_list.viewport().mapToGlobal(pos))
            if chosen in action_map:
                self._handle_source_file_context_action(action_map[chosen])

        def _show_local_file_context_menu(self, pos: QPoint) -> None:
            row = self.local_files_list.rowAt(pos.y())
            if (
                row >= 0
                and self.local_files_list.item(row, 0) is not None
                and not self.local_files_list.item(row, 0).isSelected()
            ):
                self.local_files_list.clearSelection()
                self.local_files_list.selectRow(row)
                self.local_files_list.setCurrentCell(row, 0)

            menu = QMenu(self)
            actions = [
                ("Open Selected", "open"),
                ("Create Directory", "create_dir"),
                ("Rename Selected", "rename"),
                ("Move Selected", "move"),
                ("Delete Selected", "delete"),
                ("Add Selected To Favorites", "favorite"),
                ("Copy As Reference", "reference"),
                ("Add Local File(s) To Source", "add_to_source"),
                ("Refresh", "refresh"),
                ("View Location", "view_location"),
            ]
            action_map: Dict[QAction, str] = {}
            for label, action_id in actions:
                action_map[menu.addAction(label)] = action_id
            chosen = menu.exec(self.local_files_list.viewport().mapToGlobal(pos))
            action_id = action_map.get(chosen)
            if action_id == "open":
                self._open_selected_local_files()
            elif action_id == "create_dir":
                self._create_directory_in_current_local()
            elif action_id == "rename":
                self._rename_selected_local_item()
            elif action_id == "move":
                self._move_selected_local_items()
            elif action_id == "delete":
                self._delete_selected_local_items()
            elif action_id == "favorite":
                self._add_selected_local_files_to_favorites()
            elif action_id == "reference":
                self._copy_selected_local_files_as_reference()
            elif action_id == "add_to_source":
                self._add_selected_local_files_to_source()
            elif action_id == "refresh":
                self._refresh_local_files()
            elif action_id == "view_location":
                self._view_local_current_directory_location()

        def _handle_source_file_context_action(self, action_id: str) -> None:
            if action_id == "open":
                self._open_selected_source_files()
                return
            if action_id == "rename":
                self._rename_selected_source_file()
                return
            if action_id == "delete":
                self._delete_selected_source_files()
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

        def _rename_selected_source_file(self) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return

            selected_items = self._selected_source_file_items()
            if len(selected_items) != 1:
                self._error("Select exactly one source file to rename.")
                return

            selected_item = selected_items[0]
            source_path = Path(str(selected_item.data(Qt.UserRole) or ""))
            if not source_path.exists():
                self._error("The selected source file no longer exists.")
                self._refresh_source_files()
                return

            current_name = source_path.name
            file_id = str(selected_item.data(Qt.UserRole + 2) or "").strip()
            entry = self._source_index_entry_for_file_id(current_directory, file_id)
            original_name = (
                str(entry.get("canonical_name", "")).strip()
                if entry
                else str(selected_item.data(Qt.UserRole + 1) or current_name).strip()
            ) or current_name
            history_row = self._history_lookup_for_directory(current_directory).get(current_name)
            if history_row and str(history_row.get("action", "")).strip() == "CHECK_OUT":
                self._error("Checked-out files cannot be renamed in the current version.")
                return

            new_name, accepted = QInputDialog.getText(
                self,
                "Rename File",
                "New file name:",
                text=current_name,
            )
            if not accepted:
                return

            new_name = new_name.strip()
            if not new_name:
                self._error("File name is required.")
                return
            if new_name == current_name:
                return
            if Path(new_name).name != new_name or any(sep in new_name for sep in ("\\", "/")):
                self._error("Enter a file name only, not a path.")
                return

            target_path = current_directory / new_name
            if target_path.exists():
                self._error(f"A file named '{new_name}' already exists in this folder.")
                return

            with self._busy_action("Renaming file..."):
                try:
                    source_path.rename(target_path)
                    if entry and file_id:
                        index = self._ensure_source_index(current_directory)
                        files = index.get("files", {})
                        if isinstance(files, dict) and isinstance(files.get(file_id), dict):
                            updated_entry = dict(files[file_id])  # type: ignore[index]
                            known_names = [
                                str(name).strip()
                                for name in updated_entry.get("known_names", [])
                                if str(name).strip()
                            ]
                            for candidate in (current_name, original_name, new_name):
                                if candidate and candidate not in known_names:
                                    known_names.append(candidate)
                            updated_entry["file_id"] = file_id
                            updated_entry["current_name"] = new_name
                            updated_entry["canonical_name"] = new_name
                            updated_entry["known_names"] = known_names
                            files[file_id] = updated_entry
                            self._save_source_index(current_directory, index)
                        self._sync_note_file_name(current_directory, file_id, new_name)
                    self._append_history(
                        current_directory,
                        "RENAME",
                        new_name,
                        file_id=file_id,
                        previous_file_name=original_name,
                    )
                    self._refresh_source_files()
                except OSError as exc:
                    self._error(f"Could not rename file:\n{exc}")
                    return

            self._info(f"Renamed '{current_name}' to '{new_name}'.")

        def _delete_selected_source_files(self) -> None:
            current_directory = self._validate_current_directory()
            if not current_directory:
                return

            selected_files = self._selected_source_file_paths()
            if not selected_files:
                self._error("Select at least one source file to delete.")
                return

            history_lookup = self._history_lookup_for_directory(current_directory)
            blocked: List[str] = []
            deletions: List[tuple[Path, str, str]] = []
            seen_paths: set[str] = set()
            for item in self._selected_source_file_items():
                file_path = Path(str(item.data(Qt.UserRole) or ""))
                if not str(file_path):
                    continue
                if str(file_path) in seen_paths:
                    continue
                seen_paths.add(str(file_path))
                current_name = file_path.name
                file_id = str(item.data(Qt.UserRole + 2) or "").strip()
                entry = self._source_index_entry_for_file_id(current_directory, file_id)
                original_name = (
                    str(entry.get("canonical_name", "")).strip()
                    if entry
                    else str(item.data(Qt.UserRole + 1) or current_name).strip()
                ) or current_name
                history_row = history_lookup.get(current_name)
                if history_row and str(history_row.get("action", "")).strip() == "CHECK_OUT":
                    blocked.append(current_name)
                    continue
                deletions.append((file_path, original_name, file_id))

            if blocked:
                self._error(
                    "Checked-out files cannot be deleted in the current version:\n"
                    + "\n".join(sorted(blocked, key=str.lower))
                )
                return
            if not deletions:
                self._error("Select at least one source file to delete.")
                return

            confirm = QMessageBox.question(
                self,
                "Delete Source File(s)",
                f"Delete {len(deletions)} selected source file(s)? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            deleted_names: List[str] = []
            errors: List[str] = []
            with self._busy_action("Deleting source file(s)..."):
                for file_path, original_name, file_id in deletions:
                    try:
                        if not file_path.exists():
                            errors.append(f"Missing source file: {file_path.name}")
                            continue
                        file_path.unlink()
                        deleted_names.append(original_name)
                        if file_id:
                            index = self._ensure_source_index(current_directory)
                            files = index.get("files", {})
                            if isinstance(files, dict) and isinstance(files.get(file_id), dict):
                                updated_entry = dict(files[file_id])  # type: ignore[index]
                                known_names = [
                                    str(name).strip()
                                    for name in updated_entry.get("known_names", [])
                                    if str(name).strip()
                                ]
                                if original_name not in known_names:
                                    known_names.append(original_name)
                                updated_entry["file_id"] = file_id
                                updated_entry["current_name"] = ""
                                updated_entry["canonical_name"] = original_name
                                updated_entry["status"] = "deleted"
                                updated_entry["known_names"] = known_names
                                files[file_id] = updated_entry
                                self._save_source_index(current_directory, index)
                        self._append_history(
                            current_directory,
                            "DELETE_FILE",
                            original_name,
                            file_id=file_id,
                        )
                    except OSError as exc:
                        errors.append(f"{file_path.name}: {exc}")
                self._refresh_source_files()

            if errors:
                self._error("Some files could not be deleted:\n" + "\n".join(errors))
            elif deleted_names:
                self._info(f"Deleted {len(deleted_names)} source file(s).")

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
                errors = self._remove_record_indexes(removable_indexes)
                self._save_records()
                self._render_records_tables()
            if errors:
                self._error("Some reference copies could not be removed:\n" + "\n".join(errors))

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

            current_item = self.favorites_list.currentItem()
            is_folder = current_item is not None and str(current_item.data(Qt.UserRole + 1)) == "folder"
            menu = QMenu(self)
            open_action = menu.addAction("Open Folder" if is_folder else "Open Selected")
            add_action = menu.addAction("Add Favorite")
            new_folder_action = menu.addAction("New Folder")
            up_folder_action = menu.addAction("Up Folder")
            root_action = menu.addAction("Go Root")
            rename_folder_action = menu.addAction("Rename Folder")
            delete_folder_action = menu.addAction("Delete Folder")
            view_location_action = menu.addAction("View Location")
            load_location_action = menu.addAction("Load Location")
            add_global_action = menu.addAction("Add Selected To Global Favorites")
            move_to_folder_action = menu.addAction("Move Selected To Folder")
            move_to_root_action = menu.addAction("Move Selected To Root")
            remove_action = menu.addAction("Remove Favorite")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.favorites_list.mapToGlobal(pos))
            if chosen == open_action:
                self._open_selected_favorites()
            elif chosen == new_folder_action:
                self._create_project_favorites_folder()
            elif chosen == up_folder_action:
                self._go_up_project_favorites_folder()
            elif chosen == root_action:
                self._go_root_project_favorites_folder()
            elif chosen == rename_folder_action and current_item is not None:
                self._rename_project_favorites_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == delete_folder_action and current_item is not None:
                self._delete_project_favorites_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == view_location_action:
                self._view_selected_file_locations_from_list(self.favorites_list)
            elif chosen == load_location_action:
                self._load_selected_file_location_from_list(self.favorites_list)
            elif chosen == add_action:
                self._browse_and_add_favorites()
            elif chosen == add_global_action:
                self._add_selected_project_favorites_to_global()
            elif chosen == move_to_folder_action:
                self._move_selected_favorites_to_folder()
            elif chosen == move_to_root_action:
                self._move_selected_favorites_to_root()
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

            current_item = self.notes_list.currentItem()
            is_folder = current_item is not None and str(current_item.data(Qt.UserRole + 1)) == "folder"
            menu = QMenu(self)
            new_action = menu.addAction("New Note")
            new_folder_action = menu.addAction("New Folder")
            up_folder_action = menu.addAction("Up Folder")
            root_action = menu.addAction("Go Root")
            edit_action = menu.addAction("Open Folder" if is_folder else "Edit Selected")
            rename_folder_action = menu.addAction("Rename Folder")
            delete_folder_action = menu.addAction("Delete Folder")
            presets_action = menu.addAction("Presets")
            copy_action = menu.addAction("Copy Selected To Project")
            move_project_action = menu.addAction("Move Selected To Project")
            remove_action = menu.addAction("Remove Selected")
            move_to_folder_action = menu.addAction("Move Selected To Folder")
            move_to_root_action = menu.addAction("Move Selected To Root")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            customize_action = menu.addAction("Customize/Organize")
            chosen = menu.exec(self.notes_list.mapToGlobal(pos))
            if chosen == new_action:
                self._create_note()
            elif chosen == new_folder_action:
                self._create_project_notes_folder()
            elif chosen == up_folder_action:
                self._go_up_project_notes_folder()
            elif chosen == root_action:
                self._go_root_project_notes_folder()
            elif chosen == presets_action:
                self._show_note_presets_dialog()
            elif chosen == edit_action:
                if is_folder and current_item is not None:
                    self._edit_note_item(current_item)
                else:
                    self._edit_selected_note()
            elif chosen == rename_folder_action and current_item is not None:
                self._rename_project_notes_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == delete_folder_action and current_item is not None:
                self._delete_project_notes_folder(str(current_item.data(Qt.UserRole)).strip())
            elif chosen == copy_action:
                self._copy_selected_note_to_project()
            elif chosen == move_project_action:
                self._move_selected_note_to_project()
            elif chosen == remove_action:
                self._remove_selected_note()
            elif chosen == move_to_folder_action:
                self._move_selected_notes_to_folder()
            elif chosen == move_to_root_action:
                self._move_selected_notes_to_root()
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
            relink_action = menu.addAction("Relink Directory")
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
            elif chosen == relink_action:
                self._relink_selected_source_directory()
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

        def _show_local_roots_context_menu(self, pos: QPoint) -> None:
            item = self.local_roots_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.local_roots_list.clearSelection()
                item.setSelected(True)
                self.local_roots_list.setCurrentItem(item)

            menu = QMenu(self)
            track_browse_action = menu.addAction("Track Dir (Browse)")
            track_current_action = menu.addAction("Track Directory")
            view_location_action = menu.addAction("View Location")
            untrack_action = menu.addAction("Untrack Dir")
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            move_top_action = menu.addAction("Move to Top")
            move_bottom_action = menu.addAction("Move to Bottom")
            chosen = menu.exec(self.local_roots_list.mapToGlobal(pos))
            if chosen == track_browse_action:
                self._add_local_directory()
            elif chosen == track_current_action:
                self._track_current_local_directory()
            elif chosen == view_location_action:
                self._view_selected_local_directory_location()
            elif chosen == untrack_action:
                self._remove_local_directory()
            elif chosen == move_up_action:
                self._move_selected_local_root_up()
            elif chosen == move_down_action:
                self._move_selected_local_root_down()
            elif chosen == move_top_action:
                self._move_selected_local_root_top()
            elif chosen == move_bottom_action:
                self._move_selected_local_root_bottom()

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
            selected_items = self._selected_source_file_items()
            if not selected_items:
                self._error("Select a file to view history.")
                return

            file_path = Path(selected_items[0].data(Qt.UserRole))
            file_id = str(selected_items[0].data(Qt.UserRole + 2) or "").strip()
            entry = self._source_index_entry_for_file_id(file_path.parent, file_id)
            original_name = (
                str(entry.get("canonical_name", "")).strip()
                if entry
                else str(selected_items[0].data(Qt.UserRole + 1) or file_path.name)
            ) or file_path.name
            if file_id:
                rows = self._history_rows_for_file_id(file_path.parent, file_id)
            else:
                rows = self._history_rows_for_file_name_legacy(file_path.parent, original_name)

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
                    existing_ids: set[str] = set()
                    for entry in raw_records:
                        if not isinstance(entry, dict):
                            continue
                        record = CheckoutRecord(
                            source_file=str(entry.get("source_file", "")),
                            locked_source_file=str(entry.get("locked_source_file", "")),
                            local_file=str(entry.get("local_file", "")),
                            initials=str(entry.get("initials", "")),
                            project_name=str(entry.get("project_name", "")),
                            project_dir=str(entry.get("project_dir", "")),
                            source_root=str(entry.get("source_root", "")),
                            checked_out_at=str(entry.get("checked_out_at", "")),
                            id=str(entry.get("id", "")).strip(),
                            record_type=str(entry.get("record_type", "checked_out") or "checked_out"),
                            file_id=str(entry.get("file_id", "")).strip(),
                            source_hash_at_copy=str(entry.get("source_hash_at_copy", "")).strip(),
                            local_hash_at_copy=str(entry.get("local_hash_at_copy", "")).strip(),
                            source_mtime_at_copy=self._coerce_float(entry.get("source_mtime_at_copy", 0.0)),
                            local_mtime_at_copy=self._coerce_float(entry.get("local_mtime_at_copy", 0.0)),
                            source_size_at_copy=self._coerce_int(entry.get("source_size_at_copy", 0)),
                            local_size_at_copy=self._coerce_int(entry.get("local_size_at_copy", 0)),
                            last_refreshed_at=str(entry.get("last_refreshed_at", "")).strip(),
                        )
                        if not record.id or record.id in existing_ids:
                            record.id = self._new_record_id(existing_ids)
                        existing_ids.add(record.id)
                        if not record.file_id and record.source_file:
                            source_path = Path(record.source_file)
                            source_dir = source_path.parent
                            current_name = source_path.name
                            if record.record_type == "checked_out" and record.locked_source_file:
                                current_name = Path(record.locked_source_file).name
                            index_entry = self._source_index_entry_for_current_name(source_dir, current_name)
                            if index_entry:
                                record.file_id = str(index_entry.get("file_id", "")).strip()
                        self.records.append(record)
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

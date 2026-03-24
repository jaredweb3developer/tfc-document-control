from __future__ import annotations

import app as app_module
from app import *

from .mixins.config import ConfigMixin
from .mixins.notes import NotesMixin
from .mixins.projects import ProjectsMixin
from .mixins.records import RecordsMixin
from .mixins.sources import SourcesMixin
from .mixins.ui import UiMixin


class CompactItemDelegate(QStyledItemDelegate):
        def __init__(self, min_height: int = 14, extra_vertical_padding: int = 2, parent=None) -> None:
            super().__init__(parent)
            self._min_height = min_height
            self._extra_vertical_padding = extra_vertical_padding

        def sizeHint(self, option, index):  # type: ignore[override]
            size = super().sizeHint(option, index)
            compact_height = max(self._min_height, option.fontMetrics.height() + self._extra_vertical_padding)
            return QSize(size.width(), compact_height)


class DocumentControlApp(
    UiMixin,
    ConfigMixin,
    ProjectsMixin,
    SourcesMixin,
    NotesMixin,
    RecordsMixin,
    QMainWindow,
):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(f"{app_module.APP_NAME} v{app_module.APP_VERSION}")
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
            self.note_presets_notes: List[Dict[str, object]] = []
            self.note_preset_groups: List[Dict[str, object]] = []
            self.item_customization_groups: List[str] = []
            self.item_customizations: Dict[str, Dict[str, Dict[str, object]]] = {}
            self.item_customization_group_styles: Dict[str, Dict[str, object]] = {}
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
            self._compact_item_delegates: List[CompactItemDelegate] = []

            self._build_ui()
            self._apply_compact_item_view_style()
            self._show_startup_splash("Starting TFC Document Control...")
            try:
                self._update_startup_splash("Loading settings...")
                self._load_settings()
                self._update_startup_splash("Loading filter presets...")
                self._load_filter_presets()
                self._update_startup_splash("Loading item customizations...")
                self._load_item_customizations()
                self._update_startup_splash("Loading tracked projects...")
                self._load_tracked_projects()
                self._update_startup_splash("Loading checkout records...")
                self._load_records()
                self._update_startup_splash("Loading global favorites and notes...")
                self._load_global_favorites()
                self._load_global_notes()
                self._load_note_presets()
                self._update_startup_splash("Loading current project...")
                self._load_last_or_default_project()
                self._update_startup_splash("Finalizing startup...")
            finally:
                self._close_startup_splash()

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
            self._save_note_presets()
            self._save_item_customizations()
            super().closeEvent(event)

        def _apply_compact_item_view_style(self) -> None:
            seen: set[int] = set()
            for view in [*self.findChildren(QListView), *self.findChildren(QTreeView)]:
                view_id = id(view)
                if view_id in seen:
                    continue
                seen.add(view_id)
                delegate = CompactItemDelegate(parent=view)
                view.setItemDelegate(delegate)
                self._compact_item_delegates.append(delegate)


def main() -> None:
    app = QApplication(sys.argv)
    # app.setStyle("windows11")
    app.setStyleSheet(
        """
        QListView::item,
        QTreeView::item {
            margin: 0px;
            padding: 0px;
        }
        """
    )
    window = DocumentControlApp()
    window.show()
    sys.exit(app.exec())

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

from PySide6.QtCore import QDir, QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
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
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QStyledItemDelegate,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

APP_ROOT = Path(__file__).resolve().parent
APP_NAME = "TFC Document Control"
APP_VERSION = "0.2.1"
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
SOURCE_INDEX_FILE = ".doc_control_index.json"
SOURCE_INDEX_SCHEMA_VERSION = 1
DIRECTORY_NOTES_FILE = ".doc_file_notes.json"
DIRECTORY_NOTES_SCHEMA_VERSION = 1
DEFAULT_PROJECT_NAME = "Default"
DEBUG_EVENTS_FILE = USER_DATA_ROOT / "debug_events.log"
FILE_VERSIONS_FILE = "file_versions.json"
FILE_VERSIONS_DIR = "file_versions"
GLOBAL_FAVORITES_FILE = USER_DATA_ROOT / "global_favorites.json"
GLOBAL_NOTES_FILE = USER_DATA_ROOT / "global_notes.json"
ITEM_CUSTOMIZATIONS_FILE = USER_DATA_ROOT / "item_customizations.json"
ITEM_CUSTOMIZATIONS_SCHEMA_VERSION = 1
NOTE_PRESETS_FILE = USER_DATA_ROOT / "note_presets.json"
NOTE_PRESETS_SCHEMA_VERSION = 1


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
    file_id: str = ""


@dataclass
class PendingCheckinAction:
    file_name: str
    source_file: str
    locked_source_file: str
    action_mode: str
    local_file: str = ""
    record_idx: int = -1
    reason: str = ""


sys.modules.setdefault("app", sys.modules[__name__])

from document_control.window import DocumentControlApp, main


if __name__ == "__main__":
    main()

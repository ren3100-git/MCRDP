from pathlib import Path

import pandas as pd
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mcrdp.igor import IgorCommandBuilder
from mcrdp.models import NAME_MAP_COLUMNS, NAME_TABLE_COLUMNS, ProcessorConfig
from mcrdp.processor import RheoDataProcessor
from mcrdp.naming import NAME_ORDERS
from mcrdp.excel import ExcelExporter
from mcrdp.gui.settings_dialog import SettingsDialog
from mcrdp.variables import resolve_variable_config


class MainWindow(QMainWindow):
    APP_ORG = "Katashima-Chung_Lab_RenSato"
    APP_NAME = "MCRDP"
    WINDOW_TITLE = "MCRDP_v6"
    DEFAULT_OUTPUT_NAME = "sorted.xlsx"

    def __init__(self):
        super().__init__()

        QApplication.setOrganizationName(self.APP_ORG)
        QApplication.setApplicationName(self.APP_NAME)
        self.settings = QSettings(self.APP_ORG, self.APP_NAME)
        self.default_variable_config_path = resolve_variable_config()
        config_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation
        )
        self.user_variable_config_path = Path(config_dir) / "variables.json"
        active_config_path = (
            self.user_variable_config_path
            if self.user_variable_config_path.is_file()
            else self.default_variable_config_path
        )
        self.processor = RheoDataProcessor(active_config_path)
        self.igor_builder = IgorCommandBuilder(self.processor.catalog)
        self.excel_exporter = ExcelExporter(self.processor)
        self.last_result = None
        self.last_saved_path: Path | None = None

        self.selected_dir = ""
        self.preset_profiles = {}
        self.available_vars = []

        self._load_initial_state()
        self._configure_window()
        self._apply_styles()
        self._build_ui()

    # =========================
    # Initial setup
    # =========================
    def _load_initial_state(self):
        self.selected_dir = self.settings.value("input_dir", "", type=str)

        self.preset_profiles = self.processor.preset_profiles
        self.available_vars = self.processor.get_clean_variable_list()

    def _configure_window(self):
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(1100, 720)

    def _apply_styles(self):
        self.setStyleSheet("""
        QGroupBox {
            font-weight: bold;
            border: 1px solid #b0b0b0;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px 0 4px;
        }
    """)

    # =========================
    # UI layout
    # =========================
    def _build_ui(self):
        self._build_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_main_tab(), "Main")
        self.tabs.addTab(self._build_column_name_tab(), "Column Names")
        self.tabs.addTab(self._build_igor_tab(), "IGOR Command")
        root.addWidget(self.tabs, 1)
        root.addWidget(self._build_output_group(), 0)

        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

        # Restore saved log10 / linear selections after all list widgets have been created.
        self._restore_variable_selection()
        self.set_status("Ready.")

    def _build_menu_bar(self):
        file_menu = self.menuBar().addMenu("File")

        select_folder_action = QAction("Select Input Folder…", self)
        select_folder_action.setShortcut(QKeySequence.StandardKey.Open)
        select_folder_action.triggered.connect(self.select_folder)
        file_menu.addAction(select_folder_action)

        self.action_export_excel = QAction("Export Excel", self)
        self.action_export_excel.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_excel.setEnabled(False)
        self.action_export_excel.triggered.connect(self.export_current_excel)
        file_menu.addAction(self.action_export_excel)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_action)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_action = QAction("Settings…", self)
        settings_action.setMenuRole(QAction.MenuRole.NoRole)
        settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(settings_action)

    def _build_main_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        layout.addLayout(self._build_top_row())
        layout.addWidget(self._build_variable_group(), 1)

        return tab

    def _build_column_name_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self.table_names = QTableWidget(0, len(NAME_TABLE_COLUMNS))
        self.table_names.setHorizontalHeaderLabels(NAME_TABLE_COLUMNS)
        self.table_names.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_names.setColumnWidth(0, 70)    # export
        self.table_names.setColumnWidth(1, 90)    # n_points
        self.table_names.setColumnWidth(2, 120)   # variable_key
        self.table_names.setColumnWidth(3, 120)   # mean_header
        self.table_names.setColumnWidth(4, 360)   # internal_name
        self.table_names.setColumnWidth(5, 360)   # output_name
        self.table_names.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_names.setAlternatingRowColors(True)

        self.edit_find = QLineEdit()
        self.edit_find.setPlaceholderText("Find in output_name")
        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText("Replace")

        self.btn_replace_names = QPushButton("Replace")
        self.btn_replace_names.clicked.connect(self.replace_output_names)

        self.btn_reset_names = QPushButton("Reset output_name")
        self.btn_reset_names.clicked.connect(self.reset_output_names)

        self.btn_include_selected = QPushButton("Include selected")
        self.btn_include_selected.clicked.connect(lambda: self.set_selected_export(True))

        self.btn_exclude_selected = QPushButton("Exclude selected")
        self.btn_exclude_selected.clicked.connect(lambda: self.set_selected_export(False))

        row = QHBoxLayout()
        row.addWidget(QLabel("Find:"))
        row.addWidget(self.edit_find)
        row.addWidget(QLabel("Replace:"))
        row.addWidget(self.edit_replace)
        row.addWidget(self.btn_replace_names)
        row.addSpacing(12)
        row.addWidget(self.btn_reset_names)
        row.addSpacing(12)
        row.addWidget(self.btn_include_selected)
        row.addWidget(self.btn_exclude_selected)
        row.addStretch()

        layout.addLayout(row)
        layout.addWidget(self.table_names, 1)

        info = QLabel(
            "n_points は各列の有効な数値データ点数です。"
            "export のチェックを外した列は variables シートと IGOR コマンドから除外されます。"
            "internal_name、n_points、mean_header は編集不可です。output_name のみ変更してください。"
            "Run はデータ読み込みと列名表更新のみ実行します。Export Excel で xlsx を出力します。"
            "元名は name_map シートに残します。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        return tab

    def _build_igor_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self._build_igor_group(), 1)
        return tab

    def _build_top_row(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(self._build_input_group(), 3)
        layout.addWidget(self._build_preset_group(), 1)

        return layout

    def _build_input_group(self):
        self.label_dir_path = QLabel(self.selected_dir if self.selected_dir else "(未選択)")
        self.label_dir_path.setMinimumWidth(240)
        self.label_dir_path.setWordWrap(True)

        self.btn_select_dir = QPushButton("フォルダ選択")
        self.btn_select_dir.clicked.connect(self.select_folder)

        self.btn_open_dir = QPushButton("Finderで開く")
        self.btn_open_dir.setEnabled(bool(self.selected_dir))
        self.btn_open_dir.clicked.connect(self.open_selected_folder)

        self.check_recursive = QCheckBox("サブフォルダも検索 (recursive)")
        self.check_recursive.setChecked(
            self.settings.value("recursive", False, type=bool)
        )
        self.check_recursive.toggled.connect(
            lambda checked: self.settings.setValue("recursive", checked)
        )

        layout = QVBoxLayout()
        layout.addWidget(self.label_dir_path)
        controls = QHBoxLayout()
        controls.addWidget(self.btn_select_dir)
        controls.addWidget(self.btn_open_dir)
        controls.addWidget(self.check_recursive)
        controls.addStretch()
        layout.addLayout(controls)

        return self._make_group("Input/Output folder", layout)

    def _build_preset_group(self):
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(self.preset_profiles.keys()))

        saved_preset = self.settings.value("preset", "", type=str)
        if saved_preset:
            idx = self.combo_preset.findText(saved_preset)
            if idx >= 0:
                self.combo_preset.setCurrentIndex(idx)

        self.combo_preset.currentTextChanged.connect(
            lambda text: self.settings.setValue("preset", text)
        )
        self.combo_preset.currentTextChanged.connect(self.apply_preset)

        layout = QVBoxLayout()
        layout.addWidget(self.combo_preset)

        return self._make_group("Preset", layout)

    def _build_variable_group(self):
        self.label_available = QLabel("available")
        self.list_available = QListWidget()
        self.list_available.addItems(self.available_vars)
        self.list_available.setSelectionMode(QAbstractItemView.ExtendedSelection)

        left_col = QVBoxLayout()
        left_col.addWidget(self.label_available)
        left_col.addWidget(self.list_available)

        left_wrap = QWidget()
        left_wrap.setLayout(left_col)

        mid_button_wrap = self._make_middle_button_panel()

        self.label_log = QLabel("log10")
        self.list_log = QListWidget()
        self.list_log.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.btn_log_to_lin = QPushButton("↓ linear")
        self.btn_lin_to_log = QPushButton("log10 ↑")
        self.btn_log_to_lin.clicked.connect(self.move_log_to_linear)
        self.btn_lin_to_log.clicked.connect(self.move_linear_to_log)

        self.label_lin = QLabel("linear")
        self.list_linear = QListWidget()
        self.list_linear.setSelectionMode(QAbstractItemView.ExtendedSelection)

        log_col = QVBoxLayout()
        log_col.addWidget(self.label_log)
        log_col.addWidget(self.list_log)

        log_wrap = QWidget()
        log_wrap.setLayout(log_col)

        lin_col = QVBoxLayout()
        lin_col.addWidget(self.label_lin)
        lin_col.addWidget(self.list_linear)

        lin_wrap = QWidget()
        lin_wrap.setLayout(lin_col)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        grid.addWidget(left_wrap, 0, 0, 5, 1)
        grid.addWidget(mid_button_wrap, 0, 1, 5, 1)
        grid.addWidget(log_wrap, 0, 2, 2, 4)
        grid.addWidget(self.btn_log_to_lin, 2, 3)
        grid.addWidget(self.btn_lin_to_log, 2, 4)
        grid.addWidget(lin_wrap, 3, 2, 2, 4)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 0)
        grid.setColumnStretch(4, 0)
        grid.setColumnStretch(5, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(4, 1)

        return self._make_group("Variable Selection", grid)

    def _build_output_group(self):
        self.edit_out = QLineEdit(
            self.settings.value(
                "output_name",
                self.processor.catalog.export.default_output_name,
                type=str,
            )
        )
        self.edit_out.textChanged.connect(
            lambda text: self.settings.setValue("output_name", text)
        )

        self.combo_mean_variable = QComboBox()
        self.combo_mean_variable.addItem("(none)", None)
        for variable_name in self.available_vars:
            self.combo_mean_variable.addItem(variable_name, variable_name)

        saved_mean_variable = self.settings.value("mean_variable", "", type=str)
        if saved_mean_variable:
            idx = self.combo_mean_variable.findData(saved_mean_variable)
            if idx >= 0:
                self.combo_mean_variable.setCurrentIndex(idx)

        self.combo_mean_variable.currentIndexChanged.connect(
            self._on_mean_variable_changed
        )

        self.btn_run = QPushButton("Run")
        self.btn_run.clicked.connect(self.run_processing)

        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_excel.clicked.connect(self.export_current_excel)
        self.btn_export_excel.setEnabled(False)

        primary_button_style = """
            QPushButton {
                background-color: #4a90e2;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2a5f94;
            }
            QPushButton:disabled {
                background-color: #b0b0b0;
                color: #eeeeee;
            }
        """
        self.btn_run.setStyleSheet(primary_button_style)
        self.btn_export_excel.setStyleSheet(primary_button_style)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Output xlsx:"))
        row.addWidget(self.edit_out)
        row.addSpacing(12)
        row.addWidget(QLabel("Mean header:"))
        row.addWidget(self.combo_mean_variable)
        row.addSpacing(12)
        row.addStretch()
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_export_excel)

        return self._make_group("Output", row)

    def _build_igor_group(self):
        self.combo_igor_x = QComboBox()

        self.list_igor_y = QListWidget()
        self.list_igor_y.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_igor_y.setMinimumHeight(120)

        self.combo_igor_axis = QComboBox()
        self.combo_igor_axis.addItems(["L", "R"])
        saved_axis = self.processor.catalog.igor.default_axis
        if self.processor.catalog.igor.remember_selection:
            saved_axis = self.settings.value("igor_axis", saved_axis, type=str)
        axis_index = self.combo_igor_axis.findText(saved_axis)
        if axis_index >= 0:
            self.combo_igor_axis.setCurrentIndex(axis_index)
        self.combo_igor_axis.currentTextChanged.connect(self._save_igor_selection)
        self.combo_igor_x.currentTextChanged.connect(self._save_igor_selection)
        self.list_igor_y.itemSelectionChanged.connect(self._save_igor_selection)

        self.btn_make_igor = QPushButton("Generate")
        self.btn_make_igor.clicked.connect(self.make_igor_command)

        self.btn_copy_igor = QPushButton("Copy")
        self.btn_copy_igor.clicked.connect(self.copy_igor_command)

        self.text_igor = QPlainTextEdit()
        self.text_igor.setReadOnly(True)
        self.text_igor.setPlaceholderText("Run 後に Generate してください。Export Excel 時にこの内容を保存します。")

        left_panel = self._build_igor_left_panel()
        right_panel = self._build_igor_right_panel()

        main = QHBoxLayout()
        main.setSpacing(10)
        main.addLayout(left_panel, 1)
        main.addLayout(right_panel, 2)

        wrapper = QVBoxLayout()
        wrapper.addLayout(main)

        return self._make_group("IGOR Command", wrapper)

    def _build_igor_left_panel(self):
        layout = QVBoxLayout()

        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("x variable:"))
        x_row.addWidget(self.combo_igor_x)
        x_row.addStretch()

        layout.addLayout(x_row)
        layout.addWidget(QLabel("y variables:"))
        layout.addWidget(self.list_igor_y)

        return layout

    def _build_igor_right_panel(self):
        layout = QVBoxLayout()

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("y axis:"))
        ctrl_row.addWidget(self.combo_igor_axis)
        ctrl_row.addWidget(self.btn_make_igor)
        ctrl_row.addWidget(self.btn_copy_igor)
        ctrl_row.addStretch()

        layout.addLayout(ctrl_row)
        layout.addWidget(self.text_igor)

        return layout

    # =========================
    # Small widget factories
    # =========================
    def _make_group(self, title, layout):
        box = QGroupBox(title)
        box.setLayout(layout)
        return box

    def _make_middle_button_panel(self):
        # available から log10 / linear へコピーし、出力側の選択項目を削除する中央ボタン群
        self.btn_to_log = QPushButton("→ log10")
        self.btn_back_selected = QPushButton("back ←")
        self.btn_to_lin = QPushButton("→ linear")

        self.btn_to_log.clicked.connect(self.move_available_to_log)
        self.btn_back_selected.clicked.connect(self.remove_selected_from_outputs)
        self.btn_to_lin.clicked.connect(self.move_available_to_linear)

        for btn in (self.btn_to_log, self.btn_back_selected, self.btn_to_lin):
            btn.setMinimumWidth(90)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addStretch()
        layout.addWidget(self.btn_to_log)
        layout.addWidget(self.btn_back_selected)
        layout.addWidget(self.btn_to_lin)
        layout.addStretch()

        wrap = QWidget()
        wrap.setLayout(layout)

        return wrap

    def _make_readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _make_export_item(self, checked: bool) -> QTableWidgetItem:
        # Checkable table item.
        # Checked   = export to variables sheet and IGOR command
        # Unchecked = exclude from variables sheet and IGOR command
        item = QTableWidgetItem("")
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        return item

    def set_status(self, text):
        self.status_label.setText(text)

    def set_export_buttons_enabled(self, enabled: bool):
        if hasattr(self, "btn_export_excel"):
            self.btn_export_excel.setEnabled(enabled)
        if hasattr(self, "action_export_excel"):
            self.action_export_excel.setEnabled(enabled)

    def _on_mean_variable_changed(self, _index: int) -> None:
        selected = self.combo_mean_variable.currentData()
        self.settings.setValue("mean_variable", selected or "")

        # Mean values are calculated during Run. Do not allow an older result
        # to be exported under a newly selected Mean header setting.
        if self.last_result is None:
            return

        is_current = selected == self.last_result.mean_variable
        self.set_export_buttons_enabled(is_current)
        if not is_current:
            self.set_status("Mean header changed. Run again to apply the selection.")

    def get_all_items(self, list_widget):
        return [list_widget.item(i).text() for i in range(list_widget.count())]

    def get_config(self):
        legacy_place = self.settings.value("place", "pre", type=str)
        migrated_default = {
            "pre": "var-num-name",
            "suf": "num-name-var",
        }.get(legacy_place, "var-num-name")
        if self.processor.catalog.schema_version == 1:
            name_order = self.settings.value("name_order", migrated_default, type=str)
        else:
            name_order = self.processor.catalog.naming.order
        if name_order not in NAME_ORDERS:
            name_order = "var-num-name"
        return {
            "input_dir": self.selected_dir,
            "name_order": name_order,
            "output_name": self.edit_out.text().strip(),
            "recursive": self.check_recursive.isChecked(),
            "available_vars": self.get_all_items(self.list_available),
            "log10_vars": self.get_all_items(self.list_log),
            "linear_vars": self.get_all_items(self.list_linear),
            "mean_variable": self.combo_mean_variable.currentData(),
            "preset": self.combo_preset.currentText(),
        }

    def _get_setting_list(self, key):
        value = self.settings.value(key, [])
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return [str(v) for v in value if str(v)]

    def _save_variable_selection(self):
        if not hasattr(self, "list_log") or not hasattr(self, "list_linear"):
            return
        self.settings.setValue("log10_vars", self.get_all_items(self.list_log))
        self.settings.setValue("linear_vars", self.get_all_items(self.list_linear))

    def _restore_variable_selection(self):
        has_saved_selection = (
            self.settings.contains("log10_vars")
            or self.settings.contains("linear_vars")
        )

        if not has_saved_selection:
            self.apply_preset(self.combo_preset.currentText())
            return

        saved_log = self.processor.normalize_selection_names(
            self._get_setting_list("log10_vars")
        )
        saved_linear = self.processor.normalize_selection_names(
            self._get_setting_list("linear_vars")
        )

        all_vars = self.available_vars[:]
        known = set(all_vars)
        restored_log = [var for var in saved_log if var in known]
        restored_linear = [var for var in saved_linear if var in known]

        self.list_available.clear()
        self.list_log.clear()
        self.list_linear.clear()

        self.list_available.addItems(all_vars)
        self.list_log.addItems(restored_log)
        self.list_linear.addItems(restored_linear)

        self.set_status("Previous variable selection restored.")

    # =========================
    # Column name table helpers
    # =========================
    def update_name_table(self, result=None):
        result = result or self.last_result
        self.table_names.setRowCount(0)

        if result is None or result.name_map.empty:
            self.set_status("No column names to edit.")
            return

        name_map = result.name_map[NAME_MAP_COLUMNS]
        mean_lookup: dict[str, object] = {}
        if not result.column_info.empty:
            mean_lookup = {
                str(row["internal_name"]): row.get("mean_value", "")
                for _, row in result.column_info.iterrows()
            }

        self.table_names.setRowCount(len(name_map))
        for row_idx, row in name_map.reset_index(drop=True).iterrows():
            internal_name = str(row["internal_name"])
            mean_value = mean_lookup.get(internal_name, "")
            mean_text = "" if pd.isna(mean_value) else str(mean_value)

            self.table_names.setItem(row_idx, 0, self._make_export_item(bool(row["export"])))
            self.table_names.setItem(row_idx, 1, self._make_readonly_item(str(row["n_points"])))
            self.table_names.setItem(row_idx, 2, self._make_readonly_item(str(row["variable_key"])))
            self.table_names.setItem(row_idx, 3, self._make_readonly_item(mean_text))
            self.table_names.setItem(row_idx, 4, self._make_readonly_item(internal_name))
            self.table_names.setItem(row_idx, 5, QTableWidgetItem(str(row["output_name"])))

        self.set_status(f"Column names loaded: {len(name_map)}")

    def name_map_from_table(self) -> pd.DataFrame:
        rows = []
        for row_idx in range(self.table_names.rowCount()):
            export_item = self.table_names.item(row_idx, 0)
            export = (
                export_item is not None
                and export_item.checkState() == Qt.CheckState.Checked
            )
            rows.append({
                "export": export,
                "n_points": self._table_text(row_idx, 1),
                "variable_key": self._table_text(row_idx, 2),
                "internal_name": self._table_text(row_idx, 4),
                "output_name": self._table_text(row_idx, 5),
            })
        return pd.DataFrame(rows, columns=NAME_MAP_COLUMNS)

    def _table_text(self, row: int, col: int) -> str:
        item = self.table_names.item(row, col)
        return "" if item is None else item.text().strip()

    def set_selected_export(self, export: bool):
        rows = sorted({item.row() for item in self.table_names.selectedItems()})
        if not rows:
            QMessageBox.warning(self, "警告", "行を選択してください。")
            return

        state = Qt.CheckState.Checked if export else Qt.CheckState.Unchecked
        for row_idx in rows:
            item = self.table_names.item(row_idx, 0)
            if item is None:
                self.table_names.setItem(row_idx, 0, self._make_export_item(export))
            else:
                item.setCheckState(state)

        if self.sync_name_map_from_table():
            action = "included" if export else "excluded"
            self.set_status(f"{len(rows)} row(s) {action} for variables output.")

    def sync_name_map_from_table(self) -> bool:
        if self.last_result is None:
            QMessageBox.warning(self, "警告", "先に Run を実行してください。")
            return False

        name_map = self.name_map_from_table()
        try:
            self.processor.set_output_name_map(self.last_result, name_map)
        except Exception as e:
            self.set_status(f"Error: {type(e).__name__}: {e}")
            QMessageBox.critical(self, "Column name error", f"{type(e).__name__}\n{e}")
            return False
        return True

    def replace_output_names(self):
        find_text = self.edit_find.text()
        replace_text = self.edit_replace.text()

        if not find_text:
            QMessageBox.warning(self, "警告", "Find を入力してください。")
            return

        selected_rows = sorted({item.row() for item in self.table_names.selectedItems()})
        target_rows = selected_rows if selected_rows else list(range(self.table_names.rowCount()))

        count = 0
        for row_idx in target_rows:
            item = self.table_names.item(row_idx, 5)  # output_name
            if item is None:
                continue

            current = item.text()
            replaced = current.replace(find_text, replace_text)

            if replaced != current:
                item.setText(replaced)
                count += 1

        if self.sync_name_map_from_table():
            if selected_rows:
                self.set_status(f"Replaced output_name in {count} selected row(s).")
            else:
                self.set_status(f"Replaced output_name in {count} row(s).")

    def reset_output_names(self):
        for row_idx in range(self.table_names.rowCount()):
            internal_name = self._table_text(row_idx, 4)
            item = self.table_names.item(row_idx, 5)
            if item is None:
                self.table_names.setItem(row_idx, 5, QTableWidgetItem(internal_name))
            else:
                item.setText(internal_name)

        if self.sync_name_map_from_table():
            self.set_status("output_name reset to internal_name.")

    def make_output_path(self) -> Path:
        cfg = self.get_config()
        input_dir = Path(cfg["input_dir"])
        output_name = (
            cfg["output_name"]
            or self.processor.catalog.export.default_output_name
        )
        base_path = input_dir / output_name
        if not base_path.suffix:
            base_path = base_path.with_suffix(".xlsx")
        return base_path

    def resolve_export_path(self) -> Path | None:
        output_path = self.make_output_path()
        if not output_path.exists():
            return output_path

        policy = self.processor.catalog.export.conflict_policy
        if policy == "overwrite":
            return output_path
        if policy == "ask":
            answer = QMessageBox.question(
                self,
                "Overwrite Excel file?",
                f"The following file already exists:\n\n{output_path}\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return output_path if answer == QMessageBox.StandardButton.Yes else None

        counter = 1
        while True:
            candidate = output_path.with_name(
                f"{output_path.stem}_{counter:03}{output_path.suffix}"
            )
            if not candidate.exists():
                return candidate
            counter += 1

    def export_renamed_excel(self):
        # Deprecated: xlsx output is handled by Export Excel.
        self.export_current_excel()

    def remove_selected_items(self, list_widget):
        rows = sorted(
            [list_widget.row(item) for item in list_widget.selectedItems()],
            reverse=True,
        )
        texts = []
        for row in rows:
            item = list_widget.takeItem(row)
            texts.append(item.text())
        texts.reverse()
        return texts

    def copy_selected_items(self, list_widget):
        return [item.text() for item in list_widget.selectedItems()]

    def add_unique_items(self, list_widget, texts):
        existing = {list_widget.item(i).text() for i in range(list_widget.count())}
        added = 0
        for text in texts:
            if text not in existing:
                list_widget.addItem(text)
                existing.add(text)
                added += 1
        return added

    def _move_items(self, src, dst, status_text):
        texts = self.remove_selected_items(src)
        added = self.add_unique_items(dst, texts)
        self._save_variable_selection()
        self.set_status(status_text.format(added=added))

    def _copy_items(self, src, dst, status_text):
        texts = self.copy_selected_items(src)
        added = self.add_unique_items(dst, texts)
        self._save_variable_selection()
        self.set_status(status_text.format(added=added))

    def _remove_items(self, src, status_text):
        texts = self.remove_selected_items(src)
        self._save_variable_selection()
        self.set_status(status_text.format(removed=len(texts)))

    # =========================
    # UI actions / slots
    # =========================
    def open_settings(self):
        old_catalog = self.processor.catalog
        old_default_output_name = old_catalog.export.default_output_name
        old_log = self.get_all_items(self.list_log)
        old_linear = self.get_all_items(self.list_linear)
        old_mean = self.combo_mean_variable.currentData()
        old_preset = self.combo_preset.currentText()

        dialog = SettingsDialog(
            current_config_path=self.processor.catalog.config_path,
            user_config_path=self.user_variable_config_path,
            default_config_path=self.default_variable_config_path,
            name_order=self.get_config()["name_order"],
            parent=self,
        )
        if not dialog.exec():
            return

        self.settings.setValue("name_order", dialog.combo_name_order.currentText())

        try:
            processor = RheoDataProcessor(self.user_variable_config_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Settings error",
                f"Saved settings could not be loaded.\n\n{type(exc).__name__}: {exc}",
            )
            return

        def remap(values):
            remapped = []
            seen = set()
            for value in values:
                for key in old_catalog.selection_keys(str(value)):
                    display_name = processor.catalog.canonical_display_name(key)
                    if display_name is not None and display_name not in seen:
                        remapped.append(display_name)
                        seen.add(display_name)
            return remapped

        self.processor = processor
        self.igor_builder = IgorCommandBuilder(processor.catalog)
        self.excel_exporter = ExcelExporter(processor)
        self.preset_profiles = processor.preset_profiles
        self.available_vars = processor.get_clean_variable_list()

        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItems(list(self.preset_profiles.keys()))
        preset_index = self.combo_preset.findText(old_preset)
        if preset_index >= 0:
            self.combo_preset.setCurrentIndex(preset_index)
        self.combo_preset.blockSignals(False)
        self.settings.setValue("preset", self.combo_preset.currentText())

        self.list_available.clear()
        self.list_available.addItems(self.available_vars)
        self.list_log.clear()
        self.list_log.addItems(remap(old_log))
        self.list_linear.clear()
        self.list_linear.addItems(remap(old_linear))

        remapped_mean = remap([old_mean]) if old_mean else []
        self.combo_mean_variable.blockSignals(True)
        self.combo_mean_variable.clear()
        self.combo_mean_variable.addItem("(none)", None)
        for variable_name in self.available_vars:
            self.combo_mean_variable.addItem(variable_name, variable_name)
        if remapped_mean:
            mean_index = self.combo_mean_variable.findData(remapped_mean[0])
            if mean_index >= 0:
                self.combo_mean_variable.setCurrentIndex(mean_index)
        self.combo_mean_variable.blockSignals(False)
        self.settings.setValue(
            "mean_variable", self.combo_mean_variable.currentData() or ""
        )

        if self.edit_out.text().strip() in {"", old_default_output_name}:
            self.edit_out.setText(processor.catalog.export.default_output_name)
        if not processor.catalog.igor.remember_selection:
            axis_index = self.combo_igor_axis.findText(
                processor.catalog.igor.default_axis
            )
            if axis_index >= 0:
                self.combo_igor_axis.setCurrentIndex(axis_index)

        self._save_variable_selection()
        self.last_result = None
        self.last_saved_path = None
        self.table_names.setRowCount(0)
        self.combo_igor_x.blockSignals(True)
        self.list_igor_y.blockSignals(True)
        self.combo_igor_x.clear()
        self.list_igor_y.clear()
        self.combo_igor_x.blockSignals(False)
        self.list_igor_y.blockSignals(False)
        self.text_igor.clear()
        self.set_export_buttons_enabled(False)
        self.set_status("Settings saved. Run again to process data with the new settings.")

    def select_folder(self):
        start_dir = self.selected_dir if self.selected_dir else ""
        folder = QFileDialog.getExistingDirectory(self, "入力フォルダを選択", start_dir)
        if folder:
            self.selected_dir = folder
            self.label_dir_path.setText(folder)
            self.btn_open_dir.setEnabled(True)
            self.settings.setValue("input_dir", folder)
            self.set_status(f"Input folder selected: {folder}")

    def open_selected_folder(self):
        if not self.selected_dir:
            return

        folder = Path(self.selected_dir)
        if not folder.is_dir():
            self.set_status(f"Error: folder not found: {folder}")
            QMessageBox.warning(self, "警告", f"フォルダが見つかりません。\n{folder}")
            return

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.set_status(f"Opened in Finder: {folder}")
        else:
            self.set_status(f"Error: could not open folder: {folder}")
            QMessageBox.warning(self, "警告", f"Finderでフォルダを開けませんでした。\n{folder}")

    def apply_preset(self, preset_name):
        profile = self.preset_profiles.get(preset_name, {})
        new_log = list(profile.get("log10", []))
        new_linear = list(profile.get("linear", []))

        self.list_available.clear()
        self.list_log.clear()
        self.list_linear.clear()

        self.list_available.addItems(self.available_vars)
        self.list_log.addItems(new_log)
        self.list_linear.addItems(new_linear)

        mean_variable = profile.get("mean_variable")
        mean_index = self.combo_mean_variable.findData(mean_variable)
        self.combo_mean_variable.setCurrentIndex(mean_index if mean_index >= 0 else 0)
        self.check_recursive.setChecked(bool(profile.get("recursive", False)))

        self._save_variable_selection()
        self.set_status(f"Preset applied: {preset_name}")

    def move_available_to_log(self):
        self._copy_items(
            self.list_available,
            self.list_log,
            "Copied {added} item(s) to log10.",
        )

    def move_available_to_linear(self):
        self._copy_items(
            self.list_available,
            self.list_linear,
            "Copied {added} item(s) to linear.",
        )

    def move_linear_to_log(self):
        self._move_items(
            self.list_linear,
            self.list_log,
            "Moved {added} item(s) from linear to log10.",
        )

    def move_log_to_linear(self):
        self._move_items(
            self.list_log,
            self.list_linear,
            "Moved {added} item(s) from log10 to linear.",
        )

    def remove_selected_from_outputs(self):
        # The available list is kept unchanged; "back" only removes selected
        # items from the log10 and linear output lists.
        removed_log = len(self.remove_selected_items(self.list_log))
        removed_linear = len(self.remove_selected_items(self.list_linear))
        removed_total = removed_log + removed_linear
        self._save_variable_selection()
        self.set_status(f"Removed {removed_total} item(s) from output selections.")

    def _save_igor_selection(self, *_args):
        if not self.processor.catalog.igor.remember_selection:
            return
        if not all(
            hasattr(self, name)
            for name in ("combo_igor_x", "list_igor_y", "combo_igor_axis")
        ):
            return
        self.settings.setValue("igor_x", self.combo_igor_x.currentText())
        self.settings.setValue(
            "igor_y", [item.text() for item in self.list_igor_y.selectedItems()]
        )
        self.settings.setValue("igor_axis", self.combo_igor_axis.currentText())

    def update_igor_options(self, result=None):
        result = result or self.last_result
        if result is None:
            keys = []
        else:
            try:
                data_name_set = self.processor.make_output_data_name_set(result)
            except Exception:
                data_name_set = result.data_name_set
            keys = self.igor_builder.get_processed_keys(data_name_set)

        # Keep the generated IGOR command text when Run is pressed again.
        # Only the candidate x/y variable lists are refreshed here.
        current_x = self.combo_igor_x.currentText()
        current_y = [item.text() for item in self.list_igor_y.selectedItems()]
        if self.processor.catalog.igor.remember_selection:
            if not current_x:
                current_x = self.settings.value("igor_x", "", type=str)
            if not current_y:
                current_y = self._get_setting_list("igor_y")

        self.combo_igor_x.blockSignals(True)
        self.list_igor_y.blockSignals(True)
        self.combo_igor_x.clear()
        self.list_igor_y.clear()

        self.combo_igor_x.addItems(keys)
        self.list_igor_y.addItems(keys)

        if current_x:
            idx = self.combo_igor_x.findText(current_x)
            if idx >= 0:
                self.combo_igor_x.setCurrentIndex(idx)
        selected_y = set(current_y)
        for index in range(self.list_igor_y.count()):
            item = self.list_igor_y.item(index)
            item.setSelected(item.text() in selected_y)
        self.combo_igor_x.blockSignals(False)
        self.list_igor_y.blockSignals(False)
        self._save_igor_selection()

        if self.text_igor.toPlainText().strip():
            self.set_status(
                f"Completed. IGOR keys updated: {len(keys)}. Existing IGOR command was kept."
            )
        else:
            self.set_status(f"Completed. IGOR keys updated: {len(keys)}")

    def make_igor_command(self):
        x_name = self.combo_igor_x.currentText()
        y_names = [item.text() for item in self.list_igor_y.selectedItems()]
        lr = self.combo_igor_axis.currentText()

        if not x_name:
            QMessageBox.warning(self, "警告", "x を選択してください。")
            return

        if not y_names:
            QMessageBox.warning(self, "警告", "y を1つ以上選択してください。")
            return

        if self.last_result is None:
            QMessageBox.warning(self, "警告", "先に Run を実行してください。")
            return

        if not self.sync_name_map_from_table():
            return

        try:
            output_data_name_set = self.processor.make_output_data_name_set(self.last_result)
            cmd = self.igor_builder.build_command(
                data_name_set=output_data_name_set,
                x_data_name=x_name,
                list_y_data_name=y_names,
                LR=lr,
            )
            self.text_igor.setPlainText(cmd)
            self.set_status("IGOR command generated with output_name.")
        except Exception as e:
            self.set_status(f"Error: {type(e).__name__}: {e}")
            QMessageBox.critical(self, "Error", f"{type(e).__name__}\n{e}")

    def copy_igor_command(self):
        text = self.text_igor.toPlainText()
        if not text.strip():
            self.set_status("No IGOR command to copy.")
            return

        QApplication.clipboard().setText(text)
        self.set_status("IGOR command copied to clipboard.")

    def validate_run_inputs(self, cfg: dict) -> bool:
        if not cfg["input_dir"]:
            self.set_status("Error: input folder is not selected.")
            QMessageBox.warning(self, "警告", "input folder を選択してください。")
            return False

        if not cfg["log10_vars"] and not cfg["linear_vars"]:
            self.set_status("Error: no variables selected.")
            QMessageBox.warning(self, "警告", "log10 または linear に変数を入れてください。")
            return False

        return True

    def validate_export_inputs(self, cfg: dict) -> bool:
        if self.last_result is None:
            self.set_status("Error: no processed data. Run first.")
            QMessageBox.warning(self, "警告", "先に Run を実行してください。")
            return False

        if not cfg["input_dir"]:
            self.set_status("Error: input folder is not selected.")
            QMessageBox.warning(self, "警告", "input folder を選択してください。")
            return False

        if not cfg["output_name"]:
            self.set_status("Error: output file name is empty.")
            QMessageBox.warning(self, "警告", "output file name を入力してください。")
            return False

        if cfg["mean_variable"] != self.last_result.mean_variable:
            self.set_status("Error: Mean header selection has not been applied. Run again.")
            QMessageBox.warning(
                self,
                "警告",
                "Mean header の選択が変更されています。Run を再実行してください。",
            )
            return False

        return True

    def make_processor_config(self, cfg: dict) -> ProcessorConfig:
        return ProcessorConfig(
            name_order=cfg["name_order"],
            log10_vars=cfg["log10_vars"][:],
            linear_vars=cfg["linear_vars"][:],
            mean_variable=cfg["mean_variable"],
        )

    def get_current_igor_command(self) -> str:
        text = self.text_igor.toPlainText().strip()
        if text:
            return text
        return "IGOR command was not generated."

    def run_processing(self):
        cfg = self.get_config()
        if not self.validate_run_inputs(cfg):
            return

        previous_name_map = None
        if self.last_result is not None and self.table_names.rowCount() > 0:
            if not self.sync_name_map_from_table():
                return
            previous_name_map = self.last_result.name_map.copy()

        self.set_status("Running...")
        self.set_export_buttons_enabled(False)

        try:
            self._save_variable_selection()
            config = self.make_processor_config(cfg)

            result = self.processor.load_and_process_directory(
                input_dir=Path(cfg["input_dir"]),
                recursive=cfg["recursive"],
                config=config,
            )
            self.processor.apply_existing_name_map_edits(result, previous_name_map)

            self.last_result = result
            self.last_saved_path = None
            self.update_name_table(result)
            self.update_igor_options(result)
            self.set_export_buttons_enabled(True)

            exported_count = int(result.name_map["export"].astype(bool).sum()) if not result.name_map.empty else 0
            format_counts = result.format_counts
            skipped_reports = result.skipped_reports
            self.set_status(
                f"Completed. files={len(result.processed_files)}, "
                f"RheoPlus={format_counts.get('RheoPlus', 0)}, "
                f"RheoCompass={format_counts.get('RheoCompass', 0)}, "
                f"skipped={len(skipped_reports)}, "
                f"original={result.original.shape}, "
                f"variables={result.variables.shape}, "
                f"exported_columns={exported_count}, "
                f"mean_header={config.mean_variable or '(blank)'}, "
                f"name_order={config.name_order}. Ready to export."
            )

            message = (
                "処理が完了しました。\n\n"
                f"processed files: {len(result.processed_files)}\n"
                f"RheoPlus detected: {format_counts.get('RheoPlus', 0)}\n"
                f"RheoCompass detected: {format_counts.get('RheoCompass', 0)}\n"
                f"skipped/no selected data: {len(skipped_reports)}\n"
                f"original shape: {result.original.shape}\n"
                f"variables shape before export filter: {result.variables.shape}\n"
                f"exported columns: {exported_count}\n"
                f"name_map rows: {len(result.name_map)}\n"
                "Excel は Export Excel で出力してください。"
            )
            if skipped_reports:
                details = "\n".join(
                    f"- {report.path.name}: {report.message}"
                    for report in skipped_reports[:10]
                )
                if len(skipped_reports) > 10:
                    details += "\n- ..."
                message += "\n\nSkipped details:\n" + details
                QMessageBox.warning(self, "完了（警告あり）", message)
            else:
                QMessageBox.information(self, "完了", message)

            if self.processor.catalog.export.auto_export:
                self.export_current_excel()

        except Exception as e:
            self.set_export_buttons_enabled(self.last_result is not None)
            self.set_status(f"Error: {type(e).__name__}: {e}")
            QMessageBox.critical(self, "Error", f"{type(e).__name__}\n{e}")

    def export_current_excel(self):
        cfg = self.get_config()
        if not self.validate_export_inputs(cfg):
            return

        if not self.sync_name_map_from_table():
            return

        self.set_status("Exporting Excel...")

        try:
            output_path = self.resolve_export_path()
            if output_path is None:
                self.set_status("Excel export cancelled.")
                return
            igor_command = self.get_current_igor_command()
            export_settings = self.processor.catalog.export

            saved_path = self.excel_exporter.export(
                self.last_result,
                output_path,
                use_output_names=True,
                include_original=export_settings.include_original,
                include_name_map=export_settings.include_name_map,
                igor_command=igor_command,
                include_igor_command=export_settings.include_igor_command,
            )

            self.last_saved_path = saved_path
            exported_count = int(self.last_result.name_map["export"].astype(bool).sum()) if not self.last_result.name_map.empty else 0
            self.set_status(
                f"Excel exported. exported_columns={exported_count}, saved={saved_path.name}"
            )

            sheet_names = ["variables"]
            if export_settings.include_original:
                sheet_names.insert(0, "original")
            if export_settings.include_name_map:
                sheet_names.append("name_map")
            if export_settings.include_igor_command:
                sheet_names.append("igor_command")
            QMessageBox.information(
                self,
                "Export 完了",
                "Excel を出力しました。\n\n"
                f"exported columns: {exported_count}\n"
                f"sheets: {', '.join(sheet_names)}\n"
                f"saved to:\n{saved_path}"
            )

        except Exception as e:
            self.set_status(f"Error: {type(e).__name__}: {e}")
            QMessageBox.critical(self, "Export error", f"{type(e).__name__}\n{e}")

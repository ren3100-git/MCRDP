from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mcrdp.naming import NAME_ORDERS
from mcrdp.variables import VariableCatalog


VARIABLE_COLUMNS = (
    "key",
    "display_name",
    "aliases (; separated)",
    "igor_label",
    "unit",
    "show_in_ui",
    "selection_keys (; separated)",
)


class SettingsDialog(QDialog):
    """Edit application preferences and the per-user variable catalog."""

    def __init__(
        self,
        current_config_path: Path,
        user_config_path: Path,
        default_config_path: Path,
        name_order: str,
        parent=None,
    ):
        super().__init__(parent)
        self.current_config_path = Path(current_config_path)
        self.user_config_path = Path(user_config_path)
        self.default_config_path = Path(default_config_path)

        self.setWindowTitle("Settings")
        self.resize(1050, 650)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(name_order), "General")
        self.tabs.addTab(self._build_variables_tab(), "Variables")
        self.tabs.addTab(self._build_presets_tab(), "Presets")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save_and_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.buttons)

        self._load_path(self.current_config_path)

    def _build_general_tab(self, name_order: str) -> QWidget:
        tab = QWidget()
        self.combo_name_order = QComboBox()
        self.combo_name_order.addItems(NAME_ORDERS)
        index = self.combo_name_order.findText(name_order)
        if index >= 0:
            self.combo_name_order.setCurrentIndex(index)

        self.edit_separator = QLineEdit("_")
        self.edit_separator.setMaximumWidth(100)
        self.spin_number_digits = QSpinBox()
        self.spin_number_digits.setRange(1, 9)
        self.spin_number_digits.setValue(3)
        self.spin_number_start = QSpinBox()
        self.spin_number_start.setRange(0, 999999999)
        self.check_strip_trailing_number = QCheckBox(
            "Remove trailing _number from sample names"
        )
        self.check_strip_trailing_number.setChecked(True)

        naming_form = QFormLayout()
        naming_form.addRow("Column name order:", self.combo_name_order)
        naming_form.addRow("Separator:", self.edit_separator)
        naming_form.addRow("Number digits:", self.spin_number_digits)
        naming_form.addRow("Number starts at:", self.spin_number_start)
        naming_form.addRow("", self.check_strip_trailing_number)

        naming_group = QGroupBox("Column and sample naming")
        naming_group.setLayout(naming_form)

        self.replacements_table = QTableWidget(0, 2)
        self.replacements_table.setHorizontalHeaderLabels(["Find", "Replace with"])
        self.replacements_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.replacements_table.setMaximumHeight(150)
        add_replacement = QPushButton("Add replacement")
        remove_replacement = QPushButton("Remove selected")
        add_replacement.clicked.connect(self._add_replacement_row)
        remove_replacement.clicked.connect(
            lambda: self._remove_selected_rows(self.replacements_table)
        )
        replacement_buttons = QHBoxLayout()
        replacement_buttons.addWidget(add_replacement)
        replacement_buttons.addWidget(remove_replacement)
        replacement_buttons.addStretch()
        replacement_layout = QVBoxLayout()
        replacement_layout.addLayout(replacement_buttons)
        replacement_layout.addWidget(self.replacements_table)
        replacement_group = QGroupBox("Sample-name replacements")
        replacement_group.setLayout(replacement_layout)

        self.edit_default_output_name = QLineEdit("sorted.xlsx")
        self.check_include_original = QCheckBox("Include original sheet")
        self.check_include_name_map = QCheckBox("Include name_map sheet")
        self.check_include_igor = QCheckBox("Include igor_command sheet")
        for checkbox in (
            self.check_include_original,
            self.check_include_name_map,
            self.check_include_igor,
        ):
            checkbox.setChecked(True)
        self.combo_conflict_policy = QComboBox()
        self.combo_conflict_policy.addItems(["ask", "overwrite", "auto_number"])
        self.check_auto_export = QCheckBox("Export automatically after Run")
        export_form = QFormLayout()
        export_form.addRow("Default output filename:", self.edit_default_output_name)
        export_form.addRow("If the file already exists:", self.combo_conflict_policy)
        export_form.addRow("", self.check_include_original)
        export_form.addRow("", self.check_include_name_map)
        export_form.addRow("", self.check_include_igor)
        export_form.addRow("", self.check_auto_export)
        export_group = QGroupBox("Excel export")
        export_group.setLayout(export_form)

        self.combo_default_axis = QComboBox()
        self.combo_default_axis.addItems(["L", "R"])
        self.check_remember_igor = QCheckBox("Remember the last x/y selections and axis")
        self.check_remember_igor.setChecked(True)
        igor_form = QFormLayout()
        igor_form.addRow("Default y axis:", self.combo_default_axis)
        igor_form.addRow("", self.check_remember_igor)
        igor_group = QGroupBox("IGOR Command")
        igor_group.setLayout(igor_form)

        layout = QVBoxLayout(tab)
        layout.addWidget(naming_group)
        layout.addWidget(replacement_group)
        layout.addWidget(export_group)
        layout.addWidget(igor_group)
        layout.addStretch()
        return tab

    def _build_variables_tab(self) -> QWidget:
        tab = QWidget()
        self.variables_table = QTableWidget(0, len(VARIABLE_COLUMNS))
        self.variables_table.setHorizontalHeaderLabels(VARIABLE_COLUMNS)
        self.variables_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.variables_table.setColumnWidth(0, 100)
        self.variables_table.setColumnWidth(1, 160)
        self.variables_table.setColumnWidth(2, 290)
        self.variables_table.setColumnWidth(3, 130)
        self.variables_table.setColumnWidth(4, 100)
        self.variables_table.setColumnWidth(5, 100)
        self.variables_table.setColumnWidth(6, 190)
        self.variables_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.variables_table.setAlternatingRowColors(True)

        add_button = QPushButton("Add variable")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(self._add_variable_row)
        remove_button.clicked.connect(
            lambda: self._remove_selected_rows(self.variables_table)
        )

        tools = QHBoxLayout()
        tools.addWidget(add_button)
        tools.addWidget(remove_button)
        tools.addStretch()

        note = QLabel(
            "Aliases and selection_keys are separated with semicolons. "
            "show_in_ui controls whether the variable appears in the main selection lists."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(tab)
        layout.addLayout(tools)
        layout.addWidget(self.variables_table, 1)
        layout.addWidget(note)
        return tab

    def _build_presets_tab(self) -> QWidget:
        tab = QWidget()
        self.presets_table = QTableWidget(0, 5)
        self.presets_table.setHorizontalHeaderLabels([
            "preset name",
            "log10 keys (; separated)",
            "linear keys (; separated)",
            "mean key",
            "recursive",
        ])
        self.presets_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.presets_table.setColumnWidth(0, 220)
        self.presets_table.setColumnWidth(1, 280)
        self.presets_table.setColumnWidth(2, 280)
        self.presets_table.setColumnWidth(3, 120)
        self.presets_table.setColumnWidth(4, 90)
        self.presets_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.presets_table.setAlternatingRowColors(True)

        add_button = QPushButton("Add preset")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(self._add_preset_row)
        remove_button.clicked.connect(
            lambda: self._remove_selected_rows(self.presets_table)
        )

        import_button = QPushButton("Import JSON…")
        export_button = QPushButton("Export JSON…")
        defaults_button = QPushButton("Restore defaults")
        import_button.clicked.connect(self.import_json)
        export_button.clicked.connect(self.export_json)
        defaults_button.clicked.connect(self.restore_defaults)

        tools = QHBoxLayout()
        tools.addWidget(add_button)
        tools.addWidget(remove_button)
        tools.addStretch()
        tools.addWidget(import_button)
        tools.addWidget(export_button)
        tools.addWidget(defaults_button)

        note = QLabel(
            "Import and Restore update this dialog first. Click Save to apply the changes."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(tab)
        layout.addLayout(tools)
        layout.addWidget(self.presets_table, 1)
        layout.addWidget(note)
        return tab

    @staticmethod
    def _text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()

    @staticmethod
    def _split(value: str) -> list[str]:
        return [part.strip() for part in value.split(";") if part.strip()]

    @staticmethod
    def _checked_item(checked: bool) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        return item

    def _add_variable_row(self, item: dict | None = None) -> None:
        item = item or {}
        row = self.variables_table.rowCount()
        self.variables_table.insertRow(row)
        values = (
            str(item.get("key", "")),
            str(item.get("display_name", "")),
            "; ".join(str(value) for value in item.get("aliases", [])),
            str(item.get("igor_label", "")),
            str(item.get("unit", "")),
        )
        for column, value in enumerate(values):
            self.variables_table.setItem(row, column, QTableWidgetItem(value))
        self.variables_table.setItem(
            row, 5, self._checked_item(bool(item.get("show_in_ui", True)))
        )
        selection_keys = item.get("selection_keys")
        if selection_keys is None and item.get("key"):
            selection_keys = [item["key"]]
        self.variables_table.setItem(
            row,
            6,
            QTableWidgetItem("; ".join(str(value) for value in (selection_keys or []))),
        )

    def _add_replacement_row(self, source: str = "", replacement: str = "") -> None:
        row = self.replacements_table.rowCount()
        self.replacements_table.insertRow(row)
        self.replacements_table.setItem(row, 0, QTableWidgetItem(source))
        self.replacements_table.setItem(row, 1, QTableWidgetItem(replacement))

    def _add_preset_row(self, name: str = "", profile: dict | list | None = None) -> None:
        if isinstance(profile, list):
            profile = {"log10": profile}
        profile = profile or {}
        row = self.presets_table.rowCount()
        self.presets_table.insertRow(row)
        self.presets_table.setItem(row, 0, QTableWidgetItem(name))
        self.presets_table.setItem(
            row, 1, QTableWidgetItem("; ".join(profile.get("log10", [])))
        )
        self.presets_table.setItem(
            row, 2, QTableWidgetItem("; ".join(profile.get("linear", [])))
        )
        self.presets_table.setItem(
            row, 3, QTableWidgetItem(str(profile.get("mean_variable") or ""))
        )
        self.presets_table.setItem(
            row, 4, self._checked_item(bool(profile.get("recursive", False)))
        )

    @staticmethod
    def _remove_selected_rows(table: QTableWidget) -> None:
        rows = sorted({item.row() for item in table.selectedItems()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    def _load_path(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            self._populate(raw)
        except Exception as exc:
            QMessageBox.critical(
                self, "Settings error", f"Could not load settings.\n\n{type(exc).__name__}: {exc}"
            )

    def _populate(self, raw: dict) -> None:
        naming = raw.get("naming", {})
        order = str(naming.get("order", self.combo_name_order.currentText()))
        order_index = self.combo_name_order.findText(order)
        if order_index >= 0:
            self.combo_name_order.setCurrentIndex(order_index)
        self.edit_separator.setText(str(naming.get("separator", "_")))
        self.spin_number_digits.setValue(int(naming.get("number_digits", 3)))
        self.spin_number_start.setValue(int(naming.get("number_start", 0)))
        self.check_strip_trailing_number.setChecked(
            bool(naming.get("strip_trailing_number", True))
        )
        replacements = naming.get(
            "replacements", {".": "r", "/": "per", "%": "percent"}
        )
        self.replacements_table.setRowCount(0)
        for source, replacement in replacements.items():
            self._add_replacement_row(str(source), str(replacement))

        export = raw.get("export", {})
        self.edit_default_output_name.setText(
            str(export.get("default_output_name", "sorted.xlsx"))
        )
        self.check_include_original.setChecked(bool(export.get("include_original", True)))
        self.check_include_name_map.setChecked(bool(export.get("include_name_map", True)))
        self.check_include_igor.setChecked(bool(export.get("include_igor_command", True)))
        conflict_index = self.combo_conflict_policy.findText(
            str(export.get("conflict_policy", "ask"))
        )
        if conflict_index >= 0:
            self.combo_conflict_policy.setCurrentIndex(conflict_index)
        self.check_auto_export.setChecked(bool(export.get("auto_export", False)))

        igor = raw.get("igor", {})
        axis_index = self.combo_default_axis.findText(str(igor.get("default_axis", "L")))
        if axis_index >= 0:
            self.combo_default_axis.setCurrentIndex(axis_index)
        self.check_remember_igor.setChecked(bool(igor.get("remember_selection", True)))

        self.variables_table.setRowCount(0)
        for item in raw.get("variables", []):
            self._add_variable_row(item)

        self.presets_table.setRowCount(0)
        for name, profile in raw.get("presets", {}).items():
            if isinstance(profile, list):
                normalized_profile = [str(key) for key in profile]
            else:
                normalized_profile = {
                    "log10": [str(key) for key in profile.get("log10", [])],
                    "linear": [str(key) for key in profile.get("linear", [])],
                    "mean_variable": profile.get("mean_variable"),
                    "recursive": bool(profile.get("recursive", False)),
                }
            self._add_preset_row(str(name), normalized_profile)

    def _to_raw(self) -> dict:
        variables = []
        for row in range(self.variables_table.rowCount()):
            key = self._text(self.variables_table, row, 0)
            show_item = self.variables_table.item(row, 5)
            item = {
                "key": key,
                "display_name": self._text(self.variables_table, row, 1),
                "aliases": self._split(self._text(self.variables_table, row, 2)),
                "igor_label": self._text(self.variables_table, row, 3),
                "unit": self._text(self.variables_table, row, 4),
                "show_in_ui": bool(
                    show_item is not None
                    and show_item.checkState() == Qt.CheckState.Checked
                ),
                "selection_keys": self._split(self._text(self.variables_table, row, 6))
                or ([key] if key else []),
            }
            variables.append(item)

        presets = {}
        for row in range(self.presets_table.rowCount()):
            name = self._text(self.presets_table, row, 0)
            if not name:
                raise ValueError(f"Preset name is empty in row {row + 1}")
            if name in presets:
                raise ValueError(f"Duplicate preset name: {name}")
            recursive_item = self.presets_table.item(row, 4)
            presets[name] = {
                "log10": self._split(self._text(self.presets_table, row, 1)),
                "linear": self._split(self._text(self.presets_table, row, 2)),
                "mean_variable": self._text(self.presets_table, row, 3) or None,
                "recursive": bool(
                    recursive_item is not None
                    and recursive_item.checkState() == Qt.CheckState.Checked
                ),
            }

        replacements = {}
        for row in range(self.replacements_table.rowCount()):
            source = self._text(self.replacements_table, row, 0)
            if not source:
                raise ValueError(f"Replacement source is empty in row {row + 1}")
            if source in replacements:
                raise ValueError(f"Duplicate replacement source: {source}")
            replacements[source] = self._text(self.replacements_table, row, 1)

        return {
            "schema_version": 2,
            "variables": variables,
            "presets": presets,
            "naming": {
                "order": self.combo_name_order.currentText(),
                "separator": self.edit_separator.text(),
                "number_digits": self.spin_number_digits.value(),
                "number_start": self.spin_number_start.value(),
                "replacements": replacements,
                "strip_trailing_number": self.check_strip_trailing_number.isChecked(),
            },
            "export": {
                "default_output_name": self.edit_default_output_name.text().strip(),
                "include_original": self.check_include_original.isChecked(),
                "include_name_map": self.check_include_name_map.isChecked(),
                "include_igor_command": self.check_include_igor.isChecked(),
                "conflict_policy": self.combo_conflict_policy.currentText(),
                "auto_export": self.check_auto_export.isChecked(),
            },
            "igor": {
                "default_axis": self.combo_default_axis.currentText(),
                "remember_selection": self.check_remember_igor.isChecked(),
            },
        }

    def _validated_raw(self) -> dict:
        raw = self._to_raw()
        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="variables-", suffix=".json", dir=self.user_config_path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            VariableCatalog(temporary_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return raw

    @staticmethod
    def _write_raw(path: Path, raw: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            temporary_path.replace(path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def import_json(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import variable settings", "", "JSON files (*.json);;All files (*)"
        )
        if not filename:
            return
        try:
            VariableCatalog(filename)
            with Path(filename).open("r", encoding="utf-8") as handle:
                self._populate(json.load(handle))
        except Exception as exc:
            QMessageBox.critical(
                self, "Import error", f"{type(exc).__name__}: {exc}"
            )

    def export_json(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export variable settings", "variables.json", "JSON files (*.json)"
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".json")
        try:
            raw = self._validated_raw()
            self._write_raw(path, raw)
            QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(
                self, "Export error", f"{type(exc).__name__}: {exc}"
            )

    def restore_defaults(self) -> None:
        self._load_path(self.default_config_path)

    def save_and_accept(self) -> None:
        try:
            raw = self._validated_raw()
            self._write_raw(self.user_config_path, raw)
        except Exception as exc:
            QMessageBox.critical(
                self, "Settings error", f"{type(exc).__name__}: {exc}"
            )
            return

        self.accept()

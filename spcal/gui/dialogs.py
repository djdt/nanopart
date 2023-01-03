from pathlib import Path
from typing import Dict, Generator, List, Tuple

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.gui.models import NumpyRecArrayTableModel, SearchColumnsProxyModel
from spcal.gui.units import (
    UnitsWidget,
    mass_units,
    molar_concentration_units,
    signal_units,
    size_units,
    time_units,
)
from spcal.gui.util import create_action
from spcal.gui.widgets import DoubleOrPercentValidator, ValidColorLineEdit
from spcal.io.text import export_single_particle_results, import_single_particle_file
from spcal.npdb import db
from spcal.result import SPCalResult


class HistogramOptionsDialog(QtWidgets.QDialog):
    fitChanged = QtCore.Signal(str)
    binWidthsChanged = QtCore.Signal(dict)

    def __init__(
        self,
        fit: str | None,
        bin_widths: Dict[str, float | None],
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Histogram Options")

        self.fit = fit
        self.bin_widths = bin_widths.copy()

        self.radio_fit_off = QtWidgets.QRadioButton("Off")
        self.radio_fit_norm = QtWidgets.QRadioButton("Normal")
        self.radio_fit_log = QtWidgets.QRadioButton("Log normal")

        fit_group = QtWidgets.QButtonGroup()
        for button in [self.radio_fit_off, self.radio_fit_norm, self.radio_fit_log]:
            fit_group.addButton(button)

        if self.fit is None:
            self.radio_fit_off.setChecked(True)
        elif self.fit == "normal":
            self.radio_fit_norm.setChecked(True)
        elif self.fit == "log normal":
            self.radio_fit_log.setChecked(True)
        else:
            raise ValueError("HistogramOptionsDialog: unknown fit")

        color = self.palette().color(QtGui.QPalette.Base)
        self.width_signal = UnitsWidget(
            signal_units,
            value=self.bin_widths["signal"],
            invalid_color=color,
            validator=QtGui.QIntValidator(0, 999999999),
        )
        self.width_mass = UnitsWidget(
            mass_units,
            value=self.bin_widths["mass"],
            invalid_color=color,
        )
        self.width_size = UnitsWidget(
            size_units, value=self.bin_widths["size"], invalid_color=color
        )
        self.width_conc = UnitsWidget(
            molar_concentration_units,
            value=self.bin_widths["cell_concentration"],
            invalid_color=color,
        )

        for widget in [
            self.width_signal,
            self.width_mass,
            self.width_size,
            self.width_conc,
        ]:
            widget.setBestUnit()
            widget.lineedit.setPlaceholderText("auto")

        box_fit = QtWidgets.QGroupBox("Curve Fit")
        box_fit.setLayout(QtWidgets.QHBoxLayout())
        for button in [self.radio_fit_off, self.radio_fit_norm, self.radio_fit_log]:
            box_fit.layout().addWidget(button)

        box_widths = QtWidgets.QGroupBox("Bin Widths")
        box_widths.setLayout(QtWidgets.QFormLayout())
        box_widths.layout().addRow("Signal:", self.width_signal)
        box_widths.layout().addRow("Mass:", self.width_mass)
        box_widths.layout().addRow("Size:", self.width_size)
        box_widths.layout().addRow("Concentration:", self.width_conc)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.RestoreDefaults
            | QtWidgets.QDialogButtonBox.Apply
            | QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.clicked.connect(self.buttonBoxClicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(box_fit)
        layout.addWidget(box_widths)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def buttonBoxClicked(self, button: QtWidgets.QAbstractButton) -> None:
        sbutton = self.button_box.standardButton(button)
        if sbutton == QtWidgets.QDialogButtonBox.RestoreDefaults:
            self.reset()
            self.apply()
        elif sbutton == QtWidgets.QDialogButtonBox.Apply:
            self.apply()
        elif sbutton == QtWidgets.QDialogButtonBox.Ok:
            self.apply()
            self.accept()
        else:
            self.reject()

    def apply(self) -> None:
        if self.radio_fit_off.isChecked():
            fit = None
        elif self.radio_fit_norm.isChecked():
            fit = "normal"
        else:
            fit = "log normal"

        bin_widths = {
            "signal": self.width_signal.baseValue(),
            "mass": self.width_mass.baseValue(),
            "size": self.width_size.baseValue(),
            "cell_concentration": self.width_conc.baseValue(),
        }

        # Check for changes
        if fit != self.fit:
            self.fit = fit
            self.fitChanged.emit(fit)
        if bin_widths != self.bin_widths:
            self.bin_widths = bin_widths
            self.binWidthsChanged.emit(bin_widths)

    def reset(self) -> None:
        self.radio_fit_log.setChecked(True)
        for widget in [
            self.width_signal,
            self.width_mass,
            self.width_size,
            self.width_conc,
        ]:
            widget.setBaseValue(None)


class CompositionsOptionsDialog(QtWidgets.QDialog):
    distanceChanged = QtCore.Signal(float)
    minimumSizeChanged = QtCore.Signal(str)

    def __init__(
        self,
        distance: float = 0.03,
        minimum_size: str | float = "5%",
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Composition Options")

        self.distance = distance
        self.minimum_size = minimum_size

        self.lineedit_distance = QtWidgets.QLineEdit(str(distance * 100.0))
        self.lineedit_distance.setValidator(QtGui.QDoubleValidator(0.1, 99.9, 1))

        self.lineedit_size = QtWidgets.QLineEdit(str(minimum_size))
        self.lineedit_size.setValidator(DoubleOrPercentValidator(0.0, 1e99, 3, 0, 100))

        layout_dist = QtWidgets.QHBoxLayout()
        layout_dist.addWidget(self.lineedit_distance, 1)
        layout_dist.addWidget(QtWidgets.QLabel("%"), 0)

        box = QtWidgets.QGroupBox("Clustering")
        box.setLayout(QtWidgets.QFormLayout())
        box.layout().addRow("Distance threshold", layout_dist)
        box.layout().addRow("Minimum cluster size", self.lineedit_size)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.RestoreDefaults
            | QtWidgets.QDialogButtonBox.Apply
            | QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.clicked.connect(self.buttonBoxClicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(box)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def buttonBoxClicked(self, button: QtWidgets.QAbstractButton) -> None:
        sbutton = self.button_box.standardButton(button)
        if sbutton == QtWidgets.QDialogButtonBox.RestoreDefaults:
            self.reset()
            self.apply()
        elif sbutton == QtWidgets.QDialogButtonBox.Apply:
            self.apply()
        elif sbutton == QtWidgets.QDialogButtonBox.Ok:
            self.apply()
            self.accept()
        else:
            self.reject()

    def apply(self) -> None:
        distance = float(self.lineedit_distance.text()) / 100.0
        size = self.lineedit_size.text().replace(" ", "")

        # Check for changes
        if abs(self.distance - distance) > 0.001:
            self.distance = distance
            self.distanceChanged.emit(distance)
        if size != self.minimum_size:
            self.minimum_size == size
            self.minimumSizeChanged.emit(str(size))

    def reset(self) -> None:
        self.lineedit_distance.setText(str(self.distance * 100.0))


class FilterRow(QtWidgets.QWidget):
    closeRequested = QtCore.Signal(QtWidgets.QWidget)

    def __init__(self, elements: List[str], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)

        self.boolean = QtWidgets.QComboBox()
        self.boolean.addItems(["And", "Or"])

        self.elements = QtWidgets.QComboBox()
        self.elements.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToContentsOnFirstShow
        )
        self.elements.addItems(elements)

        self.unit = QtWidgets.QComboBox()
        self.unit.addItems(["Intensity", "Mass", "Size"])
        self.unit.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContentsOnFirstShow)
        self.unit.currentTextChanged.connect(self.changeUnits)

        self.operation = QtWidgets.QComboBox()
        self.operation.addItems([">", "<", ">=", "<=", "=="])

        self.value = UnitsWidget(units=signal_units)
        self.value.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)

        self.action_close = create_action(
            "list-remove", "Remove", "Remove the filter.", self.close
        )

        self.button_close = QtWidgets.QToolButton()
        self.button_close.setAutoRaise(True)
        self.button_close.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.button_close.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.button_close.setDefaultAction(self.action_close)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.boolean, 0)
        layout.addWidget(self.elements, 0)
        layout.addWidget(self.unit, 0)
        layout.addWidget(self.operation, 0)
        layout.addWidget(self.value, 1)
        layout.addWidget(self.button_close, 0, QtCore.Qt.AlignRight)
        self.setLayout(layout)

    def asTuple(self) -> Tuple[str, str, str, str, float | None]:
        return (
            self.boolean.currentText(),
            self.elements.currentText(),
            self.unit.currentText(),
            self.operation.currentText(),
            self.value.baseValue(),
        )

    def close(self) -> None:
        self.closeRequested.emit(self)
        super().close()

    def changeUnits(self, unit: str) -> None:
        if unit == "Intensity":
            units = signal_units
        elif unit == "Mass":
            units = mass_units
        elif unit == "Size":
            units = size_units
        else:
            raise ValueError("changeUnits: unknown unit")

        self.value.setUnits(units)


class FilterRows(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)

        self.rows: List[FilterRow] = []

        widget = QtWidgets.QWidget()
        self.setWidget(widget)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.setSpacing(0)
        widget.setLayout(self.layout)

    def addRow(self, row: FilterRow) -> None:
        row.closeRequested.connect(self.removeRow)
        if len(self.rows) == 0:
            row.boolean.setEnabled(False)
        self.rows.append(row)
        self.layout.addWidget(row)

    def removeRow(self, row: FilterRow) -> None:
        self.rows.remove(row)
        self.layout.removeWidget(row)

    def asList(self) -> List[Tuple[str, str, str, str, float]]:
        filters = []
        for row in self.rows:
            filter = row.asTuple()
            if filter[-1] is not None:
                filters.append(filter)
        return filters  # type: ignore


class FilterDialog(QtWidgets.QDialog):
    filtersChanged = QtCore.Signal(list)

    def __init__(
        self,
        elements: List[str],
        filters: list,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Compositional Filters")
        self.setMinimumSize(600, 480)

        self.elements = elements
        self.rows = FilterRows()

        for filter in filters:
            self.addFilter(filter)

        self.action_add = create_action(
            "list-add", "Add Filter", "Add a new filter.", lambda: self.addFilter(None)
        )

        self.button_add = QtWidgets.QToolButton()
        self.button_add.setAutoRaise(True)
        self.button_add.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.button_add.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.button_add.setDefaultAction(self.action_add)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Close
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.button_add, 0)
        layout.addWidget(self.rows, 1)
        layout.addWidget(self.button_box, 0)
        self.setLayout(layout)

    def addFilter(self, filter: Tuple[str, str, str, str, float] | None = None) -> None:
        row = FilterRow(self.elements, parent=self)
        if filter is not None:
            boolean, element, unit, operation, value = filter
            row.boolean.setCurrentText(boolean)
            row.elements.setCurrentText(element)
            row.unit.setCurrentText(unit)
            row.operation.setCurrentText(operation)
            row.value.setBaseValue(value)
            row.value.setBestUnit()

        self.rows.addRow(row)

    def accept(self) -> None:
        self.filtersChanged.emit(self.rows.asList())
        super().accept()


class ExportDialog(QtWidgets.QDialog):
    invalid_chars = '<>:"/\\|?*'

    def __init__(
        self,
        path: str | Path,
        results: Dict[str, SPCalResult],
        units: Dict[str, Tuple[str, float]] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Results Export Options")

        self.results = results

        _units = {"mass": "kg", "size": "m", "cell_concentration": "mol/L"}
        if units is not None:
            _units.update({k: v[0] for k, v in units.items()})

        filename_regexp = QtCore.QRegularExpression(f"[^{self.invalid_chars}]+")
        self.lineedit_path = QtWidgets.QLineEdit(str(Path(path).absolute()))
        self.lineedit_path.setMinimumWidth(300)
        self.lineedit_path.setValidator(
            QtGui.QRegularExpressionValidator(filename_regexp)
        )
        self.button_path = QtWidgets.QPushButton("Select File")
        self.button_path.clicked.connect(self.dialogFilePath)

        file_box = QtWidgets.QGroupBox("Save File")
        file_box.setLayout(QtWidgets.QHBoxLayout())
        file_box.layout().addWidget(self.lineedit_path, 1)
        file_box.layout().addWidget(self.button_path, 0)

        self.mass_units = QtWidgets.QComboBox()
        self.mass_units.addItems(mass_units.keys())
        self.mass_units.setCurrentText(_units["mass"])
        self.size_units = QtWidgets.QComboBox()
        self.size_units.addItems(size_units.keys())
        self.size_units.setCurrentText(_units["size"])
        self.conc_units = QtWidgets.QComboBox()
        self.conc_units.addItems(molar_concentration_units.keys())
        self.conc_units.setCurrentText(_units["cell_concentration"])

        units_box = QtWidgets.QGroupBox("Output Units")
        units_box.setLayout(QtWidgets.QFormLayout())
        units_box.layout().addRow("Mass units", self.mass_units)
        units_box.layout().addRow("Size units", self.size_units)
        units_box.layout().addRow("Conc. units", self.conc_units)

        self.check_export_inputs = QtWidgets.QCheckBox("Export options and inputs.")
        self.check_export_inputs.setChecked(True)
        self.check_export_arrays = QtWidgets.QCheckBox(
            "Export detected particle arrays."
        )
        self.check_export_arrays.setChecked(True)
        self.check_export_compositions = QtWidgets.QCheckBox(
            "Export peak compositions."
        )

        switches_box = QtWidgets.QGroupBox("Export options")
        switches_box.setLayout(QtWidgets.QVBoxLayout())
        switches_box.layout().addWidget(self.check_export_inputs)
        switches_box.layout().addWidget(self.check_export_arrays)
        switches_box.layout().addWidget(self.check_export_compositions)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(file_box)
        layout.addWidget(units_box)
        layout.addWidget(switches_box)
        layout.addWidget(self.button_box, 0)

        self.setLayout(layout)

    def dialogFilePath(self) -> QtWidgets.QFileDialog:
        dlg = QtWidgets.QFileDialog(
            self,
            "Save Results",
            self.lineedit_path.text(),
            "CSV Documents (*.csv);;All files (*)",
        )
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dlg.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        dlg.fileSelected.connect(self.lineedit_path.setText)
        dlg.open()

    def accept(self) -> None:
        units = {
            "mass": (
                self.mass_units.currentText(),
                mass_units[self.mass_units.currentText()],
            ),
            "size": (
                self.size_units.currentText(),
                size_units[self.size_units.currentText()],
            ),
            "conc": (
                self.conc_units.currentText(),
                molar_concentration_units[self.conc_units.currentText()],
            ),
        }

        export_single_particle_results(
            self.lineedit_path.text(),
            self.results,
            units_for_results=units,
            output_inputs=self.check_export_inputs.isChecked(),
            output_compositions=self.check_export_compositions.isChecked(),
            output_arrays=self.check_export_arrays.isChecked(),
        )
        super().accept()


class ImportDialog(QtWidgets.QDialog):
    dataImported = QtCore.Signal(np.ndarray, dict)

    forbidden_names = ["Overlay"]

    def __init__(self, path: str | Path, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)

        header_row_count = 10

        self.file_path = Path(path)
        self.file_header = [
            x for _, x in zip(range(header_row_count), self.file_path.open("r"))
        ]
        self.setWindowTitle(f"SPCal File Import: {self.file_path.name}")

        first_data_line = 0
        for line in self.file_header:
            try:
                float(line.split(",")[-1])
                break
            except ValueError:
                pass
            first_data_line += 1

        column_count = max([line.count(",") for line in self.file_header]) + 1

        self.table = QtWidgets.QTableWidget()
        self.table.itemChanged.connect(self.completeChanged)
        self.table.setMinimumSize(800, 400)
        self.table.setColumnCount(column_count)
        self.table.setRowCount(header_row_count)
        self.table.setFont(QtGui.QFont("Courier"))

        self.dwelltime = UnitsWidget(
            time_units,
            default_unit="ms",
            validator=QtGui.QDoubleValidator(0.0, 10.0, 10),
        )
        self.dwelltime.valueChanged.connect(self.completeChanged)

        self.combo_intensity_units = QtWidgets.QComboBox()
        self.combo_intensity_units.addItems(["Counts", "CPS"])
        if any("cps" in line.lower() for line in self.file_header):
            self.combo_intensity_units.setCurrentText("CPS")

        self.combo_delimiter = QtWidgets.QComboBox()
        self.combo_delimiter.addItems([",", ";", "Space", "Tab"])
        self.combo_delimiter.currentIndexChanged.connect(self.fillTable)

        self.spinbox_first_line = QtWidgets.QSpinBox()
        self.spinbox_first_line.setRange(1, header_row_count - 1)
        self.spinbox_first_line.setValue(first_data_line)
        self.spinbox_first_line.valueChanged.connect(self.updateTableIgnores)

        # self.combo_ignore_columns = QtWidgets.QComboBox()
        # self.combo_ignore_columns.addItems(["Use", "Ignore"])
        # self.combo_ignore_columns.setCurrentIndex(1)
        # self.combo_ignore_columns.currentTextChanged.connect(self.updateLEIgnores)

        self.le_ignore_columns = QtWidgets.QLineEdit()
        self.le_ignore_columns.setText("1;")
        self.le_ignore_columns.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression("[0-9;]+"))
        )
        self.le_ignore_columns.textChanged.connect(self.updateTableIgnores)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        import_form = QtWidgets.QFormLayout()
        import_form.addRow("Delimiter:", self.combo_delimiter)
        import_form.addRow("Import From Row:", self.spinbox_first_line)
        import_form.addRow("Ignore Columns:", self.le_ignore_columns)

        import_box = QtWidgets.QGroupBox("Import Options")
        import_box.setLayout(import_form)

        data_form = QtWidgets.QFormLayout()
        data_form.addRow("Dwell Time:", self.dwelltime)
        data_form.addRow("Intensity Units:", self.combo_intensity_units)

        data_box = QtWidgets.QGroupBox("Data Options")
        data_box.setLayout(data_form)

        box_layout = QtWidgets.QHBoxLayout()
        box_layout.addWidget(import_box, 1)
        box_layout.addWidget(data_box, 1)

        self.fillTable()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(box_layout)
        layout.addWidget(self.table)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def isComplete(self) -> bool:
        return self.dwelltime.hasAcceptableInput() and not any(
            x in self.forbidden_names for x in self.names()
        )

    def completeChanged(self) -> None:
        complete = self.isComplete()
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(complete)

    def delimiter(self) -> str:
        delimiter = self.combo_delimiter.currentText()
        if delimiter == "Space":
            delimiter = " "
        elif delimiter == "Tab":
            delimiter = "\t"
        return delimiter

    def ignoreColumns(self) -> List[int]:
        return [int(i or 0) - 1 for i in self.le_ignore_columns.text().split(";")]

    def useColumns(self) -> List[int]:
        return [
            c for c in range(self.table.columnCount()) if c not in self.ignoreColumns()
        ]

    def names(self) -> List[str]:
        return [
            self.table.item(self.spinbox_first_line.value() - 1, c).text()
            for c in self.useColumns()
        ]

    def fillTable(self) -> None:
        lines = [line.split(self.delimiter()) for line in self.file_header]
        col_count = max(len(line) for line in lines)
        self.table.setColumnCount(col_count)

        for row, line in enumerate(lines):
            line.extend([""] * (col_count - len(line)))
            for col, text in enumerate(line):
                item = QtWidgets.QTableWidgetItem(text.strip())
                self.table.setItem(row, col, item)

        self.table.resizeColumnsToContents()
        self.updateTableIgnores()

        if self.dwelltime.value() is None:
            self.readDwelltimeFromTable()

    def updateTableIgnores(self) -> None:
        header_row = self.spinbox_first_line.value() - 1
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is None:
                    continue
                if row != header_row:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
                if row < header_row or col in self.ignoreColumns():
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                else:
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsEnabled)

    # def updateLEIgnores(self, text: str) -> None:
    #     if text == "Ignore":
    #         pass
    #     elif text == "Use":
    #         pass

    def readDwelltimeFromTable(self) -> None:
        header_row = self.spinbox_first_line.value() - 1
        for col in range(self.table.columnCount()):
            text = self.table.item(header_row, col).text().lower()
            if "time" in text:
                try:
                    times = [
                        float(self.table.item(row, col).text().replace(",", "."))
                        for row in range(header_row + 1, self.table.rowCount())
                    ]
                except ValueError:
                    continue
                if "ms" in text:
                    factor = 1e-3
                elif "us" in text or "μs" in text:
                    factor = 1e-6
                else:  # assume that value is in seconds
                    factor = 1.0
                self.dwelltime.setBaseValue(
                    np.round(np.mean(np.diff(times)), 6) * factor  # type: ignore
                )
                break

    def importOptions(self) -> dict:
        return {
            "path": self.file_path,
            "dwelltime": self.dwelltime.baseValue(),
            "delimiter": self.delimiter(),
            "ignores": self.ignoreColumns(),
            "columns": self.useColumns(),
            "first line": self.spinbox_first_line.value(),
            "names": self.names(),
            "cps": self.combo_intensity_units.currentText() == "CPS",
        }

    def accept(self) -> None:
        options = self.importOptions()

        data, old_names = import_single_particle_file(
            options["path"],
            delimiter=options["delimiter"],
            columns=options["columns"],
            first_line=options["first line"],
            new_names=options["names"],
            convert_cps=options["dwelltime"] if options["cps"] else None,
        )
        # Save original names
        assert data.dtype.names is not None
        options["old names"] = old_names

        self.dataImported.emit(data, options)
        super().accept()


class FormulaValidator(QtGui.QValidator):
    def __init__(
        self, regex: QtCore.QRegularExpression, parent: QtCore.QObject | None = None
    ):
        super().__init__(parent)
        self.regex = regex

    def validate(self, input: str, _: int) -> QtGui.QValidator.State:
        iter = self.regex.globalMatch(input)
        if len(input) == 0:
            return QtGui.QValidator.Acceptable
        if not str.isalnum(input.replace(".", "")):
            return QtGui.QValidator.Invalid
        if not iter.hasNext():  # no match
            return QtGui.QValidator.Intermediate
        while iter.hasNext():
            match = iter.next()
            if match.captured(1) not in db["elements"]["Symbol"]:
                return QtGui.QValidator.Intermediate
        return QtGui.QValidator.Acceptable


class MassFractionCalculatorDialog(QtWidgets.QDialog):
    ratiosChanged = QtCore.Signal()
    ratiosSelected = QtCore.Signal(dict)
    molarMassSelected = QtCore.Signal(float)

    def __init__(self, formula: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Molar Ratio Calculator")
        self.resize(300, 120)

        self.regex = QtCore.QRegularExpression("([A-Z][a-z]?)([0-9\\.]*)")
        self.ratios: Dict[str, float] = {}
        self.mw = 0.0

        self.lineedit_formula = ValidColorLineEdit(formula)
        self.lineedit_formula.setPlaceholderText("Molecular Formula")
        self.lineedit_formula.setValidator(FormulaValidator(self.regex))
        self.lineedit_formula.textChanged.connect(self.recalculate)

        self.label_mw = QtWidgets.QLabel("MW = 0 g/mol")

        self.textedit_ratios = QtWidgets.QTextEdit()
        self.textedit_ratios.setReadOnly(True)
        self.textedit_ratios.setFont(QtGui.QFont("Courier"))

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        self.ratiosChanged.connect(self.updateLabels)
        self.ratiosChanged.connect(self.completeChanged)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.lineedit_formula, 0)
        layout.addWidget(self.label_mw, 0)
        layout.addWidget(self.textedit_ratios, 1)
        layout.addWidget(self.button_box, 0)

        self.setLayout(layout)
        self.completeChanged()

    def accept(self) -> None:
        self.ratiosSelected.emit(self.ratios)
        self.molarMassSelected.emit(self.mw)
        super().accept()

    def completeChanged(self) -> None:
        complete = self.isComplete()
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(complete)

    def isComplete(self) -> bool:
        return len(self.ratios) > 0

    def recalculate(self) -> None:
        """Calculates the molar ratio of each valid element in the formula."""
        self.ratios = {}
        elements = db["elements"]
        for element, number in self.searchFormula():
            idx = np.flatnonzero(elements["Symbol"] == element)
            if idx.size > 0:
                ratio = elements["MW"][idx[0]] * float(number or 1.0)
                self.ratios[element] = self.ratios.get(element, 0.0) + ratio
        self.mw = sum(self.ratios.values())
        for element in self.ratios:
            self.ratios[element] = self.ratios[element] / self.mw
        self.ratiosChanged.emit()

    def searchFormula(self) -> Generator[Tuple[str, float], None, None]:
        iter = self.regex.globalMatch(self.lineedit_formula.text())
        while iter.hasNext():
            match = iter.next()
            yield match.captured(1), float(match.captured(2) or 1.0)

    def updateLabels(self) -> None:
        self.textedit_ratios.setPlainText("")
        if len(self.ratios) == 0:
            return
        text = "<html>"
        for i, (element, ratio) in enumerate(self.ratios.items()):
            if i == 0:
                text += "<b>"
            text += f"{element:<2}&nbsp;{ratio:.4f}&nbsp;&nbsp;"
            if i == 0:
                text += "</b>"
            if i % 3 == 2:
                text += "<br>"
        text += "</html>"
        self.textedit_ratios.setText(text)

        self.label_mw.setText(f"MW = {self.mw:.4g} g/mol")


class ParticleDatabaseDialog(QtWidgets.QDialog):
    densitySelected = QtCore.Signal(float)

    def __init__(self, formula: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Density Database")
        self.resize(800, 600)

        self.lineedit_search = QtWidgets.QLineEdit(formula)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.model = NumpyRecArrayTableModel(
            np.concatenate((db["inorganic"], db["polymer"])),
            column_formats={"Density": "{:.4g}"},
        )
        self.proxy = SearchColumnsProxyModel([0, 1])
        self.proxy.setSourceModel(self.model)

        self.table = QtWidgets.QTableView()
        self.table.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.AdjustToContentsOnFirstShow
        )
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setModel(self.proxy)
        self.table.setColumnHidden(4, True)

        self.lineedit_search.textChanged.connect(self.searchDatabase)
        self.lineedit_search.textChanged.connect(self.table.clearSelection)
        self.table.pressed.connect(self.completeChanged)
        self.table.doubleClicked.connect(self.accept)
        self.proxy.rowsInserted.connect(self.completeChanged)
        self.proxy.rowsRemoved.connect(self.completeChanged)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Search"), 0)
        layout.addWidget(self.lineedit_search, 0)
        layout.addWidget(self.table)
        layout.addWidget(self.button_box, 0)

        self.setLayout(layout)
        self.completeChanged()

    def searchDatabase(self, string: str) -> None:
        self.proxy.setSearchString(string)

    def isComplete(self) -> bool:
        return len(self.table.selectedIndexes()) > 0

    def completeChanged(self) -> None:
        complete = self.isComplete()
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(complete)

    def accept(self) -> None:
        idx = self.table.selectedIndexes()[3]
        self.densitySelected.emit(float(self.proxy.data(idx)))
        super().accept()

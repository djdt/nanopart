import logging
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.gui.dialogs._import import _ImportDialogBase
from spcal.gui.graphs import color_schemes
from spcal.gui.graphs.calibration import CalibrationView
from spcal.gui.graphs.response import ResponseView
from spcal.gui.io import getImportDialogForPath, getOpenNanoparticleFile
from spcal.gui.models import NumpyRecArrayTableModel
from spcal.io.nu import is_nu_directory
from spcal.io.text import is_text_file
from spcal.siunits import mass_concentration_units

logger = logging.getLogger(__name__)


class ResponseDialog(QtWidgets.QDialog):
    responsesSelected = QtCore.Signal(dict)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent=parent)
        self.setWindowTitle("Ionic Response Calculator")

        self.data = np.array([])
        self.import_options: dict | None = None

        self.button_open_file = QtWidgets.QPushButton("Open File")
        self.button_open_file.pressed.connect(self.dialogLoadFile)

        self.graph = ResponseView()
        self.graph.region.sigRegionChangeFinished.connect(self.updateResponses)

        self.graph_cal = CalibrationView()

        data = np.array([], dtype=[("_", np.float64)])
        self.model = NumpyRecArrayTableModel(data)
        self.responses = np.array([], dtype=[("_", np.float64)])

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)

        self.table.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.table.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.model.dataChanged.connect(self.completeChanged)
        self.model.dataChanged.connect(self.updateCalibration)

        self.button_add_level = QtWidgets.QPushButton("Add Level")
        self.button_add_level.setIcon(QtGui.QIcon.fromTheme("list-add"))
        self.button_add_level.pressed.connect(self.dialogLoadFile)

        self.combo_unit = QtWidgets.QComboBox()
        self.combo_unit.addItems(list(mass_concentration_units.keys()))
        self.combo_unit.setCurrentText("μg/L")

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        )
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        box_concs = QtWidgets.QGroupBox("Concentrations")
        box_concs.setLayout(QtWidgets.QVBoxLayout())
        box_concs.layout().addWidget(self.table, 1)
        box_concs.layout().addWidget(
            self.combo_unit, 0, QtCore.Qt.AlignmentFlag.AlignRight
        )

        layout_graphs = QtWidgets.QHBoxLayout()
        layout_graphs.addWidget(self.graph, 2)
        layout_graphs.addWidget(self.graph_cal, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(layout_graphs, 1)
        layout.addWidget(box_concs)
        layout.addWidget(self.button_add_level, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.button_box, 0)
        self.setLayout(layout)

    def isComplete(self) -> bool:
        if self.model.array.dtype.names is None:
            return False
        for name in self.model.array.dtype.names:
            if np.count_nonzero(~np.isnan(self.model.array[name])) > 0:
                return True
        return False

    def completeChanged(self) -> None:
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(
            self.isComplete()
        )

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if event.mimeData().hasUrls():
            # Todo, nu import check
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if (
                    (path.is_dir() and is_nu_directory(path))
                    or path.suffix.lower() == ".info"
                    or is_text_file(path)
                ):
                    self.dialogLoadFile(path)
                    break
            event.acceptProposedAction()
        elif event.mimeData().hasHtml():
            pass
        else:
            super().dropEvent(event)

    def dialogLoadFile(
        self, path: str | Path | None = None
    ) -> _ImportDialogBase | None:
        if path is None:
            path = getOpenNanoparticleFile(self)
            if path is None:
                return None
        else:
            path = Path(path)

        dlg = getImportDialogForPath(self, path)
        dlg.dataImported.connect(self.loadData)

        if self.import_options is None:
            dlg.open()
        else:
            try:
                dlg.setImportOptions(self.import_options)
                dlg.accept()
            except Exception:
                self.import_options = None
                logger.warning("dialogLoadFile: unable to set import options.")
                dlg.open()
        return dlg

    def loadData(self, data: np.ndarray, options: dict) -> None:
        # Check the new data is compatible with current loaded
        if self.model.array.size == 0:
            self.model.beginResetModel()
            self.model.array = np.full(1, np.nan, dtype=data.dtype)
            self.model.endResetModel()
            self.responses = self.model.array.copy()

        elif data.dtype.names != self.model.array.dtype.names:
            button = QtWidgets.QMessageBox.question(
                self, "Warning", "New data does not match current, overwrite?"
            )
            if button == QtWidgets.QMessageBox.StandardButton.Yes:
                self.model.beginResetModel()
                self.model.array = np.full(1, np.nan, dtype=data.dtype)
                self.model.endResetModel()
                self.responses = self.model.array.copy()
            else:
                return
        else:
            self.model.insertRow(self.model.rowCount())
            self.responses = np.append(
                self.responses, np.full(1, np.nan, self.responses.dtype)
            )

        if self.import_options is None:
            self.import_options = options

        old_size = self.data.size
        self.data = data
        tic = np.sum([data[name] for name in data.dtype.names], axis=0)
        xs = np.arange(tic.size)

        self.graph.clear()
        self.graph.plot.setTitle(f"TIC: {options['path'].name}")
        self.graph.drawData(xs, tic)
        self.graph.drawMean(0.0)
        if old_size != data.size:
            self.graph.region.blockSignals(True)
            self.graph.region.setRegion((xs[0], xs[-1]))
            self.graph.region.blockSignals(False)
        self.graph.updateMean()

        self.updateResponses()

    def updateResponses(self) -> None:
        if self.responses.dtype.names is None:
            return

        for name in self.responses.dtype.names:
            self.responses[name][-1] = np.mean(
                self.data[name][self.graph.region_start : self.graph.region_end]
            )

        self.updateCalibration()

    def updateCalibration(self) -> None:
        self.graph_cal.clear()
        if self.responses.dtype.names is None:
            return

        scheme = color_schemes[QtCore.QSettings().value("colorscheme", "IBM Carbon")]

        for i, name in enumerate(self.responses.dtype.names):
            x = self.model.array[name]
            y = self.responses[name][~np.isnan(x)]
            x = x[~np.isnan(x)]
            if x.size == 0:
                continue
            brush = QtGui.QBrush(scheme[i])
            self.graph_cal.drawPoints(x, y, trend_line=True, brush=brush)

    def accept(self) -> None:
        assert self.responses.dtype.names is not None

        responses = {}
        for name in self.responses.dtype.names:
            x = self.model.array[name]
            y = self.responses[name][~np.isnan(x)]
            x = (
                x[~np.isnan(x)]
                * mass_concentration_units[self.combo_unit.currentText()]
            )
            if x.size == 0:
                continue
            elif x.size == 1:  # single point, force 0
                m = y[0] / x[0]
            else:
                _, m = np.polynomial.polynomial.polyfit(x, y, 1)
            responses[name] = m

        if len(responses) > 0:
            self.responsesSelected.emit(responses)
        super().accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication()

    w = ResponseDialog()
    npz = np.load("/home/tom/Downloads/test_data.npz")
    names = npz.files
    data = np.empty(npz[names[0]].size, dtype=[(n, float) for n in names])
    for n in names:
        data[n] = npz[n]
    w.loadData(data, {"path": Path("test.csv")})
    w.show()
    app.exec()

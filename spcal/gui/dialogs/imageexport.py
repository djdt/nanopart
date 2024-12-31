from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.detection import detection_maxima
from spcal.gui.graphs import color_schemes, symbols
from spcal.gui.graphs.particle import ParticleView
from spcal.result import SPCalResult


def draw_particle_view(
    results: dict[str, SPCalResult],
    regions: np.ndarray,
    dwell: float,
    font: QtGui.QFont,
    scale: float,
    draw_markers: bool = False,
) -> ParticleView:

    graph = ParticleView(xscale=dwell, font=font)

    scheme = color_schemes[QtCore.QSettings().value("colorscheme", "IBM Carbon")]

    names = tuple(results.keys())
    xs = np.arange(results[names[0]].events)

    for name, result in results.items():
        index = names.index(name)
        pen = QtGui.QPen(QtGui.QColor(scheme[index % len(scheme)]), 2.0 * scale)
        pen.setCosmetic(True)
        graph.drawSignal(name, xs, result.responses, pen=pen)

    if draw_markers:
        for name, result in results.items():
            index = names.index(name)
            brush = QtGui.QBrush(QtGui.QColor(scheme[index % len(scheme)]))
            symbol = symbols[index % len(symbols)]

            maxima = detection_maxima(
                result.responses, regions[np.flatnonzero(result.detections)]
            )
            graph.drawMaxima(
                name,
                xs[maxima],
                result.responses[maxima],
                brush=brush,
                symbol=symbol,
                size=6.0 * scale,
            )
    return graph


class ImageExportDialog(QtWidgets.QDialog):
    exportSettingsSelected = QtCore.Signal(Path, QtCore.QSize, float, QtGui.QColor)

    def __init__(
        self,
        size: QtCore.QSize,
        path: Path | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Image Export")

        if path is None:
            path = Path("image.png")
        self.path = path

        settings = QtCore.QSettings()
        size_x = int(settings.value("ImageExport/SizeX", 1960))
        size_y = int(settings.value("ImageExport/SizeY", 1200))
        dpi = int(settings.value("ImageExport/DPI", 600))

        self.spinbox_size_x = QtWidgets.QSpinBox()
        self.spinbox_size_x.setRange(100, 10000)
        self.spinbox_size_x.setValue(size_x)

        self.spinbox_size_y = QtWidgets.QSpinBox()
        self.spinbox_size_y.setRange(100, 10000)
        self.spinbox_size_y.setValue(size_y)

        self.spinbox_dpi = QtWidgets.QSpinBox()
        self.spinbox_dpi.setRange(96, 1200)
        self.spinbox_dpi.setValue(dpi)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Close,
        )

        self.check_transparent = QtWidgets.QCheckBox("Transparent background")

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout_size = QtWidgets.QHBoxLayout()
        layout_size.addWidget(self.spinbox_size_x, 1)
        layout_size.addWidget(QtWidgets.QLabel("x"), 0)
        layout_size.addWidget(self.spinbox_size_y, 1)

        layout_form = QtWidgets.QFormLayout()
        layout_form.addRow("Size:", layout_size)
        layout_form.addRow("DPI:", self.spinbox_dpi)
        layout_form.addRow(self.check_transparent)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(layout_form)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def accept(self) -> None:
        path, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Image", str(self.path.absolute()), "PNG Images (*.png)"
        )
        if not ok:
            return

        size = QtCore.QSize(self.spinbox_size_x.value(), self.spinbox_size_y.value())

        if self.check_transparent.isChecked():
            background = QtCore.Qt.GlobalColor.transparent
        else:
            background = QtCore.Qt.GlobalColor.white
        self.exportSettingsSelected.emit(
            path, size, self.spinbox_dpi.value(), QtGui.QColor(background)
        )
        super().accept()

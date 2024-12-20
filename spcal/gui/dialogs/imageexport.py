import numpy as np
import pyqtgraph
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.detection import detection_maxima
from spcal.gui.graphs import color_schemes, symbols
from spcal.gui.graphs.base import SinglePlotGraphicsView
from spcal.gui.graphs.particle import ParticleView


def draw_particle_view(
    responses: np.ndarray,
    detections: np.ndarray,
    regions: np.ndarray,
    # signals: dict[str, np.ndarray],
    # results: dict[str, SPCalResult],
    dwell: float,
    font: QtGui.QFont,
    pen_size: float,
    trim_regions: dict[str, tuple[float, float]],
) -> ParticleView:

    graph = ParticleView(xscale=dwell, font=font)

    scheme = color_schemes[QtCore.QSettings().value("colorscheme", "IBM Carbon")]

    names = tuple(responses.dtype.names)

    xs = np.arange(responses.size)

    for name in names:
        index = names.index(name)
        pen = QtGui.QPen(QtGui.QColor(scheme[index % len(scheme)]), pen_size)
        graph.drawSignal(name, xs, responses[name], pen=pen)

    for name in detections.dtype.names:
        index = names.index(name)
        brush = QtGui.QBrush(QtGui.QColor(scheme[index % len(scheme)]))
        symbol = symbols[index % len(symbols)]
        trim = trim_regions[name]

        maxima = (
            detection_maxima(responses[name][trim[0] : trim[1]], regions[name])
            + trim[0]
        )
        graph.drawMaxima(
            name,
            xs[maxima],
            responses[name][maxima],
            brush=brush,
            symbol=symbol,
        )
    return graph


class ImageExportDialog(QtWidgets.QDialog):
    def __init__(self, input, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.graph = self.createGraphCopy(graph)
        # self.graph = graph
        size = graph.viewport().rect()

        self.spinbox_size_x = QtWidgets.QSpinBox()
        self.spinbox_size_x.setRange(100, 10000)
        self.spinbox_size_x.setValue(size.width())

        self.spinbox_size_y = QtWidgets.QSpinBox()
        self.spinbox_size_y.setRange(100, 10000)
        self.spinbox_size_y.setValue(size.height())

        self.spinbox_dpi = QtWidgets.QSpinBox()
        self.spinbox_dpi.setRange(96, 1200)
        self.spinbox_dpi.setValue(96)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Close,
        )

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout_size = QtWidgets.QHBoxLayout()
        layout_size.addWidget(self.spinbox_size_x, 1)
        layout_size.addWidget(QtWidgets.QLabel("x"), 0)
        layout_size.addWidget(self.spinbox_size_y, 1)

        layout_form = QtWidgets.QFormLayout()
        layout_form.addRow("Size:", layout_size)
        layout_form.addRow("DPI:", self.spinbox_dpi)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.graph)
        layout.addLayout(layout_form)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    # def createGraphCopy(self, graph: SinglePlotGraphicsView) -> SinglePlotGraphicsView:
    #     copy = SinglePlotGraphicsView(
    #         graph.plot.titleLabel.text,
    #         graph.xaxis.labelText,
    #         graph.yaxis.labelText,
    #         graph.xaxis.labelUnits,
    #         graph.yaxis.labelUnits,
    #     )
    #     for item in graph.plot.items:
    #         if isinstance(item, pyqtgraph.PlotCurveItem):
    #             pen = item.opts["pen"]
    #             # resize pen
    #             curve = pyqtgraph.PlotCurveItem(
    #                 x=item.xData,
    #                 y=item.yData,
    #                 pen=pen,
    #                 connect="all",
    #                 skipFiniteCheck=True,
    #             )
    #             copy.plot.addItem(curve)
    #         elif isinstance(item, pyqtgraph.ScatterPlotItem):
    #             brush = item.opts["brush"]
    #             scatter = pyqtgraph.ScatterPlotItem(
    #                 x=item.data["x"],
    #                 y=item.data["y"],
    #                 size=item.opts["size"],
    #                 symbol=item.opts["symbol"],
    #                 pen=None,
    #                 brush=brush,
    #             )
    #             copy.plot.addItem(scatter)
    #
    #     limits = graph.plot.vb.state["limits"]
    #     copy.plot.vb.setLimits(
    #         xMin=limits["xLimits"][0],
    #         xMax=limits["xLimits"][1],
    #         yMin=limits["yLimits"][0],
    #         yMax=limits["yLimits"][1],
    #     )
    #     view_range = graph.plot.vb.state["viewRange"]
    #     copy.plot.vb.setRange(xRange=view_range[0], yRange=view_range[1])
    #     return copy

    def accept(self) -> None:
        self.render()
        # self.timer = QtCore.QTimer()
        # self.timer.setSingleShot(True)
        # self.timer.timeout.connect(self.render)
        # self.timer.start(100)
        super().accept()

    def prepareForRender(self) -> None:
        self.original_size = self.graph.size()
        self.original_font = QtGui.QFont(self.graph.font)

        resized_font = QtGui.QFont(self.original_font)
        resized_font.setPointSizeF(
            self.original_font.pointSizeF() / 96.0 * self.spinbox_dpi.value()
        )
        self.graph.resize(self.image.size())
        self.graph.setFont(resized_font)

    def postRender(self) -> None:
        self.graph.resize(self.original_size)
        self.graph.setFont(self.original_font)

    def render(self):
        image = QtGui.QImage(
            self.spinbox_size_x.value(),
            self.spinbox_size_y.value(),
            QtGui.QImage.Format.Format_ARGB32,
        )
        image.fill(QtGui.QColor(0, 0, 0, 0))

        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)

        graph = draw_particle_view()
        # graph = self.createGraphCopy(self.graph)
        # graph.resize(image.size())
        # graph.show()

        graph.scene().prepareForPaint()
        graph.scene().render(
            painter,
            QtCore.QRectF(image.rect()),
            graph.viewRect(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        )
        painter.end()
        image.save("/home/tom/Downloads/out.png")

        # self.post_timer = QtCore.QTimer()
        # self.post_timer.setSingleShot(True)
        # self.post_timer.timeout.connect(self.postRender)
        # self.post_timer.start(100)

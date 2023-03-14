from typing import List

import numpy as np
import pyqtgraph
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.calc import pca
from spcal.gui.graphs import viridis_32
from spcal.gui.graphs.base import SinglePlotGraphicsView


class PCAArrow(QtWidgets.QGraphicsPathItem):
    def __init__(
        self,
        angle_r: float,
        length: float,
        label: str | None = None,
        label_brush: QtGui.QBrush | None = None,
        pen: QtGui.QPen | None = None,
        brush: QtGui.QPen | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.setFlag(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )

        # Angle from top
        if angle_r < 0.0:
            angle_r += 2.0 * np.pi
        angle_r = angle_r % (2.0 * np.pi)

        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.red, 2.0)
            pen.setCosmetic(True)
        self.setPen(pen)

        if brush is None:
            brush = QtGui.QBrush(QtCore.Qt.red)
        self.setBrush(brush)

        path = QtGui.QPainterPath(QtCore.QPointF(0.0, 0.0))
        path.lineTo(0.0, -length)
        path.lineTo(3.0, -length + 3.0)
        path.lineTo(-3.0, -length + 3.0)
        path.lineTo(0.0, -length)

        tr = QtGui.QTransform().rotateRadians(angle_r)
        path = tr.map(path)
        self.setPath(path)

        if label is not None:
            if label_brush is None:
                label_brush = QtGui.QBrush(QtCore.Qt.GlobalColor.darkGray)

            self.text = QtWidgets.QGraphicsSimpleTextItem(label, self)
            rect = QtGui.QFontMetrics(self.text.font()).boundingRect(self.text.text())
            pos = tr.map(QtCore.QPointF(0.0, -(length * 1.05)))
            pos.setX(pos.x() - rect.width() * (np.sin(angle_r + np.pi) + 1.0) / 2.0)
            pos.setY(pos.y() - rect.height() * (np.cos(angle_r) + 1.0) / 2.0)

            # self.text.setPen(QtCore.Qt.PenStyle.NoPen)
            self.text.setBrush(label_brush)
            self.text.setPos(pos)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        super().paint(painter, option, widget)


class PCAView(SinglePlotGraphicsView):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__("PCA", xlabel="PC 1", ylabel="PC 2", parent=parent)

        self.scatter: pyqtgraph.ScatterPlotItem | None = None

    def draw(
        self,
        X: np.ndarray,
        feature_names: List[str] | None = None,
        pen: QtGui.QPen | None = None,
        brush: QtGui.QBrush | None = None,
        arrow_pen: QtGui.QPen | None = None,
        text_brush: QtGui.QBrush | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.GlobalColor.black, 1.0)
            pen.setCosmetic(True)
        if brush is None:
            brush = QtGui.QBrush(QtCore.Qt.GlobalColor.black)

        a, v, var = pca(X, 2)

        self.scatter = pyqtgraph.ScatterPlotItem(
            x=a[:, 0], y=a[:, 1], pen=pen, brush=brush
        )
        self.plot.addItem(self.scatter)

        if feature_names is not None:
            assert len(feature_names) == v.shape[1]

            angles = np.arctan2(v[0], v[1])
            for name, angle in zip(feature_names, angles):
                arrow = PCAArrow(
                    angle, 100.0, label=name, pen=arrow_pen, label_brush=text_brush
                )
                self.plot.addItem(arrow)

        self.xaxis.setLabel(f"PC 1 ({var[0] * 100.0:.1f} %)")
        self.yaxis.setLabel(f"PC 2 ({var[1] * 100.0:.1f} %)")
        self.plot.setTitle(f"PCA: {np.sum(var) * 100.0:.1f} % explained variance")

    def colorScatter(
        self, indicies: np.ndarray, colors: List[QtGui.QColor] | None = None
    ) -> None:
        if self.scatter is None:
            return
        if colors is None:
            colors = viridis_32

        brushes = [QtGui.QBrush(colors[i]) for i in indicies]
        self.scatter.setBrush(brushes)

    def clear(self) -> None:
        super().clear()
        self.scatter = None


if __name__ == "__main__":

    app = QtWidgets.QApplication()

    data = np.genfromtxt("/home/tom/Downloads/eq.csv", delimiter=",", skip_header=22)
    data = np.nan_to_num(data)

    X = pca(data)

    win = PCAView()
    win.show()

    win.draw(data)
    c = np.zeros_like(data[:, 0])
    c = np.sum(data, axis=1)
    # np.divide(data[:, 2], data[:, 6], where=data[:, 6] > 0, out=c)
    bins = np.linspace(c.min(), c.max(), 31)
    idx = np.digitize(c, bins)
    win.colorScatter(idx)

    app.exec()

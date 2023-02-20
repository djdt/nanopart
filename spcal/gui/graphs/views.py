from typing import Dict, List

import numpy as np
import pyqtgraph
from PySide6 import QtCore, QtGui, QtWidgets

from spcal.calc import pca
from spcal.gui.graphs.base import PlotCurveItemFix, SinglePlotGraphicsView
from spcal.gui.graphs.legends import MultipleItemSampleProxy


class ResponseView(SinglePlotGraphicsView):
    def __init__(
        self,
        downsample: int = 64,
        parent: pyqtgraph.GraphicsWidget | None = None,
    ):
        super().__init__("Response TIC", "Time", "Intensity", parent=parent)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.enableAutoRange(x=True, y=True)
        self.plot.setDownsampling(ds=downsample, mode="subsample", auto=True)

        self.signal: pyqtgraph.PlotCurveItem | None = None
        self.signal_mean: pyqtgraph.PlotCurveItem | None = None

        region_pen = QtGui.QPen(QtCore.Qt.red, 1.0)
        region_pen.setCosmetic(True)

        self.region = pyqtgraph.LinearRegionItem(
            pen="grey",
            hoverPen="red",
            brush=QtGui.QBrush(QtCore.Qt.NoBrush),
            hoverBrush=QtGui.QBrush(QtCore.Qt.NoBrush),
            swapMode="block",
        )
        # self.region.movable = False  # prevent moving of region, but not lines
        self.region.lines[0].addMarker("|>", 0.9)
        self.region.lines[1].addMarker("<|", 0.9)
        self.region.sigRegionChangeFinished.connect(self.updateMean)

    @property
    def region_start(self) -> int:
        return int(self.region.lines[0].value())  # type: ignore

    @property
    def region_end(self) -> int:
        return int(self.region.lines[1].value())  # type: ignore

    def drawData(
        self,
        x: np.ndarray,
        y: np.ndarray,
        pen: QtGui.QPen | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.black, 1.0)
            pen.setCosmetic(True)

        # optimise by removing points with 0 change in gradient
        diffs = np.diff(y, n=2, append=0, prepend=0) != 0
        self.signal = pyqtgraph.PlotCurveItem(
            x=x[diffs], y=y[diffs], pen=pen, connect="all", skipFiniteCheck=True
        )
        self.plot.addItem(self.signal)

        self.region.blockSignals(True)
        self.region.setRegion((x[0], x[-1]))
        self.region.setBounds((x[0], x[-1]))
        self.region.blockSignals(False)
        self.plot.addItem(self.region)

    def drawMean(self, mean: float, pen: QtGui.QPen | None = None) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.red, 2.0, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)

        if self.signal_mean is None:
            self.signal_mean = pyqtgraph.PlotCurveItem(
                pen=pen,
                connect="all",
                skipFiniteCheck=True,
            )
            self.plot.addItem(self.signal_mean)

        self.signal_mean.updateData(
            x=[self.region_start, self.region_end], y=[mean, mean]
        )

    def updateMean(self) -> None:
        if self.signal is None or self.signal_mean is None:
            return
        mean = np.mean(self.signal.yData[self.region_start : self.region_end])
        self.drawMean(mean)


class ScatterView(SinglePlotGraphicsView):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__("Scatter", parent=parent)

    def drawData(
        self,
        x: np.ndarray,
        y: np.ndarray,
        logx: bool = False,
        logy: bool = False,
        pen: QtGui.QPen | None = None,
        brush: QtGui.QBrush | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.black, 1.0)
            pen.setCosmetic(True)
        if brush is None:
            brush = QtGui.QBrush(QtCore.Qt.black)

        if logx:
            x = np.log10(x)
        if logy:
            y = np.log10(y)

        self.plot.setLogMode(logx, logy)

        curve = pyqtgraph.ScatterPlotItem(x=x, y=y, pen=pen, brush=brush)
        self.plot.addItem(curve)

        xmin, xmax = np.amin(x), np.amax(x)
        ymin, ymax = np.amin(y), np.amax(y)

        self.plot.setLimits(
            xMin=xmin - (xmax - xmin) * 0.05,
            xMax=xmax + (xmax - xmin) * 0.05,
            yMin=ymin - (ymax - ymin) * 0.05,
            yMax=ymax + (ymax - ymin) * 0.05,
        )
        self.plot.enableAutoRange(x=True, y=True)  # rescale to max bounds

    def drawFit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        degree: int = 1,
        logx: bool = False,
        logy: bool = False,
        pen: QtGui.QPen | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.red, 1.0)
            pen.setCosmetic(True)
        poly = np.polynomial.Polynomial.fit(x, y, degree)

        xmin, xmax = np.amin(x), np.amax(x)
        sx = np.linspace(xmin, xmax, 1000)

        sy = poly(sx)

        if logx:
            sx = np.log10(sx)
        if logy:
            sy = np.log10(sy)

        curve = pyqtgraph.PlotCurveItem(
            x=sx, y=sy, pen=pen, connect="all", skipFiniteCheck=True
        )
        self.plot.addItem(curve)


class ParticleView(SinglePlotGraphicsView):
    regionChanged = QtCore.Signal()

    def __init__(
        self,
        xscale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(
            "Signal",
            xlabel="Time",
            xunits="s",
            ylabel="Intensity (counts)",
            parent=parent,
        )
        self.xaxis.setScale(xscale)

        self.plot.setMouseEnabled(y=False)
        self.plot.setAutoVisible(y=True)
        self.plot.enableAutoRange(y=True)
        self.plot.setLimits(yMin=0.0)

        self.legend_items: Dict[str, MultipleItemSampleProxy] = {}
        self.limit_items: List[pyqtgraph.PlotCurveItem] = []

        region_pen = QtGui.QPen(QtCore.Qt.red, 1.0)
        region_pen.setCosmetic(True)

        self.region = pyqtgraph.LinearRegionItem(
            pen="grey",
            hoverPen="red",
            brush=QtGui.QBrush(QtCore.Qt.NoBrush),
            hoverBrush=QtGui.QBrush(QtCore.Qt.NoBrush),
            swapMode="block",
        )
        self.region.sigRegionChangeFinished.connect(self.regionChanged)
        self.region.movable = False  # prevent moving of region, but not lines
        self.region.lines[0].addMarker("|>", 0.9)
        self.region.lines[1].addMarker("<|", 0.9)
        self.plot.addItem(self.region)

    @property
    def region_start(self) -> int:
        return int(self.region.lines[0].value())  # type: ignore

    @property
    def region_end(self) -> int:
        return int(self.region.lines[1].value())  # type: ignore

    def clear(self) -> None:
        self.legend_items.clear()
        super().clear()

    def clearScatters(self) -> None:
        for item in self.plot.listDataItems():
            if isinstance(item, pyqtgraph.ScatterPlotItem):
                self.plot.removeItem(item)

    def clearLimits(self) -> None:
        for limit in self.limit_items:
            self.plot.removeItem(limit)
        self.limit_items.clear()

    def drawSignal(
        self,
        name: str,
        x: np.ndarray,
        y: np.ndarray,
        pen: QtGui.QPen | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.black, 1.0)
            pen.setCosmetic(True)

        # optimise by removing points with 0 change in gradient
        diffs = np.diff(y, n=2, append=0, prepend=0) != 0
        curve = PlotCurveItemFix(
            x=x[diffs], y=y[diffs], pen=pen, connect="all", skipFiniteCheck=True
        )

        self.legend_items[name] = MultipleItemSampleProxy(pen.color(), items=[curve])

        self.plot.addItem(curve)
        self.plot.legend.addItem(self.legend_items[name], name)

        self.plot.addItem(self.region)

    def drawMaxima(
        self,
        name: str,
        x: np.ndarray,
        y: np.ndarray,
        brush: QtGui.QBrush | None = None,
        symbol: str = "t",
    ) -> None:
        if brush is None:
            brush = QtGui.QBrush(QtCore.Qt.red)

        scatter = pyqtgraph.ScatterPlotItem(
            x=x, y=y, size=6, symbol=symbol, pen=None, brush=brush
        )
        self.plot.addItem(scatter)

        self.legend_items[name].addItem(scatter)

    def drawLimits(
        self,
        x: np.ndarray,
        # mean: float | np.ndarray,
        limit: float | np.ndarray,
        pen: QtGui.QPen | None = None,
    ) -> None:
        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.black, 1.0, QtCore.Qt.DashLine)
            pen.setCosmetic(True)

        if isinstance(limit, float) or limit.size == 1:
            nx, y = [x[0], x[-1]], [limit, limit]
        else:
            diffs = np.diff(limit, n=2, append=0, prepend=0) != 0
            nx, y = x[diffs], limit[diffs]

        curve = pyqtgraph.PlotCurveItem(
            x=nx,
            y=y,
            name="Detection Threshold",
            pen=pen,
            connect="all",
            skipFiniteCheck=True,
        )
        self.limit_items.append(curve)
        self.plot.addItem(curve)


class PCAArrow(QtWidgets.QGraphicsPathItem):
    def __init__(
        self,
        angle_r: float,
        length: float,
        name: str | None = None,
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

        if name is not None:
            self.text = QtWidgets.QGraphicsSimpleTextItem(name, self)
            rect = QtGui.QFontMetrics(self.text.font()).boundingRect(self.text.text())
            pos = tr.map(QtCore.QPointF(0.0, -(length)))
            pos.setX(pos.x() - rect.width() / 2.0)
            pos.setY(pos.y() - rect.height() / 2.0)
            # if angle_r > np.pi:  # Left side of plot
            #     pos.setX(pos.x() - rect.width())

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

    def draw(
        self,
        X: np.ndarray,
        feature_names: List[str] | None = None,
        brush: QtGui.QBrush | None = None,
    ) -> None:
        a, v, _ = pca(X, 2)

        if brush is None:
            brush = QtGui.QBrush(QtCore.Qt.GlobalColor.black)

        scatter = pyqtgraph.ScatterPlotItem(x=a[:, 0], y=a[:, 1], pen=None, brush=brush)
        self.plot.addItem(scatter)

        if feature_names is not None:
            assert len(feature_names) == v.shape[1]

            angles = np.arctan2(v[0], v[1])
            # for angle in np.linspace(0.0, 2.0 * np.pi, 10):
                # arrow = PCAArrow(angle, 100.0, name=f"{angle * 180.0 / np.pi:.18f}")
            for name, angle in zip(feature_names, angles):
                arrow = PCAArrow(angle, 100.0, name=name)
                self.plot.addItem(arrow)


if __name__ == "__main__":
    app = QtWidgets.QApplication()
    plot = PCAView()

    import sklearn.datasets

    data = sklearn.datasets.load_iris()["data"]
    plot.draw(data, feature_names=sklearn.datasets.load_iris()["feature_names"])
    plot.zoomReset()
    plot.show()
    app.exec()

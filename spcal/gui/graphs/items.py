from typing import List

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

# class MarkerItem(QtWidgets.QGraphicsPathItem):
#     def __init__(
#         self,
#         x: float,
#         y: float,
#         text: str = "",
#         height: float = 6.0,
#         pen: QtGui.QPen | None = None,
#         brush: QtGui.QBrush | None = None,
#         parent: QtWidgets.QGraphicsItem | None = None,
#     ):
#         if pen is None:
#             pen = QtGui.QPen(QtCore.Qt.black, 1.0)
#             pen.setCosmetic(True)

#         if brush is None:
#             brush = QtGui.QBrush(QtCore.Qt.black)

#         super().__init__(parent)
#         self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations, True)
#         self.setPos(x, y)

#         width = height / np.sqrt(3.0)
#         path = QtGui.QPainterPath()
#         path.addPolygon(
#             QtGui.QPolygonF(
#                 [
#                     QtCore.QPointF(0, 0),
#                     QtCore.QPointF(-width, -height),
#                     QtCore.QPointF(width, -height),
#                 ]
#             )
#         )
#         self.setPath(path)
#         self.setPen(pen)
#         self.setBrush(brush)

#         self.text = QtWidgets.QGraphicsSimpleTextItem(text, self)
#         # self.text.setPen(pen)
#         # self.text.setBrush(brush)

#         trect = QtGui.QFontMetrics(self.text.font()).boundingRect(self.text.text())
#         self.text.setPos(-trect.width() / 2.0, -(height + trect.height()))

#     def paint(
#         self,
#         painter: QtGui.QPainter,
#         option: QtWidgets.QStyleOptionGraphicsItem,
#         widget: QtWidgets.QWidget | None = None,
#     ) -> None:
#         painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
#         super().paint(painter, option, widget)


class PieSlice(QtWidgets.QGraphicsEllipseItem):
    def __init__(
        self,
        radius: float,
        angle: int,
        span: int,
        label: str | None = None,
        hover_brush: QtGui.QBrush | None = None,
        parent: QtWidgets.QGraphicsItem | None = None,
    ):
        super().__init__(-radius, -radius, radius * 2, radius * 2, parent=parent)
        self.setStartAngle(angle)
        self.setSpanAngle(span)

        self.hover_brush = hover_brush
        self._brush = self.brush()

        if label is not None:
            self.label = QtWidgets.QGraphicsSimpleTextItem(str(label), parent=self)
            r = -(angle + span / 2.0) / 16.0 * np.pi / 180.00
            self.label.setPos(radius * 1.2 * np.cos(r), radius * 1.2 * np.sin(r))
            self.label.moveBy(
                -self.label.boundingRect().width() / 2.0,
                -self.label.boundingRect().height() / 2.0,
            )
            self.label.setVisible(False)

    def setBrush(self, brush: QtGui.QBrush) -> None:
        self._brush = brush
        super().setBrush(brush)

    def setHoverBrush(self, brush: QtGui.QBrush) -> None:
        self.hover_brush = brush

    def setHovered(self, hovered: bool = True) -> None:
        if self.label is not None:
            self.label.setVisible(hovered)
        if self.hover_brush is not None:
            super().setBrush(self.hover_brush if hovered else self._brush)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.setHovered(True)
        for item in self.scene().items():
            if item == self:
                continue
            if isinstance(item, PieSlice) and item.hover_brush == self.hover_brush:
                item.setHovered(True)

        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.setHovered(False)
        for item in self.scene().items():
            if item == self:
                continue
            if isinstance(item, PieSlice) and item.hover_brush == self.hover_brush:
                item.setHovered(False)
        super().hoverLeaveEvent(event)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        super().paint(painter, option, widget)
        painter.restore()


class PieChart(QtWidgets.QGraphicsItem):
    def __init__(
        self,
        radius: float,
        values: List[float],
        brushes: List[QtGui.QBrush],
        pen: QtGui.QPen | None = None,
        label_format: str = "{:.4g}",
        parent: QtWidgets.QGraphicsItem | None = None,
    ):
        """Pie is centered on item.pos()."""
        super().__init__(parent=parent)
        self.setFlag(QtWidgets.QGraphicsItem.ItemHasNoContents)

        if pen is None:
            pen = QtGui.QPen(QtCore.Qt.black, 0.0)
            pen.setCosmetic(True)
        self.pen = pen

        self.radius = radius
        self.slices: List[PieSlice] = []
        self.labels: List[QtWidgets.QGraphicsSimpleTextItem] = []
        self.label_format = label_format

        self.buildPie(values, brushes)

    def buildPie(
        self, values: List[float], brushes: List[QtGui.QBrush]
    ) -> List[PieSlice]:
        self.slices.clear()

        fractions = np.array(values) / np.sum(values)

        angle = 0
        for value, frac, brush in zip(values, fractions, brushes):
            span = int(360 * 16 * frac)
            hover_brush = QtGui.QBrush(brush)
            hover_brush.setColor(hover_brush.color().lighter())

            item = PieSlice(
                self.radius,
                angle,
                span,
                label=self.label_format.format(value),
                parent=self,
            )
            item.setPen(self.pen)
            item.setBrush(brush)
            item.setHoverBrush(hover_brush)
            item.setAcceptHoverEvents(True)

            angle += span
            self.slices.append(item)
        return self.slices

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(
            -self.radius, -self.radius, self.radius * 2, self.radius * 2
        )


if __name__ == "__main__":
    from spcal.gui.graphs import color_schemes

    app = QtWidgets.QApplication()

    scene = QtWidgets.QGraphicsScene(-200, -200, 800, 400)
    view = QtWidgets.QGraphicsView(scene)
    view.setMouseTracking(True)

    item = PieChart(100.0, [1.0, 2.0, 3.0, 4.0], color_schemes["IBM Carbon"])
    item.setPos(0.0, 0.0)
    scene.addItem(item)

    item2 = PieChart(100.0, [23.0, 12.0, 0.0, 32.1], color_schemes["IBM Carbon"])
    item2.setPos(300.0, 0.0)
    scene.addItem(item2)

    # for s1, s2 in zip(item.slices, item2.slices):
    #     s1.hovered.connect()

    view.show()

    app.exec()

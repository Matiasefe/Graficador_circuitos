"""Lienzo con zoom y desplazamiento."""

from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QGraphicsView

MIN_SCALE = 0.25
MAX_SCALE = 6.0


class SchematicView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.NoFrame)
        self._panning = False
        self._pan_origin = QPoint()

    def current_scale(self) -> float:
        return self.transform().m11()

    def zoom_by(self, factor: float) -> None:
        target = self.current_scale() * factor
        if target < MIN_SCALE or target > MAX_SCALE:
            return
        self.scale(factor, factor)

    def reset_zoom(self) -> None:
        self.resetTransform()

    def fit_content(self) -> None:
        rect = self.scene().content_rect()
        if rect.isNull() or rect.isEmpty():
            self.resetTransform()
            self.centerOn(0, 0)
            return
        self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)
        # fitInView ignora los limites de zoom y con la ventana aun sin
        # dimensionar puede dar escalas absurdas
        scale = min(max(self.current_scale(), MIN_SCALE), 2.0)
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center())

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom_by(1.15 if delta > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor if self.scene().tool == "select" else Qt.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

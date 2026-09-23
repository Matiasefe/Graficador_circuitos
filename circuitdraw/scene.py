"""Escena del esquematico: rejilla, herramientas y trazado de cables."""

import math
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsScene, QUndoStack

from .commands import AddItemsCommand, DeleteItemsCommand, MoveItemsCommand, OrientationCommand
from .items import ComponentItem, TextItem, WireItem, clean_points
from .symbols import GRID, Symbol, snap_point

SELECT = "select"
WIRE = "wire"
PLACE = "place"
TEXT = "text"

GRID_MINOR = QColor("#e7ecf3")
GRID_MAJOR = QColor("#d3dced")
PREVIEW = QColor("#e8590c")
JUNCTION = QColor("#0f5132")

NO_AUTO_REFERENCE = {"ground", "supply", "terminal"}


class SchematicScene(QGraphicsScene):
    document_changed = pyqtSignal()
    tool_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)
    edit_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(QRectF(-3000, -2200, 6000, 4400))
        self.setBackgroundBrush(QColor("#ffffff"))
        self.undo_stack = QUndoStack(self)
        self.show_grid = True
        self.export_mode = False
        self.tool = SELECT
        self.pending_symbol: Optional[Symbol] = None
        self.pending_factory: Optional[Callable[[], ComponentItem]] = None
        self._ghost: Optional[ComponentItem] = None
        self._wire_points: List[QPointF] = []
        self._wire_start: Optional[Tuple[ComponentItem, int]] = None
        self._wire_cursor: Optional[QPointF] = None
        self._horizontal_first = True
        self._move_origin: List[Tuple[object, QPointF]] = []

    # ------------------------------------------------------------------
    # estado de herramientas
    # ------------------------------------------------------------------
    @property
    def wiring_hint(self) -> bool:
        return self.tool == WIRE

    def set_tool(
        self,
        tool: str,
        symbol: Optional[Symbol] = None,
        factory: Optional[Callable[[], ComponentItem]] = None,
    ) -> None:
        self.cancel_action()
        self.tool = tool
        self.pending_symbol = symbol
        self.pending_factory = factory
        if tool == PLACE and (symbol is not None or factory is not None):
            self._ghost = self.new_pending_item()
            self._ghost.setFlags(QGraphicsItem.GraphicsItemFlags())
            self._ghost.setOpacity(0.45)
            self._ghost.setZValue(10)
            self.addItem(self._ghost)
            self.status_message.emit(
                f"Colocando {self._ghost.symbol.name}: clic para insertar, "
                "R para rotar, Esc para terminar."
            )
        elif tool == WIRE:
            self.status_message.emit(
                "Cable: clic en un pin o punto, clic para fijar codos, doble clic o Esc para terminar."
            )
        elif tool == TEXT:
            self.status_message.emit("Nota: clic en el lienzo para escribir un texto.")
        else:
            self.status_message.emit("Seleccion: arrastra componentes, doble clic para editar.")
        for view in self.views():
            view.setCursor(Qt.ArrowCursor if tool == SELECT else Qt.CrossCursor)
        self.update()
        self.tool_changed.emit(tool)

    def cancel_action(self) -> None:
        if self._ghost is not None:
            self.removeItem(self._ghost)
            self._ghost = None
        self.pending_factory = None
        self._wire_points = []
        self._wire_start = None
        self._wire_cursor = None
        self.update()

    def notify_changed(self) -> None:
        self.document_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # consultas
    # ------------------------------------------------------------------
    def components(self) -> List[ComponentItem]:
        return [item for item in self.items() if isinstance(item, ComponentItem)]

    def wires(self) -> List[WireItem]:
        return [item for item in self.items() if isinstance(item, WireItem)]

    def texts(self) -> List[TextItem]:
        return [item for item in self.items() if isinstance(item, TextItem)]

    def next_reference(self, symbol: Symbol) -> str:
        if symbol.key in NO_AUTO_REFERENCE:
            return ""
        used = set()
        for component in self.components():
            if component is self._ghost:
                continue
            reference = component.reference
            if reference.startswith(symbol.prefix):
                suffix = reference[len(symbol.prefix):]
                if suffix.isdigit():
                    used.add(int(suffix))
        number = 1
        while number in used:
            number += 1
        return f"{symbol.prefix}{number}"

    def pin_near(self, scene_pos: QPointF, tolerance: float = 9.0):
        best = None
        best_distance = tolerance
        for component in self.components():
            if component is self._ghost:
                continue
            for index, position in enumerate(component.pin_positions()):
                distance = QLineF(position, scene_pos).length()
                if distance <= best_distance:
                    best = (component, index)
                    best_distance = distance
        return best

    def _snap_target(self, scene_pos: QPointF) -> Tuple[QPointF, Optional[Tuple[ComponentItem, int]]]:
        pin = self.pin_near(scene_pos)
        if pin is not None:
            return pin[0].pin_pos(pin[1]), pin
        return snap_point(scene_pos), None

    # ------------------------------------------------------------------
    # acciones de alto nivel
    # ------------------------------------------------------------------
    def new_pending_item(self) -> ComponentItem:
        if self.pending_factory is not None:
            return self.pending_factory()
        return ComponentItem(self.pending_symbol)

    def reference_taken(self, reference: str) -> bool:
        return any(
            component.reference == reference and component is not self._ghost
            for component in self.components()
        )

    def add_component(self, symbol: Symbol, pos: QPointF, angle: int = 0, mirrored: bool = False) -> ComponentItem:
        return self.place_item(ComponentItem(symbol), pos, angle, mirrored)

    def place_item(
        self,
        item: ComponentItem,
        pos: QPointF,
        angle: int = 0,
        mirrored: bool = False,
    ) -> ComponentItem:
        if not item.reference or self.reference_taken(item.reference):
            item.reference = self.next_reference(item.symbol)
        item.set_orientation(angle, mirrored)
        item.setPos(snap_point(pos))
        self.undo_stack.push(AddItemsCommand(self, [item], f"Agregar {item.symbol.name}"))
        return item

    def delete_selection(self) -> None:
        items = [item for item in self.selectedItems()]
        if items:
            self.undo_stack.push(DeleteItemsCommand(self, items))

    def rotate_selection(self, delta: int) -> None:
        changes = [
            (item, item.angle, item.mirrored, (item.angle + delta) % 360, item.mirrored)
            for item in self.selectedItems()
            if isinstance(item, ComponentItem)
        ]
        if changes:
            self.undo_stack.push(OrientationCommand(changes, "Rotar"))
        elif self._ghost is not None:
            self._ghost.rotate_by(delta)

    def mirror_selection(self) -> None:
        changes = [
            (item, item.angle, item.mirrored, item.angle, not item.mirrored)
            for item in self.selectedItems()
            if isinstance(item, ComponentItem)
        ]
        if changes:
            self.undo_stack.push(OrientationCommand(changes, "Reflejar"))
        elif self._ghost is not None:
            self._ghost.set_orientation(self._ghost.angle, not self._ghost.mirrored)

    def duplicate_selection(self) -> None:
        clones = []
        for item in self.selectedItems():
            if isinstance(item, ComponentItem):
                clone = item.clone()
                clone.reference = self.next_reference(item.symbol)
                clone.set_orientation(item.angle, item.mirrored)
                clone.setPos(item.pos() + QPointF(2 * GRID, 2 * GRID))
                clones.append(clone)
            elif isinstance(item, TextItem):
                clone = TextItem(item.text, item.size)
                clone.setPos(item.pos() + QPointF(2 * GRID, 2 * GRID))
                clones.append(clone)
        if clones:
            self.undo_stack.push(AddItemsCommand(self, clones, "Duplicar"))
            self.clearSelection()
            for clone in clones:
                clone.setSelected(True)

    def clear_document(self) -> None:
        self.undo_stack.clear()
        self.cancel_action()
        self.clear()
        self.notify_changed()

    def content_rect(self) -> QRectF:
        rect = QRectF()
        for item in self.items():
            if item is self._ghost:
                continue
            rect = rect.united(item.sceneBoundingRect())
        return rect

    # ------------------------------------------------------------------
    # eventos de raton
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            if self._wire_points:
                self._finish_wire()
            elif self.tool != SELECT:
                self.set_tool(SELECT)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            self._horizontal_first = not bool(event.modifiers() & Qt.ShiftModifier)
            if self.tool == PLACE and (self.pending_symbol is not None or self.pending_factory is not None):
                pos = snap_point(event.scenePos())
                angle = self._ghost.angle if self._ghost else 0
                mirrored = self._ghost.mirrored if self._ghost else False
                self.place_item(self.new_pending_item(), pos, angle, mirrored)
                event.accept()
                return
            if self.tool == WIRE:
                self._wire_click(event.scenePos())
                event.accept()
                return
            if self.tool == TEXT:
                self._create_text(snap_point(event.scenePos()))
                event.accept()
                return

        super().mousePressEvent(event)
        self._move_origin = [
            (item, QPointF(item.pos()))
            for item in self.selectedItems()
            if item.flags() & QGraphicsItem.ItemIsMovable
        ]

    def mouseMoveEvent(self, event) -> None:
        pos = event.scenePos()
        if self._ghost is not None:
            self._ghost.setPos(snap_point(pos))
        if self._wire_points:
            self._wire_cursor = self._snap_target(pos)[0]
            self._horizontal_first = not bool(event.modifiers() & Qt.ShiftModifier)
            self.update()
        self.status_message.emit(f"x: {pos.x():.0f}   y: {pos.y():.0f}")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        moves = [
            (item, origin, QPointF(item.pos()))
            for item, origin in self._move_origin
            if item.scene() is self and item.pos() != origin
        ]
        if moves:
            self.undo_stack.push(MoveItemsCommand(moves))
            self.notify_changed()
        self._move_origin = []

    def mouseDoubleClickEvent(self, event) -> None:
        if self._wire_points:
            self._finish_wire()
            event.accept()
            return
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        if isinstance(item, (ComponentItem, TextItem)):
            self.edit_requested.emit(item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            if self._wire_points:
                self.cancel_action()
                self.status_message.emit("Cable cancelado.")
            else:
                self.set_tool(SELECT)
            event.accept()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selection()
            event.accept()
            return
        if event.key() == Qt.Key_R:
            self.rotate_selection(-90 if event.modifiers() & Qt.ShiftModifier else 90)
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._wire_points:
            self._finish_wire()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # cables
    # ------------------------------------------------------------------
    def _preview_points(self, target: QPointF) -> List[QPointF]:
        last = self._wire_points[-1]
        if abs(target.x() - last.x()) < 0.01 or abs(target.y() - last.y()) < 0.01:
            return [QPointF(target)]
        if self._horizontal_first:
            return [QPointF(target.x(), last.y()), QPointF(target)]
        return [QPointF(last.x(), target.y()), QPointF(target)]

    def _wire_click(self, scene_pos: QPointF) -> None:
        point, anchor = self._snap_target(scene_pos)
        if not self._wire_points:
            self._wire_points = [point]
            self._wire_start = anchor
            self._wire_cursor = point
            return
        new_points = self._wire_points + self._preview_points(point)
        if anchor is not None:
            self._wire_points = new_points
            self._finish_wire(anchor)
            return
        self._wire_points = new_points
        self._wire_cursor = point
        self.update()

    def _finish_wire(self, end_anchor: Optional[Tuple[ComponentItem, int]] = None) -> None:
        points = clean_points(self._wire_points)
        start = self._wire_start
        self._wire_points = []
        self._wire_start = None
        self._wire_cursor = None
        if len(points) >= 2:
            wire = WireItem(points, start, end_anchor)
            self.undo_stack.push(AddItemsCommand(self, [wire], "Agregar cable"))
        self.update()

    def _create_text(self, pos: QPointF) -> None:
        item = TextItem("Nota", 10)
        item.setPos(pos)
        self.undo_stack.push(AddItemsCommand(self, [item], "Agregar nota"))
        self.edit_requested.emit(item)

    # ------------------------------------------------------------------
    # pintado del lienzo
    # ------------------------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return
        scale = painter.worldTransform().m11()
        left = math.floor(rect.left() / GRID) * GRID
        top = math.floor(rect.top() / GRID) * GRID
        if scale > 0.6:
            painter.setPen(QPen(GRID_MINOR, 0))
            x = left
            while x < rect.right():
                painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
                x += GRID
            y = top
            while y < rect.bottom():
                painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
                y += GRID
        painter.setPen(QPen(GRID_MAJOR, 0))
        major = GRID * 10
        x = math.floor(rect.left() / major) * major
        while x < rect.right():
            painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
            x += major
        y = math.floor(rect.top() / major) * major
        while y < rect.bottom():
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
            y += major

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_junctions(painter)
        if self._wire_points:
            points = self._wire_points[:]
            if self._wire_cursor is not None:
                points += self._preview_points(self._wire_cursor)
            pen = QPen(PREVIEW, 2.0, Qt.DashLine)
            painter.setPen(pen)
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            painter.setBrush(PREVIEW)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(points[0], 3.0, 3.0)

    def _draw_junctions(self, painter: QPainter) -> None:
        wires = self.wires()
        if not wires:
            return
        counts = {}
        for wire in wires:
            for point in wire.endpoints():
                key = (round(point.x(), 1), round(point.y(), 1))
                counts[key] = counts.get(key, 0) + 1
        dots = {key for key, count in counts.items() if count >= 3}
        for wire in wires:
            for point in wire.endpoints():
                key = (round(point.x(), 1), round(point.y(), 1))
                if key in dots:
                    continue
                for other in wires:
                    if other is wire:
                        continue
                    if _point_on_polyline(point, other.points):
                        dots.add(key)
                        break
        painter.setPen(Qt.NoPen)
        painter.setBrush(JUNCTION)
        for x, y in dots:
            painter.drawEllipse(QPointF(x, y), 3.2, 3.2)


def _point_on_polyline(point: QPointF, points: List[QPointF], tolerance: float = 0.6) -> bool:
    for start, end in zip(points, points[1:]):
        if QLineF(start, point).length() < tolerance or QLineF(end, point).length() < tolerance:
            continue
        min_x, max_x = sorted((start.x(), end.x()))
        min_y, max_y = sorted((start.y(), end.y()))
        if min_x - tolerance <= point.x() <= max_x + tolerance and min_y - tolerance <= point.y() <= max_y + tolerance:
            if abs(start.x() - end.x()) < tolerance or abs(start.y() - end.y()) < tolerance:
                return True
    return False

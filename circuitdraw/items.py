"""Elementos graficos del esquematico: componentes, cables y notas de texto."""

from typing import List, Optional, Tuple

from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PyQt5.QtWidgets import QGraphicsItem

from .symbols import GRID, Symbol, snap, symbol as get_symbol

INK = QColor("#14213d")
SELECTED = QColor("#1f7ae0")
PIN_IDLE = QColor("#94a3b8")
PIN_ACTIVE = QColor("#e8590c")
WIRE = QColor("#0f5132")
TEXT = QColor("#334155")


EPSILON = 0.01


def stroke_pen(color: QColor, width: float = 2.0) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _same(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) < EPSILON and abs(a.y() - b.y()) < EPSILON


def _aligned(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) < EPSILON or abs(a.y() - b.y()) < EPSILON


def clean_points(points: List[QPointF]) -> List[QPointF]:
    """Quita puntos repetidos y codos que no cambian de direccion."""
    cleaned: List[QPointF] = []
    for point in points:
        if cleaned and _same(cleaned[-1], point):
            continue
        if len(cleaned) >= 2:
            a, b = cleaned[-2], cleaned[-1]
            same_x = abs(a.x() - b.x()) < EPSILON and abs(b.x() - point.x()) < EPSILON
            same_y = abs(a.y() - b.y()) < EPSILON and abs(b.y() - point.y()) < EPSILON
            if same_x or same_y:
                cleaned.pop()
        cleaned.append(QPointF(point))
    return cleaned


class ComponentItem(QGraphicsItem):
    """Un simbolo colocado en el esquematico."""

    def __init__(self, symbol: Symbol, reference: str = "", value: Optional[str] = None):
        super().__init__()
        self.symbol = symbol
        self.reference = reference
        self.value = symbol.default_value if value is None else value
        self.angle = 0
        self.mirrored = False
        self.show_text = True
        self.wires: List["WireItem"] = []
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self._apply_transform()

    # -- geometria ---------------------------------------------------------
    def _apply_transform(self) -> None:
        from PyQt5.QtGui import QTransform

        transform = QTransform()
        transform.rotate(self.angle)
        if self.mirrored:
            transform.scale(-1, 1)
        self.setTransform(transform)
        self.refresh_wires()

    def boundingRect(self) -> QRectF:
        return self.symbol.body.adjusted(-46, -46, 46, 46)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.symbol.body.adjusted(-4, -4, 4, 4))
        return path

    def pin_pos(self, index: int) -> QPointF:
        return self.mapToScene(self.symbol.pins[index].pos)

    def pin_positions(self) -> List[QPointF]:
        return [self.pin_pos(i) for i in range(len(self.symbol.pins))]

    def pin_direction(self, index: int) -> QPointF:
        """Direccion (unitaria y sobre un eje) en la que sale el cable del pin."""
        pin = self.symbol.pins[index]
        if abs(pin.x) >= abs(pin.y):
            local = QPointF(1.0 if pin.x >= 0 else -1.0, 0.0)
        else:
            local = QPointF(0.0, 1.0 if pin.y > 0 else -1.0)
        mapped = self.transform().map(local)
        if abs(mapped.x()) >= abs(mapped.y()):
            return QPointF(1.0 if mapped.x() >= 0 else -1.0, 0.0)
        return QPointF(0.0, 1.0 if mapped.y() > 0 else -1.0)

    def pin_key(self, index: int) -> str:
        """Identificador del pin en la netlist (unico dentro del componente)."""
        return self.symbol.pins[index].name or str(index + 1)

    def clone(self) -> "ComponentItem":
        copy = ComponentItem(self.symbol, "", self.value)
        copy.show_text = self.show_text
        return copy

    def pin_at(self, scene_pos: QPointF, tolerance: float = GRID) -> Optional[int]:
        for index, position in enumerate(self.pin_positions()):
            if QLineF(position, scene_pos).length() <= tolerance:
                return index
        return None

    def set_orientation(self, angle: int, mirrored: bool) -> None:
        self.angle = angle % 360
        self.mirrored = mirrored
        self.prepareGeometryChange()
        self._apply_transform()
        self.update()

    def rotate_by(self, delta: int) -> None:
        self.set_orientation(self.angle + delta, self.mirrored)

    def refresh_wires(self) -> None:
        for wire in list(self.wires):
            wire.follow_anchors()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(snap(value.x()), snap(value.y()))
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.refresh_wires()
        return super().itemChange(change, value)

    # -- pintado -----------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = SELECTED if self.isSelected() else INK
        painter.setPen(stroke_pen(color))
        painter.setBrush(Qt.NoBrush)
        self.symbol.draw(painter)
        self._paint_pins(painter)
        if self.show_text:
            self._paint_text(painter, color)

    def _paint_pins(self, painter: QPainter) -> None:
        scene = self.scene()
        if scene is not None and getattr(scene, "export_mode", False):
            return
        highlight = bool(scene is not None and getattr(scene, "wiring_hint", False))
        painter.save()
        if highlight:
            painter.setPen(stroke_pen(PIN_ACTIVE, 1.4))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            radius = 3.4
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(PIN_IDLE))
            radius = 2.0
        for pin in self.symbol.pins:
            painter.drawEllipse(pin.pos, radius, radius)
        painter.restore()

    def _paint_text(self, painter: QPainter, color: QColor) -> None:
        lines = [text for text in (self.reference, self.value) if text]
        if not lines:
            return
        inverted, ok = self.transform().inverted()
        if not ok:
            return
        rotated = self.transform().mapRect(self.symbol.body)
        painter.save()
        painter.setTransform(inverted, True)
        painter.setPen(stroke_pen(color, 1.0))
        font = QFont("DejaVu Sans", 8)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        height = metrics.height()
        big = max(rotated.width(), rotated.height()) > 24
        vertical = big and rotated.height() >= rotated.width()
        if vertical:
            # en componentes verticales el texto va al lado para no pisar los cables
            y = rotated.center().y() - height * len(lines) / 2
            for line in lines:
                width = metrics.horizontalAdvance(line) + 8
                painter.drawText(QRectF(rotated.right() + 4, y, width, height), Qt.AlignLeft | Qt.AlignVCenter, line)
                y += height
        else:
            y = rotated.top() - 4 - height * len(lines)
            for line in lines:
                width = max(metrics.horizontalAdvance(line), 20.0) + 8
                rect = QRectF(rotated.center().x() - width / 2, y, width, height)
                painter.drawText(rect, Qt.AlignCenter, line)
                y += height
        painter.restore()

    # -- serializacion -----------------------------------------------------
    def to_dict(self, index: int) -> dict:
        return {
            "id": index,
            "type": self.symbol.key,
            "x": self.x(),
            "y": self.y(),
            "rotation": self.angle,
            "mirrored": self.mirrored,
            "reference": self.reference,
            "value": self.value,
            "show_text": self.show_text,
        }

    @staticmethod
    def from_dict(data: dict) -> "ComponentItem":
        item = ComponentItem(get_symbol(data["type"]), data.get("reference", ""), data.get("value", ""))
        item.apply_common_dict(data)
        return item

    def apply_common_dict(self, data: dict) -> None:
        self.show_text = bool(data.get("show_text", True))
        self.set_orientation(int(data.get("rotation", 0)), bool(data.get("mirrored", False)))
        self.setPos(float(data.get("x", 0.0)), float(data.get("y", 0.0)))


def component_from_dict(data: dict) -> ComponentItem:
    """Crea el componente adecuado segun el tipo guardado."""
    from .ic import ICItem

    if data.get("type") == ICItem.TYPE_KEY:
        return ICItem.from_dict(data)
    return ComponentItem.from_dict(data)


Anchor = Optional[Tuple[ComponentItem, int]]


class WireItem(QGraphicsItem):
    """Cable ortogonal con extremos que pueden engancharse a pines."""

    def __init__(self, points: List[QPointF], start: Anchor = None, end: Anchor = None):
        super().__init__()
        self.points = [QPointF(point) for point in points]
        self.start_anchor: Anchor = None
        self.end_anchor: Anchor = None
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.set_anchor(0, start)
        self.set_anchor(-1, end)
        self.follow_anchors()

    # -- anclajes ----------------------------------------------------------
    def set_anchor(self, which: int, anchor: Anchor) -> None:
        current = self.start_anchor if which == 0 else self.end_anchor
        if current is not None and self in current[0].wires:
            other = self.end_anchor if which == 0 else self.start_anchor
            if other is None or other[0] is not current[0]:
                current[0].wires.remove(self)
        if which == 0:
            self.start_anchor = anchor
        else:
            self.end_anchor = anchor
        if anchor is not None and self not in anchor[0].wires:
            anchor[0].wires.append(self)

    def anchors(self) -> Tuple[Anchor, Anchor]:
        return self.start_anchor, self.end_anchor

    def detach_component(self, component: ComponentItem) -> List[int]:
        detached = []
        if self.start_anchor is not None and self.start_anchor[0] is component:
            self.start_anchor = None
            detached.append(0)
        if self.end_anchor is not None and self.end_anchor[0] is component:
            self.end_anchor = None
            detached.append(-1)
        if self in component.wires:
            component.wires.remove(self)
        return detached

    def follow_anchors(self) -> None:
        if len(self.points) < 2:
            return
        moved = None
        for which, anchor in ((0, self.start_anchor), (-1, self.end_anchor)):
            if anchor is None:
                continue
            component, pin = anchor
            target = component.pin_pos(pin)
            current = self.points[which]
            if _same(current, target):
                continue
            if len(self.points) > 2:
                # el codo vecino se desplaza para que el primer tramo siga
                # teniendo la misma orientacion que antes de mover el pin
                index = 1 if which == 0 else -2
                neighbour = self.points[index]
                if abs(current.y() - neighbour.y()) <= abs(current.x() - neighbour.x()):
                    self.points[index] = QPointF(neighbour.x(), target.y())
                else:
                    self.points[index] = QPointF(target.x(), neighbour.y())
            self.points[which] = target
            moved = which
        if moved is None:
            return
        self._straighten(moved)
        self.prepareGeometryChange()
        self.update()

    def _straighten(self, moved: int) -> None:
        self.points = clean_points(self.points)
        if len(self.points) != 2:
            return
        start, end = self.points
        if _aligned(start, end):
            return
        anchor = self.start_anchor if moved == 0 else self.end_anchor
        other = end if moved == 0 else start
        target = start if moved == 0 else end
        if anchor is not None:
            horizontal = abs(anchor[0].pin_direction(anchor[1]).x()) > 0
        else:
            horizontal = abs(end.x() - start.x()) >= abs(end.y() - start.y())
        elbow = QPointF(other.x(), target.y()) if horizontal else QPointF(target.x(), other.y())
        self.points = [start, elbow, end]

    # -- geometria ---------------------------------------------------------
    def path(self) -> QPainterPath:
        path = QPainterPath()
        if not self.points:
            return path
        path.moveTo(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        return path

    def boundingRect(self) -> QRectF:
        return self.path().boundingRect().adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        return stroker.createStroke(self.path())

    def set_points(self, points: List[QPointF]) -> None:
        self.prepareGeometryChange()
        self.points = [QPointF(point) for point in points]
        self.update()

    def endpoints(self) -> List[QPointF]:
        return [self.points[0], self.points[-1]] if len(self.points) >= 2 else []

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = SELECTED if self.isSelected() else WIRE
        painter.setPen(stroke_pen(color, 2.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

    # -- serializacion -----------------------------------------------------
    def to_dict(self, component_ids: dict) -> dict:
        def anchor_dict(anchor: Anchor):
            if anchor is None or anchor[0] not in component_ids:
                return None
            return {"component": component_ids[anchor[0]], "pin": anchor[1]}

        return {
            "points": [[point.x(), point.y()] for point in self.points],
            "start": anchor_dict(self.start_anchor),
            "end": anchor_dict(self.end_anchor),
        }

    @staticmethod
    def from_dict(data: dict, components: dict) -> "WireItem":
        def anchor(raw) -> Anchor:
            if not raw:
                return None
            component = components.get(raw.get("component"))
            if component is None:
                return None
            pin = int(raw.get("pin", 0))
            if pin >= len(component.symbol.pins):
                return None
            return (component, pin)

        points = [QPointF(float(x), float(y)) for x, y in data.get("points", [])]
        return WireItem(points, anchor(data.get("start")), anchor(data.get("end")))


class TextItem(QGraphicsItem):
    """Nota de texto libre sobre el esquematico."""

    def __init__(self, text: str = "Nota", size: int = 10):
        super().__init__()
        self.text = text
        self.size = size
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(3)

    def _font(self) -> QFont:
        return QFont("DejaVu Sans", self.size)

    def boundingRect(self) -> QRectF:
        metrics = QFontMetricsF(self._font())
        lines = self.text.split("\n") or [""]
        width = max((metrics.horizontalAdvance(line) for line in lines), default=10.0)
        height = metrics.height() * len(lines)
        return QRectF(-4, -4, width + 8, height + 8)

    def set_text(self, text: str, size: Optional[int] = None) -> None:
        self.prepareGeometryChange()
        self.text = text
        if size is not None:
            self.size = size
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(snap(value.x()), snap(value.y()))
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setFont(self._font())
        painter.setPen(stroke_pen(SELECTED if self.isSelected() else TEXT, 1.0))
        rect = self.boundingRect().adjusted(4, 4, -4, -4)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignTop, self.text)
        if self.isSelected():
            painter.setPen(QPen(SELECTED, 0.8, Qt.DashLine))
            painter.drawRect(self.boundingRect())

    def to_dict(self) -> dict:
        return {"x": self.x(), "y": self.y(), "text": self.text, "size": self.size}

    @staticmethod
    def from_dict(data: dict) -> "TextItem":
        item = TextItem(data.get("text", ""), int(data.get("size", 10)))
        item.setPos(float(data.get("x", 0.0)), float(data.get("y", 0.0)))
        return item

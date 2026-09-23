"""Circuitos integrados: simbolo rectangular con encapsulado y pines configurables.

El simbolo se genera a partir del numero de pines y de sus nombres, repartiendo
la mitad en el lado izquierdo (numerados de arriba hacia abajo) y la otra mitad
en el derecho (de abajo hacia arriba), igual que un DIP o un SOIC real.
"""

import math
import re
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QStyleOptionGraphicsItem

from .items import INK, SELECTED, ComponentItem, WireItem, stroke_pen
from .symbols import INTEGRATED, Pin, Symbol

PIN_SPACING = 20
LEAD = 20
EDGE_MARGIN = 20
MIN_BODY_WIDTH = 80

FONT_FAMILY = "DejaVu Sans"
PIN_FONT = 7
NAME_FONT = 8
TITLE_FONT = 9

BODY_FILL = QColor("#f8fafc")
PACKAGE_TEXT = QColor("#64748b")

#: Encapsulados frecuentes que se ofrecen en el dialogo.
COMMON_PACKAGES: Tuple[Tuple[str, int], ...] = (
    ("DIP-8", 8),
    ("DIP-14", 14),
    ("DIP-16", 16),
    ("DIP-20", 20),
    ("DIP-28", 28),
    ("DIP-40", 40),
    ("SOIC-8", 8),
    ("SOIC-14", 14),
    ("SOIC-16", 16),
    ("SOIC-20", 20),
    ("SOIC-28", 28),
    ("SOP-8", 8),
    ("TSSOP-14", 14),
    ("TSSOP-16", 16),
    ("TSSOP-20", 20),
    ("SSOP-16", 16),
    ("SSOP-24", 24),
    ("QFP-32", 32),
    ("QFP-44", 44),
    ("QFP-64", 64),
    ("QFP-100", 100),
    ("QFP-144", 144),
    ("LQFP-144", 144),
    ("QFN-16", 16),
    ("QFN-32", 32),
)

DEFAULT_PACKAGE = "SOIC-8"
MIN_PINS = 2
MAX_PINS = 144


def default_pin_names(count: int) -> List[str]:
    return [str(number) for number in range(1, count + 1)]


def pins_in_package(package: str, fallback: int = 8) -> int:
    """Extrae el numero de pines del nombre del encapsulado (SOIC-8 -> 8)."""
    match = re.search(r"(\d+)", package or "")
    if not match:
        return fallback
    return max(MIN_PINS, min(MAX_PINS, int(match.group(1))))


def rename_package(package: str, count: int) -> str:
    """Actualiza el numero del encapsulado al cambiar la cantidad de pines."""
    if not package:
        return f"DIP-{count}"
    if re.search(r"\d+", package):
        return re.sub(r"\d+", str(count), package, count=1)
    return f"{package}-{count}"


@lru_cache(maxsize=512)
def _text_width(text: str, size: int) -> float:
    if QApplication.instance() is None:  # sin interfaz, estimacion suficiente
        return 6.0 * len(text)
    return QFontMetricsF(QFont(FONT_FAMILY, size)).horizontalAdvance(text)


def ic_geometry(pin_names: Sequence[str]) -> Tuple[float, float, int]:
    """Devuelve (ancho, alto, pines por lado) del cuerpo del integrado."""
    count = max(len(pin_names), MIN_PINS)
    per_side = math.ceil(count / 2)
    height = (per_side - 1) * PIN_SPACING + 2 * EDGE_MARGIN
    longest = max((_text_width(name, NAME_FONT) for name in pin_names), default=8.0)
    width = max(MIN_BODY_WIDTH, 2 * longest + 36)
    width = math.ceil(width / (2 * PIN_SPACING)) * (2 * PIN_SPACING)
    return float(width), float(height), per_side


def _ic_painter(width: float, height: float, pins: Sequence[Pin]):
    body = QRectF(-width / 2, -height / 2, width, height)

    def draw(painter: QPainter) -> None:
        painter.save()
        painter.setBrush(BODY_FILL)
        painter.drawRect(body)
        painter.restore()
        for pin in pins:
            if pin.x < 0:
                painter.drawLine(QPointF(pin.x, pin.y), QPointF(body.left(), pin.y))
            else:
                painter.drawLine(QPointF(body.right(), pin.y), QPointF(pin.x, pin.y))
        # marca del pin 1
        painter.save()
        painter.setBrush(painter.pen().color())
        painter.drawEllipse(QPointF(body.left() + 7, body.top() + 7), 2.4, 2.4)
        painter.restore()

    return draw


def ic_layout(pin_names: Sequence[str], title: str = "", package: str = ""):
    """Ancho y alto finales del cuerpo, pines por lado y nombres normalizados."""
    names = [str(name) for name in pin_names] or default_pin_names(MIN_PINS)
    width, height, per_side = ic_geometry(names)
    legend = max(_text_width(title, TITLE_FONT), _text_width(package, PIN_FONT))
    # cuadrado, o mas ancho si el nombre o los pines no entran
    width = max(width, height, legend + 28)
    width = math.ceil(width / PIN_SPACING) * PIN_SPACING
    return float(width), float(height), per_side, names


def make_ic_symbol(pin_names: Sequence[str], title: str = "", package: str = "") -> Symbol:
    width, height, per_side, names = ic_layout(pin_names, title, package)
    pins: List[Pin] = []
    for index in range(per_side):
        y = -height / 2 + EDGE_MARGIN + index * PIN_SPACING
        pins.append(Pin(-width / 2 - LEAD, y, names[index]))
    for offset, index in enumerate(range(per_side, len(names))):
        y = height / 2 - EDGE_MARGIN - offset * PIN_SPACING
        pins.append(Pin(width / 2 + LEAD, y, names[index]))
    body = QRectF(-width / 2 - LEAD, -height / 2, width + 2 * LEAD, height)
    return Symbol(
        ICItem.TYPE_KEY,
        "Circuito integrado",
        INTEGRATED,
        "U",
        tuple(pins),
        _ic_painter(width, height, pins),
        "",
        body,
    )


class ICItem(ComponentItem):
    """Integrado rectangular con encapsulado, nombre y pines editables."""

    TYPE_KEY = "ic"

    def __init__(
        self,
        package: str = DEFAULT_PACKAGE,
        pin_names: Optional[Sequence[str]] = None,
        name: str = "",
        reference: str = "",
    ):
        names = [str(pin) for pin in pin_names] if pin_names else default_pin_names(
            pins_in_package(package)
        )
        super().__init__(make_ic_symbol(names, name, package), reference, name)
        self.package = package
        self.pin_names = names

    # ------------------------------------------------------------------
    @property
    def pin_count(self) -> int:
        return len(self.pin_names)

    def inner_rect(self) -> QRectF:
        width, height, _, _ = ic_layout(self.pin_names, self.value, self.package)
        return QRectF(-width / 2, -height / 2, width, height)

    def pin_key(self, index: int) -> str:
        number = str(index + 1)
        name = self.pin_names[index] if index < len(self.pin_names) else number
        return number if name == number else f"{number}/{name}"

    def clone(self) -> "ICItem":
        copy = ICItem(self.package, self.pin_names, self.value, "")
        copy.show_text = self.show_text
        return copy

    def configure(
        self,
        package: str,
        pin_names: Sequence[str],
        value: Optional[str] = None,
    ) -> List[Tuple[WireItem, int, Tuple[ComponentItem, int]]]:
        """Aplica una nueva configuracion.

        Devuelve los anclajes que hubo que soltar porque su pin ya no existe,
        para que el comando de deshacer pueda restaurarlos.
        """
        self.prepareGeometryChange()
        self.package = package
        self.pin_names = [str(pin) for pin in pin_names] or default_pin_names(MIN_PINS)
        if value is not None:
            self.value = value
        self.symbol = make_ic_symbol(self.pin_names, self.value, self.package)
        detached: List[Tuple[WireItem, int, Tuple[ComponentItem, int]]] = []
        for wire in list(self.wires):
            for which, anchor in ((0, wire.start_anchor), (-1, wire.end_anchor)):
                if anchor is None or anchor[0] is not self:
                    continue
                if anchor[1] >= self.pin_count:
                    detached.append((wire, which, anchor))
                    wire.set_anchor(which, None)
        self.refresh_wires()
        self.update()
        return detached

    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = SELECTED if self.isSelected() else INK
        painter.setPen(stroke_pen(color))
        painter.setBrush(Qt.NoBrush)
        self.symbol.draw(painter)
        self._paint_pins(painter)
        self._paint_ic_text(painter, color)

    def _paint_ic_text(self, painter: QPainter, color: QColor) -> None:
        inverted, ok = self.transform().inverted()
        if not ok:
            return
        transform = self.transform()
        inner = self.inner_rect()
        mapped_inner = transform.mapRect(inner)
        mapped_outer = transform.mapRect(self.symbol.body)

        painter.save()
        painter.setTransform(inverted, True)
        painter.setPen(stroke_pen(color, 1.0))
        self._paint_center_text(painter, color, mapped_inner)
        if self.show_text and self.reference:
            painter.setPen(stroke_pen(color, 1.0))
            painter.setFont(QFont(FONT_FAMILY, NAME_FONT))
            height = QFontMetricsF(painter.font()).height()
            rect = QRectF(mapped_outer.center().x() - 60, mapped_outer.top() - 4 - height, 120, height)
            painter.drawText(rect, Qt.AlignCenter, self.reference)
        self._paint_pin_text(painter, color, transform, inner, mapped_inner)
        painter.restore()

    def _paint_center_text(self, painter: QPainter, color: QColor, mapped_inner: QRectF) -> None:
        title = self.value or self.symbol.name
        painter.setFont(QFont(FONT_FAMILY, TITLE_FONT))
        metrics = QFontMetricsF(painter.font())
        center = mapped_inner.center()
        painter.drawText(
            QRectF(center.x() - 60, center.y() - metrics.height(), 120, metrics.height()),
            Qt.AlignCenter,
            title,
        )
        if self.package:
            painter.setPen(stroke_pen(PACKAGE_TEXT, 1.0))
            painter.setFont(QFont(FONT_FAMILY, PIN_FONT))
            small = QFontMetricsF(painter.font())
            painter.drawText(
                QRectF(center.x() - 60, center.y() + 1, 120, small.height()),
                Qt.AlignCenter,
                self.package,
            )
            painter.setPen(stroke_pen(color, 1.0))

    def _paint_pin_text(
        self,
        painter: QPainter,
        color: QColor,
        transform,
        inner: QRectF,
        mapped_inner: QRectF,
    ) -> None:
        number_font = QFont(FONT_FAMILY, PIN_FONT)
        name_font = QFont(FONT_FAMILY, NAME_FONT)
        center = mapped_inner.center()
        for index, pin in enumerate(self.symbol.pins):
            edge_x = inner.left() if pin.x < 0 else inner.right()
            lead_middle = transform.map(QPointF((pin.x + edge_x) / 2, pin.y))
            mapped_pin = transform.map(pin.pos)
            delta = mapped_pin - center
            horizontal = abs(delta.x()) >= abs(delta.y())

            painter.setFont(number_font)
            painter.setPen(stroke_pen(color, 1.0))
            number = str(index + 1)
            if horizontal:
                painter.drawText(
                    QRectF(lead_middle.x() - 15, lead_middle.y() - 15, 30, 12),
                    Qt.AlignCenter,
                    number,
                )
            else:
                painter.drawText(
                    QRectF(lead_middle.x() + 4, lead_middle.y() - 7, 22, 14),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    number,
                )

            name = self.pin_names[index] if index < len(self.pin_names) else number
            if name == number:
                continue
            painter.setFont(name_font)
            if horizontal:
                rect = QRectF(
                    mapped_inner.left() + 6,
                    mapped_pin.y() - 7,
                    mapped_inner.width() - 12,
                    14,
                )
                alignment = Qt.AlignVCenter | (Qt.AlignLeft if delta.x() < 0 else Qt.AlignRight)
                painter.drawText(rect, alignment, name)
            else:
                # con el integrado girado los nombres se leen a lo largo del pin
                painter.save()
                if delta.y() < 0:
                    painter.translate(mapped_pin.x(), mapped_inner.top() + 6)
                    painter.rotate(90)
                else:
                    painter.translate(mapped_pin.x(), mapped_inner.bottom() - 6)
                    painter.rotate(-90)
                painter.drawText(
                    QRectF(0, -7, mapped_inner.height() - 12, 14),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    name,
                )
                painter.restore()

    # ------------------------------------------------------------------
    def to_dict(self, index: int) -> dict:
        data = super().to_dict(index)
        data["package"] = self.package
        data["pin_names"] = list(self.pin_names)
        return data

    @staticmethod
    def from_dict(data: dict) -> "ICItem":
        package = data.get("package", DEFAULT_PACKAGE)
        names = data.get("pin_names") or default_pin_names(pins_in_package(package))
        item = ICItem(package, names, data.get("value", ""), data.get("reference", ""))
        item.apply_common_dict(data)
        return item


def render_ic_preview(item: ICItem, size: QSize) -> QPixmap:
    """Dibuja el integrado en un QPixmap (se usa en la vista previa del dialogo)."""
    pixmap = QPixmap(size)
    pixmap.fill(Qt.white)
    area = item.symbol.body.adjusted(-6, -22, 6, 22)
    scale = min(size.width() / area.width(), size.height() / area.height(), 1.6)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(size.width() / 2, size.height() / 2)
    painter.scale(scale, scale)
    painter.translate(-area.center())
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return pixmap


def ic_palette_symbol() -> Symbol:
    """Simbolo generico que se usa para el icono del panel de componentes."""
    return make_ic_symbol(default_pin_names(8))

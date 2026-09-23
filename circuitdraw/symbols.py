"""Biblioteca de simbolos electronicos.

Cada simbolo se dibuja centrado en el origen y sus pines caen siempre en
multiplos de GRID, de modo que al rotar 90 grados siguen alineados a la rejilla.
"""

from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Callable, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QFont, QPainter, QPainterPath, QPolygonF

GRID = 10


@dataclass(frozen=True)
class Pin:
    x: float
    y: float
    name: str = ""

    @property
    def pos(self) -> QPointF:
        return QPointF(self.x, self.y)


@dataclass(frozen=True, eq=False)
class Symbol:
    key: str
    name: str
    category: str
    prefix: str
    pins: Tuple[Pin, ...]
    draw: Callable[[QPainter], None]
    default_value: str = ""
    body: QRectF = field(default_factory=lambda: QRectF(-30, -30, 60, 60))


# --------------------------------------------------------------------------
# utilidades de dibujo
# --------------------------------------------------------------------------

def _polyline(painter: QPainter, *points) -> None:
    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))


def _leads(painter: QPainter, inner: float, y: float = 0.0, outer: float = 30.0) -> None:
    painter.drawLine(QPointF(-outer, y), QPointF(-inner, y))
    painter.drawLine(QPointF(inner, y), QPointF(outer, y))


def _arrow_head(painter: QPainter, tip: QPointF, angle_deg: float, size: float = 9.0) -> None:
    a = radians(angle_deg)
    back = QPointF(tip.x() - size * cos(a), tip.y() - size * sin(a))
    half = size * 0.38
    left = QPointF(back.x() - half * sin(a), back.y() + half * cos(a))
    right = QPointF(back.x() + half * sin(a), back.y() - half * cos(a))
    path = QPainterPath(tip)
    path.lineTo(left)
    path.lineTo(right)
    path.closeSubpath()
    painter.save()
    painter.setBrush(painter.pen().color())
    painter.drawPath(path)
    painter.restore()


def _glyph(painter: QPainter, text: str, rect: QRectF, size: int = 13, bold: bool = True) -> None:
    font = QFont("DejaVu Sans", size)
    font.setBold(bold)
    painter.save()
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignCenter, text)
    painter.restore()


# --------------------------------------------------------------------------
# simbolos
# --------------------------------------------------------------------------

def _draw_resistor(painter: QPainter) -> None:
    _leads(painter, 15)
    _polyline(
        painter,
        (-15, 0), (-12.5, -8), (-7.5, 8), (-2.5, -8),
        (2.5, 8), (7.5, -8), (12.5, 8), (15, 0),
    )


def _draw_potentiometer(painter: QPainter) -> None:
    _draw_resistor(painter)
    painter.drawLine(QPointF(0, -30), QPointF(0, -16))
    _arrow_head(painter, QPointF(0, -10), 90)


def _draw_capacitor(painter: QPainter) -> None:
    _leads(painter, 4)
    painter.drawLine(QPointF(-4, -13), QPointF(-4, 13))
    painter.drawLine(QPointF(4, -13), QPointF(4, 13))


def _draw_capacitor_polarized(painter: QPainter) -> None:
    _leads(painter, 5)
    painter.drawLine(QPointF(-5, -13), QPointF(-5, 13))
    path = QPainterPath()
    path.moveTo(9, -13)
    path.quadTo(1, 0, 9, 13)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.restore()
    painter.drawLine(QPointF(-16, -16), QPointF(-8, -16))
    painter.drawLine(QPointF(-12, -20), QPointF(-12, -12))


def _draw_inductor(painter: QPainter) -> None:
    _leads(painter, 16)
    for x in (-16, -8, 0, 8):
        painter.drawArc(QRectF(x, -4, 8, 8), 0, 180 * 16)


def _draw_diode(painter: QPainter) -> None:
    _leads(painter, 9)
    path = QPainterPath(QPointF(-9, -11))
    path.lineTo(-9, 11)
    path.lineTo(9, 0)
    path.closeSubpath()
    painter.save()
    painter.setBrush(painter.pen().color())
    painter.drawPath(path)
    painter.restore()
    painter.drawLine(QPointF(9, -11), QPointF(9, 11))


def _draw_led(painter: QPainter) -> None:
    _draw_diode(painter)
    for dx in (-4, 4):
        start = QPointF(dx, -13)
        tip = QPointF(dx + 9, -23)
        painter.drawLine(start, tip)
        _arrow_head(painter, tip, -48, 7)


def _draw_zener(painter: QPainter) -> None:
    _draw_diode(painter)
    painter.drawLine(QPointF(9, -11), QPointF(2, -16))
    painter.drawLine(QPointF(9, 11), QPointF(16, 16))


def _draw_battery(painter: QPainter) -> None:
    painter.drawLine(QPointF(-30, 0), QPointF(-9, 0))
    painter.drawLine(QPointF(9, 0), QPointF(30, 0))
    painter.drawLine(QPointF(-9, -14), QPointF(-9, 14))
    painter.drawLine(QPointF(-3, -7), QPointF(-3, 7))
    painter.drawLine(QPointF(3, -14), QPointF(3, 14))
    painter.drawLine(QPointF(9, -7), QPointF(9, 7))


def _draw_source_dc(painter: QPainter) -> None:
    _leads(painter, 16)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(-16, -16, 32, 32))
    painter.restore()
    painter.drawLine(QPointF(-11, -4), QPointF(-11, 4))
    painter.drawLine(QPointF(-15, 0), QPointF(-7, 0))
    painter.drawLine(QPointF(7, 0), QPointF(15, 0))


def _draw_source_ac(painter: QPainter) -> None:
    _leads(painter, 16)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(-16, -16, 32, 32))
    path = QPainterPath(QPointF(-10, 0))
    path.cubicTo(-6, -12, -1, -12, 0, 0)
    path.cubicTo(1, 12, 6, 12, 10, 0)
    painter.drawPath(path)
    painter.restore()


def _draw_ground(painter: QPainter) -> None:
    painter.drawLine(QPointF(0, -20), QPointF(0, 0))
    painter.drawLine(QPointF(-14, 0), QPointF(14, 0))
    painter.drawLine(QPointF(-9, 6), QPointF(9, 6))
    painter.drawLine(QPointF(-4, 12), QPointF(4, 12))


def _draw_supply(painter: QPainter) -> None:
    painter.drawLine(QPointF(0, 20), QPointF(0, -4))
    painter.drawLine(QPointF(-12, -4), QPointF(12, -4))
    _arrow_head(painter, QPointF(0, -12), -90, 10)


def _draw_switch(painter: QPainter) -> None:
    painter.drawLine(QPointF(-30, 0), QPointF(-14, 0))
    painter.drawLine(QPointF(14, 0), QPointF(30, 0))
    painter.save()
    painter.setBrush(Qt.white)
    painter.drawEllipse(QRectF(-16.5, -2.5, 5, 5))
    painter.drawEllipse(QRectF(11.5, -2.5, 5, 5))
    painter.restore()
    painter.drawLine(QPointF(-13, -1), QPointF(12, -14))


def _draw_push_button(painter: QPainter) -> None:
    painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
    painter.drawLine(QPointF(12, 0), QPointF(30, 0))
    painter.drawLine(QPointF(-12, 0), QPointF(-12, -6))
    painter.drawLine(QPointF(12, 0), QPointF(12, -6))
    painter.drawLine(QPointF(-16, -9), QPointF(16, -9))
    painter.drawLine(QPointF(0, -9), QPointF(0, -18))
    painter.drawLine(QPointF(-8, -18), QPointF(8, -18))


def _draw_fuse(painter: QPainter) -> None:
    _leads(painter, 16)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(-16, -8, 32, 16))
    painter.restore()
    painter.drawLine(QPointF(-16, 0), QPointF(16, 0))


def _draw_lamp(painter: QPainter) -> None:
    _leads(painter, 14)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(-14, -14, 28, 28))
    painter.restore()
    d = 14 * 0.7071
    painter.drawLine(QPointF(-d, -d), QPointF(d, d))
    painter.drawLine(QPointF(-d, d), QPointF(d, -d))


def _meter(letter: str) -> Callable[[QPainter], None]:
    def draw(painter: QPainter) -> None:
        _leads(painter, 16)
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(-16, -16, 32, 32))
        painter.restore()
        _glyph(painter, letter, QRectF(-16, -16, 32, 32))

    return draw


def _draw_bjt(npn: bool) -> Callable[[QPainter], None]:
    def draw(painter: QPainter) -> None:
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(-20, -20, 40, 40))
        painter.restore()
        painter.drawLine(QPointF(-30, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(-10, -14), QPointF(-10, 14))
        _polyline(painter, (-10, -7), (10, -18), (10, -30))
        _polyline(painter, (-10, 7), (10, 18), (10, 30))
        if npn:
            _arrow_head(painter, QPointF(7.2, 16.5), 29)
        else:
            _arrow_head(painter, QPointF(-7.5, 8.3), 180 + 29)

    return draw


def _draw_mosfet(painter: QPainter) -> None:
    painter.drawLine(QPointF(-30, 0), QPointF(-17, 0))
    painter.drawLine(QPointF(-17, -14), QPointF(-17, 14))
    for y0, y1 in ((-15, -6), (-4, 4), (6, 15)):
        painter.drawLine(QPointF(-10, y0), QPointF(-10, y1))
    _polyline(painter, (-10, -11), (10, -11), (10, -30))
    _polyline(painter, (-10, 11), (10, 11), (10, 30))
    painter.drawLine(QPointF(-10, 0), QPointF(10, 0))
    painter.drawLine(QPointF(10, 0), QPointF(10, 11))
    _arrow_head(painter, QPointF(-6, 11), 180, 8)


def _draw_opamp(painter: QPainter) -> None:
    painter.drawLine(QPointF(-30, -10), QPointF(-20, -10))
    painter.drawLine(QPointF(-30, 10), QPointF(-20, 10))
    painter.drawLine(QPointF(22, 0), QPointF(30, 0))
    path = QPainterPath(QPointF(-20, -24))
    path.lineTo(-20, 24)
    path.lineTo(22, 0)
    path.closeSubpath()
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.restore()
    painter.drawLine(QPointF(-17, -10), QPointF(-9, -10))
    painter.drawLine(QPointF(-13, -14), QPointF(-13, -6))
    painter.drawLine(QPointF(-17, 10), QPointF(-9, 10))


def _draw_motor(painter: QPainter) -> None:
    _leads(painter, 16)
    painter.save()
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(-16, -16, 32, 32))
    painter.restore()
    _glyph(painter, "M", QRectF(-16, -16, 32, 32))


def _draw_terminal(painter: QPainter) -> None:
    painter.save()
    painter.setBrush(Qt.white)
    painter.drawEllipse(QRectF(-5, -5, 10, 10))
    painter.restore()


INTEGRATED = "Integrados"
PASSIVE = "Pasivos"
SOURCES = "Fuentes y referencias"
SEMI = "Semiconductores"
SWITCHES = "Interruptores y proteccion"
LOADS = "Cargas y medicion"

SYMBOLS = (
    Symbol("resistor", "Resistencia", PASSIVE, "R",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_resistor, "1k",
           QRectF(-30, -10, 60, 20)),
    Symbol("potentiometer", "Potenciometro", PASSIVE, "RV",
           (Pin(-30, 0, "1"), Pin(30, 0, "2"), Pin(0, -30, "3")), _draw_potentiometer, "10k",
           QRectF(-30, -30, 60, 40)),
    Symbol("capacitor", "Condensador", PASSIVE, "C",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_capacitor, "100n",
           QRectF(-30, -15, 60, 30)),
    Symbol("capacitor_pol", "Condensador electrolitico", PASSIVE, "C",
           (Pin(-30, 0, "+"), Pin(30, 0, "-")), _draw_capacitor_polarized, "10u",
           QRectF(-30, -22, 60, 37)),
    Symbol("inductor", "Inductor", PASSIVE, "L",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_inductor, "10m",
           QRectF(-30, -10, 60, 14)),
    Symbol("battery", "Pila / bateria", SOURCES, "BT",
           (Pin(-30, 0, "+"), Pin(30, 0, "-")), _draw_battery, "9V",
           QRectF(-30, -15, 60, 30)),
    Symbol("source_dc", "Fuente DC", SOURCES, "V",
           (Pin(-30, 0, "+"), Pin(30, 0, "-")), _draw_source_dc, "12V",
           QRectF(-30, -17, 60, 34)),
    Symbol("source_ac", "Fuente AC", SOURCES, "V",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_source_ac, "230V~",
           QRectF(-30, -17, 60, 34)),
    Symbol("ground", "Tierra (GND)", SOURCES, "GND",
           (Pin(0, -20, "1"),), _draw_ground, "",
           QRectF(-15, -20, 30, 34)),
    Symbol("supply", "Alimentacion (VCC)", SOURCES, "VCC",
           (Pin(0, 20, "1"),), _draw_supply, "5V",
           QRectF(-13, -14, 26, 34)),
    Symbol("terminal", "Terminal / nodo", SOURCES, "T",
           (Pin(0, 0, "1"),), _draw_terminal, "",
           QRectF(-6, -6, 12, 12)),
    Symbol("diode", "Diodo", SEMI, "D",
           (Pin(-30, 0, "A"), Pin(30, 0, "K")), _draw_diode, "1N4148",
           QRectF(-30, -12, 60, 24)),
    Symbol("led", "LED", SEMI, "D",
           (Pin(-30, 0, "A"), Pin(30, 0, "K")), _draw_led, "rojo",
           QRectF(-30, -26, 60, 38)),
    Symbol("zener", "Diodo zener", SEMI, "D",
           (Pin(-30, 0, "A"), Pin(30, 0, "K")), _draw_zener, "5V1",
           QRectF(-30, -17, 60, 34)),
    Symbol("npn", "Transistor NPN", SEMI, "Q",
           (Pin(-30, 0, "B"), Pin(10, -30, "C"), Pin(10, 30, "E")), _draw_bjt(True), "BC547",
           QRectF(-30, -30, 60, 60)),
    Symbol("pnp", "Transistor PNP", SEMI, "Q",
           (Pin(-30, 0, "B"), Pin(10, -30, "C"), Pin(10, 30, "E")), _draw_bjt(False), "BC557",
           QRectF(-30, -30, 60, 60)),
    Symbol("nmos", "MOSFET canal N", SEMI, "M",
           (Pin(-30, 0, "G"), Pin(10, -30, "D"), Pin(10, 30, "S")), _draw_mosfet, "IRF540",
           QRectF(-30, -30, 60, 60)),
    Symbol("opamp", "Amplificador operacional", SEMI, "U",
           (Pin(-30, -10, "+"), Pin(-30, 10, "-"), Pin(30, 0, "OUT")), _draw_opamp, "LM358",
           QRectF(-30, -25, 60, 50)),
    Symbol("switch", "Interruptor", SWITCHES, "SW",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_switch, "",
           QRectF(-30, -16, 60, 22)),
    Symbol("push_button", "Pulsador", SWITCHES, "SW",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_push_button, "",
           QRectF(-30, -20, 60, 26)),
    Symbol("fuse", "Fusible", SWITCHES, "F",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_fuse, "1A",
           QRectF(-30, -10, 60, 20)),
    Symbol("lamp", "Lampara", LOADS, "LA",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_lamp, "",
           QRectF(-30, -15, 60, 30)),
    Symbol("motor", "Motor", LOADS, "M",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _draw_motor, "",
           QRectF(-30, -17, 60, 34)),
    Symbol("voltmeter", "Voltimetro", LOADS, "MV",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _meter("V"), "",
           QRectF(-30, -17, 60, 34)),
    Symbol("ammeter", "Amperimetro", LOADS, "MA",
           (Pin(-30, 0, "1"), Pin(30, 0, "2")), _meter("A"), "",
           QRectF(-30, -17, 60, 34)),
)

SYMBOLS_BY_KEY = {symbol.key: symbol for symbol in SYMBOLS}

CATEGORIES = (PASSIVE, SOURCES, SEMI, INTEGRATED, SWITCHES, LOADS)


def symbol(key: str) -> Symbol:
    try:
        return SYMBOLS_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Simbolo desconocido: {key!r}") from exc


def snap(value: float, grid: int = GRID) -> float:
    return round(value / grid) * grid


def snap_point(point: QPointF, grid: int = GRID) -> QPointF:
    return QPointF(snap(point.x(), grid), snap(point.y(), grid))

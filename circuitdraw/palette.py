"""Panel lateral con la biblioteca de componentes."""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .items import INK
from .symbols import CATEGORIES, INTEGRATED, SYMBOLS, Symbol

ICON_SIZE = QSize(54, 40)
IC_ENTRY = "__ic__"


def symbol_pixmap(symbol: Symbol, size: QSize = ICON_SIZE, color: QColor = INK) -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    body = symbol.body.adjusted(-4, -4, 4, 4)
    scale = min(size.width() / body.width(), size.height() / body.height())
    painter.translate(size.width() / 2, size.height() / 2)
    painter.scale(scale, scale)
    painter.translate(-body.center())
    pen = QPen(color, 2.0 / max(scale, 0.01))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    symbol.draw(painter)
    painter.end()
    return pixmap


def symbol_icon(symbol: Symbol) -> QIcon:
    return QIcon(symbol_pixmap(symbol))


class ComponentPalette(QWidget):
    symbol_chosen = pyqtSignal(object)
    ic_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar componente...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(ICON_SIZE)
        self.tree.setIndentation(10)
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._activate)
        self.tree.itemActivated.connect(self._activate)
        layout.addWidget(self.tree)

        self._groups = {}
        for category in CATEGORIES:
            group = QTreeWidgetItem(self.tree, [category])
            group.setFlags(Qt.ItemIsEnabled)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setExpanded(True)
            self._groups[category] = group

        for symbol in SYMBOLS:
            item = QTreeWidgetItem(self._groups[symbol.category], [symbol.name])
            item.setIcon(0, symbol_icon(symbol))
            item.setData(0, Qt.UserRole, symbol)
            tip = ", ".join(pin.name for pin in symbol.pins)
            item.setToolTip(0, f"{symbol.name}  ({symbol.prefix})\nPines: {tip}")

        self._add_ic_entry()

    def _add_ic_entry(self) -> None:
        from .ic import ic_palette_symbol

        item = QTreeWidgetItem(self._groups[INTEGRATED], ["Circuito integrado..."])
        item.setIcon(0, QIcon(symbol_pixmap(ic_palette_symbol())))
        item.setData(0, Qt.UserRole, IC_ENTRY)
        item.setToolTip(
            0,
            "Integrado con encapsulado configurable (DIP, SOIC, TSSOP...)\n"
            "Se elige el nombre, el numero de pines y el nombre de cada pin.",
        )

    def _activate(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.UserRole)
        if data == IC_ENTRY:
            self.ic_requested.emit()
        elif isinstance(data, Symbol):
            self.symbol_chosen.emit(data)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for category, group in self._groups.items():
            visible_children = 0
            for index in range(group.childCount()):
                child = group.child(index)
                data = child.data(0, Qt.UserRole)
                haystack = [child.text(0).lower(), category.lower()]
                if isinstance(data, Symbol):
                    haystack += [data.name.lower(), data.key.lower()]
                else:
                    haystack += ["integrado", "ic", "chip", "dip", "soic"]
                matches = not needle or any(needle in text for text in haystack)
                child.setHidden(not matches)
                visible_children += int(matches)
            group.setHidden(visible_children == 0)
            if needle:
                group.setExpanded(True)

    def clear_selection(self) -> None:
        self.tree.clearSelection()

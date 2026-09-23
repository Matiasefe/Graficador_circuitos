"""Dialogo para crear y editar circuitos integrados."""

from typing import Dict, List, Optional

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ic import (
    COMMON_PACKAGES,
    DEFAULT_PACKAGE,
    ICItem,
    MAX_PINS,
    MIN_PINS,
    default_pin_names,
    pins_in_package,
    rename_package,
    render_ic_preview,
)

PREVIEW_SIZE = QSize(240, 320)
CUSTOM = "Personalizado..."


class ICDialog(QDialog):
    """Pide nombre, encapsulado, numero de pines y nombres de cada pin."""

    def __init__(
        self,
        parent=None,
        name: str = "",
        reference: str = "",
        package: str = DEFAULT_PACKAGE,
        pin_names: Optional[List[str]] = None,
        title: str = "Nuevo circuito integrado",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._updating = False

        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body)

        form_container = QWidget()
        form = QFormLayout(form_container)
        form.setLabelAlignment(Qt.AlignRight)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("LM358, NE555, ATmega328P...")
        self.reference_edit = QLineEdit(reference)
        self.reference_edit.setPlaceholderText("U1")

        self.preset_combo = QComboBox()
        for label, _pins in COMMON_PACKAGES:
            self.preset_combo.addItem(label)
        self.preset_combo.addItem(CUSTOM)

        self.package_edit = QLineEdit(package)
        self.package_edit.setPlaceholderText("SOIC-8")

        self.pins_spin = QSpinBox()
        self.pins_spin.setRange(MIN_PINS, MAX_PINS)
        self.pins_spin.setSingleStep(2)

        form.addRow("Nombre", self.name_edit)
        form.addRow("Referencia", self.reference_edit)
        form.addRow("Encapsulado frecuente", self.preset_combo)
        form.addRow("Encapsulado (footprint)", self.package_edit)
        form.addRow("Numero de pines", self.pins_spin)

        pins_group = QGroupBox("Pines")
        pins_layout = QVBoxLayout(pins_group)
        hint = QLabel(
            "Escribe el nombre de cada pin (VCC, GND, OUT...). Si lo dejas con su "
            "numero, en el esquematico solo se muestra el numero."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;")
        pins_layout.addWidget(hint)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Pin", "Nombre"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        pins_layout.addWidget(self.table)

        reset_button = QPushButton("Restablecer nombres")
        reset_button.clicked.connect(self._reset_names)
        pins_layout.addWidget(reset_button, alignment=Qt.AlignLeft)

        left = QVBoxLayout()
        left.addWidget(form_container)
        left.addWidget(pins_group)
        body.addLayout(left, 3)

        preview_box = QGroupBox("Vista previa")
        preview_layout = QVBoxLayout(preview_box)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setMinimumSize(PREVIEW_SIZE)
        self.preview.setStyleSheet("background:#ffffff;")
        preview_layout.addWidget(self.preview)
        body.addWidget(preview_box, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        names = list(pin_names) if pin_names else default_pin_names(pins_in_package(package))
        self._load(package, names)

        self.preset_combo.currentTextChanged.connect(self._preset_chosen)
        self.package_edit.textChanged.connect(self._package_typed)
        self.pins_spin.valueChanged.connect(self._pins_changed)
        self.table.itemChanged.connect(self._pin_renamed)
        self.name_edit.textChanged.connect(self._refresh_preview)

    # ------------------------------------------------------------------
    def _load(self, package: str, names: List[str]) -> None:
        self._updating = True
        self.package_edit.setText(package)
        self.pins_spin.setValue(len(names))
        index = self.preset_combo.findText(package)
        self.preset_combo.setCurrentIndex(index if index >= 0 else self.preset_combo.count() - 1)
        self._fill_table(names)
        self._updating = False
        self._refresh_preview()

    def _fill_table(self, names: List[str]) -> None:
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            number = QTableWidgetItem(str(row + 1))
            number.setFlags(Qt.ItemIsEnabled)
            number.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, number)
            self.table.setItem(row, 1, QTableWidgetItem(name))

    def pin_names(self) -> List[str]:
        names = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            text = item.text().strip() if item else ""
            names.append(text or str(row + 1))
        return names

    # ------------------------------------------------------------------
    def _preset_chosen(self, text: str) -> None:
        if self._updating or text == CUSTOM:
            return
        self._updating = True
        self.package_edit.setText(text)
        count = pins_in_package(text)
        self.pins_spin.setValue(count)
        self._resize_pins(count)
        self._updating = False
        self._refresh_preview()

    def _package_typed(self, text: str) -> None:
        if self._updating:
            return
        self._updating = True
        index = self.preset_combo.findText(text)
        self.preset_combo.setCurrentIndex(index if index >= 0 else self.preset_combo.count() - 1)
        self._updating = False
        self._refresh_preview()

    def _pins_changed(self, count: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._resize_pins(count)
        package = rename_package(self.package_edit.text().strip(), count)
        self.package_edit.setText(package)
        index = self.preset_combo.findText(package)
        self.preset_combo.setCurrentIndex(index if index >= 0 else self.preset_combo.count() - 1)
        self._updating = False
        self._refresh_preview()

    def _resize_pins(self, count: int) -> None:
        names = self.pin_names()
        if count > len(names):
            names += default_pin_names(count)[len(names):]
        self._fill_table(names[:count])

    def _pin_renamed(self, _item) -> None:
        if not self._updating:
            self._refresh_preview()

    def _reset_names(self) -> None:
        self._updating = True
        self._fill_table(default_pin_names(self.pins_spin.value()))
        self._updating = False
        self._refresh_preview()

    # ------------------------------------------------------------------
    def _refresh_preview(self) -> None:
        item = ICItem(
            self.package_edit.text().strip() or DEFAULT_PACKAGE,
            self.pin_names(),
            self.name_edit.text().strip(),
            self.reference_edit.text().strip(),
        )
        self.preview.setPixmap(render_ic_preview(item, PREVIEW_SIZE))

    def config(self) -> Dict:
        return {
            "value": self.name_edit.text().strip(),
            "reference": self.reference_edit.text().strip(),
            "package": self.package_edit.text().strip() or DEFAULT_PACKAGE,
            "pin_names": self.pin_names(),
        }

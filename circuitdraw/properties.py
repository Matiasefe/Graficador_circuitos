"""Panel de propiedades del elemento seleccionado."""

from PyQt5 import sip
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .commands import EditComponentCommand, EditTextCommand, OrientationCommand
from .ic import ICItem
from .items import ComponentItem, TextItem, WireItem

ANGLES = (0, 90, 180, 270)


class PropertiesPanel(QWidget):
    ic_edit_requested = pyqtSignal(object)

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._target = None
        self._loading = False
        self._text_before = ("", 10)
        # las notas se editan en vivo y se agrupan en un solo paso de deshacer
        self._text_timer = QTimer(self)
        self._text_timer.setInterval(700)
        self._text_timer.setSingleShot(True)
        self._text_timer.timeout.connect(self._flush_text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.stack.addWidget(self._build_empty())
        self.stack.addWidget(self._build_component())
        self.stack.addWidget(self._build_text())

        scene.selectionChanged.connect(self.refresh)
        scene.document_changed.connect(self._refresh_from_document)
        scene.edit_requested.connect(self.focus_item)
        self.refresh()

    # ------------------------------------------------------------------
    def _build_empty(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Selecciona un componente para editar su referencia, valor y orientacion.\n\n"
            "Atajos utiles:\n"
            "  W  herramienta cable\n"
            "  R  rotar 90 grados\n"
            "  M  reflejar\n"
            "  Supr  borrar\n"
            "  Rueda  zoom\n"
            "  Boton central  desplazar"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_component(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setLabelAlignment(Qt.AlignRight)
        self.kind_label = QLabel()
        self.kind_label.setStyleSheet("font-weight:600;")
        self.reference_edit = QLineEdit()
        self.value_edit = QLineEdit()
        self.angle_combo = QComboBox()
        for angle in ANGLES:
            self.angle_combo.addItem(f"{angle}°", angle)
        self.mirror_check = QCheckBox("Reflejar horizontalmente")
        self.show_text_check = QCheckBox("Mostrar referencia y valor")
        self.pins_label = QLabel()
        self.pins_label.setStyleSheet("color:#64748b;")
        self.pins_label.setWordWrap(True)
        self.value_caption = QLabel("Valor")
        self.package_caption = QLabel("Encapsulado")
        self.package_label = QLabel()
        self.package_label.setStyleSheet("font-weight:600;")
        self.ic_caption = QLabel("")
        self.ic_button = QPushButton("Editar pines y encapsulado...")
        self.ic_button.clicked.connect(self._request_ic_edit)

        layout.addRow("Tipo", self.kind_label)
        layout.addRow("Referencia", self.reference_edit)
        layout.addRow(self.value_caption, self.value_edit)
        layout.addRow(self.package_caption, self.package_label)
        layout.addRow("Rotacion", self.angle_combo)
        layout.addRow("", self.mirror_check)
        layout.addRow("", self.show_text_check)
        layout.addRow("Pines", self.pins_label)
        layout.addRow(self.ic_caption, self.ic_button)

        self.reference_edit.editingFinished.connect(self._commit_component)
        self.value_edit.editingFinished.connect(self._commit_component)
        self.show_text_check.toggled.connect(self._commit_component)
        self.angle_combo.currentIndexChanged.connect(self._commit_orientation)
        self.mirror_check.toggled.connect(self._commit_orientation)
        return page

    def _build_text(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setFixedHeight(90)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 48)
        layout.addRow("Texto", self.text_edit)
        layout.addRow("Tamano", self.size_spin)
        self.text_edit.textChanged.connect(self._commit_text)
        self.size_spin.valueChanged.connect(self._commit_text)
        return page

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if sip.isdeleted(self.scene) or sip.isdeleted(self):
            return
        selection = self.scene.selectedItems()
        target = selection[0] if len(selection) == 1 else None
        self._target = target
        self._loading = True
        if isinstance(target, ComponentItem):
            is_ic = isinstance(target, ICItem)
            self.kind_label.setText(target.symbol.name)
            self.reference_edit.setText(target.reference)
            self.value_edit.setText(target.value)
            self.value_caption.setText("Nombre" if is_ic else "Valor")
            self.angle_combo.setCurrentIndex(ANGLES.index(target.angle % 360) if target.angle % 360 in ANGLES else 0)
            self.mirror_check.setChecked(target.mirrored)
            self.show_text_check.setChecked(target.show_text)
            self.pins_label.setText(", ".join(pin.name for pin in target.symbol.pins))
            self.package_label.setText(f"{target.package} · {target.pin_count} pines" if is_ic else "")
            for widget in (self.package_caption, self.package_label, self.ic_caption, self.ic_button):
                widget.setVisible(is_ic)
            self.stack.setCurrentIndex(1)
        elif isinstance(target, TextItem):
            if self.text_edit.toPlainText() != target.text:
                self.text_edit.setPlainText(target.text)
            self.size_spin.setValue(target.size)
            self._text_before = (target.text, target.size)
            self.stack.setCurrentIndex(2)
        else:
            self.stack.setCurrentIndex(0)
        self._loading = False

    def _request_ic_edit(self) -> None:
        if isinstance(self._target, ICItem):
            self.ic_edit_requested.emit(self._target)

    def _refresh_from_document(self) -> None:
        # tras deshacer/rehacer hay que releer el elemento, pero sin pisar lo
        # que el usuario esta escribiendo en ese momento
        if any(widget.hasFocus() for widget in (self.reference_edit, self.value_edit, self.text_edit)):
            return
        self.refresh()

    def focus_item(self, item) -> None:
        if isinstance(item, WireItem):
            return
        self.scene.clearSelection()
        item.setSelected(True)
        self.refresh()
        if isinstance(item, ComponentItem):
            self.reference_edit.setFocus()
            self.reference_edit.selectAll()
        elif isinstance(item, TextItem):
            self.text_edit.setFocus()
            self.text_edit.selectAll()

    # ------------------------------------------------------------------
    def _commit_component(self) -> None:
        target = self._target
        if self._loading or not isinstance(target, ComponentItem):
            return
        after = {
            "reference": self.reference_edit.text().strip(),
            "value": self.value_edit.text().strip(),
            "show_text": self.show_text_check.isChecked(),
        }
        before = {
            "reference": target.reference,
            "value": target.value,
            "show_text": target.show_text,
        }
        if before != after:
            self.scene.undo_stack.push(EditComponentCommand(target, before, after))

    def _commit_orientation(self) -> None:
        target = self._target
        if self._loading or not isinstance(target, ComponentItem):
            return
        angle = self.angle_combo.currentData()
        mirrored = self.mirror_check.isChecked()
        if (target.angle, target.mirrored) != (angle, mirrored):
            self.scene.undo_stack.push(
                OrientationCommand([(target, target.angle, target.mirrored, angle, mirrored)])
            )
            self.scene.notify_changed()

    def _commit_text(self) -> None:
        target = self._target
        if self._loading or not isinstance(target, TextItem):
            return
        target.set_text(self.text_edit.toPlainText(), self.size_spin.value())
        self._text_timer.start()

    def _flush_text(self) -> None:
        target = self._target
        if not isinstance(target, TextItem):
            return
        after = (self.text_edit.toPlainText(), self.size_spin.value())
        if self._text_before != after:
            self.scene.undo_stack.push(EditTextCommand(target, self._text_before, after))
            self._text_before = after
            self.scene.notify_changed()

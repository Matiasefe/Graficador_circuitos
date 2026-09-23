"""Ventana principal del editor de esquematicos."""

import os
from typing import Optional

from PyQt5.QtCore import QSize, QTimer, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QGraphicsItem,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
)

from . import document
from .example import EXAMPLE
from .palette import ComponentPalette
from .properties import PropertiesPanel
from .scene import PLACE, SELECT, TEXT, WIRE, SchematicScene
from .view import SchematicView

FILE_FILTER = "Esquematico CircuitDraw (*.json);;Todos los archivos (*)"

STYLESHEET = """
QMainWindow, QWidget { background: #f5f7fb; color: #1f2937; }
QDockWidget { titlebar-close-icon: none; }
QDockWidget::title {
    background: #e8edf6; padding: 7px 10px; font-weight: 600; border: none;
}
QToolBar { background: #ffffff; border-bottom: 1px solid #dde4f0; spacing: 4px; padding: 4px; }
QToolBar QToolButton {
    padding: 5px 10px; border-radius: 6px; color: #1f2937;
}
QToolBar QToolButton:hover { background: #e8edf6; }
QToolBar QToolButton:checked { background: #1f7ae0; color: #ffffff; }
QTreeWidget, QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: #ffffff; border: 1px solid #d7dfec; border-radius: 6px; padding: 3px;
}
QTreeWidget { padding: 2px; }
QTreeWidget::item { padding: 3px; }
QTreeWidget::item:selected { background: #dbeafe; color: #14213d; }
QStatusBar { background: #ffffff; border-top: 1px solid #dde4f0; }
QGraphicsView { border: 1px solid #dde4f0; background: #ffffff; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CircuitDraw")
        self.resize(1360, 860)
        self.setStyleSheet(STYLESHEET)

        self.scene = SchematicScene(self)
        self.view = SchematicView(self.scene, self)
        self.setCentralWidget(self.view)

        self.path: Optional[str] = None
        self._dirty = False
        self._fitted = False

        self.palette_panel = ComponentPalette()
        self.palette_panel.symbol_chosen.connect(self._start_placing)
        self.palette_panel.ic_requested.connect(self.new_integrated_circuit)
        left = QDockWidget("Componentes", self)
        left.setObjectName("dock_componentes")
        left.setWidget(self.palette_panel)
        left.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)

        self.properties_panel = PropertiesPanel(self.scene, self)
        self.properties_panel.ic_edit_requested.connect(self.edit_integrated_circuit)
        right = QDockWidget("Propiedades", self)
        right.setObjectName("dock_propiedades")
        right.setWidget(self.properties_panel)
        right.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, right)
        self.resizeDocks([left, right], [270, 290], Qt.Horizontal)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        self.hint_label = QLabel()
        self.statusBar().addPermanentWidget(self.hint_label)
        self.scene.status_message.connect(self.statusBar().showMessage)
        self.scene.document_changed.connect(self._mark_dirty)
        self.scene.tool_changed.connect(self._sync_tool_actions)
        self.scene.edit_requested.connect(self._on_edit_requested)
        self.scene.undo_stack.indexChanged.connect(self._on_undo_index_changed)

        self.load_example()
        self.scene.set_tool(SELECT)
        self._update_title()

    # ------------------------------------------------------------------
    # acciones
    # ------------------------------------------------------------------
    def _action(self, text: str, slot, shortcut: str = "", checkable: bool = False,
               local: bool = False, tip: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.setStatusTip(tip or text)
        if checkable:
            action.toggled.connect(slot)
        else:
            action.triggered.connect(slot)
        if local:
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.view.addAction(action)
        else:
            self.addAction(action)
        return action

    def _build_actions(self) -> None:
        self.action_new = self._action("Nuevo", self.new_document, "Ctrl+N")
        self.action_open = self._action("Abrir...", self.open_document, "Ctrl+O")
        self.action_save = self._action("Guardar", self.save_document, "Ctrl+S")
        self.action_save_as = self._action("Guardar como...", self.save_document_as, "Ctrl+Shift+S")
        self.action_example = self._action("Cargar ejemplo", self.load_example_action)
        self.action_png = self._action("Exportar PNG...", self.export_png, "Ctrl+E")
        self.action_svg = self._action("Exportar SVG...", self.export_svg)
        self.action_svg.setEnabled(document.svg_available())
        self.action_netlist = self._action("Ver netlist...", self.show_netlist, "Ctrl+L")
        self.action_quit = self._action("Salir", self.close, "Ctrl+Q")

        self.action_undo = self.scene.undo_stack.createUndoAction(self, "Deshacer")
        self.action_undo.setShortcut(QKeySequence.Undo)
        self.action_redo = self.scene.undo_stack.createRedoAction(self, "Rehacer")
        self.action_redo.setShortcut(QKeySequence.Redo)
        self.addAction(self.action_undo)
        self.addAction(self.action_redo)

        self.action_delete = self._action("Eliminar", self.scene.delete_selection, "Del", local=True)
        self.action_duplicate = self._action("Duplicar", self.scene.duplicate_selection, "Ctrl+D")
        self.action_select_all = self._action("Seleccionar todo", self.select_all, "Ctrl+A")
        self.action_rotate = self._action("Rotar 90", lambda: self.scene.rotate_selection(90), "R", local=True)
        self.action_rotate_ccw = self._action(
            "Rotar -90", lambda: self.scene.rotate_selection(-90), "Shift+R", local=True
        )
        self.action_mirror = self._action("Reflejar", self.scene.mirror_selection, "M", local=True)

        def tool_slot(tool):
            return lambda checked: self.scene.set_tool(tool) if checked else None

        self.action_tool_select = self._action(
            "Seleccionar", tool_slot(SELECT), "S", checkable=True, local=True
        )
        self.action_tool_wire = self._action("Cable", tool_slot(WIRE), "W", checkable=True, local=True)
        self.action_tool_text = self._action("Nota", tool_slot(TEXT), "T", checkable=True, local=True)
        self.tool_group = QActionGroup(self)
        for action in (self.action_tool_select, self.action_tool_wire, self.action_tool_text):
            self.tool_group.addAction(action)
        self.action_tool_select.setChecked(True)

        self.action_zoom_in = self._action("Acercar", lambda: self.view.zoom_by(1.2), "Ctrl++")
        self.action_zoom_out = self._action("Alejar", lambda: self.view.zoom_by(1 / 1.2), "Ctrl+-")
        self.action_zoom_reset = self._action("Zoom 100%", self.view.reset_zoom, "Ctrl+0")
        self.action_fit = self._action("Ajustar al contenido", self.view.fit_content, "Ctrl+F")
        self.action_grid = self._action("Mostrar rejilla", self.toggle_grid, "G", checkable=True, local=True)
        self.action_grid.setChecked(True)

        self.action_shortcuts = self._action("Atajos de teclado", self.show_shortcuts, "F1")
        self.action_about = self._action("Acerca de CircuitDraw", self.show_about)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Archivo")
        for action in (self.action_new, self.action_open, self.action_save, self.action_save_as):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.action_example)
        file_menu.addSeparator()
        for action in (self.action_png, self.action_svg, self.action_netlist):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        edit_menu = bar.addMenu("&Editar")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        for action in (self.action_duplicate, self.action_delete, self.action_select_all):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        for action in (self.action_rotate, self.action_rotate_ccw, self.action_mirror):
            edit_menu.addAction(action)

        tools_menu = bar.addMenu("&Herramientas")
        for action in (self.action_tool_select, self.action_tool_wire, self.action_tool_text):
            tools_menu.addAction(action)

        view_menu = bar.addMenu("&Ver")
        for action in (self.action_zoom_in, self.action_zoom_out, self.action_zoom_reset,
                       self.action_fit, self.action_grid):
            view_menu.addAction(action)

        help_menu = bar.addMenu("A&yuda")
        help_menu.addAction(self.action_shortcuts)
        help_menu.addAction(self.action_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("toolbar_principal")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addAction(self.action_new)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addSeparator()
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_redo)
        toolbar.addSeparator()
        toolbar.addAction(self.action_tool_select)
        toolbar.addAction(self.action_tool_wire)
        toolbar.addAction(self.action_tool_text)
        toolbar.addSeparator()
        toolbar.addAction(self.action_rotate)
        toolbar.addAction(self.action_mirror)
        toolbar.addAction(self.action_delete)
        toolbar.addSeparator()
        toolbar.addAction(self.action_fit)
        toolbar.addAction(self.action_grid)
        toolbar.addSeparator()
        toolbar.addAction(self.action_netlist)

    # ------------------------------------------------------------------
    # estado
    # ------------------------------------------------------------------
    def _start_placing(self, symbol) -> None:
        self.scene.set_tool(PLACE, symbol)
        self.view.setFocus()

    def new_integrated_circuit(self) -> None:
        from .ic import ICItem, ic_palette_symbol
        from .icdialog import ICDialog

        dialog = ICDialog(self, reference=self.scene.next_reference(ic_palette_symbol()))
        if dialog.exec_() != QDialog.Accepted:
            self.palette_panel.clear_selection()
            return
        config = dialog.config()

        def factory():
            return ICItem(config["package"], config["pin_names"], config["value"], config["reference"])

        self.scene.set_tool(PLACE, factory=factory)
        self.view.setFocus()

    def edit_integrated_circuit(self, item) -> None:
        from .commands import ConfigureICCommand
        from .icdialog import ICDialog

        dialog = ICDialog(
            self,
            name=item.value,
            reference=item.reference,
            package=item.package,
            pin_names=list(item.pin_names),
            title="Editar circuito integrado",
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        after = dialog.config()
        before = {
            "value": item.value,
            "reference": item.reference,
            "package": item.package,
            "pin_names": list(item.pin_names),
        }
        if before != after:
            self.scene.undo_stack.push(ConfigureICCommand(item, before, after))

    def _on_edit_requested(self, item) -> None:
        from .ic import ICItem

        if isinstance(item, ICItem):
            self.edit_integrated_circuit(item)

    def _sync_tool_actions(self, tool: str) -> None:
        self.action_tool_select.setChecked(tool == SELECT)
        self.action_tool_wire.setChecked(tool == WIRE)
        self.action_tool_text.setChecked(tool == TEXT)
        if tool != PLACE:
            self.palette_panel.clear_selection()

    def _on_undo_index_changed(self, _index: int) -> None:
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = os.path.basename(self.path) if self.path else "sin titulo"
        marker = "*" if self._dirty else ""
        self.setWindowTitle(f"CircuitDraw — {name}{marker}")
        components = len(self.scene.components())
        wires = len(self.scene.wires())
        self.hint_label.setText(f"{components} componentes · {wires} cables")

    def select_all(self) -> None:
        for item in self.scene.items():
            if item.flags() & QGraphicsItem.ItemIsSelectable:
                item.setSelected(True)

    def toggle_grid(self, enabled: bool) -> None:
        self.scene.show_grid = enabled
        self.scene.update()

    # ------------------------------------------------------------------
    # archivos
    # ------------------------------------------------------------------
    def _confirm_discard(self) -> bool:
        if not self._dirty or not self.scene.items():
            return True
        answer = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "El esquematico tiene cambios sin guardar. Deseas guardarlos?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Save:
            return self.save_document()
        return answer == QMessageBox.Discard

    def new_document(self) -> None:
        if not self._confirm_discard():
            return
        self.scene.clear_document()
        self.path = None
        self._dirty = False
        self.view.reset_zoom()
        self.view.centerOn(0, 0)
        self._update_title()

    def load_path(self, path: str) -> None:
        document.open_json(self.scene, path)
        self.path = path
        self._dirty = False
        self.view.fit_content()
        self._update_title()

    def open_document(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir esquematico", "", FILE_FILTER)
        if not path:
            return
        try:
            document.open_json(self.scene, path)
        except Exception as error:  # noqa: BLE001 - se muestra al usuario
            QMessageBox.critical(self, "No se pudo abrir", str(error))
            return
        self.path = path
        self._dirty = False
        self.view.fit_content()
        self._update_title()

    def save_document(self) -> bool:
        if not self.path:
            return self.save_document_as()
        try:
            document.save_json(self.scene, self.path)
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return False
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Guardado en {self.path}", 4000)
        return True

    def save_document_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar esquematico", "circuito.json", FILE_FILTER
        )
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        self.path = path
        return self.save_document()

    def export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar PNG", "circuito.png", "Imagen PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            document.export_png(self.scene, path)
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo exportar", str(error))
            return
        self.statusBar().showMessage(f"Imagen exportada a {path}", 4000)

    def export_svg(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar SVG", "circuito.svg", "Vector SVG (*.svg)")
        if not path:
            return
        if not path.lower().endswith(".svg"):
            path += ".svg"
        try:
            document.export_svg(self.scene, path)
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "No se pudo exportar", str(error))
            return
        self.statusBar().showMessage(f"Vector exportado a {path}", 4000)

    def load_example(self) -> None:
        document.dict_into_scene(self.scene, EXAMPLE)
        self._dirty = False
        self.view.fit_content()
        self._update_title()

    def load_example_action(self) -> None:
        if not self._confirm_discard():
            return
        self.path = None
        self.load_example()

    # ------------------------------------------------------------------
    # dialogos
    # ------------------------------------------------------------------
    def show_netlist(self) -> None:
        text = document.netlist_text(self.scene)
        dialog = QDialog(self)
        dialog.setWindowTitle("Netlist del esquematico")
        dialog.resize(560, 460)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        editor.setStyleSheet("font-family: 'DejaVu Sans Mono', monospace;")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Save).setText("Guardar como...")
        buttons.rejected.connect(dialog.close)
        buttons.accepted.connect(lambda: self._save_netlist(dialog))
        layout.addWidget(buttons)
        dialog.exec_()

    def _save_netlist(self, parent) -> None:
        path, _ = QFileDialog.getSaveFileName(parent, "Guardar netlist", "circuito.net", "Netlist (*.net *.txt)")
        if not path:
            return
        document.save_netlist(self.scene, path)
        self.statusBar().showMessage(f"Netlist guardada en {path}", 4000)

    def show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Atajos de teclado",
            "<b>Herramientas</b><br>"
            "S seleccionar · W cable · T nota<br><br>"
            "<b>Edicion</b><br>"
            "R rotar · Shift+R rotar inverso · M reflejar<br>"
            "Supr eliminar · Ctrl+D duplicar · Ctrl+Z/Ctrl+Y deshacer/rehacer<br><br>"
            "<b>Vista</b><br>"
            "Rueda zoom · boton central desplazar · Ctrl+F ajustar · G rejilla<br><br>"
            "<b>Cables</b><br>"
            "Clic para fijar un codo · Shift invierte el sentido del codo<br>"
            "Doble clic, Enter o clic derecho para terminar · Esc cancela",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca de CircuitDraw",
            "<h3>CircuitDraw</h3>"
            "<p>Editor de esquematicos electronicos escrito en Python con PyQt5.</p>"
            "<p>Biblioteca de simbolos, cableado ortogonal con enganche a pines, "
            "deshacer/rehacer, guardado en JSON, exportacion a PNG/SVG y generacion "
            "de netlist.</p>",
        )

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # el encuadre inicial necesita que el lienzo ya tenga su tamano real
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self.view.fit_content)

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

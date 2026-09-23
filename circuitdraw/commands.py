"""Comandos de deshacer/rehacer sobre la escena."""

from typing import Dict, Iterable, List, Sequence, Tuple

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QUndoCommand

from .items import ComponentItem, TextItem, WireItem


class AddItemsCommand(QUndoCommand):
    def __init__(self, scene, items: Sequence, text: str = "Agregar"):
        super().__init__(text)
        self.scene = scene
        self.items = list(items)

    def redo(self) -> None:
        for item in self.items:
            self.scene.addItem(item)
            if isinstance(item, WireItem):
                for which, anchor in ((0, item.start_anchor), (-1, item.end_anchor)):
                    if anchor is not None and item not in anchor[0].wires:
                        anchor[0].wires.append(item)
        self.scene.notify_changed()

    def undo(self) -> None:
        for item in self.items:
            if isinstance(item, WireItem):
                for anchor in item.anchors():
                    if anchor is not None and item in anchor[0].wires:
                        anchor[0].wires.remove(item)
            self.scene.removeItem(item)
        self.scene.notify_changed()


class DeleteItemsCommand(QUndoCommand):
    def __init__(self, scene, items: Iterable):
        super().__init__("Eliminar")
        self.scene = scene
        self.items = list(items)
        self._detached: List[Tuple[WireItem, int, Tuple[ComponentItem, int]]] = []

    def redo(self) -> None:
        self._detached.clear()
        deleted = set(self.items)
        for component in [item for item in self.items if isinstance(item, ComponentItem)]:
            for wire in list(component.wires):
                if wire in deleted:
                    continue
                for which in wire.detach_component(component):
                    pin = 0 if which == 0 else len(component.symbol.pins) - 1
                    self._detached.append((wire, which, (component, pin)))
        for item in self.items:
            self.scene.removeItem(item)
        self.scene.notify_changed()

    def undo(self) -> None:
        for item in self.items:
            self.scene.addItem(item)
        for wire, which, anchor in self._detached:
            wire.set_anchor(which, anchor)
        for item in self.items:
            if isinstance(item, ComponentItem):
                item.refresh_wires()
        self.scene.notify_changed()


def _copy_config(data: Dict) -> Dict:
    copied = dict(data)
    if "pin_names" in copied:
        copied["pin_names"] = list(copied["pin_names"])
    return copied


def _notify(items: Iterable) -> None:
    for item in items:
        scene = item.scene()
        if scene is not None:
            scene.notify_changed()
            return


class MoveItemsCommand(QUndoCommand):
    def __init__(self, moves: Sequence[Tuple[object, QPointF, QPointF]]):
        super().__init__("Mover")
        self.moves = [(item, QPointF(old), QPointF(new)) for item, old, new in moves]

    def _apply(self, use_new: bool) -> None:
        for item, old, new in self.moves:
            item.setPos(new if use_new else old)
            if isinstance(item, ComponentItem):
                item.refresh_wires()
        _notify(item for item, _, _ in self.moves)

    def redo(self) -> None:
        self._apply(True)

    def undo(self) -> None:
        self._apply(False)


class OrientationCommand(QUndoCommand):
    def __init__(self, changes: Sequence[Tuple[ComponentItem, int, bool, int, bool]], text: str = "Orientar"):
        super().__init__(text)
        self.changes = list(changes)

    def redo(self) -> None:
        for item, _, _, angle, mirrored in self.changes:
            item.set_orientation(angle, mirrored)
        _notify(item for item, *_ in self.changes)

    def undo(self) -> None:
        for item, angle, mirrored, _, _ in self.changes:
            item.set_orientation(angle, mirrored)
        _notify(item for item, *_ in self.changes)


class EditComponentCommand(QUndoCommand):
    def __init__(self, component: ComponentItem, before: Dict, after: Dict):
        super().__init__("Editar componente")
        self.component = component
        self.before = dict(before)
        self.after = dict(after)

    def _apply(self, data: Dict) -> None:
        self.component.prepareGeometryChange()
        self.component.reference = data.get("reference", self.component.reference)
        self.component.value = data.get("value", self.component.value)
        self.component.show_text = data.get("show_text", self.component.show_text)
        self.component.update()
        scene = self.component.scene()
        if scene is not None:
            scene.notify_changed()

    def redo(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


class ConfigureICCommand(QUndoCommand):
    """Cambia encapsulado, nombre y pines de un circuito integrado."""

    def __init__(self, item, before: Dict, after: Dict):
        super().__init__("Configurar integrado")
        self.item = item
        self.before = _copy_config(before)
        self.after = _copy_config(after)
        self._detached: List[Tuple] = []

    def _apply(self, data: Dict) -> List[Tuple]:
        self.item.reference = data.get("reference", self.item.reference)
        return self.item.configure(data["package"], data["pin_names"], data.get("value"))

    def redo(self) -> None:
        self._detached = self._apply(self.after)
        _notify([self.item])

    def undo(self) -> None:
        self._apply(self.before)
        for wire, which, anchor in self._detached:
            wire.set_anchor(which, anchor)
        self.item.refresh_wires()
        _notify([self.item])


class EditTextCommand(QUndoCommand):
    def __init__(self, item: TextItem, before: Tuple[str, int], after: Tuple[str, int]):
        super().__init__("Editar nota")
        self.item = item
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.item.set_text(*self.after)
        _notify([self.item])

    def undo(self) -> None:
        self.item.set_text(*self.before)
        _notify([self.item])

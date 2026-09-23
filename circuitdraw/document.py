"""Guardado, apertura, exportacion y extraccion de la lista de nodos (netlist)."""

import json
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter

from .items import ComponentItem, TextItem, WireItem, component_from_dict

FORMAT = "circuitdraw"
VERSION = 1

POWER_KEYS = {"ground": "GND", "supply": "VCC"}
LABEL_KEYS = ("ground", "supply", "terminal")


# ----------------------------------------------------------------------
# serializacion
# ----------------------------------------------------------------------
def scene_to_dict(scene) -> dict:
    # se ordena todo para que el archivo sea estable entre guardados
    components = sorted(
        scene.components(),
        key=lambda item: (item.x(), item.y(), item.symbol.key, item.reference),
    )
    wires = sorted(scene.wires(), key=lambda item: [(p.x(), p.y()) for p in item.points])
    texts = sorted(scene.texts(), key=lambda item: (item.x(), item.y(), item.text))
    ids = {component: index for index, component in enumerate(components)}
    return {
        "format": FORMAT,
        "version": VERSION,
        "components": [component.to_dict(ids[component]) for component in components],
        "wires": [wire.to_dict(ids) for wire in wires],
        "texts": [text.to_dict() for text in texts],
    }


def dict_into_scene(scene, data: dict) -> None:
    if data.get("format") != FORMAT:
        raise ValueError("El archivo no es un esquematico de CircuitDraw.")
    scene.clear_document()
    components: Dict[int, ComponentItem] = {}
    for raw in data.get("components", []):
        item = component_from_dict(raw)
        scene.addItem(item)
        components[int(raw.get("id", len(components)))] = item
    for raw in data.get("wires", []):
        wire = WireItem.from_dict(raw, components)
        if len(wire.points) >= 2:
            scene.addItem(wire)
    for raw in data.get("texts", []):
        scene.addItem(TextItem.from_dict(raw))
    scene.undo_stack.clear()
    scene.notify_changed()


def save_json(scene, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(scene_to_dict(scene), handle, indent=2, ensure_ascii=False)


def open_json(scene, path: str) -> None:
    with open(path, encoding="utf-8") as handle:
        dict_into_scene(scene, json.load(handle))


# ----------------------------------------------------------------------
# exportacion de imagenes
# ----------------------------------------------------------------------
def _render_rect(scene) -> QRectF:
    rect = scene.content_rect()
    if rect.isNull() or rect.isEmpty():
        rect = QRectF(-100, -100, 200, 200)
    return rect.adjusted(-30, -30, 30, 30)


def export_png(scene, path: str, scale: float = 2.0) -> None:
    rect = _render_rect(scene)
    image = QImage(int(rect.width() * scale), int(rect.height() * scale), QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    with _clean_render(scene):
        scene.render(painter, QRectF(image.rect()), rect, Qt.KeepAspectRatio)
    painter.end()
    if not image.save(path):
        raise IOError(f"No se pudo guardar la imagen en {path}")


def svg_available() -> bool:
    try:
        from PyQt5.QtSvg import QSvgGenerator  # noqa: F401
    except ImportError:
        return False
    return True


def export_svg(scene, path: str) -> None:
    try:
        from PyQt5.QtSvg import QSvgGenerator
    except ImportError as error:
        raise RuntimeError(
            "La exportacion SVG necesita el modulo QtSvg (instala PyQt5 completo "
            "o el paquete python3-pyqt5.qtsvg)."
        ) from error

    rect = _render_rect(scene)
    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(rect.size().toSize())
    generator.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
    generator.setTitle("Esquematico CircuitDraw")
    painter = QPainter(generator)
    with _clean_render(scene):
        scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect, Qt.KeepAspectRatio)
    painter.end()


class _clean_render:
    """Oculta rejilla y seleccion mientras se exporta."""

    def __init__(self, scene):
        self.scene = scene
        self.grid = scene.show_grid
        self.selection = list(scene.selectedItems())

    def __enter__(self):
        self.scene.show_grid = False
        self.scene.export_mode = True
        self.scene.clearSelection()
        return self

    def __exit__(self, *exc):
        self.scene.show_grid = self.grid
        self.scene.export_mode = False
        for item in self.selection:
            if item.scene() is self.scene:
                item.setSelected(True)
        self.scene.update()
        return False


# ----------------------------------------------------------------------
# netlist
# ----------------------------------------------------------------------
class _Union:
    def __init__(self):
        self.parent: Dict[object, object] = {}

    def find(self, key):
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a, b) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


def _key(point: QPointF) -> Tuple[float, float]:
    return (round(point.x(), 1), round(point.y(), 1))


def _on_segment(point: QPointF, start: QPointF, end: QPointF, tolerance: float = 0.6) -> bool:
    min_x, max_x = sorted((start.x(), end.x()))
    min_y, max_y = sorted((start.y(), end.y()))
    inside = min_x - tolerance <= point.x() <= max_x + tolerance and min_y - tolerance <= point.y() <= max_y + tolerance
    axis_aligned = abs(start.x() - end.x()) < tolerance or abs(start.y() - end.y()) < tolerance
    return inside and axis_aligned


def build_nets(scene) -> Tuple[Dict[str, List[str]], List[str]]:
    """Agrupa los pines en nodos electricos.

    Devuelve un diccionario nombre_de_nodo -> lista de "REF.pin" y la lista de
    pines que quedaron sin conectar.
    """
    union = _Union()
    components = scene.components()
    wires = scene.wires()

    pin_points: List[Tuple[ComponentItem, int, QPointF]] = []
    for component in components:
        for index in range(len(component.symbol.pins)):
            position = component.pin_pos(index)
            pin_points.append((component, index, position))
            union.union(("pt", _key(position)), ("pin", id(component), index))

    # los simbolos de tierra, alimentacion y los terminales con el mismo
    # nombre representan siempre el mismo nodo, aunque no haya cable entre ellos
    named: Dict[str, List[object]] = {}
    for component in components:
        key = component.symbol.key
        if key == "ground":
            named.setdefault("GND", []).append(("pin", id(component), 0))
        elif key in ("supply", "terminal") and component.value:
            named.setdefault(component.value, []).append(("pin", id(component), 0))
    for nodes in named.values():
        for node in nodes[1:]:
            union.union(nodes[0], node)

    for wire in wires:
        keys = [("pt", _key(point)) for point in wire.points]
        for other in keys[1:]:
            union.union(keys[0], other)
        for anchor, which in ((wire.start_anchor, 0), (wire.end_anchor, -1)):
            if anchor is not None:
                union.union(keys[0], ("pin", id(anchor[0]), anchor[1]))

    connectable = [("pt", _key(point)) for wire in wires for point in wire.points]
    connectable += [("pt", _key(position)) for _, _, position in pin_points]
    for wire in wires:
        for start, end in zip(wire.points, wire.points[1:]):
            for node in connectable:
                point = QPointF(node[1][0], node[1][1])
                if _on_segment(point, start, end):
                    union.union(("pt", _key(wire.points[0])), node)

    groups: Dict[object, List[Tuple[ComponentItem, int]]] = {}
    for component, index, _ in pin_points:
        groups.setdefault(union.find(("pin", id(component), index)), []).append((component, index))

    touched = set()
    for wire in wires:
        for point in wire.points:
            touched.add(union.find(("pt", _key(point))))

    nets: Dict[str, List[str]] = {}
    unconnected: List[str] = []
    counter = 1
    for root, pins in groups.items():
        # los simbolos de tierra, alimentacion y terminal dan nombre al nodo,
        # no se listan como conexiones
        labels = [
            f"{_label(component)}.{component.pin_key(index)}"
            for component, index in pins
            if component.symbol.key not in LABEL_KEYS
        ]
        if not labels:
            continue
        if root not in touched and len(pins) < 2:
            unconnected.extend(labels)
            continue
        name = _net_name(pins)
        if name is None:
            name = f"N{counter}"
            counter += 1
        while name in nets:
            name = f"{name}_"
        nets[name] = sorted(labels)
    return nets, sorted(unconnected)


def _label(component: ComponentItem) -> str:
    return component.reference or component.symbol.prefix or component.symbol.key


def _net_name(pins: List[Tuple[ComponentItem, int]]) -> Optional[str]:
    for component, _ in pins:
        if component.symbol.key == "ground":
            return "GND"
    for component, _ in pins:
        if component.symbol.key in ("supply", "terminal") and component.value:  # nombre de nodo
            return component.value.replace(" ", "_")
        if component.symbol.key == "supply":
            return POWER_KEYS["supply"]
    return None


def netlist_text(scene) -> str:
    nets, unconnected = build_nets(scene)
    pin_to_net: Dict[Tuple[int, int], str] = {}
    for name, labels in nets.items():
        for label in labels:
            pin_to_net[label] = name

    lines = [
        "* Netlist generada por CircuitDraw",
        f"* {len(scene.components())} componentes, {len(nets)} nodos",
        "",
    ]
    for component in sorted(scene.components(), key=lambda item: _label(item)):
        if component.symbol.key in LABEL_KEYS:
            continue
        label = _label(component)
        nodes = [
            pin_to_net.get(f"{label}.{component.pin_key(index)}", "?")
            for index in range(len(component.symbol.pins))
        ]
        value = component.value or component.symbol.name
        package = getattr(component, "package", "")
        suffix = f"  [{package}]" if package else ""
        lines.append(f"{label:<6} {' '.join(nodes):<22} {value}{suffix}")
    lines.append("")
    lines.append("* Nodos")
    for name in sorted(nets):
        lines.append(f"* {name}: {', '.join(nets[name])}")
    if unconnected:
        lines.append("")
        lines.append("* Pines sin conectar: " + ", ".join(unconnected))
    return "\n".join(lines) + "\n"


def save_netlist(scene, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(netlist_text(scene))

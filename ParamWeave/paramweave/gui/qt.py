"""Qt compatibility helpers using FreeCAD's own PySide wrapper."""

from PySide import QtCore, QtGui, QtWidgets


def enum(container, scoped_name: str, legacy_name: str):
    """Get a Qt5/Qt6 enum value without scattering version checks."""
    scoped = getattr(container, scoped_name, None)
    if scoped is not None:
        return scoped
    return getattr(container, legacy_name)


def item_flag(name: str):
    flags = getattr(QtWidgets.QGraphicsItem, "GraphicsItemFlag", None)
    if flags is not None:
        return getattr(flags, name)
    return getattr(QtWidgets.QGraphicsItem, name)


def dock_area(name: str):
    areas = getattr(QtCore.Qt, "DockWidgetArea", None)
    if areas is not None:
        return getattr(areas, name)
    return getattr(QtCore.Qt, name)


def orientation(name: str):
    values = getattr(QtCore.Qt, "Orientation", None)
    if values is not None:
        return getattr(values, name)
    return getattr(QtCore.Qt, name)


def mouse_button(name: str):
    values = getattr(QtCore.Qt, "MouseButton", None)
    if values is not None:
        return getattr(values, name)
    return getattr(QtCore.Qt, name)


def pen_style(name: str):
    values = getattr(QtCore.Qt, "PenStyle", None)
    if values is not None:
        return getattr(values, name)
    return getattr(QtCore.Qt, name)


def key(name: str):
    values = getattr(QtCore.Qt, "Key", None)
    if values is not None:
        return getattr(values, name)
    return getattr(QtCore.Qt, name)


def qenum(container, enum_name: str, member: str):
    """Return ``container.enum_name.member`` (Qt6) or ``container.member`` (Qt5)."""
    scoped = getattr(container, enum_name, None)
    if scoped is not None and hasattr(scoped, member):
        return getattr(scoped, member)
    return getattr(container, member)

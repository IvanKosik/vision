from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide2.QtCore import Qt, QObject, Signal, QSize, QPointF, QRectF, QMarginsF
from PySide2.QtGui import QPainter, QPixmap
from PySide2.QtWidgets import QWidget, QStyledItemDelegate, QStyle

from bsmu.vision.widgets.images import icons_rc  # noqa: F401

if TYPE_CHECKING:
    from PySide2.QtCore import QAbstractItemModel, QModelIndex, QRect
    from PySide2.QtGui import QPaintEvent, QMouseEvent, QPalette
    from PySide2.QtWidgets import QStyleOptionViewItem


class Visibility(QObject):
    class EditMode(Enum):
        EDITABLE = auto()
        READ_ONLY = auto()

    def __init__(self, visible: bool = True, opacity: float = 1):
        super().__init__()

        self._visible = visible
        self._opacity = opacity

        self._checked_icon = QPixmap(':/icons/eye-outlined.svg')
        self._unchecked_icon = QPixmap(':/icons/eye-outlined-crossed-out.svg')

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def opacity(self) -> float:
        return self._opacity

    def paint(self, painter: QPainter, rect: QRect, palette: QPalette, mode: EditMode):
        painter.save()

        icon = self._checked_icon if self._visible else self._unchecked_icon
        icon_rect_f = QRectF(rect.x(), rect.y(), rect.width() / 3, rect.height())
        margin_factor = 12
        margin = min(icon_rect_f.width() / margin_factor, icon_rect_f.height() / margin_factor)
        # Add margins around icon
        icon_rect_f -= QMarginsF(margin, margin, margin, margin)
        icon = icon.scaled(
            int(icon_rect_f.width()), int(icon_rect_f.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        draw_top_left_y = icon_rect_f.y() + (icon_rect_f.height() - icon.height()) / 2
        painter.drawPixmap(QPointF(icon_rect_f.x(), draw_top_left_y), icon)

        painter.restore()

    def sizeHint(self) -> QSize:
        return QSize(32, 32)


class VisibilityEditor(QWidget):
    editing_finished = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self._visibility = None

        #% self.setMouseTracking(True)
        self.setAutoFillBackground(True)

    def sizeHint(self) -> QSize:
        return self._visibility.sizeHint()

    @property
    def visibility(self) -> Visibility:
        return self._visibility

    @visibility.setter
    def visibility(self, value: Visibility):
        self._visibility = value

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        self._visibility.paint(painter, self.rect(), self.palette(), Visibility.EditMode.EDITABLE)

    def mouseMoveEvent(self, event: QMouseEvent):
        ...

    def mouseReleaseEvent(self, event: QMouseEvent):
        print('VisibilityEditor.mouseReleaseEvent')
        self.editing_finished.emit()
        super().mouseReleaseEvent(event)

    def _opacity_at_pos(self, x: int) -> float:
        ...


class VisibilityDelegate(QStyledItemDelegate):
    def __init__(self, parent: QObject = None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if isinstance(index.data(), Visibility):
            visibility = index.data()

            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())

            visibility.paint(painter, option.rect, option.palette, Visibility.EditMode.READ_ONLY)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if isinstance(index.data(), Visibility):
            visibility = index.data()
            return visibility.sizeHint()
        return super().sizeHint(option, index)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        print('createEditor')
        if isinstance(index.data(), Visibility):
            print('createEditor for Visibility')
            visibility_editor = VisibilityEditor(parent)
            visibility_editor.editing_finished.connect(self._commit_and_close_editor)
            return visibility_editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        if isinstance(index.data(), Visibility):
            visibility = index.data()
            editor.visibility = visibility
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex):
        if isinstance(index.data(), Visibility):
            model.setData(index, editor.visibility)
        else:
            super().setModelData(editor, model, index)

    def _commit_and_close_editor(self):
        ...

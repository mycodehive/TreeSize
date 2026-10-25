from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from .reports import format_bytes


class DiskTreeModel(QAbstractItemModel):
    HEADERS = ["이름", "파일 크기", "디스크 할당", "상위 폴더 비율", "파일 수", "폴더 수", "수정일"]

    def __init__(self, root=None, parent=None):
        super().__init__(parent)
        self.root = root
        self.column = 1
        self.descending = True
        self._orders = {}
        self._positions = {}

    def ordered(self, node):
        key = id(node)
        if key not in self._orders:
            def sort_key(child):
                values = [child.name.casefold(), child.size, child.allocated,
                          child.size, child.files, child.folders, child.modified]
                return values[self.column]
            children = sorted(node.children, key=sort_key, reverse=self.descending)
            self._orders[key] = children
            self._positions.update((id(child), row) for row, child in enumerate(children))
        return self._orders[key]

    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column < 0 or column >= len(self.HEADERS):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(0, column, self.root) if self.root and row == 0 else QModelIndex()
        if parent.column() != 0:
            return QModelIndex()
        children = self.ordered(parent.internalPointer())
        return self.createIndex(row, column, children[row]) if row < len(children) else QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer().parent
        if node is None:
            return QModelIndex()
        if node is self.root:
            return self.createIndex(0, 0, node)
        self.ordered(node.parent)
        return self.createIndex(self._positions[id(node)], 0, node)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return len(parent.internalPointer().children) if parent.column() == 0 else 0
        return 1 if self.root else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node, col = index.internalPointer(), index.column()
        if role == Qt.ItemDataRole.UserRole:
            return node
        if role == Qt.ItemDataRole.ToolTipRole:
            return node.path + ("\n" + node.error if node.error else "") + ("\n건너뛴 항목" if node.skipped else "")
        if role == Qt.ItemDataRole.ForegroundRole and (node.error or node.skipped):
            return QColor("#ab7426")
        if role == Qt.ItemDataRole.TextAlignmentRole and col > 0:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        if role == Qt.ItemDataRole.DisplayRole:
            ratio = node.size / node.parent.size if node.parent and node.parent.size else (1 if node.size else 0)
            modified = datetime.fromtimestamp(node.modified).strftime("%Y.%m.%d %H:%M") if node.modified > 0 else "—"
            return [("▸  " if node.is_dir else "    ") + node.name,
                    format_bytes(node.size), format_bytes(node.allocated), f"{ratio:.1%}",
                    f"{node.files:,}", f"{node.folders:,}" if node.is_dir else "—", modified][col]
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        old_indexes = self.persistentIndexList()
        nodes = [(index.internalPointer(), index.column()) for index in old_indexes]
        self.column, self.descending = column, order == Qt.SortOrder.DescendingOrder
        self._orders.clear()
        self._positions.clear()
        new_indexes = [self.index_for_node(node, col) for node, col in nodes]
        self.changePersistentIndexList(old_indexes, new_indexes)
        self.layoutChanged.emit()

    def index_for_node(self, node, column=0):
        if node is self.root:
            return self.createIndex(0, column, node)
        if node.parent:
            self.ordered(node.parent)
            return self.createIndex(self._positions[id(node)], column, node)
        return QModelIndex()


class UsageDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        node = index.data(Qt.ItemDataRole.UserRole)
        if index.column() == 3 and node and node.size:
            total = node.parent.size if node.parent else node.size
            rect = option.rect.adjusted(6, 7, -6, -7)
            rect.setWidth(int(rect.width() * min(1, node.size / max(1, total))))
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#b8d5fc") if not option.state & QStyle.StateFlag.State_Selected else QColor("#a8c9fa"))
            painter.drawRoundedRect(rect, 3, 3)
            painter.restore()
        super().paint(painter, option, index)

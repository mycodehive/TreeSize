from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import QWidget, QToolTip

from .reports import format_bytes

COLORS = ["#4479db", "#35a493", "#8a66cd", "#e5a345", "#539cc5", "#d57388", "#687ed1", "#72a559"]


def partition(items, x, y, width, height):
    """Balanced area-preserving binary treemap; no artificial equal-size tiles."""
    if not items or width <= 0 or height <= 0:
        return []
    if len(items) == 1:
        return [(items[0], (x, y, width, height))]
    total = sum(value for _, value in items)
    accumulated, split = 0, 1
    for i, (_, value) in enumerate(items[:-1], 1):
        accumulated += value
        split = i
        if accumulated >= total / 2:
            break
    share = sum(value for _, value in items[:split]) / total
    if width >= height:
        a = (x, y, width * share, height)
        b = (x + width * share, y, width * (1 - share), height)
    else:
        a = (x, y, width, height * share)
        b = (x, y + height * share, width, height * (1 - share))
    return partition(items[:split], *a) + partition(items[split:], *b)


class Treemap(QWidget):
    activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.node = None
        self.rectangles = []
        self.setMouseTracking(True)
        self.setMinimumHeight(180)

    def set_node(self, node):
        self.node = node
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f6f8fc"))
        self.rectangles = []
        if not self.node:
            painter.setPen(QColor("#8995a8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "폴더를 분석하면 공간의 크기가 한눈에 보입니다")
            return
        children = self.node.children if self.node.is_dir else [self.node]
        children = sorted((child for child in children if child.size > 0), key=lambda c: -c.size)
        visible = children[:150]
        # Preserve area of the long tail with a non-navigable remainder tile.
        items = [(child, child.size) for child in visible]
        remaining = sum(child.size for child in children[150:])
        if remaining:
            items.append((None, remaining))
        if not items:
            painter.setPen(QColor("#8995a8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "표시할 용량이 없습니다")
        for i, ((child, size), area) in enumerate(partition(items, 3, 3, self.width() - 6, self.height() - 6)):
            rect = QRectF(*area).adjusted(2, 2, -2, -2)
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            self.rectangles.append((rect, child, size))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS[i % len(COLORS)] if child else "#9aa6b9"))
            painter.drawRoundedRect(rect, 5, 5)
            if rect.width() > 60 and rect.height() > 33:
                painter.save()
                painter.setClipRect(rect.adjusted(8, 5, -8, -4))
                painter.setPen(QColor("#ffffff"))
                font = QFont(self.font()); font.setBold(True); painter.setFont(font)
                label = child.name if child else "기타 항목"
                painter.drawText(rect.adjusted(10, 8, -8, -5), Qt.AlignmentFlag.AlignTop, label)
                if rect.height() > 57:
                    font.setBold(False); painter.setFont(font)
                    painter.drawText(rect.adjusted(10, 31, -8, -5), Qt.AlignmentFlag.AlignTop, format_bytes(size))
                painter.restore()

    def mouseMoveEvent(self, event):
        for rect, child, size in self.rectangles:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), (child.path if child else "기타 항목") + "\n" + format_bytes(size), self)
                return
        QToolTip.hideText()

    def mouseDoubleClickEvent(self, event):
        for rect, child, _ in self.rectangles:
            if child and rect.contains(event.position()):
                self.activated.emit(child)
                return

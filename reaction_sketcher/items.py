#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget, QStyle
from PyQt6.QtGui import QPen, QColor, QPainter, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF

class ReactionHandle(QGraphicsItem):
    """A square handle for adjusting item geometry."""
    def __init__(self, parent, handle_type):
        super().__init__(parent)
        self.handle_type = handle_type # "start", "end", "control", "top-left", "bottom-right"
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(10)
        self.setVisible(False)
        self.size = 8

    def boundingRect(self):
        s = self.size / 2
        return QRectF(-s, -s, self.size, self.size)

    def paint(self, painter, option, widget):
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#0078d7"), 1))
        painter.drawRect(self.boundingRect())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if hasattr(self.parentItem(), "on_handle_moved"):
                self.parentItem().on_handle_moved(self)
        return super().itemChange(change, value)

class ReactionArrowItem(QGraphicsItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.start_p = start_pos
        self.end_p = end_pos
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 3
        
        self.h_start = ReactionHandle(self, "start")
        self.h_end = ReactionHandle(self, "end")
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

    def on_handle_moved(self, handle):
        if self._initializing: return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        self.update()

    def set_end_pos(self, pos):
        self.prepareGeometryChange()
        self.end_p = self.mapFromScene(pos)
        self.sync_handles()
        self.update()

    def setSelected(self, selected):
        super().setSelected(selected)
        self.h_start.setVisible(selected)
        self.h_end.setVisible(selected)

    def boundingRect(self):
        line = QLineF(self.start_p, self.end_p)
        extra = 20
        return QRectF(self.start_p, self.end_p).normalized().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 4))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        painter.drawLine(line)
        
        angle = line.angle()
        head_len = 15; head_angle = 30
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle)
        painter.drawLine(self.end_p, self.end_p + h1.p2())
        painter.drawLine(self.end_p, self.end_p + h2.p2())

    def create_json_data(self):
        return {
            "type": "arrow",
            "start_x": self.pos().x() + self.start_p.x(),
            "start_y": self.pos().y() + self.start_p.y(),
            "end_x": self.pos().x() + self.end_p.x(),
            "end_y": self.pos().y() + self.end_p.y(),
            "color": self.pen_color.name(),
            "width": self.pen_width
        }

class ReactionPlusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.size = 20
        self.pen_color = QColor("#222222")

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), 6))
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
            painter.drawLine(QPointF(0, -s), QPointF(0, s))

        painter.setPen(QPen(self.pen_color, 3))
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
        painter.drawLine(QPointF(0, -s), QPointF(0, s))

    def create_json_data(self):
        return {"type": "plus", "x": self.pos().x(), "y": self.pos().y(), "color": self.pen_color.name()}

class ReactionMinusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.size = 20
        self.pen_color = QColor("#222222")

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), 6))
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))

        painter.setPen(QPen(self.pen_color, 3))
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))

    def create_json_data(self):
        return {"type": "minus", "x": self.pos().x(), "y": self.pos().y(), "color": self.pen_color.name()}

class ReactionResonanceArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 4))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        painter.drawLine(line)
        angle = line.angle()
        head_len = 15
        head_angle = 30
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle)
        painter.drawLine(self.end_p, self.end_p + h1.p2())
        painter.drawLine(self.end_p, self.end_p + h2.p2())
        h3 = QLineF.fromPolar(head_len, angle + head_angle)
        h4 = QLineF.fromPolar(head_len, angle - head_angle)
        painter.drawLine(self.start_p, self.start_p + h3.p2())
        painter.drawLine(self.start_p, self.start_p + h4.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_res"
        return data

class ReactionEquilibriumArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        angle = line.angle()
        offset = 4
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_start = self.start_p + p_offset
        l1_end = self.end_p + p_offset
        l2_start = self.start_p - p_offset
        l2_end = self.end_p - p_offset
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 8))
            painter.drawLine(self.start_p, self.end_p)
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(l1_start, l1_end)
        painter.drawLine(l2_start, l2_end)
        head_len = 12
        head_angle = 30
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
        painter.drawLine(l1_end, l1_end + h1.p2())
        h2 = QLineF.fromPolar(head_len, angle + head_angle)
        painter.drawLine(l2_start, l2_start + h2.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_eq"
        return data

class ReactionRetroArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        angle = line.angle()
        offset = 3
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_start = self.start_p + p_offset
        l1_end = self.end_p + p_offset
        l2_start = self.start_p - p_offset
        l2_end = self.end_p - p_offset
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 8))
            painter.drawLine(self.start_p, self.end_p)
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(l1_start, l1_end)
        painter.drawLine(l2_start, l2_end)
        head_len = 18
        head_angle = 40
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle)
        painter.drawLine(self.end_p, self.end_p + h1.p2())
        painter.drawLine(self.end_p, self.end_p + h2.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_retro"
        return data

class ReactionNoArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 10:
            return
        mid = line.center()
        angle = line.angle()
        cross_size = 8
        pen = QPen(QColor("#d32f2f"), 3)
        painter.setPen(pen)
        l1 = QLineF.fromPolar(cross_size, angle + 45 + 90)
        l2 = QLineF.fromPolar(cross_size, angle - 45 + 90)
        painter.drawLine(mid + l1.p2(), mid - l1.p2())
        painter.drawLine(mid + l2.p2(), mid - l2.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_no"
        return data

class ReactionCurvedArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos, is_fish_hook=False):
        self.is_fish_hook = is_fish_hook
        self.control_p = None # Scene coordinates
        self.h_control = None
        super().__init__(start_pos, end_pos)
        self.h_control = ReactionHandle(self, "control")
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        super().sync_handles()
        if hasattr(self, 'h_control') and self.h_control:
            self.h_control.setPos(self.get_control_point())

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "control":
            self.control_p = self.mapToScene(handle.pos())
        self.update()

    def get_control_point(self):
        if self.control_p is not None:
            return self.mapFromScene(self.control_p)
        line = QLineF(self.start_p, self.end_p)
        mid = line.center()
        angle = line.angle()
        dist = line.length() * 0.3
        offset_line = QLineF.fromPolar(dist, angle + 90)
        return mid + offset_line.p2()

    def setSelected(self, selected):
        super().setSelected(selected)
        self.h_control.setVisible(selected)

    def boundingRect(self):
        rect = super().boundingRect()
        cp = self.get_control_point()
        return rect.united(QRectF(cp, cp).adjusted(-20, -20, 20, 20))

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 4))
            painter.drawPath(path)
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)
        angle = QLineF(cp, self.end_p).angle()
        head_len = 15
        head_angle = 30
        if self.is_fish_hook:
            h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
            painter.drawLine(self.end_p, self.end_p + h1.p2())
        else:
            h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle)
            h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle)
            painter.drawLine(self.end_p, self.end_p + h1.p2())
            painter.drawLine(self.end_p, self.end_p + h2.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "curved_fish" if self.is_fish_hook else "curved_double"
        cp = self.get_control_point()
        scp = self.mapToScene(cp)
        data["cp_x"] = scp.x()
        data["cp_y"] = scp.y()
        return data

class ReactionBracketItem(QGraphicsItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPos(start_pos)
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(end_pos))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        
        self.h_br = ReactionHandle(self, "bottom-right")
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_br.setPos(self.rect.bottomRight())

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        self.rect.setBottomRight(handle.pos())
        self.update()

    def set_end_pos(self, pos):
        self.prepareGeometryChange()
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(pos))
        self.sync_handles()
        self.update()

    def setSelected(self, selected):
        super().setSelected(selected)
        self.h_br.setVisible(selected)

    def boundingRect(self):
        return self.rect.normalized().adjusted(-5, -5, 5, 5)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        painter.setPen(QPen(self.pen_color, self.pen_width))
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 2))
        bw = 8
        painter.drawLine(r.topLeft() + QPointF(bw, 0), r.topLeft())
        painter.drawLine(r.topLeft(), r.bottomLeft())
        painter.drawLine(r.bottomLeft(), r.bottomLeft() + QPointF(bw, 0))
        painter.drawLine(r.topRight() - QPointF(bw, 0), r.topRight())
        painter.drawLine(r.topRight(), r.bottomRight())
        painter.drawLine(r.bottomRight(), r.bottomRight() - QPointF(bw, 0))

    def create_json_data(self):
        return {
            "type": "bracket",
            "x": self.pos().x(),
            "y": self.pos().y(), 
            "w": self.rect.width(),
            "h": self.rect.height(),
            "color": self.pen_color.name(),
            "width": self.pen_width
        }

class ReactionCircleItem(QGraphicsItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPos(start_pos)
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(end_pos))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(4)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        
        self.h_br = ReactionHandle(self, "bottom-right")
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_br.setPos(self.rect.bottomRight())

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        self.rect.setBottomRight(handle.pos())
        self.update()

    def set_end_pos(self, pos):
        self.prepareGeometryChange()
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(pos))
        self.sync_handles()
        self.update()

    def setSelected(self, selected):
        super().setSelected(selected)
        self.h_br.setVisible(selected)

    def boundingRect(self):
        return self.rect.normalized().adjusted(-5, -5, 5, 5)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.DashLine))
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 2))
        painter.drawEllipse(r)

    def create_json_data(self):
        return {
            "type": "circle",
            "x": self.pos().x(),
            "y": self.pos().y(), 
            "w": self.rect.width(),
            "h": self.rect.height(),
            "color": self.pen_color.name(),
            "width": self.pen_width
        }

class ReactionTextItem(QGraphicsTextItem):
    def __init__(self, text, pos):
        super().__init__(text)
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(5)
        self.setFont(QFont("Arial", 14))
        self.setDefaultTextColor(QColor("#222222"))
        
    def focusInEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        super().focusInEvent(event)
        
    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)
        
    def paint(self, painter, option, widget):
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), 2, Qt.PenStyle.DashLine))
            painter.drawRect(self.boundingRect())
        super().paint(painter, option, widget)

    def create_json_data(self):
        return {
            "type": "text",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "text": self.toPlainText(),
            "font_family": self.font().family(),
            "font_size": self.font().pointSize(),
            "bold": self.font().bold(),
            "italic": self.font().italic(),
            "color": self.defaultTextColor().name()
        }

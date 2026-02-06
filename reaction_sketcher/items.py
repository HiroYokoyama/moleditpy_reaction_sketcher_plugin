#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget, QStyle
from PyQt6.QtGui import QPen, QColor, QPainter, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF
import math

def get_main_window(scene):
    """Helper to get MainWindow from a QGraphicsScene."""
    if not scene: return None
    views = scene.views()
    if not views: return None
    win = views[0].window()
    # In some cases window() might be the viewport
    if hasattr(win, "push_undo_state"): return win
    if hasattr(win, "parent") and win.parent():
        p = win.parent()
        if hasattr(p, "push_undo_state"): return p
    return None

class ReactionHandle(QGraphicsItem):
    """A square handle for adjusting item geometry."""
    def __init__(self, parent, handle_type):
        super().__init__(parent)
        self.handle_type = handle_type # "start", "end", "control", "top-left", "bottom-right"
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(10)
        self.setVisible(False)
        self.setAcceptHoverEvents(True)
        self.size = 10
        self.is_hovered = False

    def boundingRect(self):
        s = self.size / 2
        return QRectF(-s, -s, self.size, self.size)

    def paint(self, painter, option, widget):
        color = QColor("#ff9800") if self.is_hovered else QColor("#0078d7")
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(color, 2))
        if self.handle_type == "control":
            painter.drawEllipse(self.boundingRect())
        else:
            painter.drawRect(self.boundingRect())

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def shape(self):
        path = QPainterPath()
        s = 14 / 2 # Hit area larger than visual
        path.addRect(QRectF(-s, -s, 14, 14))
        return path

    def mousePressEvent(self, event):
        # Explicitly accept the press to prevent parent from starting a drag
        event.accept()
        # Temporarily disable parent's mobility to ensure focus only on the handle
        p = self.parentItem()
        if p and p.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            p.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self._parent_was_movable = True
        else:
            self._parent_was_movable = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Re-enable parent's mobility
        if getattr(self, '_parent_was_movable', False):
            p = self.parentItem()
            if p:
                p.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        
        # Trigger undo push through main window
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Angle Snapping (30 degrees)
            from PyQt6.QtWidgets import QApplication
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.AltModifier):
                p = self.parentItem()
                if p and self.handle_type in ("start", "end"):
                    # Disable snapping for curved arrows
                    if hasattr(p, "control_p"):
                        return super().itemChange(change, value)
                        
                    pivot = p.end_p if self.handle_type == "start" else p.start_p
                    proposed_pos = value
                    line = QLineF(pivot, proposed_pos)
                    if line.length() > 5:
                        angle = line.angle()
                        snapped_angle = round(angle / 15) * 15
                        new_line = QLineF.fromPolar(line.length(), snapped_angle)
                        new_pos = pivot + new_line.p2()
                        return new_pos

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
        self.head_size = 15
        
        self.h_start = ReactionHandle(self, "start")
        self.h_end = ReactionHandle(self, "end")
        self.h_head = ReactionHandle(self, "head_size")
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)
        
        # Position head handle at one of the corners of the arrowhead
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        head_angle = 25
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos)

    def on_handle_moved(self, handle):
        if self._initializing: return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            # Project mouse movement onto the barb line for more accurate size control
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            head_angle = 25
            barb_angle = angle + 180 + head_angle
            
            # Vector from end point to handle
            vec = handle.pos() - self.end_p
            # Unit vector of the barb
            barb_u = QLineF.fromPolar(1.0, barb_angle).p2()
            # Dot product (projection)
            proj_len = vec.x() * barb_u.x() + vec.y() * barb_u.y()
            self.head_size = max(5, proj_len)
        self.sync_handles()
        self.update()

    def set_end_pos(self, pos):
        self.prepareGeometryChange()
        self.end_p = self.mapFromScene(pos)
        self.sync_handles()
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            self.h_start.setVisible(selected)
            self.h_end.setVisible(selected)
            if hasattr(self, 'h_head') and self.h_head:
                self.h_head.setVisible(selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        line = QLineF(self.start_p, self.end_p)
        extra = 8
        return QRectF(self.start_p, self.end_p).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.lineTo(self.end_p)
        # Stroke the path to create a generous but tight hit area around the line
        stroker = QPainterPath()
        stroker.addPath(path)
        # Return a tight hit area (e.g., 10px wide)
        from PyQt6.QtGui import QPainterPathStroker
        s = QPainterPathStroker()
        s.setWidth(10)
        return s.createStroke(path)

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
        head_len = self.head_size
        head_angle = 25
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))

    def create_json_data(self):
        return {
            "type": "arrow",
            "start_x": self.pos().x() + self.start_p.x(),
            "start_y": self.pos().y() + self.start_p.y(),
            "end_x": self.pos().x() + self.end_p.x(),
            "end_y": self.pos().y() + self.end_p.y(),
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "head_size": self.head_size
        }

class ReactionPlusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.size = 20
        self.pen_color = QColor("#222222")
        self.pen_width = 2

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), 6))
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
            painter.drawLine(QPointF(0, -s), QPointF(0, s))

        painter.setPen(QPen(self.pen_color, self.pen_width))
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
        painter.drawLine(QPointF(0, -s), QPointF(0, s))

    def set_size(self, size):
        self.prepareGeometryChange()
        self.size = size
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

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
        self.pen_width = 2

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        painter.setPen(QPen(self.pen_color, self.pen_width))
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))

    def set_size(self, size):
        self.prepareGeometryChange()
        self.size = size
        self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

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
        if line.length() < 1: return
        painter.drawLine(line)
        
        angle = line.angle()
        head_len = self.head_size
        head_angle = 25
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        # End head
        h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2]))
        
        # Start head
        h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2()
        h_pos4 = QLineF.fromPolar(head_len, angle - head_angle).p2()
        painter.drawPolygon(QPolygonF([self.start_p, self.start_p + h_pos3, self.start_p + h_pos4]))

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_res"
        return data

class ReactionEquilibriumArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
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
            
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(l1_start, l1_end)
        painter.drawLine(l2_start, l2_end)
        
        # heads
        head_len = 15; head_angle = 35
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        # End head (top part, external barb - points UP/OUT)
        h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
        painter.drawPolygon(QPolygonF([l1_end, l1_end + h_pos1, l1_end + QLineF.fromPolar(self.head_size * 0.6, angle + 180).p2()]))
        
        # Start head (bottom part, external barb - points DOWN/OUT)
        h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
        painter.drawPolygon(QPolygonF([l2_start, l2_start + h_pos2, l2_start + QLineF.fromPolar(self.head_size * 0.6, angle).p2()]))

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        offset = 4
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_end = self.end_p + p_offset
        head_angle = 35
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
        self.h_head.setPos(l1_end + h_pos)
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

    def on_handle_moved(self, handle):
        if self._initializing: return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            offset = 4
            p_offset = QLineF.fromPolar(offset, angle + 90).p2()
            l1_end = self.end_p + p_offset
            head_angle = 35
            barb_angle = angle + 180 - head_angle
            vec = handle.pos() - l1_end
            barb_u = QLineF.fromPolar(1.0, barb_angle).p2()
            proj_len = vec.x() * barb_u.x() + vec.y() * barb_u.y()
            self.head_size = max(5, proj_len)
        self.sync_handles()
        self.update()

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_eq"
        return data

class ReactionRetroArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
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
            
        # Retro arrowhead (large triangle)
        head_len = self.head_size * 1.33 # Retro head is usually larger
        head_angle = 35
        # Shorten lines to avoid entering triangle
        shorten_dist = head_len * math.cos(math.radians(head_angle))
        back_vec = QLineF.fromPolar(shorten_dist, angle + 180).p2()
        
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(l1_start, l1_end + back_vec)
        painter.drawLine(l2_start, l2_end + back_vec)
 
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2]))

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        head_angle = 35
        # Retro head is 1.33x
        head_len = self.head_size * 1.33
        h_pos = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos) 
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

    def on_handle_moved(self, handle):
        if self._initializing: return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            head_angle = 35
            barb_angle = angle + 180 - head_angle
            vec = handle.pos() - self.end_p
            barb_u = QLineF.fromPolar(1.0, barb_angle).p2()
            proj_len = vec.x() * barb_u.x() + vec.y() * barb_u.y()
            self.head_size = max(5, proj_len / 1.33)
        self.sync_handles()
        self.update()

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_retro"
        return data

class ReactionNoArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos):
        super().__init__(start_pos, end_pos)
        self.negation_style = "slash" # "slash", "cross"

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 10: return
        mid = line.center()
        angle = line.angle()
        slash_len = 15
        
        pen = QPen(Qt.GlobalColor.black, self.pen_width + 1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        if self.negation_style == "slash":
            # Single black slash
            l_slash = QLineF.fromPolar(slash_len, angle + 90 + 20)
            painter.drawLine(mid + l_slash.p2(), mid - l_slash.p2())
        else:
            # Cross (X)
            l_1 = QLineF.fromPolar(slash_len, angle + 90 + 30)
            l_2 = QLineF.fromPolar(slash_len, angle + 90 - 30)
            painter.drawLine(mid + l_1.p2(), mid - l_1.p2())
            painter.drawLine(mid + l_2.p2(), mid - l_2.p2())

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_no"
        data["negation_style"] = self.negation_style
        return data

class ReactionCurvedArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos, is_fish_hook=False):
        self.is_fish_hook = is_fish_hook
        self.head_style = "triangle" # "barb", "triangle"
        self.control_p = None # Local coordinates
        self.h_control = None
        super().__init__(start_pos, end_pos)
        self.h_control = ReactionHandle(self, "control")
        self._initializing = True
        self.sync_handles()
        self.h_control.setVisible(self.isSelected())
        self._initializing = False

    def sync_handles(self):
        # Specific sync for curved arrow to use tangent angle for head handle
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)
        
        cp = self.get_control_point()
        angle = QLineF(cp, self.end_p).angle()
        head_angle = 25
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos)
        
        if hasattr(self, 'h_control') and self.h_control:
            self.h_control.setPos(cp)

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "control":
            self.control_p = handle.pos()
        self.update()

    def get_control_point(self):
        if self.control_p is not None:
            return self.control_p
        line = QLineF(self.start_p, self.end_p)
        mid = line.center()
        angle = line.angle()
        dist = line.length() * 0.3
        offset_line = QLineF.fromPolar(dist, angle + 90)
        return mid + offset_line.p2()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            if hasattr(self, 'h_control') and self.h_control:
                self.h_control.setVisible(selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        rect = super().boundingRect()
        cp = self.get_control_point()
        return rect.united(QRectF(cp, cp).adjusted(-15, -15, 15, 15))

    def shape(self):
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        from PyQt6.QtGui import QPainterPathStroker
        s = QPainterPathStroker()
        s.setWidth(12)
        return s.createStroke(path)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 100), self.pen_width + 6))
            painter.drawPath(path)
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)
        
        # Arrowhead logic
        # Calculate angle at the end point (tangent to the curve)
        # For quadTo(cp, end), the tangent at end is line(cp, end)
        angle = QLineF(cp, self.end_p).angle()
        head_len = self.head_size
        head_angle = 25
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.is_fish_hook:
            # Half arrowhead (barb style usually)
            h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            painter.drawLine(self.end_p, self.end_p + h1)
        else:
            # Full arrowhead
            h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            if self.head_style == "triangle":
                painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))
            else:
                painter.drawLine(self.end_p, self.end_p + h1)
                painter.drawLine(self.end_p, self.end_p + h2)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "curved_fish" if self.is_fish_hook else "curved_double"
        data["head_style"] = self.head_style
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

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.h_br.setVisible(bool(value))
        return super().itemChange(change, value)

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

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.h_br.setVisible(bool(value))
        return super().itemChange(change, value)

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
        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

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

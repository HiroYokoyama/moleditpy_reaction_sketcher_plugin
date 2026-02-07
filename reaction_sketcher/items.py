#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush, QPainter, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QEvent
import math

def sip_isdeleted_safe(obj):
    """Check if a PyQt object has been deleted at the C++ level."""
    if obj is None: return True
    try:
        from PyQt6.QtCore import Qt # Just any property to check validity
        # hasattr check on something that requires C++ bond can trigger RuntimeError if deleted
        # But actually, 'sip' is the direct way.
        import sip
        return sip.isdeleted(obj)
    except:
        return True

def rotate_point(point, center, angle_degrees):
    """Rotate a QPointF around a center QPointF."""
    rad = math.radians(angle_degrees)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    new_dx = dx * cos_a - dy * sin_a
    new_dy = dx * sin_a + dy * cos_a
    return QPointF(center.x() + new_dx, center.y() + new_dy)

def get_main_window(scene):
    """Helper to get MainWindow from a QGraphicsScene."""
    if not scene: return None
    # Return immediately if view doesn't exist (e.g. during shutdown)
    views = scene.views()
    if not views: return None
    
    # Get window from the first view
    view = views[0]
    win = view.window()
    
    # Traverse up to find MainWindow (the one with push_undo_state)
    curr = win
    while curr:
        if hasattr(curr, "push_undo_state"): return curr
        curr = curr.parent()
        
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
        s = 24 / 2 # Hit area significantly larger than visual (10)
        path.addRect(QRectF(-s, -s, 24, 24))
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
        self.head_angle = 25
        self.head_style = "chevron" # "triangle", "barb", "harpoon", "chevron", "chevron_curved"
        self.head_concavity = 0.5 # 0.0 to 1.0 (for chevron)
        
        self.group_id = None
        self.is_group_selected = False # Flag to suppress individual handles/highlight when group-selected

        self.h_start = ReactionHandle(self, "start")
        self.h_end = ReactionHandle(self, "end")
        self.h_head = ReactionHandle(self, "head_size")
        self.h_concavity = ReactionHandle(self, "concavity") # Square handle for chevron
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)
        
        # Position head handle at one of the corners of the arrowhead
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 + self.head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos)
        
        # Position concavity handle
        # Concavity handle position: projected onto centerline
        # self.head_concavity is the fraction of head_len from Tip to Base (1.0 = Flat base)
        # MidBase = Tip + polar(head_size * concavity, angle + 180)
        c_pos = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
        self.h_concavity.setPos(self.end_p + c_pos)
        self.h_concavity.setVisible(self.isSelected() and self.head_style == "chevron")

    def on_handle_moved(self, handle):
        if self._initializing: return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            line = QLineF(self.start_p, self.end_p)
            if line.length() < 1: return
            
            handle_line = QLineF(self.end_p, handle.pos())
            self.head_size = max(5, handle_line.length())
            
            # Calculate angle difference between arrow and handle
            arrow_angle = line.angle()
            handle_angle = handle_line.angle()
            diff = (handle_angle - (arrow_angle + 180)) % 360
            if diff > 180: diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))
            
        elif handle.handle_type == "concavity":
            # Determine projection on the centerline
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            # Vector from End to Handle
            vec = handle.pos() - self.end_p
            # Project vec onto the BACKWARDS direction of the arrow
            # Back direction vector
            back_vec = QLineF.fromPolar(1.0, angle + 180).p2()
            
            # Dot product
            dp = vec.x() * back_vec.x() + vec.y() * back_vec.y()
            
            # dp is the distance from tip.
            # concavity = dp / head_size
            if self.head_size > 0:
                self.head_concavity = max(0.1, min(1.0, dp / self.head_size))
            
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
            self.h_start.setVisible(selected and not self.is_group_selected)
            self.h_end.setVisible(selected and not self.is_group_selected)
            if hasattr(self, 'h_head') and self.h_head:
                self.h_head.setVisible(selected and not self.is_group_selected)
            if hasattr(self, 'h_concavity') and self.h_concavity:
                # Only show concavity handle if selected AND style is chevron
                self.h_concavity.setVisible(selected and self.head_style == "chevron" and not self.is_group_selected)
            if hasattr(self, 'h_control') and self.h_control:
                 self.h_control.setVisible(selected and not self.is_group_selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        # We must include the arrowhead size to avoid clipping
        # Reduced padding from 10 to 2
        extra = self.head_size + self.pen_width + 2
        return QRectF(self.start_p, self.end_p).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.lineTo(self.end_p)
        
        # Stroke the line part
        from PyQt6.QtGui import QPainterPathStroker
        s = QPainterPathStroker()
        s.setWidth(10) # Generous hit width
        stroked_path = s.createStroke(path)
        
        # Add the arrowhead area
        line = QLineF(self.start_p, self.end_p)
        if line.length() >= 1:
            angle = line.angle()
            head_len = self.head_size
            head_angle = self.head_angle
            
            # Calculate points matching the paint logic
            tip = self.end_p
            h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            
            head_poly = QPolygonF([tip, tip + h1, tip + h2])
            
            # For shapes like Retro, we might simply cover the triangle area
            # For Equil, it's more complex, but a simple triangle at the end helps basic selection.
            # We add the polygon to the path.
            stroked_path.addPolygon(head_poly)
            
        return stroked_path

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            # Reduced strength: lighter blue, thinner line
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        
        # [Fix] Shorten the shaft to prevent it from protruding through the arrowhead tip
        # especially for sharp angles or 'chevron' style where the tip is narrow.
        shorten_len = 0
        if self.head_style in ["triangle", "chevron", "chevron_curved", "harpoon"]:
             # Heuristic: Shorten by roughly 3x pen width to ensure it's hidden inside the head
             # but check against head size to not disappear.
             shorten_len = min(self.head_size * 0.8, self.pen_width * 3.5)
        
        # Only shorten if line is long enough
        if line.length() > shorten_len + 2:
             # Move end point back
             new_end = line.pointAt(1.0 - shorten_len / line.length())
             line.setP2(new_end)
        
        painter.drawLine(line)
        
        angle = line.angle()
        head_len = self.head_size
        head_angle = self.head_angle
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.head_style == "triangle":
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))
        elif self.head_style == "chevron":
            # Chevron: Sharp Concave base
            mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_base, self.end_p + h2]))
        elif self.head_style == "chevron_curved":
            # Chevron: Concave base with curve
            mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
            path = QPainterPath()
            path.moveTo(self.end_p)
            path.lineTo(self.end_p + h1)
            path.quadTo(self.end_p + mid_base, self.end_p + h2)
            path.lineTo(self.end_p)
            painter.drawPath(path)
        elif self.head_style == "harpoon":
            # Harpoon: Top half filled (using h1 which corresponds to angle + 180 + head_angle)
            # We close the polygon at the center line
            mid_back = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle + 180).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_back]))
        else:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(self.end_p, self.end_p + h1)
            painter.drawLine(self.end_p, self.end_p + h2)

    def create_json_data(self):
        return {
            "type": "arrow",
            "start_x": self.pos().x() + self.start_p.x(),
            "start_y": self.pos().y() + self.start_p.y(),
            "end_x": self.pos().x() + self.end_p.x(),
            "end_y": self.pos().y() + self.end_p.y(),
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "head_size": self.head_size,
            "head_angle": self.head_angle,
            "head_style": self.head_style,
            "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        """Rotate start and end points around a center."""
        self.start_p = rotate_point(self.start_p, center, angle_degrees)
        self.end_p = rotate_point(self.end_p, center, angle_degrees)
        self.sync_handles()
        self.update()

class ReactionPlusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.size = 20
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.group_id = None
        self.is_group_selected = False

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        if (option.state & QStyle.StateFlag.State_Selected) and not self.is_group_selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
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
        return {
            "type": "plus",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "size": self.size,
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionMinusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.size = 20
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.group_id = None
        self.is_group_selected = False

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, self.size + 10, self.size + 10)

    def paint(self, painter, option, widget):
        s = self.size / 2
        painter.setPen(QPen(self.pen_color, self.pen_width))
        if (option.state & QStyle.StateFlag.State_Selected) and not self.is_group_selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
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
        return {
             "type": "minus",
             "x": self.pos().x(),
             "y": self.pos().y(),
             "rotation": self.rotation(),
             "size": self.size,
             "color": self.pen_color.name(),
             "width": self.pen_width,
             "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionResonanceArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        
        # [Fix] Shorten Both Ends for Resonance Arrow
        shorten_len = 0
        if self.head_style in ["triangle", "chevron", "chevron_curved", "harpoon"]:
             shorten_len = min(self.head_size * 0.8, self.pen_width * 3.5)
        
        if line.length() > shorten_len * 2 + 2:
             new_start = line.pointAt(shorten_len / line.length())
             new_end = line.pointAt(1.0 - shorten_len / line.length())
             line.setP1(new_start)
             line.setP2(new_end)
        
        painter.drawLine(line)
        
        angle = line.angle()
        head_len = self.head_size
        head_angle = self.head_angle
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.head_style == "triangle":
            # End head
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2]))
            
            # Start head
            h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2()
            h_pos4 = QLineF.fromPolar(head_len, angle - head_angle).p2()
            painter.drawPolygon(QPolygonF([self.start_p, self.start_p + h_pos3, self.start_p + h_pos4]))
        elif self.head_style == "harpoon":
            mid_back_end = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle + 180).p2()
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2() # Top relative to incoming
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + mid_back_end]))

            mid_back_start = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle).p2()
            h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2() # Top relative to outgoing
            # Note: For rotational symmetry, if end is Top, Start should be Bottom?
            # Standard resonance is usually symmetric. Let's keep it rotationally symmetric (Top on both ends relative to line).
            painter.drawPolygon(QPolygonF([self.start_p, self.start_p + h_pos3, self.start_p + mid_back_start]))
        else:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            # End head
            # End head
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            
            # Start head
            h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2()
            h_pos4 = QLineF.fromPolar(head_len, angle - head_angle).p2()

            if self.head_style == "triangle" or self.head_style == "chevron" or self.head_style == "harpoon":
                painter.setBrush(self.pen_color)
                painter.setPen(QPen(self.pen_color, 1))
                
                # Helper for end head
                def draw_head_poly(tip, p1, p2, angle_base):
                    points = [tip, tip + p1]
                    if self.head_style == "chevron":
                        mid = QLineF.fromPolar(head_len * self.head_concavity, angle_base).p2()
                        points.append(tip + mid)
                    elif self.head_style == "harpoon":
                         # Harpoon: Half head.
                         mid = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle_base).p2()
                         return QPolygonF([tip, tip + p1, tip + mid])

                    points.append(tip + p2)
                    return QPolygonF(points)

                # End Head (Base angle is angle+180)
                poly_end = draw_head_poly(self.end_p, h_pos1, h_pos2, angle + 180)
                painter.drawPolygon(poly_end)
                
                # Start Head (Base angle is angle)
                # h_pos3/4 are vectors from start_p for the start head.
                
                # For Harpoon at start, use h_pos3 to maintain rotational symmetry logic if desired.
                
                if self.head_style == "harpoon":
                    mid_start = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle).p2()
                    painter.drawPolygon(QPolygonF([self.start_p, self.start_p + h_pos3, self.start_p + mid_start]))
                else:
                    poly_start = draw_head_poly(self.start_p, h_pos3, h_pos4, angle)
                    painter.drawPolygon(poly_start)

            else:
                # Barb (Open)
                painter.drawLine(self.end_p, self.end_p + h_pos1)
                painter.drawLine(self.end_p, self.end_p + h_pos2)
                painter.drawLine(self.start_p, self.start_p + h_pos3)
                painter.drawLine(self.start_p, self.start_p + h_pos4)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_res"
        data["head_concavity"] = self.head_concavity
        return data

class ReactionEquilibriumArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos):
        self.double_arrow_offset = 4.0
        super().__init__(start_pos, end_pos)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        angle = line.angle()
        offset = self.double_arrow_offset
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_start = self.start_p + p_offset
        l1_end = self.end_p + p_offset
        l2_start = self.start_p - p_offset
        l2_end = self.end_p - p_offset
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)
            
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        # [Fix] Shorten shafts for Equilibrium Arrow
        # l1 (top/right) has head at End. Shorten End.
        # l2 (bottom/left) has head at Start. Shorten Start.
        
        shorten_len = 0
        if self.head_style in ["triangle", "chevron", "chevron_curved", "harpoon"]:
             # For Equilibrium, lines use FlatCap so we might strictly need less shortening,
             # but to be safe against protrusion/antialiasing:
             shorten_len = min(self.head_size * 0.8, self.pen_width * 3.5)

        draw_l1_end = l1_end
        draw_l2_start = l2_start
        
        len_l1 = QLineF(l1_start, l1_end).length()
        if len_l1 > shorten_len + 2:
             vec_l1 = QLineF(l1_start, l1_end)
             draw_l1_end = vec_l1.pointAt(1.0 - shorten_len / len_l1)
             
        len_l2 = QLineF(l2_start, l2_end).length()
        if len_l2 > shorten_len + 2:
             vec_l2 = QLineF(l2_start, l2_end)
             draw_l2_start = vec_l2.pointAt(shorten_len / len_l2)

        painter.drawLine(l1_start, draw_l1_end)
        painter.drawLine(draw_l2_start, l2_end)
        
        # heads
        head_len = self.head_size; head_angle = self.head_angle
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.head_style == "triangle":
            # Full Triangle (New)
            # End head (Right line)
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            h_pos1b = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
            painter.drawPolygon(QPolygonF([l1_end, l1_end + h_pos1, l1_end + h_pos1b]))
            
            # Start head (Left Line)
            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            h_pos2b = QLineF.fromPolar(self.head_size, angle + head_angle).p2()
            painter.drawPolygon(QPolygonF([l2_start, l2_start + h_pos2, l2_start + h_pos2b]))

        elif self.head_style == "chevron":
            # Chevron (Concave base) - Full head
            # End head (Right line)
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            h_pos1b = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
            mid_end = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
            painter.drawPolygon(QPolygonF([l1_end, l1_end + h_pos1, l1_end + mid_end, l1_end + h_pos1b]))

            # Start head (Left Line)
            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            h_pos2b = QLineF.fromPolar(self.head_size, angle + head_angle).p2()
            mid_start = QLineF.fromPolar(self.head_size * self.head_concavity, angle).p2()
            painter.drawPolygon(QPolygonF([l2_start, l2_start + h_pos2, l2_start + mid_start, l2_start + h_pos2b]))

        elif self.head_style == "harpoon":
            # Harpoon (Old "triangle" style)
            # End head (top part, external barb - points UP/OUT)
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            painter.drawPolygon(QPolygonF([l1_end, l1_end + h_pos1, l1_end + QLineF.fromPolar(self.head_size * 0.6, angle + 180).p2()]))
            
            # Start head (bottom part, external barb - points DOWN/OUT)
            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            painter.drawPolygon(QPolygonF([l2_start, l2_start + h_pos2, l2_start + QLineF.fromPolar(self.head_size * 0.6, angle).p2()]))
        else:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            painter.drawLine(l1_end, l1_end + h_pos1)
            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            painter.drawLine(l2_start, l2_start + h_pos2)

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        offset = self.double_arrow_offset
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_end = self.end_p + p_offset
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 - self.head_angle).p2()
        self.h_head.setPos(l1_end + h_pos)
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        if hasattr(self, 'h_concavity') and self.h_concavity:
             c_pos = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
             self.h_concavity.setPos(l1_end + c_pos)
             self.h_concavity.setVisible(self.isSelected() and self.head_style == "chevron")

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
            
            handle_line = QLineF(l1_end, handle.pos())
            self.head_size = max(5, handle_line.length())
            
            # Calculate angle difference
            handle_angle = handle_line.angle()
            diff = (handle_angle - (angle + 180)) % 360
            if diff > 180: diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))
        self.sync_handles()
        self.update()

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_eq"
        data["double_arrow_offset"] = getattr(self, "double_arrow_offset", 4.0)
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
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)
            
        # Retro arrowhead (large triangle)
        head_len = self.head_size
        head_angle = self.head_angle
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
        
        if self.head_style == "triangle":
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2]))
        elif self.head_style == "chevron":
            mid_back = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + mid_back, self.end_p + h_pos2]))
        elif self.head_style == "harpoon":
             mid_back = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle + 180).p2()
             painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + mid_back]))
        else:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(self.end_p, self.end_p + h_pos1)
            painter.drawLine(self.end_p, self.end_p + h_pos2)

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 - self.head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos) 
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        if hasattr(self, 'h_concavity') and self.h_concavity:
             c_pos = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
             self.h_concavity.setPos(self.end_p + c_pos)
             self.h_concavity.setVisible(self.isSelected() and self.head_style == "chevron")

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
            handle_line = QLineF(self.end_p, handle.pos())
            self.head_size = max(5, handle_line.length())
            
            # Calculate angle difference
            handle_angle = handle_line.angle()
            diff = (handle_angle - (angle + 180)) % 360
            if diff > 180: diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))
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
        # We handle selection ourselves to match style
        # But QGraphicsTextItem handles selection natively with a dashed box usually.
        # We can disable the native selection indicator by option.state &= ~State_Selected
        # and draw our own.
        
        is_selected = (option.state & QStyle.StateFlag.State_Selected)
        if is_selected and not self.is_group_selected:
             # Draw custom selection rect
             painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.drawRect(self.boundingRect())
             
        is_selected = (option.state & QStyle.StateFlag.State_Selected)
        if is_selected and not self.is_group_selected:
             # Draw custom selection rect
             painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.drawRect(self.boundingRect())
             
        is_selected = (option.state & QStyle.StateFlag.State_Selected)
        if is_selected and not self.is_group_selected:
             # Draw custom selection rect
             painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.drawRect(self.boundingRect())
             
             # Remove state so base class doesn't draw its own
             option.state &= ~QStyle.StateFlag.State_Selected

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
        elif self.negation_style == "double_slash":
            # Double slash
            l_slash = QLineF.fromPolar(slash_len, angle + 90 + 20)
            offset_vec = QLineF.fromPolar(3, angle).p2()
            ensure_gap = 4
            
            center1 = mid - offset_vec
            center2 = mid + offset_vec
            
            painter.drawLine(center1 + l_slash.p2(), center1 - l_slash.p2())
            painter.drawLine(center2 + l_slash.p2(), center2 - l_slash.p2())
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

class ReactionDashedArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)

        # Dashed Pen
        pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        
        # [Fix] Shorten shaft for Dashed Arrow
        shorten_len = 0
        if self.head_style in ["triangle", "chevron", "chevron_curved", "harpoon"]:
             shorten_len = min(self.head_size * 0.8, self.pen_width * 3.5)
        
        if line.length() > shorten_len + 2:
             new_end = line.pointAt(1.0 - shorten_len / line.length())
             line.setP2(new_end)
             
        painter.drawLine(line)
        
        angle = line.angle()
        head_len = self.head_size
        head_angle = self.head_angle
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
        
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.head_style == "triangle":
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))
        elif self.head_style == "chevron":
            # Chevron: Sharp Concave base
            mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_base, self.end_p + h2]))
        elif self.head_style == "chevron_curved":
            # Chevron: Concave base with curve
            mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
            path = QPainterPath()
            path.moveTo(self.end_p)
            path.lineTo(self.end_p + h1)
            path.quadTo(self.end_p + mid_base, self.end_p + h2)
            path.lineTo(self.end_p)
            painter.drawPath(path)
        elif self.head_style == "harpoon":
            mid_back = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle + 180).p2()
            painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_back]))
        else:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(self.end_p, self.end_p + h1)
            painter.drawLine(self.end_p, self.end_p + h2)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_dashed"
        return data

class ReactionCurvedArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos, is_fish_hook=False):
        self.is_fish_hook = is_fish_hook
        self.head_style = "chevron" # Default to chevron
        self.control_p = None # Local coordinates
        self.h_control = None
        self.curvature = 0.8 # Detailed curvature to ensure handle is accessible
        self.group_id = None
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
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 + self.head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos)
        
        if hasattr(self, 'h_control') and self.h_control:
            self.h_control.setPos(cp)
            
        if hasattr(self, 'h_concavity') and self.h_concavity:
             c_pos = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
             self.h_concavity.setPos(self.end_p + c_pos)
             self.h_concavity.setVisible(self.isSelected() and self.head_style == "chevron")

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
            # If control point is moved manually, we might want to update curvature?
            # Or just leave it as manual control.
            # If manual control_p is set, curvature property is effectively overridden/ignored for position,
            # but maybe we should update it to match new geometry?
            # For now, let's keep curvature as a param that drives auto-placement if control_p is None?
            # But get_control_point returns control_p if set.
        elif handle.handle_type == "head_size":
            cp = self.get_control_point()
            angle = QLineF(cp, self.end_p).angle()
            handle_line = QLineF(self.end_p, handle.pos())
            self.head_size = max(5, handle_line.length())
            
            # Calculate angle difference
            handle_angle = handle_line.angle()
            diff = (handle_angle - (angle + 180)) % 360
            if diff > 180: diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))
            
        elif handle.handle_type == "concavity":
             cp = self.get_control_point()
             angle = QLineF(cp, self.end_p).angle()
             vec = handle.pos() - self.end_p
             back_vec = QLineF.fromPolar(1.0, angle + 180).p2()
             dp = vec.x() * back_vec.x() + vec.y() * back_vec.y()
             if self.head_size > 0:
                 self.head_concavity = max(0.1, min(1.0, dp / self.head_size))
        self.sync_handles() # Ensure handle syncs back correctly
        self.update()

    def get_control_point(self):
        if self.control_p is not None:
            return self.control_p
        line = QLineF(self.start_p, self.end_p)
        mid = line.center()
        angle = line.angle()
        dist = line.length() * self.curvature
        offset_line = QLineF.fromPolar(dist, angle + 90)
        return mid + offset_line.p2()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            if hasattr(self, 'h_control') and self.h_control:
                self.h_control.setVisible(selected and not self.is_group_selected)
            if hasattr(self, 'h_concavity') and self.h_concavity:
                self.h_concavity.setVisible(selected and self.head_style == "chevron" and not self.is_group_selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        rect = super().boundingRect()
        cp = self.get_control_point()
        # Reduced padding from 15 to 5
        return rect.united(QRectF(cp, cp).adjusted(-5, -5, 5, 5))

    def shape(self):
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        from PyQt6.QtGui import QPainterPathStroker
        s = QPainterPathStroker()
        s.setWidth(12)
        stroked = s.createStroke(path)
        
        # Add arrowhead for hit detection
        if self.__class__.__name__ != "ReactionCurvedLineItem":
             arrow_path = QPainterPath()
             angle = QLineF(cp, self.end_p).angle()
             head_len = self.head_size
             
             if self.is_fish_hook:
                 h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
                 # Fish hook is a line, but for shape we can make it a polygon or stroke
                 arrow_path.moveTo(self.end_p)
                 arrow_path.lineTo(self.end_p + h1)
                 # Stroke it to make it clickable
                 stroked_arrow = s.createStroke(arrow_path)
                 stroked.addPath(stroked_arrow)
             else:
                 h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
                 h2 = QLineF.fromPolar(head_len, angle + 180 - self.head_angle).p2()
                 
                 if self.head_style == "triangle":
                     arrow_path.addPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))
                 elif self.head_style == "chevron":
                     mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
                     arrow_path.addPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_base, self.end_p + h2]))
                 elif self.head_style == "chevron_curved":
                     mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
                     arrow_path.moveTo(self.end_p)
                     arrow_path.lineTo(self.end_p + h1)
                     arrow_path.quadTo(self.end_p + mid_base, self.end_p + h2)
                     arrow_path.lineTo(self.end_p)
                 elif self.head_style == "harpoon":
                     # Use self.head_angle for consistency
                     mid_back = QLineF.fromPolar(head_len * math.cos(math.radians(self.head_angle)), angle + 180).p2()
                     arrow_path.addPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_back]))
                 else:
                     # Open/Barb
                     arrow_path.moveTo(self.end_p)
                     arrow_path.lineTo(self.end_p + h1)
                     arrow_path.moveTo(self.end_p)
                     arrow_path.lineTo(self.end_p + h2)
                     stroked_arrow = s.createStroke(arrow_path)
                     stroked.addPath(stroked_arrow)
                 
                 if not arrow_path.isEmpty():
                    stroked.addPath(arrow_path)

        return stroked

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        path.quadTo(cp, self.end_p)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            
        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush) # Ensure curve isn't filled
        # [Fix] Shorten curve to prevent shaft protrusion
        # Calculate approximate length to shorten
        shorten_len = 0
        if self.head_style in ["triangle", "chevron", "chevron_curved", "harpoon"] and not self.is_fish_hook:
             shorten_len = min(self.head_size * 0.8, self.pen_width * 3.5)
        
        draw_path = path
        if shorten_len > 0:
            # Approximate shortening for Quadratic Bezier
            # We want to find t < 1 such that distance(P(t), End) ~ shorten_len
            # Simple approx: linearize the end segment. 
            # chord len ~ |End - Cp|.
            d_cp_end = QLineF(cp, self.end_p).length()
            if d_cp_end > shorten_len:
                 # t_cut implies how much of the LAST LEG we cut? 
                 # Approximation: t_new = 1.0 - (shorten_len / total_arc_estimate)
                 # Better: t_new = 1.0 - (shorten_len / (d_start_cp + d_cp_end))
                 total_est = QLineF(self.start_p, cp).length() + d_cp_end
                 if total_est > shorten_len * 1.5:
                     t_cut = 1.0 - (shorten_len / total_est)
                     
                     # Split Bezier at t_cut
                     # P0 = Start, P1 = Cp, P2 = End
                     # New P1' = (1-t)P0 + tP1 ?? No.
                     # Left subcurve (0..t) control points:
                     # Q0 = P0
                     # Q1 = (1-t)P0 + tP1
                     # Q2 = P(t) = (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2
                     
                     t = t_cut
                     p0 = self.start_p
                     p1 = cp
                     p2 = self.end_p
                     
                     q1 = p0 * (1-t) + p1 * t
                     q2 = (p0 * ((1-t)**2)) + (p1 * (2*(1-t)*t)) + (p2 * (t**2))
                     
                     short_path = QPainterPath()
                     short_path.moveTo(p0)
                     short_path.quadTo(q1, q2)
                     draw_path = short_path

        painter.drawPath(draw_path)
        
        # Arrowhead logic
        # Calculate angle at the end point (tangent to the curve)
        # For quadTo(cp, end), the tangent at end is line(cp, end)
        angle = QLineF(cp, self.end_p).angle()
        head_len = self.head_size
        head_angle = 25
        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(QPen(self.pen_color, 1))
        
        if self.is_fish_hook:
            # Half arrowhead (barb style usually)
            h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
            painter.drawLine(self.end_p, self.end_p + h1)
        else:
            # Full arrowhead
            h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
            h2 = QLineF.fromPolar(head_len, angle + 180 - self.head_angle).p2()
            
            # Use Brush for filled shapes
            painter.setBrush(QBrush(self.pen_color, Qt.BrushStyle.SolidPattern))
            
            if self.head_style == "triangle":
                painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2]))
            elif self.head_style == "chevron":
                mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
                painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_base, self.end_p + h2]))
            elif self.head_style == "chevron_curved":
                mid_base = QLineF.fromPolar(head_len * self.head_concavity, angle + 180).p2()
                path = QPainterPath()
                path.moveTo(self.end_p)
                path.lineTo(self.end_p + h1)
                path.quadTo(self.end_p + mid_base, self.end_p + h2)
                path.lineTo(self.end_p)
                painter.drawPath(path)
            elif self.head_style == "harpoon":
                # Harpoon is usually just half an arrow, but if mapped to 'harpoon' style it might be filled?
                # If it's asymmetric filled:
                mid_back = QLineF.fromPolar(head_len * math.cos(math.radians(head_angle)), angle + 180).p2()
                painter.drawPolygon(QPolygonF([self.end_p, self.end_p + h1, self.end_p + mid_back]))
            else:
                # Open / Barb (no fill)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(self.end_p, self.end_p + h1)
                painter.drawLine(self.end_p, self.end_p + h2)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "curved_fish" if self.is_fish_hook else "curved_double"
        data["head_style"] = self.head_style
        cp = self.get_control_point()
        
        # [Fix] Removed mapToScene(cp), saving local coord cp directly
        data["cp_x"] = cp.x()
        data["cp_y"] = cp.y()
        data["group_id"] = self.group_id
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
        self.bracket_type = "square" # "square", "round", "curly"
        self.line_style = "solid" # "solid", "dashed"
        
        self.h_br = ReactionHandle(self, "bottom-right")
        self._initializing = True
        self.group_id = None
        self.is_group_selected = False
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
            self.h_br.setVisible(bool(value) and not self.is_group_selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        # Reduced padding from 10 to 2
        return self.rect.normalized().adjusted(-2, -2, 2, 2)

    def shape(self):
        path = QPainterPath()
        r = self.rect.normalized()
        
        if self.bracket_type == "round":
             bw = min(r.width()/2, 20)
             # Use arcMoveTo + arcTo for disjoint arcs in shape path
             path.arcMoveTo(QRectF(r.left(), r.top(), bw, r.height()), 90)
             path.arcTo(QRectF(r.left(), r.top(), bw, r.height()), 90, 180) # Left
             
             path.arcMoveTo(QRectF(r.right()-bw, r.top(), bw, r.height()), -90)
             path.arcTo(QRectF(r.right()-bw, r.top(), bw, r.height()), -90, 180) # Right
             
        elif self.bracket_type == "curly":
             bw = 15
             x, y, w, h = r.x(), r.y(), r.width(), r.height()
             
             # Left {
             p_l = QPainterPath()
             p_l.moveTo(x + bw, y)
             p_l.quadTo(x, y, x, y + h*0.25)
             p_l.lineTo(x, y + h*0.5 - 5)
             p_l.lineTo(x - 5, y + h*0.5) 
             p_l.lineTo(x, y + h*0.5 + 5)
             p_l.lineTo(x, y + h*0.75)
             p_l.quadTo(x, y + h, x + bw, y + h)
             path.addPath(p_l)
             
             # Right }
             p_r = QPainterPath()
             rx = x + w
             p_r.moveTo(rx - bw, y)
             p_r.quadTo(rx, y, rx, y + h*0.25)
             p_r.lineTo(rx, y + h*0.5 - 5)
             p_r.lineTo(rx + 5, y + h*0.5)
             p_r.lineTo(rx, y + h*0.5 + 5)
             p_r.lineTo(rx, y + h*0.75)
             p_r.quadTo(rx, y + h, rx - bw, y + h)
             path.addPath(p_r)

        else: # Square
            bw = 8
            # Left
            path.moveTo(r.topLeft() + QPointF(bw, 0))
            path.lineTo(r.topLeft())
            path.lineTo(r.bottomLeft())
            path.lineTo(r.bottomLeft() + QPointF(bw, 0))
            
            # Right
            path.moveTo(r.topRight() - QPointF(bw, 0))
            path.lineTo(r.topRight())
            path.lineTo(r.bottomRight())
            path.lineTo(r.bottomRight() - QPointF(bw, 0))

        # Create a stroke path for detection
        from PyQt6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(10) # Hit tolerance
        return stroker.createStroke(path)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        pen = QPen(self.pen_color, self.pen_width)
        if self.line_style == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), self.pen_width + 2))
        
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        if self.bracket_type == "round":
             # Round Brackets (Parentheses)
             # Left Arc
             # drawArc takes angles in 1/16th degrees
             bw = min(r.width()/2, 20)
             painter.drawArc(QRectF(r.left(), r.top(), bw, r.height()), 90*16, 180*16)
             painter.drawArc(QRectF(r.right()-bw, r.top(), bw, r.height()), -90*16, 180*16)
            
        elif self.bracket_type == "curly":
             # Curly Braces { }
             bw = 15
             x, y, w, h = r.x(), r.y(), r.width(), r.height()
             
             # Left {
             p_l = QPainterPath()
             p_l.moveTo(x + bw, y)
             p_l.quadTo(x, y, x, y + h*0.25)
             p_l.lineTo(x, y + h*0.5 - 5)
             p_l.lineTo(x - 5, y + h*0.5) 
             p_l.lineTo(x, y + h*0.5 + 5)
             p_l.lineTo(x, y + h*0.75)
             p_l.quadTo(x, y + h, x + bw, y + h)
             painter.drawPath(p_l)
             
             # Right }
             p_r = QPainterPath()
             rx = x + w
             p_r.moveTo(rx - bw, y)
             p_r.quadTo(rx, y, rx, y + h*0.25)
             p_r.lineTo(rx, y + h*0.5 - 5)
             p_r.lineTo(rx + 5, y + h*0.5)
             p_r.lineTo(rx, y + h*0.5 + 5)
             p_r.lineTo(rx, y + h*0.75)
             p_r.quadTo(rx, y + h, rx - bw, y + h)
             painter.drawPath(p_r)

        else: # Square
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
            "rotation": self.rotation(),
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "bracket_type": self.bracket_type,
            "line_style": self.line_style,
            "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionCircleItem(QGraphicsItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPos(start_pos)
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(end_pos))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(4)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.shape_type = "rectangle" # "circle", "rectangle"
        self.line_style = "solid" # "dashed", "solid"
        
        self.h_br = ReactionHandle(self, "bottom-right")
        self._initializing = True
        self.group_id = None
        self.is_group_selected = False
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
            self.h_br.setVisible(bool(value) and not self.is_group_selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        return self.rect.normalized().adjusted(-5, -5, 5, 5)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen_style = Qt.PenStyle.DashLine if self.line_style == "dashed" else Qt.PenStyle.SolidLine
        painter.setPen(QPen(self.pen_color, self.pen_width, pen_style))
        
        if (option.state & QStyle.StateFlag.State_Selected) and not self.is_group_selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), self.pen_width + 2, pen_style))
        
        if self.shape_type == "rectangle":
            painter.drawRect(r)
        else:
            painter.drawEllipse(r)

    def create_json_data(self):
        return {
            "type": "circle",
            "x": self.pos().x(),
            "y": self.pos().y(), 
            "w": self.rect.width(),
            "h": self.rect.height(),
            "rotation": self.rotation(),
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "shape_type": getattr(self, "shape_type", "circle"),
            "line_style": self.line_style,
            "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionLineItem(ReactionArrowItem):
    """Straight line without arrowheads."""
    def __init__(self, start_pos, end_pos):
        super().__init__(start_pos, end_pos)
        self.line_style = "solid" # "solid", "dashed"
        
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.drawLine(self.start_p, self.end_p)

        style = Qt.PenStyle.DashLine if self.line_style == "dashed" else Qt.PenStyle.SolidLine
        painter.setPen(QPen(self.pen_color, self.pen_width, style, Qt.PenCapStyle.RoundCap))
        
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1: return
        painter.drawLine(line)

    def create_json_data(self):
        return {
            "type": "line",
            "start_x": self.pos().x() + self.start_p.x(),
            "start_y": self.pos().y() + self.start_p.y(),
            "end_x": self.pos().x() + self.end_p.x(),
            "end_y": self.pos().y() + self.end_p.y(),
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "line_style": self.line_style,
            "group_id": self.group_id
        }

class ReactionCurvedLineItem(ReactionCurvedArrowItem):
    """Curved line without arrowheads."""
    def __init__(self, start_pos, end_pos):
        super().__init__(start_pos, end_pos)
        self.line_style = "solid"
        
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            
        style = Qt.PenStyle.DashLine if self.line_style == "dashed" else Qt.PenStyle.SolidLine
        painter.setPen(QPen(self.pen_color, self.pen_width, style, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "line_curved"
        data["line_style"] = self.line_style
        # Override head_style to None or remove it? JSON loader will need "type"
        if "head_style" in data: del data["head_style"]
        if "head_angle" in data: del data["head_angle"]
        return data

    def rotate_around(self, center, angle_degrees):
        """Rotate start and end points around a center."""
        self.start_p = rotate_point(self.start_p, center, angle_degrees)
        self.end_p = rotate_point(self.end_p, center, angle_degrees)
        
        # Rotate control point if it exists
        if self.control_p is not None:
             self.control_p = rotate_point(self.control_p, center, angle_degrees)
             
        self.sync_handles()
        self.update()

class ReactionFreehandItem(QGraphicsItem):
    """Freehand drawing item."""
    def __init__(self, start_pos):
        super().__init__()
        self.setPos(start_pos) # start_pos is origin (0,0) usually, path is relative?
                               # Actually simpler: pos is (0,0) of scene? No, let's make pos the first point.
        self.points = [QPointF(0, 0)] 
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.path = QPainterPath()
        self.path.moveTo(0, 0)
        self.path.moveTo(0, 0)
        self.boundingRect_ = QRectF(0, 0, 1, 1)
        self.group_id = None
        self.is_group_selected = False

    def add_point(self, pos):
        # pos is scene pos. Convert to local.
        local_pos = self.mapFromScene(pos)
        self.points.append(local_pos)
        self.path.lineTo(local_pos)
        self.prepareGeometryChange()
        self.boundingRect_ = self.path.boundingRect()
        self.update()

    def set_points(self, points):
        # Set points directly (e.g. from JSON load)
        self.points = points
        self.path = QPainterPath()
        if points:
            self.path.moveTo(points[0])
            for p in points[1:]:
                self.path.lineTo(p)
        self.prepareGeometryChange()
        self.boundingRect_ = self.path.boundingRect()
        self.update()

    def boundingRect(self):
        # Reduced padding from 5 to 2
        return self.boundingRect_.adjusted(-2, -2, 2, 2)

    def shape(self):
        from PyQt6.QtGui import QPainterPathStroker
        s = QPainterPathStroker()
        s.setWidth(10)
        return s.createStroke(self.path)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if (option.state & QStyle.StateFlag.State_Selected) and not self.is_group_selected:
            # Reduced strength: lighter blue, thinner line
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path)

        painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass
        
    def create_json_data(self):
        # Save points relative to item pos
        pts = [[p.x(), p.y()] for p in self.points]
        return {
             "type": "freehand",
             "x": self.pos().x(),
             "y": self.pos().y(),
             "rotation": self.rotation(),
             "points": pts,
             "color": self.pen_color.name(),
             "color": self.pen_color.name(),
             "width": self.pen_width,
             "group_id": self.group_id
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionTextItem(QGraphicsTextItem):
    def __init__(self, text, pos):
        super().__init__(text)
        self.setPos(pos)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setZValue(5)
        self.setFont(QFont("Arial", 25))
        self.setDefaultTextColor(QColor("#222222"))
        self.group_id = None
        self.is_group_selected = False

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path
        
    def sceneEvent(self, event):
        """
        Intercept ShortcutOverride to claim ALL keys when editing
        before they are processed by the main window shortcuts.
        """
        if event.type() == QEvent.Type.ShortcutOverride:
            # If in edit mode, accept ALL shortcuts to prevent them from triggering
            if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
                event.accept()
                return True
        return super().sceneEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFocus()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        # Handle shortcuts explicitly when in edit mode
        if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_B:
                    # Toggle Bold
                    fmt = self.textCursor().charFormat()
                    fmt.setFontWeight(QFont.Weight.Bold if fmt.fontWeight() != QFont.Weight.Bold else QFont.Weight.Normal)
                    self.textCursor().setCharFormat(fmt)
                    return
                elif event.key() == Qt.Key.Key_I:
                    # Toggle Italic
                    fmt = self.textCursor().charFormat()
                    fmt.setFontItalic(not fmt.fontItalic())
                    self.textCursor().setCharFormat(fmt)
                    return
                elif event.key() == Qt.Key.Key_U:
                    # Toggle Underline
                    fmt = self.textCursor().charFormat()
                    fmt.setFontUnderline(not fmt.fontUnderline())
                    self.textCursor().setCharFormat(fmt)
                    return

            if event.key() == Qt.Key.Key_Escape:
                self.clearFocus()
                event.accept()
                return

            # Handle standard editing keys (Enter, etc.) but accept the event
            # so it doesn't leak to MoleculeScene.keyPressEvent
            super().keyPressEvent(event)
            event.accept()
            return
        super().keyPressEvent(event)

    def format_as_chemical(self):
        """Format the text as a chemical formula."""
        import re
        text = self.toPlainText()
        
        # 1. Subscript numbers (not preceded by charge symbols + or -)
        # We process charges first to avoid H2O -> H2 O issue? No, numbers are sub. Charges are sup.
        
        # Charges: (+ or - or 2+, 3-) at the end of groups or line?
        # Simple heuristic: Letter followed by + or - or number then +/-
        # e.g. Cl-, Na+, Ca2+, SO4 2-
        
        # Let's do a robust multi-pass or single pass with callback.
        
        # Use span with vertical-align for better control, especially for SVG export where sub/sup might have large gaps.
        # But QGraphicsTextItem HTML support is limited. 
        # 'vertical-align: sub' is supported.
        # Let's try standard sub/sup first, but if user complained about distance, maybe they mean the vertical offset is too large?
        # Or lateral spacing?
        # A common trick is to use font-size smaller (75%)?
        # Actually, let's stick to <sub> but maybe the font handling in SVG is the culprit.
        # If I use `<sub>` it uses Qt's default sub offset.
        # Let's try using `vertical-align: sub` explicitly on a span?
        # Or maybe the user meant horizontal distance?
        # "sub or sup text get distance" -> "H 2 O".
        # This often happens if the font metrics are weird in SVG.
        
        # I will replace <sub> with <span style='vertical-align:sub;'> which might behave differently?
        # Actually, let's just try to be standard but cleaner.
        
        def replace_sub(match):
            # Using span with vertical-align
            return f"<span style='vertical-align:sub;'>{match.group(1)}</span>"

        def replace_sup(match):
            return f"<span style='vertical-align:super;'>{match.group(1)}</span>"
        #    Hard to distinguish 43- without chemical knowledge. 
        #    BUT user specifically asked "minus cannnot be sup when chem is applied".
        #    Actually user said: "minus cannnot be sup when chem is applied" -> Wait, "minus CANNOT be sup"? 
        #    "also minus cannnot be sup when chem is applied" <- This sounds like a complaint that it IS sup but shouldn't be?
        #    OR "minus cannot be sup" meaning it fails to become sup?
        #    Context: "also the font size is not adjustable. maybe once it sub or sup. also minus cannnot be sup when chem is applied. fix all"
        #    Interpretation: "Minus sign is failing to represent as superscript when chemical formatting is applied" OR "Minus sign IS becoming superscript but shouldn't".
        #    Given "Cl-", it SHOULD be superscript. So likely it is FAILING to be sup.
        #    "minus cannnot be sup" -> "I cannot make minus sup".
        
        new_html = ""
        # Split by potential ions to handle them?
        # Simplest widely accepted regex approach:
        
        # 1. Global number subscripting: ([A-Za-z\)])(\d+) -> $1<sub>$2</sub>
        # 2. Charge Superscripting: ([A-Za-z0-9\)])([+-][1-9]?|[1-9][+-]) -> $1<sup>$2</sup> ??
        #    This is risky.
        
        # Let's try iterating.
        # Common convention for simple sketchers:
        # Numbers after letters -> Sub
        # +/- after letters -> Sup
        
        # Handle "Cl-" -> Cl + sup(-)
        # Handle "Na+" -> Na + sup(+)
        # Handle "Ca2+" -> Ca + sup(2+)
        # Handle "SO42-" -> SO4(sub) + 2-(sup).
        # "SO4" -> S O sub(4).
        
        # Step 1: Subscript all numbers
        # But we need to protect charge numbers.
        # Charge numbers are followed by + or -.
        
        # Regex for Charge: (\d*[+-]) 
        # If we find a number followed by +/- it is a charge -> Sup.
        # If we find a number NOT followed by +/-, it is a count -> Sub.
        
        segments = []
        i = 0
        n = len(text)
        while i < n:
            # Check for Charge Pattern: Single Digit Number + +/- OR just +/-
            # Look ahead
            # Limit charge number to 0 or 1 digit to distinguishing from counts (e.g. SO42-)
            match_charge = re.match(r"^(\d?[+-])", text[i:])
            if match_charge and i > 0: # Charge must follow something
                 # It's a charge (e.g. "+" or "2+" or "3-" or "-")
                 # We assume charges > 9 are very rare in this context.
                 
                 charge_txt = match_charge.group(1)
                 # Ensure it's not part of a hyphenated word like "Co-op" (if text has letters)
                 # But "Co" is Cobalt. "Co-"?
                 # Heuristic: If followed by space, end of string, or punctuation.
                 is_end_of_token = (i + len(charge_txt) == n) or (text[i + len(charge_txt)] in " \t\n,.)]")
                 
                 if is_end_of_token:
                      segments.append(f"<sup>{charge_txt}</sup>")
                      i += len(charge_txt)
                      continue
            
            # Check for Subscript Number: \d+
            match_sub = re.match(r"^(\d+)", text[i:])
            if match_sub and i > 0 and text[i-1].isalpha():
                 # Digits following letter -> Sub
                 # BUT wait, what if it was part of "Ca2+"?
                 # If we missed the charge check above (e.g. 2 is separate from +?),
                 # The charge check `(\d*[+-])` would catch "2+".
                 # If we have "SO4", the "4" is not followed by +/-.
                 # So it matches here.
                 
                 num_txt = match_sub.group(1)
                 segments.append(f"<sub>{num_txt}</sub>")
                 i += len(num_txt)
                 continue
                 
            segments.append(text[i])
            i += 1
            
        new_html = "".join(segments)
        self.setHtml(new_html)

    def focusInEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        super().focusInEvent(event)
        # Disable main window shortcuts to prevent conflicts
        try:
             mw = get_main_window(self.scene())
             if mw and hasattr(mw, '_reaction_mode_manager'):
                 mw._reaction_mode_manager.disable_main_window_shortcuts()
             elif mw and hasattr(mw, 'ui_manager') and hasattr(mw.ui_manager, '_reaction_mode_manager'):
                 mw.ui_manager._reaction_mode_manager.disable_main_window_shortcuts()
        except: pass
        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        try:
            mw = get_main_window(self.scene())
            if mw: mw.push_undo_state()
        except: pass

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Clear selection to avoid confusion
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        
        super().focusOutEvent(event)
        try:
             mw = get_main_window(self.scene())
             if mw: 
                 mw.push_undo_state()
                 if hasattr(mw, '_reaction_mode_manager'):
                     mw._reaction_mode_manager.enable_main_window_shortcuts()
                 elif hasattr(mw, 'ui_manager') and hasattr(mw.ui_manager, '_reaction_mode_manager'):
                     mw.ui_manager._reaction_mode_manager.enable_main_window_shortcuts()
        except: pass

    def paint(self, painter, option, widget):
        # Handle custom selection highlight
        is_selected = (option.state & QStyle.StateFlag.State_Selected)
        if is_selected and not self.is_group_selected:
            # Custom soft blue highlight
            painter.setPen(QPen(QColor(0, 100, 255, 150), 2, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            
            # Remove state so base class doesn't draw the default dashed box
            option.state &= ~QStyle.StateFlag.State_Selected
            
        super().paint(painter, option, widget)

    def create_json_data(self):
        return {
            "type": "text",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "text": self.toPlainText(),
            "html": self.toHtml(),
            "group_id": self.group_id,
            "font_family": self.font().family(),
            "font_size": self.font().pointSize(),
            "bold": self.font().bold(),
            "italic": self.font().italic(),
            "underline": self.font().underline(),
            "color": self.defaultTextColor().name()
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)

class ReactionGroupOverlay(QGraphicsItem):
    """
    A visual overlay that draws a bounding box around a group of items.
    It is NOT selectable or movable itself; it just provides visual feedback
    for the 'Group Selection' state.
    """
    def __init__(self, group_items):
        super().__init__()
        self.group_items = group_items
        # self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemOpensExternalReference) # Removed invalid flag
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(100) # On top of everything
        self._rect = QRectF()
        self._updating = False
        self.update_rect()
        
        self.h_scale = ReactionHandle(self, "scale")
        self.h_scale.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.sync_handles()
        
    def sync_handles(self):
        self.h_scale.setPos(self._rect.bottomRight())

    def on_handle_moved(self, handle):
        if handle.handle_type == "scale":
            # Determine scale factor based on handle movement relative to TopLeft
            # Origin is Rect.topLeft()
            origin = self._rect.topLeft()
            current_br = self._rect.bottomRight()
            new_br = handle.pos()
            
            # Avoid division by zero
            if current_br.x() - origin.x() < 1 or current_br.y() - origin.y() < 1:
                return
                
            scale_x = (new_br.x() - origin.x()) / (current_br.x() - origin.x())
            scale_y = (new_br.y() - origin.y()) / (current_br.y() - origin.y())
            
            # Uniform scale? Use max or average? 
            # User typically expects uniform scale for groups unless it's just resize handles.
            # Let's use uniform scale based on the larger dimension change or projection?
            # Or just update geometry.
            
            scale = max(scale_x, scale_y) # Uniform
            
            # Apply scale to all group items
            # Center of scaling is origin (TopLeft of group box)
            
            for item in self.group_items:
                if not sip_isdeleted_safe(item):
                     # Logic:
                     # NewPos = Origin + (OldPos - Origin) * scale
                     # Item.scale *= scale ??
                     # Items like ArrowItem use start_p, end_p. They don't use Item Transform for geometry usually.
                     # We must update their standard props.
                     
                     # Generic approach: Use duck typing for `scale_by(origin, factor)` if exists,
                     # else manual property updates.
                     
                     if hasattr(item, "start_p") and hasattr(item, "end_p"):
                         item.start_p = origin + (item.start_p - origin) * scale
                         item.end_p = origin + (item.end_p - origin) * scale
                         if hasattr(item, "control_p") and item.control_p:
                              # control_p is local? No, standard ArrowItem uses local coords?
                              # ReactionCurvedArrowItem: control_p is Scene or Local? 
                              # Looking at code: `cp = self.get_control_point()` returns scene/item coords.
                              # It stores `self.control_p` which seems to be absolute based on `mouseMove` logic.
                              # Let's assume absolute for now based on handle setPos.
                              item.control_p = origin + (item.control_p - origin) * scale
                         
                         if hasattr(item, "head_size"):
                             item.head_size *= scale
                         
                         item.sync_handles()
                         item.update()
                         
                     elif hasattr(item, "setBox"): # Future proofing
                         pass
                     elif isinstance(item, QGraphicsTextItem):
                         # Text scaling: Update pos and Font size
                         item.setPos(origin + (item.pos() - origin) * scale)
                         f = item.font()
                         if f.pointSize() > 0:
                             f.setPointSize(int(f.pointSize() * scale))
                         elif f.pixelSize() > 0:
                             f.setPixelSize(int(f.pixelSize() * scale))
                         item.setFont(f)
                         
                     elif hasattr(item, "rect"): # Bracket, Circle
                         # Rect based
                         curr_r = item.rect
                         # TopLeft moves
                         new_tl = origin + (item.mapToScene(curr_r.topLeft()) - origin) * scale
                         new_br = origin + (item.mapToScene(curr_r.bottomRight()) - origin) * scale
                         
                         # Map back to item local if item pos didn't change?
                         # Usually these items are at setPos(start_pos) and rect is local?
                         # Items.py: `ReactionBracketItem`: `self.rect = QRectF(QPointF(0, 0), self.mapFromScene(end_pos))`
                         # It seems `start_pos` is item pos.
                         
                         # Safest: Update item.setPos and item geometry props (width/height)
                         new_pos = origin + (item.pos() - origin) * scale
                         item.setPos(new_pos)
                         
                         # Scale dimensions
                         new_w = curr_r.width() * scale
                         new_h = curr_r.height() * scale
                         item.rect = QRectF(0, 0, new_w, new_h)
                         item.sync_handles()
                         item.update()
                     
                     elif hasattr(item, "points"): # Freehand
                         # Scale points relative to item pos, and scale item pos
                         new_pos = origin + (item.pos() - origin) * scale
                         item.setPos(new_pos)
                         # Points are local
                         item.points = [p * scale for p in item.points]
                         # Rebuild path
                         item.path = QPainterPath()
                         if item.points:
                            item.path.moveTo(item.points[0])
                            for p in item.points[1:]:
                                item.path.lineTo(p)
                         item.prepareGeometryChange()
                         item.update()

                     elif hasattr(item, "size"): # Plus/Minus
                          new_pos = origin + (item.pos() - origin) * scale
                          item.setPos(new_pos)
                          item.size *= scale
                          item.update()

            # Push undo
            try:
                mw = get_main_window(self.scene())
                if mw: mw.push_undo_state()
            except: pass

            # Force overlay update
            self.update_rect()
            self.sync_handles()
        


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
            old_scene = self.scene()
            new_scene = value
            self._disconnect_scene(old_scene)
            self._connect_scene(new_scene)
        return super().itemChange(change, value)
    
    def _connect_scene(self, scene):
        try:
             scene.changed.connect(self.on_scene_changed)
        except: pass
        
    def _disconnect_scene(self, scene):
        try:
             scene.changed.disconnect(self.on_scene_changed)
        except: pass

    def on_scene_changed(self, region):
        if self._updating: return
        self._updating = True
        try:
            self.update_rect()
            if hasattr(self, 'h_scale'):
                self.sync_handles()
        finally:
            self._updating = False

    def update_rect(self):
        r = QRectF()
        for item in self.group_items:
            try:
                if item.scene() == self.scene() and not sip_isdeleted_safe(item):
                    if r.isNull(): r = item.sceneBoundingRect()
                    else: r = r.united(item.sceneBoundingRect())
            except: continue
        
        # Add padding
        new_rect = r.adjusted(-5, -5, 5, 5)
        
        if new_rect != self._rect:
            self.prepareGeometryChange()
            self._rect = new_rect
            # We don't call update() manually, prepareGeometryChange triggers it? 
            # Yes. But since we are inside scene.changed, it might need force?
            # No, allow standard cycle.
        
    def boundingRect(self):
        return self._rect
        
    def paint(self, painter, option, widget):
        # Do NOT call update_rect here.
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Bounding Box
        painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(0, 120, 215, 10)) # Very light blue fill
        painter.drawRect(self._rect)
        
        # Bottom-Right Corner Handle Visual
        handle_size = 8
        handle_rect = QRectF(self._rect.right() - handle_size, self._rect.bottom() - handle_size, handle_size, handle_size)
        painter.setPen(QPen(QColor(0, 120, 215), 1))
        painter.setBrush(QColor(0, 120, 215)) # Solid blue
        painter.drawRect(handle_rect)
        
        painter.restore()

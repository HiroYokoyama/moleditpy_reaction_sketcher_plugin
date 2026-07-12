#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush, QPainter, QPolygonF, QFont, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QEvent, pyqtSignal
import math

from .utils import sip_isdeleted_safe
import logging


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
    if not scene:
        return None
    # Return immediately if view doesn't exist (e.g. during shutdown)
    try:
        views = scene.views()
    except (RuntimeError, AttributeError):
        return None
    if not views:
        return None

    # Get window from the first view
    view = views[0]
    win = view.window()

    # Traverse up to find MainWindow (the one with push_undo_state)
    curr = win
    while curr:
        if hasattr(curr, "push_undo_state"):
            return curr
        curr = curr.parent()

    # Sprint("DEBUG: get_main_window failed to find push_undo_state on", win)
    return None


class ReactionHandle(QGraphicsItem):
    """A square handle for adjusting item geometry."""

    def __init__(self, parent, handle_type):
        super().__init__(parent)
        self.handle_type = (
            handle_type  # "start", "end", "control", "top-left", "bottom-right"
        )
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
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
        s = 24 / 2  # Hit area significantly larger than visual (10)
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
        if getattr(self, "_parent_was_movable", False):
            p = self.parentItem()
            if p:
                p.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Trigger undo push through main window
        mw = get_main_window(self.scene())
        if mw:
            mw.edit_actions_manager.push_undo_state()
            # print(f"DEBUG: ReactionHandle mouseReleaseEvent - mw is None for scene {self.scene()}")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Angle Snapping (30 degrees)
            from PyQt6.QtWidgets import QApplication

            modifiers = QApplication.keyboardModifiers()
            if not (modifiers.value & Qt.KeyboardModifier.AltModifier.value):
                p = self.parentItem()
                if p and self.handle_type in ("start", "end"):
                    # Disable snapping for curved arrows
                    if hasattr(p, "control_p"):
                        return super().itemChange(change, value)

                    pivot = p.end_p if self.handle_type == "start" else p.start_p
                    proposed_pos = value

                    # Axis Constraint (Shift)
                    if modifiers & Qt.KeyboardModifier.ShiftModifier:
                        delta = proposed_pos - pivot
                        if abs(delta.x()) > abs(delta.y()):
                            proposed_pos = QPointF(proposed_pos.x(), pivot.y())
                        else:
                            proposed_pos = QPointF(pivot.x(), proposed_pos.y())

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
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 3
        self.head_size = 25.0  # Updated default
        self.head_angle = 25.0
        self.head_concavity = 0.5
        self.head_style = (
            "chevron"  # "triangle", "barb", "harpoon", "chevron", "chevron_curved"
        )
        self.head_side = -1  # Default to -1 (Up) for harpoon/fish-hook side

        self.group_id = None
        self.is_group_selected = (
            False  # Flag to suppress individual handles/highlight when group-selected
        )
        self.show_handles_in_group = (
            False  # Flag to force show handles even when in group
        )

        self.h_start = ReactionHandle(self, "start")
        self.h_end = ReactionHandle(self, "end")
        self.h_head = ReactionHandle(self, "head_size")
        self.h_concavity = ReactionHandle(
            self, "concavity"
        )  # Square handle for chevron
        self._initializing = True
        self.sync_handles()
        self._initializing = False

    def sync_handles(self):
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        # Position head handle at one of the corners of the arrowhead
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        if self.head_style == "harpoon":
            # Harpoon: barb side depends on head_side
            draw_angle = self.head_angle if self.head_side >= 0 else -self.head_angle
            h_pos = QLineF.fromPolar(self.head_size, angle + 180 + draw_angle).p2()
            self.h_head.setPos(self.end_p + h_pos)
        else:
            h_pos = QLineF.fromPolar(self.head_size, angle + 180 + self.head_angle).p2()
            self.h_head.setPos(self.end_p + h_pos)

        # Position concavity handle
        # Concavity handle position: projected onto centerline
        # self.head_concavity is the fraction of head_len from Tip to Base (1.0 = Flat base)
        # MidBase = Tip + polar(head_size * concavity, angle + 180)
        c_pos = QLineF.fromPolar(self.head_size * self.head_concavity, angle + 180).p2()
        self.h_concavity.setPos(self.end_p + c_pos)
        self.update_handle_visibility()

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            line = QLineF(self.start_p, self.end_p)
            if line.length() < 1:
                return

            handle_line = QLineF(self.end_p, handle.pos())
            self.head_size = max(5, handle_line.length())

            # Calculate angle difference between arrow and handle
            arrow_angle = line.angle()
            handle_angle = handle_line.angle()
            diff = (handle_angle - (arrow_angle + 180)) % 360
            if diff > 180:
                diff -= 360
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

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu()

        # Barb Side Toggle for Harpoons
        flip_side_act = None
        if self.head_style == "harpoon":
            flip_side_act = menu.addAction("Flip Barb Side")

        if not flip_side_act:
            # Maybe generic menu items? (No items needed if not harpoon)
            return

        action = menu.exec(event.screenPos())
        if flip_side_act and action == flip_side_act:
            self.head_side = -self.head_side
            self.sync_handles()
            self.update()
            scene = self.scene()
            if scene and hasattr(scene, "push_undo"):
                scene.push_undo()
            elif scene and scene.views():
                win = scene.views()[0].window()
                if hasattr(win, "push_undo_state"):
                    win.push_undo_state()

    def set_end_pos(self, pos):
        self.prepareGeometryChange()
        self.end_p = self.mapFromScene(pos)
        self.sync_handles()
        self.update()

    def set_rect_size(self, w, h):
        """Set exact width and height by moving end_p relative to start_p."""
        self.prepareGeometryChange()
        dx = self.end_p.x() - self.start_p.x()
        dy = self.end_p.y() - self.start_p.y()
        sigx = 1 if dx >= 0 else -1
        sigy = 1 if dy >= 0 else -1
        self.end_p = QPointF(self.start_p.x() + sigx * w, self.start_p.y() + sigy * h)
        self.sync_handles()
        self.update()

    def update_handle_visibility(self):
        """Update visibility of all handles based on selection and group state."""
        selected = self.isSelected()
        show_h = selected and (
            not self.is_group_selected or getattr(self, "show_handles_in_group", False)
        )

        if getattr(self, "h_start", None) is not None and self.h_start:
            self.h_start.setVisible(show_h)
        if getattr(self, "h_end", None) is not None and self.h_end:
            self.h_end.setVisible(show_h)
        if getattr(self, "h_head", None) is not None and self.h_head:
            self.h_head.setVisible(show_h)
        if getattr(self, "h_concavity", None) is not None and self.h_concavity:
            # Also check head style for concavity
            self.h_concavity.setVisible(
                show_h
                and self.head_style
                in ["chevron", "arrow_eq", "resonance", "chevron_curved"]
            )
        if getattr(self, "h_control", None) is not None and self.h_control:
            self.h_control.setVisible(show_h)
        if getattr(self, "h_br", None) is not None and self.h_br:
            self.h_br.setVisible(show_h)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

    def boundingRect(self):
        # We must include the arrowhead size to avoid clipping
        # Reduced padding from 10 to 2
        extra = self.head_size + self.pen_width + 2
        return (
            QRectF(self.start_p, self.end_p)
            .normalized()
            .adjusted(-extra, -extra, extra, extra)
        )

    def shape(self):
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.lineTo(self.end_p)

        # Stroke the line part
        from PyQt6.QtGui import QPainterPathStroker

        s = QPainterPathStroker()
        s.setWidth(24)  # Increased hit width (from 10 to 24)
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

        # Make selection highlight thicker and more visible
        # Unified highlight: thicker than normal line
        highlight_width = max(10, self.pen_width + 8)

        if option.state & QStyle.StateFlag.State_Selected:
            # Highlight scaled with pen width for better visibility
            # Purple for groups, blue for individuals
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, highlight_width))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return

        # [Fix] Smart Shaft Shortening to prevent tip protrusion
        # The pullback distance scales with pen width
        shorten_len = max(4.0, self.pen_width * 2.0)

        # Only shorten if line is long enough
        if line.length() > shorten_len + 2:
            new_end = line.pointAt(1.0 - shorten_len / line.length())
            line.setP2(new_end)

        painter.drawLine(line)

        angle = line.angle()
        head_len = self.head_size
        head_angle = self.head_angle
        h1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()

        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(QPen(self.pen_color, 1))

        if self.head_style == "triangle":
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2])
            )
        elif self.head_style == "chevron":
            # Chevron: Sharp Concave base
            mid_base = QLineF.fromPolar(
                head_len * self.head_concavity, angle + 180
            ).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        self.end_p,
                        self.end_p + h1,
                        self.end_p + mid_base,
                        self.end_p + h2,
                    ]
                )
            )
        elif self.head_style == "chevron_curved":
            # Chevron: Concave base with curve
            mid_base = QLineF.fromPolar(
                head_len * self.head_concavity, angle + 180
            ).p2()
            path = QPainterPath()
            path.moveTo(self.end_p)
            path.lineTo(self.end_p + h1)
            path.quadTo(self.end_p + mid_base, self.end_p + h2)
            path.lineTo(self.end_p)
            painter.drawPath(path)
        elif self.head_style == "harpoon":
            # Harpoon: barb side depends on head_side
            mid_back = QLineF.fromPolar(
                head_len * math.cos(math.radians(head_angle)), angle + 180
            ).p2()
            if self.head_side >= 0:
                h_pos = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            else:
                h_pos = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos, self.end_p + mid_back])
            )
        else:
            painter.setPen(
                QPen(
                    self.pen_color,
                    self.pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
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
            "head_side": getattr(self, "head_side", 1),
            "group_id": self.group_id,
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
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.setZValue(5)
        self.size = 28  # Updated default
        self.pen_color = QColor("#222222")
        self.pen_width = 3  # Updated default
        self.group_id = None
        self.is_group_selected = False
        self.show_handles_in_group = False

    def shape(self):
        path = QPainterPath()
        s = self.size / 2 + 10  # Large hit area
        path.addRect(QRectF(-s, -s, s * 2, s * 2))
        return path

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, s * 2, s * 2)

    def update_handle_visibility(self):
        """Update visibility - Plus has no separate handles yet."""

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget):
        s = self.size / 2
        # Use thicker unified highlight
        highlight_width = max(10, self.pen_width + 8)

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if self.is_group_selected
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, highlight_width))
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
            painter.drawLine(QPointF(0, -s), QPointF(0, s))

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
        painter.drawLine(QPointF(0, -s), QPointF(0, s))

    def set_size(self, size):
        self.prepareGeometryChange()
        self.size = size
        self.update()

    def create_json_data(self):
        return {
            "type": "plus",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "size": self.size,
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "group_id": self.group_id,
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)


class ReactionMinusItem(QGraphicsItem):
    def __init__(self, pos):
        super().__init__()
        self.setPos(pos)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.setZValue(5)
        self.size = 28  # Updated default
        self.pen_color = QColor("#222222")
        self.pen_width = 3  # Updated default
        self.group_id = None
        self.is_group_selected = False
        self.show_handles_in_group = False

    def shape(self):
        path = QPainterPath()
        s = self.size / 2 + 10
        path.addRect(QRectF(-s, -s, s * 2, s * 2))
        return path

    def boundingRect(self):
        s = self.size / 2 + 5
        return QRectF(-s, -s, s * 2, s * 2)

    def update_handle_visibility(self):
        """Update visibility - Plus has no separate handles yet."""

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget):
        s = self.size / 2
        # Use thicker unified highlight
        highlight_width = max(10, self.pen_width + 8)

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if self.is_group_selected
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, highlight_width))
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(QPointF(-s, 0), QPointF(s, 0))

    def set_size(self, size):
        self.prepareGeometryChange()
        self.size = size
        self.update()

    def create_json_data(self):
        return {
            "type": "minus",
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "size": self.size,
            "color": self.pen_color.name(),
            "width": self.pen_width,
            "group_id": self.group_id,
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)


class ReactionResonanceArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return

        # [Fix] Smart Shortening for Both Ends of Resonance Arrow
        shorten_len = max(4.0, self.pen_width * 2.0)

        if line.length() > shorten_len * 2 + 2:
            new_start = line.pointAt(shorten_len / line.length())
            new_end = line.pointAt(1.0 - shorten_len / line.length())
            line.setP1(new_start)
            line.setP2(new_end)

        painter.drawLine(line)

        angle = line.angle()
        head_len = self.head_size
        head_angle = self.head_angle
        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(QPen(self.pen_color, 1))

        if self.head_style == "triangle":
            # End head
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2])
            )

            # Start head
            h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2()
            h_pos4 = QLineF.fromPolar(head_len, angle - head_angle).p2()
            painter.drawPolygon(
                QPolygonF([self.start_p, self.start_p + h_pos3, self.start_p + h_pos4])
            )
        elif self.head_style == "harpoon":
            # Harpoon: barb side depends on head_side
            # End head
            mid_back_end = QLineF.fromPolar(
                head_len * math.cos(math.radians(head_angle)), angle + 180
            ).p2()
            draw_angle_end = (
                head_angle if self.head_side >= 0 else -self.head_side * head_angle
            )  # Use head_side for end head
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + draw_angle_end).p2()
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + mid_back_end])
            )

            # Start head
            mid_back_start = QLineF.fromPolar(
                head_len * math.cos(math.radians(head_angle)), angle
            ).p2()
            draw_angle_start = (
                head_angle if self.head_side >= 0 else -self.head_side * head_angle
            )  # Use head_side for start head
            h_pos3 = QLineF.fromPolar(head_len, angle + draw_angle_start).p2()
            painter.drawPolygon(
                QPolygonF(
                    [self.start_p, self.start_p + h_pos3, self.start_p + mid_back_start]
                )
            )
        else:
            painter.setPen(
                QPen(
                    self.pen_color,
                    self.pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            # End head
            h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
            h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()

            # Start head
            h_pos3 = QLineF.fromPolar(head_len, angle + head_angle).p2()
            h_pos4 = QLineF.fromPolar(head_len, angle - head_angle).p2()

            if (
                self.head_style == "triangle"
                or self.head_style == "chevron"
                or self.head_style == "harpoon"
            ):
                painter.setBrush(self.pen_color)
                painter.setPen(QPen(self.pen_color, 1))

                # Helper for end head
                def draw_head_poly(tip, p1, p2, angle_base, head_side_val=1):
                    points = [tip, tip + p1]
                    if self.head_style == "chevron":
                        mid = QLineF.fromPolar(
                            head_len * self.head_concavity, angle_base
                        ).p2()
                        points.append(tip + mid)
                    elif self.head_style == "harpoon":
                        # Harpoon: Half head.
                        mid = QLineF.fromPolar(
                            head_len * math.cos(math.radians(head_angle)), angle_base
                        ).p2()
                        # For harpoon, p1 is the barb side, p2 is the other side (not drawn)
                        # The draw_head_poly is generic, but harpoon only uses tip, p1, mid
                        return QPolygonF([tip, tip + p1, tip + mid])

                    points.append(tip + p2)
                    return QPolygonF(points)

                # End Head (Base angle is angle+180)
                # For harpoon, p1 is the barb side.
                draw_angle_end = (
                    head_angle if self.head_side >= 0 else -self.head_side * head_angle
                )
                h_pos1_harpoon_end = QLineF.fromPolar(
                    head_len, angle + 180 + draw_angle_end
                ).p2()
                poly_end = draw_head_poly(
                    self.end_p, h_pos1_harpoon_end, h_pos2, angle + 180, self.head_side
                )
                painter.drawPolygon(poly_end)

                # Start Head (Base angle is angle)
                # h_pos3/4 are vectors from start_p for the start head.
                draw_angle_start = (
                    head_angle if self.head_side >= 0 else -self.head_side * head_angle
                )
                h_pos3_harpoon_start = QLineF.fromPolar(
                    head_len, angle + draw_angle_start
                ).p2()
                poly_start = draw_head_poly(
                    self.start_p, h_pos3_harpoon_start, h_pos4, angle, self.head_side
                )
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
        self.double_arrow_offset = 10.0
        super().__init__(start_pos, end_pos)
        self.head_size = 25.0
        self.head_style = "harpoon"
        self.head_side = 1  # Barb side: 1=Outward, -1=Inward

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        angle = line.angle()
        offset = self.double_arrow_offset
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_start = self.start_p + p_offset
        l1_end = self.end_p + p_offset
        l2_start = self.start_p - p_offset
        l2_end = self.end_p - p_offset

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, 10))
            painter.drawLine(self.start_p, self.end_p)

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.FlatCap,
            )
        )

        # Vertical Shift for head tips: 2px towards center line
        v_inset = 1.0
        v_vec = QLineF.fromPolar(v_inset, angle + 90).p2()

        # Tip positions for drawing heads
        head_tip1 = l1_end - v_vec  # Shift down towards center
        head_tip2 = l2_start + v_vec  # Shift up towards center

        # Pull back from tip to prevent protrusion (Eq Arrow)
        shorten_len = max(4.0, self.pen_width * 2.0)

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
        head_angle = self.head_angle
        painter.setBrush(self.pen_color)
        painter.setPen(QPen(self.pen_color, 1))

        if self.head_style == "triangle":
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            h_pos1b = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
            painter.drawPolygon(
                QPolygonF([head_tip1, head_tip1 + h_pos1, head_tip1 + h_pos1b])
            )

            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            h_pos2b = QLineF.fromPolar(self.head_size, angle + head_angle).p2()
            painter.drawPolygon(
                QPolygonF([head_tip2, head_tip2 + h_pos2, head_tip2 + h_pos2b])
            )

        elif self.head_style == "chevron":
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            h_pos1b = QLineF.fromPolar(self.head_size, angle + 180 + head_angle).p2()
            mid_end = QLineF.fromPolar(
                self.head_size
                * (
                    self.head_concavity
                    if getattr(self, "head_concavity", None) is not None
                    else 0.8
                ),
                angle + 180,
            ).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        head_tip1,
                        head_tip1 + h_pos1,
                        head_tip1 + mid_end,
                        head_tip1 + h_pos1b,
                    ]
                )
            )

            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            h_pos2b = QLineF.fromPolar(self.head_size, angle + head_angle).p2()
            mid_start = QLineF.fromPolar(
                self.head_size
                * (
                    self.head_concavity
                    if getattr(self, "head_concavity", None) is not None
                    else 0.8
                ),
                angle,
            ).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        head_tip2,
                        head_tip2 + h_pos2,
                        head_tip2 + mid_start,
                        head_tip2 + h_pos2b,
                    ]
                )
            )

        elif self.head_style == "harpoon":
            # Harpoon (Outward points - Old logic restored)
            draw_angle = head_angle if self.head_side >= 0 else -head_angle
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - draw_angle).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        head_tip1,
                        head_tip1 + h_pos1,
                        head_tip1
                        + QLineF.fromPolar(self.head_size * 0.6, angle + 180).p2(),
                    ]
                )
            )

            h_pos2 = QLineF.fromPolar(self.head_size, angle - draw_angle).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        head_tip2,
                        head_tip2 + h_pos2,
                        head_tip2 + QLineF.fromPolar(self.head_size * 0.6, angle).p2(),
                    ]
                )
            )
        elif self.head_style == "equilibrium":
            # Map head heads (half harpoons - points Inward as per old equilibrium style)
            v_head = QLineF.fromPolar(self.head_size, angle + 180 + 30).p2()
            painter.drawLine(head_tip1, head_tip1 + v_head)

            v_head_back = QLineF.fromPolar(self.head_size, angle + 30).p2()
            painter.drawLine(head_tip2, head_tip2 + v_head_back)
        else:
            painter.setPen(
                QPen(
                    self.pen_color,
                    self.pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            h_pos1 = QLineF.fromPolar(self.head_size, angle + 180 - head_angle).p2()
            painter.drawLine(head_tip1, head_tip1 + h_pos1)
            h_pos2 = QLineF.fromPolar(self.head_size, angle - head_angle).p2()
            painter.drawLine(head_tip2, head_tip2 + h_pos2)

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        offset = self.double_arrow_offset
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()

        # Internal vertical shift for tips
        v_inset = 1.0
        v_vec = QLineF.fromPolar(v_inset, angle + 90).p2()
        head_tip1 = self.end_p + p_offset - v_vec

        # Position head handle (use outward point for compatibility with old style)
        draw_angle = self.head_angle if self.head_side >= 0 else -self.head_angle
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 - draw_angle).p2()
        self.h_head.setPos(head_tip1 + h_pos)
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        if getattr(self, "h_concavity", None) is not None and self.h_concavity:
            c_pos = QLineF.fromPolar(
                self.head_size
                * (
                    self.head_concavity
                    if getattr(self, "head_concavity", None) is not None
                    else 0.8
                ),
                angle + 180,
            ).p2()
            self.h_concavity.setPos(head_tip1 + c_pos)
            self.h_concavity.setVisible(
                self.isSelected() and self.head_style == "chevron"
            )

    def on_handle_moved(self, handle):
        if self._initializing:
            return
        self.prepareGeometryChange()
        if handle.handle_type == "start":
            self.start_p = handle.pos()
        elif handle.handle_type == "end":
            self.end_p = handle.pos()
        elif handle.handle_type == "head_size":
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            offset = self.double_arrow_offset
            p_offset = QLineF.fromPolar(offset, angle + 90).p2()

            v_inset = 1.0
            v_vec = QLineF.fromPolar(v_inset, angle + 90).p2()
            head_tip1 = self.end_p + p_offset - v_vec

            handle_line = QLineF(head_tip1, handle.pos())
            self.head_size = max(5, handle_line.length())

            # Calculate angle difference
            handle_angle = handle_line.angle()
            diff = (handle_angle - (angle + 180)) % 360
            if diff > 180:
                diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))

        elif handle.handle_type == "concavity":
            line = QLineF(self.start_p, self.end_p)
            angle = line.angle()
            offset = self.double_arrow_offset
            p_offset = QLineF.fromPolar(offset, angle + 90).p2()

            v_inset = 1.0
            v_vec = QLineF.fromPolar(v_inset, angle + 90).p2()
            head_tip1 = self.end_p + p_offset - v_vec

            vec = handle.pos() - head_tip1
            back_vec = QLineF.fromPolar(1.0, angle + 180).p2()
            dp = vec.x() * back_vec.x() + vec.y() * back_vec.y()
            if self.head_size > 0:
                self.head_concavity = max(0.1, min(1.0, dp / self.head_size))
        self.sync_handles()
        self.update()

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_eq"
        data["double_arrow_offset"] = getattr(self, "double_arrow_offset", 4.0)
        return data


class ReactionRetroArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos):
        self.double_arrow_offset = 8.0  # 2x default spacing
        super().__init__(start_pos, end_pos)
        self.head_size = 30.0  # Updated default
        self.head_angle = 45.0

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        angle = line.angle()
        offset = self.double_arrow_offset
        p_offset = QLineF.fromPolar(offset, angle + 90).p2()
        l1_start = self.start_p + p_offset
        l1_end = self.end_p + p_offset
        l2_start = self.start_p - p_offset
        l2_end = self.end_p - p_offset

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, 10))
            painter.drawLine(self.start_p, self.end_p)

        # Retro arrowhead (large triangle)
        head_len = self.head_size
        head_angle = self.head_angle
        # Extended lines into the head for solid connection
        # User requested "longer lines that connect to head"
        base_dist = head_len * math.cos(math.radians(head_angle))

        # Extend well into the head (add 5px) for solid visual connection
        target_dist = base_dist - 5

        back_vec = QLineF.fromPolar(target_dist, angle + 180).p2()

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.FlatCap,
            )
        )
        painter.drawLine(l1_start, l1_end + back_vec)
        painter.drawLine(l2_start, l2_end + back_vec)

        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(QPen(self.pen_color, 1))
        h_pos1 = QLineF.fromPolar(head_len, angle + 180 + head_angle).p2()
        h_pos2 = QLineF.fromPolar(head_len, angle + 180 - head_angle).p2()

        if self.head_style == "triangle":
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + h_pos2])
            )
        elif self.head_style == "chevron":
            mid_back = QLineF.fromPolar(
                head_len * self.head_concavity, angle + 180
            ).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        self.end_p,
                        self.end_p + h_pos1,
                        self.end_p + mid_back,
                        self.end_p + h_pos2,
                    ]
                )
            )
        elif self.head_style == "harpoon":
            mid_back = QLineF.fromPolar(
                head_len * math.cos(math.radians(head_angle)), angle + 180
            ).p2()
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos1, self.end_p + mid_back])
            )
        else:
            painter.setPen(
                QPen(
                    self.pen_color,
                    self.pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(self.end_p, self.end_p + h_pos1)
            painter.drawLine(self.end_p, self.end_p + h_pos2)

    def sync_handles(self):
        line = QLineF(self.start_p, self.end_p)
        angle = line.angle()
        h_pos = QLineF.fromPolar(self.head_size, angle + 180 - self.head_angle).p2()
        self.h_head.setPos(self.end_p + h_pos)
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        if getattr(self, "h_concavity", None) is not None and self.h_concavity:
            c_pos = QLineF.fromPolar(
                self.head_size * self.head_concavity, angle + 180
            ).p2()
            self.h_concavity.setPos(self.end_p + c_pos)
            self.h_concavity.setVisible(
                self.isSelected() and self.head_style == "chevron"
            )

    def on_handle_moved(self, handle):
        if self._initializing:
            return
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
            if diff > 180:
                diff -= 360
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
        self.negation_style = "slash"  # "slash", "cross"
        self.cross_size = 15.0

    def paint(self, painter, option, widget):
        is_selected = option.state & QStyle.StateFlag.State_Selected
        if is_selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, 10))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(self.start_p, self.end_p)
            option.state &= ~QStyle.StateFlag.State_Selected

        super().paint(painter, option, widget)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QLineF(self.start_p, self.end_p)
        if line.length() < 10:
            return
        mid = line.center()
        angle = line.angle()
        slash_len = self.cross_size

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
        data["cross_size"] = getattr(self, "cross_size", 15.0)
        return data


class ReactionDashedArrowItem(ReactionArrowItem):
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.drawLine(self.start_p, self.end_p)

        # Dashed Pen
        pen = QPen(
            self.pen_color,
            self.pen_width,
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)

        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return

        # [Fix] Smart Shortening for Dashed Arrow
        shorten_len = max(4.0, self.pen_width * 2.0)

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
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h1, self.end_p + h2])
            )
        elif self.head_style == "chevron":
            # Chevron: Sharp Concave base
            mid_base = QLineF.fromPolar(
                head_len * self.head_concavity, angle + 180
            ).p2()
            painter.drawPolygon(
                QPolygonF(
                    [
                        self.end_p,
                        self.end_p + h1,
                        self.end_p + mid_base,
                        self.end_p + h2,
                    ]
                )
            )
        elif self.head_style == "chevron_curved":
            # Chevron: Concave base with curve
            mid_base = QLineF.fromPolar(
                head_len * self.head_concavity, angle + 180
            ).p2()
            path = QPainterPath()
            path.moveTo(self.end_p)
            path.lineTo(self.end_p + h1)
            path.quadTo(self.end_p + mid_base, self.end_p + h2)
            path.lineTo(self.end_p)
            painter.drawPath(path)
        elif self.head_style == "harpoon":
            mid_back = QLineF.fromPolar(
                head_len * math.cos(math.radians(head_angle)), angle + 180
            ).p2()
            draw_angle = head_angle if self.head_side >= 0 else -head_angle
            h_pos = QLineF.fromPolar(head_len, angle + 180 + draw_angle).p2()
            painter.drawPolygon(
                QPolygonF([self.end_p, self.end_p + h_pos, self.end_p + mid_back])
            )
        else:
            painter.setPen(
                QPen(
                    self.pen_color,
                    self.pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(self.end_p, self.end_p + h1)
            painter.drawLine(self.end_p, self.end_p + h2)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "arrow_dashed"
        return data


class ReactionCurvedArrowItem(ReactionArrowItem):
    def __init__(self, start_pos, end_pos, is_fish_hook=False):
        self.is_fish_hook = is_fish_hook
        self.head_style = "chevron"  # Default to chevron
        self.control_p = None  # Local coordinates
        self.h_control = None
        self.curvature = 0.4  # Default curvature (fixed from 4.0)
        self.head_at = "end"  # "start" or "end"
        self.head_side = 1  # 1 or -1 for fish-hook side
        self.group_id = None
        super().__init__(start_pos, end_pos)
        self.h_control = ReactionHandle(self, "control")

        self._initializing = True
        self.sync_handles()
        self.h_control.setVisible(self.isSelected())
        self._initializing = False

    def sync_handles(self):
        if self._initializing:
            return
        self._initializing = True
        try:
            # Specific sync for curved arrow to use tangent angle for head handle
            self.h_start.setPos(self.start_p)
            self.h_end.setPos(self.end_p)

            cp = self.get_control_point()
            if self.head_at == "start":
                tip_p = self.start_p
                base_p = cp
            else:
                tip_p = self.end_p
                base_p = cp

            angle = QLineF(base_p, tip_p).angle()
            # Use head_side for half-head handle placement
            draw_angle = (
                self.head_angle
                if (not self.is_fish_hook or self.head_side >= 0)
                else -self.head_angle
            )
            h_pos = QLineF.fromPolar(self.head_size, angle + 180 + draw_angle).p2()
            self.h_head.setPos(tip_p + h_pos)

            if getattr(self, "h_control", None) is not None and self.h_control:
                self.h_control.setPos(cp)

            if getattr(self, "h_concavity", None) is not None and self.h_concavity:
                c_pos = QLineF.fromPolar(
                    self.head_size * self.head_concavity, angle + 180
                ).p2()
                self.h_concavity.setPos(self.end_p + c_pos)
                self.h_concavity.setVisible(
                    self.isSelected() and self.head_style == "chevron"
                )
        finally:
            self._initializing = False

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
            if diff > 180:
                diff -= 360
            self.head_angle = max(5, min(80, abs(diff)))

        elif handle.handle_type == "concavity":
            cp = self.get_control_point()
            angle = QLineF(cp, self.end_p).angle()
            vec = handle.pos() - self.end_p
            back_vec = QLineF.fromPolar(1.0, angle + 180).p2()
            dp = vec.x() * back_vec.x() + vec.y() * back_vec.y()
            if self.head_size > 0:
                self.head_concavity = max(0.1, min(1.0, dp / self.head_size))
        self.sync_handles()  # Ensure handle syncs back correctly
        self.update()

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu()
        # flip_pos_act = menu.addAction("Flip Head Position") # Disabled by user request
        flip_side_act = None
        if self.is_fish_hook:
            flip_side_act = menu.addAction("Flip Side (Up/Down)")

        action = menu.exec(event.screenPos())
        # if action == flip_pos_act:
        #     self.head_at = "start" if self.head_at == "end" else "end"
        #     self.sync_handles()
        #     self.update()
        #     scene = self.scene()
        #     if scene and hasattr(scene, "push_undo"): scene.push_undo()
        if flip_side_act and action == flip_side_act:
            self.head_side = -self.head_side
            self.sync_handles()
            self.update()
            scene = self.scene()
            if scene and hasattr(scene, "push_undo"):
                scene.push_undo()

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
            self.update_handle_visibility()
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
        s.setWidth(24)  # Increased from 12
        stroked = s.createStroke(path)

        # Add arrowhead for hit detection
        if self.__class__.__name__ != "ReactionCurvedLineItem":
            arrow_path = QPainterPath()  # Initialize arrow_path here
            if self.head_at == "start":
                tip_p = self.start_p
                base_p = cp
            else:
                tip_p = self.end_p
                base_p = cp

            angle = QLineF(base_p, tip_p).angle()
            head_len = self.head_size

            if self.is_fish_hook:
                draw_angle = (
                    self.head_angle if self.head_side >= 0 else -self.head_angle
                )
                h1 = QLineF.fromPolar(head_len, angle + 180 + draw_angle).p2()
                # Fish hook is a line, but for shape we can make it a polygon or stroke
                arrow_path.moveTo(tip_p)
                arrow_path.lineTo(tip_p + h1)
                # Stroke it to make it clickable
                stroked_arrow = s.createStroke(arrow_path)
                stroked.addPath(stroked_arrow)
            else:
                h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
                h2 = QLineF.fromPolar(head_len, angle + 180 - self.head_angle).p2()

                if self.head_style == "triangle":
                    arrow_path.addPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + h2]))
                elif self.head_style == "chevron":
                    mid_base = QLineF.fromPolar(
                        head_len * self.head_concavity, angle + 180
                    ).p2()
                    arrow_path.addPolygon(
                        QPolygonF([tip_p, tip_p + h1, tip_p + mid_base, tip_p + h2])
                    )
                elif self.head_style == "chevron_curved":
                    mid_base = QLineF.fromPolar(
                        head_len * self.head_concavity, angle + 180
                    ).p2()
                    arrow_path.moveTo(tip_p)
                    arrow_path.lineTo(tip_p + h1)
                    arrow_path.quadTo(tip_p + mid_base, tip_p + h2)
                    arrow_path.lineTo(tip_p)
                elif self.head_style == "harpoon":
                    # Use self.head_angle for consistency
                    mid_back = QLineF.fromPolar(
                        head_len * math.cos(math.radians(self.head_angle)), angle + 180
                    ).p2()
                    arrow_path.addPolygon(
                        QPolygonF([tip_p, tip_p + h1, tip_p + mid_back])
                    )
                else:
                    # Open/Barb
                    arrow_path.moveTo(tip_p)
                    arrow_path.lineTo(tip_p + h1)
                    arrow_path.moveTo(tip_p)
                    arrow_path.lineTo(tip_p + h2)
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
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)  # Ensure curve isn't filled
        # [Fix] Smart Shortening for Curved Arrow (More aggressive for curved arrows)
        shorten_len = max(6.0, self.pen_width * 3.0)
        if self.is_fish_hook:
            shorten_len = 0

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

                    p0 = self.start_p
                    p1 = cp
                    p2 = self.end_p

                    # Extend curve to 99.5% for full connection to arrowhead
                    t_cut = 0.995

                    q1 = p0 * (1 - t_cut) + p1 * t_cut
                    q2 = (
                        (p0 * ((1 - t_cut) ** 2))
                        + (p1 * (2 * (1 - t_cut) * t_cut))
                        + (p2 * (t_cut**2))
                    )

                    short_path = QPainterPath()
                    short_path.moveTo(p0)
                    short_path.quadTo(q1, q2)
                    draw_path = short_path

        painter.drawPath(draw_path)

        # Arrowhead logic
        if self.head_at == "start":
            tip_p = self.start_p
            base_p = cp
        else:
            tip_p = self.end_p
            base_p = cp

        # Calculate angle at the end point (tangent to the curve)
        angle = QLineF(base_p, tip_p).angle()
        head_len = self.head_size

        painter.setBrush(QBrush(self.pen_color))
        painter.setPen(QPen(self.pen_color, 1))

        if self.is_fish_hook:
            # Half arrowhead - support all styles
            draw_angle = self.head_angle if self.head_side >= 0 else -self.head_angle
            h1 = QLineF.fromPolar(head_len, angle + 180 + draw_angle).p2()

            painter.setBrush(QBrush(self.pen_color))

            if self.head_style == "triangle":
                # Simple filled triangle (half)
                mid_back = QLineF.fromPolar(
                    head_len * math.cos(math.radians(self.head_angle)), angle + 180
                ).p2()
                painter.drawPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + mid_back]))
            elif self.head_style == "chevron":
                # Chevron style (half) - use concavity
                mid_base = QLineF.fromPolar(
                    head_len * self.head_concavity, angle + 180
                ).p2()
                painter.drawPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + mid_base]))
            elif self.head_style == "chevron_curved":
                # Curved chevron (half)
                mid_base = QLineF.fromPolar(
                    head_len * self.head_concavity, angle + 180
                ).p2()
                path = QPainterPath()
                path.moveTo(tip_p)
                path.lineTo(tip_p + h1)
                path.quadTo(tip_p + mid_base, tip_p)
                painter.drawPath(path)
            elif self.head_style == "harpoon":
                # Harpoon is inherently asymmetric, same as triangle
                mid_back = QLineF.fromPolar(
                    head_len * math.cos(math.radians(self.head_angle)), angle + 180
                ).p2()
                painter.drawPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + mid_back]))
            else:
                # Open / Barb (no fill) - just a line
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(tip_p, tip_p + h1)
        else:
            # Full arrowhead
            h1 = QLineF.fromPolar(head_len, angle + 180 + self.head_angle).p2()
            h2 = QLineF.fromPolar(head_len, angle + 180 - self.head_angle).p2()

            # Use Brush for filled shapes
            painter.setBrush(QBrush(self.pen_color))

            if self.head_style == "triangle":
                painter.drawPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + h2]))
            elif self.head_style == "chevron":
                mid_base = QLineF.fromPolar(
                    head_len * self.head_concavity, angle + 180
                ).p2()
                painter.drawPolygon(
                    QPolygonF([tip_p, tip_p + h1, tip_p + mid_base, tip_p + h2])
                )
            elif self.head_style == "chevron_curved":
                mid_base = QLineF.fromPolar(
                    head_len * self.head_concavity, angle + 180
                ).p2()
                path = QPainterPath()
                path.moveTo(tip_p)
                path.lineTo(tip_p + h1)
                path.quadTo(tip_p + mid_base, tip_p + h2)
                path.lineTo(tip_p)
                painter.drawPath(path)
            elif self.head_style == "harpoon":
                mid_back = QLineF.fromPolar(
                    head_len * math.cos(math.radians(self.head_angle)), angle + 180
                ).p2()
                painter.drawPolygon(QPolygonF([tip_p, tip_p + h1, tip_p + mid_back]))
            else:
                # Open / Barb (no fill)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(tip_p, tip_p + h1)
                painter.drawLine(tip_p, tip_p + h2)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "curved_fish" if self.is_fish_hook else "curved_double"
        data["head_style"] = self.head_style
        data["curvature"] = float(self.curvature)
        data["head_at"] = self.head_at
        data["head_side"] = self.head_side

        cp = self.get_control_point()
        data["cp_x"] = cp.x()
        data["cp_y"] = cp.y()

        if self.control_p:
            data["control_p"] = [self.control_p.x(), self.control_p.y()]

        data["group_id"] = self.group_id
        return data


class ReactionBracketItem(QGraphicsItem):
    def __init__(self, start_pos, end_pos):
        super().__init__()
        self.setPos(start_pos)
        self.rect = QRectF(QPointF(0, 0), self.mapFromScene(end_pos))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.bracket_type = "square"  # "square", "round", "curly"
        self.line_style = "solid"  # "solid", "dashed"

        self.h_br = ReactionHandle(self, "bottom-right")
        self._initializing = True
        self.group_id = None
        self.is_group_selected = False
        self.show_handles_in_group = False
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

    def set_rect_size(self, w, h):
        self.prepareGeometryChange()
        self.rect = QRectF(0, 0, w, h)
        self.sync_handles()
        self.update()

    def update_handle_visibility(self):
        selected = self.isSelected()
        show_h = selected and (
            not self.is_group_selected or getattr(self, "show_handles_in_group", False)
        )
        if getattr(self, "h_br", None) is not None and self.h_br:
            self.h_br.setVisible(show_h)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

    def boundingRect(self):
        # Reduced padding from 10 to 2
        return self.rect.normalized().adjusted(-2, -2, 2, 2)

    def shape(self):
        path = QPainterPath()
        r = self.rect.normalized()

        if self.bracket_type == "round":
            bw = min(r.width() / 2, 20)
            # Use arcMoveTo + arcTo for disjoint arcs in shape path
            path.arcMoveTo(QRectF(r.left(), r.top(), bw, r.height()), 90)
            path.arcTo(QRectF(r.left(), r.top(), bw, r.height()), 90, 180)  # Left

            path.arcMoveTo(QRectF(r.right() - bw, r.top(), bw, r.height()), -90)
            path.arcTo(
                QRectF(r.right() - bw, r.top(), bw, r.height()), -90, 180
            )  # Right

        elif self.bracket_type == "curly":
            bw = 15
            x, y, w, h = r.x(), r.y(), r.width(), r.height()

            # Left {
            p_l = QPainterPath()
            p_l.moveTo(x + bw, y)
            p_l.quadTo(x, y, x, y + h * 0.25)
            p_l.lineTo(x, y + h * 0.5 - 5)
            p_l.lineTo(x - 5, y + h * 0.5)
            p_l.lineTo(x, y + h * 0.5 + 5)
            p_l.lineTo(x, y + h * 0.75)
            p_l.quadTo(x, y + h, x + bw, y + h)
            path.addPath(p_l)

            # Right }
            p_r = QPainterPath()
            rx = x + w
            p_r.moveTo(rx - bw, y)
            p_r.quadTo(rx, y, rx, y + h * 0.25)
            p_r.lineTo(rx, y + h * 0.5 - 5)
            p_r.lineTo(rx + 5, y + h * 0.5)
            p_r.lineTo(rx, y + h * 0.5 + 5)
            p_r.lineTo(rx, y + h * 0.75)
            p_r.quadTo(rx, y + h, rx - bw, y + h)
            path.addPath(p_r)

        else:  # Square
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
        stroker.setWidth(24)  # Hit tolerance increased from 10
        return stroker.createStroke(path)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        pen = QPen(self.pen_color, self.pen_width)
        if self.line_style == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, self.pen_width + 8))
            # Draw a soft highlight rect too? No, stay on the lines.

        # Check if single-sided
        draw_left = True
        draw_right = True
        bracket_base_type = self.bracket_type

        if "_left" in self.bracket_type:
            draw_right = False
            bracket_base_type = self.bracket_type.replace("_left", "")
        elif "_right" in self.bracket_type:
            draw_left = False
            bracket_base_type = self.bracket_type.replace("_right", "")

        if bracket_base_type == "round":
            # Round Brackets (Parentheses)
            bw = min(r.width() / 2, 20)
            if draw_left:
                painter.drawArc(
                    QRectF(r.left(), r.top(), bw, r.height()), 90 * 16, 180 * 16
                )
            if draw_right:
                painter.drawArc(
                    QRectF(r.right() - bw, r.top(), bw, r.height()), -90 * 16, 180 * 16
                )

        elif bracket_base_type == "curly":
            # Curly Braces { }
            bw = 15
            x, y, w, h = r.x(), r.y(), r.width(), r.height()

            if draw_left:
                # Left {
                p = QPainterPath()
                p.moveTo(x + bw, y)
                p.quadTo(x, y, x, y + h * 0.25)
                p.lineTo(x, y + h * 0.5 - 5)
                p.lineTo(x - 5, y + h * 0.5)
                p.lineTo(x, y + h * 0.5 + 5)
                p.lineTo(x, y + h * 0.75)
                p.quadTo(x, y + h, x + bw, y + h)
                painter.drawPath(p)

            if draw_right:
                # Right }
                p = QPainterPath()
                rx = x + w
                p.moveTo(rx - bw, y)
                p.quadTo(rx, y, rx, y + h * 0.25)
                p.lineTo(rx, y + h * 0.5 - 5)
                p.lineTo(rx + 5, y + h * 0.5)
                p.lineTo(rx, y + h * 0.5 + 5)
                p.lineTo(rx, y + h * 0.75)
                p.quadTo(rx, y + h, rx - bw, y + h)
                painter.drawPath(p)

        else:  # Square
            bw = 8
            if draw_left:
                # Left [
                painter.drawLine(r.topLeft() + QPointF(bw, 0), r.topLeft())
                painter.drawLine(r.topLeft(), r.bottomLeft())
                painter.drawLine(r.bottomLeft(), r.bottomLeft() + QPointF(bw, 0))

            if draw_right:
                # Right ]
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
            "group_id": self.group_id,
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
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.setZValue(4)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.shape_type = "rectangle"  # "circle", "rectangle"
        self.line_style = "solid"  # "dashed", "solid"
        self.fill_color = None  # None/transparent = outline-only (click-through)

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

    def set_rect_size(self, w, h):
        self.prepareGeometryChange()
        self.rect = QRectF(0, 0, w, h)
        self.sync_handles()
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.h_br.setVisible(bool(value) and not self.is_group_selected)
        return super().itemChange(change, value)

    def boundingRect(self):
        return self.rect.normalized().adjusted(-5, -5, 5, 5)

    def _outline_path(self):
        r = self.rect.normalized()
        path = QPainterPath()
        if self.shape_type == "rectangle":
            path.addRect(r)
        else:
            path.addEllipse(r)
        return path

    def shape(self):
        from PyQt6.QtGui import QPainterPathStroker

        path = self._outline_path()

        # If the frame is filled with an opaque colour, its whole interior is a
        # legitimate click/selection target. When it is just an outline (the
        # default), only the border should be hit-testable so that
        # double-clicking a molecule drawn *inside* the frame selects the
        # molecule rather than the surrounding rectangle/circle.
        fill = getattr(self, "fill_color", None)
        if fill is not None and QColor(fill).alpha() > 0:
            return path

        stroker = QPainterPathStroker()
        stroker.setWidth(max(12, self.pen_width + 10))
        return stroker.createStroke(path)

    def paint(self, painter, option, widget):
        r = self.rect.normalized()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill = getattr(self, "fill_color", None)
        if fill is not None and QColor(fill).alpha() > 0:
            painter.setBrush(QBrush(QColor(fill)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        pen_style = (
            Qt.PenStyle.DashLine
            if self.line_style == "dashed"
            else Qt.PenStyle.SolidLine
        )
        painter.setPen(QPen(self.pen_color, self.pen_width, pen_style))

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if self.is_group_selected
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, self.pen_width + 8, pen_style))

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
            "fill_color": (
                QColor(self.fill_color).name(QColor.NameFormat.HexArgb)
                if getattr(self, "fill_color", None) is not None
                else None
            ),
            "group_id": self.group_id,
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)


class ReactionLineItem(ReactionArrowItem):
    """Straight line without arrowheads."""

    def __init__(self, start_pos, end_pos):
        super().__init__(start_pos, end_pos)
        self.line_style = "solid"  # "solid", "dashed"

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.drawLine(self.start_p, self.end_p)

        style = (
            Qt.PenStyle.DashLine
            if self.line_style == "dashed"
            else Qt.PenStyle.SolidLine
        )
        painter.setPen(
            QPen(self.pen_color, self.pen_width, style, Qt.PenCapStyle.RoundCap)
        )

        line = QLineF(self.start_p, self.end_p)
        if line.length() < 1:
            return
        painter.drawLine(line)

    def sync_handles(self):
        """Override to remove arrow head handle for lines."""
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        # Hide head and concavity handles since this is a line, not arrow
        if getattr(self, "h_head", None) is not None and self.h_head:
            self.h_head.setVisible(False)
        if getattr(self, "h_concavity", None) is not None and self.h_concavity:
            self.h_concavity.setVisible(False)

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
            "group_id": self.group_id,
        }


class ReactionCurvedLineItem(ReactionCurvedArrowItem):
    """Curved line without arrowheads."""

    def __init__(self, start_pos, end_pos):
        super().__init__(start_pos, end_pos)
        self.line_style = "solid"

    def sync_handles(self):
        """Override to remove arrow head handle for lines."""
        self.h_start.setPos(self.start_p)
        self.h_end.setPos(self.end_p)

        # Only show control point handle, NO head handle
        if getattr(self, "h_control", None) is not None and self.h_control:
            cp = self.get_control_point()
            self.h_control.setPos(cp)

        # Hide head and concavity handles since this is a line, not arrow
        if getattr(self, "h_head", None) is not None and self.h_head:
            self.h_head.setVisible(False)
        if getattr(self, "h_concavity", None) is not None and self.h_concavity:
            self.h_concavity.setVisible(False)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cp = self.get_control_point()
        path = QPainterPath()
        path.moveTo(self.start_p)
        path.quadTo(cp, self.end_p)

        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        style = (
            Qt.PenStyle.DashLine
            if self.line_style == "dashed"
            else Qt.PenStyle.SolidLine
        )
        painter.setPen(
            QPen(self.pen_color, self.pen_width, style, Qt.PenCapStyle.RoundCap)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def create_json_data(self):
        data = super().create_json_data()
        data["type"] = "line_curved"
        data["line_style"] = self.line_style
        # Override head_style to None or remove it? JSON loader will need "type"
        if "head_style" in data:
            del data["head_style"]
        if "head_angle" in data:
            del data["head_angle"]
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
        self.setPos(start_pos)
        self.points = [QPointF(0, 0)]
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        self.setZValue(5)
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.path = QPainterPath()
        self.path.moveTo(0, 0)
        self.boundingRect_ = QRectF(0, 0, 1, 1)
        self.group_id = None
        self.is_group_selected = False
        self.show_handles_in_group = False

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

    def set_rect_size(self, w, h):
        """Scale all points to fit the requested width and height."""
        if not self.points:
            return
        br = self.path.boundingRect()
        if br.width() == 0 or br.height() == 0:
            return

        scale_x = w / br.width()
        scale_y = h / br.height()

        self.prepareGeometryChange()
        new_points = []
        origin = br.topLeft()
        for p in self.points:
            # Scale relative to bounding box top-left
            nx = origin.x() + (p.x() - origin.x()) * scale_x
            ny = origin.y() + (p.y() - origin.y()) * scale_y
            new_points.append(QPointF(nx, ny))

        self.set_points(new_points)

    def boundingRect(self):
        # Reduced padding from 5 to 2
        return self.boundingRect_.adjusted(-2, -2, 2, 2)

    def update_handle_visibility(self):
        """Freehand has no separate handles yet."""

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

    def shape(self):
        from PyQt6.QtGui import QPainterPathStroker

        s = QPainterPathStroker()
        s.setWidth(24)  # Increased from 10
        return s.createStroke(self.path)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            highlight_color = (
                QColor(130, 100, 255, 120)
                if self.is_group_selected
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(QPen(highlight_color, max(10, self.pen_width + 8)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path)

        painter.setPen(
            QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path)

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
            "width": self.pen_width,
            "group_id": self.group_id,
        }

    def rotate_around(self, center, angle_degrees):
        new_pos = rotate_point(self.pos(), center, angle_degrees)
        self.setPos(new_pos)
        self.setRotation(self.rotation() + angle_degrees)


class ReactionTextItem(QGraphicsTextItem):
    # Signal for UI updates
    cursorChanged = pyqtSignal()

    def __init__(self, text, pos):
        super().__init__(text)
        self.setPos(pos)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )  # Start as object
        self.setZValue(5)
        self.setFont(QFont("Arial", 25))
        self.setDefaultTextColor(QColor("#222222"))
        self.group_id = None
        self.is_group_selected = False
        self.show_handles_in_group = False

        # Connect document cursor change to our signal
        self.document().cursorPositionChanged.connect(self._on_cursor_changed)

    def _on_cursor_changed(self, cursor):
        self.cursorChanged.emit()

    def mousePressEvent(self, event):
        # If in edit mode, consume event to prevent scene drag
        if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
            self.setFocus()
            super().mousePressEvent(event)
            event.accept()  # STOP propagation
        else:
            # Not in edit mode - allow normal selection/movement
            super().mousePressEvent(event)
        self.is_group_selected = False

    def update_handle_visibility(self):
        """Text has no separate handles yet."""

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handle_visibility()
        return super().itemChange(change, value)

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
            if (
                self.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                event.accept()
                return True
        return super().sceneEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            # Enable BOTH TextEditorInteraction AND TextSelectableByMouse for proper mouse selection
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextEditorInteraction
                | Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.setFocus()

            # Disable Movable flag so we don't drag the item while selecting text
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

            # Disable main window shortcuts to prevent conflicts
            try:
                mw = get_main_window(self.scene())
                if mw:
                    if hasattr(mw, "_reaction_mode_manager"):
                        mw._reaction_mode_manager.disable_main_window_shortcuts()
                    elif hasattr(mw, "ui_manager") and hasattr(
                        mw.ui_manager, "_reaction_mode_manager"
                    ):
                        mw.ui_manager._reaction_mode_manager.disable_main_window_shortcuts()
            except (RuntimeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

            # Set cursor to click position
            # QGraphicsTextItem doesn't have cursorForPosition. Use document layout.
            cursor_pos = (
                self.document()
                .documentLayout()
                .hitTest(event.pos(), Qt.HitTestAccuracy.FuzzyHit)
            )
            cursor = self.textCursor()
            cursor.setPosition(cursor_pos)
            self.setTextCursor(cursor)

            # FIX: Accept event and return to prevent default selection (word/sentence)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Restore Movable flag
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Auto-delete if empty
        if not self.toPlainText().strip():
            self.scene().removeItem(self)
            return

        # Clear selection to avoid confusion
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

        super().focusOutEvent(event)
        if self.scene() and hasattr(self.scene(), "on_text_edited"):
            self.scene().on_text_edited(self)
        try:
            mw = get_main_window(self.scene())
            if mw:
                mw.edit_actions_manager.push_undo_state()
                if hasattr(mw, "_reaction_mode_manager"):
                    mw._reaction_mode_manager.enable_main_window_shortcuts()
                elif hasattr(mw, "ui_manager") and hasattr(
                    mw.ui_manager, "_reaction_mode_manager"
                ):
                    mw.ui_manager._reaction_mode_manager.enable_main_window_shortcuts()
        except (RuntimeError, AttributeError) as _e:
            logging.warning("silenced: %s", _e)

    @property
    def size(self):
        return self.font().pointSize()

    @size.setter
    def size(self, value):
        f = self.font()
        f.setPointSize(int(value))
        self.setFont(f)
        self.update()

    def set_size(self, value):
        self.size = value

    def keyPressEvent(self, event):
        # Handle shortcuts explicitly when in edit mode
        if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
            # Short-circuit: require Control modifier for formatting shortcuts
            has_ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

            if has_ctrl and event.key() == Qt.Key.Key_B:
                # Toggle Bold via ModeManager (Undo + Logic)
                try:
                    mw = get_main_window(self.scene())
                    if mw and hasattr(mw, "_reaction_mode_manager"):
                        mw._reaction_mode_manager.apply_text_style("bold")
                    elif (
                        mw
                        and hasattr(mw, "ui_manager")
                        and hasattr(mw.ui_manager, "_reaction_mode_manager")
                    ):
                        mw.ui_manager._reaction_mode_manager.apply_text_style("bold")
                except (RuntimeError, AttributeError) as _e:
                    logging.warning("silenced: %s", _e)
                event.accept()
                return
            elif has_ctrl and event.key() == Qt.Key.Key_I:
                # Toggle Italic
                try:
                    mw = get_main_window(self.scene())
                    if mw and hasattr(mw, "_reaction_mode_manager"):
                        mw._reaction_mode_manager.apply_text_style("italic")
                    elif (
                        mw
                        and hasattr(mw, "ui_manager")
                        and hasattr(mw.ui_manager, "_reaction_mode_manager")
                    ):
                        mw.ui_manager._reaction_mode_manager.apply_text_style("italic")
                except (RuntimeError, AttributeError) as _e:
                    logging.warning("silenced: %s", _e)
                event.accept()
                return
            elif has_ctrl and event.key() == Qt.Key.Key_U:
                # Toggle Underline
                try:
                    mw = get_main_window(self.scene())
                    if mw and hasattr(mw, "_reaction_mode_manager"):
                        mw._reaction_mode_manager.apply_text_style("underline")
                    elif (
                        mw
                        and hasattr(mw, "ui_manager")
                        and hasattr(mw.ui_manager, "_reaction_mode_manager")
                    ):
                        mw.ui_manager._reaction_mode_manager.apply_text_style(
                            "underline"
                        )
                except (RuntimeError, AttributeError) as _e:
                    logging.warning("silenced: %s", _e)
                event.accept()
                return
            elif has_ctrl and (
                event.key() == Qt.Key.Key_Equal or event.key() == Qt.Key.Key_Plus
            ):
                # Subscript/Superscript (Ctrl+= or Ctrl+Shift+=)
                try:
                    mw = get_main_window(self.scene())
                    if mw and hasattr(mw, "_reaction_mode_manager"):
                        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                            mw._reaction_mode_manager.toggle_superscript()
                        else:
                            mw._reaction_mode_manager.toggle_subscript()
                    elif (
                        mw
                        and hasattr(mw, "ui_manager")
                        and hasattr(mw.ui_manager, "_reaction_mode_manager")
                    ):
                        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                            mw.ui_manager._reaction_mode_manager.toggle_superscript()
                        else:
                            mw.ui_manager._reaction_mode_manager.toggle_subscript()
                except (RuntimeError, AttributeError) as _e:
                    logging.warning("silenced: %s", _e)
                event.accept()
                return

            if event.key() == Qt.Key.Key_Escape:
                self.clearFocus()
                try:
                    mw = get_main_window(self.scene())
                    if mw and hasattr(mw, "_reaction_mode_manager"):
                        # Trigger select tool action
                        for action in mw._reaction_mode_manager.action_group.actions():
                            if action.property("tool_name") == "select":
                                action.trigger()
                                break
                    elif (
                        mw
                        and hasattr(mw, "ui_manager")
                        and hasattr(mw.ui_manager, "_reaction_mode_manager")
                    ):
                        for action in (
                            mw.ui_manager._reaction_mode_manager.action_group.actions()
                        ):
                            if action.property("tool_name") == "select":
                                action.trigger()
                                break
                except (RuntimeError, AttributeError) as _e:
                    logging.warning("silenced: %s", _e)

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
        from PyQt6.QtGui import QTextCursor, QTextCharFormat

        # Helper to apply sub/sup
        def apply_format(regex, format_type):
            # We iterate through matches in the plain text
            text_content = self.toPlainText()
            for match in re.finditer(regex, text_content):
                # Try to handle multiple groups if present, otherwise group 1, or whole match
                if match.lastindex:
                    start, end = match.span(match.lastindex)
                else:
                    start, end = match.span()

                cursor = self.textCursor()
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

                fmt = cursor.charFormat()

                # USER REQUEST: "pass such cases" for underlined text (prevent defaulting to small)
                if fmt.fontUnderline():
                    if not self.scene():
                        return

                    continue

                if format_type == "sub":
                    fmt.setVerticalAlignment(
                        QTextCharFormat.VerticalAlignment.AlignSubScript
                    )
                elif format_type == "sup":
                    fmt.setVerticalAlignment(
                        QTextCharFormat.VerticalAlignment.AlignSuperScript
                    )

                cursor.setCharFormat(fmt)

        # 1. "Disable sub sup" (Clean up) - REMOVED per user feedback in earlier task to "remove reset"

        # 2. Subscript Numbers (e.g. H2, C6)
        # Regex: Number immediately following a letter or closing parenthesis
        apply_format(r"(?<=[a-zA-Z\)])(\d+)", "sub")

        # 3. Superscript Charges (e.g. 2+, 3-, +, -)

        # Regex A: Number + Sign (e.g. Ca2+)
        apply_format(r"(?<=[a-zA-Z\)])(\d+[+-])", "sup")

        # Regex B: Just Sign (e.g. Na+, Cl-)
        apply_format(r"(?<=[a-zA-Z0-9\)])([+-])(?=\s|$|[^a-zA-Z0-9])", "sup")

    def focusInEvent(self, event):
        # We NO LONGER force edit mode on focus in.
        # Focus can come from single-click selection.
        super().focusInEvent(event)

        # Only disable shortcuts if we are ALREADY in edit mode
        # (e.g. from Text tool creation or double-click which sets the flags BEFORE focus)
        if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
            try:
                mw = get_main_window(self.scene())
                if mw:
                    if hasattr(mw, "_reaction_mode_manager"):
                        mw._reaction_mode_manager.disable_main_window_shortcuts()
                    elif hasattr(mw, "ui_manager") and hasattr(
                        mw.ui_manager, "_reaction_mode_manager"
                    ):
                        mw.ui_manager._reaction_mode_manager.disable_main_window_shortcuts()
            except (RuntimeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

    def paint(self, painter, option, widget):
        # Handle custom selection highlight
        is_selected = option.state & QStyle.StateFlag.State_Selected
        if is_selected:
            # Purple for groups, blue for individuals
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 100)
            )
            fill_color = (
                QColor(130, 100, 255, 20)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 20)
            )

            painter.setPen(QPen(highlight_color, 4, Qt.PenStyle.SolidLine))
            painter.setBrush(fill_color)  # Light fill for text
            painter.drawRect(self.boundingRect().adjusted(-2, -2, 2, 2))

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
            "color": self.defaultTextColor().name(),
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
        self.setZValue(100)  # On top of everything
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

            scale = max(scale_x, scale_y)  # Uniform

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

                    elif hasattr(item, "setBox"):  # Future proofing
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

                    elif hasattr(item, "rect"):  # Bracket, Circle
                        # Rect based
                        curr_r = item.rect
                        # TopLeft moves
                        origin + (item.mapToScene(curr_r.topLeft()) - origin) * scale
                        new_br = (
                            origin
                            + (item.mapToScene(curr_r.bottomRight()) - origin) * scale
                        )

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

                    elif hasattr(item, "points"):  # Freehand
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

                    elif hasattr(item, "size"):  # Plus/Minus
                        new_pos = origin + (item.pos() - origin) * scale
                        item.setPos(new_pos)
                        item.size *= scale
                        item.update()

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
        if scene is None:
            return
        try:
            scene.changed.connect(self.on_scene_changed)
        except (RuntimeError, AttributeError, TypeError) as _e:
            logging.warning("silenced: %s", _e)

    def _disconnect_scene(self, scene):
        if scene is None:
            return
        try:
            scene.changed.disconnect(self.on_scene_changed)
        except TypeError:
            pass  # not connected — expected
        except (RuntimeError, AttributeError) as _e:
            logging.warning("silenced: %s", _e)

    def on_scene_changed(self, region):
        if self._updating:
            return
        self._updating = True
        try:
            self.update_rect()
            if getattr(self, "h_scale", None) is not None:
                self.sync_handles()
        finally:
            self._updating = False

    def update_rect(self):
        r = QRectF()
        for item in self.group_items:
            try:
                if item.scene() == self.scene() and not sip_isdeleted_safe(item):
                    if r.isNull():
                        r = item.sceneBoundingRect()
                    else:
                        r = r.united(item.sceneBoundingRect())
            except RuntimeError:
                continue

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

        # Bounding Box - Purple for group selection
        painter.setPen(QPen(QColor(130, 100, 255), 1, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(130, 100, 255, 10))  # Very light purple fill
        painter.drawRect(self._rect)

        # Bottom-Right Corner Handle Visual - Purple
        handle_size = 8
        handle_rect = QRectF(
            self._rect.right() - handle_size,
            self._rect.bottom() - handle_size,
            handle_size,
            handle_size,
        )
        painter.setPen(QPen(QColor(130, 100, 255), 1))
        painter.setBrush(QColor(130, 100, 255))  # Solid purple
        painter.drawRect(handle_rect)

        painter.restore()

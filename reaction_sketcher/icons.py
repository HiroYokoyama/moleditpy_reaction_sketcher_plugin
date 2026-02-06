#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtGui import QIcon, QPainter, QPixmap, QPen, QColor, QFont, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF

def create_reaction_icon(tool_name, size=32):
    """Generates a premium QIcon dynamically using QPainter."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw Background (Rounded Square)
    margin = 2
    r_rect = QRectF(margin, margin, size - 2*margin, size - 2*margin)
    
    # Subtle gradient or fill
    painter.setPen(Qt.PenStyle.NoPen)
    if tool_name == "exit":
        painter.setBrush(QColor(211, 47, 47, 40)) # Light red for exit
    elif tool_name == "select":
        painter.setBrush(QColor(0, 120, 215, 60)) # Light blue for active select
    else:
        painter.setBrush(QColor(240, 240, 240, 255)) # Light neutral
    painter.drawRoundedRect(r_rect, 6, 6)
    
    # Draw Symbol
    pen = QPen(QColor("#222222"))
    pen.setWidthF(2.5)
    if tool_name in ["select", "arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_no", "curved_double", "curved_fish"]:
        pen.setColor(QColor("#005a9e")) # Premium Blue for primary tools
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    
    inner_margin = size * 0.25
    c = size / 2
    w = size - 2 * inner_margin
    h = size - 2 * inner_margin
    
    if tool_name == "select":
        # Draw a classic cursor arrow
        p = QPolygonF([QPointF(c-2, c-8), QPointF(c-2, c+6), QPointF(c+1, c+1), QPointF(c+6, c+1)])
        painter.setBrush(QColor("#005a9e"))
        painter.drawPolygon(p)

    elif tool_name == "arrow":
        start = QPointF(inner_margin, size - inner_margin)
        end = QPointF(size - inner_margin, inner_margin)
        painter.drawLine(start, end)
        angle = QLineF(start, end).angle()
        head = 6
        h1 = QLineF.fromPolar(head, angle + 180 + 35).p2()
        h2 = QLineF.fromPolar(head, angle + 180 - 35).p2()
        painter.setBrush(QColor("#005a9e"))
        painter.drawPolygon(QPolygonF([end, end + h1, end + h2]))
        
    elif tool_name == "arrow_eq":
        y1, y2 = c - 4, c + 4
        painter.drawLine(QPointF(inner_margin, y1), QPointF(size - inner_margin, y1))
        painter.drawLine(QPointF(size - inner_margin, y2), QPointF(inner_margin, y2))
        head = 5
        painter.drawLine(QPointF(size-inner_margin, y1), QPointF(size-inner_margin-head, y1-head*0.7))
        painter.drawLine(QPointF(inner_margin, y2), QPointF(inner_margin+head, y2+head*0.7))

    elif tool_name == "arrow_res":
        y = c
        painter.drawLine(QPointF(inner_margin, y), QPointF(size - inner_margin, y))
        head = 5
        painter.drawPolygon(QPolygonF([QPointF(inner_margin, y), QPointF(inner_margin+head, y-head*0.6), QPointF(inner_margin+head, y+head*0.6)]))
        painter.drawPolygon(QPolygonF([QPointF(size-inner_margin, y), QPointF(size-inner_margin-head, y-head*0.6), QPointF(size-inner_margin-head, y+head*0.6)]))

    elif tool_name == "arrow_retro":
        y1, y2 = c - 2.5, c + 2.5
        painter.drawLine(QPointF(inner_margin, y1), QPointF(size - inner_margin - 4, y1))
        painter.drawLine(QPointF(inner_margin, y2), QPointF(size - inner_margin - 4, y2))
        head = 8
        end = QPointF(size-inner_margin, c)
        painter.drawPolygon(QPolygonF([end, QPointF(end.x()-head, end.y()-head*0.7), QPointF(end.x()-head, end.y()+head*0.7)]))

    elif tool_name == "arrow_no":
        painter.drawLine(QPointF(inner_margin, c), QPointF(size - inner_margin, c))
        head = 5
        painter.drawLine(QPointF(size-inner_margin, c), QPointF(size-inner_margin-head, c-head*0.7))
        painter.drawLine(QPointF(size-inner_margin, c), QPointF(size-inner_margin-head, c+head*0.7))
        # Black dash
        p_dash = QPen(QColor("#222222"))
        p_dash.setWidthF(2.5)
        painter.setPen(p_dash)
        painter.drawLine(QPointF(c-5, c+5), QPointF(c+5, c-5))

    elif tool_name == "curved_double":
        rect = QRectF(inner_margin, inner_margin, w, h*1.5)
        painter.drawArc(rect, 45*16, 90*16)
        end = QPointF(c, inner_margin+1)
        painter.setBrush(QColor("#005a9e"))
        painter.drawPolygon(QPolygonF([end, QPointF(end.x()-4, end.y()+5), QPointF(end.x()+4, end.y()+5)]))

    elif tool_name == "curved_fish":
        rect = QRectF(inner_margin, inner_margin, w, h*1.5)
        painter.drawArc(rect, 45*16, 90*16)
        end = QPointF(c, inner_margin+1)
        painter.drawLine(end, QPointF(end.x()-5, end.y()+5))

    elif tool_name == "plus":
        painter.drawLine(QPointF(c-h/2, c), QPointF(c+h/2, c))
        painter.drawLine(QPointF(c, c-h/2), QPointF(c, c+h/2))
        
    elif tool_name == "minus":
        painter.drawLine(QPointF(c-h/2, c), QPointF(c+h/2, c))

    elif tool_name == "bracket":
        painter.setPen(QPen(QColor("#222222"), 2))
        bw = 5
        painter.drawLine(QPointF(inner_margin+bw, inner_margin), QPointF(inner_margin, inner_margin))
        painter.drawLine(QPointF(inner_margin, inner_margin), QPointF(inner_margin, size-inner_margin))
        painter.drawLine(QPointF(inner_margin, size-inner_margin), QPointF(inner_margin+bw, size-inner_margin))
        painter.drawLine(QPointF(size-inner_margin-bw, inner_margin), QPointF(size-inner_margin, inner_margin))
        painter.drawLine(QPointF(size-inner_margin, inner_margin), QPointF(size-inner_margin, size-inner_margin))
        painter.drawLine(QPointF(size-inner_margin, size-inner_margin), QPointF(size-inner_margin-bw, size-inner_margin))

    elif tool_name == "circle":
        painter.setPen(QPen(QColor("#222222"), 2, Qt.PenStyle.DashLine))
        painter.drawEllipse(QRectF(inner_margin, inner_margin, w, h))

    elif tool_name == "text":
        painter.setPen(QPen(QColor("#222222"), 1))
        painter.setFont(QFont("Arial", int(size * 0.5), QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "A")
        
    elif tool_name == "exit":
        pen.setColor(QColor("#d32f2f"))
        pen.setWidthF(2.5)
        painter.setPen(pen)
        painter.drawLine(QPointF(c-6, c-6), QPointF(c+6, c+6))
        painter.drawLine(QPointF(c+6, c-6), QPointF(c-6, c+6))
        
    painter.end()
    return QIcon(pixmap)
def create_style_icon(item_type, style_name, size=24):
    """Generates small style icons for sub-menus."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    pen = QPen(QColor("#005a9e"))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    
    c = size / 2
    m = size * 0.2
    
    if item_type == "arrow_no":
        # Draw a line with style
        painter.drawLine(QPointF(m, c), QPointF(size-m, c))
        if style_name == "slash":
            painter.setPen(QPen(QColor("#222222"), 2))
            painter.drawLine(QPointF(c-4, c+4), QPointF(c+4, c-4))
        elif style_name == "cross":
            painter.setPen(QPen(QColor("#222222"), 2))
            painter.drawLine(QPointF(c-3, c+3), QPointF(c+3, c-3))
            painter.drawLine(QPointF(c+3, c+3), QPointF(c-3, c-3))
            
    elif item_type == "curved":
        # Draw a small curve with head style
        rect = QRectF(m, m, size-2*m, size)
        painter.drawArc(rect, 45*16, 90*16)
        end = QPointF(c, m+1)
        if style_name == "triangle":
            painter.setBrush(QColor("#005a9e"))
            head = 5
            painter.drawPolygon(QPolygonF([end, QPointF(end.x()-4, end.y()+head), QPointF(end.x()+4, end.y()+head)]))
        elif style_name == "barb":
            painter.drawLine(end, QPointF(end.x()-5, end.y()+5))
            painter.drawLine(end, QPointF(end.x()+5, end.y()+5))
        elif style_name == "fish":
            painter.drawLine(end, QPointF(end.x()-5, end.y()+5))

    painter.end()
    return QIcon(pixmap)

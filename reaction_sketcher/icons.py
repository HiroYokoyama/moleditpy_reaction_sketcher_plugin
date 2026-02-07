#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtGui import QIcon, QPainter, QPixmap, QPen, QColor, QFont, QPolygonF, QPainterPath
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
    if tool_name in ["select", "arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_no", "curved_double", "curved_fish", "arrow_dashed", "circle"]:
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
        path = QPainterPath()
        start = QPointF(inner_margin, inner_margin + h)
        ctrl = QPointF(inner_margin, inner_margin)
        end = QPointF(inner_margin + w, inner_margin)
        path.moveTo(start)
        path.quadTo(ctrl, end)
        
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
        painter.setBrush(QColor("#005a9e"))
        painter.setPen(Qt.PenStyle.NoPen)
        head = 5
        painter.drawPolygon(QPolygonF([end, QPointF(end.x()-head, end.y()-3), QPointF(end.x()-head, end.y()+3)]))

    elif tool_name == "group":
        painter.setPen(QPen(QColor("#005a9e"), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(inner_margin, inner_margin, size - 2*inner_margin, size - 2*inner_margin))
        
        painter.setPen(QPen(QColor("#222222"), 1.5))
        painter.setBrush(QColor("#222222"))
        s = size / 4
        painter.drawRect(QRectF(c - s + 2, c - s + 2, s, s))
        painter.drawRect(QRectF(c + 2, c + 2, s, s))

    elif tool_name == "ungroup":
        painter.setPen(QPen(QColor("#222222"), 1.5))
        painter.setBrush(QColor("#222222"))
        s = size / 4
        painter.drawRect(QRectF(c - s - 2, c - s - 2, s, s))
        painter.drawRect(QRectF(c + 2, c + 2, s, s))

    elif tool_name == "curved_fish":
        path = QPainterPath()
        start = QPointF(inner_margin, inner_margin + h)
        ctrl = QPointF(inner_margin, inner_margin)
        end = QPointF(inner_margin + w, inner_margin)
        path.moveTo(start)
        path.quadTo(ctrl, end)
        
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawPath(path)
        
        painter.drawLine(end, QPointF(end.x()-5, end.y()+4))

    elif tool_name == "circle":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(inner_margin, inner_margin, w, h))
        

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
        
    elif tool_name == "line":
        painter.drawLine(QPointF(inner_margin, size - inner_margin), QPointF(size - inner_margin, inner_margin))
        
    elif tool_name == "line_dashed":
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(inner_margin, size - inner_margin), QPointF(size - inner_margin, inner_margin))
        
    elif tool_name == "line_curved":
        path = QPainterPath()
        start = QPointF(inner_margin, size - inner_margin)
        ctrl = QPointF(inner_margin, inner_margin)
        end = QPointF(size - inner_margin, inner_margin)
        path.moveTo(start)
        path.quadTo(ctrl, end)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
    elif tool_name == "freehand":
        # Scribble icon
        path = QPainterPath()
        path.moveTo(inner_margin, size - inner_margin)
        path.cubicTo(c - 5, size - inner_margin, c + 5, inner_margin, size - inner_margin, inner_margin)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
    elif tool_name == "arrow_dashed":
        # Same as arrow but dashed
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        start = QPointF(inner_margin, size - inner_margin)
        end = QPointF(size - inner_margin, inner_margin)
        painter.drawLine(start, end)
        
        # Head (solid)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#005a9e"))
        angle = QLineF(start, end).angle()
        head = 6
        h1 = QLineF.fromPolar(head, angle + 180 + 35).p2()
        h2 = QLineF.fromPolar(head, angle + 180 - 35).p2()
        painter.drawPolygon(QPolygonF([end, end + h1, end + h2]))
        
    painter.end()
    return QIcon(pixmap)
def create_style_icon(item_type, style_name, selected=False):
    # Create a pixmap for the style icon
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    if selected:
        painter.setBrush(QColor("#E0E0E0")) # Light Gray
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 4, 4)
        
    c = size / 2
    m = 4 # Margin
    
    pen_color = QColor("#333333")
    pen = QPen(pen_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    
    if item_type == "arrow": # Generic/Straight default
        w = size - 2*m
        h = size - 2*m
    
    if item_type == "arrow_no":
        # Draw a line with style
        painter.setPen(pen)
        painter.drawLine(QPointF(m, c), QPointF(size-m, c))
        
        # Draw negation symbol
        red_pen = QPen(QColor("#d32f2f"), 2)
        painter.setPen(red_pen)
        
        if style_name == "slash":
            painter.drawLine(QPointF(c-3, c+4), QPointF(c+3, c-4))
        elif style_name == "cross":
            painter.drawLine(QPointF(c-3, c+3), QPointF(c+3, c-3))
            painter.drawLine(QPointF(c+3, c+3), QPointF(c-3, c-3))
        elif style_name == "double_slash":
            painter.drawLine(QPointF(c-4, c+4), QPointF(c, c-4))
            painter.drawLine(QPointF(c, c+4), QPointF(c+4, c-4))
            
    elif item_type == "curved" or item_type == "straight":
        # Draw a curve or straight line with head style
        
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)

        if item_type == "curved":
            path = QPainterPath()
            start = QPointF(m, size-m)
            ctrl = QPointF(m, m)
            end = QPointF(size-m, m)
            path.moveTo(start)
            path.quadTo(ctrl, end)
            
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawPath(path)
            
            # Vector P2-P1 for angle
            vec = end - ctrl
            angle = QLineF(QPointF(0,0), vec).angle()
            
        else: # straight
            start = QPointF(m, size/2)
            end = QPointF(size-m, size/2)
            
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawLine(start, end)
            
            angle = QLineF(start, end).angle()
        
        # Draw Head
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#005a9e"))
        
        head_len = 5
        
        if style_name == "triangle":
             p1 = QLineF.fromPolar(head_len, angle + 180 + 30).p2() + end
             p2 = QLineF.fromPolar(head_len, angle + 180 - 30).p2() + end
             painter.drawPolygon(QPolygonF([end, p1, p2]))
             
        elif style_name == "chevron":
             # Concave base
             p1 = QLineF.fromPolar(head_len, angle + 180 + 30).p2() + end
             p2 = QLineF.fromPolar(head_len, angle + 180 - 30).p2() + end
             mid = QLineF.fromPolar(head_len * 0.5, angle + 180).p2() + end
             painter.drawPolygon(QPolygonF([end, p1, mid, p2]))
             
        elif style_name == "harpoon":
             # Half head (top side relative to angle?)
             p1 = QLineF.fromPolar(head_len, angle + 180 + 30).p2() + end
             painter.drawPolygon(QPolygonF([end, p1, QLineF.fromPolar(head_len*0.8, angle+180).p2() + end]))
             
        elif style_name == "barb":
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.setPen(QPen(QColor("#005a9e"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
             p1 = QLineF.fromPolar(head_len, angle + 180 + 35).p2() + end
             p2 = QLineF.fromPolar(head_len, angle + 180 - 35).p2() + end
             painter.drawLine(end, p1)
             painter.drawLine(end, p2)

        elif style_name == "fish":
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.setPen(QPen(QColor("#005a9e"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
             p1 = QLineF.fromPolar(head_len, angle + 180 + 35).p2() + end
             painter.drawLine(end, p1)

    painter.end()
    return QIcon(pixmap)

def create_shape_variant_icon(shape_type, line_style, size=32):
    """Generates an icon for specific shape variants (Solid/Dashed Rect/Circle)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Background
    margin = 2
    r_rect = QRectF(margin, margin, size - 2*margin, size - 2*margin)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(240, 240, 240, 255))
    painter.drawRoundedRect(r_rect, 6, 6)
    
    # Pen
    pen = QPen(QColor("#222222"))
    pen.setWidthF(2.0)
    if line_style == "dashed":
        pen.setStyle(Qt.PenStyle.DashLine)
    else:
        pen.setStyle(Qt.PenStyle.SolidLine)
    painter.setPen(pen)
    
    inner_m = size * 0.25
    r = QRectF(inner_m, inner_m, size - 2*inner_m, size - 2*inner_m)
    
    if shape_type == "rectangle":
        painter.drawRect(r)
    else:
        painter.drawEllipse(r)
        
    painter.end()
    return QIcon(pixmap)

def create_alignment_icon(tool_name, size=32):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Background
    margin = 2
    r_rect = QRectF(margin, margin, size - 2*margin, size - 2*margin)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(240, 240, 240, 255))
    painter.drawRoundedRect(r_rect, 4, 4)
    
    painter.setPen(QPen(QColor("#222222"), 2))
    painter.setBrush(QColor("#005a9e"))
    
    m = 6
    w = size
    h = size
    
    if tool_name == "align_top":
        # Bar at top
        painter.drawLine(QPointF(m, m), QPointF(w-m, m))
        # Two boxes below
        painter.drawRect(m, m+4, 6, 8)
        painter.drawRect(m+10, m+4, 6, 12)
        
    elif tool_name == "align_bottom":
        # Bar at bottom
        painter.drawLine(QPointF(m, h-m), QPointF(w-m, h-m))
        # Two boxes above
        painter.drawRect(m, h-m-12, 6, 12)
        painter.drawRect(m+10, h-m-8, 6, 8)
        
    elif tool_name == "align_center_v":
        # Line in middle
        mid = int(h/2)
        painter.drawLine(QPointF(m, mid), QPointF(w-m, mid))
        # Boxes centered
        painter.drawRect(m, mid-4, 6, 8)
        painter.drawRect(m+10, mid-6, 6, 12)
        
    elif tool_name == "distribute_h":
        # Three vertical bars equally spaced
        y1, y2 = m+4, h-m-4
        painter.drawLine(m+2, y1, m+2, y2)
        painter.drawLine(int(w/2), y1, int(w/2), y2)
        painter.drawLine(w-m-2, y1, w-m-2, y2)
        
    elif tool_name == "distribute_v":
        # Three horizontal bars equally spaced
        x1, x2 = m+4, w-m-4
        painter.drawLine(x1, m+2, x2, m+2)
        painter.drawLine(x1, int(h/2), x2, int(h/2))
        painter.drawLine(x1, h-m-2, x2, h-m-2)

    painter.end()
    return QIcon(pixmap)

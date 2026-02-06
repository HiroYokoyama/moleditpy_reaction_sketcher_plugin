#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtGui import QIcon, QPainter, QPixmap, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QPointF, QRectF

def create_reaction_icon(tool_name, size=32):
    """Generates a QIcon dynamically using QPainter."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    pen = QPen(QColor("#222222"), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    
    margin = size * 0.2
    inner_size = size - 2 * margin
    
    if tool_name == "arrow":
        # Draw an arrow pointing from bottom-left to top-right
        start = QPointF(margin, size - margin)
        end = QPointF(size - margin, margin)
        painter.drawLine(start, end)
        
        # Arrow head
        head_size = size * 0.25
        painter.drawLine(end, QPointF(end.x() - head_size, end.y()))
        painter.drawLine(end, QPointF(end.x(), end.y() + head_size))
        
    elif tool_name == "plus":
        # Draw a bold plus sign
        center = size / 2
        arm = inner_size / 2
        painter.drawLine(QPointF(center - arm, center), QPointF(center + arm, center))
        painter.drawLine(QPointF(center, center - arm), QPointF(center, center + arm))
        
    elif tool_name == "minus":
        # Draw a bold minus sign
        center = size / 2
        arm = inner_size / 2
        painter.drawLine(QPointF(center - arm, center), QPointF(center + arm, center))

    elif tool_name == "arrow_eq":
        # Equilibrium arrow (two half-headed arrows)
        y1 = size * 0.4
        y2 = size * 0.6
        painter.drawLine(QPointF(margin, y1), QPointF(size - margin, y1))
        painter.drawLine(QPointF(size - margin, y2), QPointF(margin, y2))
        head = size * 0.15
        painter.drawLine(QPointF(size - margin, y1), QPointF(size - margin - head, y1 - head))
        painter.drawLine(QPointF(margin, y2), QPointF(margin + head, y2 + head))

    elif tool_name == "arrow_res":
        # Resonance arrow (double-headed single line)
        y = size / 2
        painter.drawLine(QPointF(margin, y), QPointF(size - margin, y))
        head = size * 0.15
        painter.drawLine(QPointF(margin, y), QPointF(margin + head, y - head))
        painter.drawLine(QPointF(margin, y), QPointF(margin + head, y + head))
        painter.drawLine(QPointF(size - margin, y), QPointF(size - margin - head, y - head))
        painter.drawLine(QPointF(size - margin, y), QPointF(size - margin - head, y + head))

    elif tool_name == "arrow_retro":
        # Retrosynthetic arrow (double-line arrow)
        y1 = size * 0.45
        y2 = size * 0.55
        painter.drawLine(QPointF(margin, y1), QPointF(size - margin - 5, y1))
        painter.drawLine(QPointF(margin, y2), QPointF(size - margin - 5, y2))
        head = size * 0.2
        painter.drawLine(QPointF(size - margin, size/2), QPointF(size - margin - head, size/2 - head))
        painter.drawLine(QPointF(size - margin, size/2), QPointF(size - margin - head, size/2 + head))

    elif tool_name == "curved_double":
        # Curved double-headed arrow icon
        painter.drawArc(QRectF(margin, margin, inner_size, inner_size*1.5), 45 * 16, 90 * 16)
        # simplistic head for icon
        painter.drawLine(QPointF(size/2, margin), QPointF(size/2 - 5, margin + 5))
        painter.drawLine(QPointF(size/2, margin), QPointF(size/2 + 5, margin + 5))

    elif tool_name == "curved_single":
        # Curved single-headed fish hook icon
        painter.drawArc(QRectF(margin, margin, inner_size, inner_size*1.5), 45 * 16, 90 * 16)
        painter.drawLine(QPointF(size/2, margin), QPointF(size/2 - 5, margin + 5))

    elif tool_name == "bracket":
        # Brackets [ ] icon
        painter.drawLine(QPointF(margin, margin), QPointF(margin + 5, margin))
        painter.drawLine(QPointF(margin, margin), QPointF(margin, size - margin))
        painter.drawLine(QPointF(margin, size - margin), QPointF(margin + 5, size - margin))
        
        painter.drawLine(QPointF(size - margin, margin), QPointF(size - margin - 5, margin))
        painter.drawLine(QPointF(size - margin, margin), QPointF(size - margin, size - margin))
        painter.drawLine(QPointF(size - margin, size - margin), QPointF(size - margin - 5, size - margin))

    elif tool_name == "arrow_no":
        # No reaction arrow
        painter.drawLine(QPointF(margin, size/2), QPointF(size - margin, size/2))
        head = 6
        painter.drawLine(QPointF(size - margin, size/2), QPointF(size - margin - head, size/2 - head))
        painter.drawLine(QPointF(size - margin, size/2), QPointF(size - margin - head, size/2 + head))
        # Slash
        pen_red = QPen(QColor("#d32f2f"), 2)
        painter.setPen(pen_red)
        painter.drawLine(QPointF(size/2 - 6, size/2 - 6), QPointF(size/2 + 6, size/2 + 6))
        
    elif tool_name == "text":
        # Draw "A" letter as a symbol for text
        painter.setFont(QFont("Arial", int(size * 0.6), QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "A")
        
    elif tool_name == "exit":
        # Draw an "X" or an arrow pointing back
        pen.setColor(QColor("#d32f2f")) # Reddish for exit
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawLine(QPointF(margin, margin), QPointF(size - margin, size - margin))
        painter.drawLine(QPointF(size - margin, margin), QPointF(margin, size - margin))
        
    painter.end()
    return QIcon(pixmap)

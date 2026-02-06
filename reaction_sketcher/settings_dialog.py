#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSpinBox, QPushButton, QColorDialog, QGroupBox)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("Advanced Settings")
        self.setMinimumWidth(250)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Color Setting
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self.color_btn = QPushButton()
        self.current_color = getattr(self.item, "pen_color", QColor("#222222"))
        if hasattr(self.item, "defaultTextColor"):
            self.current_color = self.item.defaultTextColor()
        
        self.update_color_button()
        self.color_btn.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_btn)
        layout.addLayout(color_layout)

        # Line Width
        if hasattr(self.item, "pen_width"):
            width_layout = QHBoxLayout()
            width_layout.addWidget(QLabel("Line Width:"))
            self.width_spin = QSpinBox()
            self.width_spin.setRange(1, 20)
            self.width_spin.setValue(int(self.item.pen_width))
            width_layout.addWidget(self.width_spin)
            layout.addLayout(width_layout)

        # Buttons
        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def choose_color(self):
        color = QColorDialog.getColor(self.current_color, self, "Choose Color")
        if color.isValid():
            self.current_color = color
            self.update_color_button()
            
    def update_color_button(self):
        self.color_btn.setStyleSheet(f"background-color: {self.current_color.name()}; border: 1px solid #888;")

    def get_settings(self):
        settings = {"color": self.current_color}
        if hasattr(self, "width_spin"):
            settings["width"] = self.width_spin.value()
        return settings

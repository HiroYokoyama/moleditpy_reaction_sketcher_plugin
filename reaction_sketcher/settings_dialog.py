#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QColorDialog,
    QGroupBox,
    QComboBox,
    QMessageBox,
    QFormLayout,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal
import json
import os
import logging

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")


class AdvancedSettingsDialog(QDialog):
    applyRequested = pyqtSignal()

    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("Advanced Settings")
        self.setMinimumWidth(350)

        # Determine "Kind" of item for specific template storage
        self.item_kind = "general"
        if hasattr(item, "create_json_data"):
            data = item.create_json_data()
            self.item_kind = data.get("type", "general")

        self.init_ui()
        self.load_templates()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Properties Group ---
        props_group = QGroupBox("Properties")
        props_layout = QFormLayout()

        # Color
        self.color_btn = QPushButton()
        self.current_color = getattr(self.item, "pen_color", QColor("#222222"))
        if hasattr(self.item, "defaultTextColor"):
            self.current_color = self.item.defaultTextColor()
        self.update_color_button()
        self.color_btn.clicked.connect(self.choose_color)
        props_layout.addRow("Color:", self.color_btn)

        # Line Width
        if hasattr(self.item, "pen_width"):
            self.width_spin = QSpinBox()
            self.width_spin.setRange(1, 20)
            self.width_spin.setValue(int(self.item.pen_width))
            props_layout.addRow("Line Width:", self.width_spin)

        # Head Size
        if hasattr(self.item, "head_size"):
            self.head_size_spin = QDoubleSpinBox()
            self.head_size_spin.setRange(1.0, 100.0)
            self.head_size_spin.setValue(float(self.item.head_size))
            props_layout.addRow("Head Size:", self.head_size_spin)

        # Head Angle
        if hasattr(self.item, "head_angle"):
            self.head_angle_spin = QDoubleSpinBox()
            self.head_angle_spin.setRange(5.0, 85.0)
            self.head_angle_spin.setValue(float(self.item.head_angle))
            props_layout.addRow("Head Angle (Width):", self.head_angle_spin)

        # Concavity
        if hasattr(self.item, "head_concavity"):
            self.concavity_spin = QDoubleSpinBox()
            self.concavity_spin.setRange(0.0, 1.0)
            self.concavity_spin.setSingleStep(0.1)
            self.concavity_spin.setValue(float(self.item.head_concavity))
            props_layout.addRow("Chevron Concavity:", self.concavity_spin)

        # Curvature
        if hasattr(self.item, "curvature"):
            self.curvature_spin = QDoubleSpinBox()
            self.curvature_spin.setRange(0.1, 2.0)
            self.curvature_spin.setSingleStep(0.1)
            self.curvature_spin.setValue(float(self.item.curvature))
            props_layout.addRow("Curvature:", self.curvature_spin)

        # Head Style (New)
        if hasattr(self.item, "head_style"):
            self.head_style_combo = QComboBox()
            # Determine available styles based on item type?
            # For now, list standard ones.
            self.head_style_combo.addItems(["triangle", "chevron", "harpoon", "barb"])
            self.head_style_combo.setCurrentText(self.item.head_style)
            self.head_style_combo.currentTextChanged.connect(self.update_ui_state)
            props_layout.addRow("Head Style:", self.head_style_combo)

        # Head Position (Start/End) - Disabled by user request
        # if hasattr(self.item, "head_at"):
        #     self.head_at_combo = QComboBox()
        #     self.head_at_combo.addItems(["start", "end"])
        #     self.head_at_combo.setCurrentText(str(self.item.head_at))
        #     props_layout.addRow("Arrow Position:", self.head_at_combo)

        # Head Side (Up/Down) - For single-headed curved arrows
        if hasattr(self.item, "head_side"):
            self.head_side_label = QLabel("Head Side (Up/Down):")
            self.head_side_combo = QComboBox()
            self.head_side_combo.addItems(["Up", "Down"])
            # [Reversed mapping based on user feedback]
            self.head_side_combo.setCurrentText(
                "Up" if self.item.head_side < 0 else "Down"
            )
            props_layout.addRow(self.head_side_label, self.head_side_combo)

        # Double Arrow Spacing
        if hasattr(self.item, "double_arrow_offset"):
            self.spacing_spin = QDoubleSpinBox()
            self.spacing_spin.setRange(1.0, 20.0)
            self.spacing_spin.setSingleStep(0.5)
            self.spacing_spin.setValue(float(self.item.double_arrow_offset))
            props_layout.addRow("Double Arrow Spacing:", self.spacing_spin)

        # Cross Size (No Reaction)
        if hasattr(self.item, "cross_size"):
            self.cross_size_spin = QDoubleSpinBox()
            self.cross_size_spin.setRange(5.0, 100.0)
            self.cross_size_spin.setValue(float(self.item.cross_size))
            props_layout.addRow("Cross/Slash Size:", self.cross_size_spin)

        # Rect Size (Bracket, Circle, Arrow, Line, Freehand, etc.)
        if hasattr(self.item, "rect") or hasattr(self.item, "set_rect_size"):
            w_val, h_val = 100.0, 100.0
            if hasattr(self.item, "rect"):
                w_val = float(self.item.rect.width())
                h_val = float(self.item.rect.height())
            elif hasattr(self.item, "start_p") and hasattr(self.item, "end_p"):
                w_val = float(abs(self.item.end_p.x() - self.item.start_p.x()))
                h_val = float(abs(self.item.end_p.y() - self.item.start_p.y()))

            self.rect_w_spin = QDoubleSpinBox()
            self.rect_w_spin.setRange(1.0, 5000.0)
            self.rect_w_spin.setValue(w_val)
            props_layout.addRow("Width:", self.rect_w_spin)

            self.rect_h_spin = QDoubleSpinBox()
            self.rect_h_spin.setRange(1.0, 5000.0)
            self.rect_h_spin.setValue(h_val)
            props_layout.addRow("Height:", self.rect_h_spin)

        # Item Size (Plus, Minus, etc.)
        if hasattr(self.item, "size"):
            self.item_size_spin = QDoubleSpinBox()
            self.item_size_spin.setRange(5.0, 1000.0)
            self.item_size_spin.setValue(float(self.item.size))
            props_layout.addRow("Size:", self.item_size_spin)

        # Bracket Type
        if hasattr(self.item, "bracket_type"):
            self.bracket_combo = QComboBox()
            self.bracket_combo.addItems(
                [
                    "square",
                    "square_left",
                    "square_right",
                    "round",
                    "round_left",
                    "round_right",
                    "curly",
                    "curly_left",
                    "curly_right",
                ]
            )
            self.bracket_combo.setCurrentText(self.item.bracket_type)
            props_layout.addRow("Bracket Style:", self.bracket_combo)

        props_group.setLayout(props_layout)
        main_layout.addWidget(props_group)

        # --- Templates Group ---
        tmpl_group = QGroupBox("Templates")
        tmpl_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.tmpl_combo = QComboBox()
        self.tmpl_combo.currentTextChanged.connect(self.on_template_selected)
        row1.addWidget(self.tmpl_combo, 1)

        btn_apply = QPushButton("Load")
        btn_apply.clicked.connect(self.apply_template_to_ui)
        row1.addWidget(btn_apply)
        tmpl_layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_save = QPushButton("Save/Update")
        btn_save.clicked.connect(self.save_template)
        row2.addWidget(btn_save)

        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self.delete_template)
        row2.addWidget(btn_del)
        tmpl_layout.addLayout(row2)

        tmpl_group.setLayout(tmpl_layout)
        main_layout.addWidget(tmpl_group)

        # --- Dialog Buttons ---
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self.applyRequested.emit)

        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_apply)
        btn_box.addWidget(btn_cancel)
        main_layout.addLayout(btn_box)

        # Initial gray-out state
        self.update_ui_state()

    def update_ui_state(self, _=None):
        # Enable/Disable based on item state
        if getattr(self, "concavity_spin", None) is not None:
            # Enable only if head style is chevron
            is_chevron = False
            if getattr(self, "head_style_combo", None) is not None:
                is_chevron = self.head_style_combo.currentText() == "chevron"
            elif hasattr(self.item, "head_style"):
                is_chevron = self.item.head_style == "chevron"
            self.concavity_spin.setEnabled(is_chevron)

        if getattr(self, "head_side_combo", None) is not None:
            # Show for harpoon style OR if it's a curved arrow (where it's always relevant for fish-hooks)
            is_harpoon = False
            if getattr(self, "head_style_combo", None) is not None:
                is_harpoon = self.head_style_combo.currentText() == "harpoon"
            elif hasattr(self.item, "head_style"):
                is_harpoon = self.item.head_style == "harpoon"

            is_curved = "curved" in self.item_kind
            visible = is_harpoon or is_curved
            self.head_side_combo.setVisible(visible)
            if getattr(self, "head_side_label", None) is not None:
                self.head_side_label.setVisible(visible)

    def choose_color(self):
        color = QColorDialog.getColor(self.current_color, self, "Choose Color")
        if color.isValid():
            self.current_color = color
            self.update_color_button()

    def update_color_button(self):
        rgb = self.current_color.name()
        self.color_btn.setStyleSheet(
            f"background-color: {rgb}; border: 1px solid #555; min-width: 40px;"
        )
        self.color_btn.setText(rgb)

    def get_current_values(self):
        """Returns a dict of currently displayed values."""
        vals = {"color": self.current_color.name()}
        if getattr(self, "width_spin", None) is not None:
            vals["width"] = self.width_spin.value()
        if getattr(self, "head_size_spin", None) is not None:
            vals["head_size"] = self.head_size_spin.value()
        if getattr(self, "head_angle_spin", None) is not None:
            vals["head_angle"] = self.head_angle_spin.value()
        if getattr(self, "concavity_spin", None) is not None:
            vals["head_concavity"] = self.concavity_spin.value()
        if getattr(self, "curvature_spin", None) is not None:
            vals["curvature"] = self.curvature_spin.value()
        if getattr(self, "spacing_spin", None) is not None:
            vals["double_arrow_offset"] = self.spacing_spin.value()
        if getattr(self, "cross_size_spin", None) is not None:
            vals["cross_size"] = self.cross_size_spin.value()
        if getattr(self, "item_size_spin", None) is not None:
            vals["size"] = self.item_size_spin.value()
        if getattr(self, "rect_w_spin", None) is not None:
            vals["rect_width"] = self.rect_w_spin.value()
        if getattr(self, "rect_h_spin", None) is not None:
            vals["rect_height"] = self.rect_h_spin.value()
        if getattr(self, "bracket_combo", None) is not None:
            vals["bracket_type"] = self.bracket_combo.currentText()
        if getattr(self, "head_style_combo", None) is not None:
            vals["head_style"] = self.head_style_combo.currentText()
        # if hasattr(self, "head_at_combo"): vals["head_at"] = self.head_at_combo.currentText()
        if getattr(self, "head_side_combo", None) is not None:
            vals["head_side"] = -1 if self.head_side_combo.currentText() == "Up" else 1
        return vals

    def set_ui_values(self, vals):
        """Updates UI from a dict."""
        if "color" in vals:
            self.current_color = QColor(vals["color"])
            self.update_color_button()
        if "width" in vals and getattr(self, "width_spin", None) is not None:
            self.width_spin.setValue(int(vals["width"]))
        if "head_size" in vals and getattr(self, "head_size_spin", None) is not None:
            self.head_size_spin.setValue(float(vals["head_size"]))
        if "head_angle" in vals and getattr(self, "head_angle_spin", None) is not None:
            self.head_angle_spin.setValue(float(vals["head_angle"]))
        if "head_concavity" in vals and hasattr(self.item, "head_concavity"):
            self.item.head_concavity = float(vals["head_concavity"])
        if "curvature" in vals and hasattr(self.item, "curvature"):
            self.item.curvature = float(vals["curvature"])
        if "double_arrow_offset" in vals and hasattr(self.item, "double_arrow_offset"):
            self.item.double_arrow_offset = float(vals["double_arrow_offset"])
        if "cross_size" in vals and hasattr(self.item, "cross_size"):
            self.item.cross_size = float(vals["cross_size"])
        if "cross_size" in vals and getattr(self, "cross_size_spin", None) is not None:
            self.cross_size_spin.setValue(float(vals["cross_size"]))
        if "bracket_type" in vals and hasattr(self.item, "bracket_type"):
            self.item.bracket_type = vals["bracket_type"]
        if "bracket_type" in vals and getattr(self, "bracket_combo", None) is not None:
            self.bracket_combo.setCurrentText(vals["bracket_type"])
        if "head_style" in vals and getattr(self, "head_style_combo", None) is not None:
            self.head_style_combo.setCurrentText(vals["head_style"])
        # if "head_at" in vals and hasattr(self.item, "head_at"):
        #      self.item.head_at = vals["head_at"]
        # if "head_at" in vals and hasattr(self, "head_at_combo"):
        #      self.head_at_combo.setCurrentText(vals["head_at"])
        if "head_side" in vals and hasattr(self.item, "head_side"):
            self.item.head_side = int(vals["head_side"])
        if "head_side" in vals and getattr(self, "head_side_combo", None) is not None:
            self.head_side_combo.setCurrentText(
                "Up" if int(vals["head_side"]) < 0 else "Down"
            )
        if "size" in vals and hasattr(self.item, "size"):
            self.item.size = float(vals["size"])
        if "size" in vals and getattr(self, "item_size_spin", None) is not None:
            self.item_size_spin.setValue(float(vals["size"]))
        if "rect_width" in vals and getattr(self, "rect_w_spin", None) is not None:
            self.rect_w_spin.setValue(float(vals["rect_width"]))
        if "rect_height" in vals and getattr(self, "rect_h_spin", None) is not None:
            self.rect_h_spin.setValue(float(vals["rect_height"]))

        self.update_ui_state()

    # --- Template Logic ---
    def load_templates(self):
        self.templates = {}
        # Load from file
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    all_templates = data.get("templates", {})
                    self.templates = all_templates
            except Exception as _e:
                logging.warning("silenced: %s", _e)

        self.default_key = f"Default_{self.item_kind}"

        # If the file had a saved default for this kind, load it into "Default" entry
        # AND keep it in self.templates so we don't lose it if we don't save "Default" back?
        # Actually, we map it to "Default" for display using a separate dict or filtering?
        # The current implementation modifies self.templates.

        if self.default_key in self.templates:
            self.templates["Default"] = self.templates[self.default_key]
            # We should NOT delete the original key immediately if we want to preserve it,
            # but for display purposes we want "Default".
            # let's del it, and when saving, we map "Default" back to self.default_key
            del self.templates[self.default_key]
        else:
            # Factory Defaults
            self.templates["Default"] = self.get_factory_defaults()

        self.update_combo()

    def get_factory_defaults(self):
        # Return hardcoded defaults based on item kind
        # width=3 is standard in items.py
        defaults = {"color": "#000000", "width": 3}
        if "arrow" in self.item_kind:
            defaults.update(
                {
                    "head_size": 25.0,  # Updated default
                    "head_style": "chevron",
                    "width": 2,
                    "head_at": "end",
                    "head_side": -1,
                }
            )
            if "curved" in self.item_kind:
                defaults["curvature"] = 0.4
                defaults["head_style"] = "chevron"

            if "no" in self.item_kind:
                defaults["cross_size"] = 15.0

        if "bracket" in self.item_kind:
            defaults.update({"bracket_type": "square", "width": 2})
        return defaults

    def update_combo(self):
        current_text = self.tmpl_combo.currentText()
        self.tmpl_combo.clear()

        # Always "Default" first
        self.tmpl_combo.addItem("Default")

        # Then others
        # Filter: Only show "Default" and Custom templates.
        # Hide "Default_{other_kind}" keys.
        for name in sorted(self.templates.keys()):
            if name == "Default":
                continue
            if name.startswith("Default_"):
                continue  # Hide other defaults
            self.tmpl_combo.addItem(name)

        if current_text in self.templates:
            self.tmpl_combo.setCurrentText(current_text)
        elif self.templates.get("Default", None):
            self.tmpl_combo.setCurrentText("Default")

    def on_template_selected(self, text):
        pass  # No checkbox anymore

    def apply_template_to_ui(self):
        name = self.tmpl_combo.currentText()
        if name in self.templates:
            self.set_ui_values(self.templates[name])

    def save_template(self):
        from PyQt6.QtWidgets import QInputDialog

        # Suggest current name
        current = self.tmpl_combo.currentText()
        name, ok = QInputDialog.getText(
            self, "Save Template", "Template Name:", text=current
        )
        if ok and name:
            vals = self.get_current_values()
            self.templates[name] = vals
            self.save_to_file()
            self.update_combo()
            self.tmpl_combo.setCurrentText(name)

    def delete_template(self):
        name = self.tmpl_combo.currentText()
        if name == "Default":
            reply = QMessageBox.question(
                self,
                "Reset Default?",
                "Reset 'Default' to factory settings?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.templates["Default"] = self.get_factory_defaults()
                self.save_to_file()
                self.apply_template_to_ui()
            return

        if name in self.templates:
            del self.templates[name]
            self.save_to_file()
            self.update_combo()

    def save_to_file(self):
        # Prepare data for saving
        # We need to reconstruct the full list including other defaults we might have hidden.

        # 1. Reload existing from file to get "other" defaults/templates we didn't load/touch?
        # Actually load_templates loaded EVERYTHING into self.templates.
        # Then we deleted self.default_key.
        # We also ignored other "Default_" keys in update_combo, but they are still in self.templates.

        to_save = {}
        for k, v in self.templates.items():
            if k == "Default":
                to_save[self.default_key] = v
            else:
                to_save[k] = v

        # Write to file
        data = {"templates": to_save}
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.warning("silenced: %s", e)

    def get_settings(self):
        vals = self.get_current_values()
        vals["color"] = self.current_color
        return vals

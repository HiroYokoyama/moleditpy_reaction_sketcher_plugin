#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import os
from PyQt6.QtWidgets import (QToolBar, QToolButton, QSizePolicy, 
                             QComboBox, QSpinBox, QCheckBox, QHBoxLayout, QWidget, QLabel, 
                             QColorDialog, QFileDialog, QMessageBox, QMenu)
from PyQt6.QtGui import QIcon, QColor, QFont, QPainter, QBrush, QActionGroup, QGuiApplication, QAction
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtCore import Qt, QSize, QRectF, QBuffer, QIODevice, QMimeData, QPoint, QObject, QEvent
from .icons import create_reaction_icon, create_shape_variant_icon, create_style_icon
from .patcher import apply_patches, unapply_patches

class ModeManager(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.reaction_toolbar = None
        self.property_toolbar = None
        self.original_splitter_sizes = None
        self.is_reaction_mode = False
        self.auto_start_pref = False
        self.action_group = None
        self.interaction_handler = None
        
        self.italic_action = None
        self.font_combo = None
        self.size_spin = None
        self.width_spin = None
        self.color_btn = None
        self._updating_props = False
        self.default_head_styles = {
            "arrow": "chevron",
            "arrow_eq": "harpoon", 
            "arrow_res": "chevron",
            "arrow_retro": "barb", 
            "arrow_no": "chevron",
            "curved_double": "chevron",
            "curved_fish": "chevron",
            "arrow_dashed": "chevron"
        }
        self.default_no_arrow_style = "slash"
        self.default_circle_shape_type = "rectangle"
        self.default_circle_line_style = "solid"
        self.default_arrow_props = {}
        self.default_bracket_type = "square"
        self.default_double_arrow_offset = 4.0
        self._last_menu_close_time = 0
        
        # Load persisted defaults
        self.load_defaults()

    def load_defaults(self):
        """Load default settings from settings.json if available."""
        settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    data = json.load(f)
                    templates = data.get("templates", {})
                    
                    # Arrow Defaults
                    if "Default_arrow" in templates:
                        defs = templates["Default_arrow"]
                        # Save whole dict for interaction.py to use
                        self.default_arrow_props = defs
                        
                        style = defs.get("head_style")
                        if style:
                            self.default_head_styles["arrow"] = style
                            self.default_head_styles["arrow_dashed"] = style
                            self.default_head_styles["curved_double"] = style
                            self.default_head_styles["curved_double"] = style
                            self.default_head_styles["curved_fish"] = style
                        
                        if "double_arrow_offset" in defs:
                             self.default_double_arrow_offset = float(defs["double_arrow_offset"])
            except: pass


    def setup_toolbar(self, context=None):
        if self.reaction_toolbar:
            return
            
        self.reaction_toolbar = QToolBar("Reaction Tools", self.main_window)
        self.reaction_toolbar.setOrientation(Qt.Orientation.Vertical)
        self.reaction_toolbar.setIconSize(QSize(32, 32))
        self.reaction_toolbar.setMovable(False)
        
        self.action_group = QActionGroup(self.main_window)
        self.action_group.setExclusive(True)
        
        # Tools

        # Select tool (Default)
        select_action = self.add_tool("Select", "select", "Select and Move Objects")
        select_action.setChecked(True)
        
        self.reaction_toolbar.addSeparator()
        
        self.add_tool("Arrow", "arrow", "Draw Reaction Arrow")
        self.add_tool("Dashed Arrow", "arrow_dashed", "Draw Dashed Arrow")
        self.add_tool("No Rxn", "arrow_no", "Draw No-Reaction Arrow")
        self.add_tool("Equilibrium", "arrow_eq", "Draw Equilibrium Arrow")
        self.add_tool("Resonance", "arrow_res", "Draw Resonance Arrow")
        self.add_tool("Retro", "arrow_retro", "Draw Retrosynthetic Arrow")

        
        self.reaction_toolbar.addSeparator()
        
        self.add_tool("Curved", "curved_double", "Draw Curved Arrow")
        self.add_tool("Fish-hook", "curved_fish", "Draw Fish-hook Arrow")
        
        self.reaction_toolbar.addSeparator()
        
        self.add_tool("Bracket", "bracket", "Place Brackets")
        self.add_tool("Circle", "circle", "Place Circle")
        
        self.reaction_toolbar.addSeparator()
        
        self.add_tool("Plus", "plus", "Place Plus Sign")
        self.add_tool("Minus", "minus", "Place Minus Sign")
        self.add_tool("Text", "text", "Add Text Box")
        
        self.reaction_toolbar.addSeparator()
        
        # Exit Button
        exit_action = self.reaction_toolbar.addAction(create_reaction_icon("exit"), "Exit Reaction Mode")
        exit_action.setProperty("tool_name", "exit")
        exit_action.triggered.connect(self.toggle_reaction_mode)
        
        self.main_window.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.reaction_toolbar)
        self.reaction_toolbar.hide()
        
        # Property Toolbar (Top)
        self.setup_property_toolbar()
        
        # Sync with main window tools
        self.sync_with_main_window()

    def sync_with_main_window(self):
        # We now use the monkey-patch on MainWindowUiManager.set_mode (see patcher.py)
        # to intercept all mode changes, including templates.
        pass

    def _handle_main_mode_change(self, mode_str):
        if not self.is_reaction_mode:
            return
            
        # Avoid infinite loops if we are the ones who triggered this change
        if self.interaction_handler and getattr(self.interaction_handler, '_internal_mode_change', False):
            return

        # Modes that should trigger setting plugin tool to Select:
        # 1. Molecular editing modes (atom_*, bond_*, etc.)
        # 2. Main application Select mode (e.g. Space key pressed)
        is_molecular_mode = (
            mode_str.startswith('atom_') or 
            mode_str.startswith('bond_') or 
            mode_str.startswith('template_') or 
            mode_str == 'charge_plus' or 
            mode_str == 'charge_minus' or 
            mode_str == 'radical'
        )
        
        should_reset_plugin_tool = is_molecular_mode or mode_str == 'select'

        if should_reset_plugin_tool:
            # Switch plugin tool to 'select'
            for action in self.action_group.actions():
                if action.property("tool_name") == "select":
                    if not action.isChecked():
                        action.setChecked(True)
                        if self.interaction_handler:
                            # We don't want to call activate_select_mode again
                            self.interaction_handler.active_tool = "select"
                    break

    def setup_property_toolbar(self):
        self.property_toolbar = QToolBar("Reaction Properties", self.main_window)
        self.property_toolbar.setIconSize(QSize(24, 24))
        
        # Font family
        self.property_toolbar.addWidget(QLabel(" Font: "))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Arial", "Times New Roman", "Courier New", "Verdana", "Impact", "Comic Sans MS"])
        self.font_combo.currentTextChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.font_combo)

        # Font settings
        self.bold_action = self.property_toolbar.addAction("B")
        self.bold_action.setCheckable(True)
        self.bold_action.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.bold_action.triggered.connect(self.apply_properties)
        
        self.italic_action = self.property_toolbar.addAction("I")
        self.italic_action.setCheckable(True)
        self.italic_action.setFont(QFont("Arial", 10, QFont.Weight.Normal, True))
        self.italic_action.triggered.connect(self.apply_properties)
        
        self.lbl_font_size = QLabel(" Font Size: ")
        self.property_toolbar.addWidget(self.lbl_font_size)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 120)
        self.font_size_spin.valueChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.font_size_spin)
        
        # Item Size (Plus / Minus)
        self.lbl_item_size = QLabel(" Size: ")
        self.property_toolbar.addWidget(self.lbl_item_size)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 200)
        self.size_spin.valueChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.size_spin)
        
        self.property_toolbar.addSeparator()
        
        # Line width
        self.property_toolbar.addWidget(QLabel(" Width: "))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.valueChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.width_spin)
        
        self.property_toolbar.addSeparator()
        
        # Color
        self.property_toolbar.addWidget(QLabel(" Color: "))
        self.color_btn = QToolButton()
        self.color_btn.setFixedSize(24, 24)
        self.color_btn.clicked.connect(self.choose_color)
        self.property_toolbar.addWidget(self.color_btn)
        self.update_color_button(QColor("#222222"))
        
        self.property_toolbar.addSeparator()

        # SVG Export
        self.property_toolbar.addAction("Export SVG", self.export_svg)
        self.property_toolbar.addAction("Copy SVG", self.copy_svg_to_clipboard)
        
        self.property_toolbar.addSeparator()

        # Advanced Settings Button
        settings_btn = self.property_toolbar.addAction("More...")
        settings_btn.triggered.connect(lambda: self.open_advanced_settings())
        
        self.main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.property_toolbar)
        self.property_toolbar.hide()
        
        # Connect selection changed
        self.main_window.scene.selectionChanged.connect(self.sync_property_toolbar)



    def export_svg(self):
        items = [i for i in self.main_window.scene.items() if hasattr(i, "create_json_data")]
        if not items:
            self.main_window.statusBar().showMessage("No reaction items to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self.main_window, "Export SVG", "", "SVG Files (*.svg)")
        if not file_path: return
        if not file_path.lower().endswith(".svg"): file_path += ".svg"

        bounds = self.get_reaction_bounds(items)
        if bounds.isEmpty(): return

        generator = QSvgGenerator()
        generator.setFileName(file_path)
        generator.setSize(QSize(int(bounds.width()), int(bounds.height())))
        generator.setViewBox(bounds)
        generator.setTitle("Reaction Sketch")
        
        # Temporarily clear selection to avoid highlights in SVG
        selected_items = self.main_window.scene.selectedItems()
        self.main_window.scene.clearSelection()

        painter = QPainter()
        painter.begin(generator)
        self.main_window.scene.render(painter, bounds, bounds)
        painter.end()
        
        # Restore selection
        for item in selected_items:
            item.setSelected(True)
            
        self.main_window.statusBar().showMessage(f"Reaction exported to {file_path}", 3000)

    def copy_svg_to_clipboard(self):
        selected = self.main_window.scene.selectedItems()
        # If nothing selected, copy everything reaction-related
        items = [i for i in (selected if selected else self.main_window.scene.items()) if hasattr(i, "create_json_data")]
        if not items:
            self.main_window.statusBar().showMessage("No reaction items selected to copy.")
            return

        bounds = self.get_reaction_bounds(items)
        if bounds.isEmpty(): return

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        
        generator = QSvgGenerator()
        generator.setOutputDevice(buffer)
        generator.setSize(QSize(int(bounds.width()), int(bounds.height())))
        generator.setViewBox(bounds)
        
        # Temporarily clear selection to avoid highlights in SVG
        self.main_window.scene.clearSelection()

        painter = QPainter()
        painter.begin(generator)
        # Render only specific items if selected
        if selected:
            # We temporarily hide others to render only selected
            to_hide = [i for i in self.main_window.scene.items() if i.isVisible() and i not in selected]
            for i in to_hide: i.hide()
            
            # Transparency Fix: Save old bg, set to NoBrush
            old_bg = self.main_window.scene.backgroundBrush()
            self.main_window.scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
            
            self.main_window.scene.render(painter, bounds, bounds)
            
            self.main_window.scene.setBackgroundBrush(old_bg)
            
            for i in to_hide: i.show()
        else:
            to_hide = [i for i in self.main_window.scene.items() if i.isVisible() and not hasattr(i, "create_json_data")]
            for i in to_hide: i.hide()
            
            # Transparency Fix
            old_bg = self.main_window.scene.backgroundBrush()
            self.main_window.scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
            
            self.main_window.scene.render(painter, bounds, bounds)
            
            self.main_window.scene.setBackgroundBrush(old_bg)
            
            for i in to_hide: i.show()
            
        painter.end()
        
        # Restore selection
        for item in selected:
            item.setSelected(True)
            
        mime = QMimeData()
        mime.setData("image/svg+xml", buffer.data())
        # Also set text for compatibility
        mime.setText(buffer.data().data().decode('utf-8'))
        self.main_window.statusBar().showMessage("Selected reaction items copied as SVG", 3000)
        QGuiApplication.clipboard().setMimeData(mime)

    def get_reaction_bounds(self, items):
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect())
        return rect.adjusted(-10, -10, 10, 10)

    def set_auto_start(self, enabled):
        self.auto_start_pref = enabled

    def choose_color(self):
        color = QColorDialog.getColor(Qt.GlobalColor.black, self.main_window, "Choose Color")
        if color.isValid():
            self.update_color_button(color)
            self.apply_properties()

    def update_color_button(self, color):
        self.color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888;")
        self.color_btn.setProperty("current_color", color)

    def sync_property_toolbar(self):
        if not self.is_reaction_mode: return
        
        # Safety check: ensure scene is not deleted
        try:
            if not self.main_window or not self.main_window.scene:
                return
            # Accessing anything on the scene might raise RuntimeError if deleted
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            # Scene or main window was deleted during teardown
            return
        from .items import (ReactionTextItem, ReactionArrowItem, ReactionBracketItem, 
                            ReactionCircleItem, ReactionPlusItem, ReactionMinusItem)
        try:
             from modules.atom_item import AtomItem
             from modules.bond_item import BondItem
        except ImportError:
             try:
                 from moleditpy.modules.atom_item import AtomItem
                 from moleditpy.modules.bond_item import BondItem
             except ImportError:
                 AtomItem = type('AtomItem', (), {})
                 BondItem = type('BondItem', (), {})
        
        reaction_items = [i for i in items if isinstance(i, (ReactionTextItem, ReactionArrowItem, ReactionBracketItem, 
                                                              ReactionCircleItem, ReactionPlusItem, ReactionMinusItem, 
                                                              AtomItem, BondItem))]
        
        if not reaction_items:
            return

        self._updating_props = True
        first = reaction_items[0]
        
        # Sync color
        color = getattr(first, "pen_color", QColor("#222222"))
        if hasattr(first, "defaultTextColor"):
            color = first.defaultTextColor()
        self.update_color_button(color)
        
        # Sync size (for text or signs)
        self.lbl_font_size.hide()
        self.font_size_spin.hide()
        self.lbl_item_size.hide()
        self.size_spin.hide()
        
        if isinstance(first, ReactionTextItem):
            f = first.font()
            idx = self.font_combo.findText(f.family())
            if idx >= 0: self.font_combo.setCurrentIndex(idx)
            self.bold_action.setChecked(f.bold())
            self.italic_action.setChecked(f.italic())
            
            self.lbl_font_size.show()
            self.font_size_spin.show()
            self.font_size_spin.setValue(int(f.pointSize()))
            
            self.font_combo.setEnabled(True)
            self.bold_action.setEnabled(True)
            self.italic_action.setEnabled(True)
            self.font_size_spin.setEnabled(True)
        elif hasattr(first, "size"):
            self.lbl_item_size.show()
            self.size_spin.show()
            self.size_spin.setValue(int(first.size))
            self.size_spin.setEnabled(True)
            
            self.font_combo.setEnabled(False)
            self.bold_action.setEnabled(False)
            self.italic_action.setEnabled(False)
        else:
            self.font_combo.setEnabled(False)
            self.bold_action.setEnabled(False)
            self.italic_action.setEnabled(False)

        # Sync width if arrow/bracket/signs
        if hasattr(first, "pen_width"):
            self.width_spin.setValue(int(first.pen_width))
            self.width_spin.setEnabled(True)
        else:
            self.width_spin.setEnabled(False)
            
        self._updating_props = False

    def apply_properties(self):
        if self._updating_props: return
        if not self.is_reaction_mode: return
        
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
        from .items import ReactionTextItem, ReactionArrowItem, ReactionBracketItem, ReactionCircleItem
        
        color = self.color_btn.property("current_color")
        family = self.font_combo.currentText()
        bold = self.bold_action.isChecked()
        italic = self.italic_action.isChecked()
        item_size = self.size_spin.value()
        font_size = self.font_size_spin.value()
        width = self.width_spin.value()
        
        for item in items:
            if isinstance(item, ReactionTextItem):
                item.setDefaultTextColor(color)
                f = item.font()
                f.setFamily(family); f.setBold(bold); f.setItalic(italic); f.setPointSize(font_size)
                item.setFont(f)
            elif isinstance(item, (ReactionArrowItem, ReactionBracketItem, ReactionCircleItem)):
                 if hasattr(item, "pen_color"): item.pen_color = color
                 if hasattr(item, "pen_width"): item.pen_width = width
            elif hasattr(item, "set_size"):
                 # Plus, Minus
                 item.set_size(item_size)
                 if hasattr(item, "pen_color"): item.pen_color = color
                 if hasattr(item, "pen_width"): item.pen_width = width
            elif hasattr(item, "pen_color"):
                 # AtomItem, BondItem
                 item.pen_color = color
            item.update()
        
        # If we modified chemical items, push to undo stack
        chemical_modified = any(not hasattr(i, "create_json_data") for i in items)
        if chemical_modified:
            if hasattr(self.main_window, 'push_undo_state'):
                self.main_window.push_undo_state()

    def add_tool(self, name, icon_name, tooltip):
        # Create action for the group to manage exclusivity
        action = self.action_group.addAction(name)
        action.setIcon(create_reaction_icon(icon_name))
        action.setToolTip(tooltip)
        action.setCheckable(True)
        action.setProperty("tool_name", icon_name)
        
        # Create button for the toolbar to support popup menus
        button = QToolButton(self.reaction_toolbar)
        button.setDefaultAction(action)
        button.setFixedSize(36, 36)
        
        # Add Style Menu for relevant tools via Right Click
        if icon_name in ["arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_no", 
                         "curved_double", "curved_fish", "bracket", "circle", "plus", "minus", "text",
                         "line", "line_curved", "freehand", "arrow_dashed"]:
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, b=button, t=icon_name: self.show_tool_context_menu(b, t, pos))

        # Handle click to toggle menu if already active
        # We need to know if it was active *before* the click.
        button.pressed.connect(lambda: self.on_tool_pressed(icon_name))
        button.clicked.connect(lambda: self.on_tool_clicked(button, icon_name))
        
        button.triggered.connect(lambda act: self.on_action_triggered(act))
        self.reaction_toolbar.addWidget(button)
        return button

    def on_tool_pressed(self, tool_name):
        # Capture state before the action toggles
        if self.interaction_handler:
            self._was_active_before_click = (self.interaction_handler.active_tool == tool_name)
        else:
            self._was_active_before_click = False

    def on_tool_clicked(self, button, tool_name):
        # If the tool WAS already active before we clicked it, show menu
        if getattr(self, '_was_active_before_click', False):
            # Check if we just closed the menu (prevents re-opening immediately on click)
            if time.time() - self._last_menu_close_time < 0.2:
                return

            # Show menu
            if tool_name in ["arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_no", 
                             "curved_double", "curved_fish", "bracket", "circle", "plus", "minus", "text",
                             "line", "line_curved", "freehand", "arrow_dashed"]:
                self.show_tool_context_menu(button, tool_name, button.rect().bottomLeft())

    def on_action_triggered(self, action):
        tool_name = action.property("tool_name")
            
        if self.interaction_handler:
            self.interaction_handler.set_tool(tool_name)
            # Ensure focus returns to view so keyboard shortcuts (Space) work immediately
            if self.main_window and hasattr(self.main_window, 'view_2d'):
                self.main_window.view_2d.setFocus()

    def show_tool_context_menu(self, button, tool_name, pos):
        menu = self.create_tool_style_menu(tool_name)
        if menu:
            menu.exec(button.mapToGlobal(pos))
            self._last_menu_close_time = time.time()

    def create_tool_style_menu(self, tool_name):
        """Create a context menu for selecting tool styles (arrowheads, negation marks, etc.)."""
        menu = QMenu(self.main_window)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; border: 1px solid #d0d0d0; border-radius: 4px; padding: 4px; }
            QMenu::item { padding: 4px 24px 4px 10px; border-radius: 2px; }
            QMenu::item:selected { background-color: #e3f2fd; color: #0078d7; }
            QMenu::separator { height: 1px; background: #e0e0e0; margin: 4px 0; }
        """)
        
        if tool_name in ["arrow", "arrow_eq", "arrow_res", "arrow_retro", "curved_double", "curved_fish", "arrow_dashed"]:
            current_style = self.default_head_styles.get(tool_name, "triangle")
            
            try:
                if self.main_window and self.main_window.scene:
                    selected = self.main_window.scene.selectedItems()
                    if selected:
                        from .items import ReactionArrowItem
                        for item in selected:
                            if isinstance(item, ReactionArrowItem):
                                if hasattr(item, "head_style"):
                                    current_style = item.head_style
                                break
            except: pass
            
            # Determine if we should show straight or curved icons based on the tool
            icon_type = "curved" if "curved" in tool_name else "straight"
            
            # Triangle head (Full / Barbless)
            act_tri = menu.addAction(create_style_icon(icon_type, "triangle", selected=(current_style == "triangle")), "Triangle (Filled)")
            act_tri.setCheckable(True)
            act_tri.setChecked(current_style == "triangle")
            act_tri.triggered.connect(lambda: self.set_head_style(tool_name, "triangle"))
            
            # Chevron head (Concave base)
            act_chevron = menu.addAction(create_style_icon(icon_type, "chevron", selected=(current_style == "chevron")), "Chevron (Concave)")
            act_chevron.setCheckable(True)
            act_chevron.setChecked(current_style == "chevron")
            act_chevron.triggered.connect(lambda: self.set_head_style(tool_name, "chevron"))

            # Harpoon head (Asymmetric / Half)
            act_harpoon = menu.addAction(create_style_icon(icon_type, "harpoon", selected=(current_style == "harpoon")), "Harpoon (Asymmetric)")
            act_harpoon.setCheckable(True)
            act_harpoon.setChecked(current_style == "harpoon")
            act_harpoon.triggered.connect(lambda: self.set_head_style(tool_name, "harpoon"))

            # Barb head (Open)
            act_barb = menu.addAction(create_style_icon(icon_type, "barb", selected=(current_style == "barb")), "Barb (Open)")
            act_barb.setCheckable(True)
            act_barb.setChecked(current_style == "barb")
            act_barb.triggered.connect(lambda: self.set_head_style(tool_name, "barb"))

        elif tool_name == "arrow_no":
            menu.addSeparator()
            
            neg_style = self.default_no_arrow_style
            try:
                if self.main_window and self.main_window.scene:
                        selected = self.main_window.scene.selectedItems()
                        for item in selected:
                            if hasattr(item, "negation_style"):
                                neg_style = item.negation_style
                                break
            except: pass

            # Slash
            act_slash = menu.addAction(create_style_icon("arrow_no", "slash", selected=(neg_style == "slash")), "Slash (/)")
            act_slash.setCheckable(True)
            act_slash.setChecked(neg_style == "slash")
            act_slash.triggered.connect(lambda: self.set_negation_style("slash"))
            # Cross
            act_cross = menu.addAction(create_style_icon("arrow_no", "cross", selected=(neg_style == "cross")), "Cross (X)")
            act_cross.setCheckable(True)
            act_cross.setChecked(neg_style == "cross")
            act_cross.triggered.connect(lambda: self.set_negation_style("cross"))

            # Double Slash
            act_dslash = menu.addAction(create_style_icon("arrow_no", "double_slash", selected=(neg_style == "double_slash")), "Double Slash (//)")
            act_dslash.setCheckable(True)
            act_dslash.setChecked(neg_style == "double_slash")
            act_dslash.triggered.connect(lambda: self.set_negation_style("double_slash"))

            if tool_name in ["curved_double", "curved_fish"]:
                menu.addSeparator()
                # Fish hook toggle
                hook_act = menu.addAction(create_style_icon("curved", "fish"), "Fish Hook (Single Barb)")
                hook_act.setCheckable(True)
                hook_act.setChecked(tool_name == "curved_fish")
                hook_act.triggered.connect(lambda checked: self.set_curved_hook_style(checked))

        elif tool_name == "bracket":
            # Bracket Sub-types
            curr_type = getattr(self, "default_bracket_type", "square")
            try:
                if self.main_window and self.main_window.scene:
                    selected = self.main_window.scene.selectedItems()
                    for item in selected:
                        if hasattr(item, "bracket_type"):
                            curr_type = item.bracket_type
                            break
            except: pass

            act_sq = menu.addAction("Square [ ]")
            act_sq.setCheckable(True)
            act_sq.setChecked(curr_type == "square")
            act_sq.triggered.connect(lambda: self.set_bracket_type("square"))

            act_rd = menu.addAction("Round ( )")
            act_rd.setCheckable(True)
            act_rd.setChecked(curr_type == "round")
            act_rd.triggered.connect(lambda: self.set_bracket_type("round"))

            act_cur = menu.addAction("Curly { }")
            act_cur.setCheckable(True)
            act_cur.setChecked(curr_type == "curly")
            act_cur.triggered.connect(lambda: self.set_bracket_type("curly"))
            
        elif tool_name == "circle":
            # 4 Options: Solid Rect, Dashed Rect, Solid Circle, Dashed Circle
            curr_shape = "rectangle"
            curr_style = "solid"
            try:
                if self.main_window and self.main_window.scene:
                    selected = self.main_window.scene.selectedItems()
                    for item in selected:
                        if hasattr(item, "shape_type") and not hasattr(item, "bracket_type"):
                            curr_shape = item.shape_type
                            curr_style = getattr(item, "line_style", "solid")
                            break
            except: pass

            variants = [
                ("Solid Rectangle", "rectangle", "solid"),
                ("Dashed Rectangle", "rectangle", "dashed"),
                ("Solid Circle / Ellipse", "circle", "solid"),
                ("Dashed Circle / Ellipse", "circle", "dashed")
            ]
            
            for label, stype, lstyle in variants:
                act = menu.addAction(create_shape_variant_icon(stype, lstyle), label)
                act.setCheckable(True)
                act.setChecked(curr_shape == stype and curr_style == lstyle)
                def make_cb(s, l): return lambda: self.set_circle_variant(s, l)
                act.triggered.connect(make_cb(stype, lstyle))
            
            menu.addSeparator()

        # "Switch Tool" section for common grouping
        if tool_name in ["circle", "line", "line_dashed", "line_curved", "freehand"]:
            if menu.actions():
                menu.addSeparator()
            
            tools = [
                ("Straight Line", "line"),
                ("Dashed Line", "line_dashed"),
                ("Curved Line", "line_curved"),
                ("Freehand", "freehand")
            ]
            
            for label, t_name in tools:
                act = menu.addAction(create_reaction_icon(t_name), label)
                act.setCheckable(True)
                act.setChecked(tool_name == t_name)
                # Use a closure or separate method to avoid late binding issues
                def make_trigger(tn): return lambda: self.activate_tool_by_name(tn)
                act.triggered.connect(make_trigger(t_name))



        return menu

    def activate_tool_by_name(self, tool_name):
        if self.interaction_handler:
            self.interaction_handler.set_tool(tool_name)
            for action in self.action_group.actions():
                if action.property("tool_name") == tool_name:
                    action.setChecked(True)
                    break
            # Return focus
            if self.main_window and hasattr(self.main_window, 'view_2d'):
                self.main_window.view_2d.setFocus()

    def eventFilter(self, obj, event):
        # Handle ShortcutOverride to block main window shortcuts while editing text
        if event.type() == QEvent.Type.ShortcutOverride:
            if self._shortcuts_disabled:
                # Double check focus
                try:
                    focus_item = self.main_window.scene.focusItem()
                    from .items import ReactionTextItem
                    if isinstance(focus_item, ReactionTextItem) and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction):
                        event.accept()
                        return True
                except: pass
        return super().eventFilter(obj, event)

    def disable_main_window_shortcuts(self):
        """Temporarily disable main window shortcuts to allow text editing."""
        if self._shortcuts_disabled:
            return
            
        self._disabled_actions_state = []
        if not self.main_window: return
            
        # 1. Disable QActions
        for action in self.main_window.findChildren(QAction):
            # Skip our tool actions
            is_plugin_action = False
            if self.reaction_toolbar and action.parent() == self.reaction_toolbar:
                is_plugin_action = True
            if self.property_toolbar and action.parent() == self.property_toolbar:
                is_plugin_action = True
                
            if not is_plugin_action and action.shortcut() and not action.shortcut().isEmpty():
                if action.isEnabled():
                    self._disabled_actions_state.append(action)
                    action.setEnabled(False)
        
        # 2. Block direct key events via Event Filter
        self._shortcuts_disabled = True
        self.main_window.installEventFilter(self)

    def enable_main_window_shortcuts(self):
        """Restore main window shortcuts."""
        if not self._shortcuts_disabled:
            return
            
        if self.main_window:
            # 1. Restore QActions
            if hasattr(self, "_disabled_actions_state"):
                for action in self._disabled_actions_state:
                    try:
                        action.setEnabled(True)
                    except: pass
                self._disabled_actions_state = []
            
            # 2. Remove Event Filter
            self.main_window.removeEventFilter(self)
            
        self._shortcuts_disabled = False

    def open_advanced_settings(self, tool_name=None):
        """Open the advanced settings dialog for the selected item or current tool defaults."""
        from .settings_dialog import AdvancedSettingsDialog
        
        # Determine target item (first selected or a dummy for defaults)
        target_item = None
        if self.main_window and self.main_window.scene:
            items = self.main_window.scene.selectedItems()
            if items:
                 target_item = items[0]
        
        # If no item selected, we might want to configure defaults given the tool_name?
        # But dialog requires an item to read properties from. 
        # For now, let's require selection or create a dummy item of that type.
        if not target_item:
           # Create dummy item for default editing? 
           # Actually, simpler to just edit selected item.
           pass

        if target_item:
            dlg = AdvancedSettingsDialog(self.main_window, target_item)
            if dlg.exec():
                settings = dlg.get_settings()
                self._updating_props = True
                
                # Apply settings to all selected items
                for item in self.main_window.scene.selectedItems():
                    if "color" in settings:
                        if hasattr(item, "pen_color"):
                            item.pen_color = QColor(settings["color"])
                        if hasattr(item, "setDefaultTextColor"):
                            item.setDefaultTextColor(QColor(settings["color"]))
                            
                    if "width" in settings and hasattr(item, "pen_width"):
                        item.pen_width = settings["width"]
                    if "head_size" in settings and hasattr(item, "head_size"):
                        item.head_size = settings["head_size"]
                    if "head_angle" in settings and hasattr(item, "head_angle"):
                        item.head_angle = settings["head_angle"]
                    if "head_concavity" in settings and hasattr(item, "head_concavity"):
                         item.head_concavity = settings["head_concavity"]
                    if "curvature" in settings and hasattr(item, "curvature"):
                         item.curvature = settings["curvature"]
                    if "bracket_type" in settings and hasattr(item, "bracket_type"):
                         item.bracket_type = settings["bracket_type"]
                    
                    if hasattr(item, "sync_handles"):
                        item.sync_handles()
                    item.update()
                
                self._updating_props = False
                self.sync_property_toolbar()
                
                if self.main_window:
                    self.main_window.push_undo_state()

    def set_head_style(self, tool_name, style):
        self.default_head_styles[tool_name] = style
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
            
        from .items import (ReactionArrowItem, ReactionDashedArrowItem, 
                            ReactionResonanceArrowItem, ReactionEquilibriumArrowItem, 
                            ReactionRetroArrowItem, ReactionCurvedArrowItem)
        
        # Mapping tool_name to class
        tool_map = {
            "arrow": ReactionArrowItem,
            "arrow_dashed": ReactionDashedArrowItem,
            "arrow_res": ReactionResonanceArrowItem,
            "arrow_eq": ReactionEquilibriumArrowItem,
            "arrow_retro": ReactionRetroArrowItem,
            "curved_double": ReactionCurvedArrowItem,
            # "curved_fish": ReactionCurvedArrowItem # handled separately or via is_fish_hook
        }
        
        target_class = tool_map.get(tool_name)
        
        modified = False
        scene = self.main_window.scene
        
        # We collect updates to avoid modifying list while iterating if we were replacing?
        # Safe to iterate copy or index?
        # Only replacing produces new items. 
        
        for item in list(items): # copy list
            if not isinstance(item, ReactionArrowItem):
                continue
                
            # Check if conversion is needed
            # We convert if the current item class differs from the target tool's class
            # Exception: ReactionCurvedArrowItem handles both curved_double and curved_fish?
            # actually curved_fish is not usually passed to set_head_style unless we add it to map.
            # set_head_style is called for "arrow", "arrow_dashed", etc.
            
            should_convert = False
            if target_class and not isinstance(item, target_class):
                # Basic mismatch (e.g. Arrow vs Dashed)
                should_convert = True
                
            # Special case: Don't convert Curved -> Straight or vice versa implicitly unless desired?
            # User request: "different kinds of arrows... change the type".
            # So if I have Curved selected and click "Arrow (Straight)" style, it should become Straight.
            
            if should_convert:
                # Create new item
                old_state = item.create_json_data()
                new_item = target_class(item.start_p, item.end_p)
                
                # Copy properties
                if hasattr(new_item, "pen_color") and "color" in old_state:
                     new_item.pen_color = QColor(old_state["color"])
                if hasattr(new_item, "pen_width") and "width" in old_state:
                     new_item.pen_width = old_state["width"]
                if hasattr(new_item, "head_size") and "head_size" in old_state:
                     new_item.head_size = old_state["head_size"]
                if hasattr(new_item, "head_angle") and "head_angle" in old_state:
                     new_item.head_angle = old_state["head_angle"]
                if hasattr(new_item, "head_concavity") and "head_concavity" in old_state:
                     new_item.head_concavity = old_state["head_concavity"]
                
                # Special handling for curved
                if isinstance(new_item, ReactionCurvedArrowItem):
                     if "cp_x" in old_state:
                         # Try to preserve curve?
                         # If converting Straight -> Curved, start/end is fine. Control point needs default.
                         # If Curved -> Curved (e.g. Double -> Fish?), not hitting this block usually (same class)
                         pass
                
                # Set new style
                new_item.head_style = style
                
                # Replace in scene
                scene.addItem(new_item)
                scene.removeItem(item)
                new_item.setSelected(True)
                modified = True
                
            else:
                # Same type, just update style
                if hasattr(item, "head_style"):
                    item.head_style = style
                    item.update()
                    modified = True
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool(tool_name)
             for action in self.action_group.actions():
                 if action.property("tool_name") == tool_name:
                     if not action.isChecked():
                         action.setChecked(True)
                     break
                     
        if modified:
            self.main_window.push_undo_state()

    def set_text_size(self, size):
        self.size_spin.setValue(size)
        self.apply_properties()

    def set_sign_size(self, size):
        items = self.main_window.scene.selectedItems()
        from .items import ReactionPlusItem, ReactionMinusItem
        for item in items:
            if isinstance(item, (ReactionPlusItem, ReactionMinusItem)):
                item.size = size
                item.update()
        if items:
            self.main_window.push_undo_state()

    def set_negation_style(self, style):
        self.default_no_arrow_style = style
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
        from .items import ReactionNoArrowItem
        modified = False
        for item in items:
            if isinstance(item, ReactionNoArrowItem):
                item.negation_style = style
                item.update()
                modified = True
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool("arrow_no")
             for action in self.action_group.actions():
                 if action.property("tool_name") == "arrow_no":
                     if not action.isChecked():
                         action.setChecked(True)
                     break
                     
        if modified:
            self.main_window.push_undo_state()

    def set_curved_hook_style(self, is_fish):
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
        from .items import ReactionCurvedArrowItem
        new_tool = "curved_fish" if is_fish else "curved_double"
        for item in items:
            if isinstance(item, ReactionCurvedArrowItem):
                item.is_fish_hook = is_fish
                item.update()
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool(new_tool)
             for action in self.action_group.actions():
                 if action.property("tool_name") == new_tool:
                     action.setChecked(True)
                     break

        self.main_window.push_undo_state()

    def set_bracket_type(self, btype):
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except: return
        
        from .items import ReactionBracketItem
        modified = False
        for item in items:
            if isinstance(item, ReactionBracketItem):
                item.bracket_type = btype
                item.update()
                modified = True
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool("bracket")
             for action in self.action_group.actions():
                 if action.property("tool_name") == "bracket":
                     action.setChecked(True)
                     break
                     
        if modified:
            self.main_window.push_undo_state()

    def set_circle_variant(self, shape_type, line_style):
        self.default_circle_shape_type = shape_type
        self.default_circle_line_style = line_style
        try:
            if not self.main_window or not self.main_window.scene: return
            selected = self.main_window.scene.selectedItems()
            from .items import ReactionCircleItem
            modified = False
            for item in selected:
                if isinstance(item, ReactionCircleItem):
                    item.shape_type = shape_type
                    item.line_style = line_style
                    item.update()
                    modified = True
            
            # Activate tool
            if self.interaction_handler:
                 self.interaction_handler.set_tool("circle")
                 for action in self.action_group.actions():
                     if action.property("tool_name") == "circle":
                         action.setChecked(True)
                         break
            if modified:
                self.main_window.push_undo_state()
        except: pass

    def set_curved_head_style(self, style):
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
        from .items import ReactionCurvedArrowItem
        for item in items:
            if isinstance(item, ReactionCurvedArrowItem):
                item.head_style = style
                item.update()
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             curr = self.interaction_handler.active_tool
             if curr not in ["curved_double", "curved_fish"]:
                 self.interaction_handler.set_tool("curved_double")
                 for action in self.action_group.actions():
                     if action.property("tool_name") == "curved_double":
                         action.setChecked(True)
                         break

        self.main_window.push_undo_state()

    def set_bracket_type(self, b_type):
        self.default_bracket_type = b_type
        
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
            
        from .items import ReactionBracketItem
        modified = False
        for item in items:
            if isinstance(item, ReactionBracketItem):
                item.bracket_type = b_type
                # Adjust boundingRect/shape via prepareGeometryChange which item property setter should handle if implemented, 
                # but direct attribute access might not triggers update.
                # ReactionBracketItem doesn't seem to have property setter for bracket_type that calls update
                item.prepareGeometryChange()
                item.update()
                modified = True
                
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool("bracket")
             for action in self.action_group.actions():
                 if action.property("tool_name") == "bracket":
                     action.setChecked(True)
                     break
                     
        if modified:
            self.main_window.push_undo_state()

    def set_tool_thickness(self, t):
        self.width_spin.setValue(t)
        self.apply_properties()

    def set_tool_color(self, color):
        self.update_color_button(color)
        self.apply_properties()

    def toggle_reaction_mode(self):
        new_state = not self.is_reaction_mode
        
        if not new_state:
            # Check for reaction items before exiting
            items = [i for i in self.main_window.scene.items() if hasattr(i, "create_json_data")]
            if items:
                reply = QMessageBox.question(
                    self.main_window, 
                    "Confirm Exit",
                    "Reaction objects are present in the scene. Are you sure you want to exit Reaction Sketching Mode?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

        self.is_reaction_mode = new_state
        if self.is_reaction_mode:
            self.enter_reaction_mode()
        else:
            self.exit_reaction_mode()


    def enter_reaction_mode(self):
        # Save original layout
        self.original_splitter_sizes = self.main_window.splitter.sizes()
        
        # Unselect main window tool (e.g., templates, atoms)
        if hasattr(self.main_window, 'activate_select_mode'):
            self.main_window.activate_select_mode()
        
        # Maximize 2D view (index 0 usually 2D, index 1 usually 3D)
        if self.main_window.splitter.count() > 1:
            self.main_window.splitter.setSizes([1000, 0])
        
        # Show reaction toolbar
        if self.reaction_toolbar:
            self.reaction_toolbar.show()
        if self.property_toolbar:
            self.property_toolbar.show()
            
        # Apply patches (safe to call multiple times)
        apply_patches(self.main_window)
            
        self.set_3d_action_state(False)
        self.main_window.statusBar().showMessage("Reaction Sketching Mode Active", 3000)

    def exit_reaction_mode(self):
        # Restore layout
        if self.original_splitter_sizes:
            self.main_window.splitter.setSizes(self.original_splitter_sizes)
        else:
            # Fallback to 50/50
            total = sum(self.main_window.splitter.sizes())
            self.main_window.splitter.setSizes([total//2, total//2])
            
        # Hide reaction toolbar
        if self.reaction_toolbar:
            self.reaction_toolbar.hide()
        if self.property_toolbar:
            self.property_toolbar.hide()
            
        self.set_3d_action_state(True)
        self.main_window.statusBar().showMessage("Returned to Molecular Mode", 3000)
        self.is_reaction_mode = False
        
        # Reset tool to Select
        for action in self.action_group.actions():
            if action.property("tool_name") == "select":
                action.setChecked(True)
                if self.interaction_handler:
                    self.interaction_handler.set_tool("select")
                break
        
        # Unapply patches (restore original behavior)
        unapply_patches(self.main_window)

    def set_3d_action_state(self, enabled):
        # 1. Disable the specific buttons found in main_window_main_init.py
        if self.main_window:
            if hasattr(self.main_window, 'convert_button'):
                self.main_window.convert_button.setEnabled(enabled)
            
            if hasattr(self.main_window, 'optimize_3d_button'):
                # optimize_3d_button is usually disabled by default until 3D exists, 
                # but we should force disable it if in reaction mode
                if not enabled:
                    self.main_window.optimize_3d_button.setEnabled(False)
                else:
                    # When re-enabling, we should respect its check_enable_3d_features logic?
                    # For now just let the main window handle its state, or leave it disabled specific to reaction mode.
                    # The main window usually manages this button's state based on molecule existence.
                    # A safe bet is to only explicitly DISABLE it. Re-enabling might be tricky if it should remain disabled.
                    # Let's just trigger a UI update if possible, or do nothing.
                    # Actually, if we disable it, we must be able to re-enable it if valid.
                    # Let's trust the main window's update loop to re-enable it if needed, 
                    # OR just set it enabled=True if there is a molecule? 
                    # Simpler: Just target convert_button as requested.
                    pass

        # 2. Try to find other actions (menus)
        if not hasattr(self, '_3d_actions'):
            self._3d_actions = []
            # Common names
            for name in ['action_3d', 'act_3d', 'action_convert_to_3d', 'convert_3d_action', 
                         'action_convert_to_3d', 'edit_3d_action']:
                if hasattr(self.main_window, name):
                    self._3d_actions.append(getattr(self.main_window, name))
            
        for action in self._3d_actions:
            action.setEnabled(enabled)

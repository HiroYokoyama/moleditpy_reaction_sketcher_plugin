#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtWidgets import (QToolBar, QToolButton, QSizePolicy, 
                             QComboBox, QSpinBox, QCheckBox, QHBoxLayout, QWidget, QLabel, 
                             QColorDialog, QFileDialog, QMessageBox)
from PyQt6.QtGui import QIcon, QColor, QFont, QPainter, QBrush, QActionGroup, QGuiApplication
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtCore import Qt, QSize, QRectF, QBuffer, QIODevice, QMimeData, QPoint
from .icons import create_reaction_icon

class ModeManager:
    def __init__(self, main_window):
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
        self.add_tool("Equilibrium", "arrow_eq", "Draw Equilibrium Arrow")
        self.add_tool("Resonance", "arrow_res", "Draw Resonance Arrow")
        self.add_tool("Retro", "arrow_retro", "Draw Retrosynthetic Arrow")
        self.add_tool("No Rxn", "arrow_no", "Draw No-Reaction Arrow")
        
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
        # If any of the main window's molecular tools are clicked, we exit reaction mode
        if hasattr(self.main_window, 'mode_actions'):
            for mode, action in self.main_window.mode_actions.items():
                if mode != 'select':
                    action.triggered.connect(self._on_main_tool_selected)

    def _on_main_tool_selected(self):
        if self.is_reaction_mode:
            # If user selects a main tool (C, H, Bond, Template), we exit reaction mode
            self.exit_reaction_mode()

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
        
        self.property_toolbar.addWidget(QLabel(" Size: "))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
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
        settings_btn.triggered.connect(self.open_advanced_settings)
        
        self.main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.property_toolbar)
        self.property_toolbar.hide()
        
        # Connect selection changed
        self.main_window.scene.selectionChanged.connect(self.sync_property_toolbar)

    def open_advanced_settings(self):
        items = self.main_window.scene.selectedItems()
        if not items: return
        
        from .settings_dialog import AdvancedSettingsDialog
        dialog = AdvancedSettingsDialog(self.main_window, items[0])
        if dialog.exec():
            settings = dialog.get_settings()
            self._updating_props = True # Avoid recursion if we manually set some toolbar props
            # Apply to all selected
            bold = self.bold_action.isChecked()
            italic = self.italic_action.isChecked()
            size = self.size_spin.value()
            family = self.font_combo.currentText()
            
            for item in items:
                # Use settings from dialog
                if "color" in settings:
                    if hasattr(item, "pen_color"): item.pen_color = settings["color"]
                    if hasattr(item, "setDefaultTextColor"): item.setDefaultTextColor(settings["color"])
                if "width" in settings:
                    if hasattr(item, "pen_width"): item.pen_width = settings["width"]
                item.update()
            
            self._updating_props = False
            self.sync_property_toolbar()

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
            self.main_window.scene.render(painter, bounds, bounds)
            for i in to_hide: i.show()
        else:
            to_hide = [i for i in self.main_window.scene.items() if i.isVisible() and not hasattr(i, "create_json_data")]
            for i in to_hide: i.hide()
            self.main_window.scene.render(painter, bounds, bounds)
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
        if isinstance(first, ReactionTextItem):
            f = first.font()
            idx = self.font_combo.findText(f.family())
            if idx >= 0: self.font_combo.setCurrentIndex(idx)
            self.bold_action.setChecked(f.bold())
            self.italic_action.setChecked(f.italic())
            self.size_spin.setValue(int(f.pointSize()))
            self.font_combo.setEnabled(True)
            self.bold_action.setEnabled(True)
            self.italic_action.setEnabled(True)
            self.size_spin.setEnabled(True)
        elif hasattr(first, "size"):
            self.size_spin.setValue(int(first.size))
            self.size_spin.setEnabled(True)
            self.font_combo.setEnabled(False)
            self.bold_action.setEnabled(False)
            self.italic_action.setEnabled(False)
        else:
            self.size_spin.setEnabled(False)
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
        size = self.size_spin.value()
        width = self.width_spin.value()
        
        for item in items:
            if isinstance(item, ReactionTextItem):
                item.setDefaultTextColor(color)
                f = item.font()
                f.setFamily(family); f.setBold(bold); f.setItalic(italic); f.setPointSize(size)
                item.setFont(f)
            elif isinstance(item, (ReactionArrowItem, ReactionBracketItem, ReactionCircleItem)):
                 if hasattr(item, "pen_color"): item.pen_color = color
                 if hasattr(item, "pen_width"): item.pen_width = width
            elif hasattr(item, "set_size"):
                 item.set_size(size)
                 if hasattr(item, "pen_color"): item.pen_color = color
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
        
        # Add Style Menu for relevant tools
        if icon_name in ["arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_no", 
                         "curved_double", "curved_fish", "bracket", "circle", "plus", "minus", "text"]:
            button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            menu = self.create_tool_style_menu(icon_name)
            button.setMenu(menu)

        button.triggered.connect(lambda act: self.on_action_triggered(act))
        self.reaction_toolbar.addWidget(button)
        return button

    def on_action_triggered(self, action):
        tool_name = action.property("tool_name")
        if self.interaction_handler:
            self.interaction_handler.set_tool(tool_name)

    def create_tool_style_menu(self, tool_name):
        from PyQt6.QtWidgets import QMenu
        from .icons import create_style_icon
        menu = QMenu(self.main_window)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; border: 1px solid #d0d0d0; border-radius: 4px; padding: 4px; }
            QMenu::item { padding: 4px 24px 4px 10px; border-radius: 2px; }
            QMenu::item:selected { background-color: #e3f2fd; color: #0078d7; }
            QMenu::separator { height: 1px; background: #e0e0e0; margin: 4px 0; }
        """)
        
        if tool_name == "arrow_no":
            # Slash
            act_slash = menu.addAction(create_style_icon("arrow_no", "slash"), "Slash Style")
            act_slash.triggered.connect(lambda: self.set_arrow_no_style("slash"))
            # Cross
            act_cross = menu.addAction(create_style_icon("arrow_no", "cross"), "Cross Style")
            act_cross.triggered.connect(lambda: self.set_arrow_no_style("cross"))
        
        if tool_name in ["curved_double", "curved_fish"]:
            # Triangle head
            act_tri = menu.addAction(create_style_icon("curved", "triangle"), "Triangular Head")
            act_tri.setCheckable(True)
            # We need to peek at selected or default to set checked
            act_tri.triggered.connect(lambda checked: self.set_curved_head_style("triangle" if checked else "barb"))
            
            menu.addSeparator()
            
            # Fish hook toggle
            hook_act = menu.addAction(create_style_icon("curved", "fish"), "Fish Hook (Single Barb)")
            hook_act.setCheckable(True)
            hook_act.setChecked(tool_name == "curved_fish")
            hook_act.triggered.connect(lambda checked: self.set_curved_hook_style(checked))

        return menu

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

    def set_arrow_no_style(self, style):
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return
        from .items import ReactionNoArrowItem
        for item in items:
            if isinstance(item, ReactionNoArrowItem):
                item.negation_style = style
                item.update()
        
        # ACTIVATE TOOL
        if self.interaction_handler:
             self.interaction_handler.set_tool("arrow_no")
             for action in self.action_group.actions():
                 if action.property("tool_name") == "arrow_no":
                     action.setChecked(True)
                     break
                     
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

    def set_tool_thickness(self, t):
        self.width_spin.setValue(t)
        self.apply_properties()

    def set_tool_color(self, color):
        self.update_color_button(color)
        self.apply_properties()

    def toggle_reaction_mode(self):
        self.is_reaction_mode = not self.is_reaction_mode
        
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
        # Check index just in case
        if self.main_window.splitter.count() > 1:
            self.main_window.splitter.setSizes([1000, 0])
        
        # Show reaction toolbar
        if self.reaction_toolbar:
            self.reaction_toolbar.show()
        if self.property_toolbar:
            self.property_toolbar.show()
            
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
            
        self.main_window.statusBar().showMessage("Returned to Molecular Mode", 3000)
        self.is_reaction_mode = False
        
        # Reset tool to Select
        for action in self.action_group.actions():
            if action.property("tool_name") == "select":
                action.setChecked(True)
                if self.interaction_handler:
                    self.interaction_handler.set_tool("select")
                break

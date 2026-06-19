#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import uuid
from PyQt6.QtWidgets import (
    QToolBar,
    QToolButton,
    QComboBox,
    QSpinBox,
    QGridLayout,
    QWidget,
    QLabel,
    QColorDialog,
    QMessageBox,
    QMenu,
)
from PyQt6.QtGui import (
    QIcon,
    QColor,
    QFont,
    QPainter,
    QBrush,
    QActionGroup,
    QGuiApplication,
    QAction,
    QShortcut,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QFontDatabase,
    QImage,
)
from PyQt6.QtSvg import QSvgGenerator
from PyQt6.QtCore import (
    Qt,
    QSize,
    QRectF,
    QBuffer,
    QIODevice,
    QMimeData,
    QPoint,
    QPointF,
    QObject,
    QEvent,
    QFile,
)

from .utils import sip_isdeleted_safe
from .icons import (
    create_reaction_icon,
    create_shape_variant_icon,
    create_style_icon,
    create_alignment_icon,
)
from .patcher import apply_interaction_patches, apply_core_patches, revert_all_patches
from .items import (
    ReactionTextItem,
    ReactionArrowItem,
    ReactionDashedArrowItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionCurvedArrowItem,
)
import logging


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
            "arrow_retro": "chevron",
            "arrow_no": "chevron",
            "curved_double": "chevron",
            "curved_fish": "chevron",
            "arrow_dashed": "chevron",
        }
        self.default_no_arrow_style = "slash"
        self.default_circle_shape_type = "circle"
        self.default_circle_line_style = "solid"
        self.default_arrow_props = {}
        self.default_bracket_type = "square"
        self.default_double_arrow_offset = 4.0
        self._last_menu_close_time = 0

        # Load persisted defaults
        self.load_defaults()
        self.setup_shortcuts()

    def load_defaults(self):
        """Load default settings from settings.json if available."""
        self.default_props = {}  # Store all type-specific defaults

        settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    data = json.load(f)
                    templates = data.get("templates", {})

                    # Iterate all keys to find Default_{type}
                    for key, val in templates.items():
                        if key.startswith("Default_"):
                            item_type = key[len("Default_") :]
                            self.default_props[item_type] = val

                            # Legacy Support: Update individual properties where applicable
                            if item_type == "arrow":
                                style = val.get("head_style", None)
                                if style:
                                    self.default_head_styles["arrow"] = style
                                    self.default_head_styles["arrow_dashed"] = style
                                    self.default_head_styles["curved_double"] = style
                                    self.default_head_styles["curved_fish"] = style

                                # Also update specialized defaults
                                if "double_arrow_offset" in val:
                                    self.default_double_arrow_offset = float(
                                        val["double_arrow_offset"]
                                    )

                            elif item_type == "arrow_eq":
                                style = val.get("head_style", None)
                                if style:
                                    self.default_head_styles["arrow_eq"] = style
                                if "double_arrow_offset" in val:
                                    self.default_double_arrow_offset = float(
                                        val["double_arrow_offset"]
                                    )

                            elif item_type == "arrow_res":
                                style = val.get("head_style", None)
                                if style:
                                    self.default_head_styles["arrow_res"] = style

                            elif item_type == "arrow_retro":
                                style = val.get("head_style", None)
                                if style:
                                    self.default_head_styles["arrow_retro"] = style

                            elif item_type == "arrow_no":
                                style = val.get("head_style", None)
                                if style:
                                    self.default_head_styles["arrow_no"] = style
                                if "negation_style" in val:
                                    self.default_no_arrow_style = val["negation_style"]
                                if "cross_size" in val:
                                    # We don't have a specific attribute for this in mode_manager
                                    # but it will be in self.default_props["arrow_no"] automatically
                                    # because we store 'val' into default_props.
                                    pass

                            elif item_type == "bracket":
                                if "bracket_type" in val:
                                    self.default_bracket_type = val["bracket_type"]

                            elif item_type == "circle":
                                if "shape_type" in val:
                                    self.default_circle_shape_type = val["shape_type"]
                                if "line_style" in val:
                                    self.default_circle_line_style = val["line_style"]

            except Exception as e:
                # print(f"Error loading defaults: {e}")
                logging.warning("[mode_manager.py:138] silenced: %s", e)

    def setup_shortcuts(self):
        """Setup keyboard shortcuts for grouping etc."""
        self.group_shortcut = QShortcut(QKeySequence("Ctrl+G"), self.main_window)
        self.group_shortcut.activated.connect(self.group_selected_items)

        # Store clipboard for reaction items
        self.reaction_clipboard = []

        self.ungroup_shortcut = QShortcut(QKeySequence("Ctrl+U"), self.main_window)
        self.ungroup_shortcut.activated.connect(self.ungroup_selected_items)

    def _find_menu_action(self, text):
        """Find a QAction by exact text from the main menu tree."""
        menu_bar = self.main_window.menuBar()
        if not menu_bar:
            return None

        def _search(menu):
            for action in menu.actions():
                if action.text() == text:
                    return action
                sub = action.menu()
                if sub:
                    found = _search(sub)
                    if found:
                        return found
            return None

        for top_action in menu_bar.actions():
            menu = top_action.menu()
            if not menu:
                continue
            found = _search(menu)
            if found:
                return found
        return None

    def _rewire_cleanup_2d_triggers(self):
        """Ensure UI triggers call the currently active clean_up_2d method."""
        mgr = getattr(self.main_window, "edit_actions_manager", None)
        if mgr:
            target = mgr.clean_up_2d_structure
        else:
            print("Error: main_window missing 'edit_actions_manager'")
            return

        btn = getattr(self.main_window.init_manager, "cleanup_button", None)
        if btn is not None:
            try:
                btn.clicked.disconnect()
            except Exception as _e:
                logging.warning("[mode_manager.py:192] silenced: %s", _e)
            btn.clicked.connect(target)
        else:
            print("Error: init_manager missing 'cleanup_button'")

        cleanup_action = self._find_menu_action("Clean Up 2D")
        if cleanup_action is not None:
            try:
                cleanup_action.triggered.disconnect()
            except Exception as _e:
                logging.warning("[mode_manager.py:202] silenced: %s", _e)
            cleanup_action.triggered.connect(target)
        else:
            print("Error: 'Clean Up 2D' action not found in menu")

    def setup_toolbar(self, context=None):
        if self.reaction_toolbar:
            return

        self.reaction_toolbar = QToolBar("Reaction Tools", self.main_window)
        self.reaction_toolbar.setOrientation(Qt.Orientation.Vertical)
        self.reaction_toolbar.setMovable(False)

        # Create a container widget to hold the grid of buttons
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.action_group = QActionGroup(self.main_window)
        self.action_group.setExclusive(True)

        # Tools List for Grid
        # (Label/Tooltip, ToolName, ActionName(opt))
        # Helper to add separator
        def add_separator(layout, row):
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(sep, row, 0, 1, 2)
            return row + 1

        # Tool Categories
        # Each category: (Name, List of Tools)
        # Tool: (Label, ToolName, Tooltip)
        categories = [
            (
                "Selection",
                [
                    ("Select", "select", "Select and Move Objects"),
                ],
            ),
            (
                "Grouping",
                [
                    ("Group", "group", "Group Selected Items"),
                    ("Ungroup", "ungroup", "Ungroup Selected Items"),
                ],
            ),
            (
                "Basic Arrows",
                [
                    ("Arrow", "arrow", "Draw Reaction Arrow"),
                    ("Dashed Arrow", "arrow_dashed", "Draw Dashed Arrow"),
                    ("No Rxn", "arrow_no", "Draw No-Reaction Arrow"),
                    ("Equilibrium", "arrow_eq", "Draw Equilibrium Arrow"),
                    ("Resonance", "arrow_res", "Draw Resonance Arrow"),
                    ("Retro", "arrow_retro", "Draw Retrosynthetic Arrow"),
                ],
            ),
            (
                "Curved Arrows",
                [
                    ("Curved", "curved_double", "Draw Curved Arrow"),
                    ("Fish-hook", "curved_fish", "Draw Fish-hook Arrow"),
                ],
            ),
            (
                "Shapes",
                [
                    ("Bracket", "bracket", "Place Brackets"),
                    (
                        "Circle",
                        "circle",
                        "Place Circle / Rectangle (Right-click for options)",
                    ),
                ],
            ),
            (
                "Text & Signs",
                [
                    ("Plus", "plus", "Place Plus Sign"),
                    ("Minus", "minus", "Place Minus Sign"),
                    ("Text", "text", "Add Text Box"),
                ],
            ),
        ]

        row = 0
        from PyQt6.QtWidgets import QFrame

        # Define Alignment Tools
        align_tools = [
            ("align_top", "Align Top", lambda: self.align_items("top")),
            ("align_left", "Align Left", lambda: self.align_items("left")),
            (
                "align_center_v",
                "Align Vertical Center",
                lambda: self.align_items("center_v"),
            ),
            (
                "align_center_h",
                "Align Horizontal Center",
                lambda: self.align_items("center_h"),
            ),
            ("align_bottom", "Align Bottom", lambda: self.align_items("bottom")),
            ("align_right", "Align Right", lambda: self.align_items("right")),
            (
                "distribute_v",
                "Distribute Vertically",
                lambda: self.distribute_items("vertical"),
            ),
            (
                "distribute_h",
                "Distribute Horizontally",
                lambda: self.distribute_items("horizontal"),
            ),
        ]

        for cat_name, tools in categories:
            col = 0
            for label, name, tooltip in tools:
                is_action = name in ["group", "ungroup"]

                btn = QToolButton()
                btn.setCheckable(not is_action)
                btn.setIconSize(QSize(32, 32))
                btn.setToolTip(tooltip)

                # Create Action
                action = QAction(self.main_window)
                action.setCheckable(not is_action)
                action.setText(label)
                action.setToolTip(tooltip)
                action.setProperty("tool_name", name)

                if name == "group":
                    action.triggered.connect(self.group_selected_items)
                elif name == "ungroup":
                    action.triggered.connect(self.ungroup_selected_items)
                else:
                    action.triggered.connect(
                        lambda checked, a=action: self.on_action_triggered(a)
                    )

                # Load Icon
                icon_path = os.path.join(
                    os.path.dirname(__file__), "icons", f"{name}.png"
                )
                if os.path.exists(icon_path):
                    action.setIcon(QIcon(icon_path))
                else:
                    # Fallback to generated icon
                    action.setIcon(create_reaction_icon(name))

                self.action_group.addAction(action)
                btn.setDefaultAction(action)

                # Add Click-again (Left Click) support for tool options
                if name in [
                    "arrow",
                    "arrow_eq",
                    "arrow_res",
                    "arrow_retro",
                    "arrow_no",
                    "curved_double",
                    "curved_fish",
                    "bracket",
                    "circle",
                    "plus",
                    "minus",
                    "text",
                    "line",
                    "line_curved",
                    "freehand",
                    "arrow_dashed",
                ]:
                    btn.pressed.connect(lambda act=action: self.on_tool_pressed(act))
                    btn.clicked.connect(
                        lambda _, b=btn, act=action: self.on_tool_clicked(b, act)
                    )

                layout.addWidget(btn, row, col)
                col += 1
                if col > 1:
                    col = 0
                    row += 1

            # If finished odd, move to next row
            if col != 0:
                row += 1

            # Add Separator after category (if not last)
            if cat_name != "Text & Signs":
                row = add_separator(layout, row)

            # [INJECTION] Alignment Tools after Selection
            if cat_name == "Selection":
                col = 0
                for name, tooltip, func in align_tools:
                    btn = QToolButton()
                    btn.setIconSize(QSize(32, 32))  # Match other buttons
                    btn.setToolTip(tooltip)

                    action = QAction(self.main_window)
                    action.setToolTip(tooltip)
                    action.triggered.connect(func)

                    action.setIcon(create_alignment_icon(name))

                    btn.setDefaultAction(action)
                    layout.addWidget(btn, row, col)

                    col += 1
                    if col > 1:
                        col = 0
                        row += 1

                if col != 0:
                    row += 1

                # Add separator after alignment
                row = add_separator(layout, row)

        self.reaction_toolbar.addWidget(container)

        # --- About Button (Side Toolbar) ---
        self.reaction_toolbar.addSeparator()
        from .icons import create_about_icon

        about_action = QAction("About", self.main_window)
        about_action.setIcon(create_about_icon())
        about_action.setToolTip("About Reaction Sketcher")
        about_action.triggered.connect(self.show_about_dialog)
        self.reaction_toolbar.addAction(about_action)

        # Select default
        for action in self.action_group.actions():
            if action.property("tool_name") == "select":
                action.setChecked(True)
                break

        # Exit
        # Exit button commented out per user request
        # exit_action = self.reaction_toolbar.addAction(create_reaction_icon("exit"), "Exit Reaction Mode")
        # exit_action.setProperty("tool_name", "exit")
        # exit_action.triggered.connect(self.toggle_reaction_mode)

        self.main_window.addToolBar(
            Qt.ToolBarArea.LeftToolBarArea, self.reaction_toolbar
        )
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
        # Also avoid resetting if the interaction handler is in the middle of a change
        if self.interaction_handler and getattr(
            self.interaction_handler, "_internal_mode_change", False
        ):
            return

        # Check if we are currently switching modes via ModeManager
        if getattr(self, "_switching_tool", False):
            return

        # Modes that should trigger setting plugin tool to Select:
        # 1. Molecular editing modes (atom_*, bond_*, etc.)
        # 2. Main application Select mode (e.g. Space key pressed)
        is_molecular_mode = (
            mode_str.startswith("atom_")
            or mode_str.startswith("bond_")
            or mode_str.startswith("template_")
            or mode_str == "charge_plus"
            or mode_str == "charge_minus"
            or mode_str == "radical"
        )

        should_reset_plugin_tool = is_molecular_mode or mode_str == "select"

        if should_reset_plugin_tool:
            # Switch plugin tool to 'select'
            for action in self.action_group.actions():
                if action.property("tool_name") == "select":
                    if not action.isChecked():
                        action.setChecked(True)
                        if self.interaction_handler:
                            self.interaction_handler.set_tool("select")
                    break

    def setup_property_toolbar(self):
        self.property_toolbar = QToolBar("Reaction Properties", self.main_window)
        self.property_toolbar.setIconSize(QSize(24, 24))

        # Font family
        self.property_toolbar.addWidget(QLabel(" Font: "))
        self.font_combo = QComboBox()
        # Populate with all system fonts
        self.font_combo.addItems(QFontDatabase.families())
        # Try to select Arial by default if available
        idx = self.font_combo.findText("Arial")
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)

        self.font_combo.currentTextChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.font_combo)

        # Font settings - connect to functions that only format selected text
        self.bold_action = self.property_toolbar.addAction("B")
        self.bold_action.setCheckable(True)
        self.bold_action.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.bold_action.triggered.connect(lambda: self.apply_text_style("bold"))

        self.italic_action = self.property_toolbar.addAction("I")
        self.italic_action.setCheckable(True)
        self.italic_action.setFont(QFont("Arial", 10, QFont.Weight.Normal, True))
        self.italic_action.triggered.connect(lambda: self.apply_text_style("italic"))

        self.underline_action = self.property_toolbar.addAction("U")
        self.underline_action.setCheckable(True)
        f_under = QFont("Arial", 10)
        f_under.setUnderline(True)
        self.underline_action.setFont(f_under)
        self.underline_action.triggered.connect(
            lambda: self.apply_text_style("underline")
        )

        self.property_toolbar.addSeparator()

        self.sub_action = self.property_toolbar.addAction(
            create_reaction_icon("sub", 24), "Sub"
        )
        self.sub_action.setToolTip("Subscript")
        self.sub_action.triggered.connect(self.toggle_subscript)

        self.sup_action = self.property_toolbar.addAction(
            create_reaction_icon("sup", 24), "Sup"
        )
        self.sup_action.setToolTip("Superscript")
        self.sup_action.triggered.connect(self.toggle_superscript)

        self.chem_action = self.property_toolbar.addAction(
            create_reaction_icon("chem", 24), "Chem"
        )
        self.chem_action.setToolTip("Apply Chemistry Style (e.g. H_2O -> H₂O)")
        self.chem_action.triggered.connect(self.apply_chem_style)

        self.property_toolbar.addSeparator()

        self.lbl_font_size = QLabel(" Font Size: ")
        self.property_toolbar.addWidget(self.lbl_font_size)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 120)
        self.font_size_spin.valueChanged.connect(self.apply_properties)
        self.property_toolbar.addWidget(self.font_size_spin)

        # Item Size (Plus / Minus)
        # Size control removed - now only in settings dialog

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

        self.property_toolbar.addSeparator()

        # Advanced Settings Button
        settings_btn = self.property_toolbar.addAction("More...")
        settings_btn.triggered.connect(lambda: self.open_advanced_settings())

        # Add space between More and Export
        spacer = QWidget()
        spacer.setFixedWidth(40)
        self.property_toolbar.addWidget(spacer)

        self.property_toolbar.addSeparator()

        # Export/Copy Actions at the end
        # Reordered per user request: Export PNG -> Export SVG
        self.property_toolbar.addAction("Export PNG", self.export_image)
        self.property_toolbar.addAction("Export SVG", self.export_svg)
        self.property_toolbar.addAction("Copy SVG", self.copy_svg_to_clipboard)

        # Commented out per user request "comment out copy png logic"
        # self.property_toolbar.addAction("Copy PNG", self.copy_to_clipboard)

        self.main_window.addToolBar(
            Qt.ToolBarArea.TopToolBarArea, self.property_toolbar
        )
        self.property_toolbar.hide()

        # Connect selection changed
        self.main_window.scene.selectionChanged.connect(self.sync_property_toolbar)

    def _is_content_item(self, item):
        # Reliable check for Reaction Items
        if hasattr(item, "create_json_data"):
            return True
        # Check for Molecule Items (Atom/Bond)
        if hasattr(item, "atom_id") or hasattr(item, "atom1"):
            return True
        return False

    def _generate_png_data(self, items_to_render):
        """Generate PNG data (bytes) for the given items using scene render (Hide/Restore pattern)."""
        if not items_to_render:
            return b""

        # 1. Bounds
        bounds = self.get_reaction_bounds(items_to_render)
        if bounds.isEmpty():
            bounds = self.main_window.scene.itemsBoundingRect()

        # Add padding (match original: 20px)
        bounds.adjust(-20, -20, 20, 20)

        # 2. Hide unrelated items
        items_to_restore = {}
        # We need to hide everything that is NOT in items_to_render
        # But we only care about top-level items usually?
        # Safest is to iterate all items in scene.
        all_scene_items = self.main_window.scene.items()

        # Create a set for fast lookup
        render_set = set(items_to_render)

        for item in all_scene_items:
            if item.isVisible() and item not in render_set:
                # Check if it's a child of something we are rendering?
                # If parent is in render_set, we shouldn't hide child?
                # GraphicsItems hide children if parent is hidden.
                # If parent is visible and we hide child, child is hidden.
                # If we render parent, children usually render.
                # But here we are rendering SCENE with source rect.
                # So we must ensure only desired items are visible.

                # Optimization context: simple flat list usually.
                # If item is child of an item in render_set, we should NOT hide it.
                top = item.topLevelItem()
                if top in render_set:
                    continue

                items_to_restore[item] = True
                item.hide()

        # 3. Setup Image
        w = max(1, int(bounds.width()))
        h = max(1, int(bounds.height()))

        # Use Format_ARGB32 (Unpremultiplied) so that (255, 255, 255, 0) is stored as White (but transparent).
        # Premultiplied would convert it to (0, 0, 0, 0) -> Black.
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        # Fill with Transparent White (0x00FFFFFF).
        # (A=00, R=FF, G=FF, B=FF)
        image.fill(0x00FFFFFF)

        # 4. Background
        old_bg = self.main_window.scene.backgroundBrush()
        self.main_window.scene.setBackgroundBrush(
            QBrush(QColor(255, 255, 255, 0), Qt.BrushStyle.SolidPattern)
        )

        # Bonds are geometrically shortened around atom labels, so no atom paint
        # patch is needed — rendering is handled entirely by core paint.

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            selected_items = self.main_window.scene.selectedItems()
            self.main_window.scene.clearSelection()

            target = QRectF(0, 0, w, h)
            self.main_window.scene.render(painter, target, bounds)
        finally:
            painter.end()
            self.main_window.scene.setBackgroundBrush(old_bg)

            for item in items_to_restore:
                item.show()

            for item in selected_items:
                item.setSelected(True)

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        return buffer.data()

    def _generate_svg_data(self, items_to_render):
        """Generate SVG data (bytes) using scene render (Hide/Restore pattern)."""
        if not items_to_render:
            return b""

        # 1. Bounds
        bounds = self.get_reaction_bounds(items_to_render)
        if bounds.isEmpty():
            bounds = self.main_window.scene.itemsBoundingRect()

        # Add padding (match original: 20px)
        bounds.adjust(-20, -20, 20, 20)

        # 2. Hide unrelated items
        items_to_restore = {}
        all_scene_items = self.main_window.scene.items()
        render_set = set(items_to_render)

        for item in all_scene_items:
            if item.isVisible() and item not in render_set:
                top = item.topLevelItem()
                if top in render_set:
                    continue
                items_to_restore[item] = True
                item.hide()

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)

        generator = QSvgGenerator()
        generator.setOutputDevice(buffer)

        # Determine DPI to match screen
        dpi = QGuiApplication.primaryScreen().logicalDotsPerInch()
        generator.setResolution(int(dpi))

        generator.setSize(QSize(int(bounds.width()), int(bounds.height())))
        generator.setViewBox(bounds)
        generator.setTitle("Reaction Sketch")

        # Bonds are geometrically shortened around atom labels, so no atom paint
        # patch is needed for SVG export — core paint writes clean paths.

        painter = QPainter()
        painter.begin(generator)

        old_bg = self.main_window.scene.backgroundBrush()

        try:
            selected_items = self.main_window.scene.selectedItems()
            self.main_window.scene.clearSelection()

            self.main_window.scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.main_window.scene.render(painter, bounds, bounds)
        finally:
            painter.end()
            self.main_window.scene.setBackgroundBrush(old_bg)

            for item in items_to_restore:
                item.show()

            for item in selected_items:
                item.setSelected(True)

        buffer.close()
        return buffer.data()

    def export_image(self):
        # Override main window export to ensure consistent background (transparent white)
        # User requested "for png" fix specifically.

        if self.main_window and self.main_window.scene:
            # Check for selection first
            selected = self.main_window.scene.selectedItems()
            if selected:
                items = [i for i in selected if self._is_content_item(i)]
            else:
                items = [
                    i
                    for i in self.main_window.scene.items()
                    if self._is_content_item(i)
                ]
        else:
            items = []

        if not items:
            self.main_window.statusBar().showMessage("No reaction items to export.")
            return

        from PyQt6.QtWidgets import QFileDialog

        folder = os.getcwd()
        if (
            hasattr(self.main_window, "init_manager")
            and hasattr(self.main_window.init_manager, "current_file_path")
            and self.main_window.init_manager.current_file_path
        ):
            folder = os.path.dirname(self.main_window.init_manager.current_file_path)
        elif (
            hasattr(self.main_window, "last_open_path")
            and self.main_window.last_open_path
        ):
            folder = self.main_window.last_open_path
        filename, _ = QFileDialog.getSaveFileName(
            self.main_window, "Export PNG", folder, "PNG Files (*.png)"
        )
        if not filename:
            return

        data = self._generate_png_data(items)

        f = QFile(filename)
        if f.open(QIODevice.OpenModeFlag.WriteOnly):
            f.write(data)
            f.close()
            self.main_window.statusBar().showMessage(
                f"Reaction exported to {filename}", 3000
            )
        else:
            self.main_window.statusBar().showMessage(f"Failed to write to {filename}")

    def copy_to_clipboard(self):
        # Synchronize logic with SVG export/copy to ensure consistency.
        # Use shared _generate_png_data

        selected = self.main_window.scene.selectedItems()

        if not selected:
            items = [
                i for i in self.main_window.scene.items() if self._is_content_item(i)
            ]
        else:
            items = [i for i in selected if self._is_content_item(i)]

        if not items:
            self.main_window.statusBar().showMessage("No content items to copy.")
            return

        data = self._generate_png_data(items)

        mime = QMimeData()
        # 1. Set "image/png" for apps that support it (Exact match)
        mime.setData("image/png", data)

        # 2. Set standard Image data (Bitmap) for general compatibility (Windows, etc.)
        # We reconstruct QImage from the exact bytes to ensure visual fidelity.
        img_from_data = QImage.fromData(data)
        mime.setImageData(img_from_data)

        QGuiApplication.clipboard().setMimeData(mime)
        self.main_window.statusBar().showMessage("Reaction copied as Image", 3000)

    def export_svg(self, items=None, filename=None):
        if hasattr(self.main_window, "export_2d_svg") and not items:
            # If main window has it and we are exporting everything, use it?
            # BUT user says inconsistent. Maybe main window logic is different?
            # Safest to use OUR logic if we are in reaction mode/plugin.
            pass

        if items is None:
            if self.main_window and self.main_window.scene:
                # Check for selection first
                selected = self.main_window.scene.selectedItems()
                if selected:
                    items = [i for i in selected if self._is_content_item(i)]
                else:
                    items = [
                        i
                        for i in self.main_window.scene.items()
                        if self._is_content_item(i)
                    ]
            else:
                items = []

        # Filter items using our shared helper just in case
        items = [i for i in items if self._is_content_item(i)]

        if not items:
            self.main_window.statusBar().showMessage("No reaction items to export.")
            return

        if filename is None:
            from PyQt6.QtWidgets import QFileDialog

            folder = os.getcwd()
            if (
                hasattr(self.main_window, "init_manager")
                and hasattr(self.main_window.init_manager, "current_file_path")
                and self.main_window.init_manager.current_file_path
            ):
                folder = os.path.dirname(
                    self.main_window.init_manager.current_file_path
                )
            elif (
                hasattr(self.main_window, "last_open_path")
                and self.main_window.last_open_path
            ):
                folder = self.main_window.last_open_path
            filename, _ = QFileDialog.getSaveFileName(
                self.main_window, "Export SVG", folder, "SVG Files (*.svg)"
            )
            if not filename:
                return

        data = self._generate_svg_data(items)

        f = QFile(filename)
        if f.open(QIODevice.OpenModeFlag.WriteOnly):
            f.write(data)
            f.close()
            self.main_window.statusBar().showMessage(f"Reaction exported to {filename}")
        else:
            self.main_window.statusBar().showMessage(f"Failed to write to {filename}")

    def copy_svg_to_clipboard(self):
        # Determine items to copy: Selected OR All content
        selected = self.main_window.scene.selectedItems()

        if not selected:
            items = [
                i for i in self.main_window.scene.items() if self._is_content_item(i)
            ]
        else:
            items = [i for i in selected if self._is_content_item(i)]

        if not items:
            self.main_window.statusBar().showMessage("No content items to copy.")
            return

        data = self._generate_svg_data(items)

        mime = QMimeData()
        mime.setData("image/svg+xml", data)
        mime.setText(data.data().decode("utf-8"))
        self.main_window.statusBar().showMessage("Reaction copied as SVG", 3000)
        QGuiApplication.clipboard().setMimeData(mime)

    def get_reaction_bounds(self, items):
        if not items:
            return QRectF()

        molecule_bounds = QRectF()
        for item in items:
            if item.__class__.__name__ in [
                "ReactionHandle",
                "ReactionGroupOverlay",
                "SelectionRect",
                "GuideLine",
            ]:
                continue
            if hasattr(item, "handle_type"):
                continue

            # Use sceneBoundingRect() for tighter bounds
            item_bounds = item.sceneBoundingRect()
            if item_bounds.isValid() and not item_bounds.isEmpty():
                molecule_bounds = molecule_bounds.united(item_bounds)

        # No padding for tightest fit
        return molecule_bounds

    def set_auto_start(self, enabled):
        self.auto_start_pref = enabled

    def choose_color(self):
        color = QColorDialog.getColor(
            Qt.GlobalColor.black, self.main_window, "Choose Color"
        )
        if color.isValid():
            self.update_color_button(color)
            self.apply_properties()

    def update_color_button(self, color):
        self.color_btn.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #888;"
        )
        self.color_btn.setProperty("current_color", color)

    def sync_property_toolbar(self):
        if not self.is_reaction_mode:
            return

        # Safety check: ensure scene is not deleted
        try:
            if not self.main_window or not self.main_window.scene:
                return
            # Accessing anything on the scene might raise RuntimeError if deleted
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            # Scene or main window was deleted during teardown
            return
        try:
            from modules.atom_item import AtomItem
            from modules.bond_item import BondItem
        except ImportError:
            try:
                from moleditpy.ui.atom_item import AtomItem
                from moleditpy.ui.bond_item import BondItem
            except ImportError:
                AtomItem = type("AtomItem", (), {})
                BondItem = type("BondItem", (), {})

        # Filter valid items
        reaction_items = [
            i
            for i in items
            if not sip_isdeleted_safe(i)
            and (hasattr(i, "create_json_data") or isinstance(i, (AtomItem, BondItem)))
        ]

        if not reaction_items:
            # Reset Toolbar to Default (No Selection)
            self.lbl_font_size.hide()
            self.font_size_spin.hide()
            # Size control removed

            self.font_combo.setEnabled(False)
            self.bold_action.setEnabled(False)
            self.italic_action.setEnabled(False)
            self.underline_action.setEnabled(False)
            self.sub_action.setEnabled(False)
            self.sup_action.setEnabled(False)
            self.chem_action.setEnabled(False)
            self.width_spin.setEnabled(False)  # Disable width when no items selected

            # Reset color button to default logic or keep last used?
            # Usually keep last used color for next drawing action is preferred.
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
        # Size control removed

        # Sub/Sup/Chem buttons should be enabled if ANY selected item is a text item
        has_text = any(isinstance(i, ReactionTextItem) for i in reaction_items)
        self.sub_action.setEnabled(has_text)
        self.sup_action.setEnabled(has_text)
        self.chem_action.setEnabled(has_text)

        if has_text:
            try:
                from PyQt6.QtGui import QTextCursor
            except ImportError:
                pass

            # Sync text-specific properties from the first text item
            text_items = [i for i in reaction_items if isinstance(i, ReactionTextItem)]
            first_text = text_items[0]

            # Get font from actual content (Rich Text)
            f = first_text.font()  # Default fallback
            try:
                cursor = first_text.textCursor()
                if (
                    first_text.textInteractionFlags()
                    & Qt.TextInteractionFlag.TextEditorInteraction
                ):
                    f = cursor.charFormat().font()
                elif not first_text.document().isEmpty():
                    c = QTextCursor(first_text.document())
                    c.setPosition(0)
                    c.movePosition(
                        QTextCursor.MoveOperation.NextCharacter,
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    f = c.charFormat().font()
            except Exception as _e:
                logging.warning("[mode_manager.py:1061] silenced: %s", _e)

            idx = self.font_combo.findText(f.family())
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)

            self.blockSignals(True)
            self.bold_action.setChecked(f.bold())
            self.italic_action.setChecked(f.italic())
            self.underline_action.setChecked(f.underline())
            self.blockSignals(False)

            self.lbl_font_size.show()
            self.font_size_spin.show()
            size = f.pointSize()
            if size <= 0:
                size = f.pixelSize()
            if size <= 0:
                size = 12
            self.font_size_spin.setValue(int(size))

            self.font_combo.setEnabled(True)
            self.bold_action.setEnabled(True)
            self.italic_action.setEnabled(True)
            self.underline_action.setEnabled(True)
            self.font_size_spin.setEnabled(True)

            # Ensure we are listening to cursor changes for live updates
            try:
                first_text.cursorChanged.disconnect(self.sync_property_toolbar)
            except TypeError:
                pass  # not connected — expected
            except Exception as _e:
                logging.warning("[mode_manager.py:1088] silenced: %s", _e)
            first_text.cursorChanged.connect(self.sync_property_toolbar)
        else:
            self.font_combo.setEnabled(False)
            self.font_size_spin.setEnabled(False)
            self.bold_action.setEnabled(False)
            self.italic_action.setEnabled(False)
            self.underline_action.setEnabled(False)
            self.lbl_font_size.hide()
            self.font_size_spin.hide()

        # Sync width if arrow/bracket/signs
        if hasattr(first, "pen_width"):
            self.width_spin.setValue(int(first.pen_width))
            self.width_spin.setEnabled(True)
        else:
            self.width_spin.setEnabled(False)

        self._updating_props = False

    def disconnect_signals(self):
        """Safely disconnect signals on exit or destruction."""
        try:
            if self.main_window and self.main_window.scene:
                try:
                    self.main_window.scene.selectionChanged.disconnect(
                        self.sync_property_toolbar
                    )
                except TypeError:
                    pass  # not connected — expected
                except (AttributeError, RuntimeError) as _e:
                    logging.warning("[mode_manager.py:1114] silenced: %s", _e)
        except (AttributeError, RuntimeError) as _e:
            logging.warning("[mode_manager.py:1116] silenced: %s", _e)

    def _apply_text_format_property(self, property_name):
        """Helper to apply a specific text property safely."""
        try:
            if not self.main_window or not self.main_window.scene:
                return

            # Check for focus item first (Edit Mode)
            focus_item = self.main_window.scene.focusItem()

            target_items = []
            is_edit_mode = False

            if isinstance(focus_item, ReactionTextItem) and (
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                target_items = [focus_item]
                is_edit_mode = True
            else:
                # Object Mode
                target_items = [
                    i
                    for i in self.main_window.scene.selectedItems()
                    if isinstance(i, ReactionTextItem)
                ]

            if not target_items:
                return

            modified = False
            for item in target_items:
                cursor = item.textCursor()
                if not is_edit_mode:
                    cursor.select(QTextCursor.SelectionType.Document)

                fmt = cursor.charFormat()

                if property_name == "bold":
                    w = (
                        QFont.Weight.Bold
                        if fmt.fontWeight() != QFont.Weight.Bold
                        else QFont.Weight.Normal
                    )
                    fmt.setFontWeight(w)
                elif property_name == "italic":
                    fmt.setFontItalic(not fmt.fontItalic())
                elif property_name == "underline":
                    fmt.setFontUnderline(not fmt.fontUnderline())
                elif property_name == "sub":
                    # Toggle subscript: if already subscript, remove it; otherwise apply it
                    current_align = fmt.verticalAlignment()
                    if (
                        current_align
                        == QTextCharFormat.VerticalAlignment.AlignSubScript
                    ):
                        fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignNormal
                        )
                    else:
                        fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignSubScript
                        )

                elif property_name == "sup":
                    # Toggle superscript: if already superscript, remove it; otherwise apply it
                    current_align = fmt.verticalAlignment()
                    if (
                        current_align
                        == QTextCharFormat.VerticalAlignment.AlignSuperScript
                    ):
                        fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignNormal
                        )
                    else:
                        fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignSuperScript
                        )

                cursor.mergeCharFormat(fmt)
                if is_edit_mode:
                    item.setTextCursor(cursor)

            if self.is_reaction_mode:
                self.sync_property_toolbar()
                modified = True

            if modified:
                self.main_window.edit_actions_manager.push_undo_state()
                # Sync toolbar UI
                self.sync_property_toolbar()

        except Exception as e:
            logging.warning("[mode_manager.py:1212] silenced: %s", e)

    def apply_properties(self):
        if self._updating_props:
            return
        if not self.is_reaction_mode:
            return

        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return

        sender = self.sender()
        if not sender:
            return

        modified = False

        # Color Change
        if sender == self.color_btn:
            color = self.color_btn.property("current_color")
            for item in items:
                if isinstance(item, ReactionTextItem):
                    item.setDefaultTextColor(QColor(color))
                    # Apply to selection/document
                    cursor = item.textCursor()
                    if not (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        cursor.select(QTextCursor.SelectionType.Document)
                    fmt = QTextCharFormat()
                    fmt.setForeground(QBrush(QColor(color)))
                    cursor.mergeCharFormat(fmt)
                    if (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        item.setTextCursor(cursor)
                elif hasattr(item, "pen_color"):
                    item.pen_color = color
                    item.update()
                modified = True

        # Font Family Change
        elif sender == self.font_combo:
            family = self.font_combo.currentText()
            for item in items:
                if isinstance(item, ReactionTextItem):
                    cursor = item.textCursor()
                    if not (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        cursor.select(QTextCursor.SelectionType.Document)
                    fmt = QTextCharFormat()
                    fmt.setFontFamily(family)
                    cursor.mergeCharFormat(fmt)
                    if (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        item.setTextCursor(cursor)
                    # Update default font
                    f = item.font()
                    f.setFamily(family)
                    item.setFont(f)
                    modified = True

        # Font Size Change
        elif sender == self.font_size_spin:
            size = self.font_size_spin.value()
            for item in items:
                if isinstance(item, ReactionTextItem):
                    cursor = item.textCursor()
                    if not (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        cursor.select(QTextCursor.SelectionType.Document)
                    fmt = QTextCharFormat()
                    fmt.setFontPointSize(size)
                    cursor.mergeCharFormat(fmt)
                    if (
                        item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        item.setTextCursor(cursor)
                    f = item.font()
                    f.setPointSize(size)
                    item.setFont(f)
                    modified = True

        # Item Size Change (Plus/Minus)
        elif sender == self.size_spin:
            size = self.size_spin.value()
            for item in items:
                if hasattr(item, "set_size"):
                    item.set_size(size)
                    modified = True

        # Line Width Change
        elif sender == self.width_spin:
            width = self.width_spin.value()
            for item in items:
                if hasattr(item, "pen_width"):
                    item.pen_width = width
                    item.update()
                    modified = True

        if modified and hasattr(
            self.main_window.edit_actions_manager, "push_undo_state"
        ):
            self.main_window.edit_actions_manager.push_undo_state()

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
        if icon_name in [
            "arrow",
            "arrow_eq",
            "arrow_res",
            "arrow_retro",
            "arrow_no",
            "curved_double",
            "curved_fish",
            "bracket",
            "circle",
            "plus",
            "minus",
            "text",
            "line",
            "line_curved",
            "freehand",
            "arrow_dashed",
        ]:
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, b=button, t=icon_name: self.show_tool_context_menu(
                    b, t, pos
                )
            )

        # Handle click to toggle menu if already active
        # We need to know if it was active *before* the click.
        button.pressed.connect(lambda: self.on_tool_pressed(icon_name))
        button.clicked.connect(lambda: self.on_tool_clicked(button, icon_name))

        button.triggered.connect(lambda act: self.on_action_triggered(act))
        self.reaction_toolbar.addWidget(button)
        return button

    def on_action_triggered(self, action):
        tool_name = action.property("tool_name")
        if not tool_name:
            return

        if self.interaction_handler:
            # Set a flag to ignore the 'select' mode change notification that
            # might be triggered by main_window.activate_select_mode()
            self._switching_tool = True
            try:
                self.interaction_handler.set_tool(tool_name)

                # One click to activate style on selection
                if self.main_window and self.main_window.scene:
                    items = self.main_window.scene.selectedItems()
                    if items:
                        if tool_name in [
                            "arrow",
                            "arrow_dashed",
                            "arrow_eq",
                            "arrow_res",
                            "arrow_retro",
                            "curved_double",
                            "curved_fish",
                        ]:
                            self.set_head_style(
                                tool_name,
                                self.default_head_styles.get(tool_name, "triangle"),
                            )
                        elif tool_name == "arrow_no":
                            self.set_negation_style(
                                getattr(self, "default_no_arrow_style", "slash")
                            )
                        elif tool_name == "circle":
                            self.set_circle_variant(
                                getattr(self, "default_circle_shape_type", "circle"),
                                getattr(self, "default_circle_line_style", "solid"),
                            )
                        elif tool_name == "bracket":
                            self.set_bracket_type(
                                getattr(self, "default_bracket_type", "square")
                            )
            finally:
                self._switching_tool = False

            # Ensure focus returns to view so keyboard shortcuts (Space) work immediately
            if self.main_window and hasattr(self.main_window, "view_2d"):
                self.main_window.init_manager.view_2d.setFocus()

    def on_tool_pressed(self, action):
        # Capture state before the action toggles
        self._was_active_before_click = action.isChecked()

    def on_tool_clicked(self, button, action):
        # If the tool WAS already active before we clicked it -> Show Menu (Toggle options)
        # MacOS Fix: check if it WAS active. If so, ensure it REMAINS active (checked) and show menu.
        if getattr(self, "_was_active_before_click", False):
            # Force checked state back on if the click toggled it off
            if not action.isChecked():
                action.setChecked(True)

            # Toggle menu
            tool_name = action.property("tool_name")
            if tool_name:
                # Check for rapid re-click after menu close (allow 300ms cooldown)
                import time

                last_close = getattr(self, "_last_menu_close_time", 0)
                if time.time() - last_close < 0.3:
                    return

                self.show_tool_context_menu(
                    button, tool_name, QPoint(0, button.height())
                )

    def activate_select_tool(self):
        if self.interaction_handler:
            self.interaction_handler.set_tool("select")

        # Update UI
        for action in self.action_group.actions():
            if action.property("tool_name") == "select":
                action.setChecked(True)
                break

    def show_tool_context_menu(self, button, tool_name, pos):
        menu = self.create_tool_style_menu(tool_name)
        if menu:
            # Execute menu
            if button:
                menu.exec(button.mapToGlobal(pos))
            else:
                menu.exec(pos)

            # Record close time to prevent immediate re-opening
            import time

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

        if tool_name in [
            "arrow",
            "arrow_eq",
            "arrow_res",
            "arrow_retro",
            "curved_double",
            "curved_fish",
            "arrow_dashed",
        ]:
            current_style = self.default_head_styles.get(tool_name, "triangle")

            try:
                if self.main_window and self.main_window.scene:
                    selected = self.main_window.scene.selectedItems()
                    if selected:
                        for item in selected:
                            if isinstance(item, ReactionArrowItem):
                                if hasattr(item, "head_style"):
                                    current_style = item.head_style
                                break
            except Exception as _e:
                logging.warning("[mode_manager.py:1437] silenced: %s", _e)

            # Determine if we should show straight or curved icons based on the tool
            icon_type = "curved" if "curved" in tool_name else "straight"

            # Triangle head (Full / Barbless)
            act_tri = menu.addAction(
                create_style_icon(
                    icon_type, "triangle", selected=(current_style == "triangle")
                ),
                "Triangle (Filled)",
            )
            act_tri.setCheckable(True)
            act_tri.setChecked(current_style == "triangle")
            act_tri.triggered.connect(
                lambda: self.set_head_style(tool_name, "triangle")
            )

            # Chevron head (Concave base)
            act_chevron = menu.addAction(
                create_style_icon(
                    icon_type, "chevron", selected=(current_style == "chevron")
                ),
                "Chevron (Concave)",
            )
            act_chevron.setCheckable(True)
            act_chevron.setChecked(current_style == "chevron")
            act_chevron.triggered.connect(
                lambda: self.set_head_style(tool_name, "chevron")
            )

            # Harpoon head (Asymmetric / Half)
            act_harpoon = menu.addAction(
                create_style_icon(
                    icon_type, "harpoon", selected=(current_style == "harpoon")
                ),
                "Harpoon (Asymmetric)",
            )
            act_harpoon.setCheckable(True)
            act_harpoon.setChecked(current_style == "harpoon")
            act_harpoon.triggered.connect(
                lambda: self.set_head_style(tool_name, "harpoon")
            )

            # Barb head (Open)
            act_barb = menu.addAction(
                create_style_icon(
                    icon_type, "barb", selected=(current_style == "barb")
                ),
                "Barb (Open)",
            )
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
            except Exception as _e:
                logging.warning("[mode_manager.py:1479] silenced: %s", _e)

            # Slash
            act_slash = menu.addAction(
                create_style_icon("arrow_no", "slash", selected=(neg_style == "slash")),
                "Slash (/)",
            )
            act_slash.setCheckable(True)
            act_slash.setChecked(neg_style == "slash")
            act_slash.triggered.connect(lambda: self.set_negation_style("slash"))
            # Cross
            act_cross = menu.addAction(
                create_style_icon("arrow_no", "cross", selected=(neg_style == "cross")),
                "Cross (X)",
            )
            act_cross.setCheckable(True)
            act_cross.setChecked(neg_style == "cross")
            act_cross.triggered.connect(lambda: self.set_negation_style("cross"))

            # Double Slash
            act_dslash = menu.addAction(
                create_style_icon(
                    "arrow_no", "double_slash", selected=(neg_style == "double_slash")
                ),
                "Double Slash (//)",
            )
            act_dslash.setCheckable(True)
            act_dslash.setChecked(neg_style == "double_slash")
            act_dslash.triggered.connect(
                lambda: self.set_negation_style("double_slash")
            )

            if tool_name in ["curved_double", "curved_fish"]:
                menu.addSeparator()
                # Fish hook toggle
                hook_act = menu.addAction(
                    create_style_icon("curved", "fish"), "Fish Hook (Single Barb)"
                )
                hook_act.setCheckable(True)
                hook_act.setChecked(tool_name == "curved_fish")
                hook_act.triggered.connect(
                    lambda checked: self.set_curved_hook_style(checked)
                )

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
            except Exception as _e:
                logging.warning("[mode_manager.py:1516] silenced: %s", _e)

            act_sq = menu.addAction("Square [ ]")
            act_sq.setCheckable(True)
            act_sq.setChecked(curr_type == "square")
            act_sq.triggered.connect(lambda: self.set_bracket_type("square"))

            act_sq_l = menu.addAction("Square Left [")
            act_sq_l.setCheckable(True)
            act_sq_l.setChecked(curr_type == "square_left")
            act_sq_l.triggered.connect(lambda: self.set_bracket_type("square_left"))

            act_sq_r = menu.addAction("Square Right ]")
            act_sq_r.setCheckable(True)
            act_sq_r.setChecked(curr_type == "square_right")
            act_sq_r.triggered.connect(lambda: self.set_bracket_type("square_right"))

            act_rd = menu.addAction("Round ( )")
            act_rd.setCheckable(True)
            act_rd.setChecked(curr_type == "round")
            act_rd.triggered.connect(lambda: self.set_bracket_type("round"))

            act_rd_l = menu.addAction("Round Left (")
            act_rd_l.setCheckable(True)
            act_rd_l.setChecked(curr_type == "round_left")
            act_rd_l.triggered.connect(lambda: self.set_bracket_type("round_left"))

            act_rd_r = menu.addAction("Round Right )")
            act_rd_r.setCheckable(True)
            act_rd_r.setChecked(curr_type == "round_right")
            act_rd_r.triggered.connect(lambda: self.set_bracket_type("round_right"))

            act_cur = menu.addAction("Curly { }")
            act_cur.setCheckable(True)
            act_cur.setChecked(curr_type == "curly")
            act_cur.triggered.connect(lambda: self.set_bracket_type("curly"))

            act_cur_l = menu.addAction("Curly Left {")
            act_cur_l.setCheckable(True)
            act_cur_l.setChecked(curr_type == "curly_left")
            act_cur_l.triggered.connect(lambda: self.set_bracket_type("curly_left"))

            act_cur_r = menu.addAction("Curly Right }")
            act_cur_r.setCheckable(True)
            act_cur_r.setChecked(curr_type == "curly_right")
            act_cur_r.triggered.connect(lambda: self.set_bracket_type("curly_right"))

        elif tool_name == "circle":
            # 4 Options: Solid Rect, Dashed Rect, Solid Circle, Dashed Circle
            curr_shape = "rectangle"
            curr_style = "solid"
            try:
                if self.main_window and self.main_window.scene:
                    selected = self.main_window.scene.selectedItems()
                    for item in selected:
                        if hasattr(item, "shape_type") and not hasattr(
                            item, "bracket_type"
                        ):
                            curr_shape = item.shape_type
                            curr_style = getattr(item, "line_style", "solid")
                            break
            except Exception as _e:
                logging.warning("[mode_manager.py:1575] silenced: %s", _e)

            variants = [
                ("Solid Rectangle", "rectangle", "solid"),
                ("Dashed Rectangle", "rectangle", "dashed"),
                ("Solid Circle / Ellipse", "circle", "solid"),
                ("Dashed Circle / Ellipse", "circle", "dashed"),
            ]

            for label, stype, lstyle in variants:
                act = menu.addAction(create_shape_variant_icon(stype, lstyle), label)
                act.setCheckable(True)
                act.setChecked(curr_shape == stype and curr_style == lstyle)

                def make_cb(s, l):
                    return lambda: self.set_circle_variant(s, l)

                act.triggered.connect(make_cb(stype, lstyle))

            menu.addSeparator()

        elif tool_name == "text":
            # Text Options
            act_chem = menu.addAction("Format as Chemical")

            def format_chem():
                try:
                    if self.main_window and self.main_window.scene:
                        selected = self.main_window.scene.selectedItems()
                        modified = False
                        for item in selected:
                            if isinstance(item, ReactionTextItem):
                                item.format_as_chemical()
                                modified = True
                        if modified:
                            self.main_window.edit_actions_manager.push_undo_state()
                except Exception as _e:
                    logging.warning("[mode_manager.py:1607] silenced: %s", _e)

            act_chem.triggered.connect(format_chem)
            menu.addSeparator()

            # Grouping options
            act_group = menu.addAction("Group Selected Items")

            def group_items():
                try:
                    if self.main_window and self.main_window.scene:
                        items = self.main_window.scene.selectedItems()
                        if not items:
                            return

                        # Find the highest existing group_id and add 1
                        max_group_id = 0
                        for item in self.main_window.scene.items():
                            if hasattr(item, "group_id") and item.group_id is not None:
                                max_group_id = max(max_group_id, item.group_id)
                        new_group = max_group_id + 1

                        for item in items:
                            if hasattr(item, "group_id"):
                                item.group_id = new_group

                        # Show status message
                        if hasattr(self.main_window, "statusBar"):
                            self.main_window.statusBar().showMessage(
                                f"Grouped {len(items)} items", 3000
                            )

                        self.main_window.edit_actions_manager.push_undo_state()
                except Exception:
                    pass  # For debugging, can be removed

            act_group.triggered.connect(group_items)

            act_ungroup = menu.addAction("Ungroup Selected Items")

            def ungroup_items():
                try:
                    if self.main_window and self.main_window.scene:
                        items = self.main_window.scene.selectedItems()
                        if not items:
                            return

                        ungrouped_count = 0
                        for item in items:
                            if hasattr(item, "group_id") and item.group_id is not None:
                                item.group_id = None
                                ungrouped_count += 1

                        # Show status message
                        if hasattr(self.main_window, "statusBar"):
                            self.main_window.statusBar().showMessage(
                                f"Ungrouped {ungrouped_count} items", 3000
                            )

                        if ungrouped_count > 0:
                            self.main_window.edit_actions_manager.push_undo_state()
                except Exception:
                    pass  # For debugging, can be removed

            act_ungroup.triggered.connect(ungroup_items)
            menu.addSeparator()

        # "Switch Tool" section for common grouping
        if tool_name in ["circle", "line", "line_dashed", "line_curved", "freehand"]:
            if menu.actions():
                menu.addSeparator()

            tools = [
                ("Straight Line", "line"),
                ("Dashed Line", "line_dashed"),
                ("Curved Line", "line_curved"),
                ("Freehand", "freehand"),
            ]

            for label, t_name in tools:
                act = menu.addAction(create_reaction_icon(t_name), label)
                act.setCheckable(True)
                act.setChecked(tool_name == t_name)

                # Use a closure or separate method to avoid late binding issues
                def make_trigger(tn):
                    return lambda: self.activate_tool_by_name(tn)

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
            if self.main_window and hasattr(self.main_window, "view_2d"):
                self.main_window.init_manager.view_2d.setFocus()

    def eventFilter(self, obj, event):
        # Handle ShortcutOverride to block main window shortcuts while editing text
        if event.type() == QEvent.Type.ShortcutOverride:
            if self._shortcuts_disabled:
                # Double check focus
                try:
                    focus_item = self.main_window.scene.focusItem()
                    from .items import ReactionTextItem

                    if isinstance(focus_item, ReactionTextItem) and (
                        focus_item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        event.accept()
                        return True
                except Exception as _e:
                    logging.warning("[mode_manager.py:1712] silenced: %s", _e)
        return super().eventFilter(obj, event)

    def disable_main_window_shortcuts(self):
        """Temporarily disable main window shortcuts to allow text editing."""
        if self._shortcuts_disabled:
            return

        self._disabled_actions_state = []
        if not self.main_window:
            return

        # 1. Disable QActions
        for action in self.main_window.findChildren(QAction):
            # Skip our tool actions
            is_plugin_action = False
            if self.reaction_toolbar and action.parent() == self.reaction_toolbar:
                is_plugin_action = True
            if self.property_toolbar and action.parent() == self.property_toolbar:
                is_plugin_action = True

            if (
                not is_plugin_action
                and action.shortcut()
                and not action.shortcut().isEmpty()
            ):
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
            if getattr(self, "_disabled_actions_state", None) is not None:
                for action in self._disabled_actions_state:
                    try:
                        action.setEnabled(True)
                    except Exception as _e:
                        logging.warning("[mode_manager.py:1752] silenced: %s", _e)
                self._disabled_actions_state = []

            # 2. Remove Event Filter
            self.main_window.removeEventFilter(self)

        self._shortcuts_disabled = False

    def show_about_dialog(self):
        """Display About dialog with plugin version and information."""
        from PyQt6.QtWidgets import QMessageBox
        from . import PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_AUTHOR, PLUGIN_DESCRIPTION

        about_text = f"""<h2>{PLUGIN_NAME}</h2>
<p><b>Version:</b> {PLUGIN_VERSION}</p>
<p><b>Author:</b> {PLUGIN_AUTHOR}</p>
<p>{PLUGIN_DESCRIPTION}</p>
"""

        QMessageBox.about(self.main_window, f"About {PLUGIN_NAME}", about_text)

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

            def on_apply():
                s = dlg.get_settings()
                self.apply_settings_to_selection(s)
                if self.main_window:
                    self.main_window.edit_actions_manager.push_undo_state()
                self.sync_property_toolbar()  # Sync toolbar after applying settings

            dlg.applyRequested.connect(on_apply)

            if dlg.exec():
                # If dialog was accepted (OK button), apply settings and push undo state
                settings = dlg.get_settings()
                self.apply_settings_to_selection(settings)
                if self.main_window:
                    self.main_window.edit_actions_manager.push_undo_state()
                self.sync_property_toolbar()  # Sync toolbar after applying settings

    def apply_settings_to_selection(self, settings):
        """Apply a settings dictionary to all selected items."""
        if not self.main_window or not self.main_window.scene:
            return

        self._updating_props = True
        try:
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
                if "head_angle" in settings:
                    if hasattr(item, "head_angle"):
                        item.head_angle = settings["head_angle"]
                if "head_concavity" in settings:
                    if hasattr(item, "head_concavity"):
                        item.head_concavity = settings["head_concavity"]
                if "curvature" in settings:
                    if hasattr(item, "curvature"):
                        item.curvature = settings["curvature"]

                if "control_p" in settings and hasattr(item, "control_p"):
                    # Restore manual control point
                    cp_data = settings["control_p"]
                    from PyQt6.QtCore import QPointF

                    item.control_p = QPointF(cp_data[0], cp_data[1])
                    # We must force update handles or internal state
                    if hasattr(item, "sync_handles"):
                        item.sync_handles()

                if "head_side" in settings and hasattr(item, "head_side"):
                    item.head_side = settings["head_side"]
                    if hasattr(item, "sync_handles"):
                        item.sync_handles()

                if "double_arrow_offset" in settings:
                    if hasattr(item, "double_arrow_offset"):
                        item.double_arrow_offset = settings["double_arrow_offset"]

                if "cross_size" in settings:
                    if hasattr(item, "cross_size"):
                        item.cross_size = settings["cross_size"]

                # Apply Width/Height for Rect items (Arrows, Brackets, Circles, Freehand)
                if "rect_width" in settings and "rect_height" in settings:
                    if hasattr(item, "set_rect_size"):
                        item.set_rect_size(
                            settings["rect_width"], settings["rect_height"]
                        )

                # Apply Size for Plus/Minus/Text items
                if "size" in settings:
                    if hasattr(item, "set_size"):
                        item.set_size(settings["size"])
                    elif hasattr(item, "size"):
                        # Fallback if no specific setter
                        item.prepareGeometryChange()
                        item.size = settings["size"]
                        item.update()

                if "bracket_type" in settings and hasattr(item, "bracket_type"):
                    item.bracket_type = settings["bracket_type"]

                if "head_style" in settings and hasattr(item, "head_style"):
                    item.head_style = settings["head_style"]

                # if "head_at" in settings and hasattr(item, "head_at"):
                #      item.head_at = settings["head_at"]
                #      if hasattr(item, "sync_handles"):
                #          item.sync_handles()

                # Force item to update geometry and visuals
                if hasattr(item, "update"):
                    item.update()
        finally:
            self._updating_props = False
            self.sync_property_toolbar()

    def set_head_style(self, tool_name, style):
        self.default_head_styles[tool_name] = style
        try:
            if not self.main_window or not self.main_window.scene:
                return
            items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            return

            return

        # Mapping tool_name to class
        tool_map = {
            "arrow": ReactionArrowItem,
            "arrow_dashed": ReactionDashedArrowItem,
            "arrow_res": ReactionResonanceArrowItem,
            "arrow_eq": ReactionEquilibriumArrowItem,
            "arrow_retro": ReactionRetroArrowItem,
            "curved_double": ReactionCurvedArrowItem,
            "curved_fish": ReactionCurvedArrowItem,
        }

        target_class = tool_map.get(tool_name, None)

        modified = False
        scene = self.main_window.scene

        # We collect updates to avoid modifying list while iterating
        for item in list(items):  # copy list
            if not isinstance(item, ReactionArrowItem):
                continue

            # Check if conversion is needed
            should_convert = False
            if target_class and not isinstance(item, target_class):
                should_convert = True

            # Additional check for Curved Arrow variants (Double vs Fish)
            if target_class == ReactionCurvedArrowItem and isinstance(
                item, ReactionCurvedArrowItem
            ):
                is_target_fish = tool_name == "curved_fish"
                if item.is_fish_hook != is_target_fish:
                    should_convert = True

            if should_convert:
                try:
                    # Create new item
                    old_state = item.create_json_data()

                    # Pass fish hook parameter if applicable
                    kwargs = {}
                    if tool_name == "curved_fish":
                        kwargs["is_fish_hook"] = True

                    # Safety check: Ensure we don't pass kwargs to straight arrows if they don't support them
                    # ReactionCurvedArrowItem supports **kwargs in our logic above (start, end, is_fish_hook)
                    # But strictly it is __init__(start, end, is_fish_hook=False)

                    if target_class == ReactionCurvedArrowItem:
                        new_item = target_class(item.start_p, item.end_p, **kwargs)
                    else:
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
                    if (
                        hasattr(new_item, "head_concavity")
                        and "head_concavity" in old_state
                    ):
                        new_item.head_concavity = old_state["head_concavity"]

                    # Special handling for curved
                    if isinstance(new_item, ReactionCurvedArrowItem):
                        if "cp_x" in old_state:
                            # Try to preserve curve?
                            # For now, let it reset to straight-ish curve default or we can try to map it.
                            pass

                    # Set new style
                    new_item.head_style = style

                    # Replace in scene
                    scene.addItem(new_item)
                    scene.removeItem(item)
                    new_item.setSelected(True)
                    modified = True

                except Exception as e:
                    print(f"Error converting item: {e}")
                    # Do NOT remove the old item if creation failed

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
            self.main_window.edit_actions_manager.push_undo_state()

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
            self.main_window.edit_actions_manager.push_undo_state()

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
            self.main_window.edit_actions_manager.push_undo_state()

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

        self.main_window.edit_actions_manager.push_undo_state()

    def set_circle_variant(self, shape_type, line_style):
        self.default_circle_shape_type = shape_type
        self.default_circle_line_style = line_style
        try:
            if not self.main_window or not self.main_window.scene:
                return
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
                self.main_window.edit_actions_manager.push_undo_state()
        except Exception as _e:
            logging.warning("[mode_manager.py:2122] silenced: %s", _e)

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

        self.main_window.edit_actions_manager.push_undo_state()

    def set_tool(self, tool_name):
        if self.interaction_handler:
            self.interaction_handler.set_tool(tool_name)

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
            self.main_window.edit_actions_manager.push_undo_state()

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
            items = [
                i
                for i in self.main_window.scene.items()
                if hasattr(i, "create_json_data")
            ]
            if items:
                reply = QMessageBox.question(
                    self.main_window,
                    "Confirm Exit",
                    "Reaction objects are present. Exiting Reaction Mode will remove the specialized interaction tools used to edit them. Are you sure you want to exit?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return

        self.is_reaction_mode = new_state
        if self.is_reaction_mode:
            self.enter_reaction_mode()
        else:
            self.exit_reaction_mode()

    def add_action(self, icon_name, tooltip, callback):
        """Helper to add simple action buttons (not checkable tools)."""
        icon = create_alignment_icon(icon_name)
        action = self.reaction_toolbar.addAction(icon, tooltip)
        action.triggered.connect(callback)
        return action

    def enter_reaction_mode(self):
        # Save original layout
        self.original_splitter_sizes = self.main_window.init_manager.splitter.sizes()

        # Unselect main window tool (e.g., templates, atoms)
        if hasattr(self.main_window, "ui_manager") and hasattr(
            self.main_window.ui_manager, "activate_select_mode"
        ):
            self.main_window.ui_manager.activate_select_mode()
        elif hasattr(self.main_window, "activate_select_mode"):
            self.main_window.activate_select_mode()

        # Maximize 2D view (index 0 usually 2D, index 1 usually 3D)
        if self.main_window.init_manager.splitter.count() > 1:
            self.main_window.init_manager.splitter.setSizes([1000, 0])

        # Show reaction toolbar
        if self.reaction_toolbar:
            self.reaction_toolbar.show()
        if self.property_toolbar:
            self.property_toolbar.show()

        # Apply patches (Core and Interaction) dynamically
        apply_core_patches(self.main_window)
        apply_interaction_patches(self.main_window)
        # Rebind button/menu signals because Qt keeps pre-patch bound callables.
        self._rewire_cleanup_2d_triggers()
        self.main_window.scene.update()
        self.is_reaction_mode = True

        # Disable 3D actions immediately when entering reaction mode
        self.set_3d_action_state(False)
        self.main_window.statusBar().showMessage("Reaction Sketching Mode Active", 3000)

    def exit_reaction_mode(self):
        # Restore layout
        if self.original_splitter_sizes:
            self.main_window.init_manager.splitter.setSizes(
                self.original_splitter_sizes
            )
        else:
            # Fallback to 50/50
            total = sum(self.main_window.init_manager.splitter.sizes())
            self.main_window.init_manager.splitter.setSizes([total // 2, total // 2])

        self.set_3d_action_state(True)
        self.main_window.statusBar().showMessage("Returned to Molecular Mode", 3000)
        self.is_reaction_mode = False

        # Hide toolbars
        if self.reaction_toolbar:
            self.reaction_toolbar.hide()
        if self.property_toolbar:
            self.property_toolbar.hide()

        # Reset tool to Select
        for action in self.action_group.actions():
            if action.property("tool_name") == "select":
                action.setChecked(True)
                if self.interaction_handler:
                    self.interaction_handler.set_tool("select")
                break

        # Unapply patches (restore original behavior)
        self.disconnect_signals()
        revert_all_patches()
        # Rebind again so button/menu point at restored core method.
        self._rewire_cleanup_2d_triggers()

    def set_3d_action_state(self, enabled):
        # 1. Disable the specific buttons found in main_window_main_init.py
        if self.main_window:
            _init = getattr(self.main_window, "init_manager", None)
            if _init is not None:
                if hasattr(_init, "convert_button"):
                    _init.convert_button.setEnabled(enabled)
                if hasattr(_init, "optimize_3d_button"):
                    # optimize_3d_button is usually disabled by default until 3D exists,
                    # but we should force disable it if in reaction mode
                    if not enabled:
                        _init.optimize_3d_button.setEnabled(False)

        # 2. Try to find other actions (menus)
        if getattr(self, "_3d_actions", None) is None:
            self._3d_actions = []
            # Common names
            for name in [
                "action_3d",
                "act_3d",
                "action_convert_to_3d",
                "convert_3d_action",
                "action_convert_to_3d",
                "edit_3d_action",
            ]:
                if hasattr(self.main_window, name):
                    self._3d_actions.append(getattr(self.main_window, name))

        for action in self._3d_actions:
            action.setEnabled(enabled)

    def group_selected_items(self):
        """Group selected items logically."""
        if not self.main_window or not self.main_window.scene:
            return
        items = self.main_window.scene.selectedItems()
        if not items:
            return

        # Filter for items that support grouping (our plugin items + patched atoms/bonds)
        groupable = [
            i
            for i in items
            if hasattr(i, "group_id") or hasattr(i, "atom_id") or hasattr(i, "atom1")
        ]

        if not groupable:
            return

        new_group = str(uuid.uuid4())
        self.main_window.edit_actions_manager.push_undo_state()
        for item in groupable:
            item.group_id = new_group
            item.is_group_selected = True
            item.update()

        # Show status message
        if hasattr(self.main_window, "statusBar"):
            self.main_window.statusBar().showMessage(
                f"Grouped {len(groupable)} items", 3000
            )

        if self.interaction_handler:
            self.interaction_handler.update_group_overlay(groupable)
        self._sync_selection_visuals()

    def ungroup_selected_items(self):
        """Ungroup selected items."""
        if not self.main_window or not self.main_window.scene:
            return
        items = self.main_window.scene.selectedItems()
        if not items:
            return

        groupable = [
            i
            for i in items
            if hasattr(i, "group_id") or hasattr(i, "atom_id") or hasattr(i, "atom1")
        ]

        if not groupable:
            return

        self.main_window.edit_actions_manager.push_undo_state()
        ungrouped_count = 0
        for item in groupable:
            if hasattr(item, "group_id") and item.group_id is not None:
                item.group_id = None
                ungrouped_count += 1
            item.is_group_selected = False
            item.update()

        # Show status message
        if hasattr(self.main_window, "statusBar") and ungrouped_count > 0:
            self.main_window.statusBar().showMessage(
                f"Ungrouped {ungrouped_count} items", 3000
            )

        if self.interaction_handler:
            self.interaction_handler.update_group_overlay([])
        self._sync_selection_visuals()

    def _sync_selection_visuals(self):
        """Centralized synchronization of the group selection flags and overlay."""
        # Safety check: ensure main window and scene are valid and not deleted
        try:
            if (
                not self.main_window
                or not self.main_window.scene
                or sip_isdeleted_safe(self.main_window.scene)
            ):
                return

            selected_items = self.main_window.scene.selectedItems()
        except (RuntimeError, AttributeError):
            # This can happen during application shutdown if objects are partially destroyed
            return

        if not selected_items:
            # Clear all
            for item in self.main_window.scene.items():
                if hasattr(item, "is_group_selected") and item.is_group_selected:
                    item.is_group_selected = False
                    item.update()
            return

        # Identify items that belong to a logical group (Explicit Group or Molecule)
        # We use get_logical_units to find blocks.
        # Any unit with > 1 item is a candidate for purple highlight if selected.
        valid_selected = [i for i in selected_items if not sip_isdeleted_safe(i)]
        units = self.get_logical_units(valid_selected)
        purple_items = set()

        for unit_dict in units:
            members = unit_dict["members"]
            unit_selected = [i for i in members if i.isSelected()]
            selected_count = len(unit_selected)
            unit_type = unit_dict.get("type", "item")

            # Highlight purple ONLY if it's an explicit Group OR a multi-item selection that is NOT a Molecule
            # Molecules should stay blue as per user request.
            if selected_count > 1:
                if unit_type == "group":
                    for item in unit_selected:
                        purple_items.add(item)
                # If it's a molecule, we stay blue (don't add to purple_items)
            elif selected_count == 1:
                # Single item from unit selected.
                # Only highlight purple if it has an explicit group_id (part of a group)
                item = unit_selected[0]
                if hasattr(item, "group_id") and item.group_id:
                    purple_items.add(item)
        # Update flags for ALL items in the scene that have the attribute
        for item in self.main_window.scene.items():
            if sip_isdeleted_safe(item):
                continue
            if hasattr(item, "is_group_selected"):
                old_val = item.is_group_selected
                new_val = item in purple_items
                if old_val != new_val:
                    item.is_group_selected = new_val
                    # Note: we don't reset show_handles_in_group here anymore to allow
                    # it to persist during re-selection (drill-down).

                    if hasattr(item, "update_handle_visibility"):
                        item.update_handle_visibility()
                    item.update()

            # Reset handle flag if item is not the SINGLE selection
            # (Allows switching back to group selection or other items to clear the drill-down state)
            if hasattr(item, "show_handles_in_group") and item.show_handles_in_group:
                if not item.isSelected() or len(selected_items) > 1:
                    item.show_handles_in_group = False
                    if hasattr(item, "update_handle_visibility"):
                        item.update_handle_visibility()
                    item.update()

        # If logical grouping is being used, we should also update the overlay
        # (This is already handled by individual tool logic usually, but keep it in mind)

    def get_logical_units(self, items):
        """
        Group selected items into logical "moveable units".
        Rules:
        1. Explicit Groups (all scene items with same group_id)
        2. Molecules: Each connected fragment = one unit (separate molecules can align independently)
        3. Single Reaction Items
        """
        scene = self.main_window.scene if self.main_window else None
        if not scene:
            return []

        visited = set()
        units = []

        # Helper: Get connected fragment by traversing bonds visually
        def get_connected_molecule_fragment(start_item):
            """Traverse molecule connectivity via scene items (not mol_data)"""
            fragment = set()
            stack = [start_item]
            visited_in_fragment = {start_item}

            while stack:
                current = stack.pop()
                fragment.add(current)

                # If this is an atom, find connected bonds
                if hasattr(current, "bonds"):
                    for bond_item in current.bonds:
                        if bond_item not in visited_in_fragment and bond_item.scene():
                            visited_in_fragment.add(bond_item)
                            stack.append(bond_item)
                            fragment.add(bond_item)

                            # From bond, find other atom (BondItem has atom1/atom2, NOT atom1_item/atom2_item)
                            if hasattr(bond_item, "atom1") and bond_item.atom1:
                                if (
                                    bond_item.atom1 != current
                                    and bond_item.atom1 not in visited_in_fragment
                                ):
                                    visited_in_fragment.add(bond_item.atom1)
                                    stack.append(bond_item.atom1)
                            if hasattr(bond_item, "atom2") and bond_item.atom2:
                                if (
                                    bond_item.atom2 != current
                                    and bond_item.atom2 not in visited_in_fragment
                                ):
                                    visited_in_fragment.add(bond_item.atom2)
                                    stack.append(bond_item.atom2)

                # If this is a bond, get both atoms
                elif hasattr(current, "atom1") or hasattr(current, "atom2"):
                    for atom_item in [
                        getattr(current, "atom1", None),
                        getattr(current, "atom2", None),
                    ]:
                        if atom_item and atom_item not in visited_in_fragment:
                            visited_in_fragment.add(atom_item)
                            stack.append(atom_item)

            return fragment

        for item in items:
            if sip_isdeleted_safe(item) or item in visited:
                continue

            unit_members = []

            # 1. Explicit Group
            if hasattr(item, "group_id") and item.group_id:
                gid = item.group_id
                unit_members = [
                    i
                    for i in scene.items()
                    if hasattr(i, "group_id") and i.group_id == gid
                ]
                unit_type = "group"

            # 2. Molecule atom/bond - get connected fragment
            elif (
                hasattr(item, "atom_id")
                or hasattr(item, "bonds")
                or hasattr(item, "atom1")
            ):
                fragment = get_connected_molecule_fragment(item)
                unit_members = list(fragment) if fragment else [item]
                unit_type = "molecule"

            # 3. Reaction Items
            else:
                unit_members = [item]
                unit_type = "item"

            # Mark as visited
            for m in unit_members:
                visited.add(m)

            if not unit_members:
                continue

            # Filter out deleted members before calculating bounds
            unit_members = [m for m in unit_members if not sip_isdeleted_safe(m)]
            if not unit_members:
                continue

            # Calculate bounds
            rect = QRectF()
            for m in unit_members:
                if rect.isNull():
                    rect = m.sceneBoundingRect()
                else:
                    rect = rect.united(m.sceneBoundingRect())

            units.append(
                {
                    "members": unit_members,
                    "type": unit_type,
                    "rect": rect,
                    "center": rect.center(),
                }
            )

            # Calculate COG (Average of Atom positions for Molecules, or Center for others)
            cog_x = 0
            cog_y = 0
            count = 0

            # Prioritize Atoms for COG - use actual atom position, not boundingRect
            atom_members = [m for m in unit_members if hasattr(m, "atom_id")]
            target_members = atom_members if atom_members else unit_members

            for m in target_members:
                # Use scenePos for atoms (actual position), sceneBoundingRect for others
                if hasattr(m, "atom_id"):
                    pos = m.scenePos()
                    cog_x += pos.x()
                    cog_y += pos.y()
                else:
                    c = m.sceneBoundingRect().center()
                    cog_x += c.x()
                    cog_y += c.y()
                count += 1

            if count > 0:
                units[-1]["cog"] = QPointF(cog_x / count, cog_y / count)
            else:
                units[-1]["cog"] = rect.center()

        return units

    def align_items(self, mode):
        """Align selected items (Groups/Molecules Rigidly)."""
        if not self.main_window or not self.main_window.scene:
            return

        items = self.main_window.scene.selectedItems()
        if len(items) < 2:
            return

        # Get rigid units (whole molecules)
        units = self.get_logical_units(items)
        if len(units) < 2:
            return

        rects = [u["rect"] for u in units]

        moved_atoms = []

        # Calculate and apply movement for each unit
        for u in units:
            dx = 0
            dy = 0

            if mode == "top":
                ref = min(r.top() for r in rects)
                dy = ref - u["rect"].top()
            elif mode == "bottom":
                ref = max(r.bottom() for r in rects)
                dy = ref - u["rect"].bottom()
            elif mode == "center_v":
                avg_y = sum(u2["center"].y() for u2 in units) / len(units)
                dy = avg_y - u["center"].y()
            elif mode == "left":
                ref = min(r.left() for r in rects)
                dx = ref - u["rect"].left()
            elif mode == "right":
                ref = max(r.right() for r in rects)
                dx = ref - u["rect"].right()
            elif mode == "center_h":
                avg_x = sum(u2["center"].x() for u2 in units) / len(units)
                dx = avg_x - u["center"].x()

            # Apply delta
            if abs(dx) > 0.1 or abs(dy) > 0.1:
                for item in u["members"]:
                    if sip_isdeleted_safe(item):
                        continue
                    # Only move atoms, bonds update automatically
                    if hasattr(item, "atom_id"):
                        # Update core data
                        if hasattr(self.main_window, "data"):
                            mol_data = self.main_window.data
                            if hasattr(mol_data, "atoms"):
                                aid = item.atom_id
                                if aid in mol_data.atoms:
                                    atom_obj = mol_data.atoms[aid].get("atom", None)
                                    if atom_obj and hasattr(atom_obj, "x"):
                                        atom_obj.x += dx
                                        atom_obj.y += dy

                        # Move visual item (bonds update via itemChange)
                        item.moveBy(dx, dy)
                        moved_atoms.append(item)

                    # Move reaction items normally
                    elif not hasattr(item, "atom1"):
                        item.moveBy(dx, dy)

        # Update bond positions
        if moved_atoms:
            self.main_window.scene.update_connected_bonds(moved_atoms)

        if hasattr(self.main_window, "edit_3d_manager") and hasattr(
            self.main_window.edit_3d_manager, "update_2d_measurement_labels"
        ):
            self.main_window.edit_3d_manager.update_2d_measurement_labels()

        self.main_window.scene.update_all_items()

        # Push undo AFTER change completes
        mgr_edit = getattr(self.main_window, "edit_actions_manager", None)
        if mgr_edit:
            push_undo_func = getattr(mgr_edit, "push_undo_state", None)
            if push_undo_func:
                push_undo_func()
            else:
                print("Error: edit_actions_manager missing 'push_undo_state'")
        else:
            print("Error: main_window missing 'edit_actions_manager'")

    def distribute_items(self, axis):
        """Distribute selected items evenly (Groups/Molecules Rigidly)."""
        if not self.main_window or not self.main_window.scene:
            return

        items = self.main_window.scene.selectedItems()
        if len(items) < 3:
            return

        units = self.get_logical_units(items)
        if len(units) < 3:
            return

        moved_atoms = []

        def update_atom_data_model(item, delta, axis_char):
            if not hasattr(self.main_window, "data"):
                return
            mol_data = self.main_window.data
            if not hasattr(mol_data, "atoms"):
                return

            aid = getattr(item, "atom_id", None)
            if aid in mol_data.atoms:
                atom_obj = mol_data.atoms[aid].get("atom", None)
                if atom_obj and hasattr(atom_obj, axis_char):
                    current_val = getattr(atom_obj, axis_char)
                    setattr(atom_obj, axis_char, current_val + delta)

        if axis == "horizontal":
            units.sort(key=lambda u: (u["cog"].x(), u["cog"].y()))
            current_centers = [u["cog"].x() for u in units]
            start_val, end_val = current_centers[0], current_centers[-1]
            gap = (end_val - start_val) / (len(units) - 1)

            for i in range(1, len(units) - 1):
                if (
                    abs(current_centers[i] - start_val) < 1.0
                    or abs(current_centers[i] - end_val) < 1.0
                ):
                    continue
                dx = start_val + (i * gap) - current_centers[i]
                if abs(dx) > 0.1:
                    for item in units[i]["members"]:
                        if sip_isdeleted_safe(item):
                            continue
                        if hasattr(item, "atom_id"):
                            update_atom_data_model(item, dx, "x")
                            item.moveBy(dx, 0)
                            moved_atoms.append(item)
                        elif not hasattr(item, "atom1"):
                            item.moveBy(dx, 0)

        elif axis == "vertical":
            units.sort(key=lambda u: (u["cog"].y(), u["cog"].x()))
            current_centers = [u["cog"].y() for u in units]
            start_val, end_val = current_centers[0], current_centers[-1]
            gap = (end_val - start_val) / (len(units) - 1)

            for i in range(1, len(units) - 1):
                if (
                    abs(current_centers[i] - start_val) < 1.0
                    or abs(current_centers[i] - end_val) < 1.0
                ):
                    continue
                dy = start_val + (i * gap) - current_centers[i]
                if abs(dy) > 0.1:
                    for item in units[i]["members"]:
                        if sip_isdeleted_safe(item):
                            continue
                        if hasattr(item, "atom_id"):
                            update_atom_data_model(item, dy, "y")
                            item.moveBy(0, dy)
                            moved_atoms.append(item)
                        elif not hasattr(item, "atom1"):
                            item.moveBy(0, dy)

        # ---------------------------------------------------------
        # 結合(Bond)と画面の更新
        # ---------------------------------------------------------
        if moved_atoms:
            self.main_window.scene.update_connected_bonds(moved_atoms)

        if hasattr(self.main_window, "edit_3d_manager") and hasattr(
            self.main_window.edit_3d_manager, "update_2d_measurement_labels"
        ):
            self.main_window.edit_3d_manager.update_2d_measurement_labels()

        self.main_window.scene.update_all_items()

        mgr_edit = getattr(self.main_window, "edit_actions_manager", None)
        if mgr_edit:
            push_undo_func = getattr(mgr_edit, "push_undo_state", None)
            if push_undo_func:
                push_undo_func()
            else:
                print("Error: edit_actions_manager missing 'push_undo_state'")
        else:
            print("Error: main_window missing 'edit_actions_manager'")

    def toggle_subscript(self):
        self._toggle_text_format("sub")

    def toggle_superscript(self):
        self._toggle_text_format("sup")

    def _toggle_text_format(self, mode):
        if not self.main_window or not self.main_window.scene:
            return

        # Check for focused text item (editing mode)
        item = self.main_window.scene.focusItem()
        from .items import ReactionTextItem
        from PyQt6.QtGui import QTextCharFormat

        # If no focus item, check selected items
        targets = []
        if isinstance(item, ReactionTextItem) and (
            item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            targets.append(item)
        else:
            sel = self.main_window.scene.selectedItems()
            targets = [i for i in sel if isinstance(i, ReactionTextItem)]

        if not targets:
            return

        self.main_window.edit_actions_manager.push_undo_state()

        for item in targets:
            cursor = item.textCursor()
            fmt = cursor.charFormat()
            current_align = fmt.verticalAlignment()

            new_align = QTextCharFormat.VerticalAlignment.AlignNormal
            if mode == "sub":
                if current_align != QTextCharFormat.VerticalAlignment.AlignSubScript:
                    new_align = QTextCharFormat.VerticalAlignment.AlignSubScript
            elif mode == "sup":
                if current_align != QTextCharFormat.VerticalAlignment.AlignSuperScript:
                    new_align = QTextCharFormat.VerticalAlignment.AlignSuperScript

            fmt.setVerticalAlignment(new_align)

            # If valid cursor selection or editing
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            elif (
                item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                # In edit mode but no selection - set format for future typing
                cursor.mergeCharFormat(fmt)
                item.setTextCursor(cursor)
            else:
                # Apply to whole document if item is selected object
                cursor.select(QTextCursor.SelectionType.Document)
                cursor.mergeCharFormat(fmt)

    def apply_text_style(self, style):
        """Apply bold/italic/underline to selected text only."""
        if not self.main_window or not self.main_window.scene:
            return

        from .items import ReactionTextItem

        # Get focused or selected text items
        item = self.main_window.scene.focusItem()
        targets = []

        if isinstance(item, ReactionTextItem) and (
            item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            targets.append(item)
        else:
            sel = self.main_window.scene.selectedItems()
            targets = [i for i in sel if isinstance(i, ReactionTextItem)]

        if not targets:
            return

        self.main_window.edit_actions_manager.push_undo_state()

        for item in targets:
            cursor = item.textCursor()

            # Apply if selection exists OR if valid target (whole item)
            if cursor.hasSelection():
                # Apply to selection
                pass
            elif (
                item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                # In edit mode, no selection -> set alignment for future?
                # For bold/italic, usually we toggle 'current char format' for insertion.
                # But mergeCharFormat on cursor works for that.
                pass
            else:
                # Select whole document
                cursor.select(QTextCursor.SelectionType.Document)

            # Determine current state from cursor (or start of selection)
            current_fmt = cursor.charFormat()

            # Create a NEW clean format to only apply the specific change
            # merging a clean format with just one property set will preserve other properties (like subscript)
            new_fmt = QTextCharFormat()

            if style == "bold":
                current_weight = current_fmt.fontWeight()
                # Toggle based on current state
                target_weight = (
                    QFont.Weight.Bold
                    if current_weight != QFont.Weight.Bold
                    else QFont.Weight.Normal
                )
                new_fmt.setFontWeight(target_weight)
            elif style == "italic":
                new_fmt.setFontItalic(not current_fmt.fontItalic())
            elif style == "underline":
                new_fmt.setFontUnderline(not current_fmt.fontUnderline())

            cursor.mergeCharFormat(new_fmt)

            if (
                item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
                and not cursor.hasSelection()
            ):
                # Update the cursor for typing
                item.setTextCursor(cursor)

    def apply_chem_style(self):
        """Robust chemical formatting (Sub/Sup) for targets."""
        if not self.main_window or not self.main_window.scene:
            return

        from .items import ReactionTextItem
        from PyQt6.QtGui import QTextCharFormat
        import re

        focus_item = self.main_window.scene.focusItem()
        targets = []
        if isinstance(focus_item, ReactionTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            targets.append(focus_item)
        else:
            sel = self.main_window.scene.selectedItems()
            targets = [i for i in sel if isinstance(i, ReactionTextItem)]

        if not targets:
            return

        self.main_window.edit_actions_manager.push_undo_state()

        for item in targets:
            # We work with HTML to allow complex formatting updates,
            # or use cursor movements on the document.
            cursor = item.textCursor()
            cursor.beginEditBlock()

            # Step 1: Normalize (Reset formatting)
            cursor.select(cursor.SelectionType.Document)
            fmt_norm = QTextCharFormat()
            fmt_norm.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
            # Preserving font size/bold/italic from item base if needed,
            # but usually a reset is fine for the whole block.
            cursor.setCharFormat(fmt_norm)

            text = item.toPlainText()

            # Formats
            sub_fmt = QTextCharFormat()
            sub_fmt.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignSubScript
            )
            sup_fmt = QTextCharFormat()
            sup_fmt.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignSuperScript
            )

            # List of (start, end, format, new_text) for replacements
            actions = []

            def add_action(s, e, f, t):
                # Check for ANY intersection with existing actions
                for as_s, as_e, _, _ in actions:
                    if max(s, as_s) < min(e, as_e):
                        return False
                actions.append((s, e, f, t))
                return True

            # 1. LaTeX-style braces: _{...} or ^{...}
            for m in re.finditer(r"([_\^])\{([^}]*)\}", text):
                atype = m.group(1)
                content = m.group(2)
                add_action(
                    m.start(), m.end(), sub_fmt if atype == "_" else sup_fmt, content
                )

            # 2. Traditional triggers: _X or ^X or ~X (where X is not {)
            for m in re.finditer(r"([_\^~])([^{}\s])", text):
                atype = m.group(1)
                content = m.group(2)
                add_action(
                    m.start(), m.end(), sub_fmt if atype == "_" else sup_fmt, content
                )

            # 3. Smart Subscripts: Numbers following letters
            for m in re.finditer(r"([A-Za-z])([0-9]+)", text):
                # We only format the digit group
                add_action(m.start(2), m.end(2), sub_fmt, m.group(2))

            # 4. Smart Charges: + or - or 2+ etc. at the end of a word cluster
            for m in re.finditer(r"([0-9]*[\+\-])(?!\w)", text):
                add_action(m.start(), m.end(), sup_fmt, m.group(1))

            # Sort actions by start pos descending to allow safe removal/insertion
            actions.sort(key=lambda x: x[0], reverse=True)

            for start, end, fmt, new_text in actions:
                cursor.setPosition(start)
                cursor.setPosition(end, cursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertText(new_text, fmt)

            cursor.endEditBlock()
            item.update()

    def duplicate_items_immediate(self, items):
        """
        Duplicate a list of items immediately (for Ctrl+Drag).
        Returns the list of new items.
        Supports both Reaction Items and native Atoms/Bonds.
        """
        if not items:
            return []

        new_items = []
        scene = self.main_window.scene

        # === 1. Handle Molecules (Atoms + Bonds) ===
        atom_items = [
            i for i in items if hasattr(i, "atom_id") and not hasattr(i, "atom1")
        ]
        [i for i in items if hasattr(i, "atom1") and hasattr(i, "atom2")]

        if atom_items:
            try:
                # Build set of selected atom IDs
                selected_atom_ids = {a.atom_id for a in atom_items}

                # Create mapping: old_atom_id -> new_atom_item
                old_to_new_atom = {}

                for atom_item in atom_items:
                    try:
                        # Get atom data from main data structure
                        atom_id = atom_item.atom_id
                        if atom_id not in self.main_window.data.atoms:
                            continue

                        atom_data = self.main_window.data.atoms[atom_id]
                        atom_obj = atom_data.get("atom", None)

                        symbol = atom_data.get("symbol", "C")
                        pos = atom_item.pos()
                        charge = getattr(atom_obj, "charge", 0) if atom_obj else 0
                        radical = getattr(atom_obj, "radical", 0) if atom_obj else 0

                        # Create new atom using scene's API
                        new_id = scene.create_atom(
                            symbol, pos, charge=charge, radical=radical
                        )
                        if new_id and new_id in self.main_window.data.atoms:
                            new_atom_item = self.main_window.data.atoms[new_id]["item"]
                            old_to_new_atom[atom_id] = new_atom_item
                            new_items.append(new_atom_item)
                    except Exception as _e:
                        logging.warning("[mode_manager.py:3004] silenced: %s", _e)

                # Create bonds between the new atoms
                for (id1, id2), bond_data in list(self.main_window.data.bonds.items()):
                    if id1 in selected_atom_ids and id2 in selected_atom_ids:
                        if id1 in old_to_new_atom and id2 in old_to_new_atom:
                            try:
                                new_atom1 = old_to_new_atom[id1]
                                new_atom2 = old_to_new_atom[id2]
                                order = bond_data.get("order", 1)
                                stereo = bond_data.get("stereo", 0)
                                scene.create_bond(
                                    new_atom1,
                                    new_atom2,
                                    bond_order=order,
                                    bond_stereo=stereo,
                                )
                            except Exception as _e:
                                logging.warning(
                                    "[mode_manager.py:3017] silenced: %s", _e
                                )
            except Exception as _e:
                logging.warning("[mode_manager.py:3019] silenced: %s", _e)

        # === 2. Handle Reaction Items ===
        snapshot = []
        for item in items:
            if hasattr(item, "create_json_data"):
                snapshot.append(item.create_json_data())

        if not snapshot and not new_items:
            return []

        # 2. Remap Group IDs
        import uuid

        old_to_new_group = {}
        for data in snapshot:
            if "group_id" in data and data["group_id"]:
                gid = data["group_id"]
                if gid not in old_to_new_group:
                    old_to_new_group[gid] = str(uuid.uuid4())
                data["group_id"] = old_to_new_group[gid]

        # 3. Create New Reaction Items (append to new_items, don't reset)

        # Import Item Classes locally to avoid circular dependency issues
        from .items import (
            ReactionArrowItem,
            ReactionPlusItem,
            ReactionTextItem,
            ReactionMinusItem,
            ReactionResonanceArrowItem,
            ReactionEquilibriumArrowItem,
            ReactionRetroArrowItem,
            ReactionNoArrowItem,
            ReactionDashedArrowItem,
            ReactionCurvedArrowItem,
            ReactionBracketItem,
            ReactionCircleItem,
            ReactionLineItem,
            ReactionCurvedLineItem,
            ReactionFreehandItem,
        )

        for data in snapshot:
            item_type = data.get("type", None)
            new_item = None

            try:
                if item_type == "arrow":
                    new_item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "arrow_res":
                    new_item = ReactionResonanceArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "arrow_eq":
                    new_item = ReactionEquilibriumArrowItem(
                        QPointF(0, 0), QPointF(0, 0)
                    )
                elif item_type == "arrow_retro":
                    new_item = ReactionRetroArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "arrow_dashed":
                    new_item = ReactionDashedArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "arrow_no":
                    new_item = ReactionNoArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "curved_double":
                    new_item = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "curved_fish":
                    new_item = ReactionCurvedArrowItem(
                        QPointF(0, 0), QPointF(0, 0), is_fish_hook=True
                    )
                elif item_type == "plus":
                    new_item = ReactionPlusItem(QPointF(0, 0))
                elif item_type == "minus":
                    new_item = ReactionMinusItem(QPointF(0, 0))
                elif item_type == "text":
                    new_item = ReactionTextItem("", QPointF(0, 0))
                elif item_type == "bracket":
                    new_item = ReactionBracketItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "circle":
                    new_item = ReactionCircleItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "line":
                    new_item = ReactionLineItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "line_dashed":
                    new_item = ReactionLineItem(QPointF(0, 0), QPointF(0, 0))
                    new_item.line_style = "dashed"
                elif item_type == "line_curved":
                    new_item = ReactionCurvedLineItem(QPointF(0, 0), QPointF(0, 0))
                elif item_type == "freehand":
                    new_item = ReactionFreehandItem(QPointF(0, 0))

                if new_item:
                    # Generic Properties
                    if hasattr(new_item, "pen_color") and "color" in data:
                        new_item.pen_color = QColor(data["color"])
                    if hasattr(new_item, "pen_width") and "width" in data:
                        new_item.pen_width = data["width"]
                    if "rotation" in data:
                        new_item.setRotation(data["rotation"])
                    if "z" in data:
                        new_item.setZValue(data["z"])
                    if "group_id" in data:
                        new_item.group_id = data["group_id"]

                    # Specific Properties
                    if item_type in [
                        "arrow",
                        "arrow_res",
                        "arrow_retro",
                        "arrow_dashed",
                        "arrow_no",
                        "curved_double",
                        "curved_fish",
                        "line",
                        "line_dashed",
                        "line_curved",
                    ]:
                        sx = data.get("start_x", 0)
                        sy = data.get("start_y", 0)
                        ex = data.get("end_x", 0)
                        ey = data.get("end_y", 0)

                        new_item.setPos(
                            0, 0
                        )  # Item pos is 0,0; start/end are absolute in scene
                        new_item.start_p = QPointF(sx, sy)
                        new_item.end_p = QPointF(ex, ey)

                        if "head_style" in data and hasattr(new_item, "head_style"):
                            new_item.head_style = data["head_style"]
                        if "head_size" in data and hasattr(new_item, "head_size"):
                            new_item.head_size = data["head_size"]
                        if "head_angle" in data and hasattr(new_item, "head_angle"):
                            new_item.head_angle = data["head_angle"]
                        if "head_concavity" in data and hasattr(
                            new_item, "head_concavity"
                        ):
                            new_item.head_concavity = data["head_concavity"]

                        if (
                            "control_x" in data
                            and "control_y" in data
                            and hasattr(new_item, "control_p")
                        ):
                            new_item.control_p = QPointF(
                                data["control_x"], data["control_y"]
                            )

                    elif item_type == "text":
                        new_item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                        if "text" in data:
                            new_item.setPlainText(data["text"])
                        if "html" in data:
                            new_item.setHtml(data["html"])

                        f = new_item.font()
                        if "font_family" in data:
                            f.setFamily(data["font_family"])
                        if "font_size" in data:
                            f.setPointSize(data["font_size"])
                        if "bold" in data:
                            f.setBold(data["bold"])
                        if "italic" in data:
                            f.setItalic(data["italic"])
                        if "underline" in data:
                            f.setUnderline(data["underline"])
                        new_item.setFont(f)

                        if "color" in data:
                            new_item.setDefaultTextColor(QColor(data["color"]))

                    elif item_type in ["bracket", "circle"]:
                        new_item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                        w = data.get("width", 50)
                        h = data.get("height", 50)
                        new_item.rect = QRectF(0, 0, w, h)
                        if "bracket_type" in data:
                            new_item.bracket_type = data["bracket_type"]
                        if "line_style" in data:
                            new_item.line_style = data["line_style"]
                        if "shape_type" in data:
                            new_item.shape_type = data["shape_type"]
                        new_item.sync_handles()

                    elif item_type == "freehand":
                        new_item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                        if "points" in data:
                            pts = [QPointF(p[0], p[1]) for p in data["points"]]
                            new_item.set_points(pts)

                    elif item_type in ["plus", "minus"]:
                        new_item.setPos(QPointF(data.get("x", 0), data.get("y", 0)))
                        if "size" in data:
                            new_item.size = data["size"]

                    scene.addItem(new_item)
                    new_item.update()
                    new_items.append(new_item)

            except Exception as e:
                # print(f"Error duplicating item {item_type}: {e}")
                logging.warning("[mode_manager.py:3167] silenced: %s", e)

        return new_items
        """Copy selected items to system clipboard."""
        if not self.main_window:
            return

        # Check if we're editing text - if so, let default copy work
        focus_item = self.main_window.scene.focusItem()
        from .items import ReactionTextItem

        if isinstance(focus_item, ReactionTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            return

        # Call the patched copy method of the main window
        if hasattr(self.main_window, "edit_actions_manager") and hasattr(
            self.main_window.edit_actions_manager, "copy_selection"
        ):
            self.main_window.edit_actions_manager.copy_selection()
        elif hasattr(self.main_window, "main_window_edit_actions"):
            self.main_window.main_window_edit_actions.copy_selection()
        else:
            # Fallback (should not happen if patched)
            self.main_window.statusBar().showMessage(
                "Copy failed: Edit actions not found", 3000
            )

    def cut_reaction_items(self):
        """Cut selected items to system clipboard."""
        if not self.main_window:
            return

        # Check if we're editing text - if so, let default cut work
        focus_item = self.main_window.scene.focusItem()
        from .items import ReactionTextItem

        if isinstance(focus_item, ReactionTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            return

        # Copy first
        self.copy_reaction_items()

        # Then delete
        if hasattr(self.main_window, "main_window_edit_actions"):
            self.main_window.main_window_edit_actions.delete_selection()
        else:
            # Fallback to direct scene delete
            items = self.main_window.scene.selectedItems()
            if items:
                delete_func = getattr(self.main_window.scene, "delete_items", None)
                if delete_func:
                    delete_func(items)
                else:
                    print("Error: scene missing 'delete_items'")

    def paste_reaction_items(self):
        """Paste items from system clipboard."""
        if not self.main_window:
            return

        # Check if we're editing text - if so, let default paste work
        focus_item = self.main_window.scene.focusItem()
        from .items import ReactionTextItem

        if isinstance(focus_item, ReactionTextItem) and (
            focus_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        ):
            return

        # Call the patched paste method of the main window
        # The patcher should have applied 'paste_from_clipboard' to MainWindowEditActions
        if hasattr(self.main_window, "edit_actions_manager") and hasattr(
            self.main_window.edit_actions_manager, "paste_from_clipboard"
        ):
            self.main_window.edit_actions_manager.paste_from_clipboard()
        elif hasattr(self.main_window, "main_window_edit_actions"):
            self.main_window.main_window_edit_actions.paste_from_clipboard()
        else:
            # Fallback (should not happen if patched)
            self.main_window.statusBar().showMessage(
                "Paste failed: Edit actions not found", 3000
            )

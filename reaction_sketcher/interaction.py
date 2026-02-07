#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtCore import QObject, QEvent, Qt, QPointF, QLineF
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QIcon, QAction, QColor, QFont
from PyQt6.QtWidgets import QGraphicsItem, QApplication
from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                    ReactionMinusItem, ReactionResonanceArrowItem, 
                    ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                    ReactionNoArrowItem, ReactionCurvedArrowItem,
                    ReactionBracketItem, ReactionCircleItem)
from .icons import create_style_icon, create_shape_variant_icon

class InteractionHandler(QObject):
    def __init__(self, main_window, mode_manager):
        super().__init__()
        self.main_window = main_window
        self.mode_manager = mode_manager
        self.active_tool = None # "arrow", "plus", "text"
        self.preview_item = None
        self.start_pos = None
        
    def set_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name and tool_name != "select":
            # Set a flag to avoid infinite loops when we programmatically change main mode
            self._internal_mode_change = True
            try:
                if hasattr(self.main_window, 'activate_select_mode'):
                    self.main_window.activate_select_mode()
            finally:
                self._internal_mode_change = False
        
    def eventFilter(self, watched, event):
        if not self.mode_manager.is_reaction_mode:
            return False

        # PROACTIVE SYNC: If main window is in a placement/edit mode (atom, bond, template),
        # don't allow reaction drawing events to be handled here.
        try:
            if not self.main_window or not self.main_window.scene:
                return False
            scene_mode = getattr(self.main_window.scene, 'mode', 'select')
        except (RuntimeError, AttributeError):
            # Scene or main window was deleted during teardown
            return False

        if scene_mode != 'select' and scene_mode != 'bond_2_5': # bond_2_5 is E/Z mode which is fine
            return False

        # SAFEGUARD: Ensure the scene has this attribute to avoid crash in release event
        # if the press was intercepted by us.
        try:
            if not hasattr(self.main_window.scene, 'initial_positions_in_event'):
                self.main_window.scene.initial_positions_in_event = {}
        except (RuntimeError, AttributeError):
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            return self.handle_mouse_press(event)
        elif event.type() == QEvent.Type.MouseMove:
            return self.handle_mouse_move(event)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            return self.handle_mouse_release(event)
        elif event.type() == QEvent.Type.KeyPress:
            return self.handle_key_press(event)
            
        return False

    def handle_mouse_press(self, event):
        # scene_pos = self.main_window.view_2d.mapToScene(event.pos())
        
        if event.button() == Qt.MouseButton.RightButton:
            # Context Menu logic
            scene_pos = self.main_window.view_2d.mapToScene(event.pos())
            item = self.main_window.scene.itemAt(scene_pos, self.main_window.view_2d.transform())
            
            # If clicking on a handle, ignore (pass to default) or show parent's menu?
            # If item is None, maybe show global menu?
            
            if item:
                # Check if this is a Reaction Item
                # Duck Typing
                if not hasattr(item, "create_json_data"):
                    return False

                # Select the item if not already selected (and not in a multi-selection)
                selected = self.main_window.scene.selectedItems()
                if item not in selected:
                    self.main_window.scene.clearSelection()
                    item.setSelected(True)
                    selected = [item]
                
                from PyQt6.QtWidgets import QMenu
                from .icons import create_style_icon
                
                menu = QMenu(self.main_window)
                
                # Check what kind of item(s) we have. 
                # If multiple, maybe just show "Delete".
                # If single, show specific options.
                
                target = item
                # Determine main target (if handle, get parent)
                if hasattr(item, "handle_type") and item.parentItem():
                     target = item.parentItem()
                     
                # Add Style Options
                if hasattr(target, "head_style"):
                    # Arrow Styles
                    # Check if it allows head changes (not simple lines)
                    # ReactionArrowItem has head_style. ReactionLineItem (subclass) has it but maybe shouldn't?
                    # We can check class or type property.
                    json_data = target.create_json_data() if hasattr(target, "create_json_data") else {}
                    t_type = json_data.get("type", "")
                    
                    if t_type in ["arrow", "arrow_eq", "arrow_res", "arrow_retro", "arrow_dashed", "curved_arrow", "curved_double", "curved_fish"]:
                        # Arrow styling
                        style_menu = menu.addMenu("Arrow Head")
                        
                        def set_head(s):
                            target.head_style = s
                            target.update()
                            self.main_window.push_undo_state()

                        a_tri = style_menu.addAction(create_style_icon("curved", "triangle"), "Triangle")
                        a_tri.setCheckable(True)
                        a_tri.setChecked(target.head_style == "triangle")
                        a_tri.triggered.connect(lambda: set_head("triangle"))
                        
                        a_chev = style_menu.addAction(create_style_icon("curved", "chevron"), "Chevron (Sharp)")
                        a_chev.setCheckable(True)
                        a_chev.setChecked(target.head_style == "chevron")
                        a_chev.triggered.connect(lambda: set_head("chevron"))

                        a_chev_c = style_menu.addAction(create_style_icon("curved", "chevron_curved"), "Chevron (Curved)")
                        a_chev_c.setCheckable(True)
                        a_chev_c.setChecked(target.head_style == "chevron_curved")
                        a_chev_c.triggered.connect(lambda: set_head("chevron_curved"))
                        
                        a_harp = style_menu.addAction(create_style_icon("curved", "harpoon"), "Harpoon")
                        a_harp.setCheckable(True)
                        a_harp.setChecked(target.head_style == "harpoon")
                        a_harp.triggered.connect(lambda: set_head("harpoon"))

                if hasattr(target, "negation_style"):
                    # No-Reaction Arrow
                    neg_menu = menu.addMenu("Negation Style")
                    def set_neg(s):
                        target.negation_style = s
                        target.update()
                        self.main_window.push_undo_state()

                    neg_menu.addAction("Cross (X)", lambda: set_neg("cross"))
                    neg_menu.addAction("Slash (/)", lambda: set_neg("slash"))
                    neg_menu.addAction("Double Slash (//)", lambda: set_neg("double_slash"))

                from .items import ReactionCircleItem, ReactionBracketItem
                if isinstance(target, ReactionCircleItem):
                    # Consolidated 4 Options for Circle/Rectangle
                    shape_style_menu = menu.addMenu("Shape Style")
                    def set_variant(s, l):
                        target.shape_type = s
                        target.line_style = l
                        target.update()
                        self.main_window.push_undo_state()
                    
                    variants = [
                        ("Solid Rectangle", "rectangle", "solid"),
                        ("Dashed Rectangle", "rectangle", "dashed"),
                        ("Solid Circle", "circle", "solid"),
                        ("Dashed Circle", "circle", "dashed")
                    ]
                    for label, stype, lstyle in variants:
                        act = shape_style_menu.addAction(create_shape_variant_icon(stype, lstyle), label)
                        act.setCheckable(True)
                        act.setChecked(target.shape_type == stype and target.line_style == lstyle)
                        def make_cb(s, l): return (lambda: set_variant(s, l))
                        act.triggered.connect(make_cb(stype, lstyle))

                elif isinstance(target, ReactionBracketItem):
                    # Bracket Type
                    br_menu = menu.addMenu("Bracket Type")
                    def set_br(s):
                        target.bracket_type = s
                        target.update()
                        self.main_window.push_undo_state()
                    
                    for label, btype in [("Square [ ]", "square"), ("Round ( )", "round"), ("Curly { }", "curly")]:
                        act = br_menu.addAction(label)
                        act.setCheckable(True)
                        act.setChecked(target.bracket_type == btype)
                        def make_cb(bt): return (lambda: set_br(bt))
                        act.triggered.connect(make_cb(btype))

                    # Line Style for Bracket
                    line_menu = menu.addMenu("Line Style")
                    def set_bl(s):
                        target.line_style = s
                        target.update()
                        self.main_window.push_undo_state()
                    
                    for s in ["solid", "dashed"]:
                        act = line_menu.addAction(s.capitalize())
                        act.setCheckable(True)
                        act.setChecked(target.line_style == s)
                        def make_cb(ls): return (lambda: set_bl(ls))
                        act.triggered.connect(make_cb(s))

                elif hasattr(target, "line_style"):
                     # Solid / Dashed for Lines
                     line_menu = menu.addMenu("Line Style")
                     def set_ll(s):
                         target.line_style = s
                         target.update()
                         self.main_window.push_undo_state()
                     
                     for s in ["solid", "dashed"]:
                         act = line_menu.addAction(s.capitalize())
                         act.setCheckable(True)
                         act.setChecked(target.line_style == s)
                         def make_cb(ls): return (lambda: set_ll(ls))
                         act.triggered.connect(make_cb(s))
                
                menu.addSeparator()
                
                adv_action = menu.addAction("Advanced Settings")
                def open_adv_settings():
                    from .settings_dialog import AdvancedSettingsDialog
                    dlg = AdvancedSettingsDialog(self.main_window, target)
                    if dlg.exec():
                        # Reload defaults in case they were updated
                        if self.mode_manager:
                            self.mode_manager.load_defaults()
                        target.update()
                        self.main_window.push_undo_state()
                adv_action.triggered.connect(open_adv_settings)

                menu.addSeparator()
                del_action = menu.addAction("Delete")
                del_action.triggered.connect(lambda: self.delete_selection())
                
                menu.exec(event.globalPos())
                return True
            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False
            
        scene_pos = self.main_window.view_2d.mapToScene(event.pos())
        
        # PRIORITY CHECK: If clicking on a Handle (QGraphicsRectItem usually), let standard event processing handle it.
        # Handles usually have ZValue > Items.
        # We need to check if there is a selectable/movable item under cursor that IS a handle or similar control.
        # Actually, simply check if there is an item at pos that accepts mouse clicks?
        # But we want to allow placing atoms *over* bonds etc.
        # The user specifically mentioned "clicking on square" (ReactionHandle).
        items_under = self.main_window.scene.items(scene_pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, self.main_window.view_2d.transform())
        for item in items_under:
            # Check if it is a Handle. ReactionHandle usually has a 'handle_type' or we can check class name?
            # Or just check if it is selected/selectable and we are clicking it?
            # If it's a handle, we should probably return False to let Scene handle it (resizing/moving).
            if hasattr(item, "handle_type") or (isinstance(item, QGraphicsItem) and (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable) and item.isSelected()):
                 # If we clicked a handle, or a SELECTED movable item, prioritizing interaction over drawing.
                 return False

        # If in "select" tool, let it pass to standard Qt selection system
        if self.active_tool == "select" or self.active_tool is None:
            # But satisfy the scene's expectation for positions
            self.main_window.scene.initial_positions_in_event = {
                item: item.pos() for item in self.main_window.scene.items() if hasattr(item, 'pos')
            }
            return False
            
        # ... (rest of the drawing logic) ...
        
        # Helper to select and add
        def add_and_select(new_item):
            # Apply defaults if available (generic arrow props for now)
            if self.mode_manager and hasattr(self.mode_manager, "default_arrow_props"):
                props = self.mode_manager.default_arrow_props
                if props:
                    if hasattr(new_item, "pen_color") and "color" in props:
                        new_item.pen_color = QColor(props["color"])
                    if hasattr(new_item, "pen_width") and "width" in props:
                        new_item.pen_width = int(props["width"])
                    if hasattr(new_item, "head_size") and "head_size" in props:
                        new_item.head_size = float(props["head_size"])
                    if hasattr(new_item, "head_angle") and "head_angle" in props:
                        new_item.head_angle = float(props["head_angle"])
                    if hasattr(new_item, "head_concavity") and "head_concavity" in props:
                        new_item.head_concavity = float(props["head_concavity"])
                    if hasattr(new_item, "curvature") and "curvature" in props:
                        new_item.curvature = float(props["curvature"])
                    
            self.main_window.scene.addItem(new_item)
            self.main_window.scene.clearSelection()
            new_item.setSelected(True)
        
        if self.active_tool == "arrow":
            self.start_pos = scene_pos
            self.preview_item = ReactionArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow", "chevron")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "arrow_res":
            self.start_pos = scene_pos
            self.preview_item = ReactionResonanceArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow_res", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "arrow_eq":
            self.start_pos = scene_pos
            self.preview_item = ReactionEquilibriumArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow_eq", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "arrow_retro":
            self.start_pos = scene_pos
            self.preview_item = ReactionRetroArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow_retro", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "arrow_no":
            self.start_pos = scene_pos
            self.preview_item = ReactionNoArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.negation_style = self.mode_manager.default_no_arrow_style
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow_no", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "curved_double":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("curved_double", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "curved_fish":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(QPointF(0,0), QPointF(0,0), is_fish_hook=True)
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("curved_fish", "triangle")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "bracket":
            self.start_pos = scene_pos
            from .items import ReactionBracketItem
            self.preview_item = ReactionBracketItem(scene_pos, scene_pos)
            self.preview_item.bracket_type = getattr(self.mode_manager, "default_bracket_type", "square")
            self.preview_item.line_style = getattr(self.mode_manager, "default_bracket_line_style", "solid")
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "circle":
            self.start_pos = scene_pos
            from .items import ReactionCircleItem
            self.preview_item = ReactionCircleItem(scene_pos, scene_pos)
            self.preview_item.shape_type = getattr(self.mode_manager, "default_circle_shape_type", "rectangle")
            self.preview_item.line_style = getattr(self.mode_manager, "default_circle_line_style", "solid")
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "plus":
            item = ReactionPlusItem(scene_pos)
            add_and_select(item)
            return True
        elif self.active_tool == "minus":
            item = ReactionMinusItem(scene_pos)
            add_and_select(item)
            return True
        elif self.active_tool == "text":
            item = ReactionTextItem("Text", scene_pos)
            add_and_select(item)
            item.setFocus()
            
            # Select default text so user can overwrite immediately
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            cursor = item.textCursor()
            cursor.select(cursor.SelectionType.Document)
            item.setTextCursor(cursor)
            
            return True
        elif self.active_tool == "arrow_dashed":
            self.start_pos = scene_pos
            from .items import ReactionDashedArrowItem
            self.preview_item = ReactionDashedArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get("arrow", "chevron")
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "line":
            self.start_pos = scene_pos
            from .items import ReactionLineItem
            self.preview_item = ReactionLineItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "line_dashed":
            self.start_pos = scene_pos
            from .items import ReactionLineItem
            self.preview_item = ReactionLineItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.line_style = "dashed"
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "line_curved":
            self.start_pos = scene_pos
            from .items import ReactionCurvedLineItem
            self.preview_item = ReactionCurvedLineItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item)
            return True
        elif self.active_tool == "freehand":
            self.start_pos = scene_pos
            from .items import ReactionFreehandItem
            self.preview_item = ReactionFreehandItem(scene_pos)
            add_and_select(self.preview_item)
            # Special state for freehand
            self._freehand_drawing = True
            return True
            
        return False

    def handle_mouse_move(self, event):
        if self.preview_item:
            scene_pos = self.main_window.view_2d.mapToScene(event.pos())
            
            # Angle Snapping (30 degrees) if not Alt
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.AltModifier):
                if hasattr(self, "start_pos") and self.start_pos:
                    line = QLineF(self.start_pos, scene_pos)
                    if line.length() > 5:
                        angle = line.angle()
                        snapped_angle = round(angle / 15) * 15
                        new_line = QLineF.fromPolar(line.length(), snapped_angle)
                        scene_pos = self.start_pos + new_line.p2()

            if hasattr(self.preview_item, "set_end_pos"):
                self.preview_item.set_end_pos(scene_pos)
                return True
            elif self.active_tool == "freehand" and self.preview_item:
                if getattr(self, "_freehand_drawing", False):
                    self.preview_item.add_point(scene_pos)
                    return True
            elif isinstance(self.preview_item, (ReactionBracketItem, ReactionCircleItem)):
                 self.preview_item.set_rect(self.start_pos, scene_pos)
                 return True

        return False

    def handle_mouse_release(self, event):
        if self.active_tool == "select" or self.active_tool is None:
            return False

        if self.active_tool in ["plus", "minus", "text"]:
            self.main_window.push_undo_state()
            return True
        
        if self.preview_item:
            # Check for short items (prevent accidental single clicks creating tiny arrows)
            should_keep = True
            if self.active_tool not in ["freehand"]: # Freehand might be small dots
                 if hasattr(self, "start_pos") and self.start_pos:
                     scene_pos = self.main_window.view_2d.mapToScene(event.pos())
                     dist = (scene_pos - self.start_pos).manhattanLength()
                     if dist < 10:
                         should_keep = False
            
            if not should_keep:
                self.main_window.scene.removeItem(self.preview_item)
                self.preview_item = None
                self.start_pos = None
                self._freehand_drawing = False
                return True

            self.preview_item = None
            self.start_pos = None
            self._freehand_drawing = False
            self.main_window.push_undo_state()
            return True
            
        return False

    def delete_selection(self):
        selected = self.main_window.scene.selectedItems()
        if not selected:
            return False
        
        # Sanitization: Ensure we have a set of valid items
        targets = set()
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                            ReactionMinusItem, ReactionResonanceArrowItem, 
                            ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                            ReactionNoArrowItem, ReactionCurvedArrowItem,
                            ReactionBracketItem, ReactionCircleItem,
                            ReactionLineItem, ReactionCurvedLineItem,
                            ReactionFreehandItem, ReactionDashedArrowItem)

        for item in selected:
            # Duck typing for reaction items
            if hasattr(item, "create_json_data"):
                targets.add(item)
            elif hasattr(item, 'atom_id') or hasattr(item, 'atom1'): # AtomItem or BondItem
                targets.add(item)
            elif hasattr(item, 'handle_type') and item.parentItem(): # ReactionHandle
                targets.add(item.parentItem())
        
        if not targets:
            return False

        # Use the patched delete_items if available to handle all item types in one undo step
        if hasattr(self.main_window.scene, 'delete_items'):
            # patched_delete_items (in patcher.py) handles the undo push smart logic now
            return self.main_window.scene.delete_items(list(targets))
        else:
            # Fallback manual deletion
            for item in targets:
                self.main_window.scene.removeItem(item)
            self.main_window.push_undo_state()
            return True
        return False

    def handle_key_press(self, event):
        if event.key() == Qt.Key.Key_Space:
            # Match main app logic: 
            # 1. If not in select mode, switch to it.
            # 2. If already in select mode, select all.
            if self.active_tool != "select":
                if self.mode_manager:
                    for action in self.mode_manager.action_group.actions():
                        if action.property("tool_name") == "select":
                            action.setChecked(True)
                            self.set_tool("select")
                            break
            else:
                if hasattr(self.main_window, 'select_all'):
                    self.main_window.select_all()
            return True

        if event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            # Check if focus is on a text editor (ReactionTextItem)
            focus_item = self.main_window.scene.focusItem()
            if focus_item and hasattr(focus_item, "textInteractionFlags"):
                if focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
                    return False
            return self.delete_selection()
                    
        return False

    def handle_mouse_double_click(self, event):
        scene_pos = self.main_window.view_2d.mapToScene(event.pos())
        items = self.main_window.scene.items(scene_pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, self.main_window.view_2d.transform())
        
        # Prioritize Text Edit
        for item in items:
            if isinstance(item, ReactionTextItem):
                # Force focus and edit mode
                item.setFocus()
                item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
                
                # Select all text
                cursor = item.textCursor()
                cursor.select(cursor.SelectionType.Document)
                item.setTextCursor(cursor)
                
                return True
        
        # If no text item, check for Atom/Bond to select whole molecule
        # Reuse logic from main_window? Or implement BFS here.
        # usually main_window has a select_molecule_at(pos) or similar.
        # If not, let's implement simple BFS.
        from unittest.mock import Mock 
        # Actually we need AtomItem/BondItem checks. 
        # But we can't easily import them if they are in main app modules.
        # We can check attributes.
        
        start_atom = None
        for item in items:
            if hasattr(item, "atom_id"): # AtomItem
                 start_atom = item
                 break
            elif hasattr(item, "atom1") and hasattr(item, "atom2"): # BondItem
                 start_atom = item.atom1
                 break
        
        if start_atom:
            # BFS to select connected component
            visited = set()
            stack = [start_atom]
            scene = self.main_window.scene
            
            while stack:
                atom = stack.pop()
                if atom in visited: continue
                visited.add(atom)
                atom.setSelected(True)
                
                for bond in atom.bonds:
                    bond.setSelected(True)
                    other = bond.atom1 if bond.atom2 is atom else bond.atom2
                    if other and other not in visited:
                        stack.append(other)
            return True

        return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtCore import QObject, QEvent, Qt, QPointF, QLineF
from PyQt6.QtWidgets import QGraphicsItem, QApplication
from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                    ReactionMinusItem, ReactionResonanceArrowItem, 
                    ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                    ReactionNoArrowItem, ReactionCurvedArrowItem,
                    ReactionBracketItem, ReactionCircleItem)

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
            # If we select a reaction tool, deselect atoms/bonds/templates in main window
            if hasattr(self.main_window, 'activate_select_mode'):
                self.main_window.activate_select_mode()
        
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
            # Right-click deletion logic
            scene_pos = self.main_window.view_2d.mapToScene(event.pos())
            item = self.main_window.scene.itemAt(scene_pos, self.main_window.view_2d.transform())
            
            if item:
                selected = self.main_window.scene.selectedItems()
                # If clicking outside selection, delete just the item under cursor
                targets = set(selected) if item in selected else {item}
                
                if hasattr(self.main_window.scene, 'delete_items'):
                    if self.main_window.scene.delete_items(targets):
                        self.main_window.push_undo_state()
                        return True
                else:
                    # Fallback
                    for i in targets: self.main_window.scene.removeItem(i)
                    self.main_window.push_undo_state()
                    return True
            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False
            
        scene_pos = self.main_window.view_2d.mapToScene(event.pos())
        
        # If in "select" tool, let it pass to standard Qt selection system
        if self.active_tool == "select" or self.active_tool is None:
            # But satisfy the scene's expectation for positions
            self.main_window.scene.initial_positions_in_event = {
                item: item.pos() for item in self.main_window.scene.items() if hasattr(item, 'pos')
            }
            return False
            
        # ... (rest of the drawing logic) ...
        
        if self.active_tool == "arrow":
            self.start_pos = scene_pos
            self.preview_item = ReactionArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "arrow_res":
            self.start_pos = scene_pos
            self.preview_item = ReactionResonanceArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "arrow_eq":
            self.start_pos = scene_pos
            self.preview_item = ReactionEquilibriumArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "arrow_retro":
            self.start_pos = scene_pos
            self.preview_item = ReactionRetroArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "arrow_no":
            self.start_pos = scene_pos
            self.preview_item = ReactionNoArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "curved_double":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(QPointF(0,0), QPointF(0,0))
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "curved_fish":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(QPointF(0,0), QPointF(0,0), is_fish_hook=True)
            self.preview_item.setPos(self.start_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "bracket":
            self.start_pos = scene_pos
            self.preview_item = ReactionBracketItem(scene_pos, scene_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "circle":
            self.start_pos = scene_pos
            self.preview_item = ReactionCircleItem(scene_pos, scene_pos)
            self.main_window.scene.addItem(self.preview_item)
            return True
        elif self.active_tool == "plus":
            item = ReactionPlusItem(scene_pos)
            self.main_window.scene.addItem(item)
            return True
        elif self.active_tool == "minus":
            item = ReactionMinusItem(scene_pos)
            self.main_window.scene.addItem(item)
            return True
        elif self.active_tool == "text":
            item = ReactionTextItem("Text", scene_pos)
            self.main_window.scene.addItem(item)
            item.setFocus()
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
        return False

    def handle_mouse_release(self, event):
        if self.active_tool == "select" or self.active_tool is None:
            return False

        if self.active_tool in ["plus", "minus", "text"]:
            self.main_window.push_undo_state()
            return True
        
        if self.preview_item:
            self.preview_item = None
            self.start_pos = None
            self.main_window.push_undo_state()
            return True
            
        return False

    def handle_key_press(self, event):
        if event.key() == Qt.Key.Key_Space:
            # Shortcut to Select Tool
            if self.mode_manager:
                for action in self.mode_manager.action_group.actions():
                    if action.property("tool_name") == "select":
                        action.setChecked(True)
                        self.set_tool("select")
                        break
            return True

        if event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            selected = self.main_window.scene.selectedItems()
            if not selected:
                return False
            
            # Sanitization: Ensure we have a set of valid items
            targets = set()
            for item in selected:
                if isinstance(item, (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                                   ReactionMinusItem, ReactionResonanceArrowItem, 
                                   ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                                   ReactionNoArrowItem, ReactionCurvedArrowItem,
                                   ReactionBracketItem, ReactionCircleItem)):
                    targets.add(item)
                elif hasattr(item, 'atom_id') or hasattr(item, 'atom1'): # AtomItem or BondItem
                    targets.add(item)
            
            if not targets:
                return False

            # Use the patched delete_items if available to handle all item types in one undo step
            if hasattr(self.main_window.scene, 'delete_items'):
                if self.main_window.scene.delete_items(targets):
                    self.main_window.push_undo_state()
                    return True
            else:
                # Fallback manual deletion
                for item in targets:
                    self.main_window.scene.removeItem(item)
                self.main_window.push_undo_state()
                return True
                    
        return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtCore import QObject, QEvent, Qt, QPointF
from PyQt6.QtWidgets import QGraphicsItem
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

        # SAFEGUARD: Ensure the scene has this attribute to avoid crash in release event
        # if the press was intercepted by us.
        if not hasattr(self.main_window.scene, 'initial_positions_in_event'):
            self.main_window.scene.initial_positions_in_event = {}

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
        elif self.active_tool == "curved_single":
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
            if hasattr(self.preview_item, "set_end_pos"):
                self.preview_item.set_end_pos(scene_pos)
                return True
        return False

    def handle_mouse_release(self, event):
        if self.active_tool == "select" or self.active_tool is None:
            return False

        if self.preview_item:
            self.preview_item = None
            self.start_pos = None
            return True
        
        # For plus/minus/text tools, the press handled everything, 
        # but we should consume the release too to prevent scene collision.
        if self.active_tool in ["plus", "minus", "text"]:
            return True
            
        return False

    def handle_key_press(self, event):
        if event.key() == Qt.Key.Key_Delete:
            selected = self.main_window.scene.selectedItems()
            reaction_items = [item for item in selected if hasattr(item, "create_json_data")]
            
            if reaction_items:
                for item in reaction_items:
                    self.main_window.scene.removeItem(item)
                if len(reaction_items) == len(selected):
                    return True
                    
        return False

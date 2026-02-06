#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Reaction Sketcher Plugin
Adds 2D reaction drawing tools to MoleditPy.
"""

from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QPointF

from .mode_manager import ModeManager
from .interaction import InteractionHandler
from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem,
                    ReactionMinusItem, ReactionResonanceArrowItem, 
                    ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                    ReactionNoArrowItem, ReactionCurvedArrowItem,
                    ReactionBracketItem, ReactionCircleItem)
from PyQt6.QtGui import QColor, QFont

from functools import partial

PLUGIN_NAME = "Reaction Sketcher"
PLUGIN_VERSION = "0.0.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = "Adds 2D reaction drawing tools (Arrows, Plus, Text) with a dedicated toolbar."

def load_handler_core(main_window, reaction_items):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor
    for item_data in reaction_items:
        item_type = item_data.get("type")
        item = None
        
        if item_type in ["arrow", "arrow_res", "arrow_eq", "arrow_retro", "arrow_no"]:
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            if item_type == "arrow": item = ReactionArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_res": item = ReactionResonanceArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_eq": item = ReactionEquilibriumArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_retro": item = ReactionRetroArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_no": item = ReactionNoArrowItem(QPointF(0, 0), QPointF(dx, dy))
            
            if item:
                item.setPos(item_data["start_x"], item_data["start_y"])
                if "color" in item_data: item.pen_color = QColor(item_data["color"])
                if "width" in item_data: item.pen_width = item_data["width"]
        
        elif item_type in ["curved_double", "curved_fish", "curved_single"]:
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            is_fish = (item_type in ["curved_fish", "curved_single"])
            item = ReactionCurvedArrowItem(QPointF(0,0), QPointF(dx, dy), is_fish_hook=is_fish)
            item.setPos(item_data["start_x"], item_data["start_y"])
            if "cp_x" in item_data and "cp_y" in item_data:
                item.control_p = QPointF(item_data["cp_x"], item_data["cp_y"])
                item.sync_handles()
            if "color" in item_data: item.pen_color = QColor(item_data["color"])
            if "width" in item_data: item.pen_width = item_data["width"]

        elif item_type == "plus":
            item = ReactionPlusItem(QPointF(item_data["x"], item_data["y"]))
            if "color" in item_data: item.pen_color = QColor(item_data["color"])
        elif item_type == "minus":
            item = ReactionMinusItem(QPointF(item_data["x"], item_data["y"]))
            if "color" in item_data: item.pen_color = QColor(item_data["color"])
        
        elif item_type == "bracket":
            item = ReactionBracketItem(QPointF(item_data["x"], item_data["y"]), 
                                     QPointF(item_data["x"] + item_data["w"], item_data["y"] + item_data["h"]))
            if "color" in item_data: item.pen_color = QColor(item_data["color"])
            if "width" in item_data: item.pen_width = item_data["width"]
        
        elif item_type == "circle":
            item = ReactionCircleItem(QPointF(item_data["x"], item_data["y"]), 
                                    QPointF(item_data["x"] + item_data["w"], item_data["y"] + item_data["h"]))
            if "color" in item_data: item.pen_color = QColor(item_data["color"])
            if "width" in item_data: item.pen_width = item_data["width"]

        elif item_type == "text":
            item = ReactionTextItem(item_data["text"], QPointF(item_data["x"], item_data["y"]))
            if "color" in item_data: item.setDefaultTextColor(QColor(item_data["color"]))
            if "font_family" in item_data:
                f = item.font()
                f.setFamily(item_data["font_family"])
                f.setPointSize(item_data.get("font_size", 14))
                f.setBold(item_data.get("bold", False))
                f.setItalic(item_data.get("italic", False))
                item.setFont(f)

        if item:
            main_window.scene.addItem(item)

def initialize(context):
    """Plugin initialization."""
    main_window = context.get_main_window()
    
    # Initialize components
    mode_manager = ModeManager(main_window)
    interaction_handler = InteractionHandler(main_window, mode_manager)
    mode_manager.interaction_handler = interaction_handler
    
    # Setup UI
    mode_manager.setup_toolbar()
    
    # Apply monkey patches to core modules
    from .patcher import apply_patches
    apply_patches(main_window)
    
    # Connect tool actions to interaction handler
    for action in mode_manager.reaction_toolbar.actions():
        tool_name = action.property("tool_name")
        if tool_name and tool_name != "exit":
            # lambda ではなく partial を使用
            action.triggered.connect(partial(interaction_handler.set_tool, tool_name))

    # Install event filter on the 2D view
    main_window.view_2d.viewport().installEventFilter(interaction_handler)
    
    # Register main menu action
    def trigger_sketcher():
        mode_manager.toggle_reaction_mode()
        
    context.add_menu_action(
        path="Extensions",
        callback=trigger_sketcher,
        text="Reaction Sketcher...",
        icon=None,
        shortcut=None
    )

    # Auto-Start Action (Per Project)
    auto_start_action = QAction("Auto-Start Reaction Mode", main_window)
    auto_start_action.setCheckable(True)
    auto_start_action.triggered.connect(mode_manager.set_auto_start)
    
    from PyQt6.QtWidgets import QMenu
    extensions_menu = main_window.menuBar().findChild(QMenu, "Extensions")
    if extensions_menu:
        extensions_menu.addAction(auto_start_action)
    
    # Update action state on project load later
    mode_manager.auto_start_action = auto_start_action 

    # Persistence
    def save_handler():
        items = main_window.scene.items()
        reaction_items = [item.create_json_data() for item in items if hasattr(item, 'create_json_data')]
        
        # Capture chemical structure colors
        acols = {str(aid): d['item'].pen_color.name() for aid, d in main_window.data.atoms.items() if getattr(d['item'], 'pen_color', None)}
        bcols = {f"{k[0]}-{k[1]}": d['item'].pen_color.name() for k, d in main_window.data.bonds.items() if getattr(d['item'], 'pen_color', None)}

        return {
            "items": reaction_items,
            "reaction_mode_active": mode_manager.is_reaction_mode or (len(reaction_items) > 0),
            "auto_start_pref": mode_manager.auto_start_pref,
            "rs_colors": {"atoms": acols, "bonds": bcols}
        }

    def load_handler(data):
        if not data: return
        
        reaction_items = []
        should_enter_mode = False
        
        if isinstance(data, list):
            reaction_items = data
        elif isinstance(data, dict):
            reaction_items = data.get("items", [])
            mode_mgr_auto = data.get("auto_start_pref", False)
            mode_manager.auto_start_pref = mode_mgr_auto
            should_enter_mode = data.get("reaction_mode_active", False) or mode_manager.auto_start_pref
            
            if hasattr(mode_manager, "auto_start_action"):
                mode_manager.auto_start_action.setChecked(mode_manager.auto_start_pref)
            
        load_handler_core(main_window, reaction_items)
        
        # Restore chemical structure colors (Atoms and Bonds)
        rs_cols = data.get("rs_colors", {})
        ac_data = rs_cols.get("atoms", {})
        for aid_str, col in ac_data.items():
            aid = int(aid_str)
            if aid in main_window.data.atoms:
                main_window.data.atoms[aid]['item'].pen_color = QColor(col)
                main_window.data.atoms[aid]['item'].update()
        
        bc_data = rs_cols.get("bonds", {})
        for key, col in bc_data.items():
            try:
                id1_s, id2_s = key.split('-')
                k = (int(id1_s), int(id2_s))
                if k in main_window.data.bonds:
                    main_window.data.bonds[k]['item'].pen_color = QColor(col)
                    main_window.data.bonds[k]['item'].update()
                elif (k[1], k[0]) in main_window.data.bonds:
                    main_window.data.bonds[(k[1], k[0])]['item'].pen_color = QColor(col)
                    main_window.data.bonds[(k[1], k[0])]['item'].update()
            except: pass

        if should_enter_mode and not mode_manager.is_reaction_mode:
            mode_manager.toggle_reaction_mode()

    def reset_handler():
        interaction_handler.active_tool = None
        if mode_manager.is_reaction_mode:
            mode_manager.exit_reaction_mode()
        
        # 【追加】File->New (リセット) 時は、パッチによる保護を無視して強制的にアイテムを消去する
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                            ReactionMinusItem, ReactionResonanceArrowItem, 
                            ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                            ReactionNoArrowItem, ReactionCurvedArrowItem,
                            ReactionBracketItem, ReactionCircleItem)
        
        if main_window and main_window.scene:
            items_to_remove = []
            for item in main_window.scene.items():
                if isinstance(item, (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                                     ReactionMinusItem, ReactionResonanceArrowItem, 
                                     ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                                     ReactionNoArrowItem, ReactionCurvedArrowItem,
                                     ReactionBracketItem, ReactionCircleItem)):
                    items_to_remove.append(item)
            
            for item in items_to_remove:
                main_window.scene.removeItem(item)

    context.register_save_handler(save_handler)
    context.register_load_handler(load_handler)
    context.register_document_reset_handler(reset_handler)

    #print(f"Plugin '{PLUGIN_NAME}' initialized successfully.")

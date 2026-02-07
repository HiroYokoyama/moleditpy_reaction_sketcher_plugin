#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Reaction Sketcher Plugin
# This file is part of MoleditPy Reaction Sketcher Plugin.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

"""
Reaction Sketcher Plugin
Adds 2D reaction drawing tools to MoleditPy.
"""

from functools import partial
from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction, QColor, QFont
from PyQt6.QtCore import QPointF

from .mode_manager import ModeManager
from .interaction import InteractionHandler
from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem,
                    ReactionMinusItem, ReactionResonanceArrowItem, 
                    ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                    ReactionNoArrowItem, ReactionCurvedArrowItem,
                    ReactionBracketItem, ReactionCircleItem,
                    ReactionLineItem, ReactionCurvedLineItem,
                    ReactionFreehandItem, ReactionDashedArrowItem)
from .utils import load_handler_core
from .patcher import apply_patches

PLUGIN_NAME = "Reaction Sketcher"
PLUGIN_VERSION = "0.0.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = "Adds 2D reaction drawing tools (Arrows, Plus, Text) with a dedicated toolbar."

REACTION_ITEM_TYPES = (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                       ReactionMinusItem, ReactionResonanceArrowItem, 
                       ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                       ReactionNoArrowItem, ReactionCurvedArrowItem,
                       ReactionBracketItem, ReactionCircleItem,
                       ReactionLineItem, ReactionCurvedLineItem,
                       ReactionFreehandItem, ReactionDashedArrowItem)

def initialize(context):
    """Plugin initialization."""
    main_window = context.get_main_window()
    
    # Apply ALL patches globally. Interaction patches have internal guards.
    apply_patches(main_window)
    
    # Initialize components
    mode_manager = ModeManager(main_window)
    interaction_handler = InteractionHandler(main_window, mode_manager)
    mode_manager.interaction_handler = interaction_handler
    
    # Setup UI
    mode_manager.setup_toolbar()
    main_window._reaction_mode_manager = mode_manager
    
    # Connect tool actions to interaction handler
    for action in mode_manager.reaction_toolbar.actions():
        tool_name = action.property("tool_name")
        if tool_name and tool_name != "exit":
            # Use partial instead of lambda
            action.triggered.connect(partial(interaction_handler.set_tool, tool_name))

    # Install event filter on the 2D view
    main_window.view_2d.viewport().installEventFilter(interaction_handler)
    main_window.view_2d.installEventFilter(interaction_handler)
    
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
        
        # Force removal of items during File->New (Reset)
        if main_window and main_window.scene:
            items_to_remove = [item for item in main_window.scene.items() 
                               if isinstance(item, REACTION_ITEM_TYPES)]
            for item in items_to_remove:
                main_window.scene.removeItem(item)

    context.register_save_handler(save_handler)
    context.register_load_handler(load_handler)
    context.register_document_reset_handler(reset_handler)



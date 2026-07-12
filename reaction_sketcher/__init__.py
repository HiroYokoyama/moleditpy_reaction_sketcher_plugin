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

"""
Reaction Sketcher Plugin
Adds 2D reaction drawing tools to MoleditPy.
Refactored for MoleditPy V4.0 API.
"""

from functools import partial
from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction, QColor

from .mode_manager import ModeManager
from .interaction import InteractionHandler
from .items import (
    ReactionArrowItem,
    ReactionPlusItem,
    ReactionTextItem,
    ReactionMinusItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionNoArrowItem,
    ReactionCurvedArrowItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionLineItem,
    ReactionCurvedLineItem,
    ReactionFreehandItem,
    ReactionDashedArrowItem,
)
from .utils import load_handler_core
import logging

PLUGIN_NAME = "Reaction Sketcher"
PLUGIN_VERSION = "3.3.1"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Adds 2D reaction drawing tools (Arrows, Plus, Text) with a dedicated toolbar."
)
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=4.0.0, <5.0.0"

REACTION_ITEM_TYPES = (
    ReactionArrowItem,
    ReactionPlusItem,
    ReactionTextItem,
    ReactionMinusItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionNoArrowItem,
    ReactionCurvedArrowItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionLineItem,
    ReactionCurvedLineItem,
    ReactionFreehandItem,
    ReactionDashedArrowItem,
)


def initialize(context):
    """
    Entry Point for MoleditPy V3.0 Plugin System.
    """
    main_window = context.get_main_window()

    # Main window initialization
    # (Patches are now only applied when entering reaction mode)

    # Initialize components with context awareness
    mode_manager = ModeManager(main_window, context)
    interaction_handler = InteractionHandler(context, main_window, mode_manager)
    mode_manager.interaction_handler = interaction_handler

    # Setup UI via V3-aware methods
    mode_manager.setup_toolbar()
    # Store reference on main_window for patched access (avoiding core change)
    main_window._reaction_mode_manager = mode_manager

    # Connect tool actions to interaction handler
    for action in mode_manager.reaction_toolbar.actions():
        tool_name = action.property("tool_name")
        if tool_name and tool_name != "exit":
            action.triggered.connect(partial(interaction_handler.set_tool, tool_name))

    # Install event filter on the 2D view
    if (
        hasattr(main_window.init_manager, "view_2d")
        and main_window.init_manager.view_2d
    ):
        main_window.init_manager.view_2d.viewport().installEventFilter(
            interaction_handler
        )
        main_window.init_manager.view_2d.installEventFilter(interaction_handler)

    # Register main menu action via V3 context
    def trigger_sketcher():
        mode_manager.toggle_reaction_mode()

    context.add_menu_action(
        path="Extensions/Reaction Sketcher...", callback=trigger_sketcher
    )

    # Auto-Start Action (Per Project)
    auto_start_action = QAction("Auto-Start Reaction Mode", main_window)
    auto_start_action.setCheckable(True)
    auto_start_action.triggered.connect(mode_manager.set_auto_start)

    # Note: Using direct menu lookup to maintain "Extensions" grouping if possible
    extensions_menu = main_window.menuBar().findChild(QMenu, "Extensions")
    if extensions_menu:
        extensions_menu.addAction(auto_start_action)

    mode_manager.auto_start_action = auto_start_action

    # --- Persistence Handlers (V3 Standard) ---

    def save_handler():
        items = context.scene.items() if context.scene else []
        reaction_items = [
            item.create_json_data()
            for item in items
            if hasattr(item, "create_json_data")
        ]

        # Access molecular data via namespaced manager if available
        state_mgr = getattr(main_window, "state_manager", None)
        data = state_mgr.data if state_mgr else getattr(main_window, "data", None)

        acols = {}
        bcols = {}
        agroups = {}
        bgroups = {}

        if data and context.scene:
            for aid, d in data.atoms.items():
                item = context.scene.atom_items.get(aid)
                color = getattr(item, "pen_color", None)
                if color:
                    acols[str(aid)] = color.name()

            for k, d in data.bonds.items():
                item = context.scene.bond_items.get(k)
                color = getattr(item, "pen_color", None)
                if color:
                    bcols[f"{k[0]}-{k[1]}"] = color.name()

            for aid, d in data.atoms.items():
                item = context.scene.atom_items.get(aid)
                group_id = getattr(item, "group_id", None)
                if group_id is not None:
                    agroups[str(aid)] = group_id

            for k, d in data.bonds.items():
                item = context.scene.bond_items.get(k)
                group_id = getattr(item, "group_id", None)
                if group_id is not None:
                    bgroups[f"{k[0]}-{k[1]}"] = group_id

        return {
            "plugin_version": PLUGIN_VERSION,
            "items": reaction_items,
            "reaction_mode_active": mode_manager.is_reaction_mode
            or (len(reaction_items) > 0),
            "auto_start_pref": mode_manager.auto_start_pref,
            "rs_colors": {"atoms": acols, "bonds": bcols},
            "groups": {"atoms": agroups, "bonds": bgroups},
        }

    def load_handler(data):
        if not data:
            return

        reaction_items = data.get("items", []) if isinstance(data, dict) else data
        should_enter_mode = False

        if isinstance(data, dict):
            mode_manager.auto_start_pref = data.get("auto_start_pref", False)
            should_enter_mode = (
                data.get("reaction_mode_active", False)
                or mode_manager.auto_start_pref
                or (len(reaction_items) > 0)
            )
            if hasattr(mode_manager, "auto_start_action"):
                mode_manager.auto_start_action.setChecked(mode_manager.auto_start_pref)

        load_handler_core(main_window, reaction_items)

        # Restore molecular properties (colors and groups)
        state_mgr = getattr(main_window, "state_manager", None)
        mol_data = state_mgr.data if state_mgr else getattr(main_window, "data", None)

        if isinstance(data, dict) and mol_data and context.scene:
            rs_cols = data.get("rs_colors", {})
            ac_data = rs_cols.get("atoms", {})
            for aid_str, col in ac_data.items():
                aid = int(aid_str)
                item = context.scene.atom_items.get(aid)
                if item:
                    item.pen_color = QColor(col)
                    item.update()

            bc_data = rs_cols.get("bonds", {})
            for key, col in bc_data.items():
                try:
                    id1_s, id2_s = key.split("-")
                    k = (int(id1_s), int(id2_s))
                    item = context.scene.bond_items.get(k)
                    if item:
                        item.pen_color = QColor(col)
                        item.update()
                except (ValueError, KeyError) as _e:
                    logging.warning("silenced: %s", _e)

            groups = data.get("groups", {})
            ag_data = groups.get("atoms", {})
            for aid_str, gid in ag_data.items():
                aid = int(aid_str)
                item = context.scene.atom_items.get(aid)
                if item:
                    item.group_id = gid

            bg_data = groups.get("bonds", {})
            for key, gid in bg_data.items():
                try:
                    id1_s, id2_s = key.split("-")
                    k = (int(id1_s), int(id2_s))
                    item = context.scene.bond_items.get(k)
                    if item:
                        item.group_id = gid
                except (ValueError, KeyError) as _e:
                    logging.warning("silenced: %s", _e)

        if should_enter_mode and not mode_manager.is_reaction_mode:
            mode_manager.toggle_reaction_mode()

    def reset_handler():
        """Reset state for new project."""
        interaction_handler.active_tool = None
        if mode_manager.is_reaction_mode:
            mode_manager.exit_reaction_mode()

        if context.scene:
            items_to_remove = [
                item
                for item in context.scene.items()
                if isinstance(item, REACTION_ITEM_TYPES)
            ]
            for item in items_to_remove:
                context.scene.removeItem(item)

    # Register V3 lifecycle handlers
    context.register_save_handler(save_handler)
    context.register_load_handler(load_handler)
    context.register_document_reset_handler(reset_handler)

    context.show_status_message(f"{PLUGIN_NAME} v{PLUGIN_VERSION} initialized.")

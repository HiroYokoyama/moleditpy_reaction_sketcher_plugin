#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt6.QtCore import QObject, QEvent, Qt, QPointF, QLineF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem, QApplication
from .items import (
    ReactionArrowItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionCurvedArrowItem,
    ReactionTextItem,
    ReactionPlusItem,
    ReactionMinusItem,
    ReactionNoArrowItem,
    ReactionDashedArrowItem,
    ReactionLineItem,
    ReactionCurvedLineItem,
    ReactionFreehandItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionGroupOverlay,
)
from .utils import sip_isdeleted_safe
import logging


class InteractionHandler(QObject):
    def __init__(self, context, main_window, mode_manager):
        super().__init__()
        self.context = context
        self.main_window = main_window
        self.mode_manager = mode_manager
        self.active_tool = None  # "arrow", "plus", "text"
        self.preview_item = None
        self.start_pos = None
        self.group_overlay = None

        # Drag State
        self._is_dragging = False
        self._drag_start_pos = None
        self._drag_items = []
        self._drag_initial_positions = {}  # For tracking movement delta
        self._drag_original_positions = {}  # For restoring originals on Ctrl+Drag clone
        self._did_move = False
        self._has_cloned = False  # Track if we already cloned during this drag

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        if tool_name and tool_name != "select":
            # Set a flag to avoid infinite loops when we programmatically change main mode
            self._internal_mode_change = True
            try:
                # In V3, activate_select_mode is on ui_manager
                ui_mgr = getattr(self.main_window, "ui_manager", self.main_window)
                if hasattr(ui_mgr, "activate_select_mode"):
                    ui_mgr.activate_select_mode()
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
            scene_mode = getattr(self.main_window.scene, "mode", "select")
        except (RuntimeError, AttributeError):
            # Scene or main window was deleted during teardown
            return False

        # ALLOW Space key even in non-select mode so we can catch it to switch modes.
        if scene_mode != "select" and scene_mode != "bond_2_5":
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
                # Let it pass through to handle_key_press below
                pass
            else:
                return False

        # SAFEGUARD: Ensure the scene has this attribute to avoid crash in release event
        # if the press was intercepted by us.
        try:
            if not hasattr(self.main_window.scene, "initial_positions_in_event"):
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
        elif event.type() == QEvent.Type.MouseButtonDblClick:
            return self.handle_mouse_double_click(event)

        return False

    def handle_mouse_press(self, event):
        # Safeguard: If main window is in a placement/edit mode (atom, bond, template),
        # stay out of the way so the main app can handle bond creation/atom placement.
        try:
            if not self.main_window or not self.main_window.scene:
                return False
            scene_mode = getattr(self.main_window.scene, "mode", "select")
            if scene_mode != "select" and scene_mode != "bond_2_5":
                return False
        except (RuntimeError, AttributeError):
            return False

        scene_pos = self.main_window.init_manager.view_2d.mapToScene(event.pos())

        # Check if we are interacting with a text item currently being edited
        focus_item = self.main_window.scene.focusItem()
        if focus_item and hasattr(focus_item, "textInteractionFlags"):
            if (
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                # Check if click is inside the item
                if focus_item.contains(focus_item.mapFromScene(scene_pos)):
                    return (
                        False  # Pass through to text item for cursor moving/selection
                    )
                else:
                    # Click is outside the text item - exit edit mode
                    focus_item.clearFocus()
                    # Continue processing the click on other items

        if event.button() == Qt.MouseButton.RightButton:
            # Context Menu (Shift+Right) or Delete (Right)
            item = self.main_window.scene.itemAt(
                scene_pos, self.main_window.init_manager.view_2d.transform()
            )

            if item:
                # Check for Shift
                modifiers = QApplication.keyboardModifiers()
                if not (modifiers.value & Qt.KeyboardModifier.ShiftModifier.value):
                    # Just Delete
                    if hasattr(item, "create_json_data") or hasattr(
                        item, "handle_type"
                    ):
                        target = item
                        if hasattr(item, "handle_type") and item.parentItem():
                            target = item.parentItem()

                        # Use patched delete if available
                        if hasattr(self.main_window.scene, "delete_items"):
                            self.main_window.scene.delete_items([target])
                        else:
                            self.main_window.scene.removeItem(target)
                        self.context.push_undo_checkpoint()
                        return True
                    return False

                # Proceed with Context Menu (Shift held)
                if not hasattr(item, "create_json_data") and not (
                    hasattr(item, "handle_type") and item.parentItem()
                ):
                    return False

                # Make sure item is selected
                if not item.isSelected():
                    self.main_window.scene.clearSelection()
                    item.setSelected(True)

                self.mode_manager.show_tool_context_menu(
                    None, "active_item", event.globalPos()
                )
                return True
            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False

        items_under = self.main_window.scene.items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            self.main_window.init_manager.view_2d.transform(),
        )

        # Check for Handles first (Resize/Reshape)
        for item in items_under:
            if sip_isdeleted_safe(item):
                continue
            if hasattr(item, "handle_type"):
                # Pass to standard handler for handles, but ensure we are in select tool
                if self.active_tool != "select":
                    self.mode_manager.activate_tool_by_name("select")
                return False

        # If in "select" tool, implement Custom Drag (Clone / Constrain)
        if self.active_tool == "select" or self.active_tool is None:
            # Check if we are interacting with a text item currently being edited
            try:
                focus_item = self.main_window.scene.focusItem()
                if focus_item and hasattr(focus_item, "textInteractionFlags"):
                    if (
                        focus_item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    ):
                        return False
            except Exception as _e:
                logging.warning("silenced: %s", _e)

            # Check for clickable items
            top_item = None

            # Filter for our items or Atoms/Bonds
            for i in items_under:
                if sip_isdeleted_safe(i):
                    continue
                if (
                    hasattr(i, "create_json_data")
                    or hasattr(i, "atom_id")
                    or hasattr(i, "atom1")
                ):
                    top_item = i
                    break

            if top_item:
                pass

                # Manual Drag Initiation
                self._is_dragging = True
                self._drag_start_pos = scene_pos
                self._did_move = False
                self._drag_start_item_was_selected = top_item.isSelected()

                # Identify Target Group
                # If selection is empty or top_item not in selection, select it (and its group)
                modifiers = QApplication.keyboardModifiers()
                is_shift = modifiers.value & Qt.KeyboardModifier.ShiftModifier.value
                is_ctrl = modifiers.value & Qt.KeyboardModifier.ControlModifier.value

                if not top_item.isSelected():
                    # Item not selected - add to selection (with Shift/Ctrl) or replace selection
                    if not (is_shift or is_ctrl):
                        self.main_window.scene.clearSelection()

                    # Group Selection Logic (Simplified)
                    group_items = [top_item]
                    if hasattr(top_item, "group_id") and top_item.group_id:
                        gid = top_item.group_id
                        group_items = [
                            x
                            for x in self.main_window.scene.items()
                            if not sip_isdeleted_safe(x)
                            and hasattr(x, "group_id")
                            and x.group_id == gid
                        ]

                    for g in group_items:
                        g.setSelected(True)
                # else: Item is already selected - proceed to drag (no toggle on drag start)

                # Get all movable selected items
                selected_items = [
                    i
                    for i in self.main_window.scene.selectedItems()
                    if not sip_isdeleted_safe(i)
                ]
                movable_items = [
                    i
                    for i in selected_items
                    if (i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                    or hasattr(i, "atom_id")
                    or hasattr(i, "atom1")
                ]

                # Store original positions for potential Ctrl+Drag clone during move
                self._drag_items = movable_items
                self._drag_initial_positions = {i: i.pos() for i in movable_items}
                self._drag_original_positions = {
                    i: i.pos() for i in movable_items
                }  # For clone restore
                self._has_cloned = False

                # Store initial modifier state for immediate action on first move
                self._drag_start_with_ctrl = is_ctrl
                self._drag_start_with_shift = is_shift

                return True  # We handle the drag

            # If clicking background
            if not items_under:
                # Clear any text edit mode first
                focus_item = self.main_window.scene.focusItem()
                if focus_item:
                    focus_item.clearFocus()

                self.clear_group_overlay()
                self.main_window.scene.clearSelection()
                self.main_window.scene.setFocusItem(None)
                # Pass through for rubberband
                return False

            return False

        # DRAWING TOOLS (Arrow, etc.)
        # ... (Same as before) ...
        # Helper to select and add
        def add_and_select(new_item, item_type="general"):
            # Apply defaults if available
            if self.mode_manager and hasattr(self.mode_manager, "default_props"):
                props = self.mode_manager.default_props.get(item_type, {})
                if props:
                    if hasattr(new_item, "pen_color") and "color" in props:
                        new_item.pen_color = QColor(props["color"])
                    if hasattr(new_item, "pen_width") and "width" in props:
                        new_item.pen_width = int(props["width"])
                    if hasattr(new_item, "head_size") and "head_size" in props:
                        new_item.head_size = float(props["head_size"])
                    if hasattr(new_item, "head_angle") and "head_angle" in props:
                        new_item.head_angle = float(props["head_angle"])
                    if (
                        hasattr(new_item, "head_concavity")
                        and "head_concavity" in props
                    ):
                        new_item.head_concavity = float(props["head_concavity"])
                    if hasattr(new_item, "curvature") and "curvature" in props:
                        new_item.curvature = float(props["curvature"])
                    if (
                        hasattr(new_item, "double_arrow_offset")
                        and "double_arrow_offset" in props
                    ):
                        new_item.double_arrow_offset = float(
                            props["double_arrow_offset"]
                        )
                    if hasattr(new_item, "line_style") and "line_style" in props:
                        new_item.line_style = props["line_style"]
                    if hasattr(new_item, "cross_size") and "cross_size" in props:
                        new_item.cross_size = float(props["cross_size"])

            self.main_window.scene.addItem(new_item)
            self.main_window.scene.clearSelection()
            new_item.setSelected(True)

        if self.active_tool == "arrow":
            self.start_pos = scene_pos
            self.preview_item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "arrow")
            return True
        elif self.active_tool == "arrow_res":
            self.start_pos = scene_pos
            self.preview_item = ReactionResonanceArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow_res", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "arrow_res")
            return True
        elif self.active_tool == "arrow_eq":
            self.start_pos = scene_pos
            self.preview_item = ReactionEquilibriumArrowItem(scene_pos, scene_pos)
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow_eq", "harpoon"
            )
            self.preview_item.double_arrow_offset = getattr(
                self.mode_manager, "default_double_arrow_offset", 4.0
            )
            add_and_select(self.preview_item, "arrow_eq")
            return True
        elif self.active_tool == "arrow_retro":
            self.start_pos = scene_pos
            self.preview_item = ReactionRetroArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow_retro", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "arrow_retro")
            return True
        elif self.active_tool == "arrow_no":
            self.start_pos = scene_pos
            self.preview_item = ReactionNoArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.negation_style = self.mode_manager.default_no_arrow_style
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow_no", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "arrow_no")
            return True
        elif self.active_tool == "curved_double":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "curved_double", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "curved_double")
            return True
        elif self.active_tool == "curved_fish":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedArrowItem(
                QPointF(0, 0), QPointF(0, 0), is_fish_hook=True
            )
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "curved_fish", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "curved_fish")
            return True
        elif self.active_tool == "bracket":
            self.start_pos = scene_pos
            self.preview_item = ReactionBracketItem(scene_pos, scene_pos)
            self.preview_item.bracket_type = getattr(
                self.mode_manager, "default_bracket_type", "square"
            )
            self.preview_item.line_style = getattr(
                self.mode_manager, "default_bracket_line_style", "solid"
            )
            add_and_select(self.preview_item, "bracket")
            return True
        elif self.active_tool == "circle":
            self.start_pos = scene_pos
            self.preview_item = ReactionCircleItem(scene_pos, scene_pos)
            self.preview_item.shape_type = getattr(
                self.mode_manager, "default_circle_shape_type", "circle"
            )
            self.preview_item.line_style = getattr(
                self.mode_manager, "default_circle_line_style", "solid"
            )
            add_and_select(self.preview_item, "circle")
            return True
        elif self.active_tool == "plus":
            item = ReactionPlusItem(scene_pos)
            add_and_select(item, "plus")
            return True
        elif self.active_tool == "minus":
            item = ReactionMinusItem(scene_pos)
            add_and_select(item, "minus")
            return True
        elif self.active_tool == "text":
            item = ReactionTextItem("Text", scene_pos)
            add_and_select(item, "text")

            # Enable interaction FIRST, then focus, then select
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFocus(Qt.FocusReason.OtherFocusReason)

            cursor = item.textCursor()
            cursor.select(cursor.SelectionType.Document)
            item.setTextCursor(cursor)

            # Mark as an untouched placeholder so that pressing Esc / clicking
            # away without typing anything discards it (instead of leaving a
            # stray "Text" label). Any real content edit clears the flag.
            item._fresh_placeholder = True
            item.document().contentsChanged.connect(
                lambda it=item: setattr(it, "_fresh_placeholder", False)
            )

            return True
        elif self.active_tool == "arrow_dashed":
            self.start_pos = scene_pos
            self.preview_item = ReactionDashedArrowItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.head_style = self.mode_manager.default_head_styles.get(
                "arrow_dashed", "chevron"
            )
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "arrow_dashed")
            return True
        elif self.active_tool == "line":
            self.start_pos = scene_pos
            self.preview_item = ReactionLineItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "line")
            return True
        elif self.active_tool == "line_dashed":
            self.start_pos = scene_pos
            self.preview_item = ReactionLineItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.line_style = "dashed"
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "line_dashed")
            return True
        elif self.active_tool == "line_curved":
            self.start_pos = scene_pos
            self.preview_item = ReactionCurvedLineItem(QPointF(0, 0), QPointF(0, 0))
            self.preview_item.setPos(self.start_pos)
            add_and_select(self.preview_item, "line_curved")
            return True
        elif self.active_tool == "freehand":
            self.start_pos = scene_pos
            self.preview_item = ReactionFreehandItem(scene_pos)
            add_and_select(self.preview_item, "freehand")
            # Special state for freehand
            self._freehand_drawing = True
            return True

        return False

    def handle_mouse_move(self, event):
        # Always allow if we are already in a drag/preview state initiated by us
        if not self._is_dragging and not self.preview_item:
            try:
                scene_mode = getattr(self.main_window.scene, "mode", "select")
                if scene_mode != "select" and scene_mode != "bond_2_5":
                    return False
            except (RuntimeError, AttributeError):
                return False

        scene_pos = self.main_window.init_manager.view_2d.mapToScene(event.pos())

        # Check if we are interacting with a text item currently being edited
        focus_item = self.main_window.scene.focusItem()
        if focus_item and hasattr(focus_item, "textInteractionFlags"):
            if (
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                # Check if hovering inside the item
                if focus_item.contains(focus_item.mapFromScene(scene_pos)):
                    return False  # Pass through to text item selection

        # 1. Handle Dragging (Select Tool)
        if self._is_dragging and self._drag_items:
            delta = scene_pos - self._drag_start_pos

            # Implementation of movement threshold (e.g., 3 pixels) to prevent accidental moves on clicks
            if not self._did_move and delta.manhattanLength() < 3:
                return True  # Swallowing until threshold is met

            modifiers = QApplication.keyboardModifiers()
            # Use either the modifier at start of drag or the current modifier
            active_ctrl = self._drag_start_with_ctrl or (
                modifiers.value & Qt.KeyboardModifier.ControlModifier.value
            )
            active_shift = self._drag_start_with_shift or (
                modifiers.value & Qt.KeyboardModifier.ShiftModifier.value
            )

            # Ctrl+Drag Clone: Clone items once during drag, originals stay in place
            if active_ctrl and not self._has_cloned:
                if self.mode_manager:
                    # Reset originals to their starting positions
                    for item in self._drag_items:
                        if sip_isdeleted_safe(item):
                            continue
                        if item in self._drag_original_positions:
                            item.setPos(self._drag_original_positions[item])

                    # Create clones
                    clones = self.mode_manager.duplicate_items_immediate(
                        self._drag_items
                    )
                    if clones:
                        self.main_window.scene.clearSelection()
                        for c in clones:
                            c.setSelected(True)

                        # Switch to dragging the clones
                        self._drag_items = clones
                        # Clones start at original positions, so use those
                        self._drag_initial_positions = {c: c.pos() for c in clones}
                        self._has_cloned = True

            # Shift = Constrain movement to horizontal or vertical
            if active_shift:
                # Recalculate delta if cloned to ensure constraint works from start
                delta = scene_pos - self._drag_start_pos
                if abs(delta.x()) > abs(delta.y()):
                    delta.setY(0)
                else:
                    delta.setX(0)

            # Apply movement delta to current drag items
            for item in self._drag_items:
                if sip_isdeleted_safe(item):
                    continue
                if item in self._drag_initial_positions:
                    new_pos = self._drag_initial_positions[item] + delta
                    item.setPos(new_pos)
                    self._did_move = True

            # Optimized real-time bond update
            dragged_atoms = [
                i
                for i in self._drag_items
                if hasattr(i, "atom_id") and not sip_isdeleted_safe(i)
            ]
            if dragged_atoms:
                bonds_to_update = set()
                for atom in dragged_atoms:
                    # Collect all connected bonds
                    for bond in getattr(atom, "bonds", []):
                        # Optimization: Only update bonds that are NOT already in the drag items.
                        # Items in self._drag_items have already been moved by the loop above.
                        if bond not in self._drag_items:
                            bonds_to_update.add(bond)

                for bond in bonds_to_update:
                    if not sip_isdeleted_safe(bond) and hasattr(
                        bond, "update_position"
                    ):
                        # Calling update_position() ensures the bond line matches the new atom positions
                        # and calls prepareGeometryChange() to prevent visual artifacts/clipping.
                        bond.update_position()

            # Force full scene repaint to clear ghost artifacts from items with imprecise boundingRects
            self.main_window.scene.update()
            return True

        # 2. Handle drawing Preview (Drawing Tools)
        if self.preview_item:
            # Angle Snapping (15 degrees) if not Alt, ONLY for Straight Lines/Arrows
            modifiers = QApplication.keyboardModifiers()
            should_snap = self.active_tool in [
                "arrow",
                "arrow_eq",
                "arrow_res",
                "arrow_retro",
                "arrow_no",
                "arrow_dashed",
                "line",
                "line_dashed",
            ]

            if should_snap and not (
                modifiers.value & Qt.KeyboardModifier.AltModifier.value
            ):
                if getattr(self, "start_pos", None) is not None and self.start_pos:
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
            elif isinstance(
                self.preview_item, (ReactionBracketItem, ReactionCircleItem)
            ):
                self.preview_item.set_end_pos(scene_pos)
                return True

        return False

    def handle_mouse_release(self, event):
        # Always allow if we are already in a drag/preview state initiated by us
        if not self._is_dragging and not self.preview_item:
            try:
                scene_mode = getattr(self.main_window.scene, "mode", "select")
                if scene_mode != "select" and scene_mode != "bond_2_5":
                    return False
            except (RuntimeError, AttributeError):
                return False

        # 1. End Dragging
        if self._is_dragging:
            # Update bonds if atoms were moved
            if self._did_move and self._drag_items:
                atoms = [
                    i
                    for i in self._drag_items
                    if not sip_isdeleted_safe(i) and hasattr(i, "atom_id")
                ]
                if atoms:
                    # Commit the dragged atom-item positions back into the
                    # molecular data model. The drag loop only moves the QGraphics
                    # items; without writing them back, get_current_state() (and so
                    # the undo snapshot and save file) keeps the pre-drag
                    # coordinates, and any later set_state_from_data
                    # (undo/redo/save-load) snaps the molecule back to where it
                    # was before the move. Mirrors the core scene behaviour.
                    data = getattr(self.main_window, "data", None)
                    if data is not None and hasattr(data, "set_atom_pos"):
                        for atom in atoms:
                            try:
                                data.set_atom_pos(atom.atom_id, atom.pos())
                            except (RuntimeError, KeyError, AttributeError):
                                continue
                    self.main_window.scene.update_connected_bonds(atoms)

            # Capture before resetting below -- the toggle-off logic in the
            # "no move" branch needs to know the modifier state that was
            # active when the drag/click started.
            was_ctrl = self._drag_start_with_ctrl
            was_shift = self._drag_start_with_shift

            self._is_dragging = False
            self._drag_start_pos = None
            self._drag_items = []
            self._drag_initial_positions = {}
            self._drag_original_positions = {}
            self._has_cloned = False
            self._drag_start_with_ctrl = False
            self._drag_start_with_shift = False

            if self._did_move:
                self.context.refresh_2d_scene()
                self.context.push_undo_checkpoint()
                self._did_move = False
            else:
                # No move happened.
                scene_pos = self.main_window.init_manager.view_2d.mapToScene(
                    event.pos()
                )
                item = self.main_window.scene.itemAt(
                    scene_pos, self.main_window.init_manager.view_2d.transform()
                )

                # If Shift/Ctrl was used on an already selected item,
                # we should toggle it OFF now (logic was deferred from mouse_press to allow drag)
                if was_ctrl or was_shift:
                    if item and item.isSelected():
                        # Toggle off this item and its group
                        group_items = [item]
                        if hasattr(item, "group_id") and item.group_id:
                            gid = item.group_id
                            group_items = [
                                x
                                for x in self.main_window.scene.items()
                                if not sip_isdeleted_safe(x)
                                and hasattr(x, "group_id")
                                and x.group_id == gid
                            ]
                        for g in group_items:
                            g.setSelected(False)
                elif (
                    item
                    and item.isSelected()
                    and getattr(item, "is_group_selected", False)
                    and getattr(self, "_drag_start_item_was_selected", False)
                ):
                    # Pure click on a group member, and it was ALREADY selected before the press
                    selected_items = self.main_window.scene.selectedItems()

                    if len(selected_items) > 1:
                        # SECOND CLICK DRILL-DOWN:
                        # Item is already selected as part of a group.
                        # Clicking it again selects ONLY this item and shows handles.
                        self.main_window.scene.clearSelection()
                        item.setSelected(True)
                        # Sync will run, but we set flag AFTER
                        if hasattr(item, "show_handles_in_group"):
                            item.show_handles_in_group = True
                            if hasattr(item, "update_handle_visibility"):
                                item.update_handle_visibility()
                    elif len(selected_items) == 1:
                        # Already single selected, but handle might be hidden. Force it.
                        if hasattr(item, "show_handles_in_group"):
                            item.show_handles_in_group = True
                            if hasattr(item, "update_handle_visibility"):
                                item.update_handle_visibility()

                    item.update()

            return True

        if self.active_tool == "select" or self.active_tool is None:
            return False

        if self.active_tool in ["plus", "minus", "text"]:
            self.context.push_undo_checkpoint()
            return True

        if self.preview_item:
            # Check for short items (prevent accidental single clicks creating tiny arrows)
            should_keep = True
            if self.active_tool not in ["freehand"]:  # Freehand might be small dots
                if getattr(self, "start_pos", None) is not None and self.start_pos:
                    scene_pos = self.main_window.init_manager.view_2d.mapToScene(
                        event.pos()
                    )
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
            self.context.push_undo_checkpoint()
            return True

        return False

    def delete_selection(self):
        selected = [
            i
            for i in self.main_window.scene.selectedItems()
            if not sip_isdeleted_safe(i)
        ]
        if not selected:
            return False

        # Sanitization: Ensure we have a set of valid items
        targets = set()

        for item in selected:
            # Duck typing for reaction items
            if hasattr(item, "create_json_data"):
                targets.add(item)
            elif hasattr(item, "atom_id") or hasattr(
                item, "atom1"
            ):  # AtomItem or BondItem
                targets.add(item)
            elif hasattr(item, "handle_type") and item.parentItem():  # ReactionHandle
                targets.add(item.parentItem())

        if not targets:
            return False

        # Use the patched delete_items if available to handle all item types in one undo step
        if hasattr(self.main_window.scene, "delete_items"):
            # patched_delete_items (in patcher.py) handles the undo push smart logic now
            return self.main_window.scene.delete_items(list(targets))
        else:
            # Fallback manual deletion
            for item in targets:
                self.main_window.scene.removeItem(item)
            self.context.push_undo_checkpoint()
            return True
        return False

    def handle_key_press(self, event):
        # CRITICAL: Check if a ReactionTextItem is being edited
        # If so, let ALL keypresses pass through for text input
        focus_item = self.main_window.scene.focusItem()
        editing_text = bool(
            focus_item
            and hasattr(focus_item, "textInteractionFlags")
            and (
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            )
        )

        # Escape: leave text-edit mode if editing, otherwise deselect any
        # drawn objects (rectangles, arrows, molecules, ...). Handle this
        # before the text passthrough so Esc always gets us out.
        if event.key() == Qt.Key.Key_Escape:
            if editing_text:
                focus_item.clearFocus()
                return True
            if self.main_window.scene.selectedItems():
                self.main_window.scene.clearSelection()
            self.main_window.scene.setFocusItem(None)
            self.clear_group_overlay()
            return True

        if editing_text:
            return False  # Let text item handle ALL keys

        if event.key() == Qt.Key.Key_Space:
            # 1. Check if we need to switch main app or plugin to select mode
            scene_mode = getattr(self.main_window.scene, "mode", "select")
            needs_switch = (scene_mode != "select") or (self.active_tool != "select")

            if needs_switch:
                # Switch main app to select (via ui_manager in V3)
                self._internal_mode_change = True
                try:
                    ui_mgr = getattr(self.main_window, "ui_manager", self.main_window)
                    if hasattr(ui_mgr, "activate_select_mode"):
                        ui_mgr.activate_select_mode()
                finally:
                    self._internal_mode_change = False

                # Switch plugin to select
                if self.mode_manager:
                    self.mode_manager.activate_tool_by_name("select")
            else:
                # 2. If already in select mode (both app and plugin), select all
                # Call select_all (now delegated to EditActions via patcher.py)
                if hasattr(self.main_window, "select_all"):
                    self.main_window.select_all()
                elif hasattr(self.main_window, "edit_actions_manager") and hasattr(
                    self.main_window.edit_actions_manager, "select_all"
                ):
                    self.main_window.edit_actions_manager.select_all()
                elif hasattr(self.main_window, "main_window_edit_actions") and hasattr(
                    self.main_window.main_window_edit_actions, "select_all"
                ):
                    self.main_window.main_window_edit_actions.select_all()
            return True

        if event.key() == Qt.Key.Key_A and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            # Ctrl+A: Select All
            if hasattr(self.main_window, "select_all"):
                self.main_window.select_all()
            elif hasattr(self.main_window, "edit_actions_manager") and hasattr(
                self.main_window.edit_actions_manager, "select_all"
            ):
                self.main_window.edit_actions_manager.select_all()
            elif hasattr(self.main_window, "main_window_edit_actions") and hasattr(
                self.main_window.main_window_edit_actions, "select_all"
            ):
                self.main_window.main_window_edit_actions.select_all()
            return True

        if event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            return self.delete_selection()

        return False

    def handle_mouse_double_click(self, event):
        scene_pos = self.main_window.init_manager.view_2d.mapToScene(event.pos())
        raw_items = self.main_window.scene.items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            self.main_window.init_manager.view_2d.transform(),
        )
        items = [i for i in raw_items if not sip_isdeleted_safe(i)]

        # Prioritize Text Edit
        for item in items:
            if isinstance(item, ReactionTextItem):
                # Exit edit mode on any other text item FIRST
                focus_item = self.main_window.scene.focusItem()
                if focus_item and focus_item != item:
                    if isinstance(focus_item, ReactionTextItem):
                        # Exit edit mode on the previous text item
                        focus_item.setTextInteractionFlags(
                            Qt.TextInteractionFlag.NoTextInteraction
                        )
                        focus_item.setFlag(
                            QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True
                        )
                        focus_item.setSelected(False)
                        # Clear text selection highlight
                        cursor = focus_item.textCursor()
                        cursor.clearSelection()
                        focus_item.setTextCursor(cursor)
                        focus_item.clearFocus()

                # Already editing: let Qt handle it (word-select etc.)
                if (
                    item.textInteractionFlags()
                    & Qt.TextInteractionFlag.TextEditorInteraction
                ):
                    return False

                # Cancel the drag started by the preceding press so the
                # mouse-release handler does not run its drill-down selection
                # and steal focus back out of edit mode (that was why editing
                # text used to take several double-clicks).
                self._is_dragging = False
                self._did_move = False
                self._drag_items = []
                self._drag_initial_positions = {}
                self._drag_original_positions = {}

                # Enter edit mode directly on a single double-click.
                self.main_window.scene.clearSelection()
                item.setSelected(True)
                item.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextEditorInteraction
                    | Qt.TextInteractionFlag.TextSelectableByMouse
                )
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                item.setFocus(Qt.FocusReason.MouseFocusReason)

                # Silence main-window shortcuts while typing.
                if self.mode_manager and hasattr(
                    self.mode_manager, "disable_main_window_shortcuts"
                ):
                    try:
                        self.mode_manager.disable_main_window_shortcuts()
                    except Exception as _e:
                        logging.warning("silenced: %s", _e)

                # Put the caret where the user clicked.
                try:
                    local_pos = item.mapFromScene(scene_pos)
                    cursor_pos = (
                        item.document()
                        .documentLayout()
                        .hitTest(local_pos, Qt.HitTestAccuracy.FuzzyHit)
                    )
                    cursor = item.textCursor()
                    cursor.setPosition(max(0, cursor_pos))
                    item.setTextCursor(cursor)
                except Exception as _e:
                    logging.warning("silenced: %s", _e)

                event.accept()
                return True

        # If no text item, check for Atom/Bond to select whole molecule
        # Reuse logic from main_window? Or implement BFS here.
        # usually main_window has a select_molecule_at(pos) or similar.
        # If not, let's implement simple BFS.
        # Duck typing for AtomItem/BondItem since direct imports are tricky with main app modules.

        start_atom = None
        for item in items:
            if hasattr(item, "atom_id"):  # AtomItem
                start_atom = item
                break
            elif hasattr(item, "atom1") and hasattr(item, "atom2"):  # BondItem
                start_atom = item.atom1
                break

        if start_atom:
            # BFS to select connected component. atom.bonds can contain stale
            # references to deleted BondItems, so guard every hop with
            # sip_isdeleted_safe to avoid "wrapped C/C++ object ... deleted".
            visited = set()
            stack = [start_atom]

            while stack:
                atom = stack.pop()
                if atom in visited or sip_isdeleted_safe(atom):
                    continue
                visited.add(atom)
                atom.setSelected(True)

                for bond in getattr(atom, "bonds", []):
                    if sip_isdeleted_safe(bond):
                        continue
                    bond.setSelected(True)
                    other = bond.atom1 if bond.atom2 is atom else bond.atom2
                    if (
                        other
                        and not sip_isdeleted_safe(other)
                        and other not in visited
                    ):
                        stack.append(other)
            return True

        return False

    def update_group_overlay(self, items):
        self.clear_group_overlay()
        if not items:
            return
        self.group_overlay = ReactionGroupOverlay(items)
        self.main_window.scene.addItem(self.group_overlay)

    def clear_group_overlay(self):
        if self.group_overlay:
            if (
                not sip_isdeleted_safe(self.group_overlay)
                and self.group_overlay.scene()
            ):
                self.main_window.scene.removeItem(self.group_overlay)
            self.group_overlay = None

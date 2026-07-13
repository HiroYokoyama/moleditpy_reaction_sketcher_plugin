#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import copy
from PyQt6.QtGui import (
    QColor,
    QPen,
    QBrush,
    QFont,
    QPainter,
    QImage,
    QAction,
    QKeySequence,
    qRgba,
)
from PyQt6.QtCore import (
    Qt,
    QPointF,
    QByteArray,
    QMimeData,
    QRectF,
    QSize,
    QBuffer,
    QIODevice,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QFileDialog,
    QMessageBox,
    QGraphicsView,
)
import os
import math

try:
    from PyQt6.QtSvg import QSvgGenerator
except ImportError:
    QSvgGenerator = None

from .utils import sip_isdeleted_safe
import logging

# Storage for original methods
_core_originals = {}

# Half-extent of the canvas the sketcher wants (scene spans -SIZE..+SIZE on
# each axis, centred on the origin). Roughly 5x the core app's default area.
_CANVAS_HALF_EXTENT = 20000.0
# Extra margin kept around existing content when the canvas has to grow.
_CANVAS_CONTENT_MARGIN = 4000.0


def _ensure_large_canvas(scene):
    """Give ``scene`` a large, origin-centred rect that also contains its items.

    The core application sets a small, off-centre scene rect which clips large
    reaction schemes. We widen it to a generous centred area and, if the scene
    already holds content that extends further, grow the rect to include it
    (plus a margin) so nothing is ever cut off.
    """
    if not scene or sip_isdeleted_safe(scene):
        return

    rect = QRectF(
        -_CANVAS_HALF_EXTENT,
        -_CANVAS_HALF_EXTENT,
        2 * _CANVAS_HALF_EXTENT,
        2 * _CANVAS_HALF_EXTENT,
    )

    try:
        content = scene.itemsBoundingRect()
    except (RuntimeError, AttributeError):
        content = QRectF()

    if content.isValid() and not content.isNull():
        padded = content.adjusted(
            -_CANVAS_CONTENT_MARGIN,
            -_CANVAS_CONTENT_MARGIN,
            _CANVAS_CONTENT_MARGIN,
            _CANVAS_CONTENT_MARGIN,
        )
        rect = rect.united(padded)

    # Only apply if we are actually growing the canvas, to avoid churn.
    current = scene.sceneRect()
    if not current.contains(rect):
        scene.setSceneRect(rect.united(current))
_interaction_originals = {}

# Mime type for clipboard - fallback if not importable
CLIPBOARD_MIME_TYPE = "application/x-moleditpy-fragment"


def _patch(target_dict, cls, name, new_func):
    """Helper to apply a patch and save original."""
    key = (cls, name)
    if key not in target_dict:
        if hasattr(cls, name):
            target_dict[key] = getattr(cls, name)
        else:
            target_dict[key] = None  # Marker for new method
        setattr(cls, name, new_func)


def _revert(target_dict):
    """Helper to revert patches in a dict."""
    for (cls, name), original in target_dict.items():
        if original is None:
            delattr(cls, name)
        else:
            setattr(cls, name, original)
    target_dict.clear()


def apply_core_patches(main_window, context=None):
    """Applies infrastructure patches (Undo, Delete, IO, Rendering, State) that should be persistent."""
    # Dynamic Class Resolution to handle package path variations (moleditpy vs modules)
    MainWindow = main_window.__class__

    # Resolve MainWindowAppState (V3: state_manager, V2: main_window_app_state._cls)
    # Target StateManager for V3
    MainWindowAppState = None
    if hasattr(main_window, "state_manager"):
        MainWindowAppState = main_window.state_manager.__class__
    elif hasattr(main_window, "main_window_app_state") and hasattr(
        main_window.main_window_app_state, "_cls"
    ):
        MainWindowAppState = main_window.main_window_app_state._cls

    # Resolve MoleculeScene
    MoleculeScene = None
    if hasattr(main_window, "scene") and main_window.scene:
        MoleculeScene = main_window.scene.__class__

    # Resolve MainWindowEditActions (V3: edit_actions_manager, V2: main_window_edit_actions._cls)
    # Target EditActionsManager for V3
    MainWindowEditActions = None
    if hasattr(main_window, "edit_actions_manager"):
        MainWindowEditActions = main_window.edit_actions_manager.__class__
    elif hasattr(main_window, "main_window_edit_actions") and hasattr(
        main_window.main_window_edit_actions, "_cls"
    ):
        MainWindowEditActions = main_window.main_window_edit_actions._cls

    # Resolve ComputeManager (V3: compute_manager)
    ComputeManager = None
    if hasattr(main_window, "compute_manager"):
        ComputeManager = main_window.compute_manager.__class__

    # Resolve ExportManager (V3: export_manager)
    # (ExportManager is resolved below via import)

    # AtomItem is resolved below via sys.modules

    # Resolve View2D
    View2D = None
    if hasattr(main_window, "init_manager") and main_window.init_manager.view_2d:
        View2D = main_window.init_manager.view_2d.__class__

    # If standard imports are needed for other classes or fallback
    import sys

    # Try to resolve classes from ALREADY LOADED modules to avoid double-import mismatches
    AtomItem = None
    BondItem = None
    MainWindowUiManager = None

    # Check sys.modules for hints
    for mod_name in list(sys.modules.keys()):
        if mod_name.endswith("modules.atom_item") or mod_name.endswith("ui.atom_item"):
            try:
                AtomItem = sys.modules[mod_name].AtomItem
            except AttributeError as _e:
                logging.warning("silenced: %s", _e)
        if mod_name.endswith("modules.bond_item") or mod_name.endswith("ui.bond_item"):
            try:
                BondItem = sys.modules[mod_name].BondItem
            except AttributeError as _e:
                logging.warning("silenced: %s", _e)
        if mod_name.endswith("modules.main_window_ui_manager"):
            try:
                MainWindowUiManager = sys.modules[mod_name].MainWindowUiManager
            except AttributeError as _e:
                logging.warning("silenced: %s", _e)
        if mod_name.endswith("ui.ui_manager") and MainWindowUiManager is None:
            try:
                MainWindowUiManager = sys.modules[mod_name].UIManager
            except AttributeError as _e:
                logging.warning("silenced: %s", _e)

    # Fallback to instance inspection if available (Safest)
    if hasattr(main_window, "ui_manager") and MainWindowUiManager is None:
        MainWindowUiManager = main_window.ui_manager.__class__

    if hasattr(main_window, "state_manager"):
        if (
            AtomItem is None
            and hasattr(main_window, "scene")
            and main_window.scene
            and main_window.scene.atom_items
        ):
            AtomItem = next(iter(main_window.scene.atom_items.values())).__class__
        if (
            BondItem is None
            and hasattr(main_window, "scene")
            and main_window.scene
            and main_window.scene.bond_items
        ):
            BondItem = next(iter(main_window.scene.bond_items.values())).__class__

    # Final Fallback to standard imports
    if (
        AtomItem is None
        or BondItem is None
        or MainWindowUiManager is None
        or MainWindowAppState is None
        or MainWindowEditActions is None
    ):
        try:
            from modules.atom_item import AtomItem
            from modules.bond_item import BondItem
            from modules.main_window_ui_manager import MainWindowUiManager

            if MainWindowEditActions is None:
                from modules.main_window_edit_actions import MainWindowEditActions
            if View2D is None:
                from modules.view_2d import View2D
            if MoleculeScene is None:
                from modules.molecule_scene import MoleculeScene
            if MainWindowAppState is None:
                from modules.main_window_app_state import MainWindowAppState
        except ImportError:
            try:
                from moleditpy.ui.atom_item import AtomItem
                from moleditpy.ui.bond_item import BondItem
                from moleditpy.ui.ui_manager import UIManager as MainWindowUiManager

                if MainWindowEditActions is None:
                    from moleditpy.ui.edit_actions_logic import (
                        EditActionsManager as MainWindowEditActions,
                    )
                if View2D is None:
                    from moleditpy.ui.zoomable_view import ZoomableView as View2D
                if MoleculeScene is None:
                    from moleditpy.ui.molecule_scene import MoleculeScene
                if MainWindowAppState is None:
                    from moleditpy.ui.app_state import (
                        StateManager as MainWindowAppState,
                    )
            except ImportError:
                return

    def patch_core(cls, name, func):
        _patch(_core_originals, cls, name, func)

    # --- MainWindowUiManager.set_mode ---
    def patched_set_mode(self, mode_str):
        if (MainWindowUiManager, "set_mode") in _core_originals:
            _core_originals[(MainWindowUiManager, "set_mode")](self, mode_str)

        # Notify Reaction Mode Manager
        rmm = getattr(self.host, "_reaction_mode_manager", None)
        if rmm:
            try:
                rmm._handle_main_mode_change(mode_str)
            except Exception as _e:
                logging.warning("silenced: %s", _e)

    patch_core(MainWindowUiManager, "set_mode", patched_set_mode)

    # --- Connection to Selection Signal ---
    if MoleculeScene:
        # Patch update_template_preview to handle deleted C++ Qt objects gracefully
        orig_update_template_preview = getattr(
            MoleculeScene, "update_template_preview", None
        )
        if orig_update_template_preview:

            def patched_update_template_preview(self, *args, **kwargs):
                from .utils import sip_isdeleted_safe

                if hasattr(self, "atom_items") and self.atom_items:
                    self.atom_items = {
                        k: v
                        for k, v in self.atom_items.items()
                        if not sip_isdeleted_safe(v)
                    }
                if hasattr(self, "bond_items") and self.bond_items:
                    self.bond_items = {
                        k: v
                        for k, v in self.bond_items.items()
                        if not sip_isdeleted_safe(v)
                    }
                try:
                    return orig_update_template_preview(self, *args, **kwargs)
                except RuntimeError as e:
                    if "deleted" in str(e):
                        pass
                    else:
                        raise

            patch_core(
                MoleculeScene,
                "update_template_preview",
                patched_update_template_preview,
            )

        def patched_scene_init(self, *args, **kwargs):
            # Capture the original init if we haven't already
            # Wait, MoleculeScene might already be initialized when we apply patches.
            # Safest to connect it to the ACTIVE scene in apply_core_patches.
            pass

        # Connect to active scene safely
        if hasattr(main_window, "scene") and main_window.scene:
            try:
                rmm = getattr(main_window, "_reaction_mode_manager", None)
                if rmm and hasattr(rmm, "_sync_selection_visuals"):
                    # Disconnect specifically our slot if already connected (to avoid duplicates)
                    try:
                        main_window.scene.selectionChanged.disconnect(
                            rmm._sync_selection_visuals
                        )
                    except (TypeError, RuntimeError) as _e:
                        # TypeError if not connected, RuntimeError if C++ object deleted
                        logging.debug("silenced: %s", _e)

                    # Connect our sync visual slot
                    main_window.scene.selectionChanged.connect(
                        rmm._sync_selection_visuals
                    )
            except (RuntimeError, TypeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

            # Enlarge the drawing canvas. The core app installs a small,
            # off-centre scene rect (-4000,-4000,4000,4000 → only spans
            # -4000..0 on each axis), which clips large reaction schemes and
            # stops the user scrolling/placing items past the origin. Give the
            # sketcher a big, properly-centred canvas and make sure it always
            # contains whatever content is already on the scene.
            try:
                _ensure_large_canvas(main_window.scene)
            except (RuntimeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

    def patched_bond_bounding_rect(self):
        line = self.get_line_in_local_coords()
        bond_offset = 3.5
        wedge_width = 6.0
        settings = None
        try:
            if self.scene() and self.scene().views():
                win = self.scene().views()[0].window()
                if win and hasattr(win, "settings"):
                    settings = win.settings
        except (RuntimeError, AttributeError) as _e:
            logging.warning("silenced: %s", _e)

        if settings:
            if getattr(self, "order", 1) == 3:
                bond_offset = settings.get("bond_spacing_triple_2d", 3.5)
            else:
                bond_offset = settings.get("bond_spacing_double_2d", 3.5)
            wedge_width = settings.get("bond_wedge_width_2d", 6.0)
        extra = (getattr(self, "order", 1) - 1) * bond_offset + 2 + wedge_width
        return (
            QRectF(line.p1(), line.p2())
            .normalized()
            .adjusted(-extra, -extra, extra, extra)
        )

    patch_core(BondItem, "boundingRect", patched_bond_bounding_rect)

    # --- BondItem Init ---
    def patched_bond_item_init(self, atom1, atom2, order=1, stereo=0):
        _core_originals[(BondItem, "__init__")](self, atom1, atom2, order, stereo)
        self.group_id = None
        self.is_group_selected = False

    patch_core(BondItem, "__init__", patched_bond_item_init)

    # --- MainWindow.closeEvent ---
    def patched_close_event(self, event):
        """Override close to ensure all patches are reverted."""
        # 1. Call original close event FIRST while storage is still intact.
        # The core app's closeEvent in main_window_ui_manager.py will handle the unsaved changes prompt.
        orig = _core_originals.get((MainWindow, "closeEvent"))
        result = None
        if orig:
            result = orig(self, event)
        else:
            from PyQt6.QtWidgets import QMainWindow

            result = QMainWindow.closeEvent(self, event)

        # 2. Clean up ALL patches AFTER the core app had a chance to close
        # but ONLY if the event was accepted (meaning the app is actually closing).
        if event.isAccepted():
            revert_all_patches()
        return result

    patch_core(MainWindow, "closeEvent", patched_close_event)

    # --- ItemChange (Shift+Drag Constraint) ---
    # Helper for constraint logic
    def apply_axis_constraint(item, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                scene = item.scene()
                if (
                    scene
                    and hasattr(scene, "initial_positions_in_event")
                    and item in scene.initial_positions_in_event
                ):
                    start_pos = scene.initial_positions_in_event[item]
                    new_pos = value

                    diff = new_pos - start_pos
                    if abs(diff.x()) > abs(diff.y()):
                        # Horizontal movement dominant -> Lock Y
                        return QPointF(new_pos.x(), start_pos.y())
                    else:
                        # Vertical movement dominant -> Lock X
                        return QPointF(start_pos.x(), new_pos.y())
        return value

    # Patch Reaction Items (Arrow, etc) itemChange
    # They might use 'itemChange' for snapping (Arrow). We need to wrap it.
    from .items import (
        ReactionArrowItem,
        ReactionPlusItem,
        ReactionMinusItem,
        ReactionTextItem,
        ReactionBracketItem,
        ReactionCircleItem,
    )

    rxn_classes = [
        ReactionArrowItem,
        ReactionPlusItem,
        ReactionMinusItem,
        ReactionTextItem,
        ReactionBracketItem,
        ReactionCircleItem,
    ]

    for cls in rxn_classes:
        if cls.__name__ == "ReactionTextItem":
            continue

        # Use a closure to capture the original method correctly
        def apply_patch(target_cls):
            # Capture the original from the class
            original_method = target_cls.itemChange

            def patched_rxn_change(self, change, value):
                # 1. Axis Constraint
                constrained_val = apply_axis_constraint(self, change, value)
                # 2. Call original
                return original_method(self, change, constrained_val)

            target_cls.itemChange = patched_rxn_change

        apply_patch(cls)

    # --- Copy Selection ---
    def patched_copy_selection(self):
        try:
            selected_items = [
                i for i in self.host.scene.selectedItems() if not sip_isdeleted_safe(i)
            ]
            selected_atoms = [
                item for item in selected_items if hasattr(item, "atom_id")
            ]
            selected_rs_items_raw = [
                item for item in selected_items if hasattr(item, "create_json_data")
            ]

            if not selected_atoms and not selected_rs_items_raw:
                return

            all_pts = []
            for a in selected_atoms:
                all_pts.append(a.pos())
            for rs in selected_rs_items_raw:
                all_pts.append(rs.sceneBoundingRect().center())

            if not all_pts:
                return
            center = QPointF(
                sum(p.x() for p in all_pts) / len(all_pts),
                sum(p.y() for p in all_pts) / len(all_pts),
            )

            selected_atom_ids = {atom.atom_id for atom in selected_atoms}
            atom_id_to_idx_map = {}
            fragment_atoms = []
            for i, atom in enumerate(selected_atoms):
                atom_id_to_idx_map[atom.atom_id] = i
                fragment_atoms.append(
                    {
                        "symbol": atom.symbol,
                        "rel_pos": atom.pos() - center,
                        "charge": atom.charge,
                        "radical": atom.radical,
                    }
                )
            fragment_bonds = []
            for (id1, id2), bond_data in self.host.state_manager.data.bonds.items():
                if id1 in selected_atom_ids and id2 in selected_atom_ids:
                    fragment_bonds.append(
                        {
                            "idx1": atom_id_to_idx_map[id1],
                            "idx2": atom_id_to_idx_map[id2],
                            "order": bond_data["order"],
                            "stereo": bond_data.get("stereo", 0),
                        }
                    )

            fragment_rs_items = []
            for item in selected_rs_items_raw:
                if hasattr(item, "create_json_data"):
                    d = item.create_json_data()
                    if d["type"] in [
                        "arrow",
                        "arrow_res",
                        "arrow_eq",
                        "arrow_retro",
                        "arrow_no",
                        "curved_fish",
                        "curved_double",
                        "arrow_dashed",
                        "line",
                        "line_curved",
                        "line_dashed",
                    ]:
                        d["start_x"] -= center.x()
                        d["start_y"] -= center.y()
                        d["end_x"] -= center.x()
                        d["end_y"] -= center.y()
                        if "cp_x" in d:
                            d["cp_x"] -= center.x()
                            d["cp_y"] -= center.y()
                    elif d["type"] in [
                        "plus",
                        "minus",
                        "text",
                        "bracket",
                        "circle",
                        "freehand",
                    ]:
                        d["x"] -= center.x()
                        d["y"] -= center.y()
                        if "points" in d:  # Freehand
                            d["points"] = [
                                [p[0] - center.x(), p[1] - center.y()]
                                for p in d["points"]
                            ]
                    fragment_rs_items.append(d)

            import io
            import pickle

            data_to_pickle = {
                "atoms": fragment_atoms,
                "bonds": fragment_bonds,
                "rs_items": fragment_rs_items,
            }
            byte_array = QByteArray()
            buffer = io.BytesIO()
            pickle.dump(data_to_pickle, buffer)
            byte_array.append(buffer.getvalue())

            mime_data = QMimeData()
            mime_data.setData(CLIPBOARD_MIME_TYPE, byte_array)
            QApplication.clipboard().setMimeData(mime_data)
            if context:
                context.show_status_message(
                    f"Copied selection ({len(fragment_atoms)} atoms, {len(fragment_rs_items)} reaction items)."
                )

        except Exception as e:
            if context:
                context.show_status_message(f"Error during patched copy: {e}")

    patch_core(MainWindowEditActions, "copy_selection", patched_copy_selection)

    # --- Paste Selection ---
    def patched_paste_from_clipboard(self):
        try:
            from PyQt6.QtGui import QCursor

            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            if not mime_data or not mime_data.hasFormat(CLIPBOARD_MIME_TYPE):
                return

            import io
            import pickle

            byte_array = mime_data.data(CLIPBOARD_MIME_TYPE)
            buffer = io.BytesIO(byte_array)
            fragment_data = pickle.load(buffer)

            paste_center_pos = self.host.init_manager.view_2d.mapToScene(
                self.host.init_manager.view_2d.mapFromGlobal(QCursor.pos())
            )
            self.host.scene.clearSelection()

            new_atoms = []
            for atom_data in fragment_data.get("atoms", []):
                pos = paste_center_pos + atom_data["rel_pos"]
                new_id = self.host.scene.create_atom(
                    atom_data["symbol"],
                    pos,
                    charge=atom_data.get("charge", 0),
                    radical=atom_data.get("radical", 0),
                )
                item = self.host.scene.atom_items[new_id]
                new_atoms.append(item)
                item.setSelected(True)
            for bond_data in fragment_data.get("bonds", []):
                self.host.scene.create_bond(
                    new_atoms[bond_data["idx1"]],
                    new_atoms[bond_data["idx2"]],
                    bond_order=bond_data.get("order", 1),
                    bond_stereo=bond_data.get("stereo", 0),
                )

            rs_items_data = fragment_data.get("rs_items", [])
            if rs_items_data:
                for d in rs_items_data:
                    if "start_x" in d:
                        d["start_x"] += paste_center_pos.x()
                        d["start_y"] += paste_center_pos.y()
                        d["end_x"] += paste_center_pos.x()
                        d["end_y"] += paste_center_pos.y()
                        if "cp_x" in d:
                            d["cp_x"] += paste_center_pos.x()
                            d["cp_y"] += paste_center_pos.y()
                    elif "x" in d:
                        d["x"] += paste_center_pos.x()
                        d["y"] += paste_center_pos.y()
                        if "points" in d:
                            d["points"] = [
                                [
                                    p[0] + paste_center_pos.x(),
                                    p[1] + paste_center_pos.y(),
                                ]
                                for p in d["points"]
                            ]

                from .utils import load_handler_core

                load_handler_core(self.host, rs_items_data)

            self.push_undo_state()
            if context:
                context.show_status_message("Pasted selection.")
            if hasattr(self.host, "ui_manager"):
                self.host.ui_manager.activate_select_mode()
        except Exception as e:
            if context:
                context.show_status_message(f"Error during patched paste: {e}")

    patch_core(
        MainWindowEditActions, "paste_from_clipboard", patched_paste_from_clipboard
    )

    # --- Allow saving a reaction-only canvas (no atoms / no 3D molecule) ---
    # The core save refuses ("Nothing to save") unless there are atoms or a 3D
    # molecule, which blocks saving a sketch made only of arrows/text/etc. These
    # patches relax that guard to also count reaction items. They are applied
    # from apply_core_patches, i.e. only while the reaction sketcher is active.
    IOManager = None
    if hasattr(main_window, "io_manager"):
        IOManager = main_window.io_manager.__class__

    if IOManager is not None:

        def _has_saveable_content(host):
            if getattr(host.state_manager.data, "atoms", None):
                return True
            if host.view_3d_manager.current_mol is not None:
                return True
            scene = getattr(host, "scene", None)
            if scene is not None:
                for it in scene.items():
                    if hasattr(it, "create_json_data"):
                        return True
            return False

        def patched_save_project(self):
            import json as _json
            import pickle as _pickle

            host = self.host
            if not _has_saveable_content(host):
                host.statusBar().showMessage("Error: Nothing to save.")
                return

            native_exts = (".pmeprj", ".pmeraw")
            cur = host.init_manager.current_file_path
            if cur and cur.lower().endswith(native_exts):
                try:
                    if cur.lower().endswith(".pmeraw"):
                        with open(cur, "wb") as f:
                            _pickle.dump(host.state_manager.get_current_state(), f)
                    else:
                        with open(cur, "w", encoding="utf-8") as f:
                            _json.dump(
                                host.state_manager.create_json_data(),
                                f,
                                indent=2,
                                ensure_ascii=False,
                            )
                    host.set_has_unsaved_changes(False)
                    host.state_manager.update_window_title()
                    host.save_state_snapshot()
                    host.update_status_message(
                        f"Project saved to {host.get_current_file_path()}"
                    )
                except (OSError, IOError) as e:
                    host.update_status_message(f"File I/O error: {e}")
                except (ValueError, TypeError, RuntimeError) as e:
                    host.update_status_message(f"Error saving project: {e}")
            else:
                self.save_project_as()

        def patched_save_project_as(self):
            import json as _json

            host = self.host
            if not _has_saveable_content(host):
                host.statusBar().showMessage("Error: Nothing to save.")
                return

            file_path, _sel = QFileDialog.getSaveFileName(
                host,
                "Save Project As",
                self._get_default_path(),
                "PME Project Files (*.pmeprj);;All Files (*)",
            )
            if not file_path:
                return
            if not file_path.lower().endswith(".pmeprj"):
                file_path += ".pmeprj"
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    _json.dump(
                        host.state_manager.create_json_data(),
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
                host.set_has_unsaved_changes(False)
                host.set_current_file_path(file_path)
                host.update_window_title()
                host.save_state_snapshot()
                host.update_status_message(f"Project saved to {file_path}")
            except (OSError, IOError) as e:
                host.statusBar().showMessage(f"File I/O error: {e}")
            except (ValueError, TypeError, RuntimeError) as e:
                host.statusBar().showMessage(f"Error saving project: {e}")

        patch_core(IOManager, "save_project", patched_save_project)
        patch_core(IOManager, "save_project_as", patched_save_project_as)

    # --- Patch MainWindowEditActions.delete_selection ---
    def patched_delete_selection(self):
        items = self.host.scene.selectedItems()
        if not items:
            return
        # Delegate to patched scene.delete_items which handles separation
        self.host.scene.delete_items(items)

    patch_core(MainWindowEditActions, "delete_selection", patched_delete_selection)

    # --- Select All ---
    def patched_select_all(self):
        scene = self.host.scene
        if not scene:
            return
        # Each setSelected() emits scene.selectionChanged, which drives the
        # (O(n)) group-visual and property-toolbar syncs. Doing that per item
        # makes Select All O(n^2) and janky on large sketches. Block the signal,
        # select everything in one pass, then fire a single selectionChanged so
        # the syncs run exactly once.
        was_blocked = scene.signalsBlocked()
        scene.blockSignals(True)
        try:
            for item in scene.items():
                if sip_isdeleted_safe(item):
                    continue
                if hasattr(item, "create_json_data") or isinstance(
                    item, (AtomItem, BondItem)
                ):
                    item.setSelected(True)
        finally:
            scene.blockSignals(was_blocked)
        if not was_blocked:
            # Blocking signals also suppressed the scene's 'changed' signal, so
            # nudge the view to repaint the new selection highlights, then run
            # the selection syncs once for the whole batch.
            scene.update()
            scene.selectionChanged.emit()

    patch_core(MainWindowEditActions, "select_all", patched_select_all)

    # Delegate to EditActions from MainWindow
    patch_core(
        MainWindow, "select_all", lambda self: self.edit_actions_manager.select_all()
    )
    patch_core(
        MainWindow,
        "delete_selection",
        lambda self: self.edit_actions_manager.delete_selection(),
    )

    def patched_atom_paint(self, painter, option, widget):
        # ALWAYS use patched paint logic to ensure visibility and background handling

        custom_color = getattr(self, "pen_color", None)

        if not self.is_visible:
            # Still draw selection highlight even if atom is central to a bond (skeletal carbon)
            if getattr(self, "has_problem", False):
                painter.save()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 0, 0, 200), 4))
                painter.drawRect(self.boundingRect())
                painter.restore()
            elif self.isSelected():
                painter.save()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                highlight_color = (
                    QColor(130, 100, 255, 120)
                    if getattr(self, "is_group_selected", False)
                    else QColor(0, 120, 255, 120)
                )
                painter.setPen(QPen(highlight_color, 5))
                painter.drawRect(self.boundingRect())
                painter.restore()
            elif getattr(self, "hovered", False):
                painter.save()
                painter.setPen(QPen(QColor(144, 238, 144, 200), 3))
                painter.drawRect(self.boundingRect())
                painter.restore()
            return

        # Logic from original atom_item.py with custom color support
        painter.save()
        try:
            painter.setFont(self.font)
            fm = painter.fontMetrics()

            hydrogen_part = ""
            if (
                getattr(self, "implicit_h_count", None) is not None
                and self.implicit_h_count > 0
            ):
                is_skeletal_carbon = (
                    self.symbol == "C"
                    and self.charge == 0
                    and self.radical == 0
                    and len(self.bonds) > 0
                )
                if not is_skeletal_carbon:
                    hydrogen_part = "H"
                    if self.implicit_h_count > 1:
                        subscript_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
                        hydrogen_part += str(self.implicit_h_count).translate(
                            subscript_map
                        )

            flip_text = False
            if hydrogen_part and self.bonds:
                my_pos_x = self.pos().x()
                total_dx = 0.0
                for bond in self.bonds:
                    try:
                        other_atom = bond.atom1 if bond.atom2 is self else bond.atom2
                        if other_atom:
                            total_dx += other_atom.pos().x() - my_pos_x
                    except (RuntimeError, AttributeError):
                        continue
                if total_dx > 0:
                    flip_text = True

            if flip_text:
                display_text = hydrogen_part + self.symbol
                alignment_flag = (
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                display_text = self.symbol + hydrogen_part
                alignment_flag = (
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )

            text_rect = fm.boundingRect(display_text)
            text_rect.adjust(-2, -2, 2, 2)
            symbol_rect = fm.boundingRect(self.symbol)

            if not hydrogen_part:
                alignment_flag = Qt.AlignmentFlag.AlignCenter
                text_rect.moveCenter(QPointF(0, 0).toPoint())
            elif flip_text:
                offset_x = symbol_rect.width() // 2
                text_rect.moveTo(offset_x - text_rect.width(), -text_rect.height() // 2)
            else:
                offset_x = -symbol_rect.width() // 2
                text_rect.moveTo(offset_x, -text_rect.height() // 2)

            # --- Background Logic ---
            bg_rect = text_rect.adjusted(-5, -8, 5, 8)

            # Check for SVG Export
            is_svg = False
            try:
                # Type 10 is SVG
                if painter.paintEngine() and painter.paintEngine().type() == 10:
                    is_svg = True
                elif (
                    painter.device()
                    and type(painter.device()).__name__ == "QSvgGenerator"
                ):
                    is_svg = True
            except (RuntimeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

            if is_svg:
                # SVG: Use background color from settings to hide bonds (Clear mode fails in SVG)
                bg_color = QColor(255, 255, 255)  # Default white
                try:
                    if self.scene() and self.scene().views():
                        win = self.scene().views()[0].window()
                        if win and hasattr(win, "settings"):
                            bg_color_str = win.settings.get(
                                "background_color_2d", "#FFFFFF"
                            )
                            bg_color = QColor(bg_color_str)
                except (RuntimeError, AttributeError, KeyError) as _e:
                    logging.warning("silenced: %s", _e)
                painter.setBrush(bg_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(bg_rect)
            else:
                # Normal/PNG: Use Clear mode for transparency if background is empty
                bg_brush = (
                    self.scene().backgroundBrush()
                    if self.scene()
                    else QBrush(Qt.BrushStyle.NoBrush)
                )
                if bg_brush.style() == Qt.BrushStyle.NoBrush:
                    painter.save()
                    painter.setCompositionMode(
                        QPainter.CompositionMode.CompositionMode_Clear
                    )
                    painter.setBrush(QColor(0, 0, 0, 255))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(bg_rect)
                    painter.restore()
                else:
                    painter.setBrush(bg_brush)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(bg_rect)

            if getattr(self, "has_problem", False):
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 0, 0, 200), 4))
                painter.drawRect(self.boundingRect())
            elif self.isSelected():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                # Use thinner purple/blue highlight
                highlight_color = (
                    QColor(130, 100, 255, 120)
                    if getattr(self, "is_group_selected", False)
                    else QColor(0, 120, 255, 120)
                )
                painter.setPen(QPen(highlight_color, 5))
                painter.drawRect(self.boundingRect())
            elif getattr(self, "hovered", False):
                painter.setPen(QPen(QColor(144, 238, 144, 200), 3))
                painter.drawRect(self.boundingRect())

            if custom_color:
                painter.setPen(QPen(custom_color))
            else:
                try:
                    from .constants import CPK_COLORS
                except ImportError:
                    try:
                        from moleditpy.utils.constants import CPK_COLORS
                    except ImportError:
                        CPK_COLORS = {
                            "C": "#222222",
                            "O": "red",
                            "N": "blue",
                            "H": "#222222",
                            "S": "#D4A017",
                            "DEFAULT": "#222222",
                        }

                color = QColor(
                    CPK_COLORS.get(self.symbol, CPK_COLORS.get("DEFAULT", "#222222"))
                )

                # Attempt to get bond_color_2d from settings
                bond_col = "#222222"
                try:
                    scene = self.scene()
                    if scene and hasattr(scene, "get_setting"):
                        bond_col = scene.get_setting("bond_color_2d", "#222222")
                    else:
                        if scene and scene.views():
                            win = scene.views()[0].window()
                            if win:
                                if hasattr(win, "get_settings"):
                                    bond_col = win.get_settings().get("bond_color_2d", "#222222")
                                elif hasattr(win, "settings") and hasattr(win.settings, "get"):
                                    bond_col = win.settings.get("bond_color_2d", "#222222")
                except Exception as _e:
                    logging.warning("silenced setting fetch: %s", _e)

                # Standard CPK assigns white (#FFFFFF) to H, which is invisible on a white canvas.
                # Use the resolved bond color for H to ensure visibility and consistency.
                if self.symbol == "H":
                    color = QColor(bond_col)
                else:
                    # For non-H elements, check if we should use bond color
                    use_bond_color = False
                    try:
                        scene = self.scene()
                        if scene and hasattr(scene, "get_setting"):
                            use_bond_color = scene.get_setting("atom_use_bond_color_2d", False)
                        else:
                            if scene and scene.views():
                                win = scene.views()[0].window()
                                if win:
                                    if hasattr(win, "get_settings"):
                                        use_bond_color = win.get_settings().get("atom_use_bond_color_2d", False)
                                    elif hasattr(win, "settings") and hasattr(win.settings, "get"):
                                        use_bond_color = win.settings.get("atom_use_bond_color_2d", False)
                    except Exception as _e:
                        logging.warning("silenced settings fetch for other symbols: %s", _e)
                    if use_bond_color:
                        color = QColor(bond_col)

                if getattr(self, "color", None) is not None and self.color:
                    c = self.color
                    if isinstance(c, QColor):
                        color = c
                    elif isinstance(c, str):
                        color = QColor(c)

                painter.setPen(QPen(color))

            painter.drawText(text_rect, int(alignment_flag), display_text)

            if self.charge != 0:
                c_str = (
                    "+"
                    if self.charge == 1
                    else (
                        "-"
                        if self.charge == -1
                        else f"{abs(self.charge)}{'+' if self.charge > 0 else '-'}"
                    )
                )
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                cfm = painter.fontMetrics()
                cr = cfm.boundingRect(c_str)
                if flip_text:
                    cp = QPointF(
                        text_rect.left() - cr.width(), text_rect.top() + cr.height() - 2
                    )
                else:
                    cp = QPointF(text_rect.right(), text_rect.top() + cr.height() - 2)
                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(cp, c_str)

            if self.radical > 0:
                painter.setBrush(QBrush(Qt.GlobalColor.black))
                painter.setPen(Qt.PenStyle.NoPen)
                ry = text_rect.top() - 5
                if self.radical == 1:
                    painter.drawEllipse(QPointF(text_rect.center().x(), ry), 3, 3)
                elif self.radical == 2:
                    painter.drawEllipse(QPointF(text_rect.center().x() - 5, ry), 3, 3)
                    painter.drawEllipse(QPointF(text_rect.center().x() + 5, ry), 3, 3)
        finally:
            painter.restore()

    patch_core(AtomItem, "paint", patched_atom_paint)

    # --- AtomItem Init ---
    def patched_atom_item_init(self, *args, **kwargs):
        # We might not be able to easily patch __init__ if it's already created,
        # but for NEW atoms, this will work.
        # For existing atoms, we rely on getattr(self, 'is_group_selected', False).
        if (AtomItem, "__init__") in _core_originals:
            _core_originals[(AtomItem, "__init__")](self, *args, **kwargs)
        self.group_id = None
        self.is_group_selected = False

    patch_core(AtomItem, "__init__", patched_atom_item_init)

    def patched_bond_paint(self, painter, option, widget):
        line = self.get_line_in_local_coords()
        if line.length() == 0:
            return

        if getattr(self, "has_problem", False):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(
                QPen(
                    QColor(255, 0, 0, 200),
                    4,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(line)
            painter.restore()
        elif self.isSelected():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Soft thinner purple/blue glow
            highlight_color = (
                QColor(130, 100, 255, 120)
                if getattr(self, "is_group_selected", False)
                else QColor(0, 120, 255, 120)
            )
            painter.setPen(
                QPen(highlight_color, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(line)
            painter.restore()

            # Change state of option so base class doesn't draw default selection (if any)
            # option.state &= ~QStyle.StateFlag.State_Selected

        # Call original or use existing logic
        # Since we want to control everything, let's implement the rest of paint here
        # (or call original if we can access it from _core_originals)
        orig = _core_originals.get((BondItem, "paint"))
        if orig:
            return orig(self, painter, option, widget)

    patch_core(BondItem, "paint", patched_bond_paint)

    # --- Delete Items (Global) ---
    def patched_delete_items(self, items_to_delete):
        core_items = []
        reaction_items = []

        expanded_items = set(items_to_delete)
        for item in items_to_delete:
            if hasattr(item, "handle_type") and item.parentItem():
                expanded_items.add(item.parentItem())

        for item in expanded_items:
            if isinstance(item, (AtomItem, BondItem)):
                core_items.append(item)
            elif hasattr(item, "create_json_data"):
                if item not in reaction_items:
                    reaction_items.append(item)

        deleted_reaction = False
        for item in reaction_items:
            if item.scene() == self:
                if hasattr(item, "childItems"):
                    for child in item.childItems():
                        if (
                            hasattr(child, "handle_type")
                            or child.__class__.__name__ == "ReactionHandle"
                        ):
                            self.removeItem(child)
                self.removeItem(item)
                deleted_reaction = True

        success_core = False
        if core_items:
            success_core = _core_originals[(MoleculeScene, "delete_items")](
                self, core_items
            )

        if deleted_reaction and not success_core:
            views = self.views()
            if views:
                window = views[0].window()
                if hasattr(window, "edit_actions_manager"):
                    window.edit_actions_manager.push_undo_state()
            elif getattr(self, "parent", None) is not None and hasattr(
                self.parent(), "push_undo_state"
            ):
                self.parent().push_undo_state()

        return deleted_reaction or success_core

    patch_core(MoleculeScene, "delete_items", patched_delete_items)

    # --- Rotate Molecule 2D ---
    def patched_rotate_molecule_2d(self, angle_degrees):
        try:
            import math

            selected_items = [
                i for i in self.host.scene.selectedItems() if not sip_isdeleted_safe(i)
            ]

            # Identify targets
            target_atoms = [i for i in selected_items if isinstance(i, AtomItem)]
            target_reaction_items = [
                i for i in selected_items if hasattr(i, "rotate_around")
            ]

            # If nothing selected, rotate everything
            if not target_atoms and not target_reaction_items:
                target_atoms = list(self.host.scene.atom_items.values())
                # Filter out deleted atoms if any
                target_atoms = [a for a in target_atoms if a.scene() is not None]

                # Gather reaction items from scene
                for item in self.host.scene.items():
                    if sip_isdeleted_safe(item):
                        continue
                    if hasattr(item, "rotate_around"):
                        target_reaction_items.append(item)

            if not target_atoms and not target_reaction_items:
                if context:
                    context.show_status_message("No items to rotate.")
                return

            # Calculate Center
            points = []
            for atom in target_atoms:
                points.append(atom.pos())

            for item in target_reaction_items:
                # Prefer scene bounding rect center for calculation
                points.append(item.sceneBoundingRect().center())

            if not points:
                return

            center_x = sum(p.x() for p in points) / len(points)
            center_y = sum(p.y() for p in points) / len(points)
            center = QPointF(center_x, center_y)

            rad = math.radians(angle_degrees)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            # Rotate Atoms. Sync each new position into the data model too;
            # otherwise get_current_state() snapshots the pre-rotation coords
            # and the molecule snaps back on undo/redo/save-reload.
            data_model = getattr(self.host, "data", None)
            can_sync = data_model is not None and hasattr(data_model, "set_atom_pos")
            for atom in target_atoms:
                dx = atom.pos().x() - center_x
                dy = atom.pos().y() - center_y
                # Rotation logic: new_x = x*cos - y*sin
                new_dx = dx * cos_a - dy * sin_a
                new_dy = dx * sin_a + dy * cos_a
                new_pos = QPointF(center_x + new_dx, center_y + new_dy)
                atom.setPos(new_pos)
                if can_sync:
                    try:
                        data_model.set_atom_pos(atom.atom_id, new_pos)
                    except (RuntimeError, KeyError, AttributeError):
                        pass

            # Rotate Reaction Items
            for item in target_reaction_items:
                rotate_func = getattr(item, "rotate_around", None)
                if rotate_func:
                    rotate_func(center, angle_degrees)
                else:
                    logging.warning("Error: item %s missing 'rotate_around'", item)

            # Update bonds
            self.host.scene.update_connected_bonds(target_atoms)

            self.push_undo_state()
            if context:
                context.show_status_message(
                    f"Rotated {len(target_atoms) + len(target_reaction_items)} items by {angle_degrees} degrees."
                )
                context.refresh_2d_scene()

        except Exception as e:
            if context:
                context.show_status_message(f"Error rotating: {e}")

    patch_core(MainWindowEditActions, "rotate_molecule_2d", patched_rotate_molecule_2d)

    # --- MoleculeScene.keyPressEvent ---
    def patched_molecule_scene_key_press_event(self, event):
        # If focus is on a ReactionTextItem in edit mode, and it accepted the event,
        # we skip the standard molecule sketcher shortcuts.
        view = self.views()[0] if self.views() else None
        if view:
            focus_item = self.focusItem()
            from .items import ReactionTextItem

            if isinstance(focus_item, ReactionTextItem) and (
                focus_item.textInteractionFlags()
                & Qt.TextInteractionFlag.TextEditorInteraction
            ):
                # Standard QGraphicsScene logic ensures focusItem receives the key.
                # We skip MoleculeScene's shortcuts but let the base class deliver the event.
                from PyQt6.QtWidgets import QGraphicsScene

                return QGraphicsScene.keyPressEvent(self, event)

        orig = _core_originals.get((MoleculeScene, "keyPressEvent"))
        if orig:
            return orig(self, event)
        from PyQt6.QtWidgets import QGraphicsScene

        return QGraphicsScene.keyPressEvent(self, event)

    patch_core(MoleculeScene, "keyPressEvent", patched_molecule_scene_key_press_event)

    # preservation patches removed per user request: "remove everything when clear"
    # This also resolves the TypeError in clear_2d_editor.

    # --- Clean Up 2D ---
    def patched_clean_up_2d_structure(self):
        # Reaction mode variant: preserve fragment CoG and support partial-selection optimization.
        try:
            from rdkit.Chem import AllChem, rdmolops
        except ImportError:
            if context:
                context.show_status_message(
                    "Error: RDKit is required for structure optimization."
                )
            return

        host = self.host
        scene = getattr(host, "scene", None) or getattr(
            getattr(host, "init_manager", None), "scene", None
        )
        data = getattr(getattr(host, "state_manager", None), "data", None)
        if not data:
            if context:
                context.show_status_message("Error: Missing molecular data.")
            return

        if context:
            context.show_status_message("Optimizing 2D structure (CoG Preserved)...")
        if scene and hasattr(scene, "clear_all_problem_flags"):
            scene.clear_all_problem_flags()
        if not data.atoms:
            if context:
                context.show_status_message("Error: No atoms to optimize.")
            return

        try:
            mol = data.to_rdkit_mol()
            if mol is None or mol.GetNumAtoms() == 0:
                if context:
                    context.check_chemistry_problems()
                return

            frags = rdmolops.GetMolFrags(mol, asMols=False, sanitizeFrags=False)

            def resolve_atom_id(rd_atom, fallback_idx):
                try:
                    if rd_atom.HasProp("_original_atom_id"):
                        return rd_atom.GetIntProp("_original_atom_id")
                except Exception as _e:
                    logging.warning("silenced: %s", _e)
                try:
                    return rd_atom.GetIntProp("atom_id")
                except Exception:
                    return fallback_idx

            def atom_scene_pos(atom_item):
                if hasattr(atom_item, "scenePos"):
                    try:
                        return atom_item.scenePos()
                    except (RuntimeError, AttributeError) as _e:
                        logging.warning("silenced: %s", _e)
                return atom_item.pos()

            def set_atom_scene_pos(atom_item, target_scene_pos):
                parent = (
                    atom_item.parentItem() if hasattr(atom_item, "parentItem") else None
                )
                if parent is not None and hasattr(parent, "mapFromScene"):
                    atom_item.setPos(parent.mapFromScene(target_scene_pos))
                else:
                    atom_item.setPos(target_scene_pos)

            selected_items = scene.selectedItems() if scene else []
            target_atom_ids = set()
            for item in selected_items:
                atom_id = getattr(item, "atom_id", None)
                if isinstance(atom_id, int):
                    target_atom_ids.add(atom_id)
                    continue
                if hasattr(item, "atom1") and hasattr(item, "atom2"):
                    a1 = item.atom1
                    a2 = item.atom2
                    if hasattr(a1, "atom_id") and isinstance(a1.atom_id, int):
                        target_atom_ids.add(a1.atom_id)
                    elif isinstance(a1, int):
                        target_atom_ids.add(a1)
                    if hasattr(a2, "atom_id") and isinstance(a2.atom_id, int):
                        target_atom_ids.add(a2.atom_id)
                    elif isinstance(a2, int):
                        target_atom_ids.add(a2)

            if not target_atom_ids:
                for item in selected_items:
                    atom_id = getattr(item, "atom_id", None)
                    if isinstance(atom_id, int):
                        target_atom_ids.add(atom_id)

            if target_atom_ids:
                target_frag_indices = set()
                for i, frag_indices in enumerate(frags):
                    for idx in frag_indices:
                        rd_atom = mol.GetAtomWithIdx(idx)
                        aid = resolve_atom_id(rd_atom, idx)
                        if aid in target_atom_ids:
                            target_frag_indices.add(i)
                            break
            else:
                target_frag_indices = set(range(len(frags)))

            if not target_frag_indices:
                if context:
                    context.show_status_message(
                        "No valid atoms selected for optimization."
                    )
                return

            orig_cogs = {}
            for i, frag_indices in enumerate(frags):
                if i not in target_frag_indices:
                    continue
                sum_x = 0.0
                sum_y = 0.0
                count = 0
                for idx in frag_indices:
                    rd_atom = mol.GetAtomWithIdx(idx)
                    aid = resolve_atom_id(rd_atom, idx)
                    atom_entry = data.atoms.get(aid, None)
                    atom_item = None
                    if scene and hasattr(scene, "atom_items"):
                        atom_item = scene.atom_items.get(aid, None)
                    if atom_item is None:
                        continue
                    pos = atom_scene_pos(atom_item)
                    sum_x += pos.x()
                    sum_y += pos.y()
                    count += 1
                if count > 0:
                    orig_cogs[i] = QPointF(sum_x / count, sum_y / count)

            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()
            scale = 50.0
            updated_count = 0

            for i, frag_indices in enumerate(frags):
                if i not in target_frag_indices or i not in orig_cogs:
                    continue

                rd_sum_x = 0.0
                rd_sum_y = 0.0
                rd_count = 0
                for idx in frag_indices:
                    rd_pos = conf.GetAtomPosition(idx)
                    rd_sum_x += rd_pos.x
                    rd_sum_y += rd_pos.y
                    rd_count += 1
                if rd_count == 0:
                    continue

                rd_cog_x = rd_sum_x / rd_count
                rd_cog_y = rd_sum_y / rd_count
                scene_cog = orig_cogs[i]

                for idx in frag_indices:
                    rd_atom = mol.GetAtomWithIdx(idx)
                    aid = resolve_atom_id(rd_atom, idx)
                    atom_entry = data.atoms.get(aid, None)
                    atom_item = None
                    if scene and hasattr(scene, "atom_items"):
                        atom_item = scene.atom_items.get(aid, None)
                    if atom_item is None:
                        continue

                    rd_pos = conf.GetAtomPosition(idx)
                    sx = ((rd_pos.x - rd_cog_x) * scale) + scene_cog.x()
                    sy = (-(rd_pos.y - rd_cog_y) * scale) + scene_cog.y()
                    scene_target = QPointF(sx, sy)

                    set_atom_scene_pos(atom_item, scene_target)
                    local_pos = atom_item.pos()
                    if hasattr(data, "set_atom_pos"):
                        data.set_atom_pos(aid, local_pos)
                    else:
                        atom_entry["pos"] = local_pos
                updated_count += 1

            _bond_items_dict = (
                getattr(getattr(host, "init_manager", None), "scene", scene).bond_items
                if scene
                else {}
            )
            for bond_item in _bond_items_dict.values():
                if not bond_item or sip_isdeleted_safe(bond_item):
                    continue
                if not bond_item.scene():
                    continue
                update_pos_func = getattr(bond_item, "update_position", None)
                if update_pos_func:
                    update_pos_func()

            self.resolve_overlapping_groups()

            if scene and hasattr(scene, "update_all_items"):
                scene.update_all_items()

            mgr_3d = getattr(host, "edit_3d_manager", None)
            if mgr_3d:
                update_labels_func = getattr(
                    mgr_3d, "update_2d_measurement_labels", None
                )
                if update_labels_func:
                    update_labels_func()

            if context:
                context.refresh_2d_scene()

            if target_atom_ids:
                if context:
                    context.show_status_message(
                        f"Optimized {updated_count} selected fragment(s)."
                    )
            else:
                if context:
                    context.show_status_message(
                        f"Optimized {updated_count} fragment(s)."
                    )
            host.edit_actions_manager.push_undo_state()

        except Exception as e:
            if context:
                context.show_status_message(f"Error during CoG optimization: {e}")
        finally:
            if hasattr(host, "init_manager") and host.init_manager.view_2d:
                host.init_manager.view_2d.setFocus()

    patch_core(
        MainWindowEditActions, "clean_up_2d_structure", patched_clean_up_2d_structure
    )

    # --- Get/Set State, Push Undo ---
    def patched_get_current_state(self):
        state = _core_originals[(MainWindowAppState, "get_current_state")](self)

        agroups = {}
        bgroups = {}
        if hasattr(self.host, "scene") and self.host.scene:
            agroups = {
                str(aid): getattr(item, "group_id", None)
                for aid, item in self.host.scene.atom_items.items()
                if hasattr(item, "group_id")
            }
            bgroups = {
                f"{k[0]}-{k[1]}": getattr(item, "group_id", None)
                for k, item in self.host.scene.bond_items.items()
                if hasattr(item, "group_id")
            }
        state["rs_atom_groups"] = agroups
        state["rs_bond_groups"] = bgroups

        # Reaction items
        rs_items_data = []
        for item in self.host.scene.items():
            if hasattr(item, "create_json_data"):
                rs_items_data.append(item.create_json_data())

        rs_items_data.sort(
            key=lambda x: (
                x.get("type", ""),
                x.get("x", x.get("start_x", 0)),
                x.get("y", x.get("start_y", 0)),
            )
        )

        state["rs_items"] = rs_items_data
        return state

    patch_core(MainWindowAppState, "get_current_state", patched_get_current_state)

    def patched_set_state_from_data(self, state_data):
        _core_originals[(MainWindowAppState, "set_state_from_data")](self, state_data)

        agroups = state_data.get("rs_atom_groups", {})
        for aid_str, gid in agroups.items():
            aid = int(aid_str) if aid_str.isdigit() else aid_str
            scene = getattr(self.host, "scene", None)
            if scene:
                item = scene.atom_items.get(aid)
                if item:
                    item.group_id = gid

        bgroups = state_data.get("rs_bond_groups", {})
        for key, gid in bgroups.items():
            try:
                id1_str, id2_str = key.split("-")
                id1 = int(id1_str) if id1_str.isdigit() else id1_str
                id2 = int(id2_str) if id2_str.isdigit() else id2_str
                k = (id1, id2)
                scene = getattr(self.host, "scene", None)
                if scene:
                    item = scene.bond_items.get(k)
                    if item:
                        item.group_id = gid
            except (ValueError, AttributeError, KeyError) as _e:
                logging.debug("silenced: %s", _e)
                continue

        for item in list(self.host.scene.items()):
            if hasattr(item, "create_json_data"):
                self.host.scene.removeItem(item)

        if "rs_items" in state_data:
            from .utils import load_handler_core

            load_handler_core(self.host, state_data["rs_items"])

    patch_core(MainWindowAppState, "set_state_from_data", patched_set_state_from_data)

    # --- ComputeManager Patch (Cre Logic) ---
    if ComputeManager:

        def patched_on_calculation_finished(self, result):
            # 1. Call original
            if (ComputeManager, "on_calculation_finished") in _core_originals:
                _core_originals[(ComputeManager, "on_calculation_finished")](
                    self, result
                )

            # 2. Notify Sketcher or Refresh items
            try:
                mm = getattr(main_window, "_reaction_mode_manager", None)
                if mm and hasattr(mm, "interaction_handler"):
                    # Force a refresh of the 2D view to ensure reaction items are drawn correctly
                    # after the molecular change
                    if hasattr(main_window, "scene") and main_window.scene:
                        main_window.scene.update()
            except (RuntimeError, AttributeError) as _e:
                logging.warning("silenced: %s", _e)

        patch_core(
            ComputeManager, "on_calculation_finished", patched_on_calculation_finished
        )

    def patched_push_undo_state(self):
        # Prevent recursion and checks based on both Manager and Host state
        if getattr(self, "_is_restoring_state", False):
            return
        if getattr(self, "host", None) is not None and getattr(
            self.host, "_is_restoring_state", False
        ):
            return

        # Resolve correct StateManager (which has get_current_state and data)
        # In V3, self might be EditActionsManager, which lacks these.
        state_mgr = self
        if (
            getattr(self, "get_current_state", None) is None
            and hasattr(self, "host")
            and hasattr(self.host, "state_manager")
        ):
            state_mgr = self.host.state_manager

        if not hasattr(state_mgr, "get_current_state") or not hasattr(
            state_mgr, "data"
        ):
            return

        curr_state = state_mgr.get_current_state()
        data = state_mgr.data
        host = state_mgr.host

        # NOTE: Atom/bond pen colors are intentionally excluded from this dedup
        # comparison. They are never written into the saved state (no
        # rs_atom_colors/rs_bond_colors keys exist), so comparing live colors
        # against the stored state made every push look "changed" and defeated
        # deduplication — bloating the undo stack with identical snapshots and
        # making Undo require several presses to visibly do anything.
        scene = getattr(host, "scene", None)
        atoms_data = {}
        for k, v in data.atoms.items():
            item = scene.atom_items.get(k) if scene else None
            pos_x = item.pos().x() if item else v["pos"][0]
            pos_y = item.pos().y() if item else v["pos"][1]
            atoms_data[k] = (
                v["symbol"],
                pos_x,
                pos_y,
                v.get("charge", 0),
                v.get("radical", 0),
            )

        bonds_data = {}
        for k, v in data.bonds.items():
            bonds_data[k] = (v["order"], v.get("stereo", 0))

        current_comp = {
            "atoms": atoms_data,
            "bonds": bonds_data,
            "_next_atom_id": data.next_atom_id,
            "mol_3d": host.view_3d_manager.current_mol.ToBinary()
            if host.view_3d_manager.current_mol
            else None,
            "mol_3d_atom_ids": curr_state.get("mol_3d_atom_ids", []),
            "rs_items": curr_state.get("rs_items", []),
            "rs_atom_groups": curr_state.get("rs_atom_groups", {}),
            "rs_bond_groups": curr_state.get("rs_bond_groups", {}),
        }

        last_comp = None
        if self.undo_stack:
            last_state = self.undo_stack[-1]
            last_atoms = last_state.get("atoms", {})
            last_bonds = last_state.get("bonds", {})
            last_agroups = last_state.get("rs_atom_groups", {})
            last_bgroups = last_state.get("rs_bond_groups", {})

            last_comp = {
                "atoms": {
                    k: (
                        v["symbol"],
                        v["pos"][0],
                        v["pos"][1],
                        v.get("charge", 0),
                        v.get("radical", 0),
                    )
                    for k, v in last_atoms.items()
                },
                "bonds": {
                    k: (
                        v["order"],
                        v.get("stereo", 0),
                    )
                    for k, v in last_bonds.items()
                },
                "_next_atom_id": last_state.get("_next_atom_id", None),
                "mol_3d": last_state.get("mol_3d", None),
                "mol_3d_atom_ids": last_state.get("mol_3d_atom_ids", []),
                "rs_items": last_state.get("rs_items", []),
                "rs_atom_groups": last_agroups,
                "rs_bond_groups": last_bgroups,
            }

        if not last_comp or current_comp != last_comp:
            state = copy.deepcopy(curr_state)
            self.undo_stack.append(state)
            self.redo_stack.clear()

            target_obj = host if hasattr(host, "initialization_complete") else state_mgr
            if getattr(target_obj, "initialization_complete", True):
                if context is not None:
                    context.mark_project_modified()
                else:
                    if hasattr(state_mgr, "has_unsaved_changes"):
                        state_mgr.has_unsaved_changes = True
                    elif hasattr(host, "has_unsaved_changes"):
                        host.has_unsaved_changes = True
                    title_func = getattr(state_mgr, "update_window_title", None)
                    if title_func:
                        title_func()

        # 1. Update Implicit Hydrogens (On self if EditActionsManager, or state_mgr in some versions)
        h_func = getattr(self, "update_implicit_hydrogens", None)
        if not h_func:
            h_func = getattr(state_mgr, "update_implicit_hydrogens", None)

        if h_func:
            h_func()
        else:
            logging.warning(
                "Error: missing 'update_implicit_hydrogens' on self and state_manager"
            )

        # 2. Update Realtime Info (On state_manager)
        r_func = getattr(state_mgr, "update_realtime_info", None)
        if r_func:
            r_func()
        else:
            logging.warning("Error: missing 'update_realtime_info' on state_manager")

        # 3. Update Undo Redo Actions (On self if EditActionsManager)
        u_func = getattr(self, "update_undo_redo_actions", None)
        if u_func:
            u_func()
        else:
            logging.warning("Error: missing 'update_undo_redo_actions' on self")

    if MainWindowEditActions:
        patch_core(MainWindowEditActions, "push_undo_state", patched_push_undo_state)
    elif MainWindowAppState:
        patch_core(MainWindowAppState, "push_undo_state", patched_push_undo_state)

    # --- MainWindowExport Patches (PNG/SVG/Clipboard) ---
    try:
        from modules.main_window_export import MainWindowExport
    except ImportError:
        try:
            from moleditpy.ui.export_logic import ExportManager as MainWindowExport
        except ImportError:
            MainWindowExport = None

    if MainWindowExport:

        def _render_2d_to_image(self, is_transparent=True):
            all_visible_items = [i for i in self.host.scene.items() if i.isVisible()]
            molecule_bounds = QRectF()
            for item in all_visible_items:
                if item.__class__.__name__ in [
                    "ReactionHandle",
                    "ReactionGroupOverlay",
                    "SelectionRect",
                    "GuideLine",
                ]:
                    continue
                if hasattr(item, "handle_type"):
                    continue

                item_bounds = item.sceneBoundingRect()
                molecule_bounds = molecule_bounds.united(item_bounds)

            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                return None, None

            padding = 5
            rect_to_render = molecule_bounds.adjusted(
                -padding, -padding, padding, padding
            )

            w = max(1, int(math.ceil(rect_to_render.width())))
            h = max(1, int(math.ceil(rect_to_render.height())))

            # Use ARGB32 for proper alpha channel support
            image = QImage(w, h, QImage.Format.Format_ARGB32)
            if image.isNull():
                return None, None

            # Fill with truly transparent using qRgba
            if is_transparent:
                image.fill(
                    qRgba(255, 255, 255, 0)
                )  # Transparent White (helps avoid black halos)
            else:
                image.fill(Qt.GlobalColor.white)

            original_background = self.host.scene.backgroundBrush()
            if is_transparent:
                # Set truly transparent WHITE background (255,255,255,0) as requested by user.
                # The patched_atom_paint will detect alpha=0 and trigger the eraser logic.
                self.host.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))

            # Clear selection and focus to avoid highlights/cursors in export
            selected_items = self.host.scene.selectedItems()
            self.host.scene.clearSelection()
            original_focus = self.host.scene.focusItem()
            self.host.scene.setFocusItem(None)

            painter = QPainter()
            if painter.begin(image):
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    if is_transparent:
                        painter.setCompositionMode(
                            QPainter.CompositionMode.CompositionMode_SourceOver
                        )
                    self.host.scene.render(painter, QRectF(0, 0, w, h), rect_to_render)
                finally:
                    painter.end()
            else:
                self.host.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                return None, None

            self.host.scene.setBackgroundBrush(original_background)
            # Restore selection
            for item in selected_items:
                item.setSelected(True)
            if original_focus:
                original_focus.setFocus()
            return image, rect_to_render

        # Patch export_2d_png to INCLUDE reaction items
        def patched_export_2d_png(self):
            if not self.host.state_manager.data.atoms and not any(
                hasattr(i, "create_json_data") for i in self.host.scene.items()
            ):
                if context:
                    context.show_status_message("Nothing to export.")
                return

            default_name = "untitled-2d"
            try:
                if self.host.init_manager.current_file_path:
                    default_name = (
                        os.path.splitext(
                            os.path.basename(self.host.init_manager.current_file_path)
                        )[0]
                        + "-2d"
                    )
            except (AttributeError, TypeError, OSError) as _e:
                logging.warning("silenced: %s", _e)

            filePath, _ = QFileDialog.getSaveFileName(
                self, "Export 2D as PNG", default_name, "PNG Files (*.png)"
            )
            if not filePath:
                return
            if not filePath.lower().endswith(".png"):
                filePath += ".png"

            reply = QMessageBox.question(
                self,
                "Choose Background",
                'Do you want a transparent background?\n(Choose "No" to use the current background color)',
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return

            image, _ = _render_2d_to_image(
                self, is_transparent=(reply == QMessageBox.StandardButton.Yes)
            )
            if image and image.save(filePath, "PNG"):
                if context:
                    context.show_status_message(f"2D view exported to {filePath}")
            else:
                if context:
                    context.show_status_message("Failed to save image.")

        patch_core(MainWindowExport, "export_2d_png", patched_export_2d_png)

        def patched_copy_to_clipboard(self):
            if not self.host.state_manager.data.atoms and not any(
                hasattr(i, "create_json_data") for i in self.host.scene.items()
            ):
                if context:
                    context.show_status_message("Nothing to copy.")
                return

            # Default to Transparent for Clipboard as it is the most common desired behavior for passing to PPT/etc.
            # We could ask, but it interrupts flow.
            image, _ = _render_2d_to_image(self, is_transparent=True)
            if image:
                # Robust Copy: Provide both QImage and Raw PNG data to clipboard
                # This ensures transparency is preserved in more applications (e.g. Office, Slack)
                mime = QMimeData()
                mime.setImageData(image)

                # Also provide raw PNG data
                qba = QByteArray()
                buffer = QBuffer(qba)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                mime.setData("image/png", qba)

                QApplication.clipboard().setMimeData(mime)
                if context:
                    context.show_status_message(
                        "Copied 2D view to clipboard (Transparent)"
                    )
            else:
                if context:
                    context.show_status_message("Failed to copy image.")

        patch_core(MainWindowExport, "copy_to_clipboard", patched_copy_to_clipboard)

        # Patch export_2d_svg to INCLUDE reaction items
        def patched_export_2d_svg(self):
            if QSvgGenerator is None:
                if context:
                    context.show_status_message(
                        "SVG export not available (QtSvg missing)."
                    )
                return

            if not self.host.state_manager.data.atoms and not any(
                hasattr(i, "create_json_data") for i in self.host.scene.items()
            ):
                if context:
                    context.show_status_message("Nothing to export.")
                return

            default_name = "untitled-2d"
            try:
                if self.host.init_manager.current_file_path:
                    default_name = (
                        os.path.splitext(
                            os.path.basename(self.host.init_manager.current_file_path)
                        )[0]
                        + "-2d"
                    )
            except (AttributeError, TypeError, OSError) as _e:
                logging.warning("silenced: %s", _e)

            filePath, _ = QFileDialog.getSaveFileName(
                self, "Export 2D as SVG", default_name, "SVG Files (*.svg)"
            )
            if not filePath:
                return
            if not filePath.lower().endswith(".svg"):
                filePath += ".svg"

            reply = QMessageBox.question(
                self,
                "Choose Background",
                'Do you want a transparent background?\n(Choose "No" to use the current background color)',
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return

            # Get items to export: selected items if any, otherwise all visible
            selected_items = [
                i for i in self.host.scene.selectedItems() if i.isVisible()
            ]
            items_to_export = (
                selected_items if selected_items else list(self.host.scene.items())
            )

            # Get tight bounds excluding invisible and helper items
            molecule_bounds = QRectF()
            for item in items_to_export:
                # Skip if not visible
                if not item.isVisible():
                    continue
                # Skip helper items
                if item.__class__.__name__ in [
                    "ReactionHandle",
                    "ReactionGroupOverlay",
                    "SelectionRect",
                    "GuideLine",
                ]:
                    continue
                if hasattr(item, "handle_type"):
                    continue

                # Use sceneBoundingRect for tighter fit
                item_bounds = item.sceneBoundingRect()
                if item_bounds.isValid() and not item_bounds.isEmpty():
                    molecule_bounds = molecule_bounds.united(item_bounds)

            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                if context:
                    context.show_status_message(
                        "Error: Could not determine molecule bounds for export."
                    )
                return

            # Minimal padding (2px)
            rect_to_render = molecule_bounds.adjusted(-2, -2, 2, 2)

            original_background = self.host.scene.backgroundBrush()
            if reply == QMessageBox.StandardButton.Yes:
                # Use strictly transparent WHITE background
                self.host.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))
            else:
                # Use white background if user chose No transparency
                self.host.scene.setBackgroundBrush(QBrush(Qt.GlobalColor.white))

            generator = QSvgGenerator()
            generator.setFileName(filePath)
            generator.setSize(
                QSize(int(rect_to_render.width()), int(rect_to_render.height()))
            )
            generator.setResolution(96)  # Standard 96 DPI to fix small fonts

            # Normalize coordinates to 0,0 locally
            generator.setViewBox(
                QRectF(0, 0, rect_to_render.width(), rect_to_render.height())
            )
            generator.setTitle("MoleditPy Molecule")

            # Clear selection to avoid highlights in export
            selected_items = self.host.scene.selectedItems()
            self.host.scene.clearSelection()
            original_focus = self.host.scene.focusItem()
            self.host.scene.setFocusItem(None)

            painter = QPainter()
            if not painter.begin(generator):
                self.host.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                if original_focus:
                    original_focus.setFocus()
                if context:
                    context.show_status_message(
                        "Failed to start SVG painter. Check file access."
                    )
                return

            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                # Render content from scene-rect (source) to generator's origin (target)
                target_rect = QRectF(
                    0, 0, rect_to_render.width(), rect_to_render.height()
                )
                self.host.scene.render(painter, target_rect, rect_to_render)
            finally:
                painter.end()
                self.host.scene.setBackgroundBrush(original_background)
                # Restore selection
                for item in selected_items:
                    item.setSelected(True)
                if original_focus:
                    original_focus.setFocus()
            if context:
                context.show_status_message(f"2D view exported to {filePath}")

        patch_core(MainWindowExport, "export_2d_svg", patched_export_2d_svg)

        # Add Copy 2D Image to Clipboard
        def patched_copy_2d_image_to_clipboard(self):
            image, _ = _render_2d_to_image(self, is_transparent=True)
            if image:
                # Robust Copy: Provide both QImage and Raw PNG data to clipboard
                # This ensures transparency is preserved in more applications
                mime = QMimeData()
                mime.setImageData(image)

                # Also provide raw PNG data (very important for Slack/Word on Windows)
                qba = QByteArray()
                buffer = QBuffer(qba)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                mime.setData("image/png", qba)

                QApplication.clipboard().setMimeData(mime)
                if context:
                    context.show_status_message(
                        "2D Image copied to clipboard (Transparent).", 2000
                    )

        # We'll add this to MainWindowEditActions so it's easily accessible via Ctrl+Shift+C
        patch_core(
            MainWindowEditActions,
            "copy_2d_image_to_clipboard",
            patched_copy_2d_image_to_clipboard,
        )

        # Patch MainWindow with a delegator so self.copy_2d_image_to_clipboard works directly
        patch_core(
            MainWindow,
            "copy_2d_image_to_clipboard",
            lambda self: self.edit_actions_manager.copy_2d_image_to_clipboard(),
        )

        # Patch copy_svg_to_clipboard to INCLUDE reaction items
        def patched_copy_svg_to_clipboard(self):
            if QSvgGenerator is None:
                if context:
                    context.show_status_message(
                        "SVG copy not available (QtSvg missing)."
                    )
                return

            if not self.host.state_manager.data.atoms and not any(
                hasattr(i, "create_json_data") for i in self.host.scene.items()
            ):
                if context:
                    context.show_status_message("Nothing to copy.")
                return

            # Get items to export: selected items if any, otherwise all visible
            selected_items = [
                i for i in self.host.scene.selectedItems() if i.isVisible()
            ]
            items_to_export = (
                selected_items if selected_items else list(self.host.scene.items())
            )

            # Get tight bounds excluding invisible and helper items
            molecule_bounds = QRectF()
            for item in items_to_export:
                # Skip if not visible
                if not item.isVisible():
                    continue
                # Skip helper items
                if item.__class__.__name__ in [
                    "ReactionHandle",
                    "ReactionGroupOverlay",
                    "SelectionRect",
                    "GuideLine",
                ]:
                    continue
                if hasattr(item, "handle_type"):
                    continue

                # Use sceneBoundingRect for tighter fit
                item_bounds = item.sceneBoundingRect()
                if item_bounds.isValid() and not item_bounds.isEmpty():
                    molecule_bounds = molecule_bounds.united(item_bounds)

            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                if context:
                    context.show_status_message(
                        "Error: Could not determine molecule bounds for copy."
                    )
                return

            # Minimal padding (2px) - Consistent with PNG
            rect_to_render = molecule_bounds.adjusted(-2, -2, 2, 2)

            # Use strictly transparent WHITE background
            original_background = self.host.scene.backgroundBrush()
            self.host.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)

            generator = QSvgGenerator()
            generator.setOutputDevice(buffer)
            generator.setSize(
                QSize(int(rect_to_render.width()), int(rect_to_render.height()))
            )
            generator.setResolution(96)  # Standard 96 DPI
            generator.setViewBox(
                QRectF(0, 0, rect_to_render.width(), rect_to_render.height())
            )

            # Clear selection to avoid highlights
            self.host.scene.clearSelection()
            original_focus = self.host.scene.focusItem()
            self.host.scene.setFocusItem(None)

            painter = QPainter()
            if not painter.begin(generator):
                self.host.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                if original_focus:
                    original_focus.setFocus()
                return

            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                target_rect = QRectF(
                    0, 0, rect_to_render.width(), rect_to_render.height()
                )
                self.host.scene.render(painter, target_rect, rect_to_render)
            finally:
                painter.end()
                self.host.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                if original_focus:
                    original_focus.setFocus()

            mime = QMimeData()
            mime.setData("image/svg+xml", buffer.data())
            # Also set text for compatibility
            mime.setText(buffer.data().data().decode("utf-8"))
            QApplication.clipboard().setMimeData(mime)
            if context:
                context.show_status_message("Reaction copied to clipboard (SVG)")

        patch_core(
            MainWindowExport, "copy_svg_to_clipboard", patched_copy_svg_to_clipboard
        )

        # Register Shortcut
        def patched_setup_copy_shortcut(self):
            # Try to find if shortcut already exists or just create a new action
            if getattr(self, "copy_2d_action", None) is None:
                self.copy_2d_action = QAction("Copy 2D Image", self)
                self.copy_2d_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
                self.copy_2d_action.triggered.connect(self.copy_2d_image_to_clipboard)
                self.addAction(self.copy_2d_action)

        patched_setup_copy_shortcut(main_window)

        # --- ModeManager Toolbar Injection ---
        try:
            from .mode_manager import ModeManager
        except ImportError:
            try:
                from plugins.reaction_sketcher.mode_manager import ModeManager
            except ImportError:
                ModeManager = None

        if ModeManager:

            def patched_setup_property_toolbar(self):
                # Call original
                _core_originals[(ModeManager, "setup_property_toolbar")](self)

                # The original method adds SVG buttons at the end.
                # We can add our PNG/Copy buttons there too.
                self.property_toolbar.addSeparator()
                # Use proper error handling to ensure functions exist
                if hasattr(self.main_window, "export_2d_png"):
                    self.property_toolbar.addAction(
                        "Export PNG", lambda: self.main_window.export_2d_png()
                    )
                if hasattr(self.main_window, "copy_2d_image_to_clipboard"):
                    self.property_toolbar.addAction(
                        "Copy PNG",
                        lambda: self.main_window.copy_2d_image_to_clipboard(),
                    )

            patch_core(
                ModeManager, "setup_property_toolbar", patched_setup_property_toolbar
            )

            # If it's already setup, we might need to re-add buttons if we are re-patching
            rmm = getattr(main_window, "_reaction_mode_manager", None)
            if rmm and rmm.property_toolbar:
                # To avoid duplicates, check if already added
                has_png = any(
                    a.text() == "Export PNG" for a in rmm.property_toolbar.actions()
                )
                if not has_png:
                    rmm.property_toolbar.addSeparator()
                    if hasattr(main_window, "export_2d_png"):
                        rmm.property_toolbar.addAction(
                            "Export PNG", lambda: main_window.export_2d_png()
                        )
                    if hasattr(main_window, "copy_2d_image_to_clipboard"):
                        rmm.property_toolbar.addAction(
                            "Copy PNG", lambda: main_window.copy_2d_image_to_clipboard()
                        )

    # Patch MainWindow to ensure copy_to_clipboard is available for standard calls
    if MainWindowExport:

        def forward_copy_clip(self):
            # Forward to patched export logic
            if getattr(self, "copy_2d_image_to_clipboard", None) is not None:
                self.copy_2d_image_to_clipboard()
            elif hasattr(MainWindowExport, "copy_to_clipboard"):
                MainWindowExport.copy_to_clipboard(self)

        patch_core(MainWindow, "copy_to_clipboard", forward_copy_clip)


def apply_interaction_patches(main_window):
    """Applies patches to View2D for mouse/key interactions. Active only in Reaction Mode."""
    import types as _types

    try:
        from modules.view_2d import View2D
    except ImportError:
        try:
            from moleditpy.ui.zoomable_view import ZoomableView as View2D
        except ImportError:
            return

    def patch_int(cls, name, func):
        key = (cls, name)
        if key in _interaction_originals:
            setattr(cls, name, func)
            return
        if name in cls.__dict__:
            # Python-defined: save original so revert can restore it
            _interaction_originals[key] = cls.__dict__[name]
        else:
            # C++ inherited: store None so revert uses delattr (cleanly restores C++ method)
            _interaction_originals[key] = None
        setattr(cls, name, func)

    def _call_view_orig(method_name, view, *args):
        """Call the stored original view method, handling both Python and C++ (sip) methods."""
        orig = _interaction_originals.get((View2D, method_name))
        if orig is None:
            # Originally a C++ inherited method — call via super() as a bound call
            getattr(super(View2D, view), method_name)(*args)
        elif isinstance(orig, _types.FunctionType):
            # Pure Python method defined in View2D — call directly
            orig(view, *args)
        else:
            # Fallback for other callables (e.g. staticmethod wrappers)
            getattr(super(View2D, view), method_name)(*args)

    # --- View2D Mouse/Key Events ---
    def patched_mousePressEvent(view, event):
        mw = view.window()
        if (
            hasattr(mw, "_reaction_mode_manager")
            and mw._reaction_mode_manager.is_reaction_mode
        ):
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_press(event):
                return
        if (View2D, "mousePressEvent") in _interaction_originals:
            _call_view_orig("mousePressEvent", view, event)
        else:
            QGraphicsView.mousePressEvent(view, event)

    def patched_mouseMoveEvent(view, event):
        mw = view.window()
        if (
            hasattr(mw, "_reaction_mode_manager")
            and mw._reaction_mode_manager.is_reaction_mode
        ):
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_move(event):
                return
        if (View2D, "mouseMoveEvent") in _interaction_originals:
            _call_view_orig("mouseMoveEvent", view, event)
        else:
            QGraphicsView.mouseMoveEvent(view, event)

    def patched_mouseReleaseEvent(view, event):
        mw = view.window()
        if (
            hasattr(mw, "_reaction_mode_manager")
            and mw._reaction_mode_manager.is_reaction_mode
        ):
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_release(event):
                return
        if (View2D, "mouseReleaseEvent") in _interaction_originals:
            _call_view_orig("mouseReleaseEvent", view, event)
        else:
            QGraphicsView.mouseReleaseEvent(view, event)

    def patched_mouseDoubleClickEvent(view, event):
        mw = view.window()
        if (
            hasattr(mw, "_reaction_mode_manager")
            and mw._reaction_mode_manager.is_reaction_mode
        ):
            rmm = mw._reaction_mode_manager
            scene_pos = view.mapToScene(event.pos())
            scene = mw.scene
            item = scene.itemAt(scene_pos, view.transform()) if scene else None
            # Double-click on an atom/bond: select the entire connected molecule
            is_atom = item is not None and hasattr(item, "atom_id")
            is_bond = (
                item is not None
                and hasattr(item, "atom1")
                and hasattr(item, "atom2")
                and hasattr(getattr(item, "atom1", None), "atom_id")
            )
            if (is_atom or is_bond) and scene is not None:
                from collections import deque

                # Build atom and bond item maps
                atom_items = {
                    i.atom_id: i
                    for i in scene.items()
                    if hasattr(i, "atom_id") and not sip_isdeleted_safe(i)
                }
                bond_scene_items = [
                    i
                    for i in scene.items()
                    if hasattr(i, "atom1")
                    and hasattr(i, "atom2")
                    and hasattr(getattr(i, "atom1", None), "atom_id")
                    and not sip_isdeleted_safe(i)
                ]
                # Build adjacency: atom_id -> [(bond_item, neighbour_atom_id)]
                adj = {aid: [] for aid in atom_items}
                for b in bond_scene_items:
                    a1 = b.atom1.atom_id
                    a2 = b.atom2.atom_id
                    if a1 in adj and a2 in adj:
                        adj[a1].append((b, a2))
                        adj[a2].append((b, a1))
                # Determine start atom
                start_aid = getattr(item, "atom_id", None)
                if start_aid is None and is_bond:
                    start_aid = getattr(item.atom1, "atom_id", None)
                if start_aid is not None and start_aid in atom_items:
                    visited_atoms = set([start_aid])
                    visited_bond_ids = set()
                    q = deque([start_aid])
                    while q:
                        aid = q.popleft()
                        for bond_item, neighbour in adj.get(aid, []):
                            visited_bond_ids.add(id(bond_item))
                            if neighbour not in visited_atoms:
                                visited_atoms.add(neighbour)
                                q.append(neighbour)
                    scene.clearSelection()
                    for aid in visited_atoms:
                        atom_items[aid].setSelected(True)
                    for b in bond_scene_items:
                        if id(b) in visited_bond_ids:
                            b.setSelected(True)
                    return
            # Let interaction handler handle double-click
            handler = rmm.interaction_handler
            if handler and hasattr(handler, "handle_mouse_double_click"):
                if handler.handle_mouse_double_click(event):
                    return
        # Pass to original
        if (View2D, "mouseDoubleClickEvent") in _interaction_originals:
            _call_view_orig("mouseDoubleClickEvent", view, event)
        else:
            QGraphicsView.mouseDoubleClickEvent(view, event)

    def patched_keyPressEvent(view, event):
        mw = view.window()
        if (
            hasattr(mw, "_reaction_mode_manager")
            and mw._reaction_mode_manager.is_reaction_mode
        ):
            handler = mw._reaction_mode_manager.interaction_handler
            if handler:
                focus_item = view.scene().focusItem() if view.scene() else None
                is_editing_text = (
                    focus_item is not None
                    and hasattr(focus_item, "toPlainText")
                    and hasattr(focus_item, "create_json_data")
                    and bool(
                        focus_item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction
                    )
                )
                if is_editing_text:
                    # Let Qt deliver the key event normally to the focused text item
                    if (View2D, "keyPressEvent") in _interaction_originals:
                        _call_view_orig("keyPressEvent", view, event)
                    else:
                        QGraphicsView.keyPressEvent(view, event)
                    return

                if handler.handle_key_press(event):
                    event.accept()
                    return

        if (View2D, "keyPressEvent") in _interaction_originals:
            _call_view_orig("keyPressEvent", view, event)
        else:
            QGraphicsView.keyPressEvent(view, event)

    patch_int(View2D, "mousePressEvent", patched_mousePressEvent)
    patch_int(View2D, "mouseMoveEvent", patched_mouseMoveEvent)
    patch_int(View2D, "mouseReleaseEvent", patched_mouseReleaseEvent)
    patch_int(View2D, "mouseDoubleClickEvent", patched_mouseDoubleClickEvent)
    patch_int(View2D, "keyPressEvent", patched_keyPressEvent)


def revert_interaction_patches():
    _revert(_interaction_originals)


def revert_core_patches():
    _revert(_core_originals)


# Additional Imports for Atom Logic
try:
    from modules.constants import (
        ATOM_RADIUS,
        DESIRED_ATOM_PIXEL_RADIUS,
        FONT_FAMILY,
        FONT_WEIGHT_BOLD,
        CPK_COLORS,
    )
except ImportError:
    # Fallback or local definition if module path varies
    ATOM_RADIUS = 20
    DESIRED_ATOM_PIXEL_RADIUS = 15
    FONT_FAMILY = "Arial"
    FONT_WEIGHT_BOLD = 75
    CPK_COLORS = {"Default": QColor("#000000")}

# Removed shadowed sip_isdeleted_safe - using the version from .utils instead

# Removed redundant top-level patched_atom_paint - nested version inside apply_core_patches is used instead.


def revert_all_patches():
    _revert(_interaction_originals)
    _revert(_core_originals)


def apply_patches(main_window):
    """Legacy entry point: applies ALL (Core + Interaction). Used if one wants global activation."""
    apply_core_patches(main_window)
    apply_interaction_patches(main_window)


def unapply_patches(main_window):
    """Reverts all patches to restore original behavior."""
    revert_all_patches()

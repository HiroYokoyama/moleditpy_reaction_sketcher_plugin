#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import copy
from PyQt6.QtGui import (QColor, QPen, QBrush, QFont, QPainter, QPolygonF, QPaintEngine, 
                         QImage, QFontMetricsF, QAction, QKeySequence, qRgba)
from PyQt6.QtCore import Qt, QPointF, QByteArray, QMimeData, QRectF, QSize, QBuffer, QIODevice
from PyQt6.QtWidgets import QStyle, QApplication, QGraphicsItem, QFileDialog, QMessageBox, QGraphicsView
import os
import math
try:
    from PyQt6.QtSvg import QSvgGenerator
except ImportError:
    QSvgGenerator = None

# Storage for original methods
_core_originals = {}
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
            target_dict[key] = None # Marker for new method
        setattr(cls, name, new_func)

def _revert(target_dict):
    """Helper to revert patches in a dict."""
    for (cls, name), original in target_dict.items():
        if original is None:
            delattr(cls, name)
        else:
            setattr(cls, name, original)
    target_dict.clear()

def apply_core_patches(main_window):
    """Applies infrastructure patches (Undo, Delete, IO, Rendering, State) that should be persistent."""
    # Dynamic Class Resolution to handle package path variations (moleditpy vs modules)
    MainWindow = main_window.__class__
    
    # Resolve MainWindowAppState
    MainWindowAppState = None
    if hasattr(main_window, 'main_window_app_state') and hasattr(main_window.main_window_app_state, '_cls'):
        MainWindowAppState = main_window.main_window_app_state._cls
        
    # Resolve MoleculeScene
    MoleculeScene = None
    if hasattr(main_window, 'scene') and main_window.scene:
        MoleculeScene = main_window.scene.__class__

    # Resolve MainWindowEditActions
    MainWindowEditActions = None
    if hasattr(main_window, 'main_window_edit_actions') and hasattr(main_window.main_window_edit_actions, '_cls'):
        MainWindowEditActions = main_window.main_window_edit_actions._cls

    # Resolve AtomItem for Patching
    AtomItem = None
    try:
        from modules.atom_item import AtomItem
    except ImportError:
        try:
             from moleditpy.modules.atom_item import AtomItem
        except ImportError:
             pass

    # AtomItem paint patch is applied later (line 621) after the function is defined
    # if AtomItem:
    #     _patch(_core_originals, AtomItem, 'paint', patched_atom_paint)


    # Resolve View2D
    View2D = None
    if hasattr(main_window, 'view_2d') and main_window.view_2d:
        View2D = main_window.view_2d.__class__
    
    # If standard imports are needed for other classes or fallback
    import sys
    
    # Try to resolve classes from ALREADY LOADED modules to avoid double-import mismatches
    AtomItem = None
    BondItem = None
    MainWindowUiManager = None
    
    # Check sys.modules for hints
    for mod_name in list(sys.modules.keys()):
        if mod_name.endswith("modules.atom_item"):
            try: AtomItem = sys.modules[mod_name].AtomItem
            except: pass
        if mod_name.endswith("modules.bond_item"):
            try: BondItem = sys.modules[mod_name].BondItem
            except: pass
        if mod_name.endswith("modules.main_window_ui_manager"):
            try: MainWindowUiManager = sys.modules[mod_name].MainWindowUiManager
            except: pass
            
    # Fallback to instance inspection if available (Safest)
    if hasattr(main_window, 'data'):
        if AtomItem is None and main_window.data.atoms:
            for d in main_window.data.atoms.values():
                if d.get('item'):
                    AtomItem = d['item'].__class__
                    break
        if BondItem is None and main_window.data.bonds:
            for d in main_window.data.bonds.values():
                if d.get('item'):
                    BondItem = d['item'].__class__
                    break

    # Final Fallback to standard imports
    if AtomItem is None or BondItem is None:
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
                from moleditpy.modules.atom_item import AtomItem
                from moleditpy.modules.bond_item import BondItem
                from moleditpy.modules.main_window_ui_manager import MainWindowUiManager
                
                if MainWindowEditActions is None:
                    from moleditpy.modules.main_window_edit_actions import MainWindowEditActions
                if View2D is None:
                    from moleditpy.modules.view_2d import View2D
                if MoleculeScene is None:
                    from moleditpy.modules.molecule_scene import MoleculeScene
                if MainWindowAppState is None:
                    from moleditpy.modules.main_window_app_state import MainWindowAppState
            except ImportError:
                return

    def patch_core(cls, name, func):
        _patch(_core_originals, cls, name, func)

    # --- MainWindowUiManager.set_mode ---
    def patched_set_mode(self, mode_str):
        if (MainWindowUiManager, 'set_mode') in _core_originals:
             _core_originals[(MainWindowUiManager, 'set_mode')](self, mode_str)
        
        # Notify Reaction Mode Manager
        rmm = getattr(self, '_reaction_mode_manager', None)
        if rmm: 
            try:
                rmm._handle_main_mode_change(mode_str)
            except Exception: pass

    patch_core(MainWindowUiManager, 'set_mode', patched_set_mode)

    def patched_bond_bounding_rect(self):
        line = self.get_line_in_local_coords()
        bond_offset = 3.5
        settings = None
        try:
            if self.scene() and self.scene().views():
                win = self.scene().views()[0].window()
                if win and hasattr(win, 'settings'):
                     settings = win.settings
        except: pass
        
        if settings:
             if getattr(self, 'order', 1) == 3:
                 bond_offset = settings.get('bond_spacing_triple_2d', 3.5)
             else:
                 bond_offset = settings.get('bond_spacing_double_2d', 3.5)
             wedge_width = settings.get('bond_wedge_width_2d', 6.0)
        extra = (getattr(self, 'order', 1) - 1) * bond_offset + 2 + wedge_width
        return QRectF(line.p1(), line.p2()).normalized().adjusted(-extra, -extra, extra, extra)

    patch_core(BondItem, 'boundingRect', patched_bond_bounding_rect)


    # --- BondItem Init ---
    def patched_bond_item_init(self, atom1, atom2, order=1, stereo=0):
        _core_originals[(BondItem, '__init__')](self, atom1, atom2, order, stereo)
        self.group_id = None
        self.is_group_selected = False

    patch_core(BondItem, '__init__', patched_bond_item_init)

    # --- MainWindow.closeEvent ---
    def patched_close_event(self, event):
        """Override close to check for unsaved reaction items."""
        # Check if there are reaction items in the scene
        reaction_items = [i for i in self.scene.items() if hasattr(i, "create_json_data")]
        
        # Use the existing has_unsaved_changes flag from the undo system
        if reaction_items and getattr(self, 'has_unsaved_changes', False):
            reply = QMessageBox.question(
                self,
                "Unsaved Reaction Items",
                "There are unsaved reaction items. Do you want to save before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Yes:
                # Attempt to save
                if hasattr(self, "save_project"):
                     self.save_project()
                
                event.accept()
                return
            # No - just close without saving
        
        # Clean up ALL patches on close
        revert_all_patches()
        
        # Call original close event
        event.accept()
        orig = _core_originals.get((MainWindow, 'closeEvent'))
        if orig:
            return orig(self, event)
        from PyQt6.QtWidgets import QMainWindow
        return QMainWindow.closeEvent(self, event)

    patch_core(MainWindow, 'closeEvent', patched_close_event)



    # --- ItemChange (Shift+Drag Constraint) ---
    # Helper for constraint logic
    def apply_axis_constraint(item, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                scene = item.scene()
                if scene and hasattr(scene, "initial_positions_in_event") and item in scene.initial_positions_in_event:
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
    from .items import ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, ReactionTextItem, ReactionBracketItem, ReactionCircleItem
    
    rxn_classes = [ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, ReactionTextItem, ReactionBracketItem, ReactionCircleItem]
    
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
            from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                                ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
            
            selected_atoms = [item for item in self.scene.selectedItems() if hasattr(item, 'atom_id')]
            selected_rs_items_raw = [item for item in self.scene.selectedItems() if hasattr(item, 'create_json_data')]
            
            if not selected_atoms and not selected_rs_items_raw:
                return

            all_pts = []
            for a in selected_atoms: all_pts.append(a.pos())
            for rs in selected_rs_items_raw: all_pts.append(rs.sceneBoundingRect().center())
            
            if not all_pts: return
            center = QPointF(sum(p.x() for p in all_pts)/len(all_pts), sum(p.y() for p in all_pts)/len(all_pts))

            selected_atom_ids = {atom.atom_id for atom in selected_atoms}
            atom_id_to_idx_map = {}
            fragment_atoms = []
            for i, atom in enumerate(selected_atoms):
                atom_id_to_idx_map[atom.atom_id] = i
                fragment_atoms.append({
                    'symbol': atom.symbol,
                    'rel_pos': atom.pos() - center,
                    'charge': atom.charge,
                    'radical': atom.radical,
                })
            fragment_bonds = []
            for (id1, id2), bond_data in self.data.bonds.items():
                if id1 in selected_atom_ids and id2 in selected_atom_ids:
                    fragment_bonds.append({'idx1': atom_id_to_idx_map[id1], 'idx2': atom_id_to_idx_map[id2], 'order': bond_data['order'], 'stereo': bond_data.get('stereo', 0)})

            fragment_rs_items = []
            for item in selected_rs_items_raw:
                if hasattr(item, "create_json_data"):
                    d = item.create_json_data()
                    if d['type'] in ["arrow", "arrow_res", "arrow_eq", "arrow_retro", "arrow_no", "curved_fish", "curved_double", "arrow_dashed", "line", "line_curved", "line_dashed"]:
                        d['start_x'] -= center.x(); d['start_y'] -= center.y()
                        d['end_x'] -= center.x(); d['end_y'] -= center.y()
                        if "cp_x" in d: d["cp_x"] -= center.x(); d["cp_y"] -= center.y()
                    elif d['type'] in ["plus", "minus", "text", "bracket", "circle", "freehand"]:
                        d['x'] -= center.x(); d['y'] -= center.y()
                        if "points" in d: # Freehand
                             d["points"] = [[p[0]-center.x(), p[1]-center.y()] for p in d["points"]]
                    fragment_rs_items.append(d)

            import io, pickle
            data_to_pickle = {'atoms': fragment_atoms, 'bonds': fragment_bonds, 'rs_items': fragment_rs_items}
            byte_array = QByteArray()
            buffer = io.BytesIO()
            pickle.dump(data_to_pickle, buffer)
            byte_array.append(buffer.getvalue())

            mime_data = QMimeData()
            mime_data.setData(CLIPBOARD_MIME_TYPE, byte_array)
            QApplication.clipboard().setMimeData(mime_data)
            self.statusBar().showMessage(f"Copied selection ({len(fragment_atoms)} atoms, {len(fragment_rs_items)} reaction items).")

        except Exception as e:
            self.statusBar().showMessage(f"Error during patched copy: {e}")

    patch_core(MainWindowEditActions, 'copy_selection', patched_copy_selection)

    # --- Paste Selection ---
    def patched_paste_from_clipboard(self):
        try:
            from PyQt6.QtGui import QCursor
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            if not mime_data or not mime_data.hasFormat(CLIPBOARD_MIME_TYPE): return

            import io, pickle
            byte_array = mime_data.data(CLIPBOARD_MIME_TYPE)
            buffer = io.BytesIO(byte_array)
            fragment_data = pickle.load(buffer)
            
            paste_center_pos = self.view_2d.mapToScene(self.view_2d.mapFromGlobal(QCursor.pos()))
            self.scene.clearSelection()

            new_atoms = []
            for atom_data in fragment_data.get('atoms', []):
                pos = paste_center_pos + atom_data['rel_pos']
                new_id = self.scene.create_atom(atom_data['symbol'], pos, charge=atom_data.get('charge', 0), radical=atom_data.get('radical', 0))
                item = self.data.atoms[new_id]['item']
                new_atoms.append(item)
                item.setSelected(True)
            for bond_data in fragment_data.get('bonds', []):
                self.scene.create_bond(new_atoms[bond_data['idx1']], new_atoms[bond_data['idx2']], bond_order=bond_data.get('order', 1), bond_stereo=bond_data.get('stereo', 0))

            rs_items_data = fragment_data.get('rs_items', [])
            if rs_items_data:
                for d in rs_items_data:
                    if 'start_x' in d:
                        d['start_x'] += paste_center_pos.x(); d['start_y'] += paste_center_pos.y()
                        d['end_x'] += paste_center_pos.x(); d['end_y'] += paste_center_pos.y()
                        if "cp_x" in d: d["cp_x"] += paste_center_pos.x(); d["cp_y"] += paste_center_pos.y()
                    elif 'x' in d:
                        d['x'] += paste_center_pos.x(); d['y'] += paste_center_pos.y()
                        if "points" in d:
                             d["points"] = [[p[0]+paste_center_pos.x(), p[1]+paste_center_pos.y()] for p in d["points"]]
                
                from .utils import load_handler_core
                load_handler_core(self, rs_items_data)

            self.push_undo_state()
            self.statusBar().showMessage("Pasted selection.")
            if hasattr(self, 'activate_select_mode'):
                self.activate_select_mode()
        except Exception as e:
            self.statusBar().showMessage(f"Error during patched paste: {e}")

    patch_core(MainWindowEditActions, 'paste_from_clipboard', patched_paste_from_clipboard)

    # --- Patch MainWindowEditActions.delete_selection ---
    def patched_delete_selection(self):
        items = self.scene.selectedItems()
        if not items: return
        # Delegate to patched scene.delete_items which handles separation
        self.scene.delete_items(items)

    patch_core(MainWindowEditActions, 'delete_selection', patched_delete_selection)

    # --- Select All ---
    def patched_select_all(self):
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        for item in self.scene.items():
            if hasattr(item, "create_json_data") or isinstance(item, (AtomItem, BondItem)):
                item.setSelected(True)

    patch_core(MainWindowEditActions, 'select_all', patched_select_all)

    # --- Scene Delete Items ---
    def patched_scene_delete_items(self, items_to_delete):
        """Patched delete_items to filter and delete reaction items manually before calling original."""
        if not items_to_delete:
            return False

        # 1. Identify Reaction Items (generic QGraphicsItems that are NOT Atom/Bond)
        #    Reaction items usually have 'create_json_data' or are just standard items added by us.
        #    To be safe, we look for items that are NOT AtomItem or BondItem.
        reaction_items_to_delete = []
        core_items_to_delete = []

        for item in items_to_delete:
            if isinstance(item, (AtomItem, BondItem)):
                core_items_to_delete.append(item)
            else:
                reaction_items_to_delete.append(item)
        
        # 2. Delete Reaction Items manually
        #    Since the main app's delete_items might ignore or not handle them well if they aren't atoms/bonds.
        if reaction_items_to_delete:
            scene = self
            for item in reaction_items_to_delete:
                try:
                    if item.scene() == scene:
                        scene.removeItem(item)
                except Exception:
                    pass
            
            # If we only had reaction items, we are done
            if not core_items_to_delete:
                return True

        # 3. Call original delete_items for Atoms/Bonds
        if (MoleculeScene, 'delete_items') in _core_originals:
             return _core_originals[(MoleculeScene, 'delete_items')](self, set(core_items_to_delete))
        
        return False

    patch_core(MoleculeScene, 'delete_items', patched_scene_delete_items)
    def patched_atom_paint(self, painter, option, widget):
        # ALWAYS use patched paint logic to ensure visibility and background handling
        
        custom_color = getattr(self, 'pen_color', None)
        
        if not self.is_visible:
            # Still draw selection highlight even if atom is central to a bond (skeletal carbon)
            if self.isSelected():
                painter.save()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(0, 100, 255), 3))
                painter.drawRect(self.boundingRect())
                painter.restore()
            elif getattr(self, 'hovered', False):
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
            if hasattr(self, 'implicit_h_count') and self.implicit_h_count > 0:
                is_skeletal_carbon = (self.symbol == 'C' and self.charge == 0 and self.radical == 0 and len(self.bonds) > 0)
                if not is_skeletal_carbon:
                    hydrogen_part = "H"
                    if self.implicit_h_count > 1:
                        subscript_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
                        hydrogen_part += str(self.implicit_h_count).translate(subscript_map)

            flip_text = False
            if hydrogen_part and self.bonds:
                my_pos_x = self.pos().x()
                total_dx = 0.0
                for bond in self.bonds:
                    try:
                        other_atom = bond.atom1 if bond.atom2 is self else bond.atom2
                        if other_atom:
                            total_dx += (other_atom.pos().x() - my_pos_x)
                    except: continue
                if total_dx > 0: flip_text = True

            if flip_text:
                display_text = hydrogen_part + self.symbol
                alignment_flag = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                display_text = self.symbol + hydrogen_part
                alignment_flag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

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
                elif painter.device() and type(painter.device()).__name__ == "QSvgGenerator":
                    is_svg = True
            except: pass

            if is_svg:
                # [FIX] SVG: Force White Background to hide bonds (Clear mode fails in SVG)
                painter.setBrush(QColor(255, 255, 255))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(bg_rect)
            else:
                # Normal/PNG: Use Clear mode for transparency if background is empty
                bg_brush = self.scene().backgroundBrush() if self.scene() else QBrush(Qt.BrushStyle.NoBrush)
                if bg_brush.style() == Qt.BrushStyle.NoBrush:
                    painter.save()
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                    painter.setBrush(QColor(0, 0, 0, 255))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(bg_rect)
                    painter.restore()
                else:
                    painter.setBrush(bg_brush)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(bg_rect)

            if self.isSelected():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                # Use solid blue with thickness 3 for selected atom highlight
                painter.setPen(QPen(QColor(0, 100, 255), 3))
                painter.drawRect(self.boundingRect())
            elif getattr(self, 'hovered', False):
                painter.setPen(QPen(QColor(144, 238, 144, 200), 3))
                painter.drawRect(self.boundingRect())

            if custom_color:
                painter.setPen(QPen(custom_color))
            else:
                try:
                    from .constants import CPK_COLORS
                except ImportError:
                    try:
                        from moleditpy.modules.constants import CPK_COLORS
                    except ImportError:
                        CPK_COLORS = {'C': '#222222', 'O': 'red', 'N': 'blue', 'H': '#222222', 'S': '#D4A017', 'DEFAULT': '#222222'}

                color = QColor(CPK_COLORS.get(self.symbol, CPK_COLORS.get('DEFAULT', '#222222')))
                
                try:
                    if self.scene() and self.scene().views():
                        win = self.scene().views()[0].window()
                        if win and hasattr(win, 'settings'):
                             if self.symbol == 'H' or win.settings.get('atom_use_bond_color_2d', False):
                                 bond_col = win.settings.get('bond_color_2d', '#222222')
                                 color = QColor(bond_col)
                except Exception: pass
                
                if hasattr(self, "color") and self.color:
                     c = self.color
                     if isinstance(c, QColor): color = c
                     elif isinstance(c, str): color = QColor(c)

                painter.setPen(QPen(color))
                
            painter.drawText(text_rect, int(alignment_flag), display_text)
            
            if self.charge != 0:
                c_str = "+" if self.charge == 1 else ("-" if self.charge == -1 else f"{abs(self.charge)}{'+' if self.charge > 0 else '-'}")
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                cfm = painter.fontMetrics()
                cr = cfm.boundingRect(c_str)
                if flip_text:
                    cp = QPointF(text_rect.left() - cr.width(), text_rect.top() + cr.height() - 2)
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

    patch_core(AtomItem, 'paint', patched_atom_paint)


    # --- Delete Items (Global) ---
    def patched_delete_items(self, items_to_delete):
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                            ReactionMinusItem, ReactionResonanceArrowItem, 
                            ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                            ReactionNoArrowItem, ReactionCurvedArrowItem,
                            ReactionBracketItem, ReactionCircleItem,
                            ReactionLineItem, ReactionCurvedLineItem,
                            ReactionFreehandItem, ReactionDashedArrowItem)

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
                if item not in reaction_items: reaction_items.append(item)

        deleted_reaction = False
        for item in reaction_items:
            if item.scene() == self:
                if hasattr(item, "childItems"):
                    for child in item.childItems():
                        if hasattr(child, "handle_type") or child.__class__.__name__ == "ReactionHandle":
                            self.removeItem(child)
                self.removeItem(item)
                deleted_reaction = True

        success_core = False
        if core_items:
            success_core = _core_originals[(MoleculeScene, 'delete_items')](self, core_items)
            
        if deleted_reaction and not success_core:
            views = self.views()
            if views:
                window = views[0].window()
                if hasattr(window, "push_undo_state"):
                    window.push_undo_state()
            elif hasattr(self, "parent") and hasattr(self.parent(), "push_undo_state"):
                 self.parent().push_undo_state()
            
        return deleted_reaction or success_core

    patch_core(MoleculeScene, 'delete_items', patched_delete_items)

    # --- Rotate Molecule 2D ---
    def patched_rotate_molecule_2d(self, angle_degrees):
        try:
            import math
            selected_items = self.scene.selectedItems()
            
            # Identify targets
            target_atoms = [i for i in selected_items if isinstance(i, AtomItem)]
            target_reaction_items = [i for i in selected_items if hasattr(i, "rotate_around")]
            
            # If nothing selected, rotate everything
            if not target_atoms and not target_reaction_items:
                target_atoms = [data['item'] for data in self.data.atoms.values() if data.get('item')]
                # Filter out deleted atoms if any
                target_atoms = [a for a in target_atoms if a.scene() is not None]
                
                # Gather reaction items from scene
                for item in self.scene.items():
                    if hasattr(item, "rotate_around"):
                        target_reaction_items.append(item)
            
            if not target_atoms and not target_reaction_items:
                self.statusBar().showMessage("No items to rotate.")
                return

            # Calculate Center
            points = []
            for atom in target_atoms:
                points.append(atom.pos())
            
            for item in target_reaction_items:
                 # Prefer scene bounding rect center for calculation
                 points.append(item.sceneBoundingRect().center())
            
            if not points: return
            
            center_x = sum(p.x() for p in points) / len(points)
            center_y = sum(p.y() for p in points) / len(points)
            center = QPointF(center_x, center_y)
            
            rad = math.radians(angle_degrees)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            
            # Rotate Atoms
            for atom in target_atoms:
                dx = atom.pos().x() - center_x
                dy = atom.pos().y() - center_y
                # Rotation logic: new_x = x*cos - y*sin
                new_dx = dx * cos_a - dy * sin_a
                new_dy = dx * sin_a + dy * cos_a
                atom.setPos(QPointF(center_x + new_dx, center_y + new_dy))
                
            # Rotate Reaction Items
            for item in target_reaction_items:
                item.rotate_around(center, angle_degrees)

            # Update bonds
            self.scene.update_connected_bonds(target_atoms)
            
            self.push_undo_state()
            self.statusBar().showMessage(f"Rotated {len(target_atoms) + len(target_reaction_items)} items by {angle_degrees} degrees.")
            self.scene.update()
            self.scene.update_all_items()
            
        except Exception as e:
            self.statusBar().showMessage(f"Error rotating: {e}")

    patch_core(MainWindowEditActions, 'rotate_molecule_2d', patched_rotate_molecule_2d)

    # --- MoleculeScene.keyPressEvent ---
    def patched_molecule_scene_key_press_event(self, event):
        # If focus is on a ReactionTextItem in edit mode, and it accepted the event,
        # we skip the standard molecule sketcher shortcuts.
        view = self.views()[0] if self.views() else None
        if view:
            focus_item = self.focusItem()
            from .items import ReactionTextItem
            if isinstance(focus_item, ReactionTextItem) and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction):
                # Standard QGraphicsScene logic ensures focusItem receives the key.
                # We skip MoleculeScene's shortcuts but let the base class deliver the event.
                from PyQt6.QtWidgets import QGraphicsScene
                return QGraphicsScene.keyPressEvent(self, event)
        
        orig = _core_originals.get((MoleculeScene, 'keyPressEvent'))
        if orig:
            return orig(self, event)
        from PyQt6.QtWidgets import QGraphicsScene
        return QGraphicsScene.keyPressEvent(self, event)

    patch_core(MoleculeScene, 'keyPressEvent', patched_molecule_scene_key_press_event)

    # --- Scene Clear ---
    def patched_scene_clear(self):
        from PyQt6.QtWidgets import QGraphicsScene
        items_to_save = [i for i in self.items() if hasattr(i, "create_json_data")]
        for item in items_to_save: self.removeItem(item)
        QGraphicsScene.clear(self)
        for item in items_to_save: self.addItem(item)
            
    if hasattr(MoleculeScene, 'clear'):
        patch_core(MoleculeScene, 'clear', patched_scene_clear)
    else: # If clear() didn't exist, we add it. 
        # _patch handles this by setting original to None
        patch_core(MoleculeScene, 'clear', patched_scene_clear)

    # --- Clear 2D Editor ---
    def patched_clear_2d_editor(self, push_to_undo=True):
        rs_items_data = []
        for it in self.scene.items():
            if hasattr(it, "create_json_data"):
                rs_items_data.append(it.create_json_data())
        
        _core_originals[(MainWindowEditActions, 'clear_2d_editor')](self, push_to_undo=push_to_undo)
        
        if rs_items_data:
            from .utils import load_handler_core
            load_handler_core(self, rs_items_data)
        
    patch_core(MainWindowEditActions, 'clear_2d_editor', patched_clear_2d_editor)


    # --- Clean Up 2D ---
    def patched_clean_up_2d_structure(self):
        # Cleanup now works in Reaction Mode with CoG preservation and supports selection
        try:
            from rdkit.Chem import AllChem, rdmolops
        except ImportError:
            self.statusBar().showMessage("Error: RDKit is required for structure optimization.")
            return

        self.statusBar().showMessage("Optimizing 2D structure (CoG Preserved)...")
        self.scene.clear_all_problem_flags()
        if not self.data.atoms:
            self.statusBar().showMessage("Error: No atoms to optimize.")
            return

        try:
            mol = self.data.to_rdkit_mol()
            if mol is None or mol.GetNumAtoms() == 0:
                self.check_chemistry_problems_fallback()
                return

            frags = rdmolops.GetMolFrags(mol, asMols=False, sanitizeFrags=False)
            
            # Identify target fragments from selection
            selected_items = self.scene.selectedItems()
            target_atom_ids = set()
            
            for item in selected_items:
                # Check for AtomItem (atom_id)
                if hasattr(item, "atom_id") and item.atom_id is not None:
                    target_atom_ids.add(item.atom_id)
                # Check for BondItem (atom1, atom2)
                elif hasattr(item, "atom1") and hasattr(item, "atom2"):
                     a1 = item.atom1
                     a2 = item.atom2
                     # Resolve IDs if they are objects
                     if hasattr(a1, "atom_id"): target_atom_ids.add(a1.atom_id)
                     elif isinstance(a1, int): target_atom_ids.add(a1)
                     
                     if hasattr(a2, "atom_id"): target_atom_ids.add(a2.atom_id)
                     elif isinstance(a2, int): target_atom_ids.add(a2)

            target_frag_indices = set()
            if not target_atom_ids:
                # No selection -> Optimize ALL
                target_frag_indices = set(range(len(frags)))
            else:
                # Selection -> Optimize only fragments with selected atoms
                for i, frag_indices in enumerate(frags):
                    # Check intersection
                    is_target = False
                    for idx in frag_indices:
                        rd_atom = mol.GetAtomWithIdx(idx)
                        aid = rd_atom.GetIntProp("_original_atom_id")
                        if aid in target_atom_ids:
                            is_target = True
                            break
                    if is_target:
                        target_frag_indices.add(i)

            if not target_frag_indices:
                self.statusBar().showMessage("No valid atoms selected for optimization.")
                return

            orig_cogs = {}
            for i, frag_indices in enumerate(frags):
                if i not in target_frag_indices: continue
                sum_x = 0.0; sum_y = 0.0
                atom_count = 0
                for idx in frag_indices:
                    rd_atom = mol.GetAtomWithIdx(idx)
                    aid = rd_atom.GetIntProp("_original_atom_id")
                    if aid in self.data.atoms:
                        pos = self.data.atoms[aid]['item'].pos()
                        sum_x += pos.x(); sum_y += pos.y()
                        atom_count += 1
                if atom_count > 0:
                    orig_cogs[i] = QPointF(sum_x / atom_count, sum_y / atom_count)

            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()
            SCALE = 50.0
            
            updated_count = 0
            for i, frag_indices in enumerate(frags):
                if i not in target_frag_indices: continue
                if i not in orig_cogs: continue
                
                rd_sum_x = 0.0; rd_sum_y = 0.0
                for idx in frag_indices:
                    pos = conf.GetAtomPosition(idx)
                    rd_sum_x += pos.x; rd_sum_y += pos.y
                rd_cog_x = rd_sum_x / len(frag_indices)
                rd_cog_y = rd_sum_y / len(frag_indices)
                
                for idx in frag_indices:
                    rd_atom = mol.GetAtomWithIdx(idx)
                    aid = rd_atom.GetIntProp("_original_atom_id")
                    if aid in self.data.atoms:
                        item = self.data.atoms[aid]['item']
                        rd_pos = conf.GetAtomPosition(idx)
                        sx = ((rd_pos.x - rd_cog_x) * SCALE) + orig_cogs[i].x()
                        sy = (-(rd_pos.y - rd_cog_y) * SCALE) + orig_cogs[i].y()
                        new_pos = QPointF(sx, sy)
                        item.setPos(new_pos)
                        self.data.atoms[aid]['pos'] = new_pos
                updated_count += 1

            for bond_data in self.data.bonds.values():
                if bond_data.get('item'):
                    bond_data['item'].update_position()

            self.resolve_overlapping_groups()
            self.update_2d_measurement_labels()
            self.scene.update()
            
            msg = "2D optimization successful."
            if target_atom_ids:
                 msg = f"Optimized {updated_count} selected fragment(s)."
            else:
                 msg = f"Optimized {updated_count} fragment(s)."
            
            self.statusBar().showMessage(msg)
            self.push_undo_state()

        except Exception as e:
            self.statusBar().showMessage(f"Error during CoG optimization: {e}")
            import traceback
        finally:
            if hasattr(self, 'view_2d') and self.view_2d:
                self.view_2d.setFocus()

    patch_core(MainWindowEditActions, 'clean_up_2d_structure', patched_clean_up_2d_structure)


    # --- Get/Set State, Push Undo ---
    def patched_get_current_state(self):
        state = _core_originals[(MainWindowAppState, 'get_current_state')](self)
        
        # Group IDs for atoms and bonds
        agroups = {str(aid): getattr(d['item'], 'group_id', None) for aid, d in self.data.atoms.items() if hasattr(d['item'], 'group_id')}
        bgroups = {f"{k[0]}-{k[1]}": getattr(d['item'], 'group_id', None) for k, d in self.data.bonds.items() if hasattr(d['item'], 'group_id')}
        state['rs_atom_groups'] = agroups
        state['rs_bond_groups'] = bgroups
        
        # Reaction items
        rs_items_data = []
        for item in self.scene.items():
            if hasattr(item, "create_json_data"):
                 rs_items_data.append(item.create_json_data())
        
        rs_items_data.sort(key=lambda x: (x.get('type', ''), x.get('x', x.get('start_x', 0)), x.get('y', x.get('start_y', 0))))
        
        state['rs_items'] = rs_items_data
        return state

    patch_core(MainWindowAppState, 'get_current_state', patched_get_current_state)

    def patched_set_state_from_data(self, state_data):
        _core_originals[(MainWindowAppState, 'set_state_from_data')](self, state_data)
        
        agroups = state_data.get('rs_atom_groups', {})
        for aid_str, gid in agroups.items():
            aid = int(aid_str) if aid_str.isdigit() else aid_str
            if aid in self.data.atoms:
                self.data.atoms[aid]['item'].group_id = gid

        bgroups = state_data.get('rs_bond_groups', {})
        for key, gid in bgroups.items():
            try:
                id1_str, id2_str = key.split('-')
                id1 = int(id1_str) if id1_str.isdigit() else id1_str
                id2 = int(id2_str) if id2_str.isdigit() else id2_str
                k = (id1, id2)
                if k in self.data.bonds:
                    self.data.bonds[k]['item'].group_id = gid
            except: continue

        for item in list(self.scene.items()):
            if hasattr(item, "create_json_data"):
                 self.scene.removeItem(item)

        if 'rs_items' in state_data:
            from .utils import load_handler_core
            load_handler_core(self, state_data['rs_items'])

    patch_core(MainWindowAppState, 'set_state_from_data', patched_set_state_from_data)

    def patched_push_undo_state(self):
        if getattr(self, '_is_restoring_state', False): return

        curr_state = self.get_current_state()
        
        current_comp = {
            'atoms': {k: (v['symbol'], v['item'].pos().x(), v['item'].pos().y(), v.get('charge', 0), v.get('radical', 0), 
                          getattr(v['item'], 'pen_color', QColor()).name()) for k, v in self.data.atoms.items()},
            'bonds': {k: (v['order'], v.get('stereo', 0), 
                          getattr(v['item'], 'pen_color', QColor()).name()) for k, v in self.data.bonds.items()},
            '_next_atom_id': self.data._next_atom_id,
            'mol_3d': self.current_mol.ToBinary() if self.current_mol else None,
            'mol_3d_atom_ids': curr_state.get('mol_3d_atom_ids', []),
            'rs_items': curr_state.get('rs_items', []),
            'rs_atom_groups': curr_state.get('rs_atom_groups', {}),
            'rs_bond_groups': curr_state.get('rs_bond_groups', {})
        }
        
        last_comp = None
        if self.undo_stack:
            last_state = self.undo_stack[-1]
            last_atoms = last_state.get('atoms', {})
            last_bonds = last_state.get('bonds', {})
            last_acols = last_state.get('rs_atom_colors', {})
            last_bcols = last_state.get('rs_bond_colors', {})
            last_agroups = last_state.get('rs_atom_groups', {})
            last_bgroups = last_state.get('rs_bond_groups', {})
            
            last_comp = {
                'atoms': {k: (v['symbol'], v['pos'][0], v['pos'][1], v.get('charge', 0), v.get('radical', 0), 
                              last_acols.get(str(k), "")) for k, v in last_atoms.items()},
                'bonds': {k: (v['order'], v.get('stereo', 0), 
                              last_bcols.get(f"{k[0]}-{k[1]}", "")) for k, v in last_bonds.items()},
                '_next_atom_id': last_state.get('_next_atom_id'),
                'mol_3d': last_state.get('mol_3d', None),
                'mol_3d_atom_ids': last_state.get('mol_3d_atom_ids', []),
                'rs_items': last_state.get('rs_items', []),
                'rs_atom_groups': last_agroups,
                'rs_bond_groups': last_bgroups
            }

        if not last_comp or current_comp != last_comp:
            state = copy.deepcopy(curr_state)
            self.undo_stack.append(state)
            self.redo_stack.clear()
            if self.initialization_complete:
                self.has_unsaved_changes = True
                self.update_window_title()

        self.update_implicit_hydrogens()
        self.update_realtime_info()
        self.update_undo_redo_actions()

    patch_core(MainWindowAppState, 'push_undo_state', patched_push_undo_state)

    # --- MainWindowExport Patches (PNG/SVG/Clipboard) ---
    try:
        from modules.main_window_export import MainWindowExport
    except:
        try: from moleditpy.modules.main_window_export import MainWindowExport
        except: MainWindowExport = None

    if MainWindowExport:
        def _render_2d_to_image(self, is_transparent=True):
            all_visible_items = [i for i in self.scene.items() if i.isVisible()]
            molecule_bounds = QRectF()
            for item in all_visible_items:
                if item.__class__.__name__ in ["ReactionHandle", "ReactionGroupOverlay", "SelectionRect", "GuideLine"]:
                    continue
                if hasattr(item, "handle_type"):
                    continue
                
                item_bounds = item.sceneBoundingRect()
                molecule_bounds = molecule_bounds.united(item_bounds)

            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                return None, None

            padding = 5
            rect_to_render = molecule_bounds.adjusted(-padding, -padding, padding, padding)
            
            w = max(1, int(math.ceil(rect_to_render.width())))
            h = max(1, int(math.ceil(rect_to_render.height())))
            
            # Use ARGB32 for proper alpha channel support
            image = QImage(w, h, QImage.Format.Format_ARGB32)
            if image.isNull():
                return None, None
                
            # Fill with truly transparent using qRgba
            if is_transparent:
                image.fill(qRgba(255, 255, 255, 0))  # Transparent White (helps avoid black halos)
            else:
                image.fill(Qt.GlobalColor.white)
            
            original_background = self.scene.backgroundBrush()
            if is_transparent:
                # Set truly transparent WHITE background (255,255,255,0) as requested by user.
                # The patched_atom_paint will detect alpha=0 and trigger the eraser logic.
                self.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))
            
            # Clear selection and focus to avoid highlights/cursors in export
            selected_items = self.scene.selectedItems()
            self.scene.clearSelection()
            original_focus = self.scene.focusItem()
            self.scene.setFocusItem(None)
            
            painter = QPainter()
            if painter.begin(image):
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    if is_transparent:
                        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                    self.scene.render(painter, QRectF(0, 0, w, h), rect_to_render)
                finally:
                    painter.end()
            else:
                self.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                return None, None

            self.scene.setBackgroundBrush(original_background)
            # Restore selection
            for item in selected_items:
                item.setSelected(True)
            if original_focus:
                original_focus.setFocus()
            return image, rect_to_render

        # Patch export_2d_png to INCLUDE reaction items
        def patched_export_2d_png(self):
            if not self.data.atoms and not any(hasattr(i, "create_json_data") for i in self.scene.items()):
                self.statusBar().showMessage("Nothing to export.")
                return

            default_name = "untitled-2d"
            try:
                if self.current_file_path:
                    default_name = os.path.splitext(os.path.basename(self.current_file_path))[0] + "-2d"
            except: pass

            filePath, _ = QFileDialog.getSaveFileName(self, "Export 2D as PNG", default_name, "PNG Files (*.png)")
            if not filePath: return
            if not filePath.lower().endswith(".png"): filePath += ".png"

            reply = QMessageBox.question(self, 'Choose Background',
                                         'Do you want a transparent background?\n(Choose "No" to use the current background color)',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Cancel: return
            
            image, _ = _render_2d_to_image(self, is_transparent=(reply == QMessageBox.StandardButton.Yes))
            if image and image.save(filePath, "PNG"):
                self.statusBar().showMessage(f"2D view exported to {filePath}")
            else:
                self.statusBar().showMessage("Failed to save image.")

        patch_core(MainWindowExport, 'export_2d_png', patched_export_2d_png)

        def patched_copy_to_clipboard(self):
            if not self.data.atoms and not any(hasattr(i, "create_json_data") for i in self.scene.items()):
                self.statusBar().showMessage("Nothing to copy.")
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
                self.statusBar().showMessage("Copied 2D view to clipboard (Transparent)")
            else:
                self.statusBar().showMessage("Failed to copy image.")

        patch_core(MainWindowExport, 'copy_to_clipboard', patched_copy_to_clipboard)

        # Patch export_2d_svg to INCLUDE reaction items
        def patched_export_2d_svg(self):
            if QSvgGenerator is None:
                self.statusBar().showMessage("SVG export not available (QtSvg missing).")
                return

            if not self.data.atoms and not any(hasattr(i, "create_json_data") for i in self.scene.items()):
                self.statusBar().showMessage("Nothing to export.")
                return

            default_name = "untitled-2d"
            try:
                if self.current_file_path:
                    default_name = os.path.splitext(os.path.basename(self.current_file_path))[0] + "-2d"
            except: pass

            filePath, _ = QFileDialog.getSaveFileName(self, "Export 2D as SVG", default_name, "SVG Files (*.svg)")
            if not filePath: return
            if not filePath.lower().endswith(".svg"): filePath += ".svg"

            reply = QMessageBox.question(self, 'Choose Background', 'Do you want a transparent background?\n(Choose "No" to use the current background color)',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Cancel: return

            # Get items to export: selected items if any, otherwise all visible
            selected_items = [i for i in self.scene.selectedItems() if i.isVisible()]
            items_to_export = selected_items if selected_items else list(self.scene.items())
            
            # Get tight bounds excluding invisible and helper items
            molecule_bounds = QRectF()
            for item in items_to_export:
                # Skip if not visible
                if not item.isVisible():
                    continue
                # Skip helper items
                if item.__class__.__name__ in ["ReactionHandle", "ReactionGroupOverlay", "SelectionRect", "GuideLine"]:
                    continue
                if hasattr(item, "handle_type"):
                    continue
                
                # Use sceneBoundingRect for tighter fit
                item_bounds = item.sceneBoundingRect()
                if item_bounds.isValid() and not item_bounds.isEmpty():
                    molecule_bounds = molecule_bounds.united(item_bounds)
            
            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                self.statusBar().showMessage("Error: Could not determine molecule bounds for export.")
                return

            # Minimal padding (2px)
            rect_to_render = molecule_bounds.adjusted(-2, -2, 2, 2)
            
            original_background = self.scene.backgroundBrush()
            if reply == QMessageBox.StandardButton.Yes:
                # Use strictly transparent WHITE background
                self.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))
            else:
                # Use white background if user chose No transparency
                self.scene.setBackgroundBrush(QBrush(Qt.GlobalColor.white))

            generator = QSvgGenerator()
            generator.setFileName(filePath)
            generator.setSize(QSize(int(rect_to_render.width()), int(rect_to_render.height())))
            generator.setResolution(96) # Standard 96 DPI to fix small fonts
            
            # Normalize coordinates to 0,0 locally
            generator.setViewBox(QRectF(0, 0, rect_to_render.width(), rect_to_render.height()))
            generator.setTitle("MoleditPy Molecule")
            
            # Clear selection to avoid highlights in export
            selected_items = self.scene.selectedItems()
            self.scene.clearSelection()
            self.original_focus = self.scene.focusItem()
            self.scene.setFocusItem(None)
            
            painter = QPainter()
            if not painter.begin(generator):
                self.scene.setBackgroundBrush(original_background)
                for item in selected_items:
                    item.setSelected(True)
                self.statusBar().showMessage("Failed to start SVG painter. Check file access.")
                return

            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                # Render content from scene-rect (source) to generator's origin (target)
                target_rect = QRectF(0, 0, rect_to_render.width(), rect_to_render.height())
                self.scene.render(painter, target_rect, rect_to_render)
            finally:
                painter.end()
                self.scene.setBackgroundBrush(original_background)
                # Restore selection
                # Restore selection
                for item in selected_items:
                    item.setSelected(True)
                if hasattr(self, 'original_focus') and self.original_focus:
                     self.original_focus.setFocus()
            self.statusBar().showMessage(f"2D view exported to {filePath}")

        patch_core(MainWindowExport, 'export_2d_svg', patched_export_2d_svg)

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
                self.statusBar().showMessage("2D Image copied to clipboard (Transparent).", 2000)
        
        # We'll add this to MainWindowEditActions so it's easily accessible via Ctrl+Shift+C
        patch_core(MainWindowEditActions, 'copy_2d_image_to_clipboard', patched_copy_2d_image_to_clipboard)
        
        # Patch MainWindow with a delegator so self.copy_2d_image_to_clipboard works directly
        patch_core(MainWindow, 'copy_2d_image_to_clipboard', lambda self: self.main_window_edit_actions.copy_2d_image_to_clipboard())

        # Patch copy_svg_to_clipboard to INCLUDE reaction items
        def patched_copy_svg_to_clipboard(self):
            if QSvgGenerator is None:
                self.statusBar().showMessage("SVG copy not available (QtSvg missing).")
                return

            if not self.data.atoms and not any(hasattr(i, "create_json_data") for i in self.scene.items()):
                self.statusBar().showMessage("Nothing to copy.")
                return

            # Get items to export: selected items if any, otherwise all visible
            selected_items = [i for i in self.scene.selectedItems() if i.isVisible()]
            items_to_export = selected_items if selected_items else list(self.scene.items())
            
            # Get tight bounds excluding invisible and helper items
            molecule_bounds = QRectF()
            for item in items_to_export:
                # Skip if not visible
                if not item.isVisible(): continue
                # Skip helper items
                if item.__class__.__name__ in ["ReactionHandle", "ReactionGroupOverlay", "SelectionRect", "GuideLine"]:
                     continue
                if hasattr(item, "handle_type"): continue
                
                # Use sceneBoundingRect for tighter fit
                item_bounds = item.sceneBoundingRect()
                if item_bounds.isValid() and not item_bounds.isEmpty():
                    molecule_bounds = molecule_bounds.united(item_bounds)
            
            if molecule_bounds.isEmpty() or not molecule_bounds.isValid():
                self.statusBar().showMessage("Error: Could not determine molecule bounds for copy.")
                return

            # Minimal padding (2px) - Consistent with PNG
            rect_to_render = molecule_bounds.adjusted(-2, -2, 2, 2)
            
            # Use strictly transparent WHITE background
            original_background = self.scene.backgroundBrush()
            self.scene.setBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)

            generator = QSvgGenerator()
            generator.setOutputDevice(buffer)
            generator.setSize(QSize(int(rect_to_render.width()), int(rect_to_render.height())))
            generator.setResolution(96) # Standard 96 DPI
            generator.setViewBox(QRectF(0, 0, rect_to_render.width(), rect_to_render.height()))
            
            # Clear selection to avoid highlights
            self.scene.clearSelection()
            self.original_focus = self.scene.focusItem()
            self.scene.setFocusItem(None)
            
            painter = QPainter()
            if not painter.begin(generator):
                 self.scene.setBackgroundBrush(original_background)
                 for item in selected_items: item.setSelected(True)
                 return
            
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                target_rect = QRectF(0, 0, rect_to_render.width(), rect_to_render.height())
                self.scene.render(painter, target_rect, rect_to_render)
            finally:
                painter.end()
                self.scene.setBackgroundBrush(original_background)
                for item in selected_items: item.setSelected(True)
                if hasattr(self, 'original_focus') and self.original_focus:
                     self.original_focus.setFocus()
            
            mime = QMimeData()
            mime.setData("image/svg+xml", buffer.data())
            # Also set text for compatibility
            mime.setText(buffer.data().data().decode('utf-8'))
            QApplication.clipboard().setMimeData(mime)
            self.statusBar().showMessage("Reaction copied to clipboard (SVG)")

        patch_core(MainWindowExport, 'copy_svg_to_clipboard', patched_copy_svg_to_clipboard)

        # Register Shortcut
        def patched_setup_copy_shortcut(self):
            # Try to find if shortcut already exists or just create a new action
            if not hasattr(self, "copy_2d_action"):
                self.copy_2d_action = QAction("Copy 2D Image", self)
                self.copy_2d_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
                self.copy_2d_action.triggered.connect(self.copy_2d_image_to_clipboard)
                self.addAction(self.copy_2d_action)
        
        # We can hook into an existing initialization or just call it if we have 'main_window'
        if hasattr(main_window, 'setup_ui') or True: # Just apply directly
            patched_setup_copy_shortcut(main_window)

        # --- ModeManager Toolbar Injection ---
        try:
            from .mode_manager import ModeManager
        except:
            try: from plugins.reaction_sketcher.mode_manager import ModeManager
            except: ModeManager = None
            
        if ModeManager:
            def patched_setup_property_toolbar(self):
                # Call original
                _core_originals[(ModeManager, 'setup_property_toolbar')](self)
                
                # The original method adds SVG buttons at the end.
                # We can add our PNG/Copy buttons there too.
                self.property_toolbar.addSeparator()
                # Use proper error handling to ensure functions exist
                if hasattr(self.main_window, 'export_2d_png'):
                    self.property_toolbar.addAction("Export PNG", lambda: self.main_window.export_2d_png())
                if hasattr(self.main_window, 'copy_2d_image_to_clipboard'):
                    self.property_toolbar.addAction("Copy PNG", lambda: self.main_window.copy_2d_image_to_clipboard())
                
            patch_core(ModeManager, 'setup_property_toolbar', patched_setup_property_toolbar)
            
            # If it's already setup, we might need to re-add buttons if we are re-patching
            rmm = getattr(main_window, '_reaction_mode_manager', None)
            if rmm and rmm.property_toolbar:
                # To avoid duplicates, check if already added
                has_png = any(a.text() == "Export PNG" for a in rmm.property_toolbar.actions())
                if not has_png:
                    rmm.property_toolbar.addSeparator()
                    if hasattr(main_window, 'export_2d_png'):
                        rmm.property_toolbar.addAction("Export PNG", lambda: main_window.export_2d_png())
                    if hasattr(main_window, 'copy_2d_image_to_clipboard'):
                        rmm.property_toolbar.addAction("Copy PNG", lambda: main_window.copy_2d_image_to_clipboard())


    # Patch MainWindow to ensure copy_to_clipboard is available for standard calls
    if MainWindowExport:
        def forward_copy_clip(self):
            # Forward to patched export logic
            if hasattr(self, 'copy_2d_image_to_clipboard'):
                 self.copy_2d_image_to_clipboard()
            elif hasattr(MainWindowExport, 'copy_to_clipboard'):
                MainWindowExport.copy_to_clipboard(self)
            
        patch_core(MainWindow, 'copy_to_clipboard', forward_copy_clip)

def apply_interaction_patches(main_window):
    """Applies patches to View2D for mouse/key interactions. Active only in Reaction Mode."""
    try:
        from modules.view_2d import View2D
    except ImportError:
        try:
             from moleditpy.modules.view_2d import View2D
        except ImportError: return

    def patch_int(cls, name, func):
        _patch(_interaction_originals, cls, name, func)

    # --- View2D Mouse/Key Events ---
    def patched_mousePressEvent(view, event):
        mw = view.window()
        if hasattr(mw, "_reaction_mode_manager") and mw._reaction_mode_manager.is_reaction_mode:
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_press(event):
                return
        if (View2D, 'mousePressEvent') in _interaction_originals:
             _interaction_originals[(View2D, 'mousePressEvent')](view, event)
        else:
             # Fallback
             QGraphicsView.mousePressEvent(view, event)

    def patched_mouseMoveEvent(view, event):
        mw = view.window()
        if hasattr(mw, "_reaction_mode_manager") and mw._reaction_mode_manager.is_reaction_mode:
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_move(event):
                return
        if (View2D, 'mouseMoveEvent') in _interaction_originals:
            _interaction_originals[(View2D, 'mouseMoveEvent')](view, event)
        else:
            QGraphicsView.mouseMoveEvent(view, event)

    def patched_mouseReleaseEvent(view, event):
        mw = view.window()
        if hasattr(mw, "_reaction_mode_manager") and mw._reaction_mode_manager.is_reaction_mode:
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_release(event):
                return
        
        if (View2D, 'mouseReleaseEvent') in _interaction_originals:
            _interaction_originals[(View2D, 'mouseReleaseEvent')](view, event)
        else:
            QGraphicsView.mouseReleaseEvent(view, event)

    def patched_mouseDoubleClickEvent(view, event):
        mw = view.window()
        consumed = False
        if hasattr(mw, "_reaction_mode_manager") and mw._reaction_mode_manager.is_reaction_mode:
            handler = mw._reaction_mode_manager.interaction_handler
            if handler and hasattr(handler, "handle_mouse_double_click"):
                if handler.handle_mouse_double_click(event):
                    consumed = True
        
        if not consumed:
             # Important: Pass to original to allow items to receive the event (e.g. Text Edit)
             if (View2D, 'mouseDoubleClickEvent') in _interaction_originals:
                  _interaction_originals[(View2D, 'mouseDoubleClickEvent')](view, event)
             else:
                  QGraphicsView.mouseDoubleClickEvent(view, event)

    def patched_keyPressEvent(view, event):
        mw = view.window()
        if hasattr(mw, "_reaction_mode_manager") and mw._reaction_mode_manager.is_reaction_mode:
            handler = mw._reaction_mode_manager.interaction_handler
            if handler:
                focus_item = view.scene().focusItem()
                is_editing_text = (focus_item and hasattr(focus_item, "toPlainText") and hasattr(focus_item, "create_json_data") and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction))
                
                if is_editing_text:
                    if (View2D, 'keyPressEvent') in _interaction_originals:
                        _interaction_originals[(View2D, 'keyPressEvent')](view, event)
                    event.accept() 
                    return

                if handler.handle_key_press(event):
                    event.accept()
                    return
        
        if (View2D, 'keyPressEvent') in _interaction_originals:
            _interaction_originals[(View2D, 'keyPressEvent')](view, event)


    patch_int(View2D, 'mousePressEvent', patched_mousePressEvent)
    patch_int(View2D, 'mouseMoveEvent', patched_mouseMoveEvent)
    patch_int(View2D, 'mouseReleaseEvent', patched_mouseReleaseEvent)
    patch_int(View2D, 'mouseDoubleClickEvent', patched_mouseDoubleClickEvent)
    patch_int(View2D, 'keyPressEvent', patched_keyPressEvent)


def revert_interaction_patches():
    _revert(_interaction_originals)

def revert_core_patches():
    _revert(_core_originals)

# Additional Imports for Atom Logic
try:
    from modules.constants import ATOM_RADIUS, DESIRED_ATOM_PIXEL_RADIUS, FONT_FAMILY, FONT_WEIGHT_BOLD, CPK_COLORS
except ImportError:
    # Fallback or local definition if module path varies
    ATOM_RADIUS = 20
    DESIRED_ATOM_PIXEL_RADIUS = 15
    FONT_FAMILY = "Arial"
    FONT_WEIGHT_BOLD = 75
    CPK_COLORS = {'Default': QColor("#000000")}

def sip_isdeleted_safe(obj):
    if obj is None: return True
    try:
        import sip
        return sip.isdeleted(obj)
    except: return True

def patched_atom_paint(self, painter, option, widget):
    # Cloned and Modified from AtomItem.paint to support (255,255,255,0) transparency
    
    # Color logic
    color = CPK_COLORS.get(self.symbol, CPK_COLORS.get('DEFAULT', QColor(0,0,0)))
    try:
        if self.scene() and self.scene().views():
            win = self.scene().views()[0].window()
            if win and hasattr(win, 'settings'):
                if self.symbol == 'H' or win.settings.get('atom_use_bond_color_2d', False):
                    bond_col = win.settings.get('bond_color_2d', '#222222')
                    color = QColor(bond_col)
    except Exception: pass

    if self.is_visible:
        painter.setFont(self.font)
        fm = painter.fontMetrics()

        hydrogen_part = ""
        if self.implicit_h_count > 0:
            is_skeletal_carbon = (self.symbol == 'C' and self.charge == 0 and self.radical == 0 and len(self.bonds) > 0)
            if not is_skeletal_carbon:
                hydrogen_part = "H"
                if self.implicit_h_count > 1:
                    subscript_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
                    hydrogen_part += str(self.implicit_h_count).translate(subscript_map)

        flip_text = False
        if hydrogen_part and self.bonds:
            my_pos_x = self.pos().x()
            total_dx = 0.0
            for bond in self.bonds:
                try:
                    other_atom = bond.atom1 if bond.atom2 is self else bond.atom2
                    if not sip_isdeleted_safe(other_atom) and other_atom is not None:
                         other_pos = other_atom.pos()
                         total_dx += (other_pos.x() - my_pos_x)
                except: pass
            if total_dx > 0: flip_text = True

        if flip_text:
            display_text = hydrogen_part + self.symbol
            alignment_flag = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        else:
            display_text = self.symbol + hydrogen_part
            alignment_flag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

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

        # 2. Background Handling (THE FIX)
        if self.scene():
            bg_brush = self.scene().backgroundBrush()
            bg_rect = text_rect.adjusted(-5, -8, 5, 8)
            
            # Check for NoBrush OR Transparent Alpha
            is_transparent_mode = (bg_brush.style() == Qt.BrushStyle.NoBrush) or (bg_brush.color().alpha() == 0)

            # Check if we are drawing to SVG (QPaintEngine.Type.SVG = 14)
            # QSvgGenerator does NOT support PorterDuff composition modes (Clear/Source).
            # If we try, it throws "PorterDuff modes not supported on device"
            # However, paintEngine().type() might not be reliable or available.
            # Safest is to try-except the composition mode call.
            
            should_use_composition = False
            if is_transparent_mode:
                # Try setting composition mode - if it fails (SVG), fallback
                try:
                     # Check type if available to avoid unnecessary exceptions
                     if painter.paintEngine() and painter.paintEngine().type() != QPaintEngine.Type.SVG:
                        painter.save()
                        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                        should_use_composition = True
                except:
                     pass

            if should_use_composition:
                painter.setBrush(QColor(255, 255, 255, 0)) 
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(bg_rect)
                painter.restore()
            else:
                # Fallback for SVG or Opaque Background
                if not is_transparent_mode:
                     painter.setBrush(bg_brush)
                     painter.setPen(Qt.PenStyle.NoPen)
                     painter.drawEllipse(bg_rect)
                elif painter.paintEngine() and painter.paintEngine().type() == QPaintEngine.Type.SVG:
                     # SVG + Transparent Mode requested.
                     # User wants WHITE background for text in SVG to avoid "black" or transparency issues.
                     # Since we can't use CompositionMode_Source to "erase" in SVG easily,
                     # we paint a WHITE circle behind the text to mask bonds.
                     painter.setBrush(QColor(255, 255, 255))
                     painter.setPen(Qt.PenStyle.NoPen)
                     painter.drawEllipse(bg_rect)
                elif painter.paintEngine() and painter.paintEngine().type() == QPaintEngine.Type.SVG:
                     # SVG + Transparent Mode requested.
                     # User wants WHITE background for text in SVG to avoid "black" or transparency issues.
                     # Since we can't use CompositionMode_Source to "erase" in SVG easily,
                     # we paint a WHITE circle behind the text to mask bonds.
                     painter.setBrush(QColor(255, 255, 255))
                     painter.setPen(Qt.PenStyle.NoPen)
                     painter.drawEllipse(bg_rect)
        
        # 3. Draw Text
        painter.setPen(QPen(color))
        painter.drawText(text_rect, int(alignment_flag), display_text)
        
        # Charge/Radical (Simplified for brevity, assuming original logic handles them via update/standard paint)
        # Actually we need them. Let's add basic charge logic.
        if self.charge != 0:
            if self.charge == 1: charge_str = "+"
            elif self.charge == -1: charge_str = "-"
            else: charge_str = f"{abs(self.charge)}{'+' if self.charge>0 else '-'}"
            charge_font = QFont("Arial", 12, QFont.Weight.Bold)
            painter.setFont(charge_font)
            charge_rect = painter.fontMetrics().boundingRect(charge_str)
            if flip_text:
                charge_pos = QPointF(text_rect.left() - charge_rect.width() -2, text_rect.top() + charge_rect.height() - 2)
            else:
                charge_pos = QPointF(text_rect.right() + 2, text_rect.top() + charge_rect.height() - 2)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(charge_pos, charge_str)
        
        # Radical (Basic dots)
        if self.radical > 0:
            painter.setBrush(QBrush(Qt.GlobalColor.black))
            painter.setPen(Qt.PenStyle.NoPen)
            radical_pos_y = text_rect.top() - 5
            c_x = text_rect.center().x()
            if self.radical == 1:
                painter.drawEllipse(QPointF(c_x, radical_pos_y), 3, 3)
            elif self.radical == 2:
                painter.drawEllipse(QPointF(c_x - 5, radical_pos_y), 3, 3)
                painter.drawEllipse(QPointF(c_x + 5, radical_pos_y), 3, 3)


    # Selection Highlight
    if self.has_problem:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 0, 0, 200), 4))
        painter.drawRect(self.boundingRect())
    elif self.isSelected():
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 100, 255), 3))
        painter.drawRect(self.boundingRect())
    if (not self.isSelected()) and getattr(self, 'hovered', False):
        pen = QPen(QColor(144, 238, 144, 200), 3)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawRect(self.boundingRect())


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

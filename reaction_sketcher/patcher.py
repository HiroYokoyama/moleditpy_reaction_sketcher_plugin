#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import types
import copy
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtWidgets import QStyle

# Storage for original methods to allow reverting
_originals = {}

def apply_patches(main_window):
    """Applies all monkey-patches to enable undoable chemical coloring."""
    try:
        from modules.atom_item import AtomItem
        from modules.bond_item import BondItem
        from modules.molecule_scene import MoleculeScene
        from modules.main_window_app_state import MainWindowAppState
        from modules.main_window_edit_actions import MainWindowEditActions
    except ImportError:
        try:
            from moleditpy.modules.atom_item import AtomItem
            from moleditpy.modules.bond_item import BondItem
            from moleditpy.modules.molecule_scene import MoleculeScene
            from moleditpy.modules.main_window_app_state import MainWindowAppState
            from moleditpy.modules.main_window_edit_actions import MainWindowEditActions
        except ImportError:
            return

    # Helper to save and replace
    def patch(cls, name, new_func):
        key = (cls, name)
        if key not in _originals:
            _originals[key] = getattr(cls, name)
            setattr(cls, name, new_func)

    # --- 1. Patch AtomItem.paint ---
    def patched_atom_paint(self, painter, option, widget):
        custom_color = getattr(self, 'pen_color', None)
        if not custom_color:
            return _originals[(AtomItem, 'paint')](self, painter, option, widget)
            
        if not self.is_visible: return

        # Logic consistent with current core atom_item.py
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

        # Background masking
        if self.scene():
            bg_brush = self.scene().backgroundBrush()
            bg_rect = text_rect.adjusted(-5, -8, 5, 8)
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

        # Custom Selection highlighting
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 100, 255), 3))
            painter.drawRect(self.boundingRect())
        elif getattr(self, 'hovered', False):
            painter.setPen(QPen(QColor(144, 238, 144, 200), 3))
            painter.drawRect(self.boundingRect())

        # Draw symbol
        painter.setPen(QPen(custom_color))
        painter.drawText(text_rect, int(alignment_flag), display_text)
        
        # Charge
        if self.charge != 0:
            c_str = "+" if self.charge == 1 else ("-" if self.charge == -1 else f"{abs(self.charge)}{'+' if self.charge > 0 else '-'}")
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            cfm = painter.fontMetrics()
            cr = cfm.boundingRect(c_str)
            if flip_text:
                cp = QPointF(text_rect.left() - cr.width() - 2, text_rect.top() + cr.height() - 2)
            else:
                cp = QPointF(text_rect.right() + 2, text_rect.top() + cr.height() - 2)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(cp, c_str)

        # Radical
        if self.radical > 0:
            painter.setBrush(QBrush(Qt.GlobalColor.black))
            painter.setPen(Qt.PenStyle.NoPen)
            ry = text_rect.top() - 5
            if self.radical == 1:
                painter.drawEllipse(QPointF(text_rect.center().x(), ry), 3, 3)
            elif self.radical == 2:
                painter.drawEllipse(QPointF(text_rect.center().x() - 5, ry), 3, 3)
                painter.drawEllipse(QPointF(text_rect.center().x() + 5, ry), 3, 3)

        painter.restore()

    patch(AtomItem, 'paint', patched_atom_paint)

    # --- 2. Patch BondItem.paint ---
    def patched_bond_paint(self, painter, option, widget):
        custom_color = getattr(self, 'pen_color', None)
        if not custom_color:
            return _originals[(BondItem, 'paint')](self, painter, option, widget)
        try:
            settings = self.scene().views()[0].window().settings
            old = settings.get('bond_color_2d')
            settings['bond_color_2d'] = custom_color.name()
            _originals[(BondItem, 'paint')](self, painter, option, widget)
            if old is not None: settings['bond_color_2d'] = old
            else: settings.pop('bond_color_2d', None)
        except:
            _originals[(BondItem, 'paint')](self, painter, option, widget)

    patch(BondItem, 'paint', patched_bond_paint)
    
    # --- 3. Patch MoleculeScene.delete_items ---
    def patched_delete_items(self, items_to_delete):
        """
        Monkey-patch to avoid global reset when all items are deleted.
        """
        # Call original delete_items
        success = _originals[(MoleculeScene, 'delete_items')](self, items_to_delete)
        return success

    patch(MoleculeScene, 'delete_items', patched_delete_items)

    # --- 4. Patch MainWindowEditActions.clear_all and clear_2d_editor ---
    def patched_clear_all(self):
        # We allow clear_all to proceed as it's usually user-triggered (File > New)
        return _originals[(MainWindowEditActions, 'clear_all')](self)

    patch(MainWindowEditActions, 'clear_all', patched_clear_all)

    def patched_clear_2d_editor(self, push_to_undo=True):
        # Prevent clearing reaction items if they exist and we are just "refreshing"
        # usually because atoms were deleted.
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        rs_items = [it for it in self.scene.items() 
                    if isinstance(it, (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                                       ReactionTextItem, ReactionBracketItem, ReactionCircleItem))]
        
        # If there are reaction items, we should only clear AtomItems and BondItems
        # instead of a total scene.clear().
        if rs_items:
            # Temporarily remove RS items
            for it in rs_items: self.scene.removeItem(it)
            
            # Call original (which calls scene.clear())
            _originals[(MainWindowEditActions, 'clear_2d_editor')](self, push_to_undo=push_to_undo)
            
            # Restore RS items
            for it in rs_items: self.scene.addItem(it)
            
            # Re-ensure MolecularData is fresh for atoms but preserving plugin items logic
            # (MolecularData is mostly for atoms/bonds anyway)
            return
            
        return _originals[(MainWindowEditActions, 'clear_2d_editor')](self, push_to_undo=push_to_undo)

    patch(MainWindowEditActions, 'clear_2d_editor', patched_clear_2d_editor)

    # --- 5. Patch MainWindowEditActions.clean_up_2d_structure (CoG Preservation) ---
    def patched_clean_up_2d_structure(self):
        from rdkit.Chem import AllChem, rdmolops
        self.statusBar().showMessage("Optimizing 2D structure (CoG Preserved)...")
        self.scene.clear_all_problem_flags()
        if not self.data.atoms:
            self.statusBar().showMessage("Error: No atoms to optimize.")
            return

        mol = self.data.to_rdkit_mol()
        if mol is None or mol.GetNumAtoms() == 0:
            self.check_chemistry_problems_fallback()
            return

        try:
            # Calculate original CoG for each fragment
            frags = rdmolops.GetMolFrags(mol, asMols=False, sanitizeFrags=False)
            orig_cogs = {}
            for i, frag_indices in enumerate(frags):
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

            # Compute new coordinates
            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()
            SCALE = 50.0
            
            for i, frag_indices in enumerate(frags):
                if i not in orig_cogs: continue
                # Calculate new CoG for this fragment in RDKit space
                rd_sum_x = 0.0; rd_sum_y = 0.0
                for idx in frag_indices:
                    pos = conf.GetAtomPosition(idx)
                    rd_sum_x += pos.x; rd_sum_y += pos.y
                rd_cog_x = rd_sum_x / len(frag_indices)
                rd_cog_y = rd_sum_y / len(frag_indices)
                
                # Apply new positions relative to fragment CoG
                for idx in frag_indices:
                    rd_atom = mol.GetAtomWithIdx(idx)
                    aid = rd_atom.GetIntProp("_original_atom_id")
                    if aid in self.data.atoms:
                        item = self.data.atoms[aid]['item']
                        rd_pos = conf.GetAtomPosition(idx)
                        # RDKit Y is opposite to Qt Y
                        sx = ((rd_pos.x - rd_cog_x) * SCALE) + orig_cogs[i].x()
                        sy = (-(rd_pos.y - rd_cog_y) * SCALE) + orig_cogs[i].y()
                        new_pos = QPointF(sx, sy)
                        item.setPos(new_pos)
                        self.data.atoms[aid]['pos'] = new_pos

            for bond_data in self.data.bonds.values():
                if bond_data.get('item'):
                    bond_data['item'].update_position()

            self.resolve_overlapping_groups()
            self.update_2d_measurement_labels()
            self.scene.update()
            self.statusBar().showMessage("2D optimization (CoG Preserved) successful.")
            self.push_undo_state()

        except Exception as e:
            self.statusBar().showMessage(f"Error during CoG optimization: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.view_2d.setFocus()

    patch(MainWindowEditActions, 'clean_up_2d_structure', patched_clean_up_2d_structure)

    def patched_get_current_state(self):
        state = _originals[(MainWindowAppState, 'get_current_state')](self)
        
        # Atom and Bond colors
        acols = {str(aid): d['item'].pen_color.name() for aid, d in self.data.atoms.items() if getattr(d['item'], 'pen_color', None)}
        bcols = {f"{k[0]}-{k[1]}": d['item'].pen_color.name() for k, d in self.data.bonds.items() if getattr(d['item'], 'pen_color', None)}
        state['rs_atom_colors'] = acols
        state['rs_bond_colors'] = bcols
        
        # Reaction items
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        rs_items_data = []
        for item in self.scene.items():
            if isinstance(item, (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                                 ReactionTextItem, ReactionBracketItem, ReactionCircleItem)):
                if hasattr(item, "create_json_data"):
                    rs_items_data.append(item.create_json_data())
        state['rs_items'] = rs_items_data
        
        return state

    patch(MainWindowAppState, 'get_current_state', patched_get_current_state)

    def patched_set_state_from_data(self, state_data):
        _originals[(MainWindowAppState, 'set_state_from_data')](self, state_data)
        
        # Restore Atom colors
        acols = state_data.get('rs_atom_colors', {})
        for aid_str, col_name in acols.items():
            aid = int(aid_str) if aid_str.isdigit() else aid_str
            if aid in self.data.atoms:
                self.data.atoms[aid]['item'].pen_color = QColor(col_name)
                self.data.atoms[aid]['item'].update()

        # Restore Bond colors
        bcols = state_data.get('rs_bond_colors', {})
        for k_str, col_name in bcols.items():
            try:
                id1_s, id2_s = k_str.split("-")
                id1 = int(id1_s) if id1_s.isdigit() else id1_s
                id2 = int(id2_s) if id2_s.isdigit() else id2_s
                k = (id1, id2)
                if k in self.data.bonds:
                    self.data.bonds[k]['item'].pen_color = QColor(col_name)
                    self.data.bonds[k]['item'].update()
            except: continue

        # Restore Reaction items
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        # Remove existing reaction items from scene only
        for item in list(self.scene.items()):
            if isinstance(item, (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                                 ReactionTextItem, ReactionBracketItem, ReactionCircleItem)):
                self.scene.removeItem(item)

        # Load from state
        if 'rs_items' in state_data:
            from . import load_handler_core
            load_handler_core(self, state_data['rs_items'])

    patch(MainWindowAppState, 'set_state_from_data', patched_set_state_from_data)

    def patched_push_undo_state(self):
        if getattr(self, '_is_restoring_state', False): return

        # Get current state properties for comparison
        curr_state = self.get_current_state()
        
        # Build comparison dict consistent with core logic but adding plugin properties
        current_comp = {
            'atoms': {k: (v['symbol'], v['item'].pos().x(), v['item'].pos().y(), v.get('charge', 0), v.get('radical', 0), 
                          getattr(v['item'], 'pen_color', QColor()).name()) for k, v in self.data.atoms.items()},
            'bonds': {k: (v['order'], v.get('stereo', 0), 
                          getattr(v['item'], 'pen_color', QColor()).name()) for k, v in self.data.bonds.items()},
            '_next_atom_id': self.data._next_atom_id,
            'mol_3d': self.current_mol.ToBinary() if self.current_mol else None,
            'mol_3d_atom_ids': curr_state.get('mol_3d_atom_ids', []),
            'rs_items': curr_state.get('rs_items', [])
        }
        
        last_comp = None
        if self.undo_stack:
            last_state = self.undo_stack[-1]
            last_atoms = last_state.get('atoms', {})
            last_bonds = last_state.get('bonds', {})
            last_acols = last_state.get('rs_atom_colors', {})
            last_bcols = last_state.get('rs_bond_colors', {})
            
            last_comp = {
                'atoms': {k: (v['symbol'], v['pos'][0], v['pos'][1], v.get('charge', 0), v.get('radical', 0),
                              last_acols.get(str(k), "")) for k, v in last_atoms.items()},
                'bonds': {k: (v['order'], v.get('stereo', 0),
                              last_bcols.get(f"{k[0]}-{k[1]}", "")) for k, v in last_bonds.items()},
                '_next_atom_id': last_state.get('_next_atom_id'),
                'mol_3d': last_state.get('mol_3d', None),
                'mol_3d_atom_ids': last_state.get('mol_3d_atom_ids', []),
                'rs_items': last_state.get('rs_items', [])
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

    patch(MainWindowAppState, 'push_undo_state', patched_push_undo_state)

def revert_patches():
    """Removes all monkey-patches and restores original functionality."""
    for (cls, name), original in _originals.items():
        setattr(cls, name, original)
    _originals.clear()

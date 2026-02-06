#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import types
import copy
from PyQt6.QtGui import QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtWidgets import QStyle

# Storage for original methods to allow reverting
_originals = {}

def apply_patches(main_window):
    """Applies all monkey-patches to enable undoable chemical coloring."""
    try:
        from modules.atom_item import AtomItem
        from modules.bond_item import BondItem
        from modules.main_window_app_state import MainWindowAppState
    except ImportError:
        try:
            from moleditpy.modules.atom_item import AtomItem
            from moleditpy.modules.bond_item import BondItem
            from moleditpy.modules.main_window_app_state import MainWindowAppState
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
        painter.save()
        painter.setFont(self.font)
        fm = painter.fontMetrics()
        
        # Logic consistent with atom_item.py
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
            total_dx = 0.0
            for bond in self.bonds:
                try: total_dx += (bond.atom1.pos().x() if bond.atom2 is self else bond.atom2.pos().x()) - self.pos().x()
                except: continue
            if total_dx > 0: flip_text = True

        display_text = (hydrogen_part + self.symbol) if flip_text else (self.symbol + hydrogen_part)
        alignment_flag = (Qt.AlignmentFlag.AlignRight if flip_text else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter
        
        symbol_rect = fm.boundingRect(self.symbol)
        text_rect = fm.boundingRect(display_text)
        text_rect.adjust(-2, -2, 2, 2)
        
        if not hydrogen_part:
            alignment_flag = Qt.AlignmentFlag.AlignCenter
            text_rect.moveCenter(self.boundingRect().center().toPoint())
        elif flip_text:
            offset_x = int(symbol_rect.width() // 2)
            text_rect.moveTo(offset_x - text_rect.width(), -int(text_rect.height() // 2))
        else:
            offset_x = -int(symbol_rect.width() // 2)
            text_rect.moveTo(offset_x, -int(text_rect.height() // 2))

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(QColor(0, 120, 215, 60), 1))
            painter.setBrush(QBrush(QColor(0, 120, 215, 30)))
            painter.drawEllipse(self.shape().boundingRect().adjusted(2,2,-2,-2))

        painter.setPen(custom_color)
        painter.drawText(text_rect, alignment_flag, display_text)
        
        # Charge
        if self.charge != 0:
            c_str = "+" if self.charge == 1 else ("-" if self.charge == -1 else f"{abs(self.charge)}{'+' if self.charge > 0 else '-'}")
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            cfm = painter.fontMetrics()
            cr = cfm.boundingRect(c_str)
            cp = QPointF(text_rect.left() - cr.width() - 2, text_rect.top()) if flip_text else QPointF(text_rect.right() + 2, text_rect.top())
            painter.drawText(cp, c_str)

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

    def patched_get_current_state(self):
        state = _originals[(MainWindowAppState, 'get_current_state')](self)
        acols = {str(aid): d['item'].pen_color.name() for aid, d in self.data.atoms.items() if getattr(d['item'], 'pen_color', None)}
        bcols = {f"{k[0]}-{k[1]}": d['item'].pen_color.name() for k, d in self.data.bonds.items() if getattr(d['item'], 'pen_color', None)}
        state['rs_colors'] = {'atoms': acols, 'bonds': bcols}
        return state

    def patched_set_state_from_data(self, state_data):
        _originals[(MainWindowAppState, 'set_state_from_data')](self, state_data)
        rs_cols = state_data.get('rs_colors', {})
        for aid_str, col in rs_cols.get('atoms', {}).items():
            if int(aid_str) in self.data.atoms:
                self.data.atoms[int(aid_str)]['item'].pen_color = QColor(col)
                self.data.atoms[int(aid_str)]['item'].update()
        for key, col in rs_cols.get('bonds', {}).items():
            try:
                id1, id2 = map(int, key.split('-'))
                if (id1, id2) in self.data.bonds:
                    self.data.bonds[(id1, id2)]['item'].pen_color = QColor(col)
                    self.data.bonds[(id1, id2)]['item'].update()
            except: pass

    def patched_push_undo_state(self):
        if self._is_restoring_state: return
        
        # Include colors in comparison dict to trigger push on color change
        def get_comp_state():
            return {
                'atoms': {k: (v['symbol'], v['item'].pos().x(), v['item'].pos().y(), v.get('charge', 0), v.get('radical', 0), getattr(v['item'], 'pen_color', None).name() if getattr(v['item'], 'pen_color', None) else None) for k, v in self.data.atoms.items()},
                'bonds': {k: (v['order'], v.get('stereo', 0), getattr(v['item'], 'pen_color', None).name() if getattr(v['item'], 'pen_color', None) else None) for k, v in self.data.bonds.items()},
                '_next_atom_id': self.data._next_atom_id,
                'mol_3d': self.current_mol.ToBinary() if self.current_mol else None,
            }

        curr = get_comp_state()
        last_state = self.undo_stack[-1] if self.undo_stack else None
        last_comp = None
        if last_state:
            rs = last_state.get('rs_colors', {})
            ac, bc = rs.get('atoms', {}), rs.get('bonds', {})
            last_comp = {
                'atoms': {k: (v['symbol'], v['pos'][0], v['pos'][1], v.get('charge', 0), v.get('radical', 0), ac.get(str(k))) for k, v in last_state.get('atoms', {}).items()},
                'bonds': {k: (v['order'], v.get('stereo', 0), bc.get(f"{k[0]}-{k[1]}")) for k, v in last_state.get('bonds', {}).items()},
                '_next_atom_id': last_state.get('_next_atom_id'),
                'mol_3d': last_state.get('mol_3d', None),
            }

        if not last_comp or curr != last_comp:
            self.undo_stack.append(copy.deepcopy(self.get_current_state()))
            self.redo_stack.clear()
            if self.initialization_complete:
                self.has_unsaved_changes = True
                self.update_window_title()
        
        self.update_implicit_hydrogens()
        self.update_realtime_info()
        self.update_undo_redo_actions()

    patch(MainWindowAppState, 'get_current_state', patched_get_current_state)
    patch(MainWindowAppState, 'set_state_from_data', patched_set_state_from_data)
    patch(MainWindowAppState, 'push_undo_state', patched_push_undo_state)

def revert_patches():
    """Removes all monkey-patches and restores original functionality."""
    for (cls, name), original in _originals.items():
        setattr(cls, name, original)
    _originals.clear()

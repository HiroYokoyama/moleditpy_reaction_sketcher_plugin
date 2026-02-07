#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import types
import copy
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QByteArray, QMimeData, QRectF
from PyQt6.QtWidgets import QStyle, QApplication

# Storage for original methods to allow reverting
_originals = {}

def apply_patches(main_window):
    """Applies all monkey-patches to enable undoable chemical coloring."""
    try:
        from modules.atom_item import AtomItem
        from modules.bond_item import BondItem
        from modules.main_window_edit_actions import MainWindowEditActions
        from modules.main_window_ui_manager import MainWindowUiManager
        from modules.constants import CLIPBOARD_MIME_TYPE
        from modules.main_window import MainWindow
        from modules.view_2d import View2D
        from modules.molecule_scene import MoleculeScene
        from modules.main_window_app_state import MainWindowAppState
    except ImportError:
        try:
            from moleditpy.modules.atom_item import AtomItem
            from moleditpy.modules.bond_item import BondItem
            from moleditpy.modules.molecule_scene import MoleculeScene
            from moleditpy.modules.main_window_app_state import MainWindowAppState
            from moleditpy.modules.main_window_edit_actions import MainWindowEditActions
            from moleditpy.modules.main_window_ui_manager import MainWindowUiManager
            from moleditpy.modules.constants import CLIPBOARD_MIME_TYPE
            from moleditpy.modules.main_window import MainWindow
            from moleditpy.modules.view_2d import View2D
        except ImportError:
            return

    # Helper to save and replace
    def patch(cls, name, new_func):
        key = (cls, name)
        if key not in _originals:
            _originals[key] = getattr(cls, name)
            setattr(cls, name, new_func)

    # --- 0. Patch MainWindowUiManager.set_mode ---
    def patched_set_mode(self, mode_str):
        _originals[(MainWindowUiManager, 'set_mode')](self, mode_str)
        
        # Notify Reaction Mode Manager if ACTIVE
        rmm = getattr(self, '_reaction_mode_manager', None)
        if rmm and getattr(rmm, 'is_reaction_mode', False):
            try:
                rmm._handle_main_mode_change(mode_str)
            except Exception:
                pass

    patch(MainWindowUiManager, 'set_mode', patched_set_mode)

    def patched_close_event(self, event):
        orig = _originals.get((MainWindow, 'closeEvent'))
        revert_patches()
        if orig:
            return orig(self, event)
        # Fallback if somehow missing
        from PyQt6.QtWidgets import QMainWindow
        return QMainWindow.closeEvent(self, event)
    
    patch(MainWindow, 'closeEvent', patched_close_event)
    
    # --- 4. Patch View2D Mouse Events ---
    from .interaction import InteractionHandler

    def patched_mousePressEvent(view, event):
        # Access handler via main_window (we need to store it somewhere accessible or pass it)
        # We stored it in main_window.reaction_mode_manager.interaction_handler
        # But here 'view' is View2D, 'view.window()' is MainWindow
        mw = view.window()
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
            handler = mw.reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_press(event):
                return # Handled
        
        # Original behavior
        _originals[(View2D, 'mousePressEvent')](view, event)

    def patched_mouseMoveEvent(view, event):
        mw = view.window()
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
            handler = mw.reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_move(event):
                try: 
                    _originals[(View2D, 'mouseMoveEvent')](view, event)
                except: pass
                return

        _originals[(View2D, 'mouseMoveEvent')](view, event)

    def patched_mouseReleaseEvent(view, event):
        mw = view.window()
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
            handler = mw.reaction_mode_manager.interaction_handler
            if handler and handler.handle_mouse_release(event):
                return # Handled
        
        # Original behavior
        _originals[(View2D, 'mouseReleaseEvent')](view, event)
        
        # Check if we moved any reaction items (Select Mode)
        # InteractionHandler.handle_mouse_press saves 'initial_positions_in_event'
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
             scene = mw.scene
             if hasattr(scene, "initial_positions_in_event") and scene.initial_positions_in_event:
                 from .items import (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                                     ReactionMinusItem, ReactionResonanceArrowItem, 
                                     ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                                     ReactionNoArrowItem, ReactionCurvedArrowItem,
                                     ReactionBracketItem, ReactionCircleItem,
                                     ReactionLineItem, ReactionCurvedLineItem,
                                     ReactionFreehandItem, ReactionDashedArrowItem)
                 
                 reaction_types = (ReactionArrowItem, ReactionPlusItem, ReactionTextItem, 
                                     ReactionMinusItem, ReactionResonanceArrowItem, 
                                     ReactionEquilibriumArrowItem, ReactionRetroArrowItem,
                                     ReactionNoArrowItem, ReactionCurvedArrowItem,
                                     ReactionBracketItem, ReactionCircleItem,
                                     ReactionLineItem, ReactionCurvedLineItem,
                                     ReactionFreehandItem, ReactionDashedArrowItem)
                 
                 moved = False
                 for item in scene.selectedItems():
                     if isinstance(item, reaction_types):
                         if item in scene.initial_positions_in_event:
                             old_pos = scene.initial_positions_in_event[item]
                             if item.pos() != old_pos:
                                 moved = True
                                 break
                 
                 if moved:
                     if hasattr(mw, "push_undo_state"):
                         mw.push_undo_state()
                     # Clear prevents double detection (though mousePress resets it)
                     scene.initial_positions_in_event = {}
        
    def patched_mouseDoubleClickEvent(view, event):
        mw = view.window()
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
            handler = mw.reaction_mode_manager.interaction_handler
            if handler and hasattr(handler, "handle_mouse_double_click"):
                if handler.handle_mouse_double_click(event):
                    return

        # Original behavior (View2D might not have this method, so check original or call super)
        if (View2D, 'mouseDoubleClickEvent') in _originals:
            _originals[(View2D, 'mouseDoubleClickEvent')](view, event)
        else:
            # Fallback to standard QGraphicsView behavior if original didn't exist (unlikely but safe)
            super(View2D, view).mouseDoubleClickEvent(event)

    def patched_keyPressEvent(view, event):
        mw = view.window()
        if hasattr(mw, "reaction_mode_manager") and mw.reaction_mode_manager.is_reaction_mode:
            handler = mw.reaction_mode_manager.interaction_handler
            if handler:
                # Check for Text Edit Mode Suppression FIRST
                focus_item = view.scene().focusItem()
                # Duck typing for ReactionTextItem: has toPlainText and create_json_data
                is_editing_text = (focus_item and 
                                   hasattr(focus_item, "toPlainText") and 
                                   hasattr(focus_item, "create_json_data") and 
                                   (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction))
                
                if is_editing_text:
                    # We are editing text.
                    # 1. Let the item handle the event (call original View event which forwards to Scene->Item)
                    if (View2D, 'keyPressEvent') in _originals:
                        _originals[(View2D, 'keyPressEvent')](view, event)
                    else:
                        super(View2D, view).keyPressEvent(event)
                    
                    # 2. CRITICAL: Consume the event so it does NOT bubble to MainWindow shortcuts
                    event.accept() 
                    return

                # Normal interaction handling (Delete, Space, etc)
                handler_handled = handler.handle_key_press(event)
                if handler_handled:
                    event.accept()
                    return # Handled
        
        # Original behavior - Allow shortcuts to propagate!
        # If we didn't handle it above, we call original view event.
        # But for shortcuts to work, the view must NOT accept the event if it doesn't use it?
        # QGraphicsView keyPressEvent usually consumes arrow keys etc.
        # Main window shortcuts (Ctrl+Z) are usually handled by QAction shortcuts which trigger BEFORE focus widget keyPressEvent if they are WindowShortcut.
        # But Space is often a shortcut.
        
        if (View2D, 'keyPressEvent') in _originals:
            _originals[(View2D, 'keyPressEvent')](view, event)
        else:
            super(View2D, view).keyPressEvent(event)

    patch(View2D, 'mousePressEvent', patched_mousePressEvent)
    patch(View2D, 'mouseMoveEvent', patched_mouseMoveEvent)
    patch(View2D, 'mouseReleaseEvent', patched_mouseReleaseEvent)
    patch(View2D, 'mouseDoubleClickEvent', patched_mouseDoubleClickEvent)
    patch(View2D, 'keyPressEvent', patched_keyPressEvent)

    def patched_copy_selection(self):
        try:
            from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                                ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
            
            selected_atoms = [item for item in self.scene.selectedItems() if hasattr(item, 'atom_id')]
            selected_rs_items_raw = [item for item in self.scene.selectedItems() if hasattr(item, 'create_json_data')]
            
            if not selected_atoms and not selected_rs_items_raw:
                return

            # Combine center calculation
            all_pts = []
            for a in selected_atoms: all_pts.append(a.pos())
            for rs in selected_rs_items_raw: all_pts.append(rs.sceneBoundingRect().center())
            
            center = QPointF(sum(p.x() for p in all_pts)/len(all_pts), sum(p.y() for p in all_pts)/len(all_pts))

            # Molecular part
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

            # Reaction items part
            fragment_rs_items = []
            for item in selected_rs_items_raw:
                if hasattr(item, "create_json_data"):
                    d = item.create_json_data()
                    # Offset calculations
                    if d['type'] in ["arrow", "arrow_res", "arrow_eq", "arrow_retro", "arrow_no", "curved_fish", "curved_double", "arrow_dashed"]:
                        d['start_x'] -= center.x()
                        d['start_y'] -= center.y()
                        d['end_x'] -= center.x()
                        d['end_y'] -= center.y()
                        if "cp_x" in d:
                            d["cp_x"] -= center.x()
                            d["cp_y"] -= center.y()
                    elif d['type'] in ["plus", "minus", "text", "bracket", "circle"]:
                        d['x'] -= center.x()
                        d['y'] -= center.y()
                    fragment_rs_items.append(d)

            # Serialize
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
            print(f"Error during patched copy: {e}")

    patch(MainWindowEditActions, 'copy_selection', patched_copy_selection)

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

            # Atoms/Bonds
            new_atoms = []
            for atom_data in fragment_data.get('atoms', []):
                pos = paste_center_pos + atom_data['rel_pos']
                new_id = self.scene.create_atom(atom_data['symbol'], pos, charge=atom_data.get('charge', 0), radical=atom_data.get('radical', 0))
                item = self.data.atoms[new_id]['item']
                new_atoms.append(item)
                item.setSelected(True)
            for bond_data in fragment_data.get('bonds', []):
                self.scene.create_bond(new_atoms[bond_data['idx1']], new_atoms[bond_data['idx2']], bond_order=bond_data.get('order', 1), bond_stereo=bond_data.get('stereo', 0))

            # Reaction Items
            rs_items_data = fragment_data.get('rs_items', [])
            if rs_items_data:
                for d in rs_items_data:
                    if 'start_x' in d:
                        d['start_x'] += paste_center_pos.x()
                        d['start_y'] += paste_center_pos.y()
                        d['end_x'] += paste_center_pos.x()
                        d['end_y'] += paste_center_pos.y()
                        if "cp_x" in d:
                            d["cp_x"] += paste_center_pos.x()
                            d["cp_y"] += paste_center_pos.y()
                    elif 'x' in d:
                        d['x'] += paste_center_pos.x()
                        d['y'] += paste_center_pos.y()
                
                from .utils import load_handler_core
                load_handler_core(self, rs_items_data)

            self.push_undo_state()
            self.statusBar().showMessage("Pasted selection.")
            if hasattr(self, 'activate_select_mode'):
                self.activate_select_mode()
        except Exception as e:
            print(f"Error during patched paste: {e}")

    patch(MainWindowEditActions, 'paste_from_clipboard', patched_paste_from_clipboard)

    # --- 0.8 Patch MainWindowEditActions.select_all ---
    def patched_select_all(self):
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        for item in self.scene.items():
            if isinstance(item, (AtomItem, BondItem, ReactionArrowItem, ReactionPlusItem, 
                                 ReactionMinusItem, ReactionTextItem, ReactionBracketItem, ReactionCircleItem)):
                item.setSelected(True)

    patch(MainWindowEditActions, 'select_all', patched_select_all)


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
    
    # patcher.py の apply_patches 関数内

    # --- 3. Patch MoleculeScene.delete_items (Deleteキー対応) ---
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
        
        # Expand items_to_delete to include parents of handles
        expanded_items = set(items_to_delete)
        for item in items_to_delete:
            if hasattr(item, "handle_type") and item.parentItem():
                expanded_items.add(item.parentItem())
        
        for item in expanded_items:
            if isinstance(item, (AtomItem, BondItem)):
                core_items.append(item)
            # Duck typing check for reaction items
            elif hasattr(item, "create_json_data"):
                # Avoid duplicates and check if it's still in the list
                if item not in reaction_items:
                    reaction_items.append(item)

        # Remove reaction items manually
        deleted_reaction = False
        for item in reaction_items:
            if item.scene() == self:
                # Defensive: Explicitly remove child handles if any
                if hasattr(item, "childItems"):
                    for child in item.childItems():
                        if hasattr(child, "handle_type") or child.__class__.__name__ == "ReactionHandle":
                            self.removeItem(child)
                self.removeItem(item)
                deleted_reaction = True

        # Delegate core atoms/bonds to original
        # Note: Original method pushes undo. 
        success_core = False
        if core_items:
            success_core = _originals[(MoleculeScene, 'delete_items')](self, core_items)
            
        # If we deleted reaction items BUT NOT core items, we must push undo ourselves.
        if deleted_reaction and not success_core:
            views = self.views()
            if views:
                window = views[0].window()
                if hasattr(window, "push_undo_state"):
                    window.push_undo_state()
            # Fallback: Check if scene's parent (often MainWindow or related) has push_undo_state
            elif hasattr(self, "parent") and hasattr(self.parent(), "push_undo_state"):
                 self.parent().push_undo_state()
            
        return deleted_reaction or success_core

    patch(MoleculeScene, 'delete_items', patched_delete_items)

    # --- 3.5 Patch MoleculeScene.clear (全消去時の保護) ---
    # 【新規追加】原子が0になった時の強制クリアから矢印を守る
    def patched_scene_clear(self):
        from PyQt6.QtWidgets import QGraphicsScene
        
        # 1. リアクションアイテムを一時退避
        items_to_save = []
        for item in self.items():
            # Duck typing: simply check for create_json_data method
            if hasattr(item, "create_json_data"):
                items_to_save.append(item)
        
        for item in items_to_save:
            self.removeItem(item)
            
        # 2. 本来の clear() を実行 (QGraphicsSceneのメソッド)
        QGraphicsScene.clear(self)
        
        # 3. 退避していたアイテムを復帰
        for item in items_to_save:
            self.addItem(item)
            
    # MoleculeSceneにclearメソッドが存在しない場合も考慮してパッチ
    if hasattr(MoleculeScene, 'clear'):
        patch(MoleculeScene, 'clear', patched_scene_clear)
    else:
        setattr(MoleculeScene, 'clear', patched_scene_clear)

    # --- 4. Patch MainWindowEditActions.clear_2d_editor ---
    # 【修正】オブジェクト破棄後の再利用によるクラッシュを防ぐ
    def patched_clear_2d_editor(self, push_to_undo=True):
        from .items import (ReactionArrowItem, ReactionPlusItem, ReactionMinusItem, 
                            ReactionTextItem, ReactionBracketItem, ReactionCircleItem)
        
        # データを退避
        rs_items_data = []
        for it in self.scene.items():
            if hasattr(it, "create_json_data"):
                rs_items_data.append(it.create_json_data())
        
        # 本来のクリア処理（オブジェクトは破棄される）
        _originals[(MainWindowEditActions, 'clear_2d_editor')](self, push_to_undo=push_to_undo)
        
        # データから再生成
        if rs_items_data:
            from .utils import load_handler_core
            load_handler_core(self, rs_items_data)
        return

    patch(MainWindowEditActions, 'clear_2d_editor', patched_clear_2d_editor)

    # --- 5. Patch MainWindowEditActions.clean_up_2d_structure ---
    # 【修正】RDKitがない場合のクラッシュガードを追加
    def patched_clean_up_2d_structure(self):
        try:
            from rdkit.Chem import AllChem, rdmolops
        except ImportError:
            self.statusBar().showMessage("Error: RDKit is required for structure optimization.")
            return

        self.statusBar().showMessage("Optimizing 2D structure (CoG Preserved)...")
        # ... (以下、元のコードのtryの中身をそのまま記述) ...
        # ※以前提示した修正版の中身と同じです
        self.scene.clear_all_problem_flags()
        if not self.data.atoms:
            self.statusBar().showMessage("Error: No atoms to optimize.")
            return

        try:
            mol = self.data.to_rdkit_mol()
            if mol is None or mol.GetNumAtoms() == 0:
                self.check_chemistry_problems_fallback()
                return

            # ... (中略: RDKit処理) ...
            # 元のパッチ内容（CoG計算ロジック）をここに維持してください
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

            AllChem.Compute2DCoords(mol)
            conf = mol.GetConformer()
            SCALE = 50.0
            
            for i, frag_indices in enumerate(frags):
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
            if hasattr(self, 'view_2d') and self.view_2d:
                self.view_2d.setFocus()

    patch(MainWindowEditActions, 'clean_up_2d_structure', patched_clean_up_2d_structure)


    # --- 5. Patch MainWindowEditActions.clean_up_2d_structure ---
    # 【修正】RDKitがない場合のクラッシュ回避を追加
    

    def patched_get_current_state(self):
        state = _originals[(MainWindowAppState, 'get_current_state')](self)
        
        # Atom and Bond colors
        acols = {str(aid): d['item'].pen_color.name() for aid, d in self.data.atoms.items() if getattr(d['item'], 'pen_color', None)}
        bcols = {f"{k[0]}-{k[1]}": d['item'].pen_color.name() for k, d in self.data.bonds.items() if getattr(d['item'], 'pen_color', None)}
        state['rs_atom_colors'] = acols
        state['rs_bond_colors'] = bcols
        
        # Reaction items
        rs_items_data = []
        for item in self.scene.items():
             if hasattr(item, "create_json_data"):
                 rs_items_data.append(item.create_json_data())
        
        # Consistent sorting for Undo state comparison
        rs_items_data.sort(key=lambda x: (x.get('type', ''), x.get('x', x.get('start_x', 0)), x.get('y', x.get('start_y', 0))))
        
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
        # Remove existing reaction items from scene only
        for item in list(self.scene.items()):
            if hasattr(item, "create_json_data"):
                 self.scene.removeItem(item)

        # Load from state
        if 'rs_items' in state_data:
            from .utils import load_handler_core
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

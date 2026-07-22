"""
tests/test_patcher_coverage.py -- coverage-focused tests for reaction_sketcher/patcher.py.

apply_core_patches()/apply_interaction_patches() resolve their target classes by
introspecting a live main_window instance (state_manager, scene, edit_actions_manager,
ui_manager, io_manager classes). We build a small "fake app" class hierarchy in
tests/rs_fakes.py that mimics just enough of the real MoleditPy object graph for
every code path to run for real (no MagicMock stand-ins for the patched logic
itself), then drive the patched methods directly.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF

import reaction_sketcher.patcher as patcher_mod
from reaction_sketcher.patcher import (
    apply_core_patches,
    apply_interaction_patches,
    apply_patches,
    unapply_patches,
    revert_all_patches,
    revert_core_patches,
    revert_interaction_patches,
    _ensure_large_canvas,
    _CANVAS_HALF_EXTENT,
)
from reaction_sketcher.items import ReactionArrowItem, ReactionTextItem

from tests.rs_fakes import (
    FakeMainWindow,
    FakeAtomItem,
    FakeBondItem,
    FakeMoleculeScene,
)


# ---------------------------------------------------------------------------
# Install a fake "modules.main_window_export" package so the (huge) export/
# clipboard patch block in apply_core_patches actually runs instead of being
# skipped (real "modules"/"moleditpy" packages don't exist in this headless
# test env).
# ---------------------------------------------------------------------------


class FakeExportManager:
    pass


if "modules" not in sys.modules:
    sys.modules["modules"] = types.ModuleType("modules")
_export_mod = types.ModuleType("modules.main_window_export")
_export_mod.MainWindowExport = FakeExportManager
sys.modules["modules.main_window_export"] = _export_mod


# ---------------------------------------------------------------------------
# Install a fake "modules.view_2d" module so apply_interaction_patches has a
# View2D class to patch instead of returning early.
# ---------------------------------------------------------------------------


class FakeView2D:
    """Stand-in for View2D -- patched with mouse/key event methods."""

    def window(self):
        return self._window

    def mapToScene(self, pos):
        return self._scene_pos

    def transform(self):
        return MagicMock()

    def scene(self):
        return self._window.scene

    # Pure-Python "original" event handlers -- patch_int() in patcher.py
    # captures these as the pre-patch originals (the isinstance(orig,
    # FunctionType) branch of _call_view_orig), mirroring how a real
    # subclass-defined method would be captured (vs. a C++-inherited one).
    def mousePressEvent(self, event):
        self.orig_mouse_press_called = True

    def mouseMoveEvent(self, event):
        self.orig_mouse_move_called = True

    def mouseReleaseEvent(self, event):
        self.orig_mouse_release_called = True

    def mouseDoubleClickEvent(self, event):
        self.orig_double_click_called = True

    def keyPressEvent(self, event):
        self.orig_key_press_called = True


_view2d_mod = types.ModuleType("modules.view_2d")
_view2d_mod.View2D = FakeView2D
sys.modules["modules.view_2d"] = _view2d_mod


@pytest.fixture(autouse=True)
def _revert_patches_after_test():
    yield
    revert_all_patches()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mw_with_atoms():
    """A FakeMainWindow with one atom + bond already on scene (so patcher.py's
    AtomItem/BondItem class resolution via scene.atom_items/bond_items works)."""
    mw = FakeMainWindow()
    a1 = FakeAtomItem(1, "C")
    a2 = FakeAtomItem(2, "O")
    a1.setPos(QPointF(0, 0))
    a2.setPos(QPointF(10, 0))
    bond = FakeBondItem(a1, a2, order=1)
    mw.scene.addItem(a1)
    mw.scene.addItem(a2)
    mw.scene.addItem(bond)
    mw.scene.atom_items = {1: a1, 2: a2}
    mw.scene.bond_items = {(1, 2): bond}
    mw.scene._next_atom_id = 3
    mw.state_manager.data.atoms = {
        1: {"symbol": "C", "pos": [0, 0], "charge": 0, "radical": 0},
        2: {"symbol": "O", "pos": [10, 0], "charge": 0, "radical": 0},
    }
    mw.state_manager.data.bonds = {(1, 2): {"order": 1, "stereo": 0}}
    mw.state_manager.data.next_atom_id = 3
    return mw, a1, a2, bond


def apply_patches_ctx(mw, context=None):
    apply_core_patches(mw, context=context)
    return mw


# ===========================================================================
# _ensure_large_canvas / _patch / _revert
# ===========================================================================


class TestEnsureLargeCanvas:
    def test_none_scene_noop(self):
        _ensure_large_canvas(None)  # should not raise

    def test_grows_small_rect(self):
        scene = FakeMoleculeScene()
        scene._rect = QRectF(-4000, -4000, 4000, 4000)
        _ensure_large_canvas(scene)
        assert scene._rect.width() >= 2 * _CANVAS_HALF_EXTENT

    def test_grows_to_contain_content(self):
        scene = FakeMoleculeScene()
        atom = FakeAtomItem(1)
        atom.setPos(QPointF(50000, 50000))
        scene.addItem(atom)
        big_rect = QRectF(49000, 49000, 2000, 2000)
        scene.itemsBoundingRect = lambda: big_rect
        _ensure_large_canvas(scene)
        assert scene._rect.right() >= big_rect.right()

    def test_already_large_no_churn(self):
        scene = FakeMoleculeScene()
        huge = QRectF(-50000, -50000, 100000, 100000)
        scene._rect = huge
        _ensure_large_canvas(scene)
        assert scene._rect is huge


class TestApplyPatchesRoundTrip:
    def test_apply_patches_then_unapply(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches(mw)
        assert (mw.edit_actions_manager.__class__, "copy_selection") in (
            patcher_mod._core_originals
        )
        unapply_patches(mw)
        assert patcher_mod._core_originals == {}
        assert patcher_mod._interaction_originals == {}

    def test_apply_core_patches_returns_none_without_scene_or_state(self):
        mw = MagicMock(spec=[])
        # Bare object exposing nothing -- should hit the "return" path silently.
        result = apply_core_patches(mw)
        assert result is None


# ===========================================================================
# set_mode patch
# ===========================================================================


class TestSetModePatch:
    def test_notifies_reaction_mode_manager(self):
        mw, *_ = make_mw_with_atoms()
        rmm = MagicMock()
        mw._reaction_mode_manager = rmm
        apply_patches_ctx(mw)
        mw.ui_manager.set_mode("select")
        rmm._handle_main_mode_change.assert_called_once_with("select")

    def test_no_reaction_mode_manager_ok(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.ui_manager.set_mode("select")  # should not raise
        assert "select" in mw.ui_manager.modes_set

    def test_rmm_handler_exception_silenced(self):
        mw, *_ = make_mw_with_atoms()
        rmm = MagicMock()
        rmm._handle_main_mode_change.side_effect = RuntimeError("boom")
        mw._reaction_mode_manager = rmm
        apply_patches_ctx(mw)
        mw.ui_manager.set_mode("atom")  # should not raise


# ===========================================================================
# selectionChanged wiring + canvas enlargement
# ===========================================================================


class TestSceneWiring:
    def test_selection_changed_connected(self):
        mw, *_ = make_mw_with_atoms()
        rmm = MagicMock()
        rmm._sync_selection_visuals = MagicMock()
        mw._reaction_mode_manager = rmm
        apply_patches_ctx(mw)
        mw.scene.selectionChanged.emit()
        rmm._sync_selection_visuals.assert_called_once()

    def test_canvas_enlarged(self):
        mw, *_ = make_mw_with_atoms()
        mw.scene._rect = QRectF(-4000, -4000, 4000, 4000)
        apply_patches_ctx(mw)
        assert mw.scene._rect.width() >= 2 * _CANVAS_HALF_EXTENT

    def test_update_template_preview_prunes_deleted_and_calls_original(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.scene.update_template_preview("x")
        assert mw.scene.template_preview_updated is True
        # Deleted atoms/bonds get pruned from the dicts.
        assert 1 in mw.scene.atom_items

    def test_update_template_preview_prunes_deleted_items(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6 import sip

        orig = sip.isdeleted
        sip.isdeleted = lambda o: o is a1 or o is bond
        try:
            mw.scene.update_template_preview()
        finally:
            sip.isdeleted = orig
        assert 1 not in mw.scene.atom_items
        assert 2 in mw.scene.atom_items
        assert (1, 2) not in mw.scene.bond_items

    def test_update_template_preview_swallows_deleted_runtime_error(self):
        class _DeletedRaisingScene(FakeMoleculeScene):
            def update_template_preview(self, *a, **k):
                raise RuntimeError("wrapped C/C++ object has been deleted")

        mw, *_ = make_mw_with_atoms()
        mw.scene.__class__ = _DeletedRaisingScene
        apply_patches_ctx(mw)
        mw.scene.update_template_preview()  # should not raise (swallowed)

    def test_update_template_preview_reraises_other_runtime_error(self):
        class _OtherRaisingScene(FakeMoleculeScene):
            def update_template_preview(self, *a, **k):
                raise RuntimeError("some other failure")

        mw, *_ = make_mw_with_atoms()
        mw.scene.__class__ = _OtherRaisingScene
        apply_patches_ctx(mw)
        with pytest.raises(RuntimeError, match="some other failure"):
            mw.scene.update_template_preview()

    def test_compute_manager_patch_refreshes_scene(self):
        from tests.rs_fakes import FakeComputeManager

        mw, *_ = make_mw_with_atoms()
        mw.compute_manager = FakeComputeManager(mw)
        rmm = MagicMock()
        rmm.interaction_handler = MagicMock()
        mw._reaction_mode_manager = rmm
        apply_patches_ctx(mw)
        mw.compute_manager.on_calculation_finished("result")
        assert mw.compute_manager.last_result == "result"

    def test_compute_manager_patch_no_rmm(self):
        from tests.rs_fakes import FakeComputeManager

        mw, *_ = make_mw_with_atoms()
        mw.compute_manager = FakeComputeManager(mw)
        apply_patches_ctx(mw)
        mw.compute_manager.on_calculation_finished("result")  # should not raise


# ===========================================================================
# BondItem.boundingRect / paint, AtomItem.paint, __init__ patches
# ===========================================================================


class TestBondAtomPatches:
    def test_bond_bounding_rect(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        rect = bond.boundingRect()
        assert rect.width() > 0

    def test_bond_bounding_rect_with_settings(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        win = MagicMock()
        win.settings = {
            "bond_spacing_triple_2d": 4.0,
            "bond_spacing_double_2d": 3.0,
            "bond_wedge_width_2d": 7.0,
        }
        view = MagicMock()
        view.window.return_value = win
        mw.scene.views = lambda: [view]
        bond.order = 3
        apply_patches_ctx(mw)
        rect = bond.boundingRect()
        assert rect.width() > 0

    def test_bond_item_init_sets_group_defaults(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1 = FakeAtomItem(10)
        a2 = FakeAtomItem(11)
        new_bond = FakeBondItem(a1, a2)
        assert new_bond.group_id is None
        assert new_bond.is_group_selected is False

    def test_atom_item_init_sets_group_defaults(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        new_atom = FakeAtomItem(99, "N")
        assert new_atom.group_id is None
        assert new_atom.is_group_selected is False

    def test_atom_paint_invisible_with_problem(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.is_visible = False
        a1.has_problem = True
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_invisible_selected(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.is_visible = False
        a1.setSelected(True)
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_invisible_hovered(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.is_visible = False
        a1.hovered = True
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_invisible_plain(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.is_visible = False
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_visible_with_hydrogens_and_charge(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.implicit_h_count = 2
        a1.charge = 1
        a1.radical = 1
        painter = MagicMock()
        a1.paint(painter, MagicMock(), MagicMock())

    def test_atom_paint_flip_text_when_neighbour_left(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.implicit_h_count = 1
        a1.setPos(QPointF(10, 0))
        a2.setPos(QPointF(0, 0))
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_selected_and_has_problem_and_hovered(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        for problem, selected, hovered in [
            (True, False, False),
            (False, True, False),
            (False, False, True),
            (False, False, False),
        ]:
            a1.has_problem = problem
            a1.setSelected(selected)
            a1.hovered = hovered
            a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_custom_pen_color(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtGui import QColor

        a1.pen_color = QColor("red")
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_hydrogen_symbol_uses_bond_color(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.symbol = "H"
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_color_string_override(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.color = "#ff00ff"
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_atom_paint_radical_two(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.radical = 2
        a1.paint(MagicMock(), MagicMock(), MagicMock())

    def test_bond_paint_zero_length_skips(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        bond.get_line_in_local_coords = lambda: type(
            "L", (), {"length": lambda self: 0}
        )()
        bond.paint(MagicMock(), MagicMock(), MagicMock())

    def test_bond_paint_selected(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        bond.setSelected(True)
        bond.paint(MagicMock(), MagicMock(), MagicMock())

    def test_bond_paint_has_problem(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        bond.has_problem = True
        bond.paint(MagicMock(), MagicMock(), MagicMock())


# ===========================================================================
# closeEvent
# ===========================================================================


class TestCloseEvent:
    def test_close_event_accepted_reverts_patches(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        event = MagicMock()
        event.isAccepted.return_value = True
        mw.closeEvent(event)
        assert patcher_mod._core_originals == {}

    def test_close_event_rejected_keeps_patches(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        event = MagicMock()
        event.isAccepted.return_value = False
        mw.closeEvent(event)
        assert patcher_mod._core_originals != {}


# ===========================================================================
# Reaction item axis constraint (itemChange)
# ===========================================================================


class TestAxisConstraint:
    def test_itemchange_shift_locks_axis(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QApplication, QGraphicsItem
        from PyQt6.QtCore import Qt

        item = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        mw.scene.addItem(item)
        mw.scene.initial_positions_in_event = {item: QPointF(0, 0)}
        QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.ShiftModifier
        new_val = item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, QPointF(10, 2)
        )
        assert new_val.y() == 0
        QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.NoModifier

    def test_itemchange_no_shift_passthrough(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QGraphicsItem

        item = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        mw.scene.addItem(item)
        result = item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, QPointF(5, 5)
        )
        assert result.x() == 5


# ===========================================================================
# Copy / Paste selection
# ===========================================================================


class TestCopyPaste:
    def test_copy_selection_nothing_selected(self):
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.copy_selection()
        ctx.show_status_message.assert_not_called()

    def test_copy_selection_atoms_and_items(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        a1.setSelected(True)
        a2.setSelected(True)
        arrow = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        arrow.setSelected(True)
        mw.scene.addItem(arrow)
        mw.edit_actions_manager.copy_selection()
        ctx.show_status_message.assert_called_once()

    def test_copy_selection_error_path(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        a1.setSelected(True)
        a1.pos = MagicMock(side_effect=RuntimeError("deleted"))
        mw.edit_actions_manager.copy_selection()
        ctx.show_status_message.assert_called_once()
        assert "Error" in ctx.show_status_message.call_args[0][0]

    def test_paste_no_clipboard_data(self):
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        from PyQt6.QtWidgets import QApplication

        clip = MagicMock()
        clip.mimeData.return_value = None
        QApplication.clipboard.return_value = clip
        mw.edit_actions_manager.paste_from_clipboard()  # should not raise

    def test_copy_then_paste_round_trip(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        a1.setSelected(True)
        a2.setSelected(True)

        from PyQt6.QtWidgets import QApplication

        # Real stateful QMimeData/clipboard stand-ins -- copy_selection creates
        # its own QMimeData() and hands it to clipboard.setMimeData(); paste
        # reads it back via clipboard.mimeData(). Both must be the SAME
        # object for the round-trip to see real bytes.
        class RealMimeData:
            def __init__(self):
                self._by_format = {}

            def setData(self, fmt, byte_array):
                self._by_format[fmt] = bytes(byte_array)

            def hasFormat(self, fmt):
                return fmt in self._by_format

            def data(self, fmt):
                return self._by_format[fmt]

        holder = {}
        clip = MagicMock()
        clip.setMimeData = lambda m: holder.__setitem__("m", m)
        clip.mimeData = lambda: holder.get("m")
        QApplication.clipboard.return_value = clip

        import reaction_sketcher.patcher as pmod

        real_qmimedata = pmod.QMimeData
        pmod.QMimeData = RealMimeData
        try:
            mw.edit_actions_manager.copy_selection()
        finally:
            pmod.QMimeData = real_qmimedata

        assert "m" in holder  # something was serialized to the clipboard

        view = MagicMock()
        view.mapToScene.return_value = QPointF(100, 100)
        view.mapFromGlobal.return_value = QPointF(0, 0)
        mw.init_manager.view_2d = view

        mw.edit_actions_manager.paste_from_clipboard()
        # 2 new atoms should have been created via scene.create_atom
        assert len(mw.scene.atom_items) >= 4
        ctx.show_status_message.assert_called()

    def test_copy_paste_plus_item_and_freehand(self):
        """Exercise the 'plus/minus/text/bracket/circle/freehand' branch of
        copy_selection's coordinate-shift loop (as opposed to the
        arrow/line branch already covered above), and the matching
        'x'/'points' branch in paste_from_clipboard."""
        from reaction_sketcher.items import ReactionPlusItem, ReactionFreehandItem

        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)

        plus = ReactionPlusItem(QPointF(5, 5))
        plus.setSelected(True)
        mw.scene.addItem(plus)
        freehand = ReactionFreehandItem(QPointF(0, 0))
        freehand.set_points([QPointF(1, 1), QPointF(2, 2)])
        freehand.setSelected(True)
        mw.scene.addItem(freehand)

        class RealMimeData:
            def __init__(self):
                self._by_format = {}

            def setData(self, fmt, byte_array):
                self._by_format[fmt] = bytes(byte_array)

            def hasFormat(self, fmt):
                return fmt in self._by_format

            def data(self, fmt):
                return self._by_format[fmt]

        holder = {}
        from PyQt6.QtWidgets import QApplication

        clip = MagicMock()
        clip.setMimeData = lambda m: holder.__setitem__("m", m)
        clip.mimeData = lambda: holder.get("m")
        QApplication.clipboard.return_value = clip

        import reaction_sketcher.patcher as pmod

        real_qmimedata = pmod.QMimeData
        pmod.QMimeData = RealMimeData
        try:
            mw.edit_actions_manager.copy_selection()
        finally:
            pmod.QMimeData = real_qmimedata

        view = MagicMock()
        view.mapToScene.return_value = QPointF(50, 50)
        view.mapFromGlobal.return_value = QPointF(0, 0)
        mw.init_manager.view_2d = view

        before = len(mw.scene.items())
        mw.edit_actions_manager.paste_from_clipboard()
        assert len(mw.scene.items()) > before

    def test_paste_error_path_reports_status(self):
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        from PyQt6.QtWidgets import QApplication

        clip = MagicMock()
        mime = MagicMock()
        mime.hasFormat.return_value = True
        mime.data.side_effect = RuntimeError("boom")
        clip.mimeData.return_value = mime
        QApplication.clipboard.return_value = clip
        mw.edit_actions_manager.paste_from_clipboard()
        ctx.show_status_message.assert_called_once()
        assert "Error" in ctx.show_status_message.call_args[0][0]


# ===========================================================================
# save_project / save_project_as
# ===========================================================================


class TestSaveProject:
    def test_save_project_nothing_to_save(self):
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.atoms = {}
        apply_patches_ctx(mw)
        mw.io_manager.save_project()
        assert "Nothing to save" in mw._status_messages[-1]

    def test_save_project_pmeprj(self, tmp_path):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        f = tmp_path / "proj.pmeprj"
        mw.init_manager.current_file_path = str(f)
        mw.io_manager.save_project()
        assert f.exists()

    def test_save_project_pmeraw(self, tmp_path):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        f = tmp_path / "proj.pmeraw"
        mw.init_manager.current_file_path = str(f)
        mw.io_manager.save_project()
        assert f.exists()

    def test_save_project_no_current_path_delegates_to_save_as(self, tmp_path):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.init_manager.current_file_path = None
        from PyQt6.QtWidgets import QFileDialog

        f = tmp_path / "new.pmeprj"
        QFileDialog.getSaveFileName.return_value = (str(f), "")
        mw.io_manager.save_project()
        assert f.exists()

    def test_save_project_as_nothing_to_save(self):
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.atoms = {}
        apply_patches_ctx(mw)
        mw.io_manager.save_project_as()
        assert "Nothing to save" in mw._status_messages[-1]

    def test_save_project_as_cancelled(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mw.io_manager.save_project_as()  # should not raise

    def test_save_project_as_appends_extension(self, tmp_path):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QFileDialog

        f = tmp_path / "noext"
        QFileDialog.getSaveFileName.return_value = (str(f), "")
        mw.io_manager.save_project_as()
        assert (tmp_path / "noext.pmeprj").exists()

    def test_save_project_io_error(self, tmp_path, monkeypatch):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        f = tmp_path / "proj.pmeprj"
        mw.init_manager.current_file_path = str(f)

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", boom)
        mw.io_manager.save_project()
        assert any("File I/O error" in m for m in mw._status_messages)

    def test_saveable_content_via_3d_mol(self):
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.atoms = {}
        mw.view_3d_manager.current_mol = object()
        apply_patches_ctx(mw)
        mw.io_manager.save_project_as()  # proceeds past "nothing to save" (dialog cancels)

    def test_saveable_content_via_rs_items(self):
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.atoms = {}
        apply_patches_ctx(mw)
        item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(item)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mw.io_manager.save_project_as()  # cancels but must not report "nothing to save"
        assert "Nothing to save." not in mw._status_messages


# ===========================================================================
# delete_selection / select_all delegation
# ===========================================================================


class TestDeleteSelectAllDelegation:
    def test_delete_selection_no_items(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.edit_actions_manager.delete_selection()  # no-op, no raise

    def test_delete_selection_deletes(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.setSelected(True)
        mw.edit_actions_manager.delete_selection()
        assert a1 not in mw.scene.items()

    def test_mainwindow_delete_selection_delegate(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.setSelected(True)
        mw.delete_selection()
        assert a1 not in mw.scene.items()

    def test_select_all(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.edit_actions_manager.select_all()
        assert a1.isSelected() and a2.isSelected() and bond.isSelected()

    def test_select_all_no_scene(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.scene = None
        mw.edit_actions_manager.select_all()  # should not raise

    def test_mainwindow_select_all_delegate(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.select_all()
        assert a1.isSelected()

    def test_select_all_skips_deleted_items(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6 import sip

        orig = sip.isdeleted
        sip.isdeleted = lambda o: o is a1
        try:
            mw.edit_actions_manager.select_all()
        finally:
            sip.isdeleted = orig
        assert not a1.isSelected()
        assert a2.isSelected()


# ===========================================================================
# delete_items (scene-level, patched)
# ===========================================================================


class TestDeleteItemsScene:
    def test_delete_reaction_item_only(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(item)
        result = mw.scene.delete_items([item])
        assert result is True
        assert item not in mw.scene.items()

    def test_delete_atoms_and_bonds(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        result = mw.scene.delete_items([a1, bond])
        assert result is True

    def test_delete_handle_expands_to_parent(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        parent_item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(parent_item)
        handle = MagicMock()
        handle.handle_type = "resize"
        handle.parentItem.return_value = parent_item
        result = mw.scene.delete_items([handle])
        assert result is True
        assert parent_item not in mw.scene.items()

    def test_delete_reaction_item_with_child_handles(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(item)
        handle = MagicMock()
        handle.handle_type = "resize"
        item.childItems = lambda: [handle]
        result = mw.scene.delete_items([item])
        assert result is True

    def test_delete_nothing_returns_false(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        result = mw.scene.delete_items([])
        assert result is False


# ===========================================================================
# rotate_molecule_2d
# ===========================================================================


class TestRotateMolecule2D:
    def test_rotate_selected_atoms(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        a1.setSelected(True)
        a2.setSelected(True)
        mw.edit_actions_manager.rotate_molecule_2d(90)
        ctx.show_status_message.assert_called_once()

    def test_rotate_nothing_selected_rotates_all(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.rotate_molecule_2d(45)
        ctx.show_status_message.assert_called_once()

    def test_rotate_no_items_at_all(self):
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        # Clear content *after* patching so class resolution (which needs a
        # populated scene.atom_items) already succeeded.
        mw.scene.atom_items = {}
        for it in list(mw.scene.items()):
            mw.scene.removeItem(it)
        mw.edit_actions_manager.rotate_molecule_2d(30)
        ctx.show_status_message.assert_called_once_with("No items to rotate.")

    def test_rotate_reaction_item(self):
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        item = ReactionArrowItem(QPointF(10, 0), QPointF(20, 0))
        item.setSelected(True)
        mw.scene.addItem(item)
        mw.edit_actions_manager.rotate_molecule_2d(90)

    def test_rotate_error_path(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        a1.setSelected(True)
        a1.pos = MagicMock(side_effect=RuntimeError("boom"))
        mw.edit_actions_manager.rotate_molecule_2d(10)
        ctx.show_status_message.assert_called_once()
        assert "Error rotating" in ctx.show_status_message.call_args[0][0]


# ===========================================================================
# MoleculeScene.keyPressEvent
# ===========================================================================


class TestSceneKeyPressEvent:
    def test_passthrough_when_no_view(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.scene.views = lambda: []
        event = MagicMock()
        mw.scene.keyPressEvent(event)  # should not raise

    def test_editing_text_item_delegates_to_base(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        from PyQt6.QtCore import Qt

        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene._focus_item = text_item
        view = MagicMock()
        mw.scene.views = lambda: [view]
        event = MagicMock()
        mw.scene.keyPressEvent(event)  # should not raise (delegates to base)

    def test_non_editing_calls_original(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        view = MagicMock()
        mw.scene.views = lambda: [view]
        event = MagicMock()
        mw.scene.keyPressEvent(event)  # should not raise


# ===========================================================================
# clean_up_2d_structure (RDKit-dependent)
# ===========================================================================


class _FakeRDAtom:
    def __init__(self, atom_id):
        self._atom_id = atom_id

    def HasProp(self, name):
        return name == "_original_atom_id"

    def GetIntProp(self, name):
        return self._atom_id


class _FakePos:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _FakeConformer:
    def __init__(self, positions):
        self._positions = positions

    def GetAtomPosition(self, idx):
        return self._positions[idx]


class _FakeMol:
    def __init__(self, atom_ids, positions):
        self._atom_ids = atom_ids
        self._conf = _FakeConformer(positions)

    def GetNumAtoms(self):
        return len(self._atom_ids)

    def GetAtomWithIdx(self, idx):
        return _FakeRDAtom(self._atom_ids[idx])

    def GetConformer(self):
        return self._conf


def _install_fake_rdkit(frags):
    """Install a minimal rdkit.Chem so `from rdkit.Chem import AllChem, rdmolops`
    succeeds inside patched_clean_up_2d_structure, driving the real function body."""
    rdkit_mod = types.ModuleType("rdkit")
    chem_mod = types.ModuleType("rdkit.Chem")
    allchem_mod = types.ModuleType("rdkit.Chem.AllChem")
    allchem_mod.Compute2DCoords = lambda mol: None
    rdmolops_mod = types.ModuleType("rdkit.Chem.rdmolops")
    rdmolops_mod.GetMolFrags = lambda mol, asMols=False, sanitizeFrags=False: frags
    chem_mod.AllChem = allchem_mod
    chem_mod.rdmolops = rdmolops_mod
    rdkit_mod.Chem = chem_mod
    sys.modules["rdkit"] = rdkit_mod
    sys.modules["rdkit.Chem"] = chem_mod
    sys.modules["rdkit.Chem.AllChem"] = allchem_mod
    sys.modules["rdkit.Chem.rdmolops"] = rdmolops_mod


def _uninstall_fake_rdkit():
    for name in (
        "rdkit",
        "rdkit.Chem",
        "rdkit.Chem.AllChem",
        "rdkit.Chem.rdmolops",
    ):
        sys.modules.pop(name, None)


@pytest.fixture()
def fake_rdkit():
    yield _install_fake_rdkit
    _uninstall_fake_rdkit()


class TestCleanUp2DStructure:
    def test_rdkit_missing_reports_error(self, monkeypatch):
        # Force ImportError regardless of whether rdkit happens to be
        # installed in the local dev environment (CI never has it).
        monkeypatch.setitem(sys.modules, "rdkit", None)
        monkeypatch.delitem(sys.modules, "rdkit.Chem", raising=False)
        mw, *_ = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        ctx.show_status_message.assert_called_once()
        assert "RDKit" in ctx.show_status_message.call_args[0][0]

    def test_no_atoms_reports_error(self, fake_rdkit):
        fake_rdkit([])
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.atoms = {}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        assert any(
            "No atoms" in str(c) for c in ctx.show_status_message.call_args_list
        )

    def test_missing_data_reports_error(self, fake_rdkit):
        fake_rdkit([])
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data = None
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        assert any(
            "Missing molecular data" in str(c)
            for c in ctx.show_status_message.call_args_list
        )

    def test_mol_none_checks_chemistry_problems(self, fake_rdkit):
        fake_rdkit([(0, 1)])
        mw, *_ = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: None
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        ctx.check_chemistry_problems.assert_called_once()

    def test_full_success_path_all_fragments(self, fake_rdkit):
        positions = [_FakePos(0.0, 0.0), _FakePos(1.0, 0.0)]
        mol = _FakeMol([1, 2], positions)
        fake_rdkit([(0, 1)])
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: mol
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        ctx.refresh_2d_scene.assert_called_once()
        assert mw.edit_actions_manager.overlap_resolved is True

    def test_success_path_with_selected_subset(self, fake_rdkit):
        positions = [_FakePos(0.0, 0.0), _FakePos(1.0, 0.0)]
        mol = _FakeMol([1, 2], positions)
        fake_rdkit([(0, 1)])
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: mol
        a1.setSelected(True)
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        assert any(
            "selected fragment" in str(c)
            for c in ctx.show_status_message.call_args_list
        )

    def test_success_path_via_selected_bond(self, fake_rdkit):
        positions = [_FakePos(0.0, 0.0), _FakePos(1.0, 0.0)]
        mol = _FakeMol([1, 2], positions)
        fake_rdkit([(0, 1)])
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: mol
        bond.setSelected(True)
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()

    def test_no_valid_frag_indices(self, fake_rdkit):
        positions = [_FakePos(0.0, 0.0), _FakePos(1.0, 0.0)]
        mol = _FakeMol([1, 2], positions)
        fake_rdkit([])  # no fragments at all
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: mol
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        assert any(
            "No valid atoms" in str(c)
            for c in ctx.show_status_message.call_args_list
        )

    def test_success_path_updates_3d_labels(self, fake_rdkit):
        positions = [_FakePos(0.0, 0.0), _FakePos(1.0, 0.0)]
        mol = _FakeMol([1, 2], positions)
        fake_rdkit([(0, 1)])
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.state_manager.data.to_rdkit_mol = lambda: mol
        mw.edit_3d_manager = MagicMock()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.clean_up_2d_structure()
        mw.edit_3d_manager.update_2d_measurement_labels.assert_called_once()


# ===========================================================================
# get_current_state / set_state_from_data / push_undo_state
# ===========================================================================


class TestStateManagement:
    def test_get_current_state_includes_groups_and_items(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        a1.group_id = "g1"
        bond.group_id = "g1"
        item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(item)
        state = mw.state_manager.get_current_state()
        assert state["rs_atom_groups"]["1"] == "g1"
        assert "rs_items" in state

    def test_get_current_state_no_scene(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.scene = None
        with pytest.raises(AttributeError):
            # rs_items loop unconditionally does self.host.scene.items()
            mw.state_manager.get_current_state()

    def test_set_state_from_data_restores_groups(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.state_manager.set_state_from_data(
            {
                "rs_atom_groups": {"1": "g9"},
                "rs_bond_groups": {"1-2": "g9"},
                "rs_items": [],
            }
        )
        assert a1.group_id == "g9"
        assert bond.group_id == "g9"

    def test_set_state_from_data_removes_old_reaction_items(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        item = ReactionArrowItem(QPointF(0, 0), QPointF(1, 1))
        mw.scene.addItem(item)
        mw.state_manager.set_state_from_data({"rs_items": []})
        assert item not in mw.scene.items()

    def test_set_state_from_data_bad_bond_key_ignored(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.state_manager.set_state_from_data(
            {"rs_bond_groups": {"bad-key-format-x": "g1"}}
        )  # should not raise

    def test_push_undo_state_records_snapshot(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 1
        ctx.mark_project_modified.assert_called_once()

    def test_push_undo_state_dedups_identical(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.push_undo_state()
        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 1

    def test_push_undo_state_no_context_sets_unsaved(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw, context=None)
        mw.edit_actions_manager.push_undo_state()
        assert mw.state_manager.has_unsaved_changes is True

    def test_push_undo_state_restoring_state_skips(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw.edit_actions_manager._is_restoring_state = True
        mw.edit_actions_manager.push_undo_state()
        assert mw.edit_actions_manager.undo_stack == []

    def test_push_undo_state_host_restoring_state_skips(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        mw._is_restoring_state = True
        mw.edit_actions_manager.push_undo_state()
        assert mw.edit_actions_manager.undo_stack == []

    def test_push_undo_state_missing_helpers_logs_warning(self, caplog):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        # Shadow the class-level methods with None on the instance so
        # getattr(..., None) sees them as "missing" (hits the warning path).
        mw.edit_actions_manager.update_implicit_hydrogens = None
        mw.edit_actions_manager.update_undo_redo_actions = None
        mw.state_manager.update_realtime_info = None
        mw.edit_actions_manager.push_undo_state()  # should not raise

    def test_push_undo_state_no_get_current_state_no_data_returns(self):
        mw, *_ = make_mw_with_atoms()
        apply_patches_ctx(mw)
        bare = object()
        # Wrap in a namespace with a `.host` but nothing else useful.
        mw.edit_actions_manager.get_current_state = None
        mw.edit_actions_manager.host = MagicMock(spec=[])
        mw.edit_actions_manager.push_undo_state()  # should not raise (early return)

    def test_push_undo_state_with_3d_mol(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        apply_patches_ctx(mw)
        fake_mol = MagicMock()
        fake_mol.ToBinary.return_value = b"abc"
        mw.view_3d_manager.current_mol = fake_mol
        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 1


# ===========================================================================
# Export / clipboard (MainWindowExport patches)
# ===========================================================================


class TestExportPatches:
    def _mw_with_export(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        mw.export_manager = FakeExportManager()
        mw.export_manager.host = mw
        return mw, a1, a2, bond

    def test_export_2d_png_nothing_to_export(self):
        mw, *_ = self._mw_with_export()
        mw.state_manager.data.atoms = {}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.export_manager.export_2d_png()
        ctx.show_status_message.assert_called_once_with("Nothing to export.")

    def test_export_2d_png_cancelled_dialog(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mw.export_manager.export_2d_png()  # should not raise

    def test_export_2d_png_success(self, tmp_path):
        mw, *_ = self._mw_with_export()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        f = tmp_path / "out.png"
        QFileDialog.getSaveFileName.return_value = (str(f), "")
        QMessageBox.question.return_value = QMessageBox.StandardButton.Yes
        QMessageBox.StandardButton = QMessageBox.StandardButton
        mw.export_manager.export_2d_png()

    def test_export_2d_png_cancel_background_choice(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        QFileDialog.getSaveFileName.return_value = ("out.png", "")
        QMessageBox.question.return_value = QMessageBox.StandardButton.Cancel
        mw.export_manager.export_2d_png()  # should not raise

    def test_copy_to_clipboard_nothing(self):
        mw, *_ = self._mw_with_export()
        mw.state_manager.data.atoms = {}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.export_manager.copy_to_clipboard()
        ctx.show_status_message.assert_called_once_with("Nothing to copy.")

    def test_copy_to_clipboard_success(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        mw.export_manager.copy_to_clipboard()  # should not raise

    def test_export_2d_svg_missing_generator(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        orig = patcher_mod.QSvgGenerator
        patcher_mod.QSvgGenerator = None
        try:
            ctx_calls = []
            mw.export_manager.export_2d_svg()
        finally:
            patcher_mod.QSvgGenerator = orig

    def test_export_2d_svg_nothing_to_export(self):
        mw, *_ = self._mw_with_export()
        mw.state_manager.data.atoms = {}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.export_manager.export_2d_svg()
        ctx.show_status_message.assert_called_once_with("Nothing to export.")

    def test_export_2d_svg_cancelled(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mw.export_manager.export_2d_svg()

    def test_export_2d_svg_success(self, tmp_path):
        mw, a1, a2, bond = self._mw_with_export()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        f = tmp_path / "out.svg"
        QFileDialog.getSaveFileName.return_value = (str(f), "")
        QMessageBox.question.return_value = QMessageBox.StandardButton.Yes
        mw.export_manager.export_2d_svg()

    def test_export_2d_svg_no_bounds(self):
        mw, *_ = self._mw_with_export()
        # Remove all items from scene so molecule_bounds is empty
        for it in list(mw.scene.items()):
            mw.scene.removeItem(it)
        mw.state_manager.data.atoms = {1: {"symbol": "C", "pos": [0, 0]}}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        QFileDialog.getSaveFileName.return_value = ("out.svg", "")
        QMessageBox.question.return_value = QMessageBox.StandardButton.Yes
        mw.export_manager.export_2d_svg()
        assert any(
            "Could not determine molecule bounds" in str(c)
            for c in ctx.show_status_message.call_args_list
        )

    def test_copy_svg_to_clipboard_missing_generator(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        orig = patcher_mod.QSvgGenerator
        patcher_mod.QSvgGenerator = None
        try:
            mw.export_manager.copy_svg_to_clipboard()
        finally:
            patcher_mod.QSvgGenerator = orig

    def test_copy_svg_to_clipboard_nothing(self):
        mw, *_ = self._mw_with_export()
        mw.state_manager.data.atoms = {}
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.export_manager.copy_svg_to_clipboard()
        ctx.show_status_message.assert_called_once_with("Nothing to copy.")

    def test_copy_svg_to_clipboard_success(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        mw.export_manager.copy_svg_to_clipboard()

    def test_copy_2d_image_to_clipboard_via_edit_actions(self):
        mw, *_ = self._mw_with_export()
        ctx = MagicMock()
        apply_patches_ctx(mw, ctx)
        mw.edit_actions_manager.copy_2d_image_to_clipboard()

    def test_mainwindow_copy_2d_image_delegate(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        mw.copy_2d_image_to_clipboard()

    def test_setup_copy_shortcut_creates_action_once(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        assert mw.copy_2d_action is not None
        first_action = mw.copy_2d_action
        # Re-applying (idempotent-ish call) should not duplicate since guard checks None
        patcher_mod._patch(
            patcher_mod._core_originals, mw.__class__, "_noop_marker", lambda self: None
        )
        assert mw.copy_2d_action is first_action

    def test_mainwindow_forward_copy_clip(self):
        mw, *_ = self._mw_with_export()
        apply_patches_ctx(mw)
        mw.copy_to_clipboard()  # should not raise


# ===========================================================================
# apply_interaction_patches
# ===========================================================================


class TestInteractionPatchesInstalled:
    def _view_and_mw(self):
        mw, a1, a2, bond = make_mw_with_atoms()
        view = FakeView2D()
        view._window = mw
        view._scene_pos = QPointF(1, 1)
        return mw, view, a1, a2, bond

    def test_reverts_cleanly(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        assert (view.__class__, "mousePressEvent") in patcher_mod._interaction_originals
        revert_interaction_patches()
        assert patcher_mod._interaction_originals == {}

    def test_mouse_press_delegates_to_handler(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        handler.handle_mouse_press.return_value = True
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        event = MagicMock()
        view.mousePressEvent(event)
        handler.handle_mouse_press.assert_called_once_with(event)

    def test_mouse_press_not_reaction_mode_calls_super(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = False
        mw._reaction_mode_manager = rmm
        event = MagicMock()
        view.mousePressEvent(event)  # falls through to QGraphicsView.mousePressEvent

    def test_mouse_move_delegates(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        handler.handle_mouse_move.return_value = True
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        view.mouseMoveEvent(MagicMock())
        handler.handle_mouse_move.assert_called_once()

    def test_mouse_release_delegates(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        handler.handle_mouse_release.return_value = True
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        view.mouseReleaseEvent(MagicMock())
        handler.handle_mouse_release.assert_called_once()

    def test_double_click_atom_selects_molecule(self):
        mw, view, a1, a2, bond = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        mw._reaction_mode_manager = rmm
        mw.scene._item_at = a1
        event = MagicMock()
        event.pos.return_value = QPointF(0, 0)
        view.mouseDoubleClickEvent(event)
        assert a1.isSelected() and a2.isSelected()

    def test_double_click_delegates_to_handler_for_non_atom(self):
        mw, view, a1, a2, bond = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        handler.handle_mouse_double_click.return_value = True
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        mw.scene._item_at = None
        event = MagicMock()
        event.pos.return_value = QPointF(0, 0)
        view.mouseDoubleClickEvent(event)
        handler.handle_mouse_double_click.assert_called_once()

    def test_key_press_text_edit_passthrough(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        from PyQt6.QtCore import Qt

        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene._focus_item = text_item
        event = MagicMock()
        view.keyPressEvent(event)
        handler.handle_key_press.assert_not_called()

    def test_key_press_handled_by_handler(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = True
        handler = MagicMock()
        handler.handle_key_press.return_value = True
        rmm.interaction_handler = handler
        mw._reaction_mode_manager = rmm
        event = MagicMock()
        view.keyPressEvent(event)
        event.accept.assert_called_once()

    def test_key_press_not_reaction_mode(self):
        mw, view, *_ = self._view_and_mw()
        apply_interaction_patches(mw)
        rmm = MagicMock()
        rmm.is_reaction_mode = False
        mw._reaction_mode_manager = rmm
        view.keyPressEvent(MagicMock())  # falls through to QGraphicsView


class TestInteractionPatchesMissingView2D:
    def test_returns_early_without_view2d_module(self):
        saved = sys.modules.pop("modules.view_2d", None)
        try:
            mw, *_ = make_mw_with_atoms()
            apply_interaction_patches(mw)  # should not raise, no-op
        finally:
            if saved is not None:
                sys.modules["modules.view_2d"] = saved

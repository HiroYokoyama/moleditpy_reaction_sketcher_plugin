"""ModeManager.mirror_items: flips the selection about its own centre in place."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF

import reaction_sketcher.patcher as patcher_mod
from reaction_sketcher.items import ReactionArrowItem, ReactionPlusItem
from reaction_sketcher.mode_manager import ModeManager

from tests.rs_fakes import FakeAtomItem, FakeBondItem, FakeMainWindow


@pytest.fixture(autouse=True)
def _revert_patches_after_test():
    yield
    patcher_mod.revert_all_patches()


def _mw_with_molecule():
    mw = FakeMainWindow()
    a1 = FakeAtomItem(1, "C")
    a2 = FakeAtomItem(2, "O")
    a1.setPos(QPointF(0, 0))
    a2.setPos(QPointF(40, 0))
    bond = FakeBondItem(a1, a2, order=1)
    for item in (a1, a2, bond):
        mw.scene.addItem(item)
    mw.scene.atom_items = {1: a1, 2: a2}
    mw.scene.bond_items = {(1, 2): bond}
    mw.state_manager.data.atoms = {
        1: {"symbol": "C", "pos": [0, 0], "charge": 0, "radical": 0},
        2: {"symbol": "O", "pos": [40, 0], "charge": 0, "radical": 0},
    }
    mw.data = mw.state_manager.data
    return mw, a1, a2


class TestMirrorItems:
    def test_nothing_selected_is_a_no_op(self):
        mw, a1, a2 = _mw_with_molecule()
        mm = ModeManager(mw, context=MagicMock())
        mm.mirror_items("v")
        assert a1.pos().x() == pytest.approx(0.0)
        assert mw.edit_actions_manager.push_undo_state_calls == 0

    def test_selected_atoms_swap_around_their_centre(self):
        mw, a1, a2 = _mw_with_molecule()
        mm = ModeManager(mw, context=MagicMock())
        a1.setSelected(True)
        a2.setSelected(True)
        mm.mirror_items("v")
        assert a1.pos().x() == pytest.approx(40.0)
        assert a2.pos().x() == pytest.approx(0.0)
        assert a1.pos().y() == pytest.approx(0.0)

    def test_atom_positions_are_written_back_to_the_data_model(self):
        mw, a1, a2 = _mw_with_molecule()
        mm = ModeManager(mw, context=MagicMock())
        a1.setSelected(True)
        a2.setSelected(True)
        mm.mirror_items("v")
        # Without this the next undo snapshot would restore the old coordinates.
        assert mw.state_manager.data.atoms[1]["pos"] == [40.0, 0.0]
        assert mw.state_manager.data.atoms[2]["pos"] == [0.0, 0.0]

    def test_bonds_and_undo_are_refreshed(self):
        mw, a1, a2 = _mw_with_molecule()
        ctx = MagicMock()
        mm = ModeManager(mw, context=ctx)
        a1.setSelected(True)
        mm.mirror_items("h")
        assert mw.scene.update_connected_bonds_calls
        assert mw.edit_actions_manager.push_undo_state_calls == 1
        ctx.refresh_2d_scene.assert_called()

    def test_reaction_items_flip_in_place(self):
        mw, a1, a2 = _mw_with_molecule()
        mm = ModeManager(mw, context=MagicMock())
        arrow = ReactionArrowItem(QPointF(10, 10), QPointF(60, 10))
        plus = ReactionPlusItem(QPointF(100, 10))
        for item in (arrow, plus):
            mw.scene.addItem(item)
            item.setSelected(True)

        arrow_mid_before = (
            arrow.mapToScene(arrow.start_p).x() + arrow.mapToScene(arrow.end_p).x()
        ) / 2.0
        mm.mirror_items("v")

        # Selection centre = mean of the arrow midpoint (35) and the plus (100).
        center_x = (arrow_mid_before + 100.0) / 2.0
        arrow_mid_after = (
            arrow.mapToScene(arrow.start_p).x() + arrow.mapToScene(arrow.end_p).x()
        ) / 2.0
        assert arrow_mid_after == pytest.approx(2 * center_x - arrow_mid_before)
        assert plus.pos().x() == pytest.approx(2 * center_x - 100.0)
        # The arrow flipped rather than merely moving: its ends swapped.
        assert arrow.mapToScene(arrow.start_p).x() > arrow.mapToScene(arrow.end_p).x()

    def test_no_scene_is_a_no_op(self):
        mw, a1, a2 = _mw_with_molecule()
        mm = ModeManager(mw, context=MagicMock())
        mw.scene = None
        mm.mirror_items("v")  # must not raise

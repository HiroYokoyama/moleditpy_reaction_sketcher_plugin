"""Show C toggle: selection narrowing, persistence, and label geometry.

Pressing Show C with carbons selected must label only those carbons, and the
state has to survive undo/redo (app state) and save/load (project file).
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF

import reaction_sketcher.patcher as patcher_mod
from reaction_sketcher.mode_manager import ModeManager
from reaction_sketcher.utils import is_carbon_shown, show_carbon_state

from tests.rs_fakes import FakeAtomItem, FakeBondItem, FakeMainWindow


def apply_patches_ctx(mw, context=None):
    # Local copy rather than an import of test_patcher_coverage: importing that
    # module under a second name re-runs its module-level fake-class setup and
    # leaves its own tests patching a stale class.
    patcher_mod.apply_core_patches(mw, context=context)
    return mw


@pytest.fixture(autouse=True)
def _revert_patches_after_test():
    # apply_core_patches() rewrites the fake classes process-wide; leaving them
    # patched breaks every later test file.
    yield
    patcher_mod.revert_all_patches()


class _SceneStub:
    def __init__(self, show_all=False, ids=None):
        self._rs_show_carbon = show_all
        self._rs_show_carbon_ids = ids if ids is not None else set()


class _AtomStub:
    def __init__(self, atom_id, symbol, scene):
        self.atom_id = atom_id
        self.symbol = symbol
        self._scene = scene

    def scene(self):
        return self._scene


class TestIsCarbonShown:
    def test_no_scene_is_never_shown(self):
        assert is_carbon_shown(_AtomStub(1, "C", None)) is False
        assert show_carbon_state(None) == (False, frozenset())

    def test_show_all_covers_every_carbon(self):
        scene = _SceneStub(show_all=True)
        assert is_carbon_shown(_AtomStub(1, "C", scene)) is True
        assert is_carbon_shown(_AtomStub(2, "C", scene)) is True

    def test_only_listed_ids_when_narrowed(self):
        scene = _SceneStub(show_all=False, ids={2})
        assert is_carbon_shown(_AtomStub(1, "C", scene)) is False
        assert is_carbon_shown(_AtomStub(2, "C", scene)) is True

    def test_show_all_with_an_exception_hides_that_carbon(self):
        scene = _SceneStub(show_all=True, ids={2})
        assert is_carbon_shown(_AtomStub(2, "C", scene)) is False
        assert is_carbon_shown(_AtomStub(1, "C", scene)) is True

    def test_non_carbon_never_shown(self):
        scene = _SceneStub(show_all=True)
        assert is_carbon_shown(_AtomStub(1, "O", scene)) is False

    def test_deleted_wrapper_is_not_shown(self):
        atom = _AtomStub(1, "C", None)

        def boom():
            raise RuntimeError("wrapped C/C++ object has been deleted")

        atom.scene = boom
        assert is_carbon_shown(atom) is False


class _FakeAction:
    """Checkable QAction stand-in: blockSignals must stop re-entry."""

    def __init__(self, checked=False):
        self._checked = checked
        self._blocked = False
        self.emitted = []

    def isChecked(self):
        return self._checked

    def setChecked(self, value):
        self._checked = bool(value)
        if not self._blocked:
            self.emitted.append(self._checked)

    def blockSignals(self, block):
        was = self._blocked
        self._blocked = bool(block)
        return was


def _mode_manager_with_atoms():
    mw = FakeMainWindow()
    c1 = FakeAtomItem(1, "C")
    c2 = FakeAtomItem(2, "C")
    o3 = FakeAtomItem(3, "O")
    for item in (c1, c2, o3):
        mw.scene.addItem(item)
    mw.scene.atom_items = {1: c1, 2: c2, 3: o3}
    mm = ModeManager(mw, context=MagicMock())
    return mm, mw, c1, c2, o3


class TestToggleShowCarbon:
    def test_nothing_selected_shows_all_carbons(self):
        mm, mw, *_ = _mode_manager_with_atoms()
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon is True
        assert mw.scene._rs_show_carbon_ids == set()

    def test_selected_carbon_narrows_the_toggle(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        c2.setSelected(True)
        o3.setSelected(True)
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon is False
        assert mw.scene._rs_show_carbon_ids == {2}
        assert is_carbon_shown(c2) is True
        assert is_carbon_shown(c1) is False

    def test_selecting_only_a_heteroatom_falls_back_to_all(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        o3.setSelected(True)
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon is True

    def test_toggling_off_clears_both(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        c1.setSelected(True)
        mm.toggle_show_carbon(True)
        mm.toggle_show_carbon(False)
        assert mw.scene._rs_show_carbon is False
        assert mw.scene._rs_show_carbon_ids == set()

    def test_toggle_pushes_an_undo_state(self):
        mm, mw, *_ = _mode_manager_with_atoms()
        mm.toggle_show_carbon(True)
        assert mw.edit_actions_manager.push_undo_state_calls == 1

    def test_apply_state_syncs_the_toolbar_action(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        action = _FakeAction(checked=False)
        mm.show_carbon_action = action
        c2.setSelected(True)
        mm.apply_show_carbon_state(False, [2], sync_action=True)
        assert action.isChecked() is True
        assert action.emitted == []  # syncing must not re-enter the toggle

    def test_restored_narrowing_leaves_the_button_released(self):
        # Loading a project or undoing restores labels with nothing selected.
        mm, mw, *_ = _mode_manager_with_atoms()
        action = _FakeAction(checked=True)
        mm.show_carbon_action = action
        mm.apply_show_carbon_state(False, [2], sync_action=True)
        assert action.isChecked() is False

    def test_adding_a_selection_keeps_the_earlier_labels(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        c2.setSelected(True)
        mm.toggle_show_carbon(True)
        c2.setSelected(False)
        c1.setSelected(True)
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon_ids == {1, 2}
        assert mw.scene._rs_show_carbon is False

    def test_no_scene_is_a_no_op(self):
        mm, mw, *_ = _mode_manager_with_atoms()
        mw.scene = None
        mm.toggle_show_carbon(True)  # must not raise


class _FakeFontMetrics:
    """Qt is stubbed in this suite, so stand in for QFontMetricsF."""

    def __init__(self, font):
        self.font = font

    def horizontalAdvance(self, text):
        return 12.0


class _StyledAtomItem(FakeAtomItem):
    """FakeAtomItem plus the core AtomItem hooks the Show C patches wrap."""

    def update_style(self):
        self.is_visible = not (
            self.symbol == "C"
            and len(self.bonds) > 0
            and self.charge == 0
            and self.radical == 0
        )

    def visual_rect(self):
        return QRectF(-10, -10, 20, 20)


def _mw_with_styled_atoms():
    mw = FakeMainWindow()
    c1 = _StyledAtomItem(1, "C")
    c2 = _StyledAtomItem(2, "C")
    c1.setPos(QPointF(0, 0))
    c2.setPos(QPointF(30, 0))
    bond = FakeBondItem(c1, c2, order=1)
    for item in (c1, c2, bond):
        mw.scene.addItem(item)
    mw.scene.atom_items = {1: c1, 2: c2}
    mw.scene.bond_items = {(1, 2): bond}
    mw.state_manager.data.atoms = {
        1: {"symbol": "C", "pos": [0, 0], "charge": 0, "radical": 0},
        2: {"symbol": "C", "pos": [30, 0], "charge": 0, "radical": 0},
    }
    mw.state_manager.data.bonds = {(1, 2): {"order": 1, "stereo": 0}}
    return mw, c1, c2


class TestShowCarbonTouchesOnlyTheSelection:
    """With carbons selected the button changes those carbons and no others."""

    def _show_all(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        action = _FakeAction()
        mm.show_carbon_action = action
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon is True
        return mm, mw, c1, c2, o3, action

    def test_pressing_with_a_selection_hides_only_that_carbon(self):
        mm, mw, c1, c2, o3, action = self._show_all()
        c2.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is True  # the selected carbon is labelled

        mm.toggle_show_carbon(False)

        assert mw.scene._rs_show_carbon is True  # the rest keep their labels
        assert mw.scene._rs_show_carbon_ids == {2}
        assert is_carbon_shown(c2) is False
        assert is_carbon_shown(c1) is True
        assert action.isChecked() is False

    def test_button_reads_the_first_selected_carbon(self):
        # Bold/Italic/Underline read the first selected item; so does this.
        mm, mw, c1, c2, o3, action = self._show_all()
        c2.setSelected(True)
        mm.toggle_show_carbon(False)  # C2 hidden, C1 still labelled
        c2.setSelected(False)
        c1.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is True

    def test_pressing_flips_every_selected_carbon(self):
        mm, mw, c1, c2, o3, action = self._show_all()
        c1.setSelected(True)
        c2.setSelected(True)
        mm.toggle_show_carbon(False)
        assert mw.scene._rs_show_carbon_ids == {1, 2}
        assert is_carbon_shown(c1) is False
        assert is_carbon_shown(c2) is False

    def test_pressing_again_brings_the_label_back(self):
        mm, mw, c1, c2, o3, action = self._show_all()
        c2.setSelected(True)
        mm.toggle_show_carbon(False)
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon_ids == set()
        assert is_carbon_shown(c2) is True

    def test_clearing_the_selection_still_covers_everything(self):
        mm, mw, c1, c2, o3, action = self._show_all()
        c2.setSelected(True)
        mm.toggle_show_carbon(False)
        c2.setSelected(False)
        mm.toggle_show_carbon(False)  # nothing selected: scene-wide off
        assert mw.scene._rs_show_carbon is False
        assert mw.scene._rs_show_carbon_ids == set()
        assert is_carbon_shown(c1) is False

    def test_hiding_a_labelled_carbon_while_off(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        mm.show_carbon_action = _FakeAction()
        c2.setSelected(True)
        mm.toggle_show_carbon(True)
        assert mw.scene._rs_show_carbon_ids == {2}
        mm.toggle_show_carbon(False)
        assert mw.scene._rs_show_carbon is False
        assert mw.scene._rs_show_carbon_ids == set()
        assert is_carbon_shown(c2) is False


class TestShowCarbonButtonFollowsSelection:
    """Deselecting releases the button but keeps the labels."""

    def _narrowed(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        action = _FakeAction()
        mm.show_carbon_action = action
        c2.setSelected(True)
        mm.toggle_show_carbon(True)
        assert action.isChecked() is True
        return mm, mw, c1, c2, o3, action

    def test_deselecting_keeps_the_labels(self):
        mm, mw, c1, c2, o3, action = self._narrowed()
        c2.setSelected(False)
        mm.sync_show_carbon_to_selection()
        assert mw.scene._rs_show_carbon_ids == {2}
        assert is_carbon_shown(c2) is True

    def test_deselecting_releases_the_button(self):
        mm, mw, c1, c2, o3, action = self._narrowed()
        c2.setSelected(False)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is False
        assert action.emitted == []

    def test_selecting_an_unlabelled_carbon_leaves_it_released(self):
        # The next press must add C1, not switch everything off.
        mm, mw, c1, c2, o3, action = self._narrowed()
        c2.setSelected(False)
        c1.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is False

    def test_reselecting_a_labelled_carbon_presses_it_again(self):
        mm, mw, c1, c2, o3, action = self._narrowed()
        c2.setSelected(False)
        mm.sync_show_carbon_to_selection()
        c2.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is True
        # ...so that this press clears the labels.
        mm.toggle_show_carbon(False)
        assert mw.scene._rs_show_carbon_ids == set()

    def test_show_all_stays_pressed_whatever_is_selected(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        action = _FakeAction()
        mm.show_carbon_action = action
        mm.toggle_show_carbon(True)
        for selected in (True, False):
            c1.setSelected(selected)
            mm.sync_show_carbon_to_selection()
            assert action.isChecked() is True

    def test_selecting_a_heteroatom_releases_the_button(self):
        mm, mw, c1, c2, o3, action = self._narrowed()
        c2.setSelected(False)
        o3.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is False
        assert mw.scene._rs_show_carbon_ids == {2}

    def test_following_does_not_repaint_or_push_undo(self):
        mm, mw, c1, c2, o3, action = self._narrowed()
        mm.refresh_carbon_labels = MagicMock()
        c2.setSelected(False)
        mm.sync_show_carbon_to_selection()
        mm.refresh_carbon_labels.assert_not_called()
        assert mw.edit_actions_manager.push_undo_state_calls == 1

    def test_no_action_yet_is_a_no_op(self):
        mm, mw, c1, *_ = _mode_manager_with_atoms()
        mm.show_carbon_action = None
        mm.sync_show_carbon_to_selection()  # must not raise

    def test_off_state_keeps_the_button_released(self):
        mm, mw, c1, c2, o3 = _mode_manager_with_atoms()
        action = _FakeAction(checked=True)
        mm.show_carbon_action = action
        c1.setSelected(True)
        mm.sync_show_carbon_to_selection()
        assert action.isChecked() is False


class TestShowCarbonPatches:
    def test_update_style_keeps_shown_carbon_visible(self):
        mw, c1, c2 = _mw_with_styled_atoms()
        apply_patches_ctx(mw)
        c1.update_style()
        assert c1.is_visible is False  # bonded skeletal carbon, stock behaviour

        mw.scene._rs_show_carbon_ids = {1}
        c1.update_style()
        c2.update_style()
        assert c1.is_visible is True
        assert c2.is_visible is False

    def test_visual_rect_grows_for_the_implicit_h_label(self, monkeypatch):
        monkeypatch.setattr(patcher_mod, "QFontMetricsF", _FakeFontMetrics)
        mw, c1, c2 = _mw_with_styled_atoms()
        apply_patches_ctx(mw)
        stock = c1.visual_rect()

        c1.implicit_h_count = 3
        mw.scene._rs_show_carbon = True
        grown = c1.visual_rect()
        # c1's neighbour is to its right, so paint() writes "H₃C" and the
        # label grows to the left.
        assert grown.left() == pytest.approx(stock.left() - 12.0)
        assert grown.right() == pytest.approx(stock.right())
        assert grown.top() == pytest.approx(stock.top())

        # c2's neighbour is to its left, so it reads "CH₃" and grows right.
        c2.implicit_h_count = 3
        grown2 = c2.visual_rect()
        assert grown2.right() == pytest.approx(stock.right() + 12.0)
        assert grown2.left() == pytest.approx(stock.left())

    def test_visual_rect_untouched_for_hidden_carbon(self, monkeypatch):
        monkeypatch.setattr(patcher_mod, "QFontMetricsF", _FakeFontMetrics)
        mw, c1, c2 = _mw_with_styled_atoms()
        apply_patches_ctx(mw)
        c1.implicit_h_count = 3
        rect = c1.visual_rect()
        assert (rect.left(), rect.top(), rect.width()) == (-10.0, -10.0, 20.0)

    def test_unusable_font_metrics_leave_the_rect_alone(self, monkeypatch):
        def boom(_font):
            raise TypeError("argument 1 has unexpected type")

        monkeypatch.setattr(patcher_mod, "QFontMetricsF", boom)
        mw, c1, c2 = _mw_with_styled_atoms()
        apply_patches_ctx(mw)
        c1.implicit_h_count = 3
        mw.scene._rs_show_carbon = True
        rect = c1.visual_rect()
        assert (rect.left(), rect.width()) == (-10.0, 20.0)

    def test_state_round_trip_restores_narrowed_selection(self):
        mw, c1, c2 = _mw_with_styled_atoms()
        mm = ModeManager(mw, context=MagicMock())
        mw._reaction_mode_manager = mm
        apply_patches_ctx(mw)

        mw.scene._rs_show_carbon = False
        mw.scene._rs_show_carbon_ids = {2}
        state = mw.state_manager.get_current_state()
        assert state["rs_show_carbon"] is False
        assert state["rs_show_carbon_atoms"] == [2]

        mw.scene._rs_show_carbon_ids = set()
        mw.state_manager.set_state_from_data(state)
        assert mw.scene._rs_show_carbon_ids == {2}
        assert c2.is_visible is True

    def test_undo_snapshot_notices_a_show_carbon_change(self):
        mw, c1, c2 = _mw_with_styled_atoms()
        mm = ModeManager(mw, context=MagicMock())
        mw._reaction_mode_manager = mm
        apply_patches_ctx(mw, MagicMock())

        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 1
        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 1  # deduplicated

        mw.scene._rs_show_carbon = True
        mw.edit_actions_manager.push_undo_state()
        assert len(mw.edit_actions_manager.undo_stack) == 2

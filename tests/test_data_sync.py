"""
tests/test_data_sync.py -- regression tests for the "moved/cloned atoms must be
written back into the molecular data model" family of bugs.

Several reaction-sketcher operations moved the QGraphicsItem for an atom but
never updated data.atoms[...]["pos"] (or read charge/radical from a
non-existent atoms[aid]["atom"] object). The visual scene looked right, but the
data model kept the old values, so the change reverted on undo / save-reload or
the clone silently dropped charge/radical.

These tests exercise the ModeManager methods directly (via __new__ so the heavy
Qt __init__ is skipped) with a MagicMock host, asserting that the data model is
kept in sync.
"""

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, QRectF

from reaction_sketcher.mode_manager import ModeManager


class FakeAtomItem:
    """Minimal atom graphics item: has atom_id, no atom1/atom2, movable."""

    def __init__(self, atom_id, x=0.0, y=0.0):
        self.atom_id = atom_id
        self._x = float(x)
        self._y = float(y)

    def pos(self):
        return QPointF(self._x, self._y)

    def moveBy(self, dx, dy):
        self._x += dx
        self._y += dy


def _bare_mode_manager():
    mm = ModeManager.__new__(ModeManager)
    mm.main_window = MagicMock()
    mm.context = MagicMock()
    return mm


# ---------------------------------------------------------------------------
# Ctrl+Drag clone must preserve charge and radical
# ---------------------------------------------------------------------------


class TestCloneChargeRadical:
    def _run(self, atom_data):
        mm = _bare_mode_manager()
        mm.main_window.data.atoms = {1: atom_data}
        mm.main_window.data.bonds = {}
        scene = mm.main_window.scene
        scene.create_atom.return_value = 2
        scene.atom_items = {2: FakeAtomItem(2)}
        mm.duplicate_items_immediate([FakeAtomItem(1, 5.0, 5.0)])
        assert scene.create_atom.call_count == 1
        return scene.create_atom.call_args

    def test_charge_and_radical_preserved(self):
        args = self._run(
            {"symbol": "N", "pos": (0.0, 0.0), "charge": 1, "radical": 2}
        )
        assert args.kwargs.get("charge") == 1
        assert args.kwargs.get("radical") == 2

    def test_neutral_atom_defaults_zero(self):
        args = self._run({"symbol": "C", "pos": (0.0, 0.0)})
        assert args.kwargs.get("charge") == 0
        assert args.kwargs.get("radical") == 0

    def test_symbol_passed_through(self):
        args = self._run({"symbol": "O", "pos": (0.0, 0.0), "charge": -1})
        assert args.args and args.args[0] == "O"
        assert args.kwargs.get("charge") == -1


# ---------------------------------------------------------------------------
# Align must write moved atom positions back into the data model
# ---------------------------------------------------------------------------


def _unit(atom_item, rect):
    center = rect.center()
    return {
        "rect": rect,
        "members": [atom_item],
        "center": center,
        "cog": center,
        "type": "molecule",
    }


class TestAlignSyncsData:
    def test_align_top_writes_moved_atom_to_data(self):
        mm = _bare_mode_manager()
        moved = FakeAtomItem(1, 0.0, 100.0)
        stay = FakeAtomItem(2, 0.0, 0.0)
        mm.main_window.scene.selectedItems.return_value = [moved, stay]
        mm.get_logical_units = lambda items: [
            _unit(moved, QRectF(0, 100, 10, 10)),
            _unit(stay, QRectF(0, 0, 10, 10)),
        ]

        mm.align_items("top")

        called_ids = [c.args[0] for c in mm.main_window.data.set_atom_pos.call_args_list]
        # The unit at top=100 is shifted up to top=0; the one already at top=0
        # does not move.
        assert 1 in called_ids
        assert 2 not in called_ids
        # And its item actually moved to y=0.
        assert moved.pos().y() == 0.0


# ---------------------------------------------------------------------------
# Distribute must write the shifted middle atom position back into the data model
# ---------------------------------------------------------------------------


class TestDistributeSyncsData:
    def test_distribute_horizontal_writes_middle_atom(self):
        mm = _bare_mode_manager()
        left = FakeAtomItem(10, 0.0, 0.0)
        middle = FakeAtomItem(11, 30.0, 0.0)
        right = FakeAtomItem(12, 100.0, 0.0)
        mm.main_window.scene.selectedItems.return_value = [left, middle, right]
        mm.get_logical_units = lambda items: [
            _unit(left, QRectF(0, 0, 10, 10)),
            _unit(middle, QRectF(30, 0, 10, 10)),
            _unit(right, QRectF(100, 0, 10, 10)),
        ]

        mm.distribute_items("horizontal")

        called_ids = [c.args[0] for c in mm.main_window.data.set_atom_pos.call_args_list]
        # Endpoints stay put; only the middle unit is redistributed.
        assert 11 in called_ids
        assert 10 not in called_ids
        assert 12 not in called_ids


# ---------------------------------------------------------------------------
# Cloning reaction items must go through load_handler_core (no size/shape loss)
# ---------------------------------------------------------------------------


class TestCloneReactionItems:
    def test_cloned_rectangle_keeps_size(self):
        # Regression: the old inline clone read "width"/"height" while
        # create_json_data emits "w"/"h", so cloned frames collapsed to 50x50.
        from reaction_sketcher.items import ReactionCircleItem

        mm = _bare_mode_manager()
        mm.main_window.data.atoms = {}
        mm.main_window.data.bonds = {}

        original = ReactionCircleItem(QPointF(10, 10), QPointF(90, 60))
        original.shape_type = "rectangle"
        original.line_style = "dashed"

        result = mm.duplicate_items_immediate([original])

        clones = [i for i in result if isinstance(i, ReactionCircleItem)]
        assert clones, "clone should have produced a circle item"
        clone = clones[0]
        # Attributes round-trip through load_handler_core.
        assert clone.shape_type == "rectangle"
        assert clone.line_style == "dashed"
        # Size comes from the json "w"/"h". The old inline copy read
        # "width"/"height" (absent) and collapsed every frame to the 50x50
        # default, so a real (larger) frame proves the loader path is used.
        assert clone.rect.width() > 50
        assert clone.rect.height() > 50

    def test_copy_reaction_items_method_exists(self):
        # Regression: this method had lost its `def` line, so cut_reaction_items
        # -> self.copy_reaction_items() raised AttributeError.
        assert callable(getattr(ModeManager, "copy_reaction_items", None))

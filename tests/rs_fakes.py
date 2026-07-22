"""
tests/rs_fakes.py -- shared fake classes for patcher.py / interaction.py coverage tests.

Not a test file itself (no test_ prefix) so pytest does not collect it directly;
imported by test_patcher_coverage.py and test_interaction_coverage.py.
"""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene
from PyQt6.QtCore import QRectF, QPointF


class FakeSignal:
    """Minimal Qt-signal stand-in supporting connect/disconnect/emit."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
            return
        if slot not in self._slots:
            raise TypeError("not connected")
        self._slots.remove(slot)

    def emit(self, *args, **kwargs):
        for s in list(self._slots):
            s(*args, **kwargs)


class FakeAtomItem(QGraphicsItem):
    def __init__(self, atom_id, symbol="C", charge=0, radical=0):
        super().__init__()
        self.atom_id = atom_id
        self.symbol = symbol
        self.charge = charge
        self.radical = radical
        self.bonds = []
        self.implicit_h_count = 0
        self.is_visible = True
        self.hovered = False
        self.has_problem = False
        self.group_id = None
        self.is_group_selected = False
        self.font = MagicMock()
        self.pen_color = None
        self.color = None
        self._selected = False

    def isSelected(self):
        return self._selected

    def setSelected(self, v):
        self._selected = v

    def sceneBoundingRect(self):
        return QRectF(self.pos().x() - 5, self.pos().y() - 5, 10, 10)


class _LineMock:
    def __init__(self, p1=QPointF(0, 0), p2=QPointF(10, 10), length=10):
        self._p1 = p1
        self._p2 = p2
        self._length = length

    def p1(self):
        return self._p1

    def p2(self):
        return self._p2

    def length(self):
        return self._length


class FakeBondItem(QGraphicsItem):
    def __init__(self, atom1, atom2, order=1, stereo=0):
        super().__init__()
        self.atom1 = atom1
        self.atom2 = atom2
        self.order = order
        self.stereo = stereo
        self.group_id = None
        self.is_group_selected = False
        self._selected = False
        self.update_position_calls = 0
        atom1.bonds.append(self)
        atom2.bonds.append(self)

    def isSelected(self):
        return self._selected

    def setSelected(self, v):
        self._selected = v

    def get_line_in_local_coords(self):
        return _LineMock()

    def update_position(self):
        self.update_position_calls += 1

    def sceneBoundingRect(self):
        return QRectF(0, 0, 10, 10)


class FakeMoleculeScene(QGraphicsScene):
    """Stand-in for MoleculeScene with just enough surface for patcher/interaction."""

    def __init__(self):
        super().__init__()
        self.mode = "select"
        self.atom_items = {}
        self.bond_items = {}
        self._focus_item = None
        self._item_at = None
        self._items_under = []
        self.selectionChanged = FakeSignal()
        self._bg_brush = MagicMock()
        self._rect = QRectF(-4000, -4000, 4000, 4000)
        self.initial_positions_in_event = {}
        self._signals_blocked = False
        self.update_connected_bonds_calls = []
        self._next_atom_id = 1

    def focusItem(self):
        return self._focus_item

    def setFocusItem(self, item):
        self._focus_item = item

    def clearSelection(self):
        for it in self._items:
            it.setSelected(False)

    def itemAt(self, pos, transform=None):
        return self._item_at

    def items(self, *args, **kwargs):
        if args or kwargs:
            return list(self._items_under)
        return list(self._items)

    def update_connected_bonds(self, atoms):
        self.update_connected_bonds_calls.append(atoms)

    def backgroundBrush(self):
        return self._bg_brush

    def setBackgroundBrush(self, b):
        self._bg_brush = b

    def sceneRect(self):
        return self._rect

    def setSceneRect(self, r):
        self._rect = r

    def itemsBoundingRect(self):
        return QRectF()

    def signalsBlocked(self):
        return self._signals_blocked

    def blockSignals(self, v):
        old = self._signals_blocked
        self._signals_blocked = v
        return old

    def get_setting(self, key, default=None):
        return default

    def update(self):
        pass

    def create_atom(self, symbol, pos, charge=0, radical=0):
        aid = self._next_atom_id
        self._next_atom_id += 1
        item = FakeAtomItem(aid, symbol, charge, radical)
        item.setPos(pos)
        self.atom_items[aid] = item
        self.addItem(item)
        return aid

    def create_bond(self, a1, a2, bond_order=1, bond_stereo=0):
        b = FakeBondItem(a1, a2, bond_order, bond_stereo)
        self.bond_items[(a1.atom_id, a2.atom_id)] = b
        self.addItem(b)
        return b


class FakeDataModel:
    """Stand-in for MainWindowAppState's molecular data (host.state_manager.data)."""

    def __init__(self):
        self.atoms = {}
        self.bonds = {}
        self.next_atom_id = 1
        self._rdkit_mol = None

    def set_atom_pos(self, atom_id, pos):
        if atom_id in self.atoms:
            self.atoms[atom_id]["pos"] = [pos.x(), pos.y()]

    def to_rdkit_mol(self):
        return self._rdkit_mol


class FakeAppState:
    """Stand-in for MainWindowAppState (V3 state_manager)."""

    def __init__(self, host):
        self.host = host
        self.data = FakeDataModel()
        self.has_unsaved_changes = False

    def get_current_state(self):
        return {}

    def set_state_from_data(self, state_data):
        self._last_loaded = state_data

    def create_json_data(self):
        return {"atoms": {}, "bonds": {}}

    def update_window_title(self):
        self.window_title_updated = True

    def update_realtime_info(self):
        self.realtime_info_updated = True


class FakeEditActionsManager:
    """Stand-in for MainWindowEditActions (V3 edit_actions_manager)."""

    def __init__(self, host):
        self.host = host
        self.undo_stack = []
        self.redo_stack = []

    def update_implicit_hydrogens(self):
        self.implicit_hydrogens_updated = True

    def update_undo_redo_actions(self):
        self.undo_redo_actions_updated = True

    def resolve_overlapping_groups(self):
        self.overlap_resolved = True

    def _get_default_path(self):
        return ""

    def save_project_as(self):
        self.save_as_called = True


class FakeUiManager:
    """Stand-in for MainWindowUiManager."""

    def __init__(self, host):
        self.host = host
        self.modes_set = []

    def set_mode(self, mode_str):
        self.modes_set.append(mode_str)

    def activate_select_mode(self):
        self.select_mode_activated = True


class FakeIOManager:
    def __init__(self, host):
        self.host = host


class FakeInitManager:
    def __init__(self):
        self.current_file_path = None
        self.view_2d = None


class FakeView3DManager:
    def __init__(self):
        self.current_mol = None


class FakeMainWindow:
    """Stand-in MainWindow (host) with the attribute surface patcher.py reads."""

    def __init__(self):
        self.scene = FakeMoleculeScene()
        self.state_manager = FakeAppState(self)
        self.edit_actions_manager = FakeEditActionsManager(self)
        self.ui_manager = FakeUiManager(self)
        self.io_manager = FakeIOManager(self)
        self.init_manager = FakeInitManager()
        self.view_3d_manager = FakeView3DManager()
        self._reaction_mode_manager = None
        self._status_messages = []
        self._unsaved = False
        self._current_file_path = None
        self._actions = []

    # --- MainWindow surface used by patched methods ---
    def statusBar(self):
        sb = MagicMock()
        sb.showMessage = lambda msg: self._status_messages.append(msg)
        return sb

    def set_has_unsaved_changes(self, v):
        self._unsaved = v

    def update_window_title(self):
        pass

    def save_state_snapshot(self):
        pass

    def update_status_message(self, msg):
        self._status_messages.append(msg)

    def get_current_file_path(self):
        return self._current_file_path

    def set_current_file_path(self, path):
        self._current_file_path = path

    def addAction(self, action):
        self._actions.append(action)

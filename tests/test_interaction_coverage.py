"""
tests/test_interaction_coverage.py -- coverage-focused tests for InteractionHandler
in reaction_sketcher/interaction.py.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from reaction_sketcher.interaction import InteractionHandler
from reaction_sketcher.items import ReactionTextItem, ReactionArrowItem

from tests.rs_fakes import FakeMainWindow, FakeAtomItem, FakeBondItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEvent:
    def __init__(
        self,
        pos=QPointF(0, 0),
        button=Qt.MouseButton.LeftButton,
        etype=QEvent.Type.MouseButtonPress,
        key=None,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ):
        self._pos = pos
        self._button = button
        self._type = etype
        self._key = key
        self._modifiers = modifiers
        self.accepted = False

    def pos(self):
        return self._pos

    def button(self):
        return self._button

    def type(self):
        return self._type

    def key(self):
        return self._key

    def modifiers(self):
        return self._modifiers

    def globalPos(self):
        return self._pos

    def accept(self):
        self.accepted = True


@pytest.fixture(autouse=True)
def _reset_keyboard_modifiers():
    """Ensure QApplication.keyboardModifiers() is deterministic for every test."""
    QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.NoModifier
    yield
    QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.NoModifier


def _make_view_2d(scene_pos=QPointF(5, 5)):
    view = MagicMock()
    view.mapToScene.return_value = scene_pos
    view.transform.return_value = MagicMock()
    return view


def make_handler(mode_manager=None):
    mw = FakeMainWindow()
    mw.init_manager.view_2d = _make_view_2d()
    context = MagicMock()
    if mode_manager is None:
        mode_manager = MagicMock()
        mode_manager.is_reaction_mode = True
        mode_manager.default_props = {}
        mode_manager.default_head_styles = {}
        mode_manager.default_no_arrow_style = "cross"
        mode_manager.default_double_arrow_offset = 4.0
        mode_manager.default_bracket_type = "square"
        mode_manager.default_bracket_line_style = "solid"
        mode_manager.default_circle_shape_type = "circle"
        mode_manager.default_circle_line_style = "solid"
        mode_manager.duplicate_items_immediate = MagicMock(return_value=[])
    handler = InteractionHandler(context, mw, mode_manager)
    return handler, mw, context, mode_manager


# ---------------------------------------------------------------------------
# set_tool
# ---------------------------------------------------------------------------


class TestSetTool:
    def test_set_tool_select(self):
        handler, mw, ctx, mm = make_handler()
        handler.set_tool("select")
        assert handler.active_tool == "select"

    def test_set_tool_arrow_activates_select_mode(self):
        handler, mw, ctx, mm = make_handler()
        handler.set_tool("arrow")
        assert handler.active_tool == "arrow"
        assert mw.ui_manager.select_mode_activated is True

    def test_set_tool_none(self):
        handler, mw, ctx, mm = make_handler()
        handler.set_tool(None)
        assert handler.active_tool is None


# ---------------------------------------------------------------------------
# eventFilter
# ---------------------------------------------------------------------------


class TestEventFilter:
    def test_returns_false_if_not_reaction_mode(self):
        handler, mw, ctx, mm = make_handler()
        mm.is_reaction_mode = False
        event = FakeEvent()
        assert handler.eventFilter(None, event) is False

    def test_returns_false_if_no_main_window(self):
        handler, mw, ctx, mm = make_handler()
        handler.main_window = None
        assert handler.eventFilter(None, FakeEvent()) is False

    def test_non_select_mode_blocks_non_space(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        event = FakeEvent(etype=QEvent.Type.MouseButtonPress)
        assert handler.eventFilter(None, event) is False

    def test_non_select_mode_allows_space(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Space)
        # Space should proceed to handle_key_press (returns True by design)
        result = handler.eventFilter(None, event)
        assert result is True

    def test_mouse_press_dispatch(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene._items_under = []
        event = FakeEvent(etype=QEvent.Type.MouseButtonPress)
        handler.eventFilter(None, event)  # background click -> False, but no crash

    def test_mouse_move_dispatch(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.MouseMove)
        assert handler.eventFilter(None, event) is False

    def test_mouse_release_dispatch(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.MouseButtonRelease)
        assert handler.eventFilter(None, event) is False

    def test_key_press_dispatch(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_A)
        handler.eventFilter(None, event)

    def test_double_click_dispatch(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.MouseButtonDblClick)
        handler.eventFilter(None, event)

    def test_unhandled_event_type(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.Paint)
        assert handler.eventFilter(None, event) is False

    def test_bond_2_5_mode_allowed(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "bond_2_5"
        event = FakeEvent(etype=QEvent.Type.MouseMove)
        handler.eventFilter(None, event)

    def test_scene_attr_error_handled(self):
        handler, mw, ctx, mm = make_handler()

        class Boom:
            def __getattr__(self, item):
                raise RuntimeError("deleted")

        mw.scene = Boom()
        assert handler.eventFilter(None, FakeEvent()) is False


# ---------------------------------------------------------------------------
# handle_mouse_press
# ---------------------------------------------------------------------------


class TestHandleMousePress:
    def test_not_select_mode_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        assert handler.handle_mouse_press(FakeEvent()) is False

    def test_no_scene_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene = None
        assert handler.handle_mouse_press(FakeEvent()) is False

    def test_editing_text_inside_passes_through(self):
        handler, mw, ctx, mm = make_handler()
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        text_item.contains = lambda p: True
        mw.scene._focus_item = text_item
        result = handler.handle_mouse_press(FakeEvent())
        assert result is False

    def test_editing_text_outside_clears_focus(self):
        handler, mw, ctx, mm = make_handler()
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        text_item.contains = lambda p: False
        cleared = {"v": False}
        text_item.clearFocus = lambda: cleared.update(v=True)
        mw.scene._focus_item = text_item
        mw.scene._items_under = []
        handler.handle_mouse_press(FakeEvent())
        assert cleared["v"] is True

    def test_right_click_no_item(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene._item_at = None
        event = FakeEvent(button=Qt.MouseButton.RightButton)
        assert handler.handle_mouse_press(event) is False

    def test_right_click_delete_item(self):
        handler, mw, ctx, mm = make_handler()
        arrow = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        mw.scene.addItem(arrow)
        mw.scene._item_at = arrow
        event = FakeEvent(button=Qt.MouseButton.RightButton)
        result = handler.handle_mouse_press(event)
        assert result is True
        assert arrow not in mw.scene.items()
        ctx.push_undo_checkpoint.assert_called_once()

    def test_right_click_non_deletable_item(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene._item_at = object()
        event = FakeEvent(button=Qt.MouseButton.RightButton)
        assert handler.handle_mouse_press(event) is False

    def test_right_click_shift_context_menu(self):
        handler, mw, ctx, mm = make_handler()
        arrow = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        mw.scene.addItem(arrow)
        mw.scene._item_at = arrow
        QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.ShiftModifier
        event = FakeEvent(button=Qt.MouseButton.RightButton)
        result = handler.handle_mouse_press(event)
        assert result is True
        mm.show_tool_context_menu.assert_called_once()

    def test_middle_button_ignored(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(button=Qt.MouseButton.MiddleButton)
        assert handler.handle_mouse_press(event) is False

    def test_handle_item_forces_select_tool(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        handle_item = MagicMock()
        handle_item.handle_type = "resize"
        mw.scene._items_under = [handle_item]
        result = handler.handle_mouse_press(FakeEvent())
        assert result is False
        mm.activate_tool_by_name.assert_called_once_with("select")

    def test_click_background_clears_selection(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene._items_under = []
        result = handler.handle_mouse_press(FakeEvent())
        assert result is False

    def test_click_atom_starts_drag(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        mw.scene._items_under = [atom]
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True
        assert handler._is_dragging is True
        assert atom in handler._drag_items

    def test_click_already_selected_group_member(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.group_id = "g1"
        a2.group_id = "g1"
        a1.setSelected(True)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene._items_under = [a1]
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True

    def test_click_with_shift_adds_to_selection(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        mw.scene._items_under = [atom]
        QApplication.keyboardModifiers.return_value = Qt.KeyboardModifier.ShiftModifier
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True

    def test_drawing_tool_arrow(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True
        assert handler.preview_item is not None

    @pytest.mark.parametrize(
        "tool",
        [
            "arrow_res",
            "arrow_eq",
            "arrow_retro",
            "arrow_no",
            "curved_double",
            "curved_fish",
            "bracket",
            "circle",
            "plus",
            "minus",
            "text",
            "arrow_dashed",
            "line",
            "line_dashed",
            "line_curved",
            "freehand",
        ],
    )
    def test_drawing_tools_all(self, tool):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = tool
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True

    def test_drawing_tool_with_default_props(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        mm.default_props = {
            "arrow": {
                "color": "#ff0000",
                "width": 3,
                "head_size": 10.0,
                "head_angle": 30.0,
                "head_concavity": 0.5,
                "curvature": 0.2,
                "double_arrow_offset": 2.0,
                "line_style": "dashed",
                "cross_size": 5.0,
            }
        }
        result = handler.handle_mouse_press(FakeEvent())
        assert result is True

    def test_unknown_tool_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "nonexistent_tool"
        mw.scene._items_under = []
        # No items and not select tool falls through to final return False
        assert handler.handle_mouse_press(FakeEvent()) is False


# ---------------------------------------------------------------------------
# handle_mouse_move
# ---------------------------------------------------------------------------


class TestHandleMouseMove:
    def test_not_dragging_not_previewing_wrong_mode(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        assert handler.handle_mouse_move(FakeEvent()) is False

    def test_editing_text_inside(self):
        handler, mw, ctx, mm = make_handler()
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        text_item.contains = lambda p: True
        mw.scene._focus_item = text_item
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        assert handler.handle_mouse_move(FakeEvent()) is False

    def test_drag_below_threshold_swallows(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._drag_items = [atom]
        handler._drag_start_pos = QPointF(5, 5)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(5, 5)
        assert handler.handle_mouse_move(FakeEvent()) is True

    def test_drag_moves_items(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._drag_items = [atom]
        handler._drag_initial_positions = {atom: QPointF(0, 0)}
        handler._drag_start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(20, 20)
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True
        assert handler._did_move is True

    def test_drag_updates_connected_bonds(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        bond = FakeBondItem(a1, a2)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene.addItem(bond)
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._drag_items = [a1]
        handler._drag_initial_positions = {a1: QPointF(0, 0)}
        handler._drag_start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(20, 20)
        handler.handle_mouse_move(FakeEvent())
        assert bond.update_position_calls == 1

    def test_drag_shift_constrains(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._drag_items = [atom]
        handler._drag_initial_positions = {atom: QPointF(0, 0)}
        handler._drag_start_pos = QPointF(0, 0)
        handler._drag_start_with_shift = True
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(20, 5)
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True

    def test_drag_ctrl_clones(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        clone = FakeAtomItem(2)
        mw.scene.addItem(atom)
        mm.duplicate_items_immediate = MagicMock(return_value=[clone])
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._drag_items = [atom]
        handler._drag_original_positions = {atom: QPointF(0, 0)}
        handler._drag_initial_positions = {atom: QPointF(0, 0)}
        handler._drag_start_pos = QPointF(0, 0)
        handler._drag_start_with_ctrl = True
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(20, 20)
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True
        assert handler._has_cloned is True
        assert handler._drag_items == [clone]

    def test_preview_arrow_snap(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        handler.preview_item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
        handler.start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(20, 1)
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True

    def test_preview_freehand(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "freehand"
        from reaction_sketcher.items import ReactionFreehandItem

        handler.preview_item = ReactionFreehandItem(QPointF(0, 0))
        handler._freehand_drawing = True
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(5, 5)
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True

    def test_preview_bracket(self):
        handler, mw, ctx, mm = make_handler()
        from reaction_sketcher.items import ReactionBracketItem

        handler.active_tool = "bracket"
        handler.preview_item = ReactionBracketItem(QPointF(0, 0), QPointF(0, 0))
        result = handler.handle_mouse_move(FakeEvent())
        assert result is True

    def test_no_preview_no_drag_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        assert handler.handle_mouse_move(FakeEvent()) is False


# ---------------------------------------------------------------------------
# handle_mouse_release
# ---------------------------------------------------------------------------


class TestHandleMouseRelease:
    def test_wrong_mode_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        assert handler.handle_mouse_release(FakeEvent()) is False

    def test_end_drag_with_move(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._did_move = True
        handler._drag_items = [atom]
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True
        ctx.refresh_2d_scene.assert_called_once()
        ctx.push_undo_checkpoint.assert_called_once()

    def test_end_drag_with_move_syncs_data_model(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        mw.data = mw.state_manager.data
        mw.data.atoms[1] = {"pos": [0, 0]}
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._did_move = True
        handler._drag_items = [atom]
        handler.handle_mouse_release(FakeEvent())
        assert mw.scene.update_connected_bonds_calls

    def test_end_drag_no_move_toggle_off(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        atom.setSelected(True)
        atom.group_id = "g1"
        mw.scene.addItem(atom)
        mw.scene._item_at = atom
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._did_move = False
        handler._drag_start_with_ctrl = True
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True
        assert atom.isSelected() is False

    def test_end_drag_no_move_drill_down(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.setSelected(True)
        a2.setSelected(True)
        a1.is_group_selected = True
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene._item_at = a1
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._did_move = False
        handler._drag_start_item_was_selected = True
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True

    def test_end_drag_no_move_single_selected(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a1.setSelected(True)
        a1.is_group_selected = True
        mw.scene.addItem(a1)
        mw.scene._item_at = a1
        handler._is_dragging = True
        handler._drag_start_with_ctrl = getattr(handler, '_drag_start_with_ctrl', False)
        handler._drag_start_with_shift = getattr(handler, '_drag_start_with_shift', False)
        handler._did_move = False
        handler._drag_start_item_was_selected = True
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True

    def test_select_tool_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "select"
        assert handler.handle_mouse_release(FakeEvent()) is False

    def test_plus_minus_text_tool(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "plus"
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True
        ctx.push_undo_checkpoint.assert_called_once()

    def test_preview_small_item_removed(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
        mw.scene.addItem(item)
        handler.preview_item = item
        handler.start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(1, 1)
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True
        assert handler.preview_item is None
        assert item not in mw.scene.items()

    def test_preview_kept(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
        mw.scene.addItem(item)
        handler.preview_item = item
        handler.start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(100, 100)
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True
        assert handler.preview_item is None
        ctx.push_undo_checkpoint.assert_called_once()

    def test_freehand_kept_even_if_small(self):
        handler, mw, ctx, mm = make_handler()
        from reaction_sketcher.items import ReactionFreehandItem

        handler.active_tool = "freehand"
        item = ReactionFreehandItem(QPointF(0, 0))
        mw.scene.addItem(item)
        handler.preview_item = item
        handler.start_pos = QPointF(0, 0)
        mw.init_manager.view_2d.mapToScene.return_value = QPointF(0.1, 0.1)
        result = handler.handle_mouse_release(FakeEvent())
        assert result is True

    def test_no_preview_no_drag_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "arrow"
        assert handler.handle_mouse_release(FakeEvent()) is False


# ---------------------------------------------------------------------------
# delete_selection
# ---------------------------------------------------------------------------


class TestDeleteSelection:
    def test_no_selection_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        assert handler.delete_selection() is False

    def test_deletes_reaction_item(self):
        handler, mw, ctx, mm = make_handler()
        item = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        item.setSelected(True)
        mw.scene.addItem(item)
        result = handler.delete_selection()
        assert result is True
        assert item not in mw.scene.items()

    def test_deletes_atom(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        atom.setSelected(True)
        mw.scene.addItem(atom)
        result = handler.delete_selection()
        assert result is True

    def test_deletes_handle_parent(self):
        handler, mw, ctx, mm = make_handler()
        parent_item = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        mw.scene.addItem(parent_item)
        handle = MagicMock()
        handle.handle_type = "resize"
        handle.parentItem.return_value = parent_item
        handle.isSelected = lambda: True
        # selectedItems() reads scene._items which need the handle in it
        mw.scene.addItem(handle)
        handle._scene = mw.scene
        result = handler.delete_selection()
        assert result is True

    def test_fallback_manual_deletion(self, monkeypatch):
        handler, mw, ctx, mm = make_handler()
        item = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        item.setSelected(True)
        mw.scene.addItem(item)
        # Hide delete_items so delete_selection() takes the fallback path.
        monkeypatch.delattr(type(mw.scene), "delete_items", raising=False)
        result = handler.delete_selection()
        assert result is True
        ctx.push_undo_checkpoint.assert_called_once()


# ---------------------------------------------------------------------------
# handle_key_press
# ---------------------------------------------------------------------------


class TestHandleKeyPress:
    def test_escape_clears_text_focus(self):
        handler, mw, ctx, mm = make_handler()
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        cleared = {"v": False}
        text_item.clearFocus = lambda: cleared.update(v=True)
        mw.scene._focus_item = text_item
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Escape)
        result = handler.handle_key_press(event)
        assert result is True
        assert cleared["v"] is True

    def test_escape_clears_selection(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        atom.setSelected(True)
        mw.scene.addItem(atom)
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Escape)
        result = handler.handle_key_press(event)
        assert result is True
        assert atom.isSelected() is False

    def test_editing_text_passthrough(self):
        handler, mw, ctx, mm = make_handler()
        text_item = ReactionTextItem("hi", QPointF(0, 0))
        text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene._focus_item = text_item
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_A)
        assert handler.handle_key_press(event) is False

    def test_space_switches_mode(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene.mode = "atom"
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Space)
        result = handler.handle_key_press(event)
        assert result is True
        mm.activate_tool_by_name.assert_called_once_with("select")

    def test_space_selects_all_via_main_window(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "select"
        mw.select_all = MagicMock()
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Space)
        result = handler.handle_key_press(event)
        assert result is True
        mw.select_all.assert_called_once()

    def test_space_selects_all_via_edit_actions_manager(self):
        handler, mw, ctx, mm = make_handler()
        handler.active_tool = "select"
        mw.edit_actions_manager.select_all = MagicMock()
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Space)
        handler.handle_key_press(event)
        mw.edit_actions_manager.select_all.assert_called_once()

    def test_ctrl_a_select_all(self):
        handler, mw, ctx, mm = make_handler()
        mw.select_all = MagicMock()
        event = FakeEvent(
            etype=QEvent.Type.KeyPress,
            key=Qt.Key.Key_A,
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        result = handler.handle_key_press(event)
        assert result is True
        mw.select_all.assert_called_once()

    def test_delete_key(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        atom.setSelected(True)
        mw.scene.addItem(atom)
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Delete)
        result = handler.handle_key_press(event)
        assert result is True

    def test_other_key_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        event = FakeEvent(etype=QEvent.Type.KeyPress, key=Qt.Key.Key_Z)
        assert handler.handle_key_press(event) is False


# ---------------------------------------------------------------------------
# handle_mouse_double_click
# ---------------------------------------------------------------------------


class TestHandleMouseDoubleClick:
    def test_enter_text_edit_mode(self):
        handler, mw, ctx, mm = make_handler()
        item = ReactionTextItem("hi", QPointF(0, 0))
        mw.scene.addItem(item)
        mw.scene._items_under = [item]
        event = FakeEvent()
        result = handler.handle_mouse_double_click(event)
        assert result is True
        assert (
            item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction
        )

    def test_already_editing_text_passthrough(self):
        handler, mw, ctx, mm = make_handler()
        item = ReactionTextItem("hi", QPointF(0, 0))
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.addItem(item)
        mw.scene._items_under = [item]
        result = handler.handle_mouse_double_click(FakeEvent())
        assert result is False

    def test_exit_previous_text_item_first(self):
        handler, mw, ctx, mm = make_handler()
        old_item = ReactionTextItem("old", QPointF(0, 0))
        old_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        new_item = ReactionTextItem("new", QPointF(50, 50))
        mw.scene.addItem(old_item)
        mw.scene.addItem(new_item)
        mw.scene._focus_item = old_item
        mw.scene._items_under = [new_item]
        result = handler.handle_mouse_double_click(FakeEvent())
        assert result is True
        assert not (
            old_item.textInteractionFlags()
            & Qt.TextInteractionFlag.TextEditorInteraction
        )

    def test_select_molecule_via_atom(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        bond = FakeBondItem(a1, a2)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene.addItem(bond)
        mw.scene._items_under = [a1]
        result = handler.handle_mouse_double_click(FakeEvent())
        assert result is True
        assert a1.isSelected() and a2.isSelected() and bond.isSelected()

    def test_select_molecule_via_bond(self):
        handler, mw, ctx, mm = make_handler()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        bond = FakeBondItem(a1, a2)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene.addItem(bond)
        mw.scene._items_under = [bond]
        result = handler.handle_mouse_double_click(FakeEvent())
        assert result is True

    def test_no_matching_item_returns_false(self):
        handler, mw, ctx, mm = make_handler()
        mw.scene._items_under = []
        assert handler.handle_mouse_double_click(FakeEvent()) is False


# ---------------------------------------------------------------------------
# group overlay
# ---------------------------------------------------------------------------


class TestGroupOverlay:
    def test_update_group_overlay_creates(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler.update_group_overlay([atom])
        assert handler.group_overlay is not None
        assert handler.group_overlay in mw.scene.items()

    def test_update_group_overlay_empty_clears(self):
        handler, mw, ctx, mm = make_handler()
        atom = FakeAtomItem(1)
        mw.scene.addItem(atom)
        handler.update_group_overlay([atom])
        handler.update_group_overlay([])
        assert handler.group_overlay is None

    def test_clear_group_overlay_noop_when_none(self):
        handler, mw, ctx, mm = make_handler()
        handler.clear_group_overlay()
        assert handler.group_overlay is None

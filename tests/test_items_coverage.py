"""
tests/test_items_coverage.py -- broad coverage tests for reaction_sketcher/items.py.

items.py's classes are real QGraphicsItem/QGraphicsTextItem subclasses (the
conftest.py stand-ins are plain, real Python classes -- not Mocks), so unlike
settings_dialog.py, instantiating them directly runs the real source code and
pytest-cov attributes it correctly. No ast-extraction trickery is needed here.

Style: instantiate each item class, drive boundingRect/shape/paint across
head-style and selection-state variants, exercise handle-drag logic
(on_handle_moved), context menus, rotate_around, and create_json_data. A
shared `opt(selected)` helper controls `option.state & QStyle.StateFlag.
State_Selected` (QStyle is a bare MagicMock in conftest.py, so we monkeypatch
State_Selected to a real int once at import time and build option.state to
match).
"""

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem

import reaction_sketcher.items as items_mod
from reaction_sketcher.items import (
    rotate_point,
    get_main_window,
    ReactionHandle,
    ReactionArrowItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionNoArrowItem,
    ReactionDashedArrowItem,
    ReactionCurvedArrowItem,
    ReactionPlusItem,
    ReactionMinusItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionLineItem,
    ReactionCurvedLineItem,
    ReactionFreehandItem,
    ReactionTextItem,
    ReactionGroupOverlay,
)

# QStyle is a bare MagicMock() in conftest.py; give StateFlag.State_Selected a
# real int so `option.state & QStyle.StateFlag.State_Selected` behaves like
# real Qt bit-masking instead of MagicMock's always-truthy __rand__.
items_mod.QStyle.StateFlag.State_Selected = 2


def opt(selected=True):
    o = MagicMock()
    o.state = 2 if selected else 0
    return o


PAINTER = MagicMock()
S = QPointF(0, 0)
E = QPointF(100, 50)


class _FakeView:
    def __init__(self, window):
        self._window = window

    def window(self):
        return self._window


def scene_returning(mw):
    """A minimal scene-like object exposing only views() -> [view(mw)]."""
    scene = MagicMock()
    scene.views.return_value = [_FakeView(mw)]
    return scene


class _SceneNoPushUndo:
    """A scene stand-in that lacks `push_undo` (unlike a plain MagicMock,
    which would always satisfy hasattr(scene, "push_undo"))."""

    def __init__(self, mw):
        self._mw = mw

    def views(self):
        return [_FakeView(self._mw)]


HEAD_STYLES = ["triangle", "chevron", "chevron_curved", "harpoon", "barb"]


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------


class TestGetMainWindow:
    def test_none_scene_returns_none(self):
        assert get_main_window(None) is None

    def test_no_views_returns_none(self):
        scene = MagicMock()
        scene.views.return_value = []
        assert get_main_window(scene) is None

    def test_views_raising_runtime_error_returns_none(self):
        scene = MagicMock()
        scene.views.side_effect = RuntimeError("gone")
        assert get_main_window(scene) is None

    def test_views_raising_attribute_error_returns_none(self):
        scene = MagicMock()
        scene.views.side_effect = AttributeError("gone")
        assert get_main_window(scene) is None

    def test_returns_view_window(self):
        mw = MagicMock()
        assert get_main_window(scene_returning(mw)) is mw


class TestRotatePoint:
    def test_full_rotation_is_identity(self):
        p = QPointF(10, 5)
        c = QPointF(1, 1)
        r = rotate_point(p, c, 360)
        assert abs(r.x() - p.x()) < 1e-9
        assert abs(r.y() - p.y()) < 1e-9

    def test_rotation_preserves_distance_from_center(self):
        p = QPointF(10, 0)
        c = QPointF(0, 0)
        r = rotate_point(p, c, 37)
        dist_before = math.hypot(p.x() - c.x(), p.y() - c.y())
        dist_after = math.hypot(r.x() - c.x(), r.y() - c.y())
        assert abs(dist_before - dist_after) < 1e-9


# ---------------------------------------------------------------------------
# ReactionHandle
# ---------------------------------------------------------------------------


class TestReactionHandle:
    def test_bounding_rect_and_shape(self):
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        r = h.boundingRect()
        assert r.width() == h.size
        assert h.shape() is not None

    def test_paint_hover_and_not_hover(self):
        parent = ReactionArrowItem(S, E)
        h = ReactionHandle(parent, "control")
        h.is_hovered = True
        h.paint(PAINTER, opt(), None)
        h.is_hovered = False
        h.paint(PAINTER, opt(), None)

    def test_paint_control_type_draws_ellipse(self):
        parent = ReactionArrowItem(S, E)
        h = ReactionHandle(parent, "control")
        h.paint(PAINTER, opt(), None)  # exercises drawEllipse branch

    def test_hover_enter_and_leave(self):
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        h.hoverEnterEvent(MagicMock())
        assert h.is_hovered is True
        h.hoverLeaveEvent(MagicMock())
        assert h.is_hovered is False

    def test_mouse_press_disables_movable_parent(self):
        parent = ReactionArrowItem(S, E)
        parent.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        h = parent.h_start
        h.mousePressEvent(MagicMock())
        assert h._parent_was_movable is True
        assert not (parent.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def test_mouse_press_parent_already_not_movable(self):
        parent = ReactionArrowItem(S, E)
        parent.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        h = parent.h_start
        h.mousePressEvent(MagicMock())
        assert h._parent_was_movable is False

    def test_mouse_release_reenables_parent_and_pushes_undo(self):
        mw = MagicMock()
        parent = ReactionArrowItem(S, E)
        parent.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        h = parent.h_start
        h._parent_was_movable = True
        h.scene = lambda: scene_returning(mw)
        h.mouseReleaseEvent(MagicMock())
        assert parent.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert mw.edit_actions_manager.push_undo_state.called

    def test_mouse_release_no_reenable_when_flag_not_set(self):
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        h._parent_was_movable = False
        h.scene = lambda: None
        h.mouseReleaseEvent(MagicMock())  # must not raise, no mw available

    def test_item_change_position_change_alt_skips_snap(self, monkeypatch):
        import PyQt6.QtWidgets as qtw

        monkeypatch.setattr(
            qtw.QApplication,
            "keyboardModifiers",
            MagicMock(return_value=Qt.KeyboardModifier.AltModifier),
        )
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        new_pos = QPointF(5, 5)
        result = h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, new_pos
        )
        assert result is new_pos

    def test_item_change_position_change_non_start_end_handle_no_snap(
        self, monkeypatch
    ):
        import PyQt6.QtWidgets as qtw

        monkeypatch.setattr(
            qtw.QApplication,
            "keyboardModifiers",
            MagicMock(return_value=Qt.KeyboardModifier.NoModifier),
        )
        parent = ReactionArrowItem(S, E)
        h = parent.h_head  # handle_type "head_size", not in (start, end)
        new_pos = QPointF(5, 5)
        result = h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, new_pos
        )
        assert result is new_pos

    def test_item_change_position_change_curved_parent_skips_snap(self, monkeypatch):
        import PyQt6.QtWidgets as qtw

        monkeypatch.setattr(
            qtw.QApplication,
            "keyboardModifiers",
            MagicMock(return_value=Qt.KeyboardModifier.NoModifier),
        )
        parent = ReactionCurvedArrowItem(S, E)
        h = parent.h_start
        new_pos = QPointF(5, 5)
        result = h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, new_pos
        )
        assert result is new_pos

    def test_item_change_position_change_shift_axis_constraint(self, monkeypatch):
        import PyQt6.QtWidgets as qtw

        monkeypatch.setattr(
            qtw.QApplication,
            "keyboardModifiers",
            MagicMock(return_value=Qt.KeyboardModifier.ShiftModifier),
        )
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        result = h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, QPointF(60, 5)
        )
        assert hasattr(result, "x") and hasattr(result, "y")

    def test_item_change_position_change_short_line_no_snap(self, monkeypatch):
        import PyQt6.QtWidgets as qtw

        monkeypatch.setattr(
            qtw.QApplication,
            "keyboardModifiers",
            MagicMock(return_value=Qt.KeyboardModifier.NoModifier),
        )
        parent = ReactionArrowItem(S, E)
        h = parent.h_end
        proposed = QPointF(1, 1)  # very close to start_p -> length < 5
        result = h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionChange, proposed
        )
        assert result is proposed

    def test_item_change_position_has_changed_calls_on_handle_moved(self):
        parent = ReactionArrowItem(S, E)
        h = parent.h_start
        parent.on_handle_moved = MagicMock()
        h.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged, QPointF(1, 1)
        )
        parent.on_handle_moved.assert_called_once_with(h)


# ---------------------------------------------------------------------------
# ReactionArrowItem
# ---------------------------------------------------------------------------


class TestReactionArrowItem:
    def test_sync_handles_harpoon_side_variants(self):
        item = ReactionArrowItem(S, E)
        item.head_style = "harpoon"
        for side in (1, -1):
            item.head_side = side
            item.sync_handles()

    def test_on_handle_moved_start_end(self):
        item = ReactionArrowItem(S, E)
        item.h_start.setPos(QPointF(5, 5))
        item.on_handle_moved(item.h_start)
        assert item.start_p == QPointF(5, 5)
        item.h_end.setPos(QPointF(90, 40))
        item.on_handle_moved(item.h_end)
        assert item.end_p == QPointF(90, 40)

    def test_on_handle_moved_head_size_short_line_returns_early(self):
        item = ReactionArrowItem(QPointF(0, 0), QPointF(0, 0))
        before = item.head_size
        item.h_head.setPos(QPointF(1, 1))
        item.on_handle_moved(item.h_head)
        assert item.head_size == before

    def test_on_handle_moved_head_size_updates_size_and_angle(self):
        item = ReactionArrowItem(S, E)
        item.h_head.setPos(item.end_p + QPointF(-20, 5))
        item.on_handle_moved(item.h_head)
        assert item.head_size > 0
        assert 5 <= item.head_angle <= 80

    def test_on_handle_moved_concavity(self):
        item = ReactionArrowItem(S, E)
        item.h_concavity.setPos(item.end_p + QPointF(-5, 0))
        item.on_handle_moved(item.h_concavity)
        assert 0.1 <= item.head_concavity <= 1.0

    def test_context_menu_non_harpoon_returns_without_menu_exec(self):
        item = ReactionArrowItem(S, E)
        item.head_style = "chevron"
        event = MagicMock()
        item.contextMenuEvent(event)
        # menu.exec should never be reached for non-harpoon styles

    def test_context_menu_harpoon_flip_pushes_undo_via_scene_push_undo(
        self, monkeypatch
    ):
        import PyQt6.QtWidgets as qtw

        item = ReactionArrowItem(S, E)
        item.head_style = "harpoon"
        item.head_side = 1
        fake_action = MagicMock()
        fake_menu = MagicMock()
        fake_menu.addAction.return_value = fake_action
        fake_menu.exec.return_value = fake_action
        monkeypatch.setattr(qtw, "QMenu", MagicMock(return_value=fake_menu))
        scene = MagicMock()  # has push_undo (auto-attr)
        item.scene = lambda: scene
        item.contextMenuEvent(MagicMock())
        assert item.head_side == -1
        assert scene.push_undo.called

    def test_context_menu_harpoon_flip_falls_back_to_window_push_undo_state(
        self, monkeypatch
    ):
        import PyQt6.QtWidgets as qtw

        item = ReactionArrowItem(S, E)
        item.head_style = "harpoon"
        item.head_side = 1
        fake_action = MagicMock()
        fake_menu = MagicMock()
        fake_menu.addAction.return_value = fake_action
        fake_menu.exec.return_value = fake_action
        monkeypatch.setattr(qtw, "QMenu", MagicMock(return_value=fake_menu))
        mw = MagicMock()
        item.scene = lambda: _SceneNoPushUndo(mw)
        item.contextMenuEvent(MagicMock())
        assert item.head_side == -1
        assert mw.push_undo_state.called

    def test_set_end_pos_and_set_rect_size(self):
        item = ReactionArrowItem(S, E)
        item.set_end_pos(QPointF(200, 200))
        assert item.end_p == QPointF(200, 200)
        item2 = ReactionArrowItem(QPointF(0, 0), QPointF(10, 10))
        item2.set_rect_size(50, 30)
        assert item2.end_p.x() == 50
        assert item2.end_p.y() == 30
        item3 = ReactionArrowItem(QPointF(0, 0), QPointF(-10, -10))
        item3.set_rect_size(50, 30)
        assert item3.end_p.x() == -50
        assert item3.end_p.y() == -30

    def test_update_handle_visibility_selected_and_group(self):
        item = ReactionArrowItem(S, E)
        item.setSelected(True)
        item.is_group_selected = False
        item.update_handle_visibility()
        item.is_group_selected = True
        item.show_handles_in_group = False
        item.update_handle_visibility()
        item.show_handles_in_group = True
        item.update_handle_visibility()

    def test_item_change_selected_has_changed_calls_visibility(self):
        item = ReactionArrowItem(S, E)
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )

    def test_bounding_rect_and_shape(self):
        item = ReactionArrowItem(S, E)
        assert item.boundingRect() is not None
        assert item.shape() is not None

    def test_rotate_around(self):
        item = ReactionArrowItem(S, E)
        item.rotate_around(QPointF(50, 25), 45)

    def test_create_json_data(self):
        item = ReactionArrowItem(S, E)
        item.pen_color = QColor("red")
        d = item.create_json_data()
        assert d["type"] == "arrow"

    @pytest.mark.parametrize("style", HEAD_STYLES)
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint_all_head_styles(self, style, selected):
        item = ReactionArrowItem(S, E)
        item.head_style = style
        item.paint(PAINTER, opt(selected), None)

    def test_paint_zero_length_line_returns_early(self):
        item = ReactionArrowItem(QPointF(5, 5), QPointF(5, 5))
        item.paint(PAINTER, opt(False), None)


# ---------------------------------------------------------------------------
# ReactionPlusItem / ReactionMinusItem
# ---------------------------------------------------------------------------


class TestReactionPlusMinus:
    @pytest.mark.parametrize("cls", [ReactionPlusItem, ReactionMinusItem])
    def test_shape_bounding_rect_paint(self, cls):
        item = cls(QPointF(10, 20))
        item.shape()
        item.boundingRect()
        item.paint(PAINTER, opt(True), None)
        item.paint(PAINTER, opt(False), None)

    @pytest.mark.parametrize("cls", [ReactionPlusItem, ReactionMinusItem])
    def test_group_selected_paint_variant(self, cls):
        item = cls(QPointF(10, 20))
        item.is_group_selected = True
        item.paint(PAINTER, opt(True), None)

    @pytest.mark.parametrize("cls", [ReactionPlusItem, ReactionMinusItem])
    def test_item_change_calls_visibility_noop(self, cls):
        item = cls(QPointF(0, 0))
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )

    @pytest.mark.parametrize("cls", [ReactionPlusItem, ReactionMinusItem])
    def test_set_size_and_json(self, cls):
        item = cls(QPointF(0, 0))
        item.set_size(40)
        d = item.create_json_data()
        assert d["size"] == 40

    @pytest.mark.parametrize("cls", [ReactionPlusItem, ReactionMinusItem])
    def test_rotate_around(self, cls):
        item = cls(QPointF(10, 10))
        item.rotate_around(QPointF(0, 0), 90)


# ---------------------------------------------------------------------------
# ReactionResonanceArrowItem
# ---------------------------------------------------------------------------


class TestReactionResonanceArrowItem:
    @pytest.mark.parametrize("style", HEAD_STYLES)
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint_all_styles(self, style, selected):
        item = ReactionResonanceArrowItem(S, E)
        item.head_style = style
        item.paint(PAINTER, opt(selected), None)

    @pytest.mark.parametrize("side", [1, -1])
    def test_paint_harpoon_side_variants(self, side):
        item = ReactionResonanceArrowItem(S, E)
        item.head_style = "harpoon"
        item.head_side = side
        item.paint(PAINTER, opt(False), None)

    def test_paint_zero_length_returns_early(self):
        item = ReactionResonanceArrowItem(QPointF(1, 1), QPointF(1, 1))
        item.paint(PAINTER, opt(False), None)

    def test_paint_short_line_skips_double_shorten(self):
        item = ReactionResonanceArrowItem(QPointF(0, 0), QPointF(3, 0))
        item.paint(PAINTER, opt(False), None)

    def test_json(self):
        d = ReactionResonanceArrowItem(S, E).create_json_data()
        assert d["type"] == "arrow_res"
        assert "head_concavity" in d


# ---------------------------------------------------------------------------
# ReactionEquilibriumArrowItem
# ---------------------------------------------------------------------------


class TestReactionEquilibriumArrowItem:
    @pytest.mark.parametrize(
        "style", ["triangle", "chevron", "harpoon", "equilibrium", "barb"]
    )
    def test_paint_all_styles(self, style):
        item = ReactionEquilibriumArrowItem(S, E)
        item.head_style = style
        item.paint(PAINTER, opt(True), None)
        item.paint(PAINTER, opt(False), None)

    def test_paint_zero_length_returns_early(self):
        item = ReactionEquilibriumArrowItem(QPointF(1, 1), QPointF(1, 1))
        item.paint(PAINTER, opt(False), None)

    def test_sync_handles_and_concavity_visibility(self):
        item = ReactionEquilibriumArrowItem(S, E)
        item.head_style = "chevron"
        item.setSelected(True)
        item.sync_handles()
        item.head_style = "triangle"
        item.sync_handles()

    def test_on_handle_moved_start_end_head_size_concavity(self):
        item = ReactionEquilibriumArrowItem(S, E)
        item.h_start.setPos(QPointF(5, 5))
        item.on_handle_moved(item.h_start)
        item.h_end.setPos(QPointF(95, 45))
        item.on_handle_moved(item.h_end)
        item.h_head.setPos(item.h_head.pos() + QPointF(2, 2))
        item.on_handle_moved(item.h_head)
        item.h_concavity.setPos(item.h_concavity.pos() + QPointF(1, 1))
        item.on_handle_moved(item.h_concavity)

    def test_json(self):
        d = ReactionEquilibriumArrowItem(S, E).create_json_data()
        assert d["type"] == "arrow_eq"
        assert "double_arrow_offset" in d


# ---------------------------------------------------------------------------
# ReactionRetroArrowItem
# ---------------------------------------------------------------------------


class TestReactionRetroArrowItem:
    @pytest.mark.parametrize("style", HEAD_STYLES)
    def test_paint_all_styles(self, style):
        item = ReactionRetroArrowItem(S, E)
        item.head_style = style
        item.paint(PAINTER, opt(True), None)
        item.paint(PAINTER, opt(False), None)

    def test_paint_zero_length_returns_early(self):
        item = ReactionRetroArrowItem(QPointF(2, 2), QPointF(2, 2))
        item.paint(PAINTER, opt(False), None)

    def test_sync_handles_concavity_visible_for_chevron(self):
        item = ReactionRetroArrowItem(S, E)
        item.head_style = "chevron"
        item.setSelected(True)
        item.sync_handles()

    def test_on_handle_moved_all(self):
        item = ReactionRetroArrowItem(S, E)
        item.h_start.setPos(QPointF(5, 5))
        item.on_handle_moved(item.h_start)
        item.h_end.setPos(QPointF(95, 45))
        item.on_handle_moved(item.h_end)
        item.h_head.setPos(item.h_head.pos() + QPointF(3, 3))
        item.on_handle_moved(item.h_head)

    def test_json(self):
        assert ReactionRetroArrowItem(S, E).create_json_data()["type"] == "arrow_retro"


# ---------------------------------------------------------------------------
# ReactionNoArrowItem
# ---------------------------------------------------------------------------


class TestReactionNoArrowItem:
    @pytest.mark.parametrize("style", ["slash", "double_slash", "cross"])
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint_negation_styles(self, style, selected):
        item = ReactionNoArrowItem(S, E)
        item.negation_style = style
        item.paint(PAINTER, opt(selected), None)

    def test_paint_short_line_skips_negation_mark(self):
        item = ReactionNoArrowItem(QPointF(0, 0), QPointF(5, 0))
        item.paint(PAINTER, opt(False), None)

    def test_json(self):
        d = ReactionNoArrowItem(S, E).create_json_data()
        assert d["type"] == "arrow_no"
        assert "negation_style" in d
        assert "cross_size" in d


# ---------------------------------------------------------------------------
# ReactionDashedArrowItem
# ---------------------------------------------------------------------------


class TestReactionDashedArrowItem:
    @pytest.mark.parametrize("style", HEAD_STYLES)
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint_all_styles(self, style, selected):
        item = ReactionDashedArrowItem(S, E)
        item.head_style = style
        item.paint(PAINTER, opt(selected), None)

    def test_paint_zero_length_returns_early(self):
        item = ReactionDashedArrowItem(QPointF(1, 1), QPointF(1, 1))
        item.paint(PAINTER, opt(False), None)

    def test_json(self):
        assert (
            ReactionDashedArrowItem(S, E).create_json_data()["type"] == "arrow_dashed"
        )


# ---------------------------------------------------------------------------
# ReactionCurvedArrowItem / ReactionCurvedLineItem
# ---------------------------------------------------------------------------


class TestReactionCurvedArrowItem:
    def test_get_control_point_explicit_and_auto(self):
        item = ReactionCurvedArrowItem(S, E)
        auto_cp = item.get_control_point()
        assert auto_cp is not None
        item.control_p = QPointF(40, 40)
        assert item.get_control_point() == QPointF(40, 40)

    @pytest.mark.parametrize("fish_hook", [False, True])
    @pytest.mark.parametrize("style", HEAD_STYLES)
    def test_paint_all_combinations(self, fish_hook, style):
        item = ReactionCurvedArrowItem(S, E, is_fish_hook=fish_hook)
        item.head_style = style
        item.paint(PAINTER, opt(True), None)
        item.paint(PAINTER, opt(False), None)

    def test_paint_head_at_start(self):
        item = ReactionCurvedArrowItem(S, E)
        item.head_at = "start"
        item.paint(PAINTER, opt(False), None)

    def test_paint_short_curve_skips_shortening(self):
        item = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(2, 0))
        item.paint(PAINTER, opt(False), None)

    @pytest.mark.parametrize("fish_hook", [False, True])
    @pytest.mark.parametrize("style", HEAD_STYLES)
    def test_shape_all_combinations(self, fish_hook, style):
        item = ReactionCurvedArrowItem(S, E, is_fish_hook=fish_hook)
        item.head_style = style
        assert item.shape() is not None

    def test_shape_head_at_start(self):
        item = ReactionCurvedArrowItem(S, E)
        item.head_at = "start"
        assert item.shape() is not None

    def test_curved_line_item_shape_skips_arrowhead(self):
        item = ReactionCurvedLineItem(S, E)
        assert item.shape() is not None

    def test_bounding_rect(self):
        item = ReactionCurvedArrowItem(S, E)
        assert item.boundingRect() is not None

    def test_on_handle_moved_start_end_control(self):
        item = ReactionCurvedArrowItem(S, E)
        item.h_start.setPos(QPointF(5, 5))
        item.on_handle_moved(item.h_start)
        item.h_end.setPos(QPointF(95, 45))
        item.on_handle_moved(item.h_end)
        item.h_control.setPos(QPointF(50, 10))
        item.on_handle_moved(item.h_control)
        assert item.control_p == QPointF(50, 10)

    def test_on_handle_moved_head_size_and_concavity(self):
        item = ReactionCurvedArrowItem(S, E)
        item.h_head.setPos(item.h_head.pos() + QPointF(3, 3))
        item.on_handle_moved(item.h_head)
        item.h_concavity.setPos(item.h_concavity.pos() + QPointF(1, 1))
        item.on_handle_moved(item.h_concavity)

    def test_context_menu_fish_hook_flips_side(self, monkeypatch):
        import PyQt6.QtWidgets as qtw

        item = ReactionCurvedArrowItem(S, E, is_fish_hook=True)
        item.head_side = 1
        fake_action = MagicMock()
        fake_menu = MagicMock()
        fake_menu.addAction.return_value = fake_action
        fake_menu.exec.return_value = fake_action
        monkeypatch.setattr(qtw, "QMenu", MagicMock(return_value=fake_menu))
        scene = MagicMock()
        item.scene = lambda: scene
        item.contextMenuEvent(MagicMock())
        assert item.head_side == -1
        assert scene.push_undo.called

    def test_context_menu_non_fish_hook_returns_without_flip(self):
        item = ReactionCurvedArrowItem(S, E, is_fish_hook=False)
        item.contextMenuEvent(MagicMock())  # must not raise

    def test_json_with_and_without_control_p(self):
        item = ReactionCurvedArrowItem(S, E, is_fish_hook=True)
        d = item.create_json_data()
        assert d["type"] == "curved_fish"
        assert "control_p" not in d

        item.control_p = QPointF(1, 2)
        d2 = item.create_json_data()
        assert d2["control_p"] == [1, 2]

    def test_json_non_fish_hook(self):
        d = ReactionCurvedArrowItem(S, E, is_fish_hook=False).create_json_data()
        assert d["type"] == "curved_double"


class TestReactionCurvedLineItem:
    def test_sync_handles_hides_head_and_concavity(self):
        item = ReactionCurvedLineItem(S, E)
        item.sync_handles()
        assert item.h_head.isVisible() is False
        assert item.h_concavity.isVisible() is False

    @pytest.mark.parametrize("selected", [True, False])
    @pytest.mark.parametrize("style", ["solid", "dashed"])
    def test_paint(self, selected, style):
        item = ReactionCurvedLineItem(S, E)
        item.line_style = style
        item.paint(PAINTER, opt(selected), None)

    def test_rotate_around_with_and_without_control_p(self):
        item = ReactionCurvedLineItem(S, E)
        item.rotate_around(QPointF(50, 25), 30)
        item.control_p = QPointF(60, 60)
        item.rotate_around(QPointF(50, 25), 30)

    def test_json_strips_head_style_and_angle(self):
        d = ReactionCurvedLineItem(S, E).create_json_data()
        assert d["type"] == "line_curved"
        assert "head_style" not in d
        assert "head_angle" not in d
        assert "cp_x" in d and "cp_y" in d


# ---------------------------------------------------------------------------
# ReactionBracketItem
# ---------------------------------------------------------------------------


BRACKET_TYPES = [
    "square",
    "square_left",
    "square_right",
    "round",
    "round_left",
    "round_right",
    "curly",
    "curly_left",
    "curly_right",
]


class TestReactionBracketItem:
    @pytest.mark.parametrize("bracket_type", BRACKET_TYPES)
    def test_shape_all_types(self, bracket_type):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.bracket_type = bracket_type
        assert item.shape() is not None

    @pytest.mark.parametrize("bracket_type", BRACKET_TYPES)
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint_all_types(self, bracket_type, selected):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.bracket_type = bracket_type
        item.paint(PAINTER, opt(selected), None)

    def test_paint_dashed_line_style(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.line_style = "dashed"
        item.paint(PAINTER, opt(False), None)

    def test_on_handle_moved_and_set_end_pos_and_set_rect_size(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.h_br.setPos(QPointF(70, 100))
        item.on_handle_moved(item.h_br)
        item.set_end_pos(QPointF(80, 110))
        item.set_rect_size(40, 40)
        assert item.rect.width() == 40

    def test_update_handle_visibility_group_variants(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.setSelected(True)
        item.is_group_selected = False
        item.update_handle_visibility()
        item.is_group_selected = True
        item.show_handles_in_group = True
        item.update_handle_visibility()

    def test_item_change_selected_has_changed(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )

    def test_bounding_rect(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        assert item.boundingRect() is not None

    def test_rotate_around(self):
        item = ReactionBracketItem(S, QPointF(60, 90))
        item.rotate_around(QPointF(30, 30), 45)

    def test_json(self):
        d = ReactionBracketItem(S, QPointF(60, 90)).create_json_data()
        assert d["type"] == "bracket"


# ---------------------------------------------------------------------------
# ReactionCircleItem
# ---------------------------------------------------------------------------


class TestReactionCircleItem:
    @pytest.mark.parametrize("shape_type", ["rectangle", "circle"])
    def test_shape_outline_only(self, shape_type):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.shape_type = shape_type
        assert item.shape() is not None

    @pytest.mark.parametrize("shape_type", ["rectangle", "circle"])
    def test_shape_filled(self, shape_type):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.shape_type = shape_type
        item.fill_color = "#ff0000"
        assert item.shape() is not None

    @pytest.mark.parametrize("shape_type", ["rectangle", "circle"])
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint(self, shape_type, selected):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.shape_type = shape_type
        item.paint(PAINTER, opt(selected), None)

    def test_paint_filled_and_dashed(self):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.fill_color = "#00ff00"
        item.line_style = "dashed"
        item.paint(PAINTER, opt(True), None)

    def test_on_handle_moved_and_set_end_pos_and_set_rect_size(self):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.h_br.setPos(QPointF(70, 70))
        item.on_handle_moved(item.h_br)
        item.set_end_pos(QPointF(90, 90))
        item.set_rect_size(30, 30)
        assert item.rect.width() == 30

    def test_item_change_updates_handle_visibility(self):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )

    def test_rotate_around(self):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.rotate_around(QPointF(30, 30), 30)

    def test_json_with_fill_color(self):
        item = ReactionCircleItem(S, QPointF(60, 60))
        item.fill_color = "#ff00ff"
        d = item.create_json_data()
        assert d["fill_color"] is not None


# ---------------------------------------------------------------------------
# ReactionLineItem
# ---------------------------------------------------------------------------


class TestReactionLineItem:
    @pytest.mark.parametrize("style", ["solid", "dashed"])
    @pytest.mark.parametrize("selected", [True, False])
    def test_paint(self, style, selected):
        item = ReactionLineItem(S, E)
        item.line_style = style
        item.paint(PAINTER, opt(selected), None)

    def test_paint_zero_length_returns_early(self):
        item = ReactionLineItem(QPointF(1, 1), QPointF(1, 1))
        item.paint(PAINTER, opt(False), None)

    def test_sync_handles_hides_head_and_concavity(self):
        item = ReactionLineItem(S, E)
        item.sync_handles()
        assert item.h_head.isVisible() is False
        assert item.h_concavity.isVisible() is False

    def test_json(self):
        assert ReactionLineItem(S, E).create_json_data()["type"] == "line"


# ---------------------------------------------------------------------------
# ReactionFreehandItem
# ---------------------------------------------------------------------------


class TestReactionFreehandItem:
    def test_add_point_updates_bounding_rect(self):
        item = ReactionFreehandItem(S)
        before = item.boundingRect()
        item.add_point(QPointF(20, 20))
        after = item.boundingRect()
        assert after != before or after.width() >= before.width()

    def test_set_points(self):
        item = ReactionFreehandItem(S)
        item.set_points([QPointF(1, 2), QPointF(3, 4), QPointF(5, 6)])
        assert len(item.points) == 3

    def test_set_rect_size_scales_points(self):
        item = ReactionFreehandItem(S)
        item.set_points([QPointF(0, 0), QPointF(10, 10)])
        item.set_rect_size(50, 50)
        d = item.create_json_data()
        assert len(d["points"]) == 2

    def test_set_rect_size_no_op_when_no_points(self):
        item = ReactionFreehandItem(S)
        item.points = []
        item.set_rect_size(50, 50)  # must not raise

    def test_set_rect_size_no_op_when_zero_area(self):
        item = ReactionFreehandItem(S)
        item.set_points([QPointF(0, 0)])  # single point -> zero-size bbox
        item.set_rect_size(50, 50)  # must not raise

    @pytest.mark.parametrize("selected", [True, False])
    def test_paint(self, selected):
        item = ReactionFreehandItem(S)
        item.add_point(QPointF(10, 10))
        item.paint(PAINTER, opt(selected), None)

    def test_item_change_and_shape(self):
        item = ReactionFreehandItem(S)
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )
        assert item.shape() is not None

    def test_rotate_around(self):
        item = ReactionFreehandItem(S)
        item.rotate_around(QPointF(0, 0), 90)

    def test_json_initial_single_point(self):
        # __init__ seeds `points` with a single origin point.
        d = ReactionFreehandItem(S).create_json_data()
        assert d["type"] == "freehand"
        assert d["points"] == [[0.0, 0.0]]


# ---------------------------------------------------------------------------
# ReactionTextItem
# ---------------------------------------------------------------------------


class _MwWithUiManagerOnly:
    """Lacks `_reaction_mode_manager` so hasattr() correctly routes methods
    to the `elif hasattr(mw, "ui_manager")...` branch."""

    def __init__(self):
        self.ui_manager = MagicMock()


class TestReactionTextItem:
    def test_mouse_press_in_edit_mode_vs_not(self):
        item = ReactionTextItem("H2O", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.mousePressEvent(MagicMock())
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.mousePressEvent(MagicMock())

    def test_shape_and_item_change(self):
        item = ReactionTextItem("A", S)
        assert item.shape() is not None
        item.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged, True
        )

    def test_scene_event_shortcut_override_in_edit_mode_accepts(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        event = MagicMock()
        event.type.return_value = items_mod.QEvent.Type.ShortcutOverride
        result = item.sceneEvent(event)
        assert result is True
        assert event.accept.called

    def test_scene_event_shortcut_override_not_editing_falls_through(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        event = MagicMock()
        event.type.return_value = items_mod.QEvent.Type.ShortcutOverride
        item.sceneEvent(event)  # falls through to super().sceneEvent

    def test_mouse_double_click_enters_edit_mode(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        event = MagicMock()
        item.mouseDoubleClickEvent(event)
        assert (
            item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction
        )
        assert event.accept.called

    def test_mouse_double_click_already_editing_calls_super(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.mouseDoubleClickEvent(MagicMock())  # must not raise

    def test_mouse_double_click_disables_shortcuts_via_reaction_mode_manager(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        mw = MagicMock()
        item.scene = lambda: scene_returning(mw)
        item.mouseDoubleClickEvent(MagicMock())
        assert mw._reaction_mode_manager.disable_main_window_shortcuts.called

    def test_mouse_double_click_disables_shortcuts_via_ui_manager(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        mw = _MwWithUiManagerOnly()
        item.scene = lambda: scene_returning(mw)
        item.mouseDoubleClickEvent(MagicMock())
        assert mw.ui_manager._reaction_mode_manager.disable_main_window_shortcuts.called

    def test_focus_out_auto_deletes_when_empty(self):
        item = ReactionTextItem("", S)
        scene = MagicMock()
        item.scene = lambda: scene
        item.focusOutEvent(MagicMock())
        assert scene.removeItem.called

    def test_focus_out_auto_deletes_fresh_placeholder(self):
        item = ReactionTextItem("kept text", S)
        item._fresh_placeholder = True
        scene = MagicMock()
        item.scene = lambda: scene
        item.focusOutEvent(MagicMock())
        assert scene.removeItem.called

    def test_focus_out_normal_path_notifies_scene_and_pushes_undo(self):
        item = ReactionTextItem("kept text", S)
        mw = MagicMock()
        scene = scene_returning(mw)
        item.scene = lambda: scene
        item.focusOutEvent(MagicMock())
        assert scene.on_text_edited.called
        assert mw.edit_actions_manager.push_undo_state.called

    def test_focus_out_no_main_window_still_safe(self):
        item = ReactionTextItem("kept text", S)
        item.scene = lambda: None
        item.focusOutEvent(MagicMock())  # must not raise

    def test_focus_out_reenables_via_last_main_window_fallback(self):
        item = ReactionTextItem("kept text", S)
        mw = MagicMock()
        item._last_main_window = mw
        item.scene = lambda: None
        item.focusOutEvent(MagicMock())
        assert mw._reaction_mode_manager.enable_main_window_shortcuts.called

    @pytest.mark.parametrize(
        "key_name,style",
        [("Key_B", "bold"), ("Key_I", "italic"), ("Key_U", "underline")],
    )
    def test_key_press_style_shortcuts(self, key_name, style):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = MagicMock()
        item.scene = lambda: scene_returning(mw)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        event.key.return_value = getattr(Qt.Key, key_name)
        item.keyPressEvent(event)
        mw._reaction_mode_manager.apply_text_style.assert_called_with(style)
        assert event.accept.called

    def test_key_press_style_shortcut_via_ui_manager(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = _MwWithUiManagerOnly()
        item.scene = lambda: scene_returning(mw)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        event.key.return_value = Qt.Key.Key_B
        item.keyPressEvent(event)
        mw.ui_manager._reaction_mode_manager.apply_text_style.assert_called_with("bold")

    def test_key_press_subscript_and_superscript(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = MagicMock()
        item.scene = lambda: scene_returning(mw)

        event_sub = MagicMock()
        event_sub.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        event_sub.key.return_value = Qt.Key.Key_Equal
        item.keyPressEvent(event_sub)
        assert mw._reaction_mode_manager.toggle_subscript.called

        event_sup = MagicMock()
        event_sup.modifiers.return_value = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )
        event_sup.key.return_value = Qt.Key.Key_Plus
        item.keyPressEvent(event_sup)
        assert mw._reaction_mode_manager.toggle_superscript.called

    def test_key_press_subscript_via_ui_manager(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = _MwWithUiManagerOnly()
        item.scene = lambda: scene_returning(mw)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        event.key.return_value = Qt.Key.Key_Equal
        item.keyPressEvent(event)
        assert mw.ui_manager._reaction_mode_manager.toggle_subscript.called

    def test_key_press_escape_triggers_select_tool(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = MagicMock()
        select_action = MagicMock()
        select_action.property.return_value = "select"
        mw._reaction_mode_manager.action_group.actions.return_value = [select_action]
        item.scene = lambda: scene_returning(mw)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        event.key.return_value = Qt.Key.Key_Escape
        item.keyPressEvent(event)
        assert select_action.trigger.called

    def test_key_press_escape_via_ui_manager(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = _MwWithUiManagerOnly()
        select_action = MagicMock()
        select_action.property.return_value = "select"
        mw.ui_manager._reaction_mode_manager.action_group.actions.return_value = [
            select_action
        ]
        item.scene = lambda: scene_returning(mw)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        event.key.return_value = Qt.Key.Key_Escape
        item.keyPressEvent(event)
        assert select_action.trigger.called

    def test_key_press_other_key_falls_through_to_super(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        event = MagicMock()
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        event.key.return_value = Qt.Key.Key_A
        item.keyPressEvent(event)
        assert event.accept.called

    def test_key_press_not_editing_calls_super_directly(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        event = MagicMock()
        item.keyPressEvent(event)  # must not raise

    def test_format_as_chemical_subscripts_and_superscripts(self):
        item = ReactionTextItem("Ca2+ Na+ H2O", S)
        item.format_as_chemical()  # must not raise

    def test_focus_in_event_edit_mode_disables_shortcuts(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw = MagicMock()
        item.scene = lambda: scene_returning(mw)
        item.focusInEvent(MagicMock())
        assert mw._reaction_mode_manager.disable_main_window_shortcuts.called

    def test_focus_in_event_not_edit_mode_is_noop(self):
        item = ReactionTextItem("A", S)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.focusInEvent(MagicMock())  # must not raise

    @pytest.mark.parametrize("selected", [True, False])
    def test_paint(self, selected):
        item = ReactionTextItem("A", S)
        item.paint(PAINTER, opt(selected), None)

    def test_size_property_getter_setter_and_set_size(self):
        item = ReactionTextItem("A", S)
        item.size = 30
        assert item.size == item.font().pointSize.return_value
        item.set_size(40)

    def test_rotate_around(self):
        item = ReactionTextItem("A", S)
        item.rotate_around(QPointF(0, 0), 90)

    def test_json(self):
        item = ReactionTextItem("H2O", QPointF(3, 4))
        d = item.create_json_data()
        assert d["type"] == "text"
        assert d["text"] == "H2O"


# ---------------------------------------------------------------------------
# ReactionGroupOverlay
# ---------------------------------------------------------------------------


class _ArrowLikeItem:
    def __init__(self):
        self.start_p = QPointF(0, 0)
        self.end_p = QPointF(10, 0)
        self.control_p = QPointF(5, 5)
        self.head_size = 10.0
        self.sync_calls = 0
        self.update_calls = 0

    def scene(self):
        return None

    def sceneBoundingRect(self):
        return items_mod.QRectF(
            min(self.start_p.x(), self.end_p.x()),
            min(self.start_p.y(), self.end_p.y()),
            abs(self.end_p.x() - self.start_p.x()),
            abs(self.end_p.y() - self.start_p.y()),
        )

    def sync_handles(self):
        self.sync_calls += 1

    def update(self):
        self.update_calls += 1


class _RectLikeItem:
    """Mimics Bracket/Circle: has .rect + setPos/pos/mapToScene."""

    def __init__(self):
        self._pos = QPointF(0, 0)
        self.rect = MagicMock()
        self.rect.width.return_value = 20.0
        self.rect.height.return_value = 20.0
        self.rect.topLeft.return_value = QPointF(0, 0)
        self.rect.bottomRight.return_value = QPointF(20, 20)
        self.sync_calls = 0
        self.update_calls = 0

    def pos(self):
        return self._pos

    def setPos(self, p):
        self._pos = p

    def mapToScene(self, p):
        return p

    def scene(self):
        return None

    def sceneBoundingRect(self):
        return items_mod.QRectF(0, 0, 20, 20)

    def sync_handles(self):
        self.sync_calls += 1

    def update(self):
        self.update_calls += 1


class _FreehandLikeItem:
    def __init__(self):
        self._pos = QPointF(0, 0)
        self.points = [QPointF(0, 0), QPointF(10, 10)]

    def pos(self):
        return self._pos

    def setPos(self, p):
        self._pos = p

    def prepareGeometryChange(self):
        pass

    def scene(self):
        return None

    def sceneBoundingRect(self):
        return items_mod.QRectF(0, 0, 10, 10)

    def update(self):
        pass


class _SizedLikeItem:
    def __init__(self):
        self._pos = QPointF(0, 0)
        self.size = 20.0

    def pos(self):
        return self._pos

    def setPos(self, p):
        self._pos = p

    def scene(self):
        return None

    def sceneBoundingRect(self):
        return items_mod.QRectF(self._pos.x(), self._pos.y(), 20, 20)

    def update(self):
        pass


class TestReactionGroupOverlay:
    def test_init_builds_scale_handle(self):
        overlay = ReactionGroupOverlay([])
        assert overlay.h_scale is not None

    def test_on_handle_moved_scale_arrow_like(self):
        arrow = _ArrowLikeItem()
        overlay = ReactionGroupOverlay([arrow])
        overlay._rect = items_mod.QRectF(0, 0, 10, 10)
        overlay.h_scale.setPos(QPointF(20, 20))
        overlay.on_handle_moved(overlay.h_scale)
        assert arrow.sync_calls >= 1
        assert arrow.end_p.x() != 10 or arrow.head_size != 10.0

    def test_on_handle_moved_scale_text_like(self):
        text_item = ReactionTextItem("A", QPointF(5, 5))
        overlay = ReactionGroupOverlay([text_item])
        overlay._rect = items_mod.QRectF(0, 0, 10, 10)
        overlay.h_scale.setPos(QPointF(20, 20))
        overlay.on_handle_moved(overlay.h_scale)

    def test_on_handle_moved_scale_rect_like(self):
        rect_item = _RectLikeItem()
        overlay = ReactionGroupOverlay([rect_item])
        overlay._rect = items_mod.QRectF(0, 0, 20, 20)
        overlay.h_scale.setPos(QPointF(40, 40))
        overlay.on_handle_moved(overlay.h_scale)
        assert rect_item.sync_calls >= 1

    def test_on_handle_moved_scale_freehand_like(self):
        fh = _FreehandLikeItem()
        overlay = ReactionGroupOverlay([fh])
        overlay._rect = items_mod.QRectF(0, 0, 10, 10)
        overlay.h_scale.setPos(QPointF(20, 20))
        overlay.on_handle_moved(overlay.h_scale)

    def test_on_handle_moved_scale_sized_like(self):
        sized = _SizedLikeItem()
        overlay = ReactionGroupOverlay([sized])
        overlay._rect = items_mod.QRectF(0, 0, 10, 10)
        overlay.h_scale.setPos(QPointF(20, 20))
        overlay.on_handle_moved(overlay.h_scale)
        assert sized.size != 20.0

    def test_on_handle_moved_returns_early_for_degenerate_rect(self):
        arrow = _ArrowLikeItem()
        overlay = ReactionGroupOverlay([arrow])
        overlay._rect = items_mod.QRectF(0, 0, 0.5, 0.5)
        overlay.h_scale.setPos(QPointF(1, 1))
        overlay.on_handle_moved(overlay.h_scale)  # must not raise

    def test_on_handle_moved_skips_deleted_items(self, monkeypatch):
        arrow = _ArrowLikeItem()
        monkeypatch.setattr(items_mod, "sip_isdeleted_safe", lambda x: True)
        overlay = ReactionGroupOverlay([arrow])
        overlay._rect = items_mod.QRectF(0, 0, 10, 10)
        overlay.h_scale.setPos(QPointF(20, 20))
        overlay.on_handle_moved(overlay.h_scale)
        assert arrow.sync_calls == 0

    def test_item_change_scene_change_connects_and_disconnects(self):
        overlay = ReactionGroupOverlay([])
        scene1 = MagicMock()
        overlay.itemChange(
            QGraphicsItem.GraphicsItemChange.ItemSceneChange, scene1
        )
        assert scene1.changed.connect.called

    def test_connect_scene_none_is_noop(self):
        overlay = ReactionGroupOverlay([])
        overlay._connect_scene(None)  # must not raise

    def test_disconnect_scene_none_is_noop(self):
        overlay = ReactionGroupOverlay([])
        overlay._disconnect_scene(None)  # must not raise

    def test_disconnect_scene_type_error_is_silenced(self):
        overlay = ReactionGroupOverlay([])
        scene = MagicMock()
        scene.changed.disconnect.side_effect = TypeError("not connected")
        overlay._disconnect_scene(scene)  # must not raise

    def test_disconnect_scene_runtime_error_is_silenced(self):
        overlay = ReactionGroupOverlay([])
        scene = MagicMock()
        scene.changed.disconnect.side_effect = RuntimeError("gone")
        overlay._disconnect_scene(scene)  # must not raise

    def test_connect_scene_error_is_silenced(self):
        overlay = ReactionGroupOverlay([])
        scene = MagicMock()
        scene.changed.connect.side_effect = RuntimeError("gone")
        overlay._connect_scene(scene)  # must not raise

    def test_on_scene_changed_reentrancy_guard(self):
        overlay = ReactionGroupOverlay([])
        overlay._updating = True
        overlay.on_scene_changed(None)  # returns immediately, must not raise
        overlay._updating = False
        overlay.on_scene_changed(None)

    def test_update_rect_handles_removed_item_runtime_error(self):
        class Flaky:
            def scene(self):
                raise RuntimeError("dead")

        overlay = ReactionGroupOverlay([Flaky()])
        overlay.update_rect()  # must not raise

    def test_bounding_rect_and_paint(self):
        overlay = ReactionGroupOverlay([])
        assert overlay.boundingRect() is overlay._rect
        overlay.paint(PAINTER, opt(True), None)

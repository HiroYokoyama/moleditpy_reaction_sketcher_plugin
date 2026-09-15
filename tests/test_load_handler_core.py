"""
tests/test_load_handler_core.py -- tests for utils.load_handler_core().

Uses a real QGraphicsScene so items are actually added and can be counted.
"""

import pytest
from PyQt6.QtCore import QPointF

from reaction_sketcher.utils import load_handler_core


class TestLoadHandlerCoreEmpty:
    def test_empty_list_adds_nothing(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [])
        assert len(mock_scene.items()) == 0

    def test_none_list_adds_nothing(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, None)
        assert len(mock_scene.items()) == 0


class TestLoadHandlerCoreArrows:
    def _arrow_data(self, type_tag="arrow"):
        return {"type": type_tag, "start_x": 0, "start_y": 0, "end_x": 100, "end_y": 50}

    def test_loads_arrow(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [self._arrow_data("arrow")])
        assert len(mock_scene.items()) == pytest.approx(1, abs=5)  # item + handles

    def test_loads_resonance_arrow(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [self._arrow_data("arrow_res")])
        assert len(mock_scene.items()) >= 1

    def test_loads_equilibrium_arrow(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [self._arrow_data("arrow_eq")])
        assert len(mock_scene.items()) >= 1

    def test_loads_retro_arrow(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [self._arrow_data("arrow_retro")])
        assert len(mock_scene.items()) >= 1

    def test_loads_no_arrow(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [self._arrow_data("arrow_no")])
        assert len(mock_scene.items()) >= 1

    def test_loads_dashed_arrow(self, mock_main_window, mock_scene):
        d = {
            "type": "arrow_dashed",
            "start_x": 0,
            "start_y": 0,
            "end_x": 80,
            "end_y": 0,
        }
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_loads_multiple_arrows(self, mock_main_window, mock_scene):
        data = [self._arrow_data("arrow"), self._arrow_data("arrow_res")]
        load_handler_core(mock_main_window, data)
        assert len(mock_scene.items()) >= 2


class TestLoadHandlerCoreSymbols:
    def test_loads_plus(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [{"type": "plus", "x": 10, "y": 20}])
        assert len(mock_scene.items()) >= 1

    def test_loads_minus(self, mock_main_window, mock_scene):
        load_handler_core(mock_main_window, [{"type": "minus", "x": 10, "y": 20}])
        assert len(mock_scene.items()) >= 1

    def test_plus_with_color(self, mock_main_window, mock_scene):
        load_handler_core(
            mock_main_window, [{"type": "plus", "x": 0, "y": 0, "color": "#ff0000"}]
        )
        assert len(mock_scene.items()) >= 1

    def test_plus_with_size(self, mock_main_window, mock_scene):
        load_handler_core(
            mock_main_window, [{"type": "plus", "x": 0, "y": 0, "size": 25}]
        )
        assert len(mock_scene.items()) >= 1


class TestLoadHandlerCoreShapes:
    def test_loads_bracket(self, mock_main_window, mock_scene):
        d = {"type": "bracket", "x": 0, "y": 0, "w": 50, "h": 80}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_loads_circle(self, mock_main_window, mock_scene):
        d = {"type": "circle", "x": 0, "y": 0, "w": 60, "h": 60}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_loads_line(self, mock_main_window, mock_scene):
        d = {"type": "line", "start_x": 0, "start_y": 0, "end_x": 100, "end_y": 0}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_loads_curved_line(self, mock_main_window, mock_scene):
        d = {
            "type": "line_curved",
            "start_x": 0,
            "start_y": 0,
            "end_x": 100,
            "end_y": 0,
        }
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_loads_freehand(self, mock_main_window, mock_scene):
        d = {"type": "freehand", "x": 0, "y": 0, "points": [[0, 0], [10, 5], [20, 0]]}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1


class TestLoadHandlerCoreText:
    def test_loads_text(self, mock_main_window, mock_scene):
        d = {"type": "text", "text": "A + B", "x": 50, "y": 50}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1

    def test_text_with_html(self, mock_main_window, mock_scene):
        d = {
            "type": "text",
            "text": "H2O",
            "x": 0,
            "y": 0,
            "html": "<b>H<sub>2</sub>O</b>",
        }
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1


class TestLoadHandlerCoreRobustness:
    def test_unknown_type_skipped(self, mock_main_window, mock_scene):
        """Unknown item types should not raise, just be silently ignored."""
        d = {"type": "nonexistent_item_type", "x": 0, "y": 0}
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) == 0

    def test_mixed_valid_and_unknown(self, mock_main_window, mock_scene):
        data = [
            {"type": "plus", "x": 0, "y": 0},
            {"type": "nonexistent", "x": 10, "y": 10},
            {"type": "minus", "x": 20, "y": 0},
        ]
        load_handler_core(mock_main_window, data)
        assert len(mock_scene.items()) >= 2  # plus + minus

    def test_unknown_type_with_rotation_does_not_raise(
        self, mock_main_window, mock_scene
    ):
        """Unknown item types combined with a 'rotation' key must not crash:
        item stays None for unrecognized types, so setRotation() must be
        guarded the same way group_id/addItem are."""
        d = {"type": "nonexistent_item_type", "x": 0, "y": 0, "rotation": 45.0}
        load_handler_core(mock_main_window, [d])  # should not raise
        assert len(mock_scene.items()) == 0

    def test_item_with_rotation(self, mock_main_window, mock_scene):
        d = {
            "type": "arrow",
            "start_x": 0,
            "start_y": 0,
            "end_x": 100,
            "end_y": 0,
            "rotation": 45.0,
        }
        load_handler_core(mock_main_window, [d])
        assert len(mock_scene.items()) >= 1


class TestCurvedRoundTrip:
    """Saving and reloading must not change how a curved item bends.

    The loader rebuilds the item with start_p at the origin, so a control
    point stored in the old local frame came back shifted by the old start_p
    — undo visibly changed the curvature of any arrow whose start handle had
    been dragged.
    """

    def _curved(self, cls_name, start, end, control):
        from reaction_sketcher import items as items_mod

        cls = getattr(items_mod, cls_name)
        item = cls(QPointF(*start), QPointF(*end))
        item.control_p = QPointF(*control)
        return item

    @pytest.mark.parametrize(
        "cls_name", ["ReactionCurvedArrowItem", "ReactionCurvedLineItem"]
    )
    def test_control_point_survives_a_shifted_start(
        self, mock_main_window, mock_scene, cls_name
    ):
        item = self._curved(cls_name, (20, 10), (120, 60), (70, -30))
        data = item.create_json_data()

        loaded = load_handler_core(mock_main_window, [data])[0]

        # Same curve in scene coordinates: pos + local control point.
        before = item.pos() + item.get_control_point()
        after = loaded.pos() + loaded.get_control_point()
        assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()))

    def test_legacy_data_without_the_offset_still_loads(
        self, mock_main_window, mock_scene
    ):
        item = self._curved("ReactionCurvedArrowItem", (0, 0), (100, 50), (50, -40))
        data = item.create_json_data()
        del data["cp_dx"], data["cp_dy"]

        loaded = load_handler_core(mock_main_window, [data])[0]

        cp = loaded.get_control_point()
        assert (cp.x(), cp.y()) == pytest.approx((50.0, -40.0))

    def test_curvature_only_data_keeps_its_automatic_control_point(
        self, mock_main_window, mock_scene
    ):
        loaded = load_handler_core(
            mock_main_window,
            [
                {
                    "type": "curved_double",
                    "start_x": 0,
                    "start_y": 0,
                    "end_x": 100,
                    "end_y": 0,
                    "curvature": 0.25,
                }
            ],
        )[0]
        assert loaded.control_p is None
        assert loaded.curvature == 0.25


class TestPropertiesRestoredOnLoad:
    def test_plus_keeps_its_line_width(self, mock_main_window, mock_scene):
        loaded = load_handler_core(
            mock_main_window,
            [{"type": "plus", "x": 0, "y": 0, "size": 20, "width": 7}],
        )[0]
        assert loaded.pen_width == 7

    def test_minus_keeps_its_line_width(self, mock_main_window, mock_scene):
        loaded = load_handler_core(
            mock_main_window,
            [{"type": "minus", "x": 0, "y": 0, "size": 20, "width": 7}],
        )[0]
        assert loaded.pen_width == 7

    def test_retro_arrow_keeps_its_double_arrow_offset(
        self, mock_main_window, mock_scene
    ):
        from reaction_sketcher.items import ReactionRetroArrowItem

        item = ReactionRetroArrowItem(QPointF(0, 0), QPointF(100, 0))
        item.double_arrow_offset = 9.5
        data = item.create_json_data()
        assert data["double_arrow_offset"] == 9.5

        loaded = load_handler_core(mock_main_window, [data])[0]
        assert loaded.double_arrow_offset == 9.5

"""
tests/test_items_json.py -- create_json_data() round-trip tests for all item types.

Each item is constructed, serialized to a dict, and the dict is validated for
required keys and correct type tag.  No scene/main_window is needed.
"""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from reaction_sketcher.items import (
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
)

START = QPointF(0, 0)
END = QPointF(100, 50)


# ---------------------------------------------------------------------------
# Arrow items
# ---------------------------------------------------------------------------


class TestReactionArrowItemJson:
    def test_type_tag(self, qapp):
        d = ReactionArrowItem(START, END).create_json_data()
        assert d["type"] == "arrow"

    def test_has_position_keys(self, qapp):
        d = ReactionArrowItem(START, END).create_json_data()
        for k in ("start_x", "start_y", "end_x", "end_y"):
            assert k in d, f"missing key {k!r}"

    def test_color_key(self, qapp):
        item = ReactionArrowItem(START, END)
        item.pen_color = QColor("red")
        d = item.create_json_data()
        assert "color" in d

    def test_width_key(self, qapp):
        d = ReactionArrowItem(START, END).create_json_data()
        assert "width" in d


class TestReactionResonanceArrowJson:
    def test_type_tag(self, qapp):
        assert (
            ReactionResonanceArrowItem(START, END).create_json_data()["type"]
            == "arrow_res"
        )


class TestReactionEquilibriumArrowJson:
    def test_type_tag(self, qapp):
        assert (
            ReactionEquilibriumArrowItem(START, END).create_json_data()["type"]
            == "arrow_eq"
        )


class TestReactionRetroArrowJson:
    def test_type_tag(self, qapp):
        assert (
            ReactionRetroArrowItem(START, END).create_json_data()["type"]
            == "arrow_retro"
        )


class TestReactionNoArrowJson:
    def test_type_tag(self, qapp):
        assert ReactionNoArrowItem(START, END).create_json_data()["type"] == "arrow_no"


class TestReactionDashedArrowJson:
    def test_type_tag(self, qapp):
        assert (
            ReactionDashedArrowItem(START, END).create_json_data()["type"]
            == "arrow_dashed"
        )

    def test_has_position_keys(self, qapp):
        d = ReactionDashedArrowItem(START, END).create_json_data()
        for k in ("start_x", "start_y", "end_x", "end_y"):
            assert k in d


# ---------------------------------------------------------------------------
# Curved arrow
# ---------------------------------------------------------------------------


class TestReactionCurvedArrowJson:
    def test_double_type_tag(self, qapp):
        item = ReactionCurvedArrowItem(START, END, is_fish_hook=False)
        assert item.create_json_data()["type"] == "curved_double"

    def test_fishhook_type_tag(self, qapp):
        item = ReactionCurvedArrowItem(START, END, is_fish_hook=True)
        assert item.create_json_data()["type"] in ("curved_fish", "curved_single")

    def test_has_control_point(self, qapp):
        d = ReactionCurvedArrowItem(START, END).create_json_data()
        assert "cp_x" in d and "cp_y" in d


# ---------------------------------------------------------------------------
# Simple symbols
# ---------------------------------------------------------------------------


class TestReactionPlusItemJson:
    def test_type_tag(self, qapp):
        assert ReactionPlusItem(QPointF(10, 20)).create_json_data()["type"] == "plus"

    def test_has_xy(self, qapp):
        d = ReactionPlusItem(QPointF(10, 20)).create_json_data()
        assert "x" in d and "y" in d

    def test_set_size_reflected_in_json(self, qapp):
        item = ReactionPlusItem(QPointF(0, 0))
        item.set_size(30)
        assert item.create_json_data()["size"] == 30


class TestReactionMinusItemJson:
    def test_type_tag(self, qapp):
        assert ReactionMinusItem(QPointF(0, 0)).create_json_data()["type"] == "minus"

    def test_has_xy(self, qapp):
        d = ReactionMinusItem(QPointF(5, 5)).create_json_data()
        assert "x" in d and "y" in d


# ---------------------------------------------------------------------------
# Shape items
# ---------------------------------------------------------------------------


class TestReactionBracketItemJson:
    def test_type_tag(self, qapp):
        item = ReactionBracketItem(QPointF(0, 0), QPointF(50, 80))
        assert item.create_json_data()["type"] == "bracket"

    def test_has_geometry_keys(self, qapp):
        d = ReactionBracketItem(QPointF(0, 0), QPointF(50, 80)).create_json_data()
        for k in ("x", "y", "w", "h"):
            assert k in d, f"missing key {k!r}"


class TestReactionCircleItemJson:
    def test_type_tag(self, qapp):
        item = ReactionCircleItem(QPointF(0, 0), QPointF(60, 60))
        assert item.create_json_data()["type"] == "circle"

    def test_has_geometry_keys(self, qapp):
        d = ReactionCircleItem(QPointF(0, 0), QPointF(60, 60)).create_json_data()
        for k in ("x", "y", "w", "h"):
            assert k in d

    def test_fill_color_defaults_to_none(self, qapp):
        # Default frame is outline-only (fill_color None) so its create_json_data
        # records None and its shape() is border-only / click-through.
        item = ReactionCircleItem(QPointF(0, 0), QPointF(60, 60))
        assert item.fill_color is None
        assert item.create_json_data()["fill_color"] is None


# ---------------------------------------------------------------------------
# Line items
# ---------------------------------------------------------------------------


class TestReactionLineItemJson:
    def test_type_tag(self, qapp):
        assert ReactionLineItem(START, END).create_json_data()["type"] == "line"

    def test_has_position_keys(self, qapp):
        d = ReactionLineItem(START, END).create_json_data()
        for k in ("start_x", "start_y", "end_x", "end_y"):
            assert k in d


class TestReactionCurvedLineItemJson:
    def test_type_tag(self, qapp):
        assert (
            ReactionCurvedLineItem(START, END).create_json_data()["type"]
            == "line_curved"
        )

    def test_has_control_point(self, qapp):
        d = ReactionCurvedLineItem(START, END).create_json_data()
        assert "cp_x" in d and "cp_y" in d


# ---------------------------------------------------------------------------
# Freehand
# ---------------------------------------------------------------------------


class TestReactionFreehandItemJson:
    def test_type_tag(self, qapp):
        item = ReactionFreehandItem(QPointF(0, 0))
        assert item.create_json_data()["type"] == "freehand"

    def test_empty_points(self, qapp):
        item = ReactionFreehandItem(QPointF(0, 0))
        d = item.create_json_data()
        assert "points" in d
        assert isinstance(d["points"], list)

    def test_set_points_reflected(self, qapp):
        item = ReactionFreehandItem(QPointF(0, 0))
        pts = [QPointF(1, 2), QPointF(3, 4), QPointF(5, 6)]
        item.set_points(pts)
        d = item.create_json_data()
        assert len(d["points"]) == 3


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


class TestReactionTextItemJson:
    def test_type_tag(self, qapp):
        item = ReactionTextItem("A + B", QPointF(0, 0))
        d = item.create_json_data()
        assert d["type"] == "text"

    def test_text_preserved(self, qapp):
        item = ReactionTextItem("H2O", QPointF(0, 0))
        d = item.create_json_data()
        assert "text" in d
        assert d["text"] == "H2O"

    def test_has_position(self, qapp):
        d = ReactionTextItem("X", QPointF(10, 20)).create_json_data()
        assert "x" in d and "y" in d

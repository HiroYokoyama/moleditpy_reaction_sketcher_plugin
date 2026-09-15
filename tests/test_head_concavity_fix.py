from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPointF
from reaction_sketcher.items import (
    ReactionArrowItem,
    ReactionCurvedArrowItem,
    ReactionDashedArrowItem,
)
from reaction_sketcher.utils import load_handler_core


class _CollectingScene:
    def __init__(self):
        self.items = []

    def addItem(self, item):
        self.items.append(item)


def test_arrow_head_concavity_in_json(qapp):
    arrow = ReactionArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.8
    data = arrow.create_json_data()
    assert "head_concavity" in data
    assert data["head_concavity"] == pytest.approx(0.8)


def test_dashed_arrow_head_concavity_in_json(qapp):
    arrow = ReactionDashedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.35
    arrow.head_side = -1
    data = arrow.create_json_data()
    assert "head_concavity" in data
    assert data["head_concavity"] == pytest.approx(0.35)


def test_curved_arrow_head_concavity_survives_a_reload(qapp):
    arrow = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.9
    data = arrow.create_json_data()
    assert data["head_concavity"] == pytest.approx(0.9)

    mw = SimpleNamespace(scene=_CollectingScene())
    restored = load_handler_core(mw, [data])
    assert restored[0].head_concavity == pytest.approx(0.9)


def test_dashed_arrow_head_concavity_survives_a_reload(qapp):
    arrow = ReactionDashedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.25
    arrow.head_side = -1
    mw = SimpleNamespace(scene=_CollectingScene())
    restored = load_handler_core(mw, [arrow.create_json_data()])
    assert restored[0].head_concavity == pytest.approx(0.25)
    assert restored[0].head_side == -1

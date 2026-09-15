import pytest
from PyQt6.QtCore import QPointF
from reaction_sketcher.items import ReactionArrowItem, ReactionDashedArrowItem
from reaction_sketcher.utils import load_handler_core


def test_arrow_head_concavity_in_json(qapp):
    arrow = ReactionArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.8
    data = arrow.create_json_data()
    assert 'head_concavity' in data
    assert data['head_concavity'] == pytest.approx(0.8)


def test_dashed_arrow_head_concavity_in_json(qapp):
    arrow = ReactionDashedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_concavity = 0.35
    arrow.head_side = -1
    data = arrow.create_json_data()
    assert 'head_concavity' in data
    assert data['head_concavity'] == pytest.approx(0.35)

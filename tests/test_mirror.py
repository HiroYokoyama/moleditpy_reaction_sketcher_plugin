import pytest
from PyQt6.QtCore import QPointF, QRectF
from reaction_sketcher.items import (
    mirror_point,
    ReactionArrowItem,
    ReactionPlusItem,
    ReactionMinusItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionCurvedArrowItem,
    ReactionFreehandItem,
    ReactionTextItem,
)


def test_mirror_point_vertical():
    center = QPointF(100, 100)
    p = QPointF(120, 150)
    mirrored = mirror_point(p, center, 'v')
    assert mirrored.x() == pytest.approx(80.0)
    assert mirrored.y() == pytest.approx(150.0)


def test_mirror_point_horizontal():
    center = QPointF(100, 100)
    p = QPointF(120, 150)
    mirrored = mirror_point(p, center, 'h')
    assert mirrored.x() == pytest.approx(120.0)
    assert mirrored.y() == pytest.approx(50.0)


def test_mirror_point_at_center():
    center = QPointF(50, 50)
    assert mirror_point(center, center, 'v') == center
    assert mirror_point(center, center, 'h') == center


def test_reaction_arrow_mirror_v_in_place(qapp):
    arrow = ReactionArrowItem(QPointF(10, 20), QPointF(50, 20))
    # Center of arrow in scene coords
    p1 = arrow.mapToScene(arrow.start_p)
    p2 = arrow.mapToScene(arrow.end_p)
    center = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
    arrow.mirror_around(center, 'v')
    # Arrow should flip in place: start and end X swapped, center unchanged
    new_p1 = arrow.mapToScene(arrow.start_p)
    new_p2 = arrow.mapToScene(arrow.end_p)
    assert new_p1.x() == pytest.approx(50.0)
    assert new_p2.x() == pytest.approx(10.0)
    assert arrow.pos().x() == pytest.approx(30.0)


def test_reaction_arrow_mirror_h_in_place(qapp):
    arrow = ReactionArrowItem(QPointF(20, 10), QPointF(20, 50))
    p1 = arrow.mapToScene(arrow.start_p)
    p2 = arrow.mapToScene(arrow.end_p)
    center = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
    arrow.mirror_around(center, 'h')
    new_p1 = arrow.mapToScene(arrow.start_p)
    new_p2 = arrow.mapToScene(arrow.end_p)
    assert new_p1.y() == pytest.approx(50.0)
    assert new_p2.y() == pytest.approx(10.0)
    assert arrow.pos().y() == pytest.approx(30.0)


def test_curved_arrow_mirror(qapp):
    arrow = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.control_p = QPointF(50, -50)
    center = QPointF(50, 0)
    arrow.mirror_around(center, 'h')
    new_cp = arrow.mapToScene(arrow.control_p)
    assert new_cp.y() == pytest.approx(50.0)


def test_plus_minus_mirror(qapp):
    center = QPointF(100, 100)
    plus = ReactionPlusItem(QPointF(120, 130))
    plus.setRotation(30)
    plus.mirror_around(center, 'v')
    assert plus.pos().x() == pytest.approx(80.0)
    assert plus.pos().y() == pytest.approx(130.0)
    assert plus.rotation() == pytest.approx(-30.0)

    minus = ReactionMinusItem(QPointF(120, 130))
    minus.setRotation(45)
    minus.mirror_around(center, 'h')
    assert minus.pos().x() == pytest.approx(120.0)
    assert minus.pos().y() == pytest.approx(70.0)
    assert minus.rotation() == pytest.approx(135.0)


def test_text_item_mirror(qapp):
    center = QPointF(100, 100)
    txt = ReactionTextItem('Reaction', QPointF(120, 100))
    txt.mirror_around(center, 'v')
    assert txt.pos().x() == pytest.approx(80.0)


def test_freehand_item_mirror(qapp):
    center = QPointF(100, 100)
    fh = ReactionFreehandItem(QPointF(120, 100))
    fh.points = [QPointF(0, 0), QPointF(10, 20)]
    fh.mirror_around(center, 'v')
    assert fh.pos().x() == pytest.approx(80.0)
    assert fh.points[1].x() == pytest.approx(-10.0)
    assert fh.points[1].y() == pytest.approx(20.0)

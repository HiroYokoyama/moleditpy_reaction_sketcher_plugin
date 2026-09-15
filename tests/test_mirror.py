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
    mirrored = mirror_point(p, center, "v")
    assert mirrored.x() == pytest.approx(80.0)
    assert mirrored.y() == pytest.approx(150.0)


def test_mirror_point_horizontal():
    center = QPointF(100, 100)
    p = QPointF(120, 150)
    mirrored = mirror_point(p, center, "h")
    assert mirrored.x() == pytest.approx(120.0)
    assert mirrored.y() == pytest.approx(50.0)


def test_mirror_point_at_center():
    center = QPointF(50, 50)
    assert mirror_point(center, center, "v") == center
    assert mirror_point(center, center, "h") == center


def test_reaction_arrow_mirror_v_in_place(qapp):
    arrow = ReactionArrowItem(QPointF(10, 20), QPointF(50, 20))
    # Center of arrow in scene coords
    p1 = arrow.mapToScene(arrow.start_p)
    p2 = arrow.mapToScene(arrow.end_p)
    center = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
    arrow.mirror_around(center, "v")
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
    arrow.mirror_around(center, "h")
    new_p1 = arrow.mapToScene(arrow.start_p)
    new_p2 = arrow.mapToScene(arrow.end_p)
    assert new_p1.y() == pytest.approx(50.0)
    assert new_p2.y() == pytest.approx(10.0)
    assert arrow.pos().y() == pytest.approx(30.0)


def test_curved_arrow_mirror(qapp):
    arrow = ReactionCurvedArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.control_p = QPointF(50, -50)
    center = QPointF(50, 0)
    arrow.mirror_around(center, "h")
    new_cp = arrow.mapToScene(arrow.control_p)
    assert new_cp.y() == pytest.approx(50.0)


def test_plus_minus_mirror(qapp):
    center = QPointF(100, 100)
    plus = ReactionPlusItem(QPointF(120, 130))
    plus.setRotation(30)
    plus.mirror_around(center, "v")
    assert plus.pos().x() == pytest.approx(80.0)
    assert plus.pos().y() == pytest.approx(130.0)
    assert plus.rotation() == pytest.approx(-30.0)

    minus = ReactionMinusItem(QPointF(120, 130))
    minus.setRotation(45)
    minus.mirror_around(center, "h")
    assert minus.pos().x() == pytest.approx(120.0)
    assert minus.pos().y() == pytest.approx(70.0)
    # Reflection maps the angle to -angle for either axis, once the glyph's own
    # (symmetric) geometry is accounted for. 180-angle would spin it instead.
    assert minus.rotation() == pytest.approx(-45.0)


def test_rect_shaped_items_mirror_by_their_centre(qapp):
    # pos() is the top-left of a bracket/circle, so mirroring pos() would shift
    # the item sideways by its own width instead of flipping it in place.
    center = QPointF(100, 100)
    for cls in (ReactionBracketItem, ReactionCircleItem):
        item = cls(QPointF(100, 90), QPointF(160, 110))
        before = item.sceneBoundingRect().center()
        item.mirror_around(center, "v")
        after = item.sceneBoundingRect().center()
        assert after.x() == pytest.approx(2 * center.x() - before.x())
        assert after.y() == pytest.approx(before.y())


def test_single_sided_bracket_swaps_side_on_horizontal_flip(qapp):
    item = ReactionBracketItem(QPointF(0, 0), QPointF(50, 40))
    item.bracket_type = "square_left"
    item.mirror_around(QPointF(100, 100), "v")
    assert item.bracket_type == "square_right"
    item.mirror_around(QPointF(100, 100), "v")
    assert item.bracket_type == "square_left"
    # A vertical flip leaves a bracket unchanged; it is symmetric about its own
    # horizontal axis.
    item.mirror_around(QPointF(100, 100), "h")
    assert item.bracket_type == "square_left"


def test_text_item_mirror(qapp):
    center = QPointF(100, 100)
    txt = ReactionTextItem("Reaction", QPointF(120, 100))
    before = txt.sceneBoundingRect().center()
    txt.mirror_around(center, "v")
    after = txt.sceneBoundingRect().center()
    assert after.x() == pytest.approx(2 * center.x() - before.x())
    # Text stays upright: a flipped label must remain readable.
    assert txt.rotation() == pytest.approx(0.0)


def test_freehand_item_mirror(qapp):
    center = QPointF(100, 100)
    fh = ReactionFreehandItem(QPointF(120, 100))
    fh.points = [QPointF(0, 0), QPointF(10, 20)]
    fh.mirror_around(center, "v")
    assert fh.pos().x() == pytest.approx(80.0)
    assert fh.points[1].x() == pytest.approx(-10.0)
    assert fh.points[1].y() == pytest.approx(20.0)


def test_arrow_mirror_flips_the_asymmetric_head(qapp):
    arrow = ReactionArrowItem(QPointF(0, 0), QPointF(100, 0))
    arrow.head_side = 1
    arrow.mirror_around(QPointF(50, 0), "h")
    assert arrow.head_side == -1
    arrow.mirror_around(QPointF(50, 0), "h")
    assert arrow.head_side == 1


def test_freehand_mirror_flips_rotation_for_either_axis(qapp):
    for axis in ("h", "v"):
        fh = ReactionFreehandItem(QPointF(120, 100))
        fh.points = [QPointF(0, 0), QPointF(10, 20)]
        fh.setRotation(25)
        fh.mirror_around(QPointF(100, 100), axis)
        # Local points are mirrored too, so the angle maps to -angle, not 180-angle.
        assert fh.rotation() == pytest.approx(-25.0)


def test_double_mirror_is_the_identity(qapp):
    center = QPointF(100, 100)
    for axis in ("h", "v"):
        arrow = ReactionArrowItem(QPointF(40, 60), QPointF(90, 130))
        start = arrow.mapToScene(arrow.start_p)
        end = arrow.mapToScene(arrow.end_p)
        arrow.mirror_around(center, axis)
        arrow.mirror_around(center, axis)
        assert arrow.mapToScene(arrow.start_p).x() == pytest.approx(start.x())
        assert arrow.mapToScene(arrow.start_p).y() == pytest.approx(start.y())
        assert arrow.mapToScene(arrow.end_p).x() == pytest.approx(end.x())
        assert arrow.mapToScene(arrow.end_p).y() == pytest.approx(end.y())

        plus = ReactionPlusItem(QPointF(40, 60))
        plus.mirror_around(center, axis)
        plus.mirror_around(center, axis)
        assert plus.pos().x() == pytest.approx(40.0)
        assert plus.pos().y() == pytest.approx(60.0)

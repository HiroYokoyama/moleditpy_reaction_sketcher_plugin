import logging


def sip_isdeleted_safe(obj):
    """Check if a PyQt object has been deleted at the C++ level."""
    if obj is None:
        return True

    # Try PyQt6.sip (Standard for modern PyQt6 environments)
    try:
        from PyQt6 import sip

        return sip.isdeleted(obj)
    except ImportError:
        pass

    # Try top-level sip (Legacy or specific environments)
    try:
        import sip

        return sip.isdeleted(obj)
    except Exception as _e:
        logging.warning("silenced: %s", _e)

    # If we truly cannot check, assume it is NOT deleted to allow functionality.
    # The RuntimeError is worse than a potential crash in some cases,
    # but False prevents total failure of the plugin if sip is missing.
    return False


def get_main_window(scene):
    """Helper to get the main window from a scene."""
    if not scene:
        return None
    views = scene.views()
    if views:
        # The view's window() method returns the top-level window
        return views[0].window()
    return None


def load_handler_core(main_window, reaction_items):
    """
    Core function to load reaction items from a list of dictionaries.
    Moved here to avoid circular imports between __init__.py and patcher.py.
    """
    from .items import (
        ReactionArrowItem,
        ReactionResonanceArrowItem,
        ReactionEquilibriumArrowItem,
        ReactionRetroArrowItem,
        ReactionNoArrowItem,
        ReactionCurvedArrowItem,
        ReactionDashedArrowItem,
        ReactionLineItem,
        ReactionCurvedLineItem,
        ReactionFreehandItem,
        ReactionPlusItem,
        ReactionMinusItem,
        ReactionBracketItem,
        ReactionCircleItem,
        ReactionTextItem,
    )
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    if not reaction_items:
        return

    for item_data in reaction_items:
        item_type = item_data.get("type", None)
        item = None

        if item_type in ["arrow", "arrow_res", "arrow_eq", "arrow_retro", "arrow_no"]:
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            if item_type == "arrow":
                item = ReactionArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_res":
                item = ReactionResonanceArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_eq":
                item = ReactionEquilibriumArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_retro":
                item = ReactionRetroArrowItem(QPointF(0, 0), QPointF(dx, dy))
            elif item_type == "arrow_no":
                item = ReactionNoArrowItem(QPointF(0, 0), QPointF(dx, dy))

            if item:
                item.setPos(item_data["start_x"], item_data["start_y"])
                if "color" in item_data:
                    item.pen_color = QColor(item_data["color"])
                if "width" in item_data:
                    item.pen_width = item_data["width"]
                if "head_size" in item_data:
                    item.head_size = item_data["head_size"]
                if "head_angle" in item_data:
                    item.head_angle = item_data["head_angle"]
                if "head_concavity" in item_data and hasattr(item, "head_concavity"):
                    item.head_concavity = item_data["head_concavity"]
                if "negation_style" in item_data and hasattr(item, "negation_style"):
                    item.negation_style = item_data["negation_style"]
                if "head_style" in item_data and hasattr(item, "head_style"):
                    item.head_style = item_data["head_style"]
                item.sync_handles()  # Ensure handles match loaded data

        elif item_type in ["curved_double", "curved_fish", "curved_single"]:
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            is_fish = item_type in ["curved_fish", "curved_single"]
            item = ReactionCurvedArrowItem(
                QPointF(0, 0), QPointF(dx, dy), is_fish_hook=is_fish
            )
            item.setPos(item_data["start_x"], item_data["start_y"])
            if "cp_x" in item_data and "cp_y" in item_data:
                # Coordinate is local if it was saved as local?
                # In items.py create_json_data we saved cp directly.
                # If item was moved, cp is relative to item pos?
                # ReactionCurvedArrowItem expects local control_p logic.
                item.control_p = QPointF(item_data["cp_x"], item_data["cp_y"])
                item.sync_handles()
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "head_size" in item_data:
                item.head_size = item_data["head_size"]
            if "head_angle" in item_data:
                item.head_angle = item_data["head_angle"]
            if "head_style" in item_data:
                item.head_style = item_data["head_style"]
            if "curvature" in item_data:
                item.curvature = item_data["curvature"]
            item.sync_handles()

        elif item_type == "arrow_dashed":
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            item = ReactionDashedArrowItem(QPointF(0, 0), QPointF(dx, dy))
            item.setPos(item_data["start_x"], item_data["start_y"])
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "head_style" in item_data:
                item.head_style = item_data["head_style"]
            if "head_size" in item_data:
                item.head_size = item_data["head_size"]
            if "head_angle" in item_data:
                item.head_angle = item_data["head_angle"]
            item.sync_handles()

        elif item_type == "line":
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            item = ReactionLineItem(QPointF(0, 0), QPointF(dx, dy))
            item.setPos(item_data["start_x"], item_data["start_y"])
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "line_style" in item_data:
                item.line_style = item_data["line_style"]
            item.sync_handles()

        elif item_type == "line_curved":
            dx = item_data["end_x"] - item_data["start_x"]
            dy = item_data["end_y"] - item_data["start_y"]
            item = ReactionCurvedLineItem(QPointF(0, 0), QPointF(dx, dy))
            item.setPos(item_data["start_x"], item_data["start_y"])
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "line_style" in item_data:
                item.line_style = item_data["line_style"]
            if "cp_x" in item_data and "cp_y" in item_data:
                item.control_p = QPointF(item_data["cp_x"], item_data["cp_y"])
            if "curvature" in item_data:
                item.curvature = item_data["curvature"]
            item.sync_handles()

        elif item_type == "freehand":
            item = ReactionFreehandItem(QPointF(0, 0))
            item.setPos(item_data["x"], item_data["y"])
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]

            raw_points = item_data.get("points", [])
            points = [QPointF(p[0], p[1]) for p in raw_points]
            item.set_points(points)

        elif item_type == "plus":
            item = ReactionPlusItem(QPointF(item_data["x"], item_data["y"]))
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "size" in item_data:
                item.set_size(item_data["size"])

        elif item_type == "minus":
            item = ReactionMinusItem(QPointF(item_data["x"], item_data["y"]))
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "size" in item_data:
                item.set_size(item_data["size"])

        elif item_type == "bracket":
            item = ReactionBracketItem(
                QPointF(item_data["x"], item_data["y"]),
                QPointF(
                    item_data["x"] + item_data["w"], item_data["y"] + item_data["h"]
                ),
            )
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "bracket_type" in item_data:
                item.bracket_type = item_data["bracket_type"]
            if "line_style" in item_data:
                item.line_style = item_data["line_style"]

        elif item_type == "circle":
            item = ReactionCircleItem(
                QPointF(item_data["x"], item_data["y"]),
                QPointF(
                    item_data["x"] + item_data["w"], item_data["y"] + item_data["h"]
                ),
            )
            if "color" in item_data:
                item.pen_color = QColor(item_data["color"])
            if "width" in item_data:
                item.pen_width = item_data["width"]
            if "shape_type" in item_data:
                item.shape_type = item_data["shape_type"]
            if "line_style" in item_data:
                item.line_style = item_data["line_style"]
            if item_data.get("fill_color") is not None:
                item.fill_color = QColor(item_data["fill_color"])

        elif item_type == "text":
            item = ReactionTextItem(
                item_data["text"], QPointF(item_data["x"], item_data["y"])
            )
            if "html" in item_data:
                item.setHtml(item_data["html"])
            if "color" in item_data:
                item.setDefaultTextColor(QColor(item_data["color"]))
            if (
                "font_family" in item_data
            ):  # Apply font regardless of HTML to ensure defaults
                f = item.font()
                f.setFamily(item_data["font_family"])
                f.setPointSize(int(item_data.get("font_size", 14)))
                f.setBold(item_data.get("bold", False))
                f.setItalic(item_data.get("italic", False))
                f.setUnderline(item_data.get("underline", False))
                item.setFont(f)

        if item:
            if "rotation" in item_data:
                item.setRotation(item_data["rotation"])
            if "group_id" in item_data:
                item.group_id = item_data["group_id"]
            main_window.scene.addItem(item)

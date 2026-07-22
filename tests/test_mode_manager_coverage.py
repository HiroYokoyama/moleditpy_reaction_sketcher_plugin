"""
tests/test_mode_manager_coverage.py -- coverage-focused tests for
reaction_sketcher/mode_manager.py (ModeManager).

ModeManager is constructed with a FakeMainWindow (tests/rs_fakes.py) standing
in for the real MainWindow, and a MagicMock context (mirrors the pattern used
in test_interaction_coverage.py). Qt widget classes used purely for UI
plumbing (QToolBar, QComboBox, QMenu, ...) come from the conftest.py stubs
(mostly permissive MagicMocks); QAction/QActionGroup are replaced with small
real stand-ins so action_group.actions() / action.property()/.setChecked()
behave like real Qt so the tool-switching logic can be exercised for real.
"""

import time
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor

import reaction_sketcher.mode_manager as mm_mod
from reaction_sketcher.mode_manager import ModeManager
from reaction_sketcher.items import (
    ReactionArrowItem,
    ReactionDashedArrowItem,
    ReactionResonanceArrowItem,
    ReactionEquilibriumArrowItem,
    ReactionRetroArrowItem,
    ReactionCurvedArrowItem,
    ReactionNoArrowItem,
    ReactionBracketItem,
    ReactionCircleItem,
    ReactionTextItem,
)

from tests.rs_fakes import (
    FakeMainWindow,
    FakeAtomItem,
    FakeBondItem,
    FakeSignal,
)


# ---------------------------------------------------------------------------
# Lightweight real stand-ins for QAction / QActionGroup so tool-switching
# logic (action.property("tool_name"), setChecked/isChecked, actions()) works
# for real instead of via MagicMock auto-attributes.
# ---------------------------------------------------------------------------


class FakeQAction:
    def __init__(self, *args, **kwargs):
        self._props = {}
        self._checkable = False
        self._checked = False
        self._enabled = True
        self._text = ""
        for a in args:
            if isinstance(a, str):
                self._text = a
        self.triggered = FakeSignal()

    def setCheckable(self, v):
        self._checkable = v

    def isCheckable(self):
        return self._checkable

    def setChecked(self, v):
        self._checked = v

    def isChecked(self):
        return self._checked

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text

    def setToolTip(self, t):
        self._tooltip = t

    def setProperty(self, k, v):
        self._props[k] = v

    def property(self, k):
        return self._props.get(k)

    def setIcon(self, i):
        pass

    def setShortcut(self, s):
        pass

    def setFont(self, f):
        pass

    def setEnabled(self, v):
        self._enabled = v

    def isEnabled(self):
        return self._enabled

    def menu(self):
        return None


class FakeToolButton:
    """Stand-in for QToolButton with a real setProperty/property store (the
    conftest.py stub uses one shared MagicMock singleton for all QToolButton
    instances, which makes per-button state like the color swatch
    unobservable)."""

    def __init__(self, *args, **kwargs):
        self._props = {}
        self._stylesheet = ""
        self.pressed = FakeSignal()
        self.clicked = FakeSignal()
        self.customContextMenuRequested = FakeSignal()
        self.triggered = FakeSignal()

    def setCheckable(self, v):
        pass

    def setIconSize(self, s):
        pass

    def setToolTip(self, t):
        pass

    def setDefaultAction(self, a):
        self._action = a

    def setFixedSize(self, *a):
        pass

    def setContextMenuPolicy(self, p):
        pass

    def setProperty(self, k, v):
        self._props[k] = v

    def property(self, k):
        return self._props.get(k)

    def setStyleSheet(self, s):
        self._stylesheet = s

    def height(self):
        return 20

    def mapToGlobal(self, p):
        return p


class FakeActionGroup:
    def __init__(self, *args, **kwargs):
        self._actions = []
        self._exclusive = True

    def setExclusive(self, v):
        self._exclusive = v

    def addAction(self, action_or_text):
        if isinstance(action_or_text, str):
            act = FakeQAction(action_or_text)
        else:
            act = action_or_text
        self._actions.append(act)
        return act

    def actions(self):
        return list(self._actions)


class FakeMenuAction:
    """Stand-in for a QAction living in the real application's menu tree."""

    def __init__(self, text, submenu=None):
        self._text = text
        self._submenu = submenu
        self.triggered = FakeSignal()

    def text(self):
        return self._text

    def menu(self):
        return self._submenu


class FakeMenu:
    def __init__(self, actions=None):
        self._actions = actions or []

    def actions(self):
        return list(self._actions)


class FakeMenuBar:
    def __init__(self, top_actions):
        self._top_actions = top_actions

    def actions(self):
        return list(self._top_actions)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_action_classes(monkeypatch):
    """Swap the real QAction/QActionGroup imports in mode_manager for our
    controllable fakes so action_group.actions() driven logic works."""
    monkeypatch.setattr(mm_mod, "QAction", FakeQAction)
    monkeypatch.setattr(mm_mod, "QActionGroup", FakeActionGroup)
    monkeypatch.setattr(mm_mod, "QToolButton", FakeToolButton)
    yield


@pytest.fixture(autouse=True)
def _patch_patcher_calls(monkeypatch):
    """apply_core_patches/apply_interaction_patches/revert_all_patches belong
    to patcher.py (covered by test_patcher_coverage.py); stub them out here
    so enter/exit_reaction_mode tests stay focused on ModeManager's own
    orchestration logic."""
    monkeypatch.setattr(mm_mod, "apply_core_patches", MagicMock())
    monkeypatch.setattr(mm_mod, "apply_interaction_patches", MagicMock())
    monkeypatch.setattr(mm_mod, "revert_all_patches", MagicMock())
    yield


def make_mm(with_toolbar=False):
    mw = FakeMainWindow()
    mw.edit_actions_manager.clean_up_2d_structure = MagicMock()
    context = MagicMock()
    mgr = ModeManager(mw, context)
    if with_toolbar:
        mgr.setup_toolbar()
    return mgr, mw, context


def add_arrow(mw, cls=ReactionArrowItem, start=None, end=None, select=True):
    item = cls(start or QPointF(0, 0), end or QPointF(50, 0))
    mw.scene.addItem(item)
    if select:
        item.setSelected(True)
    return item


def add_text(mw, text="Hello", pos=None, select=True):
    item = ReactionTextItem(text, pos or QPointF(0, 0))
    mw.scene.addItem(item)
    if select:
        item.setSelected(True)
    return item


# ===========================================================================
# Construction / load_defaults
# ===========================================================================


class TestConstructionAndDefaults:
    def test_construct_basic(self):
        mgr, mw, ctx = make_mm()
        assert mgr.main_window is mw
        assert mgr.context is ctx
        assert mgr.is_reaction_mode is False
        assert mgr.default_bracket_type == "square"

    def test_load_defaults_no_file(self, tmp_path, monkeypatch):
        # os.path.dirname(__file__)/settings.json most likely doesn't exist
        mgr, mw, ctx = make_mm()
        assert mgr.default_props == {}

    def test_load_defaults_with_settings_file(self, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            """
            {
                "templates": {
                    "Default_arrow": {"head_style": "triangle", "double_arrow_offset": 6.0},
                    "Default_arrow_eq": {"head_style": "harpoon", "double_arrow_offset": 8.0},
                    "Default_arrow_res": {"head_style": "barb"},
                    "Default_arrow_retro": {"head_style": "chevron"},
                    "Default_arrow_no": {"head_style": "triangle", "negation_style": "cross", "cross_size": 10},
                    "Default_bracket": {"bracket_type": "round"},
                    "Default_circle": {"shape_type": "circle", "line_style": "dashed"}
                }
            }
            """
        )
        monkeypatch.setattr(
            mm_mod.os.path, "dirname", lambda p: str(tmp_path)
        )
        mgr, mw, ctx = make_mm()
        assert mgr.default_head_styles["arrow"] == "triangle"
        assert mgr.default_head_styles["arrow_dashed"] == "triangle"
        assert mgr.default_double_arrow_offset == 8.0
        assert mgr.default_head_styles["arrow_eq"] == "harpoon"
        assert mgr.default_head_styles["arrow_res"] == "barb"
        assert mgr.default_head_styles["arrow_retro"] == "chevron"
        assert mgr.default_head_styles["arrow_no"] == "triangle"
        assert mgr.default_no_arrow_style == "cross"
        assert mgr.default_bracket_type == "round"
        assert mgr.default_circle_shape_type == "circle"
        assert mgr.default_circle_line_style == "dashed"

    def test_load_defaults_malformed_json_is_silenced(self, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{not valid json")
        monkeypatch.setattr(mm_mod.os.path, "dirname", lambda p: str(tmp_path))
        # Should not raise
        mgr, mw, ctx = make_mm()
        assert mgr.default_props == {}


# ===========================================================================
# _find_menu_action / _rewire_cleanup_2d_triggers
# ===========================================================================


class TestMenuActions:
    def test_find_menu_action_no_menu_bar(self):
        mgr, mw, ctx = make_mm()
        mw.menuBar = lambda: None
        assert mgr._find_menu_action("Anything") is None

    def test_find_menu_action_found_nested(self):
        mgr, mw, ctx = make_mm()
        target = FakeMenuAction("Clean Up 2D")
        sub_menu = FakeMenu([target])
        nested_action = FakeMenuAction("Submenu", submenu=sub_menu)
        top_menu = FakeMenu([nested_action])
        top_action = FakeMenuAction("Edit", submenu=top_menu)
        mw.menuBar = lambda: FakeMenuBar([top_action])
        found = mgr._find_menu_action("Clean Up 2D")
        assert found is target

    def test_find_menu_action_not_found(self):
        mgr, mw, ctx = make_mm()
        top_action = FakeMenuAction("Edit", submenu=FakeMenu([]))
        mw.menuBar = lambda: FakeMenuBar([top_action])
        assert mgr._find_menu_action("Nope") is None

    def test_find_menu_action_skips_actions_without_submenu(self):
        mgr, mw, ctx = make_mm()
        plain_action = FakeMenuAction("Quit")
        mw.menuBar = lambda: FakeMenuBar([plain_action])
        assert mgr._find_menu_action("Quit") is None

    def test_rewire_cleanup_2d_triggers_full(self):
        mgr, mw, ctx = make_mm()
        mw.edit_actions_manager.clean_up_2d_structure = MagicMock()
        cleanup_action = FakeMenuAction("Clean Up 2D")
        save_action = FakeMenuAction("&Save Project")
        save_as_action = FakeMenuAction("Save Project &As...")
        top_menu = FakeMenu([cleanup_action, save_action, save_as_action])
        top_action = FakeMenuAction("Edit", submenu=top_menu)
        mw.menuBar = lambda: FakeMenuBar([top_action])

        mw.init_manager.cleanup_button = MagicMock()
        mw.init_manager.copy_action = FakeMenuAction("Copy")
        mw.init_manager.cut_action = FakeMenuAction("Cut")
        mw.init_manager.paste_action = FakeMenuAction("Paste")

        mgr._rewire_cleanup_2d_triggers()
        mw.init_manager.cleanup_button.clicked.connect.assert_called_with(
            mw.edit_actions_manager.clean_up_2d_structure
        )

    def test_rewire_cleanup_2d_triggers_missing_everything(self):
        mgr, mw, ctx = make_mm()
        mw.menuBar = lambda: FakeMenuBar([])
        mw.edit_actions_manager = None
        # Should not raise, just log warnings
        mgr._rewire_cleanup_2d_triggers()

    def test_rewire_cleanup_2d_triggers_reconnect_disconnects_existing(self):
        mgr, mw, ctx = make_mm()
        mw.edit_actions_manager.clean_up_2d_structure = MagicMock()
        cleanup_action = FakeMenuAction("Clean Up 2D")
        top_menu = FakeMenu([cleanup_action])
        top_action = FakeMenuAction("Edit", submenu=top_menu)
        mw.menuBar = lambda: FakeMenuBar([top_action])
        mw.init_manager.cleanup_button = MagicMock()
        # Pre-connect a slot so disconnect() has something to remove
        mw.init_manager.cleanup_button.clicked.disconnect.side_effect = None
        cleanup_action.triggered.connect(lambda: None)
        mgr._rewire_cleanup_2d_triggers()


# ===========================================================================
# Export / clipboard helpers
# ===========================================================================


class TestExportHelpers:
    def test_is_content_item_reaction_item(self):
        mgr, mw, ctx = make_mm()
        arrow = add_arrow(mw, select=False)
        assert mgr._is_content_item(arrow) is True

    def test_is_content_item_atom(self):
        mgr, mw, ctx = make_mm()
        atom = FakeAtomItem(1)
        assert mgr._is_content_item(atom) is True

    def test_is_content_item_bond(self):
        mgr, mw, ctx = make_mm()
        a1, a2 = FakeAtomItem(1), FakeAtomItem(2)
        bond = FakeBondItem(a1, a2)
        assert mgr._is_content_item(bond) is True

    def test_is_content_item_other(self):
        mgr, mw, ctx = make_mm()
        assert mgr._is_content_item(object()) is False

    def test_get_reaction_bounds_empty(self):
        mgr, mw, ctx = make_mm()
        assert mgr.get_reaction_bounds([]).isNull()

    def test_get_reaction_bounds_skips_handles(self):
        mgr, mw, ctx = make_mm()
        arrow = add_arrow(mw, select=False)
        # handle items expose handle_type; should be skipped
        bounds = mgr.get_reaction_bounds([arrow, arrow.h_start])
        assert not bounds.isNull()

    def test_generate_png_data_empty_items(self):
        mgr, mw, ctx = make_mm()
        assert mgr._generate_png_data([]) == b""

    def test_generate_png_data_with_items(self):
        mgr, mw, ctx = make_mm()
        arrow = add_arrow(mw)
        mgr._generate_png_data([arrow])  # QBuffer/QImage are Qt stubs -- just must not raise

    def test_generate_svg_data_empty_items(self):
        mgr, mw, ctx = make_mm()
        assert mgr._generate_svg_data([]) == b""

    def test_generate_svg_data_with_items(self):
        mgr, mw, ctx = make_mm()
        arrow = add_arrow(mw)
        mgr._generate_svg_data([arrow])  # QSvgGenerator/QBuffer are Qt stubs -- just must not raise

    def test_export_image_no_items(self):
        mgr, mw, ctx = make_mm()
        mgr.export_image()
        ctx.show_status_message.assert_called_with("No reaction items to export.")

    def test_export_image_with_selection(self, monkeypatch, tmp_path):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        out_file = tmp_path / "out.png"
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = (str(out_file), "")
        mgr.export_image()  # QFile is a Qt stub -- doesn't hit the real filesystem
        ctx.show_status_message.assert_called()

    def test_export_image_cancelled_dialog(self, monkeypatch):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mgr.export_image()

    def test_export_image_uses_current_file_path_folder(self, tmp_path):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        mw.init_manager.current_file_path = str(tmp_path / "proj.pmeprj")
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mgr.export_image()

    def test_copy_to_clipboard_no_items(self):
        mgr, mw, ctx = make_mm()
        mgr.copy_to_clipboard()
        ctx.show_status_message.assert_called_with("No content items to copy.")

    def test_copy_to_clipboard_with_items(self):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        mgr.copy_to_clipboard()
        ctx.show_status_message.assert_called_with("Reaction copied as Image", 3000)

    def test_copy_to_clipboard_no_selection_falls_back_to_all(self):
        mgr, mw, ctx = make_mm()
        add_arrow(mw, select=False)
        mgr.copy_to_clipboard()
        ctx.show_status_message.assert_called_with("Reaction copied as Image", 3000)

    def test_export_svg_no_items(self):
        mgr, mw, ctx = make_mm()
        mgr.export_svg()
        ctx.show_status_message.assert_called_with("No reaction items to export.")

    def test_export_svg_with_explicit_items_and_filename(self, tmp_path):
        mgr, mw, ctx = make_mm()
        arrow = add_arrow(mw, select=False)
        out_file = tmp_path / "out.svg"
        mgr.export_svg(items=[arrow], filename=str(out_file))  # QFile stub -- no real I/O

    def test_export_svg_dialog_cancelled(self):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        from PyQt6.QtWidgets import QFileDialog

        QFileDialog.getSaveFileName.return_value = ("", "")
        mgr.export_svg()

    def test_copy_svg_to_clipboard_no_items(self):
        mgr, mw, ctx = make_mm()
        mgr.copy_svg_to_clipboard()
        ctx.show_status_message.assert_called_with("No content items to copy.")

    def test_copy_svg_to_clipboard_with_items(self):
        mgr, mw, ctx = make_mm()
        add_arrow(mw)
        mgr.copy_svg_to_clipboard()
        ctx.show_status_message.assert_called_with("Reaction copied as SVG", 3000)


# ===========================================================================
# Property toolbar / color / text formatting
# ===========================================================================


class TestPropertyToolbar:
    def test_setup_toolbar_and_property_toolbar_build_without_error(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        assert mgr.reaction_toolbar is not None
        assert mgr.property_toolbar is not None
        # "select" tool should be the checked default
        select_actions = [
            a for a in mgr.action_group.actions() if a.property("tool_name") == "select"
        ]
        assert select_actions and select_actions[0].isChecked()

    def test_setup_toolbar_idempotent(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        tb = mgr.reaction_toolbar
        mgr.setup_toolbar()
        assert mgr.reaction_toolbar is tb

    def test_choose_color_valid(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        from PyQt6.QtWidgets import QColorDialog

        QColorDialog.getColor.return_value = QColor("#abcdef")
        mgr.is_reaction_mode = True
        mgr.choose_color()
        assert mgr.color_btn.property("current_color").name() == "#abcdef"

    def test_choose_color_invalid_is_noop(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        from PyQt6.QtWidgets import QColorDialog

        bad_color = QColor("#000000")
        monkeypatch.setattr(bad_color, "isValid", lambda: False)
        QColorDialog.getColor.return_value = bad_color
        mgr.choose_color()

    def test_update_color_button(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.update_color_button(QColor("#112233"))
        assert mgr.color_btn.property("current_color").name() == "#112233"

    def test_sync_property_toolbar_not_reaction_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = False
        mgr.sync_property_toolbar()  # should return early, no crash

    def test_sync_property_toolbar_no_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr.sync_property_toolbar()

    def test_sync_property_toolbar_with_arrow_selected(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_arrow(mw)
        mgr.sync_property_toolbar()

    def test_sync_property_toolbar_with_text_selected(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_text(mw)
        mgr.sync_property_toolbar()

    def test_sync_property_toolbar_scene_deleted_swallowed(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True

        class BoomScene:
            def selectedItems(self):
                raise RuntimeError("deleted")

        mw.scene = BoomScene()
        mgr.sync_property_toolbar()

    def test_disconnect_signals(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.disconnect_signals()  # first disconnect ok
        mgr.disconnect_signals()  # second call: not connected -> swallowed

    def test_disconnect_signals_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.disconnect_signals()

    def test_apply_text_format_property_object_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_text(mw)
        mgr.is_reaction_mode = True
        mgr._apply_text_format_property("bold")
        mgr._apply_text_format_property("italic")
        mgr._apply_text_format_property("underline")
        mgr._apply_text_format_property("sub")
        mgr._apply_text_format_property("sup")

    def test_apply_text_format_property_no_targets(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr._apply_text_format_property("bold")

    def test_apply_text_format_property_edit_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        mgr._apply_text_format_property("sub")
        mgr._apply_text_format_property("sup")

    def test_apply_properties_no_sender_noop(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr.sender = lambda: None
        mgr.apply_properties()

    def test_apply_properties_updating_flag_short_circuits(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr._updating_props = True
        mgr.apply_properties()  # returns immediately

    def test_apply_properties_not_reaction_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = False
        mgr.apply_properties()

    def test_apply_properties_color_change_on_text(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_text(mw)
        mgr.color_btn.setProperty("current_color", "#ff0000")
        mgr.sender = lambda: mgr.color_btn
        mgr.apply_properties()
        assert mw.edit_actions_manager.push_undo_state_calls == 1

    def test_apply_properties_color_change_on_arrow(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_arrow(mw)
        mgr.color_btn.setProperty("current_color", "#00ff00")
        mgr.sender = lambda: mgr.color_btn
        mgr.apply_properties()

    def test_apply_properties_font_family_change(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_text(mw)
        mgr.font_combo.currentText.return_value = "Times New Roman"
        mgr.sender = lambda: mgr.font_combo
        mgr.apply_properties()

    def test_apply_properties_font_size_change(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_text(mw)
        mgr.font_size_spin.value.return_value = 18
        mgr.sender = lambda: mgr.font_size_spin
        mgr.apply_properties()

    def test_apply_properties_width_change(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_arrow(mw)
        mgr.width_spin.value.return_value = 7
        mgr.sender = lambda: mgr.width_spin
        mgr.apply_properties()

    def test_apply_properties_scene_deleted(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True

        class BoomScene:
            def selectedItems(self):
                raise RuntimeError("gone")

        mw.scene = BoomScene()
        mgr.apply_properties()


# ===========================================================================
# Tools: add_tool, activation, context menu
# ===========================================================================


class TestTools:
    def test_add_tool(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        button = mgr.add_tool("Line", "line", "Draw a line")
        assert button is not None
        assert any(a.property("tool_name") == "line" for a in mgr.action_group.actions())

    def test_on_action_triggered_no_tool_name(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        action = FakeQAction()
        mgr.on_action_triggered(action)  # no-op, tool_name None

    def test_on_action_triggered_sets_tool_and_style(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        add_arrow(mw)
        action = FakeQAction()
        action.setProperty("tool_name", "arrow")
        mgr.on_action_triggered(action)
        mgr.interaction_handler.set_tool.assert_called_with("arrow")

    def test_on_action_triggered_arrow_no(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        add_arrow(mw, cls=ReactionNoArrowItem)
        action = FakeQAction()
        action.setProperty("tool_name", "arrow_no")
        mgr.on_action_triggered(action)

    def test_on_action_triggered_circle(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        add_arrow(mw, cls=ReactionCircleItem, start=QPointF(0, 0), end=QPointF(10, 10))
        action = FakeQAction()
        action.setProperty("tool_name", "circle")
        mgr.on_action_triggered(action)

    def test_on_action_triggered_bracket(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        add_arrow(mw, cls=ReactionBracketItem, start=QPointF(0, 0), end=QPointF(10, 10))
        action = FakeQAction()
        action.setProperty("tool_name", "bracket")
        mgr.on_action_triggered(action)

    def test_on_action_triggered_no_interaction_handler(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        action = FakeQAction()
        action.setProperty("tool_name", "select")
        mgr.on_action_triggered(action)  # interaction_handler is None -> no-op

    def test_on_tool_pressed_and_clicked_reopens_menu(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        action = FakeQAction()
        action.setProperty("tool_name", "arrow")
        action.setChecked(True)
        mgr.on_tool_pressed(action)
        assert mgr._was_active_before_click is True
        mgr._last_menu_close_time = 0  # cooldown passed
        called = {}
        monkeypatch.setattr(
            mgr, "show_tool_context_menu", lambda b, t, p: called.setdefault("t", t)
        )
        button = MagicMock()
        mgr.on_tool_clicked(button, action)
        assert called["t"] == "arrow"

    def test_on_tool_clicked_cooldown_blocks_reopen(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        action = FakeQAction()
        action.setProperty("tool_name", "arrow")
        action.setChecked(True)
        mgr.on_tool_pressed(action)
        mgr._last_menu_close_time = time.time()
        called = {"n": 0}
        monkeypatch.setattr(
            mgr, "show_tool_context_menu", lambda b, t, p: called.__setitem__("n", called["n"] + 1)
        )
        mgr.on_tool_clicked(MagicMock(), action)
        assert called["n"] == 0

    def test_on_tool_clicked_not_previously_active(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        action = FakeQAction()
        action.setProperty("tool_name", "arrow")
        mgr._was_active_before_click = False
        mgr.on_tool_clicked(MagicMock(), action)  # no-op branch

    def test_activate_select_tool(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        mgr.activate_select_tool()
        mgr.interaction_handler.set_tool.assert_called_with("select")

    def test_activate_select_tool_no_handler(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.activate_select_tool()

    def test_show_tool_context_menu_with_button(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        button = MagicMock()
        mgr.show_tool_context_menu(button, "arrow", QPointF(0, 0))

    def test_show_tool_context_menu_no_button(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.show_tool_context_menu(None, "arrow", QPointF(0, 0))

    @pytest.mark.parametrize(
        "tool_name",
        [
            "arrow",
            "arrow_eq",
            "curved_double",
            "curved_fish",
            "arrow_no",
            "bracket",
            "circle",
            "text",
            "line",
        ],
    )
    def test_create_tool_style_menu_variants(self, tool_name):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        menu = mgr.create_tool_style_menu(tool_name)
        assert menu is not None

    def test_create_tool_style_menu_with_selection_reads_current_style(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw)
        menu = mgr.create_tool_style_menu("arrow")
        assert menu is not None

    def test_create_tool_style_menu_bracket_with_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw, cls=ReactionBracketItem, start=QPointF(0, 0), end=QPointF(5, 5))
        menu = mgr.create_tool_style_menu("bracket")
        assert menu is not None

    def test_create_tool_style_menu_circle_with_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw, cls=ReactionCircleItem, start=QPointF(0, 0), end=QPointF(5, 5))
        menu = mgr.create_tool_style_menu("circle")
        assert menu is not None

    def test_create_tool_style_menu_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        menu = mgr.create_tool_style_menu("arrow")
        assert menu is not None

    def test_activate_tool_by_name(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        mgr.activate_tool_by_name("arrow")
        mgr.interaction_handler.set_tool.assert_called_with("arrow")

    def test_activate_tool_by_name_no_handler(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.activate_tool_by_name("arrow")

    def test_set_tool(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        mgr.set_tool("bracket")
        mgr.interaction_handler.set_tool.assert_called_with("bracket")

    def test_set_tool_no_handler(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.set_tool("bracket")


# ===========================================================================
# Style setters
# ===========================================================================


class TestStyleSetters:
    def test_set_head_style_converts_item(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        add_arrow(mw, cls=ReactionArrowItem)
        mgr.set_head_style("arrow_dashed", "triangle")
        assert any(isinstance(i, ReactionDashedArrowItem) for i in mw.scene.items())
        assert mw.edit_actions_manager.push_undo_state_calls == 1

    def test_set_head_style_same_type_just_updates(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw, cls=ReactionArrowItem)
        mgr.set_head_style("arrow", "harpoon")
        assert arrow.head_style == "harpoon"

    def test_set_head_style_curved_fish_conversion(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.set_head_style("curved_fish", "triangle")
        items = [i for i in mw.scene.items() if isinstance(i, ReactionCurvedArrowItem)]
        assert items and items[0].is_fish_hook is True

    def test_set_head_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_head_style("arrow", "triangle")

    def test_set_head_style_conversion_error_is_swallowed(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw, cls=ReactionArrowItem)
        monkeypatch.setattr(
            arrow, "create_json_data", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        mgr.set_head_style("arrow_dashed", "triangle")  # should not raise

    def test_set_text_size(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.size_spin = MagicMock()
        mgr.set_text_size(30)
        mgr.size_spin.setValue.assert_called_with(30)

    def test_set_sign_size(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        from reaction_sketcher.items import ReactionPlusItem

        plus = ReactionPlusItem(QPointF(0, 0))
        mw.scene.addItem(plus)
        plus.setSelected(True)
        mgr.set_sign_size(40)
        assert plus.size == 40
        assert mw.edit_actions_manager.push_undo_state_calls == 1

    def test_set_sign_size_no_items(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.set_sign_size(40)
        assert mw.edit_actions_manager.push_undo_state_calls == 0

    def test_set_negation_style(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        item = add_arrow(mw, cls=ReactionNoArrowItem)
        mgr.set_negation_style("cross")
        assert item.negation_style == "cross"
        assert mgr.default_no_arrow_style == "cross"

    def test_set_negation_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_negation_style("cross")

    def test_set_curved_hook_style_true(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        item = add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.set_curved_hook_style(True)
        assert item.is_fish_hook is True
        mgr.interaction_handler.set_tool.assert_called_with("curved_fish")

    def test_set_curved_hook_style_false(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.set_curved_hook_style(False)

    def test_set_curved_hook_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_curved_hook_style(True)

    def test_set_circle_variant(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        item = add_arrow(mw, cls=ReactionCircleItem, start=QPointF(0, 0), end=QPointF(10, 10))
        mgr.set_circle_variant("circle", "dashed")
        assert item.shape_type == "circle"
        assert item.line_style == "dashed"

    def test_set_circle_variant_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_circle_variant("circle", "solid")

    def test_set_curved_head_style_activates_tool(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        mgr.interaction_handler.active_tool = "select"
        item = add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.set_curved_head_style("triangle")
        assert item.head_style == "triangle"

    def test_set_curved_head_style_already_curved_tool(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        mgr.interaction_handler.active_tool = "curved_double"
        add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.set_curved_head_style("barb")

    def test_set_curved_head_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_curved_head_style("barb")

    def test_set_bracket_type(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        item = add_arrow(mw, cls=ReactionBracketItem, start=QPointF(0, 0), end=QPointF(10, 10))
        mgr.set_bracket_type("round")
        assert item.bracket_type == "round"
        assert mgr.default_bracket_type == "round"

    def test_set_bracket_type_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.set_bracket_type("round")

    def test_set_tool_thickness(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.set_tool_thickness(9)
        mgr.width_spin.setValue.assert_called_with(9)

    def test_set_tool_color(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.set_tool_color(QColor("#123456"))
        assert mgr.color_btn.property("current_color").name() == "#123456"


# ===========================================================================
# Reaction mode toggling
# ===========================================================================


class TestReactionMode:
    def test_toggle_reaction_mode_enters(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.toggle_reaction_mode()
        assert mgr.is_reaction_mode is True

    def test_toggle_reaction_mode_exits_no_items(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr.toggle_reaction_mode()
        assert mgr.is_reaction_mode is False

    def test_toggle_reaction_mode_exit_confirmed(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_arrow(mw)
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.question.return_value = QMessageBox.StandardButton.Yes
        mgr.toggle_reaction_mode()
        assert mgr.is_reaction_mode is False

    def test_toggle_reaction_mode_exit_cancelled(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        add_arrow(mw)
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.question.return_value = QMessageBox.StandardButton.No
        mgr.toggle_reaction_mode()
        assert mgr.is_reaction_mode is True

    def test_enter_reaction_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.enter_reaction_mode()
        assert mgr.is_reaction_mode is True
        ctx.show_status_message.assert_called_with(
            "Reaction Sketching Mode Active", 3000
        )

    def test_enter_reaction_mode_activate_select_mode_fallback(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        del mw.ui_manager
        mw.activate_select_mode = MagicMock()
        mgr.enter_reaction_mode()
        mw.activate_select_mode.assert_called_once()

    def test_enter_reaction_mode_splitter_single_pane(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.init_manager.splitter.count.return_value = 1
        mgr.enter_reaction_mode()

    def test_exit_reaction_mode_with_saved_sizes(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.enter_reaction_mode()
        mgr.exit_reaction_mode()
        assert mgr.is_reaction_mode is False
        ctx.show_status_message.assert_called_with("Returned to Molecular Mode", 3000)

    def test_exit_reaction_mode_no_saved_sizes_fallback(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.original_splitter_sizes = None
        mgr.exit_reaction_mode()

    def test_exit_reaction_mode_restores_shortcuts(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.disable_main_window_shortcuts()
        mgr.exit_reaction_mode()
        assert mgr._shortcuts_disabled is False

    def test_set_3d_action_state_enable_disable(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.init_manager.convert_button = MagicMock()
        mw.init_manager.optimize_3d_button = MagicMock()
        mgr.set_3d_action_state(False)
        mw.init_manager.convert_button.setEnabled.assert_called_with(False)
        mw.init_manager.optimize_3d_button.setEnabled.assert_called_with(False)
        mgr.set_3d_action_state(True)
        mw.init_manager.convert_button.setEnabled.assert_called_with(True)

    def test_set_3d_action_state_no_main_window(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.main_window = None
        mgr.set_3d_action_state(True)

    def test_set_3d_action_state_extra_actions(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.action_3d = MagicMock()
        mgr.set_3d_action_state(False)
        mw.action_3d.setEnabled.assert_called_with(False)


# ===========================================================================
# sync_with_main_window / _handle_main_mode_change / eventFilter / shortcuts
# ===========================================================================


class TestModeChangeAndShortcuts:
    def test_sync_with_main_window_noop(self):
        mgr, mw, ctx = make_mm()
        mgr.sync_with_main_window()

    def test_handle_main_mode_change_not_reaction_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = False
        mgr._handle_main_mode_change("atom_carbon")

    def test_handle_main_mode_change_internal_change_ignored(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr.interaction_handler = MagicMock()
        mgr.interaction_handler._internal_mode_change = True
        mgr._handle_main_mode_change("atom_carbon")

    def test_handle_main_mode_change_switching_tool_ignored(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr._switching_tool = True
        mgr._handle_main_mode_change("select")

    def test_handle_main_mode_change_resets_tool_for_molecular_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr.interaction_handler = MagicMock()
        mgr.interaction_handler._internal_mode_change = False
        # Force current tool to something other than select first.
        for a in mgr.action_group.actions():
            a.setChecked(a.property("tool_name") == "arrow")
        mgr._handle_main_mode_change("atom_carbon")
        select_actions = [
            a for a in mgr.action_group.actions() if a.property("tool_name") == "select"
        ]
        assert select_actions[0].isChecked()

    def test_handle_main_mode_change_bond_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr._handle_main_mode_change("bond_single")

    def test_handle_main_mode_change_other_mode_ignored(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr._handle_main_mode_change("some_other_mode")

    def test_handle_main_mode_change_charge_and_radical_modes(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.is_reaction_mode = True
        mgr._handle_main_mode_change("charge_plus")
        mgr._handle_main_mode_change("charge_minus")
        mgr._handle_main_mode_change("radical")

    def test_event_filter_shortcut_override_blocked(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr._shortcuts_disabled = True
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)

        class Ev:
            def type(self):
                return QEvent.Type.ShortcutOverride

            def accept(self):
                self.accepted = True

        from PyQt6.QtCore import QEvent

        ev = Ev()
        result = mgr.eventFilter(mw, ev)
        assert result is True
        assert ev.accepted is True

    def test_event_filter_shortcuts_enabled_passthrough(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        from PyQt6.QtCore import QEvent

        class Ev:
            def type(self):
                return QEvent.Type.ShortcutOverride

        mgr._shortcuts_disabled = False
        result = mgr.eventFilter(mw, Ev())
        assert result is False

    def test_event_filter_non_shortcut_event(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)

        class Ev:
            def type(self):
                return "other"

        result = mgr.eventFilter(mw, Ev())
        assert result is False

    def test_disable_enable_main_window_shortcuts(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.disable_main_window_shortcuts()
        assert mgr._shortcuts_disabled is True
        mgr.disable_main_window_shortcuts()  # already disabled -> no-op
        mgr.enable_main_window_shortcuts()
        assert mgr._shortcuts_disabled is False
        mgr.enable_main_window_shortcuts()  # already enabled -> no-op

    def test_disable_main_window_shortcuts_no_main_window(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.main_window = None
        mgr.disable_main_window_shortcuts()

    def test_show_about_dialog(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.show_about_dialog()  # QMessageBox.about is a Mock -- just should not raise


# ===========================================================================
# Advanced settings / apply_settings_to_selection
# ===========================================================================


class TestAdvancedSettings:
    def test_open_advanced_settings_no_selection(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        called = {}
        monkeypatch.setattr(
            mm_mod, "AdvancedSettingsDialog", MagicMock(), raising=False
        )
        mgr.open_advanced_settings()  # no target item -> no dialog created

    def test_open_advanced_settings_with_selection_accepted(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw)

        dlg = MagicMock()
        dlg.exec.return_value = True
        dlg.get_settings.return_value = {"color": "#ff0000", "width": 5}
        monkeypatch.setattr(
            "reaction_sketcher.settings_dialog.AdvancedSettingsDialog",
            MagicMock(return_value=dlg),
        )
        mgr.open_advanced_settings()
        assert mw.edit_actions_manager.push_undo_state_calls >= 1

    def test_open_advanced_settings_rejected(self, monkeypatch):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_arrow(mw)

        dlg = MagicMock()
        dlg.exec.return_value = False
        monkeypatch.setattr(
            "reaction_sketcher.settings_dialog.AdvancedSettingsDialog",
            MagicMock(return_value=dlg),
        )
        mgr.open_advanced_settings()

    def test_apply_settings_to_selection_all_fields(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw)
        settings = {
            "color": "#ff00ff",
            "width": 4,
            "head_size": 12,
            "head_angle": 30,
            "head_concavity": 0.4,
            "head_style": "barb",
            "head_side": 1,
        }
        mgr.apply_settings_to_selection(settings)
        assert arrow.pen_width == 4
        assert arrow.head_size == 12
        assert arrow.head_style == "barb"

    def test_apply_settings_to_selection_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.apply_settings_to_selection({"color": "#000000"})

    def test_apply_settings_to_selection_curvature_and_control_point(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        item = add_arrow(mw, cls=ReactionCurvedArrowItem)
        mgr.apply_settings_to_selection(
            {"curvature": 0.5, "control_p": [3.0, 4.0]}
        )
        assert item.control_p == QPointF(3.0, 4.0)

    def test_apply_settings_to_selection_text_size(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        from reaction_sketcher.items import ReactionPlusItem

        plus = ReactionPlusItem(QPointF(0, 0))
        mw.scene.addItem(plus)
        plus.setSelected(True)
        mgr.apply_settings_to_selection({"size": 55})
        assert plus.size == 55

    def test_apply_settings_to_selection_rect_size(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        item = add_arrow(mw, cls=ReactionCircleItem, start=QPointF(0, 0), end=QPointF(5, 5))
        mgr.apply_settings_to_selection({"rect_width": 30, "rect_height": 40})

    def test_apply_settings_to_selection_bracket_and_double_offset_and_cross(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        b = add_arrow(mw, cls=ReactionBracketItem, start=QPointF(0, 0), end=QPointF(5, 5))
        mgr.apply_settings_to_selection({"bracket_type": "round"})
        assert b.bracket_type == "round"

        a = add_arrow(mw, cls=ReactionEquilibriumArrowItem)
        mgr.apply_settings_to_selection({"double_arrow_offset": 9.0})

        no_arrow = add_arrow(mw, cls=ReactionNoArrowItem)
        mgr.apply_settings_to_selection({"cross_size": 15})


# ===========================================================================
# Grouping / logical units / alignment / distribution
# ===========================================================================


class TestGroupingAndLayout:
    def test_group_selected_items_no_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.group_selected_items()  # no-op

    def test_group_selected_items_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.group_selected_items()

    def test_group_selected_items_none_groupable(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_text(mw)  # ReactionTextItem lacks group_id/atom_id/atom1? has group_id
        # (text items DO have group_id; use an item lacking it entirely instead)
        mgr.group_selected_items()

    def test_group_selected_items_and_ungroup(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.interaction_handler = MagicMock()
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        a1.setSelected(True)
        a2.setSelected(True)
        mgr.group_selected_items()
        assert a1.group_id is not None
        assert a1.group_id == a2.group_id
        mgr.ungroup_selected_items()
        assert a1.group_id is None

    def test_ungroup_selected_items_no_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.ungroup_selected_items()

    def test_ungroup_selected_items_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.ungroup_selected_items()

    def test_sync_selection_visuals_no_selection_clears(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a1.is_group_selected = True
        mw.scene.addItem(a1)
        mgr._sync_selection_visuals()
        assert a1.is_group_selected is False

    def test_sync_selection_visuals_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr._sync_selection_visuals()

    def test_sync_selection_visuals_group_highlight(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.group_id = "g1"
        a2.group_id = "g1"
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        a1.setSelected(True)
        a2.setSelected(True)
        mgr._sync_selection_visuals()
        assert a1.is_group_selected is True
        assert a2.is_group_selected is True

    def test_sync_selection_visuals_single_group_member(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a1.group_id = "g1"
        mw.scene.addItem(a1)
        a1.setSelected(True)
        mgr._sync_selection_visuals()
        assert a1.is_group_selected is True

    def test_get_logical_units_empty_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        assert mgr.get_logical_units([]) == []

    def test_get_logical_units_molecule_fragment(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.setPos(QPointF(0, 0))
        a2.setPos(QPointF(10, 0))
        bond = FakeBondItem(a1, a2)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene.addItem(bond)
        units = mgr.get_logical_units([a1])
        assert len(units) == 1
        assert units[0]["type"] == "molecule"
        assert a2 in units[0]["members"]

    def test_get_logical_units_explicit_group(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.group_id = "g1"
        a2.group_id = "g1"
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        units = mgr.get_logical_units([a1])
        assert units[0]["type"] == "group"
        assert len(units[0]["members"]) == 2

    def test_get_logical_units_single_reaction_item(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw)
        units = mgr.get_logical_units([arrow])
        assert units[0]["type"] == "item"

    def test_align_items_top_left_bottom_right_center(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        a2 = FakeAtomItem(2)
        a1.setPos(QPointF(0, 0))
        a2.setPos(QPointF(100, 100))
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        a1.setSelected(True)
        a2.setSelected(True)
        for mode in ["top", "bottom", "left", "right", "center_v", "center_h"]:
            mgr.align_items(mode)

    def test_align_items_too_few_selected(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        mw.scene.addItem(a1)
        a1.setSelected(True)
        mgr.align_items("top")

    def test_align_items_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.align_items("top")

    def test_align_items_moves_reaction_item(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow1 = add_arrow(mw, start=QPointF(0, 0), end=QPointF(10, 0))
        arrow2 = add_arrow(mw, start=QPointF(100, 100), end=QPointF(110, 100))
        mgr.align_items("left")

    def test_distribute_items_horizontal_and_vertical(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        atoms = []
        for i, x in enumerate([0, 50, 100]):
            a = FakeAtomItem(i + 1)
            a.setPos(QPointF(x, 0))
            mw.scene.addItem(a)
            a.setSelected(True)
            atoms.append(a)
        mgr.distribute_items("horizontal")

        for a in atoms:
            a.setPos(QPointF(0, a.pos().x()))
        mgr.distribute_items("vertical")

    def test_distribute_items_too_few(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1)
        mw.scene.addItem(a1)
        a1.setSelected(True)
        mgr.distribute_items("horizontal")

    def test_distribute_items_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.distribute_items("horizontal")


# ===========================================================================
# Text formatting helpers
# ===========================================================================


class TestTextFormatting:
    def test_toggle_subscript_and_superscript(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_text(mw)
        mgr.toggle_subscript()
        mgr.toggle_superscript()

    def test_toggle_text_format_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr._toggle_text_format("sub")

    def test_toggle_text_format_no_targets(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr._toggle_text_format("sub")

    def test_toggle_text_format_edit_mode_with_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        text.textCursor().hasSelection.return_value = True
        mgr._toggle_text_format("sup")

    def test_apply_text_style_bold_italic_underline(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        add_text(mw)
        mgr.apply_text_style("bold")
        mgr.apply_text_style("italic")
        mgr.apply_text_style("underline")

    def test_apply_text_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.apply_text_style("bold")

    def test_apply_text_style_no_targets(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.apply_text_style("bold")

    def test_apply_text_style_edit_mode_with_selection(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        text.textCursor().hasSelection.return_value = True
        mgr.apply_text_style("italic")

    def test_apply_chem_style(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, text="H2O+ CO2 _n{2} x^{3}")
        mgr.apply_chem_style()

    def test_apply_chem_style_no_scene(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene = None
        mgr.apply_chem_style()

    def test_apply_chem_style_no_targets(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.apply_chem_style()

    def test_apply_chem_style_edit_mode(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, text="H2O", select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        mgr.apply_chem_style()


# ===========================================================================
# Duplicate / copy / cut / paste
# ===========================================================================


class TestDuplicateCopyCutPaste:
    def test_duplicate_items_immediate_empty(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        assert mgr.duplicate_items_immediate([]) == []

    def test_duplicate_items_immediate_reaction_item(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw, select=False)
        new_items = mgr.duplicate_items_immediate([arrow])
        assert len(new_items) == 1
        assert isinstance(new_items[0], ReactionArrowItem)

    def test_duplicate_items_immediate_molecule(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        a1 = FakeAtomItem(1, "C")
        a2 = FakeAtomItem(2, "O")
        a1.setPos(QPointF(0, 0))
        a2.setPos(QPointF(10, 0))
        bond = FakeBondItem(a1, a2, order=1)
        mw.scene.addItem(a1)
        mw.scene.addItem(a2)
        mw.scene.addItem(bond)
        mw.state_manager.data.atoms = {
            1: {"symbol": "C", "pos": [0, 0], "charge": 0, "radical": 0},
            2: {"symbol": "O", "pos": [10, 0], "charge": 0, "radical": 0},
        }
        mw.state_manager.data.bonds = {(1, 2): {"order": 1, "stereo": 0}}
        new_items = mgr.duplicate_items_immediate([a1, a2])
        assert len(new_items) == 2

    def test_duplicate_items_immediate_no_snapshot_no_new_items(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        plain = object()
        assert mgr.duplicate_items_immediate([plain]) == []

    def test_copy_reaction_items_editing_text_is_noop(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        mgr.copy_reaction_items()

    def test_copy_reaction_items_delegates_to_edit_actions_manager(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager.copy_selection = MagicMock()
        mgr.copy_reaction_items()
        mw.edit_actions_manager.copy_selection.assert_called_once()

    def test_copy_reaction_items_no_main_window(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.main_window = None
        mgr.copy_reaction_items()

    def test_copy_reaction_items_fallback_main_window_edit_actions(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager = None
        mw.main_window_edit_actions = MagicMock()
        mgr.copy_reaction_items()
        mw.main_window_edit_actions.copy_selection.assert_called_once()

    def test_copy_reaction_items_no_edit_actions_at_all(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager = None
        mgr.copy_reaction_items()
        ctx.show_status_message.assert_called_with(
            "Copy failed: Edit actions not found", 3000
        )

    def test_cut_reaction_items_editing_text_is_noop(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        mgr.cut_reaction_items()

    def test_cut_reaction_items_delegates(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.main_window_edit_actions = MagicMock()
        mgr.cut_reaction_items()
        mw.main_window_edit_actions.delete_selection.assert_called_once()

    def test_cut_reaction_items_fallback_direct_scene_delete(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        arrow = add_arrow(mw)
        mgr.cut_reaction_items()

    def test_cut_reaction_items_no_main_window(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.main_window = None
        mgr.cut_reaction_items()

    def test_cut_reaction_items_no_items_no_delete_func(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.scene.delete_items = None
        mgr.cut_reaction_items()

    def test_paste_reaction_items_editing_text_is_noop(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        text = add_text(mw, select=False)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mw.scene.setFocusItem(text)
        mgr.paste_reaction_items()

    def test_paste_reaction_items_delegates_to_edit_actions_manager(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager.paste_from_clipboard = MagicMock()
        mgr.paste_reaction_items()
        mw.edit_actions_manager.paste_from_clipboard.assert_called_once()

    def test_paste_reaction_items_no_main_window(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mgr.main_window = None
        mgr.paste_reaction_items()

    def test_paste_reaction_items_fallback(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager = None
        mw.main_window_edit_actions = MagicMock()
        mgr.paste_reaction_items()
        mw.main_window_edit_actions.paste_from_clipboard.assert_called_once()

    def test_paste_reaction_items_no_edit_actions_at_all(self):
        mgr, mw, ctx = make_mm(with_toolbar=True)
        mw.edit_actions_manager = None
        mgr.paste_reaction_items()
        ctx.show_status_message.assert_called_with(
            "Paste failed: Edit actions not found", 3000
        )

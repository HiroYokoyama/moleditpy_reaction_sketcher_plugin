"""
tests/test_init_coverage.py -- additional coverage for reaction_sketcher/__init__.py.

Follows the same "load a fresh copy of the package with mode_manager/
interaction/utils mocked" technique as tests/test_save_handler.py, but keeps
a handle on the installed mocks so each test can configure ModeManager's
return_value (toolbar actions, is_reaction_mode, ...) before calling
initialize()/its registered handlers. A fresh copy is loaded per test (rather
than once at module scope) so each test can set up its own ModeManager mock
state without bleeding into other tests.
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QColor

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_MOCK_NAMES = (
    "reaction_sketcher.mode_manager",
    "reaction_sketcher.interaction",
    "reaction_sketcher.utils",
)
# Every sys.modules entry this loader touches -- including the top-level
# package itself and .items (kept real for isinstance() in reset_handler) --
# must be captured *before* the first mocked exec and restored exactly after
# every call (this loader runs many times per test session, unlike
# test_save_handler.py's one-shot module-level call, so any imprecise
# restore compounds and corrupts sys.modules for every later test file).
_ALL_TOUCHED_NAMES = ("reaction_sketcher", "reaction_sketcher.items") + _MOCK_NAMES

# Ensure the real modules are loaded (and therefore captured by `saved`
# below) before any test mocks them out.
import reaction_sketcher  # noqa: E402
import reaction_sketcher.items  # noqa: E402
import reaction_sketcher.mode_manager  # noqa: E402
import reaction_sketcher.interaction  # noqa: E402
import reaction_sketcher.utils  # noqa: E402


def _load_init_mocked():
    """Load reaction_sketcher/__init__.py with mode_manager/interaction/utils
    mocked, returning (module, {name: mock}) so tests can pre-configure the
    ModeManager mock class before calling initialize().
    """
    saved = {n: sys.modules.get(n) for n in _ALL_TOUCHED_NAMES}

    mocks = {}
    for name in _MOCK_NAMES:
        m = MagicMock()
        sys.modules[name] = m
        mocks[name] = m

    spec = importlib.util.spec_from_file_location(
        "reaction_sketcher",
        os.path.join(_REPO_ROOT, "reaction_sketcher", "__init__.py"),
    )
    pkg = importlib.util.module_from_spec(spec)
    pkg.__package__ = "reaction_sketcher"
    sys.modules["reaction_sketcher"] = pkg
    spec.loader.exec_module(pkg)

    for n, v in saved.items():
        if v is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = v

    return pkg, mocks


def _make_context_and_mw():
    context = MagicMock()
    mw = MagicMock()
    mw.state_manager = MagicMock()
    mw.state_manager.data = MagicMock()
    mw.state_manager.data.atoms = {}
    mw.state_manager.data.bonds = {}
    context.get_main_window.return_value = mw
    context.scene = MagicMock()
    context.scene.items.return_value = []
    context.scene.atom_items = {}
    context.scene.bond_items = {}
    return context, mw


class TestToolbarActionWiring:
    def test_connects_non_exit_actions_skips_exit_and_untagged(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value

        draw_action = MagicMock()
        draw_action.property.return_value = "draw"
        exit_action = MagicMock()
        exit_action.property.return_value = "exit"
        untagged_action = MagicMock()
        untagged_action.property.return_value = None
        mm.reaction_toolbar.actions.return_value = [
            draw_action,
            exit_action,
            untagged_action,
        ]

        ctx, _mw = _make_context_and_mw()
        pkg.initialize(ctx)

        assert draw_action.triggered.connect.called
        assert not exit_action.triggered.connect.called
        assert not untagged_action.triggered.connect.called


class TestTriggerSketcherCallback:
    def test_menu_callback_toggles_reaction_mode(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value
        mm.reaction_toolbar.actions.return_value = []

        ctx, _mw = _make_context_and_mw()
        pkg.initialize(ctx)

        callback = ctx.add_menu_action.call_args[1].get(
            "callback"
        ) or ctx.add_menu_action.call_args[0][1]
        callback()
        assert mm.toggle_reaction_mode.called


class TestViewportEventFilterInstallation:
    def test_installed_when_view_2d_present(self):
        pkg, mocks = _load_init_mocked()
        mocks["reaction_sketcher.mode_manager"].ModeManager.return_value.reaction_toolbar.actions.return_value = (
            []
        )
        ctx, mw = _make_context_and_mw()
        mw.init_manager.view_2d = MagicMock()
        pkg.initialize(ctx)
        assert mw.init_manager.view_2d.viewport().installEventFilter.called
        assert mw.init_manager.view_2d.installEventFilter.called

    def test_skipped_when_view_2d_missing(self):
        pkg, mocks = _load_init_mocked()
        mocks["reaction_sketcher.mode_manager"].ModeManager.return_value.reaction_toolbar.actions.return_value = (
            []
        )
        ctx, mw = _make_context_and_mw()
        mw.init_manager.view_2d = None
        pkg.initialize(ctx)  # must not raise


class TestAutoStartActionMenuLookup:
    def test_found_extensions_menu_adds_action(self):
        pkg, mocks = _load_init_mocked()
        mocks["reaction_sketcher.mode_manager"].ModeManager.return_value.reaction_toolbar.actions.return_value = (
            []
        )
        ctx, mw = _make_context_and_mw()
        extensions_menu = MagicMock()
        mw.menuBar.return_value.findChild.return_value = extensions_menu
        pkg.initialize(ctx)
        assert extensions_menu.addAction.called

    def test_missing_extensions_menu_is_a_no_op(self):
        pkg, mocks = _load_init_mocked()
        mocks["reaction_sketcher.mode_manager"].ModeManager.return_value.reaction_toolbar.actions.return_value = (
            []
        )
        ctx, mw = _make_context_and_mw()
        mw.menuBar.return_value.findChild.return_value = None
        pkg.initialize(ctx)  # must not raise


class TestSaveHandlerColorsAndGroups:
    def _get_save_handler(self):
        pkg, mocks = _load_init_mocked()
        mocks["reaction_sketcher.mode_manager"].ModeManager.return_value.reaction_toolbar.actions.return_value = (
            []
        )
        ctx, mw = _make_context_and_mw()
        pkg.initialize(ctx)
        return ctx.register_save_handler.call_args[0][0], ctx, mw

    def test_atom_and_bond_colors_and_groups_collected(self):
        handler, ctx, mw = self._get_save_handler()
        mw.state_manager.data.atoms = {1: {}, 2: {}}
        mw.state_manager.data.bonds = {(1, 2): {}}

        atom_item = MagicMock()
        atom_item.pen_color = QColor("#112233")
        atom_item.group_id = "gA"
        ctx.scene.atom_items = {1: atom_item, 2: MagicMock(pen_color=None, group_id=None)}

        bond_item = MagicMock()
        bond_item.pen_color = QColor("#445566")
        bond_item.group_id = "gB"
        ctx.scene.bond_items = {(1, 2): bond_item}

        result = handler()
        assert result["rs_colors"]["atoms"]["1"] == "#112233"
        assert result["rs_colors"]["bonds"]["1-2"] == "#445566"
        assert result["groups"]["atoms"]["1"] == "gA"
        assert result["groups"]["bonds"]["1-2"] == "gB"
        # Atom 2 has no color/group -> not present.
        assert "2" not in result["rs_colors"]["atoms"]
        assert "2" not in result["groups"]["atoms"]

    def test_no_scene_or_no_data_skips_color_collection(self):
        handler, ctx, mw = self._get_save_handler()
        ctx.scene = None
        result = handler()
        assert result["rs_colors"] == {"atoms": {}, "bonds": {}}


class TestLoadHandlerColorsAndGroups:
    def _get_load_handler(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value
        mm.reaction_toolbar.actions.return_value = []
        mm.is_reaction_mode = False
        ctx, mw = _make_context_and_mw()
        pkg.initialize(ctx)
        return ctx.register_load_handler.call_args[0][0], ctx, mw, mm

    def test_restores_atom_and_bond_colors(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        atom_item = MagicMock()
        bond_item = MagicMock()
        ctx.scene.atom_items = {5: atom_item}
        ctx.scene.bond_items = {(5, 6): bond_item}

        handler(
            {
                "items": [],
                "rs_colors": {"atoms": {"5": "#abcdef"}, "bonds": {"5-6": "#fedcba"}},
            }
        )
        assert atom_item.pen_color.name() == "#abcdef"
        assert atom_item.update.called
        assert bond_item.pen_color.name() == "#fedcba"
        assert bond_item.update.called

    def test_restores_atom_and_bond_groups(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        atom_item = MagicMock()
        bond_item = MagicMock()
        ctx.scene.atom_items = {7: atom_item}
        ctx.scene.bond_items = {(7, 8): bond_item}

        handler(
            {
                "items": [],
                "groups": {"atoms": {"7": "gX"}, "bonds": {"7-8": "gY"}},
            }
        )
        assert atom_item.group_id == "gX"
        assert bond_item.group_id == "gY"

    def test_malformed_bond_color_key_is_silenced(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        handler({"items": [], "rs_colors": {"bonds": {"not-a-valid-key-x-y": "#111111"}}})

    def test_malformed_bond_group_key_is_silenced(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        handler({"items": [], "groups": {"bonds": {"not-a-valid-key-x-y": "gZ"}}})

    def test_missing_atom_or_bond_item_is_skipped(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        ctx.scene.atom_items = {}
        ctx.scene.bond_items = {}
        handler(
            {
                "items": [],
                "rs_colors": {"atoms": {"99": "#000000"}, "bonds": {"9-10": "#000000"}},
                "groups": {"atoms": {"99": "g"}, "bonds": {"9-10": "g"}},
            }
        )  # must not raise even though items.get() returns None for all keys

    def test_no_mol_data_skips_restore_block(self):
        handler, ctx, mw, _mm = self._get_load_handler()
        mw.state_manager = None
        mw.data = None
        handler(
            {"items": [], "rs_colors": {"atoms": {"1": "#111111"}}}
        )  # must not raise

    def test_should_enter_mode_toggles_when_not_already_active(self):
        handler, ctx, mw, mm = self._get_load_handler()
        handler({"items": [{"type": "arrow"}], "reaction_mode_active": False})
        assert mm.toggle_reaction_mode.called

    def test_should_enter_mode_via_reaction_mode_active_flag(self):
        handler, ctx, mw, mm = self._get_load_handler()
        handler({"items": [], "reaction_mode_active": True})
        assert mm.toggle_reaction_mode.called

    def test_should_enter_mode_via_auto_start_pref(self):
        handler, ctx, mw, mm = self._get_load_handler()
        handler({"items": [], "auto_start_pref": True})
        assert mm.toggle_reaction_mode.called

    def test_does_not_toggle_when_already_in_reaction_mode(self):
        handler, ctx, mw, mm = self._get_load_handler()
        mm.is_reaction_mode = True
        handler({"items": [{"type": "arrow"}]})
        assert not mm.toggle_reaction_mode.called

    def test_sets_auto_start_action_checked_state(self):
        handler, ctx, mw, mm = self._get_load_handler()
        handler({"items": [], "auto_start_pref": True})
        mm.auto_start_action.setChecked.assert_called_with(True)


class TestResetHandlerExitsReactionMode:
    def test_exits_reaction_mode_when_active(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value
        mm.reaction_toolbar.actions.return_value = []
        mm.is_reaction_mode = True
        ctx, mw = _make_context_and_mw()
        pkg.initialize(ctx)
        handler = ctx.register_document_reset_handler.call_args[0][0]
        handler()
        assert mm.exit_reaction_mode.called

    def test_does_not_exit_when_not_active(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value
        mm.reaction_toolbar.actions.return_value = []
        mm.is_reaction_mode = False
        ctx, mw = _make_context_and_mw()
        pkg.initialize(ctx)
        handler = ctx.register_document_reset_handler.call_args[0][0]
        handler()
        assert not mm.exit_reaction_mode.called

    def test_clears_active_tool(self):
        pkg, mocks = _load_init_mocked()
        mm = mocks["reaction_sketcher.mode_manager"].ModeManager.return_value
        mm.reaction_toolbar.actions.return_value = []
        mm.is_reaction_mode = False
        ctx, mw = _make_context_and_mw()
        pkg.initialize(ctx)
        interaction_handler = mocks[
            "reaction_sketcher.interaction"
        ].InteractionHandler.return_value
        interaction_handler.active_tool = "arrow"
        handler = ctx.register_document_reset_handler.call_args[0][0]
        handler()
        assert interaction_handler.active_tool is None

"""
tests/test_save_handler.py -- tests for the save/load/reset handlers in __init__.py.

All Qt and MoleditPy dependencies are mocked so no display is needed.
"""

import sys
import os
import types
import importlib.util
from unittest.mock import MagicMock, patch, call
import pytest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_init_mocked():
    """Load reaction_sketcher/__init__.py with heavy deps (mode_manager, interaction) mocked.

    Submodules that may already be loaded from other test files are temporarily
    replaced with MagicMocks for the duration of exec_module so that the
    initialize() function captured by _init always calls mock objects, not the
    real Qt-heavy implementations.  The real modules are restored afterwards so
    other test files are not affected.
    """
    _MOCK_NAMES = (
        "reaction_sketcher.mode_manager",
        "reaction_sketcher.interaction",
        "reaction_sketcher.utils",
    )
    # Save originals (may be real modules if collected after test_load_handler_core)
    _saved = {n: sys.modules[n] for n in _MOCK_NAMES if n in sys.modules}
    # Install MagicMock stubs for the duration of exec_module
    for name in _MOCK_NAMES:
        sys.modules[name] = MagicMock()

    # Items: keep the real module if already loaded (so load_handler_core works),
    # otherwise install lightweight stubs with real Python classes for isinstance().
    _items_saved = sys.modules.get("reaction_sketcher.items")
    if _items_saved is None:
        items_mock = MagicMock()
        for cls_name in (
            "ReactionArrowItem",
            "ReactionPlusItem",
            "ReactionTextItem",
            "ReactionMinusItem",
            "ReactionResonanceArrowItem",
            "ReactionEquilibriumArrowItem",
            "ReactionRetroArrowItem",
            "ReactionNoArrowItem",
            "ReactionCurvedArrowItem",
            "ReactionBracketItem",
            "ReactionCircleItem",
            "ReactionLineItem",
            "ReactionCurvedLineItem",
            "ReactionFreehandItem",
            "ReactionDashedArrowItem",
        ):
            setattr(items_mock, cls_name, type(cls_name, (), {}))
        sys.modules["reaction_sketcher.items"] = items_mock

    # Load under the real package name so relative imports work.
    spec = importlib.util.spec_from_file_location(
        "reaction_sketcher",
        os.path.join(_REPO_ROOT, "reaction_sketcher", "__init__.py"),
    )
    pkg = importlib.util.module_from_spec(spec)
    pkg.__package__ = "reaction_sketcher"
    sys.modules["reaction_sketcher"] = pkg
    spec.loader.exec_module(pkg)

    # Restore originals so other test files use the real submodules.
    sys.modules.update(_saved)

    return pkg


_init = _load_init_mocked()


def _make_context_and_mw():
    """Return a (context, main_window) pair wired for initialize()."""
    context = MagicMock()
    mw = MagicMock()
    mw.state_manager = MagicMock()
    mw.state_manager.data = MagicMock()
    mw.state_manager.data.atoms = {}
    mw.state_manager.data.bonds = {}
    context.get_main_window.return_value = mw
    context.scene = MagicMock()
    context.scene.items.return_value = []
    return context, mw


class TestInitialize:
    def test_registers_save_handler(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        ctx.register_save_handler.assert_called_once()

    def test_registers_load_handler(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        ctx.register_load_handler.assert_called_once()

    def test_registers_reset_handler(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        ctx.register_document_reset_handler.assert_called_once()

    def test_registers_menu_action(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        ctx.add_menu_action.assert_called_once()

    def test_menu_action_path(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        path = (
            ctx.add_menu_action.call_args[1].get("path")
            or ctx.add_menu_action.call_args[0][0]
        )
        assert "Reaction Sketcher" in path

    def test_shows_status_message(self):
        ctx, _ = _make_context_and_mw()
        _init.initialize(ctx)
        ctx.show_status_message.assert_called_once()


class TestSaveHandler:
    def _get_save_handler(self):
        ctx, mw = _make_context_and_mw()
        _init.initialize(ctx)
        return ctx.register_save_handler.call_args[0][0], mw

    def test_returns_dict(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert isinstance(result, dict)

    def test_has_plugin_version(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert result["plugin_version"] == _init.PLUGIN_VERSION

    def test_has_items_key(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_has_reaction_mode_active(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert "reaction_mode_active" in result

    def test_has_auto_start_pref(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert "auto_start_pref" in result

    def test_has_rs_colors(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert "rs_colors" in result
        assert "atoms" in result["rs_colors"]
        assert "bonds" in result["rs_colors"]

    def test_has_groups(self):
        handler, _ = self._get_save_handler()
        result = handler()
        assert "groups" in result


class TestLoadHandler:
    def _get_load_handler(self):
        ctx, mw = _make_context_and_mw()
        _init.initialize(ctx)
        return ctx.register_load_handler.call_args[0][0]

    def test_none_data_does_not_raise(self):
        handler = self._get_load_handler()
        handler(None)  # should not raise

    def test_empty_dict_does_not_raise(self):
        handler = self._get_load_handler()
        handler({})  # should not raise

    @pytest.mark.skip(
        reason="triggers real ModeManager.toggle_reaction_mode via auto_start_pref; complex Qt interaction not worth stubbing"
    )
    def test_restores_auto_start_pref(self):
        ctx, mw = _make_context_and_mw()
        _init.initialize(ctx)
        mode_manager = mw._reaction_mode_manager
        handler = ctx.register_load_handler.call_args[0][0]
        handler({"auto_start_pref": True, "items": []})
        assert mode_manager.auto_start_pref is True

    def test_list_data_does_not_raise(self):
        """Legacy list format (no dict wrapper) should not crash."""
        handler = self._get_load_handler()
        handler([])  # should not raise


class TestResetHandler:
    def test_reset_clears_reaction_items(self):
        ctx, mw = _make_context_and_mw()
        # Create a real instance of a REACTION_ITEM_TYPES class (bypass __init__)
        # so isinstance() in reset_handler returns True.
        item_cls = _init.REACTION_ITEM_TYPES[0]
        fake_item = item_cls.__new__(item_cls)
        ctx.scene.items.return_value = [fake_item]
        _init.initialize(ctx)
        handler = ctx.register_document_reset_handler.call_args[0][0]
        handler()
        ctx.scene.removeItem.assert_called()

    def test_reset_does_not_raise_with_empty_scene(self):
        ctx, mw = _make_context_and_mw()
        ctx.scene.items.return_value = []
        _init.initialize(ctx)
        handler = ctx.register_document_reset_handler.call_args[0][0]
        handler()  # should not raise

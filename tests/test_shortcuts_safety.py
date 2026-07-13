"""
tests/test_shortcuts_safety.py -- unit tests for main window shortcut restoration safety.

The plugin suppresses main-window keyboard shortcuts while a text item is in
edit mode by installing an event-filter on the main window.  It must NEVER
call setEnabled(False) on any QAction — that would grey-out the File/Edit
menus, which is the exact bug these tests guard against.
"""

from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QPointF
from reaction_sketcher.items import ReactionTextItem
from reaction_sketcher.mode_manager import ModeManager


def test_text_item_focus_out_restores_shortcuts_even_if_scene_is_none():
    # 1. Create a dummy main window and manager
    mw = MagicMock()
    mgr = MagicMock()
    mw._reaction_mode_manager = mgr
    mw.ui_manager = MagicMock()
    mw.ui_manager._reaction_mode_manager = mgr

    # 2. Mock get_main_window to return our mw when scene is valid
    scene = MagicMock()
    fake_view = MagicMock()
    fake_view.window.return_value = mw
    scene.views.return_value = [fake_view]

    # 3. Create a text item
    item = ReactionTextItem("Test", QPointF(0, 0))

    # Mock scene() to return our scene initially
    item.scene = MagicMock(return_value=scene)

    # 4. Trigger focusInEvent (mocked event)
    class DummyEvent:
        pass

    # Set TextEditorInteraction flag so focusInEvent tries to disable shortcuts
    from PyQt6.QtCore import Qt
    item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
    item.focusInEvent(DummyEvent())

    assert item._last_main_window is mw

    # 5. Set scene to return None (simulating removeItem)
    item.scene = MagicMock(return_value=None)

    # 6. Trigger focusOutEvent
    item.focusOutEvent(DummyEvent())

    # 7. Check if enable_main_window_shortcuts was called on the manager
    mgr.enable_main_window_shortcuts.assert_called_once()


def test_exit_reaction_mode_restores_shortcuts():
    mw = MagicMock()
    mw.init_manager = MagicMock()
    mw.init_manager.splitter = MagicMock()
    mw.init_manager.splitter.sizes.return_value = [500, 500]

    context = MagicMock()

    with patch.object(ModeManager, 'setup_toolbar'), \
         patch.object(ModeManager, 'setup_property_toolbar'):
        mode_mgr = ModeManager(mw, context)

    # Simulate shortcuts being disabled
    mode_mgr._shortcuts_disabled = True

    # Mock enable_main_window_shortcuts
    mode_mgr.enable_main_window_shortcuts = MagicMock()

    mode_mgr.disconnect_signals = MagicMock()
    mode_mgr._rewire_cleanup_2d_triggers = MagicMock()

    with patch('reaction_sketcher.mode_manager.revert_all_patches'):
        mode_mgr.exit_reaction_mode()
        mode_mgr.enable_main_window_shortcuts.assert_called_once()


def test_disable_shortcuts_only_uses_event_filter_not_setEnabled():
    """The disable path must NOT call setEnabled(False) on any QAction.

    Doing so visually greys out the File/Edit menus — the bug we are
    guarding against.  The correct approach is to install an event-filter
    on the main window that intercepts ShortcutOverride events.
    """
    mw = MagicMock()
    mw.installEventFilter = MagicMock()
    mw.removeEventFilter = MagicMock()
    context = MagicMock()

    with patch.object(ModeManager, 'setup_toolbar'), \
         patch.object(ModeManager, 'setup_property_toolbar'):
        mode_mgr = ModeManager(mw, context)

    # Call disable
    mode_mgr.disable_main_window_shortcuts()

    # event filter must be installed
    mw.installEventFilter.assert_called_once_with(mode_mgr)

    # _shortcuts_disabled flag must be set
    assert mode_mgr._shortcuts_disabled is True

    # CRITICAL: setEnabled must NEVER have been called on any child action
    mw.findChildren.assert_not_called()

    # Call enable
    mode_mgr.enable_main_window_shortcuts()

    mw.removeEventFilter.assert_called_once_with(mode_mgr)
    assert mode_mgr._shortcuts_disabled is False


def test_enable_shortcuts_idempotent_when_not_disabled():
    """enable_main_window_shortcuts is a no-op if shortcuts weren't disabled."""
    mw = MagicMock()
    mw.removeEventFilter = MagicMock()
    context = MagicMock()

    with patch.object(ModeManager, 'setup_toolbar'), \
         patch.object(ModeManager, 'setup_property_toolbar'):
        mode_mgr = ModeManager(mw, context)

    assert mode_mgr._shortcuts_disabled is False
    mode_mgr.enable_main_window_shortcuts()
    # removeEventFilter must NOT be called — nothing was installed
    mw.removeEventFilter.assert_not_called()

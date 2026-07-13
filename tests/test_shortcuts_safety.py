"""
tests/test_shortcuts_safety.py -- unit tests for main window shortcut restoration safety.
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
    # This should store the main window reference in _last_main_window
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
    # Mock layouts to avoid AttributeError during exit_reaction_mode
    mw.init_manager = MagicMock()
    mw.init_manager.splitter = MagicMock()
    mw.init_manager.splitter.sizes.return_value = [500, 500]

    context = MagicMock()
    
    # Mock setup_toolbar and setup_property_toolbar called in __init__
    with patch.object(ModeManager, 'setup_toolbar'), \
         patch.object(ModeManager, 'setup_property_toolbar'):
        mode_mgr = ModeManager(mw, context)
    
    # Simulate shortcuts being disabled
    mode_mgr._shortcuts_disabled = True
    
    # Mock enable_main_window_shortcuts
    mode_mgr.enable_main_window_shortcuts = MagicMock()
    
    # Mock disconnect_signals and revert_all_patches
    mode_mgr.disconnect_signals = MagicMock()
    mode_mgr._rewire_cleanup_2d_triggers = MagicMock()
    
    with patch('reaction_sketcher.mode_manager.revert_all_patches') as mock_revert:
        mode_mgr.exit_reaction_mode()
        mode_mgr.enable_main_window_shortcuts.assert_called_once()


def test_shortcuts_failsafe_preserves_actions():
    mw = MagicMock()
    # Mock install/remove event filter methods
    mw.installEventFilter = MagicMock()
    mw.removeEventFilter = MagicMock()
    context = MagicMock()

    with patch.object(ModeManager, 'setup_toolbar'), \
         patch.object(ModeManager, 'setup_property_toolbar'):
        mode_mgr = ModeManager(mw, context)

    action1 = MagicMock()
    action1.shortcut.return_value = MagicMock(isEmpty=lambda: False)
    action1.isEnabled.return_value = True

    # Mock findChildren to return our action
    mw.findChildren.return_value = [action1]

    # 1. Disable shortcuts
    mode_mgr.disable_main_window_shortcuts()
    assert action1 in mode_mgr._disabled_actions_state
    action1.setEnabled.assert_any_call(False)

    # Reset mock calls
    action1.setEnabled.reset_mock()

    # 2. Call disable again, but simulate _shortcuts_disabled being True (should return early)
    mode_mgr._shortcuts_disabled = True
    mode_mgr.disable_main_window_shortcuts()
    # It should not clear _disabled_actions_state!
    assert action1 in mode_mgr._disabled_actions_state

    # 3. Simulate desync: _shortcuts_disabled is False, but _disabled_actions_state is not empty.
    # Call disable again, it should NOT clear the list or lose action1.
    mode_mgr._shortcuts_disabled = False
    action2 = MagicMock()
    action2.shortcut.return_value = MagicMock(isEmpty=lambda: False)
    action2.isEnabled.return_value = True
    mw.findChildren.return_value = [action1, action2]

    mode_mgr.disable_main_window_shortcuts()
    assert action1 in mode_mgr._disabled_actions_state
    assert action2 in mode_mgr._disabled_actions_state

    # 4. Call enable_main_window_shortcuts when _shortcuts_disabled is False
    # (due to desync), it should still restore all actions in _disabled_actions_state!
    mode_mgr._shortcuts_disabled = False
    mode_mgr.enable_main_window_shortcuts()
    action1.setEnabled.assert_called_with(True)
    action2.setEnabled.assert_called_with(True)
    assert mode_mgr._disabled_actions_state == []

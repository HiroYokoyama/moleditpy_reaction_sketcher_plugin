import pytest
from unittest.mock import MagicMock
from reaction_sketcher.mode_manager import ModeManager


def test_convert_button_disabled_in_reaction_mode():
    mw = MagicMock()
    init_mgr = MagicMock()
    convert_btn = MagicMock()
    init_mgr.convert_button = convert_btn
    mw.init_manager = init_mgr

    mm = ModeManager(mw, context=MagicMock())
    mm.set_3d_action_state(False)
    convert_btn.setEnabled.assert_called_with(False)

    mm.set_3d_action_state(True)
    convert_btn.setEnabled.assert_called_with(True)

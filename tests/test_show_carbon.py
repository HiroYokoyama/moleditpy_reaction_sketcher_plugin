import pytest
from unittest.mock import MagicMock
from reaction_sketcher.mode_manager import ModeManager


def test_toggle_show_carbon():
    mw = MagicMock()
    scene = MagicMock()
    mw.scene = scene
    atom = MagicMock()
    atom.update_style = MagicMock()
    scene.atom_items = {1: atom}
    scene._rs_show_carbon = False

    mm = ModeManager(mw, context=MagicMock())
    mm.toggle_show_carbon(True)

    assert scene._rs_show_carbon is True
    atom.update_style.assert_called_once()
    scene.update.assert_called()

    mm.toggle_show_carbon(False)
    assert scene._rs_show_carbon is False

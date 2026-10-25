"""Exercise signal ownership with real Qt rather than the stub test suite."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reaction_sketcher import patcher
from reaction_sketcher.mode_manager import ModeManager


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("method_name", [
    "clean_up_2d_structure", "copy_selection", "cut_selection", "paste_from_clipboard",
    "save_project", "save_project_as", "export_2d_png", "export_2d_svg",
])
def test_rewire_preserves_observers_and_tracks_patch_revert(app, method_name):
    class Manager:
        pass

    stock, patched, observer = Mock(), Mock(), Mock()
    original = lambda self: stock()
    setattr(Manager, method_name, original)
    manager = Manager()
    action = QAction("Host action")
    action.triggered.connect(getattr(manager, method_name))
    action.triggered.connect(observer)
    patcher._core_originals[(Manager, method_name)] = original
    setattr(Manager, method_name, lambda self: patched())
    try:
        for _ in range(3):
            patcher.rewire_method_signal(action, "triggered", manager, method_name)
        action.trigger()
        patched.assert_called_once_with()
        stock.assert_not_called()
        observer.assert_called_once()
        setattr(Manager, method_name, original)
        patcher._core_originals.pop((Manager, method_name))
        patcher.rewire_method_signal(action, "triggered", manager, method_name)
        action.trigger()
        stock.assert_called_once_with()
        assert observer.call_count == 2
        assert patched.call_count == 1
    finally:
        patcher._core_originals.pop((Manager, method_name), None)


def test_fresh_action_without_original_connection(app):
    manager = SimpleNamespace(run=Mock())
    action = QAction("New action")
    patcher.rewire_method_signal(action, "triggered", manager, "run")
    patcher.rewire_method_signal(action, "triggered", manager, "run")
    action.trigger()
    manager.run.assert_called_once_with()


def test_mode_manager_rewires_all_host_controls_once(app):
    class Manager:
        def clean_up_2d_structure(self):
            calls.append("stock")

    calls = []
    receiver = Manager()
    original = Manager.clean_up_2d_structure
    button = QPushButton()
    action = QAction("Clean Up 2D")
    observer = Mock()
    button.clicked.connect(receiver.clean_up_2d_structure)
    button.clicked.connect(observer)
    action.triggered.connect(receiver.clean_up_2d_structure)
    action.triggered.connect(observer)
    window = SimpleNamespace(
        init_manager=SimpleNamespace(cleanup_button=button),
        edit_actions_manager=receiver,
    )
    manager = SimpleNamespace(
        main_window=window,
        _find_menu_action=lambda name: action if name == "Clean Up 2D" else None,
    )
    patcher._core_originals[(Manager, "clean_up_2d_structure")] = original
    Manager.clean_up_2d_structure = lambda self: calls.append("patched")
    try:
        ModeManager._rewire_cleanup_2d_triggers(manager)
        ModeManager._rewire_cleanup_2d_triggers(manager)
        button.click()
        action.trigger()
        assert calls == ["patched", "patched"]
        assert observer.call_count == 2
    finally:
        patcher._core_originals.pop((Manager, "clean_up_2d_structure"), None)


def test_recreated_action_gets_its_own_connection(app):
    manager = SimpleNamespace(run=Mock())
    for _ in range(3):
        action = QAction("New action")
        patcher.rewire_method_signal(action, "triggered", manager, "run")
        action.trigger()
    assert manager.run.call_count == 3

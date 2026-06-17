"""
Integration tests for reaction_sketcher/__init__.py
Verifies the plugin contract (menu action, save/load/reset handlers) without Qt.

Two execution modes
-------------------
1. Stub mode    Ealways runs (CI + local).
2. Real-context mode  Eruns when python_molecular_editor is present.

CI setup
--------
    - name: Clone main app (for real-context integration tests)
      run: git clone --depth 1 https://github.com/HiroYokoyama/python_molecular_editor.git
             ../python_molecular_editor || true
"""
import sys
import os
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub Qt before importing the plugin
# conftest.py already installs stubs  Ethis function is idempotent.
# ---------------------------------------------------------------------------

def _install_stubs():
    if "PyQt6" in sys.modules and hasattr(sys.modules["PyQt6"], "__file__"):
        return  # real Qt already available

    pyqt6 = types.ModuleType("PyQt6")

    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_core.Qt = MagicMock()

    class _QTimer:
        @staticmethod
        def singleShot(ms, fn):
            pass  # suppress deferred Qt calls

    qt_core.QTimer = _QTimer
    qt_core.pyqtSignal = MagicMock()
    qt_core.QThread = MagicMock()

    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    for cls_name in ["QMenu", "QDialog", "QVBoxLayout", "QHBoxLayout", "QWidget"]:
        setattr(qt_widgets, cls_name, MagicMock())

    qt_gui = types.ModuleType("PyQt6.QtGui")
    qt_gui.QAction = MagicMock()
    qt_gui.QColor = MagicMock()

    sys.modules.setdefault("PyQt6", pyqt6)
    sys.modules.setdefault("PyQt6.QtCore", qt_core)
    sys.modules.setdefault("PyQt6.QtWidgets", qt_widgets)
    sys.modules.setdefault("PyQt6.QtGui", qt_gui)


_install_stubs()

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from reaction_sketcher import initialize, PLUGIN_NAME, PLUGIN_VERSION


# ---------------------------------------------------------------------------
# Stub PluginContext
# ---------------------------------------------------------------------------

class _StubContext:
    def __init__(self):
        self._menu_actions = []
        self._save_handler = None
        self._load_handler = None
        self._reset_handler = None
        self._status_messages = []
        # scene attribute accessed by save/reset handlers
        self.scene = None

    def add_menu_action(self, path, callback, **kwargs):
        self._menu_actions.append((path, callback))

    def register_save_handler(self, fn):
        self._save_handler = fn

    def register_load_handler(self, fn):
        self._load_handler = fn

    def register_document_reset_handler(self, fn):
        self._reset_handler = fn

    def show_status_message(self, msg, duration=0):
        self._status_messages.append((msg, duration))

    # Full standard API stubs
    def get_main_window(self):
        mw = MagicMock()
        mw.menuBar.return_value.findChild.return_value = None
        mw.init_manager.view_2d = None
        mw.state_manager = None
        mw.data = None
        return mw

    def register_file_opener(self, ext, fn, priority=0): pass
    def register_drop_handler(self, fn, priority=0): pass
    def add_export_action(self, label, fn): pass
    def add_analysis_tool(self, label, fn): pass
    def add_toolbar_action(self, fn, text, icon=None, tooltip=None): pass
    def register_window(self, key, win): pass
    def get_window(self, key): return None


# ---------------------------------------------------------------------------
# Tests: metadata
# ---------------------------------------------------------------------------

class TestMetadata(unittest.TestCase):
    def test_plugin_name(self):
        self.assertEqual(PLUGIN_NAME, "Reaction Sketcher")

    def test_plugin_version_is_semver(self):
        parts = PLUGIN_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit(), f"Non-numeric version part: {p!r}")


# ---------------------------------------------------------------------------
# Tests: initialize contract
# ---------------------------------------------------------------------------

class TestInitialize(unittest.TestCase):
    def setUp(self):
        self.ctx = _StubContext()
        initialize(self.ctx)

    def test_registers_menu_action(self):
        self.assertGreater(len(self.ctx._menu_actions), 0)

    def test_menu_action_path_mentions_reaction_sketcher(self):
        paths = [p for p, _ in self.ctx._menu_actions]
        self.assertTrue(
            any("Reaction" in p for p in paths),
            f"Expected 'Reaction' in menu path, got: {paths}",
        )

    def test_menu_action_is_callable(self):
        for _, cb in self.ctx._menu_actions:
            self.assertTrue(callable(cb))

    def test_menu_path_is_namespaced(self):
        for path, _ in self.ctx._menu_actions:
            self.assertIn("/", path)

    def test_registers_save_handler(self):
        self.assertIsNotNone(self.ctx._save_handler)

    def test_registers_load_handler(self):
        self.assertIsNotNone(self.ctx._load_handler)

    def test_registers_reset_handler(self):
        self.assertIsNotNone(self.ctx._reset_handler)

    def test_shows_status_message_on_init(self):
        self.assertGreater(len(self.ctx._status_messages), 0)


# ---------------------------------------------------------------------------
# Tests: save handler contract
# ---------------------------------------------------------------------------

class TestSaveHandler(unittest.TestCase):
    def setUp(self):
        self.ctx = _StubContext()
        initialize(self.ctx)

    def test_save_returns_dict(self):
        result = self.ctx._save_handler()
        self.assertIsInstance(result, dict)

    def test_save_includes_plugin_version(self):
        result = self.ctx._save_handler()
        self.assertIn("plugin_version", result)

    def test_save_includes_items_key(self):
        result = self.ctx._save_handler()
        self.assertIn("items", result)

    def test_save_items_is_list(self):
        result = self.ctx._save_handler()
        self.assertIsInstance(result["items"], list)

    def test_save_includes_reaction_mode_active(self):
        result = self.ctx._save_handler()
        self.assertIn("reaction_mode_active", result)


# ---------------------------------------------------------------------------
# Tests: load handler contract
# ---------------------------------------------------------------------------

class TestLoadHandler(unittest.TestCase):
    def setUp(self):
        self.ctx = _StubContext()
        initialize(self.ctx)

    def test_load_none_is_safe(self):
        self.ctx._load_handler(None)  # must not raise

    def test_load_empty_dict_is_safe(self):
        self.ctx._load_handler({})  # must not raise

    def test_load_empty_items_list_is_safe(self):
        self.ctx._load_handler({"items": [], "reaction_mode_active": False})

    def test_load_accepts_auto_start_pref(self):
        self.ctx._load_handler({"auto_start_pref": False, "items": []})


# ---------------------------------------------------------------------------
# Tests: reset handler contract
# ---------------------------------------------------------------------------

class TestResetHandler(unittest.TestCase):
    def setUp(self):
        self.ctx = _StubContext()
        initialize(self.ctx)

    def test_reset_is_safe_with_no_scene(self):
        self.ctx.scene = None
        self.ctx._reset_handler()  # must not raise

    def test_reset_is_safe_with_empty_scene(self):
        mock_scene = MagicMock()
        mock_scene.items.return_value = []
        self.ctx.scene = mock_scene
        self.ctx._reset_handler()  # must not raise


# ---------------------------------------------------------------------------
# Real PluginContext tier
# ---------------------------------------------------------------------------

_MAIN_APP_CANDIDATES = [
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "python_molecular_editor", "moleditpy", "src")
    ),
    os.environ.get("CI_MAIN_APP_SRC", ""),
]
_MAIN_APP_SRC = next(
    (p for p in _MAIN_APP_CANDIDATES if p and os.path.isdir(p)),
    None,
)
HAS_MAIN_APP = _MAIN_APP_SRC is not None

try:
    import pytest
    _skipif = pytest.mark.skipif(
        not HAS_MAIN_APP,
        reason="main app not found; clone python_molecular_editor or set CI_MAIN_APP_SRC",
    )
except ImportError:
    def _skipif(cls):
        return unittest.skip("pytest not available")(cls)



def _clear_qt_stubs():
    """Remove fake PyQt6 stub modules so real PyQt6 can be imported by moleditpy."""
    to_remove = [
        k for k in list(sys.modules)
        if k.startswith("PyQt6") and not hasattr(sys.modules[k], "__file__")
    ]
    for k in to_remove:
        del sys.modules[k]
    # Clear any moleditpy import that may have been attempted with stubs
    for k in [k for k in list(sys.modules) if k.startswith("moleditpy")]:
        del sys.modules[k]

@_skipif
class TestWithRealPluginContext(unittest.TestCase):
    """Verify initialize() works with the actual MoleditPy PluginContext."""

    @classmethod
    def setUpClass(cls):
        if not HAS_MAIN_APP:
            return
        # Load plugin_interface.py directly to avoid triggering moleditpy/__init__.py
        # which imports PyQt6 and conflicts with PySide6 loaded by pytest-qt on Windows.
        import importlib.util as _ilu
        _pi_path = os.path.join(_MAIN_APP_SRC, 'moleditpy', 'plugins', 'plugin_interface.py')
        _spec = _ilu.spec_from_file_location('moleditpy.plugins.plugin_interface', _pi_path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        cls.PluginContext = _mod.PluginContext
        mock_manager = MagicMock()
        mw = MagicMock()
        mw.menuBar.return_value.findChild.return_value = None
        mw.init_manager.view_2d = None
        mw.state_manager = None
        mw.data = None
        mock_manager.get_main_window.return_value = mw
        cls.real_ctx = cls.PluginContext(mock_manager, PLUGIN_NAME)

    def test_real_initialize_does_not_raise(self):
        try:
            initialize(self.real_ctx)
        except Exception as e:
            self.fail(f"initialize(real_context) raised: {e}")

    def test_real_context_is_plugincontext_instance(self):
        self.assertIsInstance(self.real_ctx, self.PluginContext)

    def test_stub_interface_matches_real(self):
        for method in [
            "add_menu_action", "register_save_handler",
            "register_load_handler", "register_document_reset_handler",
            "show_status_message", "get_main_window",
        ]:
            self.assertTrue(
                hasattr(self.PluginContext, method),
                f"Real PluginContext missing: {method}",
            )


if __name__ == "__main__":
    unittest.main()

"""The File > Export > 2D Formats actions must reach the patched exporters.

Qt captured export_manager's bound methods when the menus were built at
startup, so patching the class afterwards left the menu calling the stock
exporter and the saved PNG/SVG lost every reaction item.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

import reaction_sketcher.patcher as patcher_mod
from tests.rs_fakes import FakeMainWindow


class FakeExportManager:
    """Stands in for MainWindowExport, the class the patcher rewrites."""

    def export_2d_png(self):
        self.called = "stock_png"

    def export_2d_svg(self):
        self.called = "stock_svg"


@pytest.fixture(autouse=True)
def _export_module_and_revert():
    if "modules" not in sys.modules:
        sys.modules["modules"] = types.ModuleType("modules")
    saved = sys.modules.get("modules.main_window_export")
    mod = types.ModuleType("modules.main_window_export")
    mod.MainWindowExport = FakeExportManager
    sys.modules["modules.main_window_export"] = mod
    yield
    patcher_mod.revert_all_patches()
    if saved is None:
        del sys.modules["modules.main_window_export"]
    else:
        sys.modules["modules.main_window_export"] = saved


class FakeAction:
    def __init__(self, text):
        self._text = text
        self._props = {}
        self.slots = []
        self.disconnect_calls = 0
        self.triggered = self

    def text(self):
        return self._text

    def property(self, name):
        return self._props.get(name)

    def setProperty(self, name, value):
        self._props[name] = value

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self):
        self.disconnect_calls += 1
        self.slots.clear()

    def trigger(self):
        for slot in list(self.slots):
            slot(False)


class FakeMenu:
    def __init__(self, title, actions):
        self._title = title
        self._actions = actions

    def title(self):
        return self._title

    def actions(self):
        return list(self._actions)


def _mw_with_export_menu():
    from PyQt6.QtCore import QPointF
    from tests.rs_fakes import FakeAtomItem, FakeBondItem

    mw = FakeMainWindow()
    a1 = FakeAtomItem(1, "C")
    a2 = FakeAtomItem(2, "O")
    a1.setPos(QPointF(0, 0))
    a2.setPos(QPointF(10, 0))
    bond = FakeBondItem(a1, a2, order=1)
    for item in (a1, a2, bond):
        mw.scene.addItem(item)
    mw.scene.atom_items = {1: a1, 2: a2}
    mw.scene.bond_items = {(1, 2): bond}
    mgr = FakeExportManager()
    mgr.host = mw
    mw.export_manager = mgr
    png = FakeAction("PNG Image...")
    svg = FakeAction("SVG Image...")
    other = FakeAction("MOL File...")
    menu_2d = FakeMenu("2D Formats", [png, svg, other])
    menu_3d = FakeMenu("3D Formats", [FakeAction("PNG Image...")])
    mw.findChildren = lambda _cls: [menu_2d, menu_3d]
    return mw, mgr, png, svg, other, menu_3d


class TestRewire2dExportActions:
    def test_menu_actions_reach_the_patched_methods(self):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        ctx = MagicMock()
        patcher_mod.apply_core_patches(mw, context=ctx)

        assert png.disconnect_calls == 1
        assert svg.disconnect_calls == 1
        # An empty document makes the patched exporters bail out with a status
        # message the stock ones never send, which is what identifies them.
        png.trigger()
        svg.trigger()
        assert ctx.show_status_message.call_args_list[-2:] == [
            (("Nothing to export.",),),
            (("Nothing to export.",),),
        ]
        assert not hasattr(mgr, "called")

    def test_unrelated_actions_are_left_alone(self):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        patcher_mod.apply_core_patches(mw, context=MagicMock())
        assert other.disconnect_calls == 0
        # The 3D PNG action shares its text but lives in another menu.
        assert menu_3d.actions()[0].disconnect_calls == 0

    def test_rewiring_is_not_repeated(self):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        patcher_mod.apply_core_patches(mw, context=MagicMock())
        patcher_mod.apply_core_patches(mw, context=MagicMock())
        assert png.disconnect_calls == 1
        assert len(png.slots) == 1

    def test_host_without_find_children_is_skipped(self):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        del mw.findChildren
        patcher_mod.apply_core_patches(mw, context=MagicMock())  # must not raise
        assert png.disconnect_calls == 0

    def test_reverting_restores_the_stock_exporter(self):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        patcher_mod.apply_core_patches(mw, context=MagicMock())
        patcher_mod.revert_core_patches()
        svg.trigger()
        assert mgr.called == "stock_svg"


class TestExportDialogParent:
    """The patched exporters live on ExportManager, so the parent is its host.

    Passing `self` handed QFileDialog an ExportManager and PyQt raised
    TypeError: argument 1 has unexpected type 'ExportManager'.
    """

    @pytest.mark.parametrize(
        "action_name, caption",
        [("png", "Export 2D as PNG"), ("svg", "Export 2D as SVG")],
    )
    def test_save_dialog_gets_the_window(self, monkeypatch, action_name, caption):
        mw, mgr, png, svg, other, menu_3d = _mw_with_export_menu()
        mw.state_manager.data.atoms = {1: object()}
        patcher_mod.apply_core_patches(mw, context=MagicMock())

        seen = {}

        def fake_save(parent, title, *args, **kwargs):
            seen["parent"] = parent
            seen["title"] = title
            return "", ""

        monkeypatch.setattr(
            patcher_mod.QFileDialog, "getSaveFileName", staticmethod(fake_save)
        )
        {"png": png, "svg": svg}[action_name].trigger()

        assert seen["title"] == caption
        assert seen["parent"] is mw


class TestExportCallback:
    """The reaction toolbar button must find the exporter on export_manager.

    The core moved export_2d_png off MainWindow, so the old
    hasattr(main_window, ...) guard dropped the button entirely.
    """

    class FakeToolbar:
        def __init__(self):
            self.added = []
            self.separators = 0

        def actions(self):
            return []

        def addSeparator(self):
            self.separators += 1

        def addAction(self, text, callback=None):
            self.added.append((text, callback))
            return MagicMock()

    def _patch_with_toolbar(self, mw):
        toolbar = self.FakeToolbar()
        rmm = MagicMock()
        rmm.property_toolbar = toolbar
        mw._reaction_mode_manager = rmm
        patcher_mod.apply_core_patches(mw, context=MagicMock())
        return dict(toolbar.added)

    def test_button_added_and_routed_to_the_manager(self):
        mw, mgr, *_ = _mw_with_export_menu()
        calls = []
        mgr.export_2d_png = lambda: calls.append("manager")
        added = self._patch_with_toolbar(mw)

        assert "Export PNG" in added
        added["Export PNG"]()
        assert calls == ["manager"]

    def test_button_skipped_when_nothing_provides_it(self):
        mw, mgr, *_ = _mw_with_export_menu()
        del mw.export_manager
        added = self._patch_with_toolbar(mw)
        assert "Export PNG" not in added

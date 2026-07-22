"""
tests/test_settings_dialog_coverage.py -- coverage tests for
AdvancedSettingsDialog (reaction_sketcher/settings_dialog.py).

AdvancedSettingsDialog subclasses QDialog, which tests/conftest.py stubs as a
bare MagicMock() *instance* -- instantiating the real class therefore never
runs our Python source (MagicMock.__call__ intercepts construction and hands
back an opaque mock). Per the project's established technique (see
test_settings_dialog_bugfixes.py), each method is extracted from source via
ast + exec and driven with a lightweight fake `self`. Unlike the existing
file, we exec into a copy of the *module's own globals* so the extracted
method body can resolve names like QColorDialog/QMessageBox/QInputDialog/
QComboBox/json/os that it references at module scope.
"""

import ast
import inspect
import json
import os
from unittest.mock import MagicMock

import reaction_sketcher.settings_dialog as sd
import PyQt6.QtWidgets as qtw
from PyQt6.QtGui import QColor


def _bind_real_get_factory_defaults(fake_self):
    """save_template/delete_template/load_templates call self.get_factory_defaults();
    bind the real (extracted) implementation for tests that check its output."""
    _ns, real_fn = _extract("get_factory_defaults")
    fake_self.get_factory_defaults = lambda: real_fn(fake_self)


def _extract(method_name):
    """Extract `method_name` from AdvancedSettingsDialog and exec it as a
    free function whose globals are a copy of the settings_dialog module's
    own globals (so QColorDialog, QMessageBox, QInputDialog, json, os, ...
    all resolve). Returns (globals_dict, function).

    The extracted AST node keeps its original lineno/filename (we compile the
    node in place rather than round-tripping through re-parsed source text),
    so pytest-cov attributes executed lines back to the real
    reaction_sketcher/settings_dialog.py source -- letting these tests count
    towards that file's statement coverage.
    """
    filename = sd.__file__
    src = inspect.getsource(sd)
    tree = ast.parse(src, filename=filename)
    class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method_node = next(
        n
        for n in class_node.body
        if isinstance(n, ast.FunctionDef) and n.name == method_name
    )
    module = ast.Module(body=[method_node], type_ignores=[])
    ns = dict(vars(sd))
    exec(compile(module, filename, "exec"), ns)
    return ns, ns[method_name]


# ---------------------------------------------------------------------------
# Fake widgets (real objects, not Mocks, so hasattr()/state checks behave)
# ---------------------------------------------------------------------------


class FakeSpin:
    def __init__(self, initial=0.0):
        self._value = initial
        self._enabled = True
        self.set_calls = []

    def setValue(self, v):
        self._value = v
        self.set_calls.append(v)

    def value(self):
        return self._value

    def setRange(self, lo, hi):
        pass

    def setSingleStep(self, s):
        pass

    def setEnabled(self, v):
        self._enabled = v

    def isEnabled(self):
        return self._enabled


class FakeCombo:
    def __init__(self, text="", items=None):
        self._text = text
        self._items = list(items or [])
        self._visible = True

    def addItems(self, items):
        self._items.extend(items)

    def addItem(self, item):
        self._items.append(item)

    def clear(self):
        self._items = []

    def setCurrentText(self, t):
        self._text = t

    def currentText(self):
        return self._text

    def setVisible(self, v):
        self._visible = v

    def isVisible(self):
        return self._visible


class FakeLabel:
    def __init__(self):
        self._visible = True

    def setVisible(self, v):
        self._visible = v


class FakeButton:
    def __init__(self):
        self.text_ = ""
        self.style = ""

    def setStyleSheet(self, s):
        self.style = s

    def setText(self, t):
        self.text_ = t


class FakeDialogSelf:
    """Lightweight fake `self` for AdvancedSettingsDialog methods."""

    def __init__(self, item=None, item_kind="general"):
        self.item = item
        self.item_kind = item_kind
        for name in (
            "update_ui_state",
            "choose_color",
            "update_color_button",
            "get_factory_defaults",
            "apply_template_to_ui",
            "save_template",
            "delete_template",
            "on_template_selected",
            "accept",
            "reject",
        ):
            setattr(self, name, MagicMock())
        self.applyRequested = MagicMock()


# ---------------------------------------------------------------------------
# init_ui
# ---------------------------------------------------------------------------


class FakeItemPlain:
    """No optional attrs at all -- exercises only the base color path."""


class FakeItemWithTextColor:
    def defaultTextColor(self):
        return QColor("#333333")


class FakeItemFullArrow:
    def __init__(self):
        self.pen_color = QColor("#222222")
        self.pen_width = 3
        self.head_size = 25.0
        self.head_angle = 25.0
        self.head_concavity = 0.5
        self.head_style = "chevron"
        self.head_side = -1
        self.double_arrow_offset = 8.0
        self.cross_size = 15.0
        self.start_p = MagicMock(x=lambda: 0.0, y=lambda: 0.0)
        self.end_p = MagicMock(x=lambda: 10.0, y=lambda: 20.0)

    def set_rect_size(self, w, h):
        pass


class _Rect:
    def __init__(self, w, h):
        self._w = w
        self._h = h

    def width(self):
        return self._w

    def height(self):
        return self._h


class FakeItemWithRect:
    def __init__(self):
        self.pen_color = QColor("#222222")
        self.pen_width = 2
        self.rect = _Rect(50.0, 80.0)
        self.bracket_type = "square"


class FakeItemWithCurvature:
    def __init__(self):
        self.curvature = 0.4


class FakeItemWithSize:
    def __init__(self):
        self.size = 28.0


class TestInitUi:
    def _run(self, item, item_kind="general"):
        _ns, init_ui = _extract("init_ui")
        fake_self = FakeDialogSelf(item=item, item_kind=item_kind)
        init_ui(fake_self)
        return fake_self

    def test_plain_item_only_creates_color_button(self):
        fake_self = self._run(FakeItemPlain())
        assert hasattr(fake_self, "color_btn")
        assert not hasattr(fake_self, "width_spin")
        assert not hasattr(fake_self, "head_size_spin")
        assert fake_self.update_ui_state.called

    def test_text_item_uses_default_text_color(self):
        fake_self = self._run(FakeItemWithTextColor())
        assert fake_self.current_color.name() == "#333333"

    def test_full_arrow_item_creates_expected_widgets(self):
        fake_self = self._run(FakeItemFullArrow(), item_kind="arrow")
        for attr in (
            "width_spin",
            "head_size_spin",
            "head_angle_spin",
            "concavity_spin",
            "head_style_combo",
            "head_side_label",
            "head_side_combo",
            "spacing_spin",
            "cross_size_spin",
            "rect_w_spin",
            "rect_h_spin",
        ):
            assert hasattr(fake_self, attr), f"missing {attr}"
        assert not hasattr(fake_self, "bracket_combo")
        assert not hasattr(fake_self, "item_size_spin")

    def test_rect_item_creates_rect_spins_from_rect_attr(self):
        fake_self = self._run(FakeItemWithRect(), item_kind="bracket")
        assert hasattr(fake_self, "rect_w_spin")
        assert hasattr(fake_self, "bracket_combo")

    def test_curvature_item_creates_curvature_spin(self):
        fake_self = self._run(FakeItemWithCurvature(), item_kind="curved_double")
        assert hasattr(fake_self, "curvature_spin")

    def test_size_item_creates_item_size_spin(self):
        fake_self = self._run(FakeItemWithSize())
        assert hasattr(fake_self, "item_size_spin")
        assert not hasattr(fake_self, "rect_w_spin")


# ---------------------------------------------------------------------------
# update_ui_state
# ---------------------------------------------------------------------------


class TestUpdateUiState:
    def _self(self, **kw):
        fake_self = FakeDialogSelf(item=kw.pop("item", FakeItemPlain()))
        fake_self.item_kind = kw.pop("item_kind", "general")
        for k, v in kw.items():
            setattr(fake_self, k, v)
        return fake_self

    def test_no_optional_widgets_is_a_no_op(self):
        _ns, fn = _extract("update_ui_state")
        fake_self = self._self()
        fn(fake_self)  # must not raise

    def test_concavity_enabled_when_combo_says_chevron(self):
        _ns, fn = _extract("update_ui_state")
        combo = FakeCombo("chevron")
        spin = FakeSpin()
        fake_self = self._self(head_style_combo=combo, concavity_spin=spin)
        fn(fake_self)
        assert spin.isEnabled() is True

    def test_concavity_disabled_when_combo_says_other(self):
        _ns, fn = _extract("update_ui_state")
        combo = FakeCombo("triangle")
        spin = FakeSpin()
        fake_self = self._self(head_style_combo=combo, concavity_spin=spin)
        fn(fake_self)
        assert spin.isEnabled() is False

    def test_concavity_falls_back_to_item_head_style(self):
        _ns, fn = _extract("update_ui_state")

        class Item:
            head_style = "chevron"

        spin = FakeSpin()
        fake_self = self._self(item=Item(), concavity_spin=spin)
        fn(fake_self)
        assert spin.isEnabled() is True

    def test_head_side_visible_for_harpoon(self):
        _ns, fn = _extract("update_ui_state")
        combo = FakeCombo("harpoon")
        side_combo = FakeCombo("Down")
        label = FakeLabel()
        fake_self = self._self(
            head_style_combo=combo, head_side_combo=side_combo, head_side_label=label
        )
        fn(fake_self)
        assert side_combo.isVisible() is True
        assert label._visible is True

    def test_head_side_visible_for_curved_item_kind(self):
        _ns, fn = _extract("update_ui_state")
        side_combo = FakeCombo("Up")
        fake_self = self._self(item_kind="curved_double", head_side_combo=side_combo)
        fn(fake_self)
        assert side_combo.isVisible() is True

    def test_head_side_hidden_when_neither_harpoon_nor_curved(self):
        _ns, fn = _extract("update_ui_state")
        combo = FakeCombo("triangle")
        side_combo = FakeCombo("Up")
        fake_self = self._self(
            item_kind="arrow", head_style_combo=combo, head_side_combo=side_combo
        )
        fn(fake_self)
        assert side_combo.isVisible() is False

    def test_head_side_falls_back_to_item_head_style(self):
        _ns, fn = _extract("update_ui_state")

        class Item:
            head_style = "harpoon"

        side_combo = FakeCombo("Up")
        fake_self = self._self(item=Item(), head_side_combo=side_combo)
        fn(fake_self)
        assert side_combo.isVisible() is True


# ---------------------------------------------------------------------------
# choose_color / update_color_button
# ---------------------------------------------------------------------------


class TestChooseColor:
    def test_valid_color_updates_current_and_button(self):
        ns, fn = _extract("choose_color")
        new_color = MagicMock()
        new_color.isValid.return_value = True
        ns["QColorDialog"].getColor = MagicMock(return_value=new_color)
        fake_self = FakeDialogSelf()
        fake_self.current_color = QColor("#111111")
        fn(fake_self)
        assert fake_self.current_color is new_color
        assert fake_self.update_color_button.called

    def test_invalid_color_leaves_current_unchanged(self):
        ns, fn = _extract("choose_color")
        rejected = MagicMock()
        rejected.isValid.return_value = False
        ns["QColorDialog"].getColor = MagicMock(return_value=rejected)
        fake_self = FakeDialogSelf()
        orig = QColor("#111111")
        fake_self.current_color = orig
        fn(fake_self)
        assert fake_self.current_color is orig
        assert not fake_self.update_color_button.called


class TestUpdateColorButton:
    def test_sets_stylesheet_and_text(self):
        _ns, fn = _extract("update_color_button")
        fake_self = FakeDialogSelf()
        fake_self.current_color = QColor("#abcdef")
        fake_self.color_btn = FakeButton()
        fn(fake_self)
        assert "#abcdef" in fake_self.color_btn.style
        assert fake_self.color_btn.text_ == "#abcdef"


# ---------------------------------------------------------------------------
# get_current_values / set_ui_values
# ---------------------------------------------------------------------------


class TestGetCurrentValues:
    def test_minimal_only_color(self):
        _ns, fn = _extract("get_current_values")
        fake_self = FakeDialogSelf()
        fake_self.current_color = QColor("#010203")
        vals = fn(fake_self)
        assert vals == {"color": "#010203"}

    def test_full_set_of_widgets(self):
        _ns, fn = _extract("get_current_values")
        fake_self = FakeDialogSelf()
        fake_self.current_color = QColor("#010203")
        fake_self.width_spin = FakeSpin(3)
        fake_self.head_size_spin = FakeSpin(25.0)
        fake_self.head_angle_spin = FakeSpin(25.0)
        fake_self.concavity_spin = FakeSpin(0.5)
        fake_self.curvature_spin = FakeSpin(0.4)
        fake_self.spacing_spin = FakeSpin(8.0)
        fake_self.cross_size_spin = FakeSpin(15.0)
        fake_self.item_size_spin = FakeSpin(28.0)
        fake_self.rect_w_spin = FakeSpin(50.0)
        fake_self.rect_h_spin = FakeSpin(80.0)
        fake_self.bracket_combo = FakeCombo("square")
        fake_self.head_style_combo = FakeCombo("chevron")
        fake_self.head_side_combo = FakeCombo("Up")
        vals = fn(fake_self)
        assert vals["width"] == 3
        assert vals["head_size"] == 25.0
        assert vals["head_angle"] == 25.0
        assert vals["head_concavity"] == 0.5
        assert vals["curvature"] == 0.4
        assert vals["double_arrow_offset"] == 8.0
        assert vals["cross_size"] == 15.0
        assert vals["size"] == 28.0
        assert vals["rect_width"] == 50.0
        assert vals["rect_height"] == 80.0
        assert vals["bracket_type"] == "square"
        assert vals["head_style"] == "chevron"
        assert vals["head_side"] == -1  # "Up" -> -1

        fake_self.head_side_combo.setCurrentText("Down")
        vals2 = fn(fake_self)
        assert vals2["head_side"] == 1


class TestSetUiValues:
    def test_color_updates_button(self):
        _ns, fn = _extract("set_ui_values")
        fake_self = FakeDialogSelf(item=FakeItemPlain())
        fake_self.current_color = QColor("#000000")
        fake_self.update_color_button = MagicMock()
        fn(fake_self, {"color": "#ff0000"})
        assert fake_self.current_color.name() == "#ff0000"
        assert fake_self.update_color_button.called

    def test_bracket_type_updates_item_and_combo(self):
        _ns, fn = _extract("set_ui_values")

        class Item:
            bracket_type = "square"

        item = Item()
        fake_self = FakeDialogSelf(item=item)
        fake_self.bracket_combo = FakeCombo("square")
        fn(fake_self, {"bracket_type": "round_left"})
        assert item.bracket_type == "round_left"
        assert fake_self.bracket_combo.currentText() == "round_left"

    def test_head_style_updates_combo_only(self):
        _ns, fn = _extract("set_ui_values")
        fake_self = FakeDialogSelf(item=FakeItemPlain())
        fake_self.head_style_combo = FakeCombo("chevron")
        fn(fake_self, {"head_style": "harpoon"})
        assert fake_self.head_style_combo.currentText() == "harpoon"

    def test_head_side_updates_item_and_combo(self):
        _ns, fn = _extract("set_ui_values")

        class Item:
            head_side = -1

        item = Item()
        fake_self = FakeDialogSelf(item=item)
        fake_self.head_side_combo = FakeCombo("Up")
        fn(fake_self, {"head_side": 1})
        assert item.head_side == 1
        assert fake_self.head_side_combo.currentText() == "Down"

    def test_size_updates_item_and_spin(self):
        _ns, fn = _extract("set_ui_values")

        class Item:
            size = 10.0

        item = Item()
        fake_self = FakeDialogSelf(item=item)
        fake_self.item_size_spin = FakeSpin(10.0)
        fn(fake_self, {"size": 40.0})
        assert item.size == 40.0
        assert fake_self.item_size_spin.value() == 40.0

    def test_rect_width_height_update_spins(self):
        _ns, fn = _extract("set_ui_values")
        fake_self = FakeDialogSelf(item=FakeItemPlain())
        fake_self.rect_w_spin = FakeSpin(1.0)
        fake_self.rect_h_spin = FakeSpin(1.0)
        fn(fake_self, {"rect_width": 99.0, "rect_height": 77.0})
        assert fake_self.rect_w_spin.value() == 99.0
        assert fake_self.rect_h_spin.value() == 77.0

    def test_all_remaining_spin_widgets_updated(self):
        """Covers the width/head_size/head_angle/concavity/curvature/
        double_arrow_offset/cross_size spin-box branches of set_ui_values in
        one pass (each guarded by `getattr(self, "..._spin", None) is not
        None`, independent of the matching item.<attr> hasattr checks)."""
        _ns, fn = _extract("set_ui_values")

        class Item:
            head_concavity = 0.1
            curvature = 0.1
            double_arrow_offset = 1.0
            cross_size = 1.0

        fake_self = FakeDialogSelf(item=Item())
        fake_self.width_spin = FakeSpin(1)
        fake_self.head_size_spin = FakeSpin(1.0)
        fake_self.head_angle_spin = FakeSpin(1.0)
        fake_self.concavity_spin = FakeSpin(0.1)
        fake_self.curvature_spin = FakeSpin(0.1)
        fake_self.spacing_spin = FakeSpin(1.0)
        fake_self.cross_size_spin = FakeSpin(1.0)
        fn(
            fake_self,
            {
                "width": 5,
                "head_size": 30.0,
                "head_angle": 40.0,
                "head_concavity": 0.9,
                "curvature": 0.8,
                "double_arrow_offset": 12.0,
                "cross_size": 20.0,
            },
        )
        assert fake_self.width_spin.value() == 5
        assert fake_self.head_size_spin.value() == 30.0
        assert fake_self.head_angle_spin.value() == 40.0
        assert fake_self.concavity_spin.value() == 0.9
        assert fake_self.curvature_spin.value() == 0.8
        assert fake_self.spacing_spin.value() == 12.0
        assert fake_self.cross_size_spin.value() == 20.0

    def test_calls_update_ui_state(self):
        _ns, fn = _extract("set_ui_values")
        fake_self = FakeDialogSelf(item=FakeItemPlain())
        fn(fake_self, {})
        assert fake_self.update_ui_state.called


# ---------------------------------------------------------------------------
# load_templates / get_factory_defaults / update_combo
# ---------------------------------------------------------------------------


class TestLoadTemplates:
    def test_missing_file_uses_factory_defaults(self, tmp_path):
        ns, fn = _extract("load_templates")
        ns["SETTINGS_FILE"] = str(tmp_path / "does_not_exist.json")
        fake_self = FakeDialogSelf(item_kind="arrow")
        _bind_real_get_factory_defaults(fake_self)
        fake_self.update_combo = MagicMock()
        fn(fake_self)
        assert fake_self.templates["Default"]["head_style"] == "chevron"
        assert fake_self.update_combo.called

    def test_existing_default_key_promoted_to_default(self, tmp_path):
        ns, fn = _extract("load_templates")
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"templates": {"Default_arrow": {"color": "#123456"}}})
        )
        ns["SETTINGS_FILE"] = str(path)
        fake_self = FakeDialogSelf(item_kind="arrow")
        _bind_real_get_factory_defaults(fake_self)
        fake_self.update_combo = MagicMock()
        fn(fake_self)
        assert fake_self.templates["Default"]["color"] == "#123456"
        assert "Default_arrow" not in fake_self.templates

    def test_corrupt_json_is_silenced(self, tmp_path):
        ns, fn = _extract("load_templates")
        path = tmp_path / "settings.json"
        path.write_text("{not valid json")
        ns["SETTINGS_FILE"] = str(path)
        fake_self = FakeDialogSelf(item_kind="general")
        _bind_real_get_factory_defaults(fake_self)
        fake_self.update_combo = MagicMock()
        fn(fake_self)  # must not raise
        assert fake_self.templates["Default"]["color"] == "#000000"


class TestGetFactoryDefaults:
    def _defaults(self, item_kind):
        _ns, fn = _extract("get_factory_defaults")
        fake_self = FakeDialogSelf(item_kind=item_kind)
        return fn(fake_self)

    def test_general_kind(self):
        d = self._defaults("general")
        assert d == {"color": "#000000", "width": 3}

    def test_arrow_kind(self):
        d = self._defaults("arrow")
        assert d["head_style"] == "chevron"
        assert d["width"] == 2
        assert "curvature" not in d
        assert "cross_size" not in d

    def test_curved_arrow_kind(self):
        # get_factory_defaults only sets "curvature" when item_kind matches
        # BOTH the "arrow" and "curved" substrings (nested `if` in source).
        d = self._defaults("curved_arrow")
        assert d["curvature"] == 0.4

    def test_no_reaction_arrow_kind(self):
        d = self._defaults("arrow_no")
        assert d["cross_size"] == 15.0

    def test_bracket_kind(self):
        d = self._defaults("bracket")
        assert d["bracket_type"] == "square"
        assert d["width"] == 2


class TestUpdateCombo:
    def test_keeps_current_text_if_present(self):
        _ns, fn = _extract("update_combo")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Custom1")
        fake_self.templates = {"Default": {}, "Custom1": {}, "Default_arrow": {}}
        fn(fake_self)
        assert fake_self.tmpl_combo.currentText() == "Custom1"
        assert "Default_arrow" not in fake_self.tmpl_combo._items

    def test_falls_back_to_default(self):
        _ns, fn = _extract("update_combo")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Missing")
        fake_self.templates = {"Default": {"color": "#000"}}
        fn(fake_self)
        assert fake_self.tmpl_combo.currentText() == "Default"

    def test_no_default_and_no_match_leaves_combo_empty_text(self):
        _ns, fn = _extract("update_combo")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Missing")
        fake_self.templates = {}
        fn(fake_self)
        # Neither branch matched -- currentText stays whatever clear() left it.
        assert fake_self.tmpl_combo.currentText() in ("", "Missing")


class TestOnTemplateSelected:
    def test_is_a_no_op(self):
        _ns, fn = _extract("on_template_selected")
        fake_self = FakeDialogSelf()
        assert fn(fake_self, "anything") is None


# ---------------------------------------------------------------------------
# apply_template_to_ui / save_template / delete_template / save_to_file
# ---------------------------------------------------------------------------


class TestApplyTemplateToUi:
    def test_applies_when_present(self):
        _ns, fn = _extract("apply_template_to_ui")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Default")
        fake_self.templates = {"Default": {"color": "#222222"}}
        fake_self.set_ui_values = MagicMock()
        fn(fake_self)
        fake_self.set_ui_values.assert_called_once_with({"color": "#222222"})

    def test_no_op_when_missing(self):
        _ns, fn = _extract("apply_template_to_ui")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Ghost")
        fake_self.templates = {}
        fake_self.set_ui_values = MagicMock()
        fn(fake_self)
        assert not fake_self.set_ui_values.called


class TestSaveTemplate:
    def test_saves_when_ok_and_named(self, tmp_path):
        ns, fn = _extract("save_template")
        qtw.QInputDialog.getText = MagicMock(return_value=("MyTemplate", True))
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Default")
        fake_self.templates = {}
        fake_self.get_current_values = MagicMock(return_value={"color": "#abcabc"})
        fake_self.save_to_file = MagicMock()
        fake_self.update_combo = MagicMock()
        fn(fake_self)
        assert fake_self.templates["MyTemplate"] == {"color": "#abcabc"}
        assert fake_self.save_to_file.called
        assert fake_self.update_combo.called
        assert fake_self.tmpl_combo.currentText() == "MyTemplate"

    def test_cancelled_dialog_is_a_no_op(self):
        ns, fn = _extract("save_template")
        qtw.QInputDialog.getText = MagicMock(return_value=("Ignored", False))
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Default")
        fake_self.templates = {}
        fake_self.save_to_file = MagicMock()
        fn(fake_self)
        assert fake_self.templates == {}
        assert not fake_self.save_to_file.called

    def test_empty_name_is_a_no_op(self):
        ns, fn = _extract("save_template")
        qtw.QInputDialog.getText = MagicMock(return_value=("", True))
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Default")
        fake_self.templates = {}
        fake_self.save_to_file = MagicMock()
        fn(fake_self)
        assert not fake_self.save_to_file.called


class TestDeleteTemplate:
    def test_default_reset_confirmed(self):
        ns, fn = _extract("delete_template")
        ns["QMessageBox"].question = MagicMock(
            return_value=ns["QMessageBox"].StandardButton.Yes
        )
        fake_self = FakeDialogSelf(item_kind="general")
        _bind_real_get_factory_defaults(fake_self)
        fake_self.tmpl_combo = FakeCombo("Default")
        fake_self.templates = {"Default": {"color": "#999999"}}
        fake_self.save_to_file = MagicMock()
        fake_self.apply_template_to_ui = MagicMock()
        fn(fake_self)
        assert fake_self.templates["Default"] == {"color": "#000000", "width": 3}
        assert fake_self.save_to_file.called
        assert fake_self.apply_template_to_ui.called

    def test_default_reset_declined(self):
        ns, fn = _extract("delete_template")
        ns["QMessageBox"].question = MagicMock(
            return_value=ns["QMessageBox"].StandardButton.No
        )
        fake_self = FakeDialogSelf(item_kind="general")
        fake_self.tmpl_combo = FakeCombo("Default")
        original = {"color": "#999999"}
        fake_self.templates = {"Default": original}
        fake_self.save_to_file = MagicMock()
        fn(fake_self)
        assert fake_self.templates["Default"] is original
        assert not fake_self.save_to_file.called

    def test_deletes_custom_template(self):
        _ns, fn = _extract("delete_template")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Custom1")
        fake_self.templates = {"Custom1": {}, "Default": {}}
        fake_self.save_to_file = MagicMock()
        fake_self.update_combo = MagicMock()
        fn(fake_self)
        assert "Custom1" not in fake_self.templates
        assert fake_self.save_to_file.called
        assert fake_self.update_combo.called

    def test_missing_custom_template_is_a_no_op(self):
        _ns, fn = _extract("delete_template")
        fake_self = FakeDialogSelf()
        fake_self.tmpl_combo = FakeCombo("Ghost")
        fake_self.templates = {}
        fake_self.save_to_file = MagicMock()
        fn(fake_self)
        assert not fake_self.save_to_file.called


class TestSaveToFile:
    def test_writes_templates_mapping_default_back_to_kind_key(self, tmp_path):
        ns, fn = _extract("save_to_file")
        path = tmp_path / "settings.json"
        ns["SETTINGS_FILE"] = str(path)
        fake_self = FakeDialogSelf(item_kind="arrow")
        fake_self.default_key = "Default_arrow"
        fake_self.templates = {"Default": {"color": "#111111"}, "Custom1": {"a": 1}}
        fn(fake_self)
        data = json.loads(path.read_text())
        assert data["templates"]["Default_arrow"] == {"color": "#111111"}
        assert data["templates"]["Custom1"] == {"a": 1}

    def test_write_failure_is_silenced(self, tmp_path):
        ns, fn = _extract("save_to_file")
        # Point at a path inside a non-existent directory so open() raises OSError.
        ns["SETTINGS_FILE"] = str(tmp_path / "missing_dir" / "settings.json")
        fake_self = FakeDialogSelf(item_kind="general")
        fake_self.default_key = "Default_general"
        fake_self.templates = {"Default": {}}
        fn(fake_self)  # must not raise


class TestGetSettings:
    def test_replaces_color_with_qcolor_object(self):
        _ns, fn = _extract("get_settings")
        fake_self = FakeDialogSelf()
        fake_self.current_color = QColor("#456789")
        fake_self.get_current_values = MagicMock(return_value={"color": "#456789"})
        vals = fn(fake_self)
        assert vals["color"] is fake_self.current_color

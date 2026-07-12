"""
tests/test_settings_dialog_bugfixes.py -- regression tests for
AdvancedSettingsDialog.set_ui_values().

AdvancedSettingsDialog subclasses QDialog, which is stubbed as a bare
MagicMock() *instance* in tests/conftest.py -- instantiating the real class
therefore returns an opaque Mock and never runs our Python code. We extract
the target method's source with `ast` and `exec` it as a free function bound
to a lightweight fake "self", per the project's established technique for
testing methods on Qt-derived classes in the headless test harness.

Bug fixed: set_ui_values() mutated self.item.head_concavity / .curvature /
.double_arrow_offset directly when applying a loaded template, but never
updated the corresponding spin box widgets (concavity_spin, curvature_spin,
spacing_spin). Since get_current_values() (used by both "Apply" and "OK")
reads those spin boxes -- not the item -- the stale widget value was written
straight back over the freshly-loaded item value the moment the user clicked
Apply/OK, silently discarding the loaded template value.
"""

import ast
import inspect
from unittest.mock import MagicMock

import reaction_sketcher.settings_dialog as settings_dialog_module


def _extract_method_as_fn(cls_source, method_name):
    """Extract a method's source from a class definition and exec it as a
    standalone function so it can be called with a lightweight fake `self`.
    """
    tree = ast.parse(cls_source)
    class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method_node = next(
        n
        for n in class_node.body
        if isinstance(n, ast.FunctionDef) and n.name == method_name
    )
    method_src = ast.get_source_segment(cls_source, method_node)
    namespace = {}
    exec(compile(ast.parse(method_src), "<extracted>", "exec"), namespace)
    return namespace[method_name]


_MODULE_SOURCE = inspect.getsource(settings_dialog_module)
_SET_UI_VALUES = _extract_method_as_fn(_MODULE_SOURCE, "set_ui_values")


class FakeSpin:
    """Real (non-Mock) stand-in for a QDoubleSpinBox: hasattr must behave."""

    def __init__(self, initial=0.0):
        self._value = initial
        self.set_calls = []

    def setValue(self, v):
        self._value = v
        self.set_calls.append(v)

    def value(self):
        return self._value


class FakeCombo:
    def __init__(self, text=""):
        self._text = text

    def setCurrentText(self, t):
        self._text = t

    def currentText(self):
        return self._text


class FakeCurvedArrowItem:
    """Minimal real fake mimicking ReactionCurvedArrowItem's relevant attrs."""

    def __init__(self):
        self.head_concavity = 0.5
        self.curvature = 0.4
        self.double_arrow_offset = 10.0
        self.head_style = "chevron"


class FakeSelf:
    """Fake `self` for AdvancedSettingsDialog.set_ui_values, with only the
    attributes the extracted method touches.
    """

    def __init__(self, item):
        self.item = item
        self.concavity_spin = FakeSpin(0.5)
        self.curvature_spin = FakeSpin(0.4)
        self.spacing_spin = FakeSpin(10.0)
        self.head_style_combo = FakeCombo("chevron")
        self.update_ui_state = MagicMock()


class TestSetUiValuesSyncsSpinBoxes:
    def test_head_concavity_updates_spin_box(self):
        fake_self = FakeSelf(FakeCurvedArrowItem())
        _SET_UI_VALUES(fake_self, {"head_concavity": 0.9})
        assert fake_self.item.head_concavity == 0.9
        assert fake_self.concavity_spin.value() == 0.9
        assert fake_self.concavity_spin.set_calls == [0.9]

    def test_curvature_updates_spin_box(self):
        fake_self = FakeSelf(FakeCurvedArrowItem())
        _SET_UI_VALUES(fake_self, {"curvature": 1.2})
        assert fake_self.item.curvature == 1.2
        assert fake_self.curvature_spin.value() == 1.2
        assert fake_self.curvature_spin.set_calls == [1.2]

    def test_double_arrow_offset_updates_spin_box(self):
        fake_self = FakeSelf(FakeCurvedArrowItem())
        _SET_UI_VALUES(fake_self, {"double_arrow_offset": 15.5})
        assert fake_self.item.double_arrow_offset == 15.5
        assert fake_self.spacing_spin.value() == 15.5
        assert fake_self.spacing_spin.set_calls == [15.5]

    def test_apply_after_template_load_no_longer_reverts_value(self):
        """End-to-end regression: without the fix, get_current_values() (as
        called by Apply/OK) would read the stale spin box and clobber the
        item value that set_ui_values() had just set from the template.
        """
        fake_self = FakeSelf(FakeCurvedArrowItem())
        _SET_UI_VALUES(fake_self, {"head_concavity": 0.85, "curvature": 0.9})

        # Simulate what get_current_values() would read for these two keys.
        vals = {
            "head_concavity": fake_self.concavity_spin.value(),
            "curvature": fake_self.curvature_spin.value(),
        }
        assert vals["head_concavity"] == 0.85
        assert vals["curvature"] == 0.9

"""Reverting a patch on an inherited Qt method must delete it, not re-assign it.

MainWindow does not define closeEvent -- it inherits QMainWindow's. Writing that
sip method back onto the subclass left a non-descriptor class attribute, so
`window.closeEvent` no longer bound self and Qt passed the QCloseEvent as `self`:
    TypeError: closeEvent(self, a0: QCloseEvent|None):
        first argument of unbound method must have type 'QMainWindow'
That fired at quit once the plugin had been enabled and disabled.
"""

from reaction_sketcher.patcher import _patch, _revert


def test_inherited_method_is_removed_on_revert():
    class Base:
        def handle(self, event):
            return ("base", event)

    class Sub(Base):
        """No handle() of its own, like the host MainWindow and closeEvent."""

    originals = {}
    calls = []

    def patched(self, event):
        calls.append(self)
        return ("patched", event)

    _patch(originals, Sub, "handle", patched)
    window = Sub()
    assert window.handle("event") == ("patched", "event")
    assert calls == [window]

    _revert(originals)
    # The regression: the inherited method was written onto Sub itself.
    assert "handle" not in Sub.__dict__
    assert Sub().handle("event") == ("base", "event")


def test_python_method_is_restored_on_revert():
    class Base:
        def greet(self):
            return "base"

    class Sub(Base):
        def greet(self):
            return "sub"

    originals = {}
    _patch(originals, Sub, "greet", lambda self: "patched")
    assert Sub().greet() == "patched"

    _revert(originals)
    assert Sub().greet() == "sub"
    assert Base().greet() == "base"


def test_added_method_is_deleted_on_revert():
    class Plain:
        pass

    originals = {}
    _patch(originals, Plain, "brand_new", lambda self: "added")
    assert Plain().brand_new() == "added"

    _revert(originals)
    assert not hasattr(Plain, "brand_new")

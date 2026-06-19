"""
tests/test_version.py -- plugin metadata sanity checks (no Qt required).
"""

import re
import sys
import os
import importlib.util

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_init_without_qt():
    """Load reaction_sketcher/__init__.py with sub-modules stubbed."""
    from unittest.mock import MagicMock

    for name in (
        "reaction_sketcher.mode_manager",
        "reaction_sketcher.interaction",
        "reaction_sketcher.items",
        "reaction_sketcher.utils",
    ):
        sys.modules.setdefault(name, MagicMock())

    # Register under the real package name so relative imports resolve.
    pkg = sys.modules.get("reaction_sketcher") or importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            "reaction_sketcher",
            os.path.join(_REPO_ROOT, "reaction_sketcher", "__init__.py"),
        )
    )
    pkg.__package__ = "reaction_sketcher"
    sys.modules["reaction_sketcher"] = pkg

    spec = importlib.util.spec_from_file_location(
        "reaction_sketcher",
        os.path.join(_REPO_ROOT, "reaction_sketcher", "__init__.py"),
    )
    spec.loader.exec_module(pkg)
    return pkg


_init = _load_init_without_qt()


class TestPluginMetadata:
    def test_name(self):
        assert _init.PLUGIN_NAME == "Reaction Sketcher"

    def test_version_format(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", _init.PLUGIN_VERSION), (
            f"PLUGIN_VERSION {_init.PLUGIN_VERSION!r} does not match X.Y.Z"
        )

    def test_author_nonempty(self):
        assert _init.PLUGIN_AUTHOR.strip()

    def test_description_nonempty(self):
        assert _init.PLUGIN_DESCRIPTION.strip()

    def test_reaction_item_types_is_tuple(self):
        assert isinstance(_init.REACTION_ITEM_TYPES, tuple)
        assert len(_init.REACTION_ITEM_TYPES) > 0

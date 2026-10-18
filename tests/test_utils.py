"""
tests/test_utils.py -- unit tests for reaction_sketcher/utils.py.
"""

from unittest.mock import MagicMock, patch
import pytest

from reaction_sketcher.utils import qt_is_deleted, get_main_window


class TestSipIsdeletedSafe:
    def test_none_returns_true(self):
        assert qt_is_deleted(None) is True

    def test_mock_object_does_not_raise(self):
        obj = MagicMock()
        # Should return False (can't confirm deleted) without raising
        result = qt_is_deleted(obj)
        assert isinstance(result, bool)

    @pytest.mark.parametrize("valid", [True, False])
    def test_shiboken_validity(self, valid):
        """Validity is inverted for live and deleted Qt wrappers."""
        fake_shiboken = MagicMock()
        fake_shiboken.isValid.return_value = valid
        obj = MagicMock()
        with patch.dict("sys.modules", {"shiboken6": fake_shiboken}):
            assert qt_is_deleted(obj) is (not valid)
        fake_shiboken.isValid.assert_called_once_with(obj)


class TestGetMainWindow:
    def test_none_scene_returns_none(self):
        assert get_main_window(None) is None

    def test_scene_with_no_views_returns_none(self):
        scene = MagicMock()
        scene.views.return_value = []
        assert get_main_window(scene) is None

    def test_scene_with_view_returns_window(self):
        fake_window = MagicMock()
        fake_view = MagicMock()
        fake_view.window.return_value = fake_window
        scene = MagicMock()
        scene.views.return_value = [fake_view]
        assert get_main_window(scene) is fake_window

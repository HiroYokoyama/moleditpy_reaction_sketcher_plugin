# Reaction Sketcher — Test Suite

758 tests across 16 files. All run headlessly — no Qt installation or display
required. Qt dependencies are stubbed in files that need them using standard mocks and lightweight test double implementations.

---

## Running the tests

```bash
# Full suite
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_mode_manager_coverage.py -v

# Single test
python -m pytest tests/ -k "test_loads_arrow"
```

---

## Test files overview

| File | Tests | Area |
|---|---|---|
| `test_api.py` | 1 | API boundary compliance & isolation checks |
| `test_data_sync.py` | 12 | Data model synchronization & regression tests (moved/cloned items) |
| `test_init_coverage.py` | 22 | Plugin initialization, menu callbacks, and lifecycle hooks (`__init__.py`) |
| `test_interaction_coverage.py` | 79 | User interactions, mouse events, key events, and tool dispatching (`interaction.py`) |
| `test_items_coverage.py` | 156 | Graphical item rendering, shapes, handles, and context menus (`items.py`) |
| `test_items_json.py` | 33 | JSON serialization round-trips for all reaction item types |
| `test_load_handler_core.py` | 24 | Scene item deserialization from JSON data (`utils.py`) |
| `test_mode_manager_coverage.py` | 190 | Reaction mode state management, tool selection, action handling (`mode_manager.py`) |
| `test_patcher_coverage.py` | 127 | Core & interaction patching on MoleditPy main window (`patcher.py`) |
| `test_plugin_integration.py` | 24 | Plugin lifecycle and integration tests (`__init__.py`) |
| `test_save_handler.py` | 20 | Save, load, and reset handlers, metadata persistence (`__init__.py`) |
| `test_settings_dialog_bugfixes.py` | 4 | Settings dialog bug fixes and edge-case regressions (`settings_dialog.py`) |
| `test_settings_dialog_coverage.py` | 51 | Settings UI dialog logic, configuration reading/writing (`settings_dialog.py`) |
| `test_shortcuts_safety.py` | 4 | Shortcut preservation and restoration safety on main window |
| `test_utils.py` | 6 | Utility functions (`sip_isdeleted_safe`, `get_main_window`) |
| `test_version.py` | 5 | Plugin metadata & semver checks |

---

## Test files — detailed

### `test_api.py` — API Boundary (1 test)
Validates compliance with allowed API boundaries and prevents illegal internal access.

### `test_data_sync.py` — Data Model Sync & Regressions (12 tests)
Ensures moved or cloned items/atoms accurately write back into the molecular data model (preventing stale atom positions or missing charge/radical data after undo/redo/save).

### `test_init_coverage.py` — Initialization Coverage (22 tests)
Exercises plugin startup, action registration, menu callbacks, and mode initialization in `reaction_sketcher/__init__.py`.

### `test_interaction_coverage.py` — Interaction Handler (79 tests)
Tests tool dispatching, mouse press/move/release events, key presses, and double clicks in `reaction_sketcher/interaction.py`.

### `test_items_coverage.py` — Item Rendering & Handles (156 tests)
Broad coverage for `reaction_sketcher/items.py`. Tests shape creation, bounding rect calculation, handle dragging (`on_handle_moved`), context menus, rotation, and custom painting.

### `test_items_json.py` — JSON Serialization (33 tests)
Verifies that every reaction item type serializes to a JSON dictionary with expected schema tags and geometric properties.

### `test_load_handler_core.py` — Deserialization (24 tests)
Tests `load_reaction_items_core()` for reconstructing scene items from JSON data.

### `test_mode_manager_coverage.py` — Mode Manager (190 tests)
Comprehensive coverage for `reaction_sketcher/mode_manager.py`, exercising mode toggles, tool state transitions, color palettes, and UI action triggers.

### `test_patcher_coverage.py` — Main Window Patcher (127 tests)
Tests patch application and teardown (`patcher.py`) against mock host main window components.

### `test_plugin_integration.py` — Integration (24 tests)
Integration tests validating the plugin lifecycle, handler hookups, and cross-module interactions.

### `test_save_handler.py` — Save/Load/Reset Handlers (20 tests)
Verifies state save dict structure, load restoration, and reset cleanup routines.

### `test_settings_dialog_bugfixes.py` — Settings Bugfixes (4 tests)
Regression tests covering specific edge cases and bugfixes in `settings_dialog.py`.

### `test_settings_dialog_coverage.py` — Settings Dialog (51 tests)
Coverage suite for reading, updating, and applying settings configuration options via the dialog.

### `test_shortcuts_safety.py` — Shortcut Safety (4 tests)
Ensures host keyboard shortcuts are safely backed up and restored when entering or exiting reaction mode.

### `test_utils.py` — Utility Functions (6 tests)
Unit tests for `reaction_sketcher/utils.py`, including `sip_isdeleted_safe` and `get_main_window`.

### `test_version.py` — Plugin Metadata (5 tests)
Checks that `PLUGIN_NAME`, `PLUGIN_VERSION`, `PLUGIN_AUTHOR`, `PLUGIN_DESCRIPTION`, and `REACTION_ITEM_TYPES` are present and valid.

## CI

Automated testing is configured via GitHub Actions in `.github/workflows/tests.yml`. Tests run on push and pull requests across Python versions 3.11, 3.12, and 3.13 with `pytest` and coverage reporting (`pytest-cov`).


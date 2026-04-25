# Reaction Sketcher — Test Suite

85 tests across 5 files. All run headlessly — no Qt installation or display
required. Qt dependencies are stubbed in files that need them.

---

## Running the tests

```bash
# Full suite
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_items_json.py -v

# Single test
python -m pytest tests/ -k "test_loads_arrow"
```

---

## Test files

| File | Tests | Area |
|---|---|---|
| `test_items_json.py` | 31 | JSON serialisation of all reaction item types |
| `test_load_handler_core.py` | 23 | Load handler — deserialising items from JSON |
| `test_save_handler.py` | 21 | `initialize()` contract, save/load/reset handlers |
| `test_utils.py` | 5 | Utility functions (`sip_isdeleted_safe`, `get_main_window`) |
| `test_version.py` | 5 | Plugin metadata constants |

---

## Test files — detailed

### `test_items_json.py` — JSON serialisation (31 tests)

Verifies that every reaction item type serialises to a JSON dict with the
correct shape. No deserialization — pure output-structure checks.

| Class | Item type tested |
|---|---|
| `TestReactionArrowItemJson` | Standard reaction arrow: `type` tag, `x1/y1/x2/y2` keys, `color` |
| `TestReactionResonanceArrowJson` | Resonance arrow: `type` tag |
| `TestReactionEquilibriumArrowJson` | Equilibrium arrow: `type` tag |
| `TestReactionRetroArrowJson` | Retrosynthetic arrow: `type` tag |
| `TestReactionNoArrowJson` | No-arrow (bond break): `type` tag |
| `TestReactionDashedArrowJson` | Dashed arrow: `type` tag, position keys |
| `TestReactionCurvedArrowJson` | Curved arrow (double/fishhook): `type` tag, `control_point` key |
| `TestReactionPlusItemJson` | Plus symbol: `type`, `x/y`, size reflected in JSON |
| `TestReactionMinusItemJson` | Minus symbol: `type`, `x/y` |
| `TestReactionBracketItemJson` | Bracket: `type`, geometry keys |
| `TestReactionCircleItemJson` | Circle: `type`, geometry keys |
| `TestReactionLineItemJson` | Line: `type`, position keys |
| `TestReactionCurvedLineItemJson` | Curved line: `type`, `control_point` |
| `TestReactionFreehandItemJson` | Freehand: `type`, empty/set points reflected |
| `TestReactionTextItemJson` | Text: `type`, text content preserved, position |

---

### `test_load_handler_core.py` — Load handler deserialisation (23 tests)

Tests `load_reaction_items_core()` which reconstructs scene items from
serialised JSON dicts.

| Class | What is tested |
|---|---|
| `TestLoadHandlerCoreEmpty` | Empty list and `None` add nothing to the scene |
| `TestLoadHandlerCoreArrows` | All arrow types loaded: standard, resonance, equilibrium, retro, no-arrow, dashed, multiple arrows |
| `TestLoadHandlerCoreSymbols` | Plus and minus loaded; plus with custom color/size |
| `TestLoadHandlerCoreShapes` | Bracket, circle, line, curved line, freehand loaded |
| `TestLoadHandlerCoreText` | Plain text and HTML text loaded |
| `TestLoadHandlerCoreRobustness` | Unknown type skipped gracefully; mixed valid+unknown; item with rotation |

---

### `test_save_handler.py` — Initialize and persistence (21 tests)

| Class | What is tested |
|---|---|
| `TestInitialize` | `initialize(context)` calls `add_menu_action`, `register_save_handler`, `register_load_handler`, `register_reset_handler`, `show_status_message`; correct menu path |
| `TestSaveHandler` | Save handler returns a dict; has keys `plugin_version`, `items`, `reaction_mode_active`, `auto_start_pref`, `rs_colors`, `groups` |
| `TestLoadHandler` | `None` / empty dict / list data do not raise; `auto_start_pref` restored from dict |
| `TestResetHandler` | Reset clears reaction items; safe on empty scene |

---

### `test_utils.py` — Utility functions (5 tests)

| Class | What is tested |
|---|---|
| `TestSipIsdeletedSafe` | `None` → `True`; mock object does not raise; PyQt6 sip path |
| `TestGetMainWindow` | `None` scene → `None`; scene with no views → `None`; scene with view → returns window |

---

### `test_version.py` — Plugin metadata (5 tests)

`PLUGIN_NAME`, `PLUGIN_VERSION` (semver format), `PLUGIN_AUTHOR`,
`PLUGIN_DESCRIPTION` all present and non-empty. `REACTION_ITEM_TYPES` is a
tuple.

---

## CI

No CI workflow currently configured for this repo.

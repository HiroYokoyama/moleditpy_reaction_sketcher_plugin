# Reaction Sketcher Plugin for MoleditPy

![Reaction Sketcher](img/main.png)

A comprehensive chemical reaction sketching tool for MoleditPy, allowing users to draw reaction text, arrows, brackets, and annotations directly in the 2D workspace.

## Features

- **Reaction Arrows**: Standard, Equilibrium, Resonance, Retrosynthetic, Dashed, and "No Reaction" arrows.
- **Curved Arrows**: Electron pushing arrows (Double headed and Fish-hook/Single electron).
- **Annotations**: Text boxes, Plus (+), and Minus (-) signs.
- **Grouping**: Brackets (Square, Round, Curly) and Circles/Ellipses.
- **Customization**:
  - **Head Styles**: Triangle, Chevron, Harpoon, Barb.
  - **Double Arrow Spacing**: Adjustable spacing for equilibrium arrows.
  - **Properties**: Configurable line widths, colors, head sizes, and curvature.
  - **Templates**: Save and load custom element styles.
- **Undo/Redo Support**: Fully integrated with the main application's undo stack.
- **Smart Interaction**:
  - **Auto-Select**: Automatically switches to Select mode after placing an item (except for continuous tools).
  - **Right-Click**: Delete item.
  - **Shift+Right-Click**: Open Context Menu (Styles, Properties).
  - **Clickable Heads**: Easy selection of curved arrows by clicking their arrowheads.
  - **Angle snapping**: Every 15 degrees for straight arrows (hold Alt to bypass).
  - **Double-click**: Edit Text items.

## Installation

1. Copy the `reaction_sketcher` folder into the `plugins` directory of your MoleditPy installation.
2. Restart MoleditPy.
3. The plugin will automatically load.

## Usage

### Activation
- Click the **Reaction Tool** icon (Flask) in the main toolbar.
- Or use the menu: `View -> Toolbars -> Reaction Tools`.

### Tools Overview
The side toolbar provides the following tools:
- **Select**: Move and select items.
- **Arrows**:
  - **Standard**: Basic reaction arrow.
  - **Equilibrium**: Reversible reaction arrow.
  - **Resonance**: Double-headed resonance arrow.
  - **Retro**: Retrosynthetic arrow (thick open arrow).
  - **No Rxn**: Arrow with a cross or slash indicating no reaction.
  - **Dashed**: Dashed arrow for theoretical steps.
- **Curved Arrows**:
  - **Double**: Two-electron transfer (curved).
  - **Fish-hook**: Single-electron radical transfer.
- **Shapes**:
  - **Bracket**: Enclose structures. (Context menu to change style: Square, Round, Curly).
  - **Circle**: Highlight areas.
- **Annotations**:
  - **Plus/Minus**: Charge or addition symbols.
  - **Text**: Add labels or conditions.

### Advanced Customization
**Basic Actions:**
- **Right-Click**: Delete the item under cursor.
- **Shift + Right-Click**: Open **Context Menu** to change Color, Line Width, Head Style, or open **Properties**.

**Properties Dialog:**
- Accessible via Context Menu -> Properties.
- Adjust **Color**, **Line Width**, **Head Size**, **Head Angle**, **Curvature**.
- **Double Arrow Spacing**: Adjust spacing for Equilibrium arrows.
- **Templates**: Save your settings as "Default" to apply them to future items.

### Tips
- **3D Conversion**: The "Convert to 3D" button is disabled while in Reaction Mode to prevent accidental conversion of annotations. Exit Reaction Mode to convert your molecules.
- **Deleting**: Select items and press `Delete` or `Backspace`. Simple Right-click also deletes.
- **Curve Control**: Curved arrows have control points (orange handles) to adjust their arc.

## License
This project is licensed under the GNU General Public License v3.0 (GPLv3).

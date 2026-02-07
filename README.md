# Reaction Sketcher Plugin for MoleditPy

A comprehensive chemical reaction sketching tool for MoleditPy, allowing users to draw reaction text, arrows, brackets, and annotations directly in the 2D workspace.

## Features

- **Reaction Arrows**: Standard, Equilibrium, Resonance, Retrosynthetic, and "No Reaction" arrows.
- **Curved Arrows**: Electron pushing arrows (Double headed and Fish-hook/Single electron).
- **Annotations**: Text boxes, Plus (+), and Minus (-) signs.
- **Grouping**: Brackets (Square, Round, Curly) and Circles/Ellipses.
- **Customization**:
  - Adjustable arrow heads (Triangle, Chevron, Harpoon, Barb).
  - Configurable line widths, colors, and head sizes.
  - Interactive handles for adjusting arrow length, angle, and head shape (concavity).
- **Undo/Redo Support**: Fully integrated with the main application's undo stack.
- **Smart Interaction**:
  - Angle snapping (every 15 degrees) for straight arrows (hold Alt to bypass).
  - Context menus for quick style changes.
  - Double-click Text items to edit.

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
- **Curved Arrows**:
  - **Double**: Two-electron transfer.
  - **Fish-hook**: Single-electron radical transfer.
- **Shapes**:
  - **Bracket**: Enclose structures. (Context menu to change style: Square, Round, Curly).
  - **Circle**: Highlight areas.
- **Annotations**:
  - **Plus/Minus**: Charge or addition symbols.
  - **Text**: Add labels or conditions.

### Advanced Customization
Right-click on any selected item to access the **Context Menu**:
- Change **Color**, **Line Width**, **Head Style**.
- **Properties...**: Opens the Advanced Settings dialog.

### Default Settings
You can save your preferred styles as defaults:
1. Select an item (e.g., an Arrow).
2. Right-click and choose **Properties...** (or click "More..." in the toolbar).
3. Adjust settings (Color, Head Style, Size, etc.).
4. Click **"Save/Update"** and name the template **"Default"**.
5. Future items of this type will automatically use these settings.

### Tips
- **3D Conversion**: The "Convert to 3D" button is disabled while in Reaction Mode to prevent accidental conversion of annotations. Exit Reaction Mode to convert your molecules.
- **Deleting**: Select items and press `Delete` or `Backspace`. Right-click deletion is also supported.
- **Curve Control**: Curved arrows have control points (orange handles) to adjust their arc.

## License
This project is licensed under the GNU General Public License v3.0 (GPLv3).

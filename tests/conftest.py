"""
tests/conftest.py -- headless test setup for Reaction Sketcher.

PyQt6 is stubbed with pure-Python stand-ins so the plugin code can be
imported and exercised without a display or installed Qt binaries.
"""

import math
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Minimal Qt stand-ins
# ---------------------------------------------------------------------------


class _QPointF:
    def __init__(self, x=0.0, y=0.0):
        self._x = float(x)
        self._y = float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def __sub__(self, o):
        return _QPointF(self._x - o._x, self._y - o._y)

    def __add__(self, o):
        return _QPointF(self._x + o._x, self._y + o._y)

    def __mul__(self, factor):
        return _QPointF(self._x * factor, self._y * factor)

    __rmul__ = __mul__

    def manhattanLength(self):
        return abs(self._x) + abs(self._y)

    def toPoint(self):
        return self

    def setX(self, x):
        self._x = float(x)

    def setY(self, y):
        self._y = float(y)

    def __eq__(self, o):
        return isinstance(o, _QPointF) and self._x == o._x and self._y == o._y

    def __hash__(self):
        return hash((self._x, self._y))

    def __repr__(self):
        return f"QPointF({self._x}, {self._y})"


class _QRectF:
    def __init__(self, x=0, y=0, w=0, h=0):
        # Support QRectF(QPointF, QPointF) — top-left and bottom-right points
        if isinstance(x, _QPointF) and isinstance(y, _QPointF):
            self._x = x.x()
            self._y = x.y()
            self._w = y.x() - x.x()
            self._h = y.y() - x.y()
        elif isinstance(x, _QPointF):
            self._x = x.x()
            self._y = x.y()
            self._w = float(y)
            self._h = float(w)
        else:
            self._x = float(x)
            self._y = float(y)
            self._w = float(w)
            self._h = float(h)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h

    def left(self):
        return self._x

    def top(self):
        return self._y

    def right(self):
        return self._x + self._w

    def bottom(self):
        return self._y + self._h

    def topLeft(self):
        return _QPointF(self._x, self._y)

    def topRight(self):
        return _QPointF(self._x + self._w, self._y)

    def bottomLeft(self):
        return _QPointF(self._x, self._y + self._h)

    def bottomRight(self):
        return _QPointF(self._x + self._w, self._y + self._h)

    def center(self):
        return _QPointF(self._x + self._w / 2, self._y + self._h / 2)

    def normalized(self):
        x = min(self._x, self._x + self._w)
        y = min(self._y, self._y + self._h)
        return _QRectF(x, y, abs(self._w), abs(self._h))

    def contains(self, p):
        if isinstance(p, _QRectF):
            return (
                p.left() >= self.left()
                and p.right() <= self.right()
                and p.top() >= self.top()
                and p.bottom() <= self.bottom()
            )
        return (
            self.left() <= p.x() <= self.right()
            and self.top() <= p.y() <= self.bottom()
        )

    def isNull(self):
        return self._w == 0 and self._h == 0

    def isValid(self):
        return self._w > 0 and self._h > 0

    def isEmpty(self):
        return self._w <= 0 or self._h <= 0

    def adjusted(self, dx1, dy1, dx2, dy2):
        return _QRectF(
            self._x + dx1, self._y + dy1, self._w + dx2 - dx1, self._h + dy2 - dy1
        )

    def adjust(self, dx1, dy1, dx2, dy2):
        """In-place variant of adjusted() (real QRectF.adjust mutates self)."""
        self._x += dx1
        self._y += dy1
        self._w += dx2 - dx1
        self._h += dy2 - dy1

    def setWidth(self, w):
        self._w = float(w)

    def setHeight(self, h):
        self._h = float(h)

    def setX(self, x):
        self._x = float(x)

    def setY(self, y):
        self._y = float(y)

    def setBottomRight(self, p):
        self._w = p.x() - self._x
        self._h = p.y() - self._y

    def setTopLeft(self, p):
        self._x = p.x()
        self._y = p.y()

    def united(self, other):
        if self.isNull() or not self.isValid():
            return _QRectF(other._x, other._y, other._w, other._h)
        if other.isNull() or not other.isValid():
            return _QRectF(self._x, self._y, self._w, self._h)
        left = min(self.left(), other.left())
        top = min(self.top(), other.top())
        right = max(self.right(), other.right())
        bottom = max(self.bottom(), other.bottom())
        return _QRectF(left, top, right - left, bottom - top)

    def intersected(self, other):
        return _QRectF()

    def intersects(self, other):
        return False

    def __repr__(self):
        return f"QRectF({self._x}, {self._y}, {self._w}, {self._h})"


class _QColor:
    class NameFormat:
        HexRgb = 0
        HexArgb = 1

    def __init__(self, *args):
        self._name = args[0] if args and isinstance(args[0], str) else "#000000"

    def name(self, fmt=None):
        return self._name

    def isValid(self):
        return True

    def red(self):
        return 0

    def green(self):
        return 0

    def blue(self):
        return 0

    def redF(self):
        return 0.0

    def greenF(self):
        return 0.0

    def blueF(self):
        return 0.0

    def alpha(self):
        return 255

    def alphaF(self):
        return 1.0


class _GraphicsItemFlag:
    ItemIsMovable = 1
    ItemIsSelectable = 2
    ItemSendsGeometryChanges = 4
    ItemIsFocusable = 8
    ItemIsPanel = 16
    ItemClipsToShape = 32
    ItemClipsChildrenToShape = 64
    ItemIgnoresTransformations = 128
    ItemIgnoresParentOpacity = 256
    ItemDoesntPropagateOpacityToChildren = 512
    ItemStacksBehindParent = 1024
    ItemUsesExtendedStyleOption = 2048
    ItemHasNoContents = 4096
    ItemSendsScenePositionChanges = 8192
    ItemNegativeZStacksBehindParent = 16384
    ItemIsSelectable = 2
    ItemAcceptsInputMethod = 65536
    ItemContainsChildrenInShape = 131072


class _GraphicsItemChange:
    ItemPositionChange = 0
    ItemPositionHasChanged = 1
    ItemSelectedChange = 2
    ItemSelectedHasChanged = 3
    ItemSceneChange = 4
    ItemSceneHasChanged = 5
    ItemVisibleChange = 6
    ItemVisibleHasChanged = 7
    ItemParentChange = 8
    ItemParentHasChanged = 9
    ItemTransformChange = 10
    ItemTransformHasChanged = 11
    ItemRotationChange = 12
    ItemRotationHasChanged = 13


class _QGraphicsItem:
    ItemIsMovable = 1
    ItemIsSelectable = 2
    ItemSendsGeometryChanges = 4
    GraphicsItemFlag = _GraphicsItemFlag
    GraphicsItemChange = _GraphicsItemChange

    def __init__(self, parent=None):
        self._pos = _QPointF()
        self._rotation = 0.0
        self._scene = None
        self._flags = 0
        self._tooltip = ""
        self._parent_item = parent

    def setPos(self, x, y=None):
        if isinstance(x, _QPointF):
            self._pos = x
        else:
            self._pos = _QPointF(x, y or 0)

    def pos(self):
        return self._pos

    def x(self):
        return self._pos.x()

    def y(self):
        return self._pos.y()

    def setRotation(self, r):
        self._rotation = r

    def rotation(self):
        return self._rotation

    def boundingRect(self):
        return _QRectF(-50, -50, 100, 100)

    def sceneBoundingRect(self):
        r = self.boundingRect()
        return _QRectF(
            self._pos.x() + r.x(), self._pos.y() + r.y(), r.width(), r.height()
        )

    def paint(self, *a):
        pass

    def update(self):
        pass

    def prepareGeometryChange(self):
        pass

    def setFlags(self, f):
        self._flags = f

    def flags(self):
        return self._flags

    def setFlag(self, f, v=True):
        if v:
            self._flags |= f
        else:
            self._flags &= ~f

    def setToolTip(self, t):
        self._tooltip = t

    def scene(self):
        return self._scene

    def setZValue(self, z):
        pass

    def zValue(self):
        return 0

    def setVisible(self, v):
        self._visible = v

    def isVisible(self):
        return getattr(self, "_visible", True)

    def setSelected(self, s):
        self._selected = s

    def isSelected(self):
        return getattr(self, "_selected", False)

    def setAcceptHoverEvents(self, v):
        pass

    def setFocus(self, reason=None):
        self._has_focus = True

    def clearFocus(self):
        self._has_focus = False

    def hasFocus(self):
        return getattr(self, "_has_focus", False)

    def setAcceptedMouseButtons(self, b):
        pass

    def setCursor(self, c):
        pass

    def mapToScene(self, p):
        return p

    def mapFromScene(self, p):
        return p

    def mapFromParent(self, p):
        return p

    def childItems(self):
        return []

    def parentItem(self):
        return self._parent_item

    def setParentItem(self, p):
        self._parent_item = p

    def hoverEnterEvent(self, event):
        pass

    def hoverLeaveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        pass

    def mouseReleaseEvent(self, event):
        pass

    def mouseDoubleClickEvent(self, event):
        pass

    def keyPressEvent(self, event):
        pass

    def sceneEvent(self, event):
        return False

    def contextMenuEvent(self, event):
        pass

    def collidingItems(self):
        return []

    def shape(self):
        return MagicMock()

    def contains(self, p):
        return False

    def itemChange(self, change, value):
        return value

    def moveBy(self, dx, dy):
        self.setPos(_QPointF(self._pos.x() + dx, self._pos.y() + dy))

    def scenePos(self):
        return self._pos

    def topLevelItem(self):
        p = self.parentItem()
        return p.topLevelItem() if p is not None else self


class _QGraphicsTextItem(_QGraphicsItem):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._html = text
        self._color = _QColor()
        self._font = MagicMock()
        self._text_interaction_flags = 0

    def toPlainText(self):
        return self._text

    def toHtml(self):
        return self._html

    def setPlainText(self, t):
        self._text = t

    def setHtml(self, h):
        self._html = h

    def setDefaultTextColor(self, c):
        self._color = c

    def defaultTextColor(self):
        return self._color

    def font(self):
        return self._font

    def setFont(self, f):
        self._font = f

    def setTextInteractionFlags(self, f):
        self._text_interaction_flags = f

    def textInteractionFlags(self):
        return self._text_interaction_flags

    def document(self):
        return MagicMock()

    def focusInEvent(self, event):
        pass

    def focusOutEvent(self, event):
        pass

    def textCursor(self):
        return MagicMock()

    def setTextCursor(self, c):
        pass


class _QLineF:
    """Minimal QLineF stand-in with the subset interaction.py uses."""

    def __init__(self, p1=None, p2=None):
        self._p1 = p1 if p1 is not None else _QPointF()
        self._p2 = p2 if p2 is not None else _QPointF()

    def p1(self):
        return self._p1

    def p2(self):
        return self._p2

    def setP1(self, p):
        self._p1 = p

    def setP2(self, p):
        self._p2 = p

    def pointAt(self, t):
        return _QPointF(
            self._p1.x() + (self._p2.x() - self._p1.x()) * t,
            self._p1.y() + (self._p2.y() - self._p1.y()) * t,
        )

    def center(self):
        return _QPointF(
            (self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2
        )

    def length(self):
        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        return math.hypot(dx, dy)

    def angle(self):
        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        deg = math.degrees(math.atan2(dy, dx))
        return -deg % 360

    @staticmethod
    def fromPolar(length, angle):
        rad = math.radians(-angle)
        return _QLineF(_QPointF(0, 0), _QPointF(length * math.cos(rad), length * math.sin(rad)))


class _QByteArray(bytearray):
    """Minimal QByteArray stand-in -- real bytes-like storage so code that
    round-trips binary data through it (e.g. clipboard copy/paste) works."""

    def append(self, data):
        self.extend(data)
        return self

    def data(self):
        return bytes(self)


class _QPainterPath:
    def moveTo(self, *a):
        pass

    def lineTo(self, *a):
        pass

    def cubicTo(self, *a):
        pass

    def quadTo(self, *a):
        pass

    def arcMoveTo(self, *a):
        pass

    def arcTo(self, *a):
        pass

    def closeSubpath(self):
        pass

    def addRect(self, *a):
        pass

    def addEllipse(self, *a):
        pass

    def addPolygon(self, *a):
        self._has_content = True

    def addPath(self, *a):
        self._has_content = True

    def isEmpty(self):
        return not getattr(self, "_has_content", False)

    def boundingRect(self):
        return _QRectF()

    def contains(self, p):
        return False


class _Flag(int):
    """int subclass exposing a PyQt6-style `.value` accessor.

    Real PyQt6 KeyboardModifier/MouseButton constants are IntFlag-like
    objects with a `.value` attribute (code in interaction.py does
    ``modifiers.value & Qt.KeyboardModifier.ShiftModifier.value``). Plain
    ints don't have `.value`, so wrap the stub constants in this subclass.
    """

    @property
    def value(self):
        return int(self)


class _Qt:
    class KeyboardModifier:
        ControlModifier = _Flag(0x04000000)
        ShiftModifier = _Flag(0x02000000)
        AltModifier = _Flag(0x08000000)
        NoModifier = _Flag(0)

    class MouseButton:
        LeftButton = 1
        RightButton = 2
        MiddleButton = 4
        NoButton = 0

    class Key:
        Key_A = 65
        Key_Delete = 16777223
        Key_Backspace = 16777219
        Key_Z = 90
        Key_C = 67
        Key_V = 86
        Key_X = 88
        Key_Escape = 16777216
        Key_Return = 16777220
        Key_Enter = 16777221
        Key_Space = 32
        Key_B = 66
        Key_I = 73
        Key_U = 85
        Key_Equal = 61
        Key_Plus = 43

    class TextInteractionFlag:
        TextEditorInteraction = 5
        NoTextInteraction = 0
        TextSelectableByMouse = 1
        TextSelectableByKeyboard = 2
        LinksAccessibleByMouse = 4
        LinksAccessibleByKeyboard = 8

    class Orientation:
        Horizontal = 1
        Vertical = 2

    class AlignmentFlag:
        AlignLeft = 1
        AlignRight = 2
        AlignCenter = 4
        AlignTop = 32
        AlignBottom = 64
        AlignVCenter = 128
        AlignHCenter = 4

    class CursorShape:
        ArrowCursor = 0
        CrossCursor = 2
        PointingHandCursor = 13
        OpenHandCursor = 17
        ClosedHandCursor = 18
        ForbiddenCursor = 10
        SizeFDiagCursor = 12
        SizeBDiagCursor = 11
        SizeVerCursor = 9
        SizeHorCursor = 10
        WaitCursor = 3

    class ContextMenuPolicy:
        DefaultContextMenu = 1
        NoContextMenu = 0
        CustomContextMenu = 2

    class PenStyle:
        NoPen = 0
        SolidLine = 1
        DashLine = 2
        DotLine = 3
        DashDotLine = 4
        DashDotDotLine = 5

    class PenCapStyle:
        FlatCap = 0
        SquareCap = 16
        RoundCap = 32

    class PenJoinStyle:
        MiterJoin = 0
        BevelJoin = 64
        RoundJoin = 128

    class BrushStyle:
        NoBrush = 0
        SolidPattern = 1
        Dense1Pattern = 2

    class SortOrder:
        AscendingOrder = 0
        DescendingOrder = 1

    class ItemSelectionMode:
        ContainsItemShape = 0
        IntersectsItemShape = 1
        ContainsItemBoundingRect = 2
        IntersectsItemBoundingRect = 3

    class ToolBarArea:
        LeftToolBarArea = 1
        RightToolBarArea = 2
        TopToolBarArea = 4
        BottomToolBarArea = 8
        NoToolBarArea = 0

    class FocusReason:
        TabFocusReason = 0
        BacktabFocusReason = 1
        MouseFocusReason = 2
        ActiveWindowFocusReason = 3
        PopupFocusReason = 4
        ShortcutFocusReason = 5
        OtherFocusReason = 7
        NoFocusReason = 8

    class HitTestAccuracy:
        ExactHit = 0
        WindingFill = 1
        FuzzyHit = 1

    class GlobalColor:
        black = 2
        white = 3
        red = 7
        green = 8
        blue = 9
        transparent = 19

    GlobalColor = MagicMock()
    black = MagicMock()
    red = MagicMock()
    SolidLine = 1
    DashLine = 2
    DotLine = 3
    NoPen = 0
    RoundCap = 16
    FlatCap = 0
    RoundJoin = 128
    BevelJoin = 64
    MiterJoin = 0
    ItemPositionChange = 0
    ItemSceneChange = 1


class _QObject:
    """Minimal QObject stand-in providing the small surface ModeManager/
    InteractionHandler rely on (blockSignals, eventFilter default, event
    filter install/remove) that plain `object` doesn't have."""

    def __init__(self, *a, **kw):
        self._signals_blocked = False

    def blockSignals(self, v):
        old = self._signals_blocked
        self._signals_blocked = v
        return old

    def signalsBlocked(self):
        return self._signals_blocked

    def eventFilter(self, obj, event):
        return False

    def installEventFilter(self, obj):
        pass

    def removeEventFilter(self, obj):
        pass

    def sender(self):
        return getattr(self, "_sender", None)


class _QGraphicsScene:
    """Minimal scene stub with item tracking."""

    def __init__(self, parent=None):
        self._items = []

    def addItem(self, item):
        self._items.append(item)
        item._scene = self

    def removeItem(self, item):
        if item in self._items:
            self._items.remove(item)
        item._scene = None

    def items(self):
        return list(self._items)

    def selectedItems(self):
        return [i for i in self._items if i.isSelected()]

    def views(self):
        return []

    def keyPressEvent(self, event):
        pass


# ---------------------------------------------------------------------------
# Install stubs into sys.modules
# ---------------------------------------------------------------------------


def _make_stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


_pen_mock = MagicMock()
_brush_mock = MagicMock()
_font_mock = MagicMock()

_qt_core = _make_stub(
    "PyQt6.QtCore",
    QPointF=_QPointF,
    QRectF=_QRectF,
    Qt=_Qt,
    QTimer=MagicMock(),
    QObject=_QObject,
    QEvent=MagicMock(),
    QLineF=_QLineF,
    QSizeF=MagicMock(),
    QSize=MagicMock(),
    QThread=MagicMock(),
    QPoint=MagicMock(),
    QBuffer=MagicMock(),
    QIODevice=MagicMock(),
    QMimeData=MagicMock(),
    QFile=MagicMock(),
    QByteArray=_QByteArray,
    QRect=MagicMock(),
    QMargins=MagicMock(),
    QUrl=MagicMock(),
    # PyQt6 signal/slot/property
    pyqtSignal=MagicMock(),
    pyqtSlot=MagicMock(),
    pyqtProperty=MagicMock(),
    # Version attrs required by pytest-qt
    PYQT_VERSION=0x060700,
    PYQT_VERSION_STR="6.7.0",
    QT_VERSION=0x060700,
    QT_VERSION_STR="6.7.0",
    # Logging functions required by pytest-qt
    qDebug=MagicMock(),
    qInfo=MagicMock(),
    qWarning=MagicMock(),
    qCritical=MagicMock(),
    qFatal=MagicMock(),
    qVersion=MagicMock(return_value="6.7.0"),
    qInstallMessageHandler=MagicMock(return_value=None),
    QMessageLogger=MagicMock(),
)
_qt_gui = _make_stub(
    "PyQt6.QtGui",
    QColor=_QColor,
    QPainterPath=_QPainterPath,
    QPen=MagicMock(return_value=_pen_mock),
    QBrush=MagicMock(return_value=_brush_mock),
    QFont=MagicMock(return_value=_font_mock),
    QPainter=MagicMock(),
    QPolygonF=MagicMock(),
    QAction=MagicMock(),
    QIcon=MagicMock(),
    QKeySequence=MagicMock(),
    QCursor=MagicMock(),
    QPixmap=MagicMock(),
    QImage=MagicMock(),
    QTransform=MagicMock(),
    QLinearGradient=MagicMock(),
    QActionGroup=MagicMock(),
    QGuiApplication=MagicMock(),
    QShortcut=MagicMock(),
    QTextCharFormat=MagicMock(),
    QTextCursor=MagicMock(),
    QFontDatabase=MagicMock(),
    qRgba=MagicMock(return_value=0),
    qRgb=MagicMock(return_value=0),
    QPainterPathStroker=MagicMock(),
    QFontMetrics=MagicMock(),
    QFontMetricsF=MagicMock(),
    QDesktopServices=MagicMock(),
    QClipboard=MagicMock(),
    QPalette=MagicMock(),
    QRegion=MagicMock(),
    QDrag=MagicMock(),
    QDropEvent=MagicMock(),
    QDragEnterEvent=MagicMock(),
    QMouseEvent=MagicMock(),
    QKeyEvent=MagicMock(),
    QWheelEvent=MagicMock(),
    QPaintEvent=MagicMock(),
    QResizeEvent=MagicMock(),
    QContextMenuEvent=MagicMock(),
)
_qt_widgets = _make_stub(
    "PyQt6.QtWidgets",
    QGraphicsItem=_QGraphicsItem,
    QGraphicsTextItem=_QGraphicsTextItem,
    QGraphicsScene=_QGraphicsScene,
    QApplication=MagicMock(),
    QWidget=MagicMock(),
    QMenu=MagicMock(),
    QDialog=MagicMock(),
    QMessageBox=MagicMock(),
    QToolBar=MagicMock(),
    QSplitter=MagicMock(),
    QFileDialog=MagicMock(),
    QColorDialog=MagicMock(),
    QFontDialog=MagicMock(),
    QLineEdit=MagicMock(),
    QPushButton=MagicMock(),
    QLabel=MagicMock(),
    QCheckBox=MagicMock(),
    QSpinBox=MagicMock(),
    QDoubleSpinBox=MagicMock(),
    QComboBox=MagicMock(),
    QSlider=MagicMock(),
    QGroupBox=MagicMock(),
    QHBoxLayout=MagicMock(),
    QVBoxLayout=MagicMock(),
    QGridLayout=MagicMock(),
    QFormLayout=MagicMock(),
    QGraphicsView=MagicMock(),
    QGraphicsLineItem=_QGraphicsItem,
    QGraphicsEllipseItem=_QGraphicsItem,
    QGraphicsRectItem=_QGraphicsItem,
    QGraphicsPathItem=_QGraphicsItem,
    QStyleOptionGraphicsItem=MagicMock(),
    QSizePolicy=MagicMock(),
    QToolButton=MagicMock(),
    QActionGroup=MagicMock(),
    QShortcut=MagicMock(),
    QStyle=MagicMock(),
    QButtonGroup=MagicMock(),
    QRadioButton=MagicMock(),
    QTabWidget=MagicMock(),
    QTabBar=MagicMock(),
    QStackedWidget=MagicMock(),
    QScrollArea=MagicMock(),
    QScrollBar=MagicMock(),
    QFrame=MagicMock(),
    QTextEdit=MagicMock(),
    QPlainTextEdit=MagicMock(),
    QListWidget=MagicMock(),
    QListWidgetItem=MagicMock(),
    QTreeWidget=MagicMock(),
    QTreeWidgetItem=MagicMock(),
    QTableWidget=MagicMock(),
    QTableWidgetItem=MagicMock(),
    QHeaderView=MagicMock(),
    QAbstractItemView=MagicMock(),
    QDockWidget=MagicMock(),
    QMainWindow=MagicMock(),
    QStatusBar=MagicMock(),
    QMenuBar=MagicMock(),
    QAction=MagicMock(),
    QWidgetAction=MagicMock(),
    QGraphicsProxyWidget=MagicMock(),
    QGraphicsSimpleTextItem=_QGraphicsItem,
    QGraphicsPixmapItem=_QGraphicsItem,
    QGraphicsItemGroup=_QGraphicsItem,
    QProgressBar=MagicMock(),
    QProgressDialog=MagicMock(),
    QInputDialog=MagicMock(),
    QErrorMessage=MagicMock(),
    QAbstractButton=MagicMock(),
    QDialogButtonBox=MagicMock(),
)
_qt_test = _make_stub("PyQt6.QtTest", QTest=MagicMock())
_qt_svg = _make_stub("PyQt6.QtSvg", QSvgGenerator=MagicMock(), QSvgRenderer=MagicMock())
_qt_svg_widgets = _make_stub(
    "PyQt6.QtSvgWidgets", QGraphicsSvgItem=MagicMock(), QSvgWidget=MagicMock()
)
_qt_opengl = _make_stub("PyQt6.QtOpenGL", QOpenGLWidget=MagicMock())
_qt_print = _make_stub(
    "PyQt6.QtPrintSupport", QPrinter=MagicMock(), QPrintDialog=MagicMock()
)
_pyqt6 = _make_stub(
    "PyQt6",
    QtCore=_qt_core,
    QtGui=_qt_gui,
    QtWidgets=_qt_widgets,
    QtTest=_qt_test,
    QtSvg=_qt_svg,
)

_sip_mock = MagicMock()
_sip_mock.isdeleted.return_value = False

for name, mod in [
    ("PyQt6", _pyqt6),
    ("PyQt6.QtCore", _qt_core),
    ("PyQt6.QtGui", _qt_gui),
    ("PyQt6.QtWidgets", _qt_widgets),
    ("PyQt6.QtTest", _qt_test),
    ("PyQt6.QtSvg", _qt_svg),
    ("PyQt6.QtSvgWidgets", _qt_svg_widgets),
    ("PyQt6.QtOpenGL", _qt_opengl),
    ("PyQt6.QtPrintSupport", _qt_print),
    ("PyQt6.sip", _sip_mock),
]:
    sys.modules.setdefault(name, mod)

# ---------------------------------------------------------------------------
# Configure MagicMock return values that need to be comparable as integers.
# This prevents TypeError when real Qt-heavy code runs through the stubs
# (e.g. QComboBox.findText compared to 0 with >=).
# ---------------------------------------------------------------------------
_qt_widgets.QComboBox.return_value.findText.return_value = -1
_qt_widgets.QComboBox.return_value.currentIndex.return_value = 0
_qt_widgets.QComboBox.return_value.count.return_value = 0
_qt_widgets.QSpinBox.return_value.value.return_value = 12
_qt_widgets.QDoubleSpinBox.return_value.value.return_value = 1.0
_qt_widgets.QSlider.return_value.value.return_value = 0
_qt_gui.QFont.return_value.pointSize.return_value = 12
_qt_gui.QFont.return_value.pixelSize.return_value = -1
_qt_gui.QFont.return_value.bold.return_value = False
_qt_gui.QFont.return_value.italic.return_value = False
_qt_gui.QFont.return_value.underline.return_value = False
_qt_gui.QFont.return_value.family.return_value = "Arial"
_qt_gui.QFont.return_value.weight.return_value = 50

# Make the repo root importable.
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------
import pytest


@pytest.fixture()
def mock_scene():
    return _QGraphicsScene()


@pytest.fixture()
def mock_main_window(mock_scene):
    mw = MagicMock()
    mw.scene = mock_scene
    return mw


# Alias for tests that reference qapp fixture (no-op here — no real QApp needed)
@pytest.fixture(scope="session")
def qapp():
    return None

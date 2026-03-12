import sys, os, requests, json, win32gui, win32con, winreg, logging, math
from PySide6.QtCore import Qt, QPoint, QPointF, QThread, Signal
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon, 
                                QFileDialog, QDialog, QLabel, 
                                QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QSlider, QColorDialog, QSpinBox)
from PySide6.QtGui import (QPixmap, QIcon, QPainter, QPainterPath, QColor, QPen, QFont, 
                           QCursor, QTextListFormat, QTextCursor, QConicalGradient, 
                           QRadialGradient, QTextCharFormat)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QInputDialog)

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', handlers=[logging.StreamHandler(sys.stdout)])

# --- CONFIGURATION ---
CURRENT_VERSION = "4.6"
UPDATE_URL = "https://raw.githubusercontent.com/designswithharshit/Custom-Windows-Widget/main/version.json"
APP_NAME = "WinWidget"

# 1. CHANGED: Save path is now the user's home directory inside a hidden folder
APPDATA_DIR = os.path.join(os.path.expanduser("~"), ".winwidget")
os.makedirs(APPDATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")
COLOR_HISTORY_PATH = os.path.join(APPDATA_DIR, "colors.json")

def resource_path(relative_path):
    try: return os.path.join(sys._MEIPASS, relative_path)
    except Exception: return os.path.abspath(relative_path)

ICON_PATH = resource_path("app.ico")
DEFAULT_IMG = resource_path("default.jpg")
HEADERS = {'User-Agent': 'Mozilla/5.0'}

MENU_STYLE = """
    QMenu { background-color: #1e1e1e; color: #ececec; border: 1px solid #333; border-radius: 6px; padding: 4px; font-family: 'Segoe UI'; font-size: 13px; }
    QMenu::item { padding: 6px 25px 6px 15px; border-radius: 4px; }
    QMenu::item:selected { background-color: #2c2c2c; }
    QMenu::separator { height: 1px; background: #333; margin: 4px 10px; }
"""

SLIDER_STYLE = """
    QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: rgba(255,255,255,50); }
    QSlider::handle:horizontal { background: #00a8ff; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
"""

def get_wallpaper_window():
    progman = win32gui.FindWindow("Progman", None)
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)
    res = []
    win32gui.EnumWindows(lambda h, r: r.append(h) if win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None) else None, res)
    return win32gui.FindWindowEx(0, res[0], "WorkerW", None) if res else None

# --- WELCOME SCREEN ---
class WelcomeScreen(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Welcome")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(500, 350)
        
        layout = QVBoxLayout(self); layout.setContentsMargins(20,20,20,20)
        self.bg = QLabel(self); self.bg.setStyleSheet("background-color: rgba(20, 20, 20, 230); border: 1px solid #444; border-radius: 15px;")
        self.bg.setGeometry(0, 0, 500, 350); self.bg.lower()

        title = QLabel("WinWidget is Active!", self); title.setStyleSheet("color: white; font-size: 24px; font-weight: bold;"); title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel("1. The app runs in your System Tray (Bottom Right).\n2. Right-Click the Tray Icon to 'Edit Layout'.\n3. Right-Click any widget to change its image.", self)
        info.setStyleSheet("color: #ccc; font-size: 14px; margin: 15px;"); info.setWordWrap(True); info.setAlignment(Qt.AlignLeft)
        layout.addWidget(info)
        
        btn = QPushButton("Got it"); btn.setStyleSheet("background: #E60023; color: white; padding: 8px; border-radius: 5px;")
        btn.clicked.connect(self.accept); layout.addWidget(btn)
        layout.setAlignment(btn, Qt.AlignCenter)
        self.exec()

# --- SAFE IMAGE THREADING ---
class ImageLoader(QThread):
    loaded = Signal(bytes, str) 
    
    def __init__(self, src, parent=None): 
        super().__init__(parent) 
        self.src = src
        
    def run(self):
        try:
            if os.path.isfile(self.src):
                with open(self.src, "rb") as f:
                    data = f.read()
            else: 
                data = requests.get(self.src, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).content
            
            if data:
                self.loaded.emit(data, self.src)
        except Exception as e: 
            logging.error(f"Image load failed: {e}")

class ColorWheel(QWidget):
    colorChanged = Signal(QColor)
    def __init__(self):
        super().__init__()
        self.setFixedSize(160, 160)
        self.hue = 0; self.sat = 0; self.val = 255
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect(); cx, cy = r.width()/2, r.height()/2
        
        # Hue Gradient
        conical = QConicalGradient(cx, cy, 0)
        for i in range(7): conical.setColorAt(i/6.0, QColor.fromHsv(int(359*(i/6.0)), 255, 255))
        p.setBrush(conical); p.setPen(Qt.NoPen); p.drawEllipse(r)
        
        # Saturation Fade (White in center)
        radial = QRadialGradient(cx, cy, r.width()/2)
        radial.setColorAt(0, QColor(255, 255, 255, 255))
        radial.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(radial); p.drawEllipse(r)
        
        # Target Marker
        angle = math.radians(self.hue)
        dist = (self.sat / 255) * (r.width() / 2)
        mx, my = cx + math.cos(angle)*dist, cy - math.sin(angle)*dist
        p.setBrush(Qt.NoBrush); p.setPen(QPen(Qt.black, 2)); p.drawEllipse(QPointF(mx, my), 5, 5)
        p.setPen(QPen(Qt.white, 1)); p.drawEllipse(QPointF(mx, my), 4, 4)

    def mouseMoveEvent(self, e): self.update_color(e.position().toPoint())
    def mousePressEvent(self, e): self.update_color(e.position().toPoint())
    
    def update_color(self, pos):
        cx, cy = self.width()/2, self.height()/2
        dx, dy = pos.x() - cx, pos.y() - cy
        self.hue = int(math.degrees(math.atan2(-dy, dx)) % 360)
        self.sat = min(255, int((math.hypot(dx, dy) / (self.width()/2)) * 255))
        self.colorChanged.emit(QColor.fromHsv(self.hue, self.sat, self.val))
        self.update()

class ModernColorPicker(QDialog):
    def __init__(self, initial=Qt.white, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.current_color = QColor(initial)
        self.oldPos = None
        
        self.setStyleSheet("""
            QDialog > QWidget { background: #fdfdfd; border: 1px solid #ccc; border-radius: 8px; }
            QPushButton { background: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; padding: 5px 15px; font-weight: bold; color: #333; }
            QPushButton:hover { background: #e0e0e0; }
            QPushButton#btnOK { background: #007aff; color: white; border: none; }
            QPushButton#btnOK:hover { background: #005bb5; }
        """)
        
        main_layout = QVBoxLayout(self)
        container = QWidget(self); main_layout.addWidget(container)
        layout = QVBoxLayout(container); layout.setContentsMargins(15, 15, 15, 15)
        
        # Color Wheel
        self.wheel = ColorWheel()
        self.wheel.colorChanged.connect(self.sync_color)
        layout.addWidget(self.wheel, alignment=Qt.AlignCenter)
        
        # Brightness Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 255); self.slider.setValue(255)
        self.slider.setStyleSheet("QSlider::groove:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #000, stop:1 #fff); height: 10px; border-radius: 5px; } QSlider::handle:horizontal { background: white; border: 2px solid #999; width: 14px; margin: -3px 0; border-radius: 7px; }")
        self.slider.valueChanged.connect(self.update_brightness)
        layout.addWidget(self.slider)
        
        # Preview Bar (Full width)
        self.preview = QLabel()
        self.preview.setFixedHeight(20)
        layout.addWidget(self.preview)
        
        # History (Centered below preview)
        self.history_layout = QHBoxLayout()
        self.history_layout.setSpacing(4)
        self.history_layout.setAlignment(Qt.AlignCenter)
        layout.addLayout(self.history_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("OK"); btn_ok.setObjectName("btnOK"); btn_ok.clicked.connect(self.accept)
        btn_layout.addStretch(); btn_layout.addWidget(btn_cancel); btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        self.load_history()
        self.sync_color(self.current_color)

    # --- ADDED DRAG SUPPORT ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.oldPos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.oldPos is not None:
            delta = e.globalPosition().toPoint() - self.oldPos
            self.move(self.pos() + delta)
            self.oldPos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self.oldPos = None
    # --------------------------

    def sync_color(self, c):
        self.current_color = c
        self.preview.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #aaa; border-radius: 4px;")
        
    def update_brightness(self, val):
        self.wheel.val = val
        self.wheel.colorChanged.emit(QColor.fromHsv(self.wheel.hue, self.wheel.sat, val))

    def load_history(self):
        history = []
        if os.path.exists(COLOR_HISTORY_PATH):
            try: history = json.load(open(COLOR_HISTORY_PATH, "r"))
            except: pass
        for hex_code in history[:8]:
            btn = QPushButton(); btn.setFixedSize(20, 20)
            btn.setStyleSheet(f"background-color: {hex_code}; border: 1px solid #ddd; border-radius: 2px;")
            btn.clicked.connect(lambda _, c=hex_code: self.sync_color(QColor(c)))
            self.history_layout.addWidget(btn)
            
    def save_history(self):
        history = [self.current_color.name()]
        if os.path.exists(COLOR_HISTORY_PATH):
            try: history += json.load(open(COLOR_HISTORY_PATH, "r"))
            except: pass
        history = list(dict.fromkeys(history))[:8] # Keep unique, max 8
        json.dump(history, open(COLOR_HISTORY_PATH, "w"))

    @classmethod
    def getColor(cls, initial=Qt.white, parent=None):
        dlg = cls(initial, parent)
        if dlg.exec():
            dlg.save_history()
            return dlg.current_color
        return QColor() # Invalid if canceled

# --- FLOATING TOOLBAR ---
class FloatingToolbar(QWidget):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 1. Create the shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40)) # Soft light shadow
        shadow.setOffset(0, 4)
        
        # 2. Main layout needs margins so the shadow doesn't get cut off
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15) 
        
        # 3. Create the white container box
        self.container = QWidget(self)
        self.container.setGraphicsEffect(shadow)
        self.container.setStyleSheet("""
            QWidget { 
                background-color: #ffffff; 
                border: 1px solid #e0e0e0; 
                border-radius: 6px; 
            }
            QPushButton { 
                background: transparent; 
                color: #37352f; /* Notion's dark text color */
                border: none; 
                font-weight: bold; 
                font-family: 'Segoe UI', sans-serif; 
                border-radius: 4px; 
                padding: 6px 12px; 
            }
            QPushButton:hover { 
                background-color: #f1f1ef; /* Light gray hover */
            }
        """)
        
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(2)

        # 2. CHANGED: Added A+ and A- for fast text resizing
        for text, action in [("B", 'bold'), ("I", 'italic'), ("S", 'strike'), ("H1", 'h1'), ("A+", 'size_up'), ("A-", 'size_down'), ("🎨", 'color')]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, a=action: self.apply_format(a))
            container_layout.addWidget(btn)
            
        main_layout.addWidget(self.container)

    def apply_format(self, action):
        fmt = QTextCharFormat()
        current_size = self.text_edit.currentCharFormat().fontPointSize()
        if current_size == 0: current_size = 14 # Default if none set

        if action == 'bold': fmt.setFontWeight(QFont.Bold if self.text_edit.currentCharFormat().fontWeight() != QFont.Bold else QFont.Normal)
        elif action == 'italic': fmt.setFontItalic(not self.text_edit.currentCharFormat().fontItalic())
        elif action == 'strike': fmt.setFontStrikeOut(not self.text_edit.currentCharFormat().fontStrikeOut())
        elif action == 'h1': fmt.setFontPointSize(18); fmt.setFontWeight(QFont.Bold)
        elif action == 'size_up': fmt.setFontPointSize(current_size + 2)
        elif action == 'size_down': fmt.setFontPointSize(max(6, current_size - 2))
        elif action == 'color':
            self.show_color_menu()
            return
            
        self.text_edit.mergeCurrentCharFormat(fmt)

    def show_color_menu(self):
        menu = QMenu(self)
        menu.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground)
        
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 5px; }
            QMenu::item { padding: 6px 25px 6px 10px; border-radius: 4px; color: #37352f; font-family: 'Segoe UI', sans-serif; font-weight: 500; }
            QMenu::item:selected { background-color: #f1f1ef; }
            QMenu::separator { height: 1px; background: #e0e0e0; margin: 4px 10px; }
        """)

        colors = {
            "Default (Dark)": "#181818", "Gray": "#9b9a97", "Brown": "#64473a",
            "Orange": "#d9730d", "Yellow": "#dfab01", "Green": "#0f7b6c",
            "Blue": "#0b6e99", "Purple": "#6940a5", "Pink": "#ad1a72", "Red": "#e03e3e", "White": "#ececec"
        }

        for name, hex_code in colors.items():
            pix = QPixmap(14, 14); pix.fill(QColor(hex_code))
            action = menu.addAction(QIcon(pix), name)
            action.triggered.connect(lambda checked=False, c=hex_code: self.set_text_color(c))

        # Add the custom color option at the bottom
        menu.addSeparator()
        custom_action = menu.addAction("More Colors...")
        custom_action.triggered.connect(self.open_custom_text_color)

        menu.exec(QCursor.pos())

    def open_custom_text_color(self):
        color = ModernColorPicker.getColor(Qt.black, self)
        if color.isValid():
            self.set_text_color(color.name())

    def set_text_color(self, hex_color):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(hex_color))
        self.text_edit.mergeCurrentCharFormat(fmt)


# --- NOTION TEXT EDIT (INTERACTIVE CHECKBOXES) ---
class NotionTextEdit(QTextEdit):
    toggled_checkbox = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.toolbar = FloatingToolbar(self)
        self.selectionChanged.connect(self.handle_selection)

    def handle_selection(self):
        parent = self.parentWidget()
        is_editing = parent and getattr(parent, 'is_editing', False)
        
        if self.textCursor().hasSelection() and is_editing:
            rect = self.cursorRect(self.textCursor())
            global_pos = self.viewport().mapToGlobal(rect.topRight())
            self.toolbar.move(global_pos.x() + 10, global_pos.y() - 40)
            self.toolbar.show()
        else:
            self.toolbar.hide()

    def get_checkbox_cursor(self, pos_pt):
        cursor = self.cursorForPosition(pos_pt)
        rect = self.cursorRect(cursor)
        
        if abs(pos_pt.y() - rect.center().y()) < 15:
            pos = cursor.position()
            for offset in [-2, -1, 0, 1]:
                test_cursor = QTextCursor(self.document())
                test_cursor.setPosition(pos)
                if offset < 0:
                    test_cursor.movePosition(QTextCursor.PreviousCharacter, n=-offset)
                elif offset > 0:
                    test_cursor.movePosition(QTextCursor.NextCharacter, n=offset)
                    
                test_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
                if test_cursor.selectedText() in ['☐', '☑\uFE0E', '☑']:
                    cb_rect = self.cursorRect(test_cursor)
                    if abs(pos_pt.x() - cb_rect.x()) < 25:
                        return test_cursor
        return None

    def mouseMoveEvent(self, e):
        cb_cursor = self.get_checkbox_cursor(e.position().toPoint())
        parent = self.parentWidget()
        is_locked = parent and hasattr(parent, 'is_editing') and not parent.is_editing

        self.viewport().setCursor(Qt.PointingHandCursor if cb_cursor else (Qt.ArrowCursor if is_locked else Qt.IBeamCursor))
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        cb_cursor = self.get_checkbox_cursor(e.position().toPoint())
        parent = self.parentWidget()
        is_locked = parent and hasattr(parent, 'is_editing') and not parent.is_editing

        if cb_cursor:
            was_ro = self.isReadOnly()
            if was_ro: self.setReadOnly(False)
            
            char = cb_cursor.selectedText()
            cb_cursor.insertText('☑\uFE0E' if char == '☐' else '☐')
            
            if was_ro: self.setReadOnly(True)
            self.toggled_checkbox.emit()
            return

        if is_locked:
            e.ignore()
            return

        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        parent = self.parentWidget()
        if parent and hasattr(parent, 'is_editing') and not parent.is_editing:
            return

        if e.key() == Qt.Key_Space:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            text = cursor.selectedText()

            if text in ['-', '*']:
                cursor.removeSelectedText()
                self.textCursor().createList(QTextListFormat.ListDisc)
                return
            elif text == '[]':
                cursor.removeSelectedText()
                self.insertPlainText("☐ ")
                return
            elif text == '1.':
                cursor.removeSelectedText()
                self.textCursor().createList(QTextListFormat.ListDecimal)
                return
            cursor.clearSelection()

        super().keyPressEvent(e)

class ModernInputDialog(QDialog):
    def __init__(self, title, label_text, current_val, min_val, max_val, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.oldPos = None

        main_layout = QVBoxLayout(self)
        container = QWidget(self)
        container.setStyleSheet("""
            QWidget { background: #2c2c2c; border: 1px solid #444; border-radius: 8px; color: #ececec; font-family: 'Segoe UI'; }
            QLabel { font-size: 14px; font-weight: bold; border: none; }
            QSpinBox { background: #1e1e1e; border: 1px solid #555; border-radius: 4px; padding: 5px; color: white; font-size: 14px; }
            QPushButton { background: #444; border: none; border-radius: 4px; padding: 6px 15px; font-weight: bold; color: white; }
            QPushButton:hover { background: #555; }
            QPushButton#btnOK { background: #007aff; }
            QPushButton#btnOK:hover { background: #005bb5; }
        """)
        main_layout.addWidget(container)
        
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel(label_text))
        
        self.spin = QSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setValue(current_val)
        layout.addWidget(self.spin)
        
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("OK"); btn_ok.setObjectName("btnOK"); btn_ok.clicked.connect(self.accept)
        
        btn_layout.addStretch(); btn_layout.addWidget(btn_cancel); btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.oldPos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if hasattr(self, 'oldPos') and self.oldPos:
            self.move(self.pos() + (e.globalPosition().toPoint() - self.oldPos))
            self.oldPos = e.globalPosition().toPoint()
    def mouseReleaseEvent(self, e): self.oldPos = None

    @classmethod
    def getInt(cls, parent, title, label_text, current_val, min_val, max_val):
        dlg = cls(title, label_text, current_val, min_val, max_val, parent)
        if dlg.exec(): return dlg.spin.value(), True
        return current_val, False

# --- BASE WIDGET ARCHITECTURE ---
class BaseWidget(QWidget):
    def __init__(self, data, controller):
        super().__init__()
        self.controller = controller 
        self.w_type = data.get("type", "base")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.opacity = data.get("opacity", 1.0)
        self.roundness = data.get("roundness", 12)
        self.is_editing = False
        self.action_state = None 
        
        self.resize(data.get("w", 250), data.get("h", 300))
        self.move(data.get("x", 200), data.get("y", 200))

        self.op_slider = QSlider(Qt.Horizontal, self)
        self.op_slider.setRange(10, 100); self.op_slider.setValue(int(self.opacity*100))
        self.op_slider.setStyleSheet(SLIDER_STYLE); self.op_slider.hide()
        self.op_slider.valueChanged.connect(lambda v: self.set_val('op', v))
        self.op_slider.sliderReleased.connect(lambda: self.controller.save_all())

        self.rd_slider = QSlider(Qt.Horizontal, self)
        self.rd_slider.setRange(0, 100); self.rd_slider.setValue(self.roundness)
        self.rd_slider.setStyleSheet(SLIDER_STYLE); self.rd_slider.hide()
        self.rd_slider.valueChanged.connect(lambda v: self.set_val('rd', v))
        self.rd_slider.sliderReleased.connect(lambda: self.controller.save_all())

    def set_val(self, kind, val):
        if kind == 'op': self.opacity = val/100.0
        if kind == 'rd': self.roundness = val
        self.repaint() 

    def setup_complete(self):
        self.set_interaction(False)

    def set_interaction(self, enable):
        self.is_editing = enable
        hwnd = int(self.winId())
        
        if enable:
            win32gui.SetParent(hwnd, 0)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.show()
            
            new_hwnd = int(self.winId())
            style = win32gui.GetWindowLong(new_hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(new_hwnd, win32con.GWL_EXSTYLE, style & ~win32con.WS_EX_TRANSPARENT)
            
            self.op_slider.show(); self.rd_slider.show()
            self.activateWindow(); self.raise_()
        else:
            self.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.Tool |
                Qt.WindowDoesNotAcceptFocus
            )

            self.show()
            hwnd = int(self.winId())

            # Put behind normal windows but NOT inside wallpaper
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_BOTTOM,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE |
                win32con.SWP_NOSIZE |
                win32con.SWP_NOACTIVATE
            )

            self.op_slider.hide()
            self.rd_slider.hide()

    def resizeEvent(self, e):
        if hasattr(self, 'op_slider'):
            self.op_slider.setGeometry(15, self.height() - 45, self.width() - 65, 15)
            self.rd_slider.setGeometry(15, self.height() - 25, self.width() - 65, 15)

    def mousePressEvent(self, e):
        if not self.is_editing: return
        self.activateWindow()
        self.setFocus() 
        
        pos = e.position().toPoint()
        self.last_pos = e.globalPosition().toPoint()
        self.start_global = self.last_pos
        self.start_size = self.size()
        
        if pos.x() > self.width()-40 and pos.y() > self.height()-40: 
            self.action_state = 'resize'
        elif pos.y() < 40: 
            self.action_state = 'drag' 
        else: 
            self.action_state = None

    def mouseMoveEvent(self, e):
        if not self.action_state:
            return super().mouseMoveEvent(e)
            
        curr = e.globalPosition().toPoint()
        if self.action_state == 'drag': 
            self.move(self.pos() + (curr - self.last_pos))
            self.last_pos = curr
        elif self.action_state == 'resize': 
            total_delta = curr - self.start_global
            self.resize(max(150, self.start_size.width() + total_delta.x()), max(150, self.start_size.height() + total_delta.y()))
        
        self.repaint()

    def mouseReleaseEvent(self, e): 
        if self.action_state:
            self.action_state = None
            self.controller.save_all()
        else:
            super().mouseReleaseEvent(e)
    
    def contextMenuEvent(self, e):
        if self.is_editing: self.show_context_menu(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() == Qt.ShiftModifier and self.is_editing: 
            self.controller.toggle_edit()
        else:
            super().keyPressEvent(e)

    def show_context_menu(self, pos):
        m = QMenu(self); m.setStyleSheet(MENU_STYLE)
        m.addAction("✅ Finish & Lock", self.controller.toggle_edit)
        m.addSeparator()
        self.add_custom_menu_items(m)
        m.addSeparator()
        
        st = m.addMenu("⚙️ Manual Settings")
        st.addAction(f"Opacity: {int(self.opacity*100)}%", self.change_opacity)
        st.addAction(f"Roundness: {self.roundness}px", self.change_roundness)
        
        m.addSeparator()
        m.addAction("🗑️ Delete Widget", self.delete_widget)
        m.exec(pos)

    def change_opacity(self):
        val, ok = ModernInputDialog.getInt(self, "Opacity", "Enter % (10-100):", int(self.opacity*100), 10, 100)
        if ok: self.opacity = val/100.0; self.op_slider.setValue(val); self.repaint(); self.controller.save_all()

    def change_roundness(self):
        val, ok = ModernInputDialog.getInt(self, "Roundness", "Enter radius (0-100):", self.roundness, 0, 100)
        if ok: self.roundness = val; self.rd_slider.setValue(val); self.repaint(); self.controller.save_all()

    def delete_widget(self):
        self.hide(); self.controller.widgets.remove(self); self.controller.save_all(); self.deleteLater()

    def add_custom_menu_items(self, m): pass
    def get_save_data(self): return {}

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        self.draw_content(p, rect)
        
        if self.is_editing:
            grip_w, grip_h = 40, 5
            p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 120))
            p.drawRoundedRect((rect.width() - grip_w) // 2, 10, grip_w, grip_h, 2, 2)
            
            p.setPen(QPen(QColor(0, 168, 255, 100), 2)); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1,1,-1,-1), self.roundness, self.roundness)
            
            p.setBrush(QColor(0, 168, 255, 200)); p.setPen(Qt.NoPen)
            p.drawEllipse(rect.bottomRight() - QPoint(15, 15), 6, 6)

    def draw_content(self, p, rect): pass

# --- SPECIFIC WIDGETS ---
class ImageWidget(BaseWidget):
    def __init__(self, data, controller):
        data["type"] = "image"
        super().__init__(data, controller)
        self.url = data.get("url", DEFAULT_IMG if os.path.exists(DEFAULT_IMG) else "https://i.pinimg.com/1200x/e3/bf/36/e3bf36325fce44e12106bdc49549641e.jpg")
        self.zoom = data.get("zoom", 1.0)
        self.img_offset = QPoint(data.get("ox", 0), data.get("oy", 0))
        self.pixmap = None
        self.start_loading(self.url)
        self.setup_complete()

    def start_loading(self, src): 
        self.loader = ImageLoader(src)
        self.loader.loaded.connect(self.on_load)
        self.loader.start()
        
    def on_load(self, img_data, url): 
        pix = QPixmap()
        pix.loadFromData(img_data)
        if not pix.isNull():
            self.pixmap = pix
            self.url = url
            self.repaint()

    def draw_content(self, p, rect):
        if not self.pixmap: return
        p.setOpacity(self.opacity)
        path = QPainterPath(); path.addRoundedRect(rect, self.roundness, self.roundness)
        p.save(); p.setClipPath(path)
        scaled = self.pixmap.scaled(int(rect.width()*self.zoom), int(rect.height()*self.zoom), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        cx, cy = rect.x() + (rect.width()-scaled.width())//2 + self.img_offset.x(), rect.y() + (rect.height()-scaled.height())//2 + self.img_offset.y()
        p.drawPixmap(cx, cy, scaled)
        p.restore()

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        if self.is_editing and e.modifiers() == Qt.ShiftModifier: self.action_state = 'pan'

    def mouseMoveEvent(self, e):
        if self.action_state == 'pan':
            self.img_offset += (e.globalPosition().toPoint() - self.last_pos)
            self.last_pos = e.globalPosition().toPoint(); self.repaint()
        else: super().mouseMoveEvent(e)

    def wheelEvent(self, e):
        if not self.is_editing: return
        self.zoom = max(1.0, self.zoom + (0.1 if e.angleDelta().y() > 0 else -0.1))
        self.repaint(); self.controller.save_all()

    def add_custom_menu_items(self, m):
        m.addAction("🖼️ Choose Local Image", self.load_local)
        m.addAction("🌐 Paste Web URL", self.load_web)

    def load_local(self): 
        f, _ = QFileDialog.getOpenFileName(self, "Image", "", "Images (*.png *.jpg *.jpeg)")
        if f: self.start_loading(f); self.controller.save_all()
        
    def load_web(self): 
        u, k = ModernInputDialog.getText(self, "Input", "Image URL:", text=self.url)
        if k and u: self.start_loading(u); self.controller.save_all()

    def get_save_data(self): return {"url": self.url, "zoom": self.zoom, "ox": self.img_offset.x(), "oy": self.img_offset.y()}

class NoteWidget(BaseWidget):
    def __init__(self, data, controller):
        data["type"] = "note"
        super().__init__(data, controller)
        self.text_edit = NotionTextEdit(self)
        default_text = "<h3 style='color:#ffffff; font-weight: 600; margin-bottom: 5px;'>Notes</h3><p style='color:#a0a0a0;'>Type here...</p>"
        self.text_edit.setHtml(data.get("text", default_text))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: transparent; 
                color: #ececec; 
                border: none; 
                font-family: 'Segoe UI', sans-serif; 
                font-size: 14px;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        self.text_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.text_edit.mapToGlobal(pos)))
        
        self.text_edit.toggled_checkbox.connect(lambda: self.controller.save_all())
        self.bg_color = data.get("bg_color", "rgba(25, 25, 25, 230)")
        self.setup_complete()

    def draw_content(self, p, rect):
        p.setOpacity(self.opacity)
        path = QPainterPath(); path.addRoundedRect(rect, self.roundness, self.roundness)
        p.fillPath(path, QColor(self.bg_color))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'text_edit'):
            top_offset = 40 if self.is_editing else 15
            bot_offset = 65 if self.is_editing else 15
            self.text_edit.setGeometry(15, top_offset, self.width() - 30, self.height() - top_offset - bot_offset)

    def set_interaction(self, enable):
        super().set_interaction(enable)
        self.text_edit.setReadOnly(not enable)
        if enable:
            self.text_edit.setTextInteractionFlags(Qt.TextEditorInteraction)
            self.text_edit.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.text_edit.setTextInteractionFlags(Qt.TextBrowserInteraction)
            cursor = self.text_edit.textCursor()
            cursor.clearSelection()
            self.text_edit.setTextCursor(cursor)
        self.resizeEvent(None)

    def add_custom_menu_items(self, m):
        # 1. Formatting
        fmt = m.addMenu("📝 Insert...")
        fmt.addAction("☐ Checkbox", lambda: self.text_edit.textCursor().insertText("☐ "))
        fmt.addAction("• Bullet Point", lambda: self.text_edit.textCursor().createList(QTextListFormat.ListDisc))
        fmt.addAction("1. Number List", lambda: self.text_edit.textCursor().createList(QTextListFormat.ListDecimal))
        
        # 2. Styling
        style = m.addMenu("Style Text")
        style.addAction("Bold", lambda: self.apply_format('bold'))
        style.addAction("Italic", lambda: self.apply_format('italic'))
        style.addAction("Strikethrough", lambda: self.apply_format('strike'))
        style.addSeparator()
        style.addAction("Heading 1", lambda: self.apply_format('h1'))
        style.addAction("Normal Text", lambda: self.apply_format('normal'))
        style.addSeparator()
        style.addAction("Increase Size (A+)", lambda: self.apply_format('size_up'))
        style.addAction("Decrease Size (A-)", lambda: self.apply_format('size_down'))
        style.addAction("Set Exact Size...", self.set_custom_text_size)

        # 3. Colors
        colors = m.addMenu("Colors")
        colors.addAction("Change Text Color", self.change_text_color)
        colors.addAction("Change Background Color", self.change_bg_color)

    def apply_format(self, action):
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        current_size = self.text_edit.currentCharFormat().fontPointSize()
        if current_size == 0: current_size = 14

        if action == 'bold':
            current = self.text_edit.currentCharFormat().fontWeight()
            fmt.setFontWeight(QFont.Bold if current != QFont.Bold else QFont.Normal)
        elif action == 'italic':
            fmt.setFontItalic(not self.text_edit.currentCharFormat().fontItalic())
        elif action == 'strike':
            fmt.setFontStrikeOut(not self.text_edit.currentCharFormat().fontStrikeOut())
        elif action == 'h1':
            fmt.setFontPointSize(18); fmt.setFontWeight(QFont.Bold)
        elif action == 'normal':
            fmt.setFontPointSize(14); fmt.setFontWeight(QFont.Normal)
        elif action == 'size_up':
            fmt.setFontPointSize(current_size + 2)
        elif action == 'size_down':
            fmt.setFontPointSize(max(6, current_size - 2))
            
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.controller.save_all()

    def set_custom_text_size(self):
        current_size = int(self.text_edit.currentCharFormat().fontPointSize())
        if current_size == 0: current_size = 14
        val, ok = ModernInputDialog.getInt(self, "Text Size", "Enter size (6-100):", current_size, 6, 100)
        if ok:
            fmt = QTextCharFormat()
            fmt.setFontPointSize(val)
            self.text_edit.textCursor().mergeCharFormat(fmt)
            self.text_edit.mergeCurrentCharFormat(fmt)
            self.controller.save_all()

    def change_text_color(self):
        color = ModernColorPicker.getColor(Qt.white, self)
        if color.isValid():
            self.text_edit.setTextColor(color)
            self.controller.save_all()

    def change_bg_color(self):
        color = ModernColorPicker.getColor(QColor(self.bg_color), self)
        if color.isValid():
            self.bg_color = color.name(QColor.HexArgb)
            self.repaint()
            self.controller.save_all()

    def get_save_data(self): 
        return {"text": self.text_edit.toHtml(), "bg_color": self.bg_color}
    
class TrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.is_edit = False
        self.widgets = []
        
        if os.path.exists("app.ico"):
            icon = QIcon("app.ico")
        else:
            p = QPixmap(64, 64); p.fill(Qt.transparent)
            pt = QPainter(p); pt.setRenderHint(QPainter.Antialiasing)
            pt.setBrush(QColor("#00a8ff")); pt.setPen(Qt.NoPen)
            pt.drawEllipse(12, 12, 40, 40); pt.end()
            icon = QIcon(p)
            
        self.tray = QSystemTrayIcon(icon)
        self.menu = QMenu(); self.menu.setStyleSheet(MENU_STYLE)
        
        self.act_edit = self.menu.addAction("🛠️ Edit Layout")
        self.act_edit.triggered.connect(self.toggle_edit)
        self.menu.addSeparator()
        self.menu.addAction("🖼️ Add Image", lambda: self.spawn_widget({"type": "image"}))
        self.menu.addAction("📝 Add Note", lambda: self.spawn_widget({"type": "note"}))
        self.menu.addSeparator()
        self.act_start = self.menu.addAction("Run on Startup"); self.act_start.setCheckable(True)
        self.act_start.setChecked(self.chk_start()); self.act_start.triggered.connect(self.set_start)
        self.menu.addSeparator(); self.menu.addAction("🞩 Quit", self.qt_app.quit)
        
        self.tray.setContextMenu(self.menu); self.tray.show()
        self.tray.activated.connect(lambda r: self.tray.contextMenu().exec(QCursor.pos()) if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.Context) else None)
        self.load_init()

    def toggle_edit(self):
        self.is_edit = not self.is_edit
        self.act_edit.setText("✅ Finish & Lock" if self.is_edit else "🛠️ Edit Layout")
        for w in self.widgets: w.set_interaction(self.is_edit)
        if not self.is_edit: self.save_all()

    def spawn_widget(self, data):
        w = ImageWidget(data, self) if data.get("type") == "image" else NoteWidget(data, self)
        self.widgets.append(w)
        if self.is_edit: w.set_interaction(True)

    def load_init(self):
        if os.path.exists(CONFIG_PATH):
            try:
                for d in json.load(open(CONFIG_PATH, "r")): self.spawn_widget(d)
            except: self.spawn_widget({"type": "image"})
        else: self.spawn_widget({"type": "image"})

    def save_all(self):
        data = []
        for w in self.widgets:
            base = {"type": w.w_type, "x": w.x(), "y": w.y(), "w": w.width(), "h": w.height(), "opacity": w.opacity, "roundness": w.roundness}
            base.update(w.get_save_data())
            data.append(base)
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f)
        except Exception as e: logging.error(f"Save failed: {e}")

    def chk_start(self):
        try: k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ); winreg.QueryValueEx(k, APP_NAME); return True
        except: return False
        
    def set_start(self, s):
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if s: 
            if getattr(sys, 'frozen', False):
                exe_path = f'"{sys.executable}"'
            else:
                exe_path = f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe_path)
        else: 
            try: winreg.DeleteValue(k, APP_NAME)
            except: pass

if __name__ == "__main__":
    app = TrayApp()
    sys.exit(app.qt_app.exec())
import sys, os, requests, json, win32gui, win32con, winreg, webbrowser
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon, 
                             QInputDialog, QSlider, QFileDialog, QDialog, QLabel, 
                             QVBoxLayout, QPushButton, QMessageBox)
from PySide6.QtCore import Qt, QSize, QPoint, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPainterPath, QColor, QPen, QFont

# --- CONFIGURATION ---
CURRENT_VERSION = "1.0"
# IMPORTANT: Replace this with your raw GitHub JSON link
UPDATE_URL = "https://raw.githubusercontent.com/designswithharshit/Custom-Windows-Widget/main/version.json"

# --- RESOURCE PATH FIXER ---
def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONSTANTS ---
APP_NAME = "WinWidget"
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
if not os.path.exists(APPDATA_DIR): os.makedirs(APPDATA_DIR)
CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")

# Assets
ICON_PATH = resource_path("app.ico")
DEFAULT_IMG_PATH = resource_path("default.jpg")
HEADERS = {'User-Agent': 'Mozilla/5.0'}
MENU_STYLE = """
    QMenu { background-color: rgba(30, 30, 30, 240); color: white; border: 1px solid rgba(255, 255, 255, 30); border-radius: 10px; padding: 5px; }
    QMenu::item { padding: 8px 25px; border-radius: 5px; }
    QMenu::item:selected { background-color: rgba(255, 255, 255, 40); }
    QMenu::separator { height: 1px; background: rgba(255, 255, 255, 20); margin: 5px 10px; }
"""

# --- AUTO-UPDATE WORKER ---
class UpdateChecker(QThread):
    found_update = Signal(str, str) # version, url

    def run(self):
        try:
            # 1. Fetch JSON from GitHub
            response = requests.get(UPDATE_URL, timeout=5)
            if response.status_code == 200:
                data = response.json()
                latest = data.get("version", "0.0")
                url = data.get("url", "")
                
                # 2. Compare Versions
                if float(latest) > float(CURRENT_VERSION):
                    self.found_update.emit(latest, url)
        except: pass

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

# --- WORKER ---
class ImageLoader(QThread):
    loaded = Signal(QPixmap, str)
    def __init__(self, source): super().__init__(); self.source = source
    def run(self):
        try:
            pix = QPixmap()
            if os.path.isfile(self.source): pix.load(self.source)
            else: 
                r = requests.get(self.source, headers=HEADERS, timeout=10)
                pix.loadFromData(r.content)
            if not pix.isNull(): self.loaded.emit(pix, self.source)
        except: pass

# --- WIDGET ---
class PinterestWidget(QWidget):
    def __init__(self, data):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        saved_url = data.get("url")
        if saved_url: self.url = saved_url
        elif os.path.exists(DEFAULT_IMG_PATH): self.url = DEFAULT_IMG_PATH
        else: self.url = "https://i.pinimg.com/1200x/e3/bf/36/e3bf36325fce44e12106bdc49549641e.jpg"

        self.img_offset = QPoint(data.get("ox", 0), data.get("oy", 0))
        self.zoom, self.opacity, self.border_style = data.get("zoom", 1.0), data.get("opacity", 1.0), data.get("border_style", 2)
        
        self.show_hints = data.get("show_hints", True)

        if "w" in data:
            self.resize(data.get("w"), data.get("h"))
        elif os.path.exists(self.url) and os.path.isfile(self.url):
            temp = QPixmap(self.url)
            if not temp.isNull():
                base_w = 250
                ratio = temp.height() / temp.width()
                self.resize(base_w, int(base_w * ratio))
            else: self.resize(220, 330)
        else: self.resize(220, 330)

        self.move(data.get("x", 200), data.get("y", 200))
        
        self.pixmap = None; self.is_editing = False
        self.dragging = self.resizing = self.panning = False
        
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(10, 100); self.slider.setValue(int(self.opacity*100)); self.slider.hide()
        self.slider.setStyleSheet("QSlider::groove:horizontal {height:4px; background:#555;} QSlider::handle:horizontal {background:white; width:14px; margin:-5px 0; border-radius:7px;}")
        self.slider.valueChanged.connect(lambda v: self.set_op(v/100.0))

        if os.path.isfile(self.url):
            self.pixmap = QPixmap(self.url)
            self.update()
        else:
            self.start_loading(self.url)
            
        self.set_interaction(False)

    def set_op(self, val): self.opacity = val; self.update()
    def start_loading(self, src): self.loader = ImageLoader(src); self.loader.loaded.connect(self.on_load); self.loader.start()
    def on_load(self, pix, url): self.pixmap = pix; self.url = url; self.update()

    def set_interaction(self, enable):
        self.is_editing = enable; self.slider.hide(); hwnd = int(self.winId())
        if enable:
            win32gui.SetParent(hwnd, 0); self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style & ~win32con.WS_EX_TRANSPARENT)
        else:
            win32gui.SetParent(hwnd, get_wallpaper_window()); self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style & ~win32con.WS_EX_TRANSPARENT)
        self.show()

    def paintEvent(self, event):
        if not self.pixmap: return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        pad = 20 if self.border_style == 2 else 5; rect = self.rect().adjusted(pad, pad, -pad, -pad)
        
        if self.border_style == 2:
            path = QPainterPath(); path.addRoundedRect(rect.adjusted(2,4,2,4), 30, 30)
            p.setOpacity(self.opacity*0.4); p.fillPath(path, QColor(0,0,0))

        p.setOpacity(self.opacity); path = QPainterPath(); path.addRoundedRect(rect, 30, 30)
        p.save(); p.setClipPath(path)
        scaled = self.pixmap.scaled(int(rect.width()*self.zoom), int(rect.height()*self.zoom), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        lx, ly = (scaled.width()-rect.width())//2, (scaled.height()-rect.height())//2
        self.img_offset.setX(max(-lx, min(lx, self.img_offset.x()))); self.img_offset.setY(max(-ly, min(ly, self.img_offset.y())))
        p.drawPixmap(rect.x()+(rect.width()-scaled.width())//2+self.img_offset.x(), rect.y()+(rect.height()-scaled.height())//2+self.img_offset.y(), scaled)
        p.restore()

        if self.border_style == 1: p.setPen(QPen(QColor(255,255,255,120), 2)); p.drawRoundedRect(rect, 30, 30)
        
        if self.is_editing:
            p.setPen(QPen(QColor(0,150,255), 2, Qt.DashLine)); p.drawRoundedRect(rect, 30, 30)
            p.setBrush(QColor(0,150,255)); p.drawEllipse(rect.bottomRight()-QPoint(10,10), 6, 6)
            self.slider.setGeometry(rect.x()+20, rect.bottom()-30, rect.width()-40, 20)
            if self.show_hints:
                p.setPen(QColor(255, 255, 255, 200))
                p.setFont(QFont("Arial", 10, QFont.Bold))
                p.drawText(rect, Qt.AlignCenter, "MOVE: Drag\nPAN: Shift+Drag\nRESIZE: ↘")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.last_pos = e.globalPosition().toPoint()
            if e.pos().x() > self.width()-60 and e.pos().y() > self.height()-60: self.resizing = True
            elif e.modifiers() == Qt.ShiftModifier: self.panning = True
            else: self.dragging = True
        elif e.button() == Qt.RightButton: self.show_menu(e.globalPosition().toPoint())
    def mouseMoveEvent(self, e):
        curr = e.globalPosition().toPoint(); delta = curr - self.last_pos
        if self.dragging: self.move(self.pos() + delta)
        elif self.resizing: self.resize(max(100, e.pos().x()), max(150, e.pos().y()))
        elif self.panning: self.img_offset += delta
        self.last_pos = curr; self.update()
    def mouseReleaseEvent(self, e): self.dragging=self.resizing=self.panning=False; save_layouts()
    def wheelEvent(self, e):
        if e.modifiers() == Qt.AltModifier: self.set_op(max(0.1, min(1.0, self.opacity + (0.05 if e.angleDelta().y()>0 else -0.05)))); self.slider.setValue(int(self.opacity*100))
        else: self.zoom = max(1.0, self.zoom + (0.1 if e.angleDelta().y()>0 else -0.1))
        self.update(); save_layouts()
    
    def show_menu(self, pos):
        m = QMenu(self); m.setStyleSheet(MENU_STYLE)
        src = m.addMenu("Source Image")
        src.addAction("Choose from Folder", self.local_src); src.addAction("Paste Web URL", self.web_src)
        hint_act = m.addAction("Hide Hints" if self.show_hints else "Show Hints")
        hint_act.triggered.connect(self.toggle_hints)
        m.addAction("Show/Hide Opacity Slider", lambda: self.slider.setVisible(not self.slider.isVisible()))
        m.addSeparator(); m.addAction(f"Style: {['Trans','Border','Shadow'][(self.border_style+1)%3]}", self.cycle_style)
        m.addSeparator(); m.addAction("Delete Widget", self.close_w); m.exec(pos)

    def toggle_hints(self):
        self.show_hints = not self.show_hints
        self.update(); save_layouts()

    def local_src(self): 
        f, _ = QFileDialog.getOpenFileName(self, "Image", "", "Img (*.png *.jpg)"); 
        if f: self.start_loading(f); save_layouts()
    def web_src(self): 
        u, k = QInputDialog.getText(self, "Input", "URL:", text=self.url); 
        if k and u: self.start_loading(u); save_layouts()
    def cycle_style(self): self.border_style = (self.border_style+1)%3; self.update(); save_layouts()
    def close_w(self): self.close(); app.widgets.remove(self); save_layouts()

def get_wallpaper_window():
    progman = win32gui.FindWindow("Progman", None)
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)
    res = []
    win32gui.EnumWindows(lambda h, r: r.append(h) if win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None) else None, res)
    return win32gui.FindWindowEx(0, res[0], "WorkerW", None) if res else None

class TrayApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.is_edit = False
        
        if os.path.exists(ICON_PATH): self.icon = QIcon(ICON_PATH)
        else:
            p = QPixmap(64,64); p.fill(Qt.transparent); pt = QPainter(p); pt.setRenderHint(QPainter.Antialiasing); pt.setBrush(QColor("#ff4757")); pt.setPen(Qt.NoPen); pt.drawEllipse(12,12,40,40); pt.end()
            self.icon = QIcon(p)
            
        self.tray = QSystemTrayIcon(self.icon)
        self.menu = QMenu(); self.menu.setStyleSheet(MENU_STYLE)
        
        # VERSION IN MENU
        self.menu.addAction(f"Version: {CURRENT_VERSION}").setEnabled(False)
        self.menu.addSeparator()

        self.act_edit = self.menu.addAction("EDIT LAYOUT"); self.act_edit.triggered.connect(self.toggle_edit)
        self.menu.addAction("ADD WIDGET", self.create_w)
        self.menu.addSeparator()
        self.act_start = self.menu.addAction("Run on Startup"); self.act_start.setCheckable(True); self.act_start.setChecked(self.chk_start()); self.act_start.triggered.connect(self.set_start)
        self.menu.addSeparator(); self.menu.addAction("EXIT", self.qt_app.quit)
        self.tray.setContextMenu(self.menu); self.tray.show()
        
        self.widgets = []
        self.load_init()
        if not os.path.exists(CONFIG_PATH): QTimer.singleShot(1000, self.show_welcome)

        # START AUTO UPDATE CHECK
        self.updater = UpdateChecker()
        self.updater.found_update.connect(self.prompt_update)
        self.updater.start()

    def prompt_update(self, new_ver, url):
        msg = QMessageBox()
        msg.setWindowTitle("Update Available")
        msg.setText(f"A new version ({new_ver}) is available!")
        msg.setInformativeText("Download and install now?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        if msg.exec() == QMessageBox.Yes:
            self.download_and_install(url)

    def download_and_install(self, url):
        try:
            # Download installer to Temp
            installer_name = url.split("/")[-1]
            temp_path = os.path.join(os.environ["TEMP"], installer_name)
            
            r = requests.get(url, stream=True)
            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            
            # Launch Installer
            os.startfile(temp_path)
            self.qt_app.quit()
        except: pass

    def show_welcome(self): self.welcome = WelcomeScreen(); self.welcome.show()
    def chk_start(self):
        try: k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ); winreg.QueryValueEx(k, APP_NAME); return True
        except: return False
    def set_start(self, s):
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if s: winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        else: 
            try: winreg.DeleteValue(k, APP_NAME)
            except: pass

    def toggle_edit(self):
        self.is_edit = not self.is_edit; self.act_edit.setText("FINISH & LOCK" if self.is_edit else "EDIT LAYOUT")
        for w in self.widgets: w.set_interaction(self.is_edit)
        if not self.is_edit: save_layouts()

    def create_w(self, data=None): w = PinterestWidget(data or {}); w.show(); self.widgets.append(w)
    def load_init(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    for d in json.load(f): self.create_w(d)
            except: self.create_w()
        else: self.create_w()

def save_layouts():
    data = [{"url": w.url, "x": w.x(), "y": w.y(), "w": w.width(), "h": w.height(), "ox": w.img_offset.x(), "oy": w.img_offset.y(), "zoom": w.zoom, "opacity": w.opacity, "border_style": w.border_style, "show_hints": w.show_hints} for w in app.widgets]
    with open(CONFIG_PATH, "w") as f: json.dump(data, f)

if __name__ == "__main__":
    app = TrayApp()
    sys.exit(app.qt_app.exec())
"""
Floating desktop indicator for Claude Code sessions.

One dot per active Claude Code session, all packed into a draggable rounded
panel that hovers on screen. Yellow pulsing = working, green = waiting for
input. Hover a dot for tooltip + label editor. Right-click a dot for menu.
Drag the panel anywhere on the panel (outside a dot) to move all dots.

State is read from state/<session_id>.json files written by cc_hook.py.
Config (labels keyed by cwd, panel position, autostart) persists in config.json.
"""
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve, Property, Signal,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QGuiApplication, QAction, QIcon, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QMenu,
    QSystemTrayIcon,
)

# ---------- paths & config ----------

ROOT = Path(__file__).parent
STATE_DIR = ROOT / "state"
CONFIG_FILE = ROOT / "config.json"

DOT_SIZE = 22
DOT_GAP = 6
PANEL_PAD_H = 12
PANEL_PAD_V = 7
PANEL_RADIUS = 12
ANCHOR_MARGIN = 12  # distance from screen edge when no saved position

DEFAULT_CONFIG = {
    "panel_pos": None,   # [x, y] absolute screen coords, or None = auto top-right
    "labels": {},        # cwd -> user label
    "autostart": False,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------- bubble (hover tooltip with label editor) ----------

class Bubble(QWidget):
    """Floating tooltip-style panel that appears below/next-to a dot."""
    label_changed = Signal(str, str)  # (cwd, new_label)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._cwd = ""

        root = QWidget(self)
        root.setObjectName("card")
        root.setStyleSheet("""
            QWidget#card {
                background: rgba(28, 30, 36, 235);
                border: 1px solid rgba(255,255,255,30);
                border-radius: 10px;
            }
            QLabel { color: #e6e6e6; }
            QLabel#title { font-weight: 600; font-size: 12px; }
            QLabel#meta  { color: #9aa0a6; font-size: 11px; }
            QLineEdit {
                background: rgba(255,255,255,18);
                border: 1px solid rgba(255,255,255,30);
                border-radius: 5px;
                color: #e6e6e6;
                padding: 3px 6px;
                font-size: 12px;
            }
        """)

        self.lbl_title  = QLabel(objectName="title")
        self.lbl_cwd    = QLabel(objectName="meta")
        self.lbl_state  = QLabel(objectName="meta")
        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("打个标签… (回车保存)")
        self.edit_label.returnPressed.connect(self._commit_label)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_cwd)
        lay.addWidget(self.lbl_state)
        lay.addWidget(self.edit_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        self.resize(260, 110)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._maybe_hide)
        self._hover_owner = None

    def show_for(self, dot, state, label):
        """Open / re-target the bubble. Resets the editor to the saved label
        — only call this on initial display (e.g. hover-enter), NOT on the
        periodic refresh, or you'll clobber what the user is typing."""
        self._cwd = state.get("cwd", "")
        self._hover_owner = dot

        self.edit_label.blockSignals(True)
        self.edit_label.setText(label or "")
        self.edit_label.blockSignals(False)

        self.refresh_meta(state, label)
        self._position_near(dot)
        self.show()
        self.raise_()

    def refresh_meta(self, state, label):
        """Update the read-only header text (title / cwd / status+duration).
        Does NOT touch the editor — safe to call while the user is typing,
        including while an IME is composing characters."""
        sid = state.get("session_id", "?")[:8]
        title = label or f"session {sid}"
        self.lbl_title.setText(title)
        self.lbl_cwd.setText(self._cwd or "(no cwd)")

        secs = max(0, int(time.time() - state.get("started", time.time())))
        status_zh = "等你输入" if state.get("status") == "waiting" else "正在做"
        self.lbl_state.setText(f"{status_zh} · {_fmt_dur(secs)} · {sid}")

    def _position_near(self, dot):
        top_left = dot.mapToGlobal(QPoint(0, 0))
        dot_rect = QRect(top_left, dot.size())

        screen = QGuiApplication.screenAt(dot_rect.center())
        sgeo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = dot_rect.right() - self.width()
        y = dot_rect.bottom() + 8
        x = max(sgeo.left() + 4, min(x, sgeo.right() - self.width() - 4))
        if y + self.height() > sgeo.bottom():
            y = dot_rect.top() - self.height() - 8
        self.move(x, y)

    def schedule_hide(self):
        self._hide_timer.start(280)

    def cancel_hide(self):
        self._hide_timer.stop()

    def _maybe_hide(self):
        if self.underMouse():
            return
        if self._hover_owner and self._hover_owner.underMouse():
            return
        self.hide()

    def enterEvent(self, ev):
        self.cancel_hide()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.schedule_hide()
        super().leaveEvent(ev)

    def _commit_label(self):
        text = self.edit_label.text().strip()
        if self._cwd:
            self.label_changed.emit(self._cwd, text)
        self.lbl_title.setText(text or f"session {self._cwd[-12:]}")


def _fmt_dur(s):
    if s < 60: return f"{s}s"
    if s < 3600: return f"{s//60}m{s%60:02d}s"
    return f"{s//3600}h{(s%3600)//60:02d}m"


# ---------- dot widget (child of PanelFrame) ----------

class Dot(QWidget):
    request_bubble = Signal(object)
    request_hide   = Signal(object)
    request_menu   = Signal(object, QPoint)

    def __init__(self, session_id, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self.state = {"status": "waiting", "cwd": "", "started": time.time()}
        self._pulse = 1.0

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(DOT_SIZE, DOT_SIZE)
        self.setCursor(Qt.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(1200)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.45)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

    def getPulse(self): return self._pulse
    def setPulse(self, v):
        self._pulse = v
        self.update()
    pulse = Property(float, getPulse, setPulse)

    def update_state(self, state):
        prev_status = self.state.get("status")
        self.state = state
        if state.get("status") == "working":
            if prev_status != "working":
                self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        status = self.state.get("status", "waiting")
        if status == "waiting":
            color = QColor(60, 200, 110)
        else:
            color = QColor(245, 190, 70)
            color.setAlphaF(self._pulse)

        halo = QColor(color)
        halo.setAlphaF(0.25 * (self._pulse if status == "working" else 1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(0, 0, DOT_SIZE, DOT_SIZE)

        inset = 4
        p.setBrush(color)
        p.drawEllipse(inset, inset, DOT_SIZE - 2*inset, DOT_SIZE - 2*inset)

        hi = QColor(255, 255, 255, 70)
        p.setBrush(hi)
        p.drawEllipse(inset + 2, inset + 1, (DOT_SIZE - 2*inset)//2, (DOT_SIZE - 2*inset)//2)

    def enterEvent(self, ev):
        self.request_bubble.emit(self)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.request_hide.emit(self)
        super().leaveEvent(ev)

    def contextMenuEvent(self, ev):
        self.request_menu.emit(self, ev.globalPos())


# ---------- dot slot (dot stacked above an optional persistent label) ----------

class DotSlot(QWidget):
    """Wraps a Dot with an optional label shown UNDERNEATH it.

    The dot itself receives mouse events directly (so hover-bubble and
    right-click still work). The label is mouse-transparent. Empty-space
    clicks inside the slot are forwarded to the panel so dragging works
    no matter where in the panel you grab — even on a label.
    """
    def __init__(self, dot, panel):
        super().__init__()
        self.dot = dot
        self._panel = panel

        self.lbl = QLabel("")
        self.lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.lbl.setStyleSheet(
            "color: #e6e6e6; font-size: 11px; padding: 0 2px;"
        )
        self.lbl.setMaximumWidth(140)
        # Reserve label-row height even when empty, so dots stay aligned
        # whether any given session has a label or not.
        self.lbl.setFixedHeight(14)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(dot, 0, Qt.AlignHCenter)
        lay.addWidget(self.lbl, 0, Qt.AlignHCenter)

    def set_label(self, text):
        # Keep the label widget visible; just swap the text. Don't hide/show,
        # since a hidden child would collapse the layout and misalign dots.
        self.lbl.setText((text or "").strip())

    # Forward drag events to the panel — these only fire when the click was
    # NOT on the Dot (Dot consumes its own events). Label is transparent, so
    # clicking the label lands here too.
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._panel.begin_drag(ev.globalPosition().toPoint())
            ev.accept()

    def mouseMoveEvent(self, ev):
        self._panel.continue_drag(ev.globalPosition().toPoint())
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._panel.end_drag()
            ev.accept()


# ---------- panel frame (draggable container for all dots) ----------

class PanelFrame(QWidget):
    def __init__(self, app):
        super().__init__()
        self._app = app
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.SizeAllCursor)

        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(PANEL_PAD_H, PANEL_PAD_V, PANEL_PAD_H, PANEL_PAD_V)
        self._lay.setSpacing(DOT_GAP)

        self._drag_global = None  # QPoint at press, in screen coords
        self._win_origin = None   # window topleft at press
        self._moved = False       # did we actually drag (vs just click)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        # rounded translucent dark background + faint border
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        p.setBrush(QColor(28, 30, 36, 185))
        p.drawRoundedRect(r, PANEL_RADIUS, PANEL_RADIUS)
        # drag handle hint on far-left (three little dots)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 110))
        cx = 6
        cy = self.height() // 2
        for dy in (-5, 0, 5):
            p.drawEllipse(QPoint(cx, cy + dy), 1, 1)

    def add_dot(self, dot):
        self._lay.addWidget(dot)
        self.adjustSize()

    def remove_dot(self, dot):
        self._lay.removeWidget(dot)
        dot.setParent(None)
        self.adjustSize()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.begin_drag(ev.globalPosition().toPoint())
            ev.accept()

    def mouseMoveEvent(self, ev):
        self.continue_drag(ev.globalPosition().toPoint())
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.end_drag()
            ev.accept()

    # Drag state — exposed so DotSlot (which may swallow clicks on its own
    # blank areas / label) can forward events here.
    def begin_drag(self, global_pos):
        self._drag_global = global_pos
        self._win_origin = self.frameGeometry().topLeft()
        self._moved = False

    def continue_drag(self, global_pos):
        if self._drag_global is None:
            return
        delta = global_pos - self._drag_global
        if abs(delta.x()) + abs(delta.y()) > 2:
            self._moved = True
        self.move(self._win_origin + delta)

    def end_drag(self):
        if self._drag_global is not None and self._moved:
            pos = self.pos()
            self._app.save_panel_pos(pos.x(), pos.y())
        self._drag_global = None
        self._win_origin = None
        self._moved = False

    def contextMenuEvent(self, ev):
        # Right-click on empty panel area: app-wide menu.
        self._app.show_panel_menu(ev.globalPos())


# ---------- main controller ----------

class App(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = load_config()
        self.dots = {}    # session_id -> Dot
        self.slots = {}   # session_id -> DotSlot

        self.panel = PanelFrame(self)
        self.bubble = Bubble()
        self.bubble.label_changed.connect(self._on_label_changed)

        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Claude Code Indicator")
        self._build_tray_menu()
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(800)
        self._refresh()

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._tick)
        self.tick.start(1000)

    # ----- panel position -----

    def save_panel_pos(self, x, y):
        self.cfg["panel_pos"] = [x, y]
        save_config(self.cfg)

    def _place_panel(self):
        """Position panel: saved coords if any, otherwise top-right corner.
        Keep it inside the screen bounds so it can't get stranded off-screen."""
        self.panel.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pos = self.cfg.get("panel_pos")
        if pos:
            x, y = int(pos[0]), int(pos[1])
        else:
            x = screen.right() - self.panel.width() - ANCHOR_MARGIN
            y = screen.top() + ANCHOR_MARGIN
        # Clamp to screen.
        x = max(screen.left(), min(x, screen.right() - self.panel.width()))
        y = max(screen.top(),  min(y, screen.bottom() - self.panel.height()))
        self.panel.move(x, y)

    # ----- tray -----

    def _tray_icon(self):
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 200, 110))
        p.drawEllipse(4, 4, 24, 24)
        p.end()
        return QIcon(pm)

    def _build_tray_menu(self):
        m = QMenu()

        a_reset_pos = QAction("重置位置 (贴右上角)", m)
        a_reset_pos.triggered.connect(self._reset_panel_pos)
        m.addAction(a_reset_pos)

        a_auto = QAction("开机自启", m, checkable=True)
        a_auto.setChecked(self.cfg.get("autostart", False))
        a_auto.toggled.connect(self._toggle_autostart)
        m.addAction(a_auto)

        a_reset_labels = QAction("清理所有标签", m)
        a_reset_labels.triggered.connect(self._reset_labels)
        m.addAction(a_reset_labels)

        m.addSeparator()
        a_quit = QAction("退出", m)
        a_quit.triggered.connect(self.quit)
        m.addAction(a_quit)

        self.tray.setContextMenu(m)
        self._tray_menu = m  # keep alive

    def show_panel_menu(self, global_pos):
        # Reuse the tray menu for panel right-click.
        self._tray_menu.exec(global_pos)

    def _reset_panel_pos(self):
        self.cfg["panel_pos"] = None
        save_config(self.cfg)
        self._place_panel()

    # ----- state polling -----

    def _refresh(self):
        seen = set()
        for f in STATE_DIR.glob("*.json"):
            try:
                state = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                # Empty or malformed file. If it's old enough to not be a
                # mid-write race, drop it so it stops cluttering the dir.
                try:
                    if time.time() - f.stat().st_mtime > 30:
                        f.unlink()
                except Exception:
                    pass
                continue
            sid = state.get("session_id") or f.stem
            seen.add(sid)

            age = time.time() - state.get("updated", 0)
            if age > 3600:
                try: f.unlink()
                except Exception: pass
                continue

            if sid not in self.dots:
                dot = Dot(sid)
                slot = DotSlot(dot, self.panel)
                dot.request_bubble.connect(self._show_bubble_for)
                dot.request_hide.connect(self._maybe_hide_bubble)
                dot.request_menu.connect(self._dot_menu)
                self.dots[sid] = dot
                self.slots[sid] = slot
                self.panel.add_dot(slot)

            self.dots[sid].update_state(state)
            self.slots[sid].set_label(self._label_for(state.get("cwd", "")))

        # Drop dots whose files disappeared.
        for sid in list(self.dots):
            if sid not in seen:
                self.panel.remove_dot(self.slots[sid])
                self.slots[sid].deleteLater()
                del self.dots[sid]
                del self.slots[sid]

        if self.dots:
            self._place_panel()
            if not self.panel.isVisible():
                self.panel.show()
        else:
            if self.panel.isVisible():
                self.panel.hide()

    def _tick(self):
        if self.bubble.isVisible() and self.bubble._hover_owner in self.dots.values():
            dot = self.bubble._hover_owner
            # Refresh ONLY the read-only meta line (duration ticks every
            # second) — don't reset the editor or we'd kill in-progress input.
            self.bubble.refresh_meta(dot.state, self._label_for(dot.state.get("cwd", "")))

    # ----- bubble plumbing -----

    def _label_for(self, cwd):
        return self.cfg.get("labels", {}).get(cwd, "")

    def _show_bubble_for(self, dot):
        self.bubble.cancel_hide()
        self.bubble.show_for(dot, dot.state, self._label_for(dot.state.get("cwd", "")))

    def _maybe_hide_bubble(self, _dot):
        self.bubble.schedule_hide()

    def _on_label_changed(self, cwd, label):
        labels = dict(self.cfg.get("labels", {}))
        if label:
            labels[cwd] = label
        else:
            labels.pop(cwd, None)
        self.cfg["labels"] = labels
        save_config(self.cfg)
        # Update any slot whose dot belongs to this cwd, then resize panel.
        for sid, dot in self.dots.items():
            if dot.state.get("cwd") == cwd:
                self.slots[sid].set_label(label)
        self.panel.adjustSize()
        self._place_panel()

    # ----- per-dot context menu -----

    def _dot_menu(self, dot, global_pos):
        m = QMenu()
        sid = dot.session_id[:8]
        a_head = QAction(f"会话 {sid}", m); a_head.setEnabled(False)
        m.addAction(a_head)
        m.addSeparator()

        a_label = QAction("编辑标签…", m)
        a_label.triggered.connect(lambda: (self._show_bubble_for(dot),
                                           self.bubble.edit_label.setFocus(),
                                           self.bubble.edit_label.selectAll()))
        m.addAction(a_label)

        a_copy = QAction("复制 session id", m)
        a_copy.triggered.connect(lambda: QApplication.clipboard().setText(dot.session_id))
        m.addAction(a_copy)

        a_dismiss = QAction("从面板移除", m)
        a_dismiss.triggered.connect(lambda: self._dismiss(dot.session_id))
        m.addAction(a_dismiss)

        m.exec(global_pos)

    def _dismiss(self, sid):
        f = STATE_DIR / f"{sid}.json"
        try: f.unlink()
        except Exception: pass
        self._refresh()

    # ----- settings -----

    def _toggle_autostart(self, on):
        self.cfg["autostart"] = on
        save_config(self.cfg)
        try:
            _set_autostart(on)
        except Exception as e:
            self.tray.showMessage("开机自启", f"设置失败：{e}", QSystemTrayIcon.Warning)

    def _reset_labels(self):
        self.cfg["labels"] = {}
        save_config(self.cfg)
        for slot in self.slots.values():
            slot.set_label("")
        self.panel.adjustSize()
        self._place_panel()


def _set_autostart(enable):
    """Write/remove a shortcut in the user's Startup folder."""
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    lnk = startup / "CC Indicator.lnk"
    if not enable:
        if lnk.exists():
            lnk.unlink()
        return
    target = ROOT / "start.bat"
    vbs = f'''
Set s = CreateObject("WScript.Shell")
Set lnk = s.CreateShortcut("{lnk}")
lnk.TargetPath = "{target}"
lnk.WorkingDirectory = "{ROOT}"
lnk.WindowStyle = 7
lnk.Save
'''
    tmp = ROOT / "_mklink.vbs"
    tmp.write_text(vbs, encoding="utf-8")
    os.system(f'cscript //nologo "{tmp}"')
    try: tmp.unlink()
    except Exception: pass


def main():
    app = App(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

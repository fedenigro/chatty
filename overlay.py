"""
Floating recording HUD — bottom-centre of the active screen.

  • Click ✕  (right, outline)  → cancel  — discard audio, no transcription
  • Click ✓  (right, filled)   → confirm — transcribe and paste
  • Drag anywhere              → reposition freely
Must be shown/hidden on the main thread.
"""

import math
import os
import time

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSCursor,
    NSEvent,
    NSImage,
    NSMakePoint,
    NSMakeRect,
    NSScreen,
    NSTimer,
    NSTrackingArea,
    NSView,
    NSWindow,
)
from Foundation import NSObject

_DIR = os.path.dirname(os.path.abspath(__file__))
_MIC = os.path.join(_DIR, "assets", "mic_on.png")

# ── Colours ────────────────────────────────────────────────────────────────────
_BG        = (0.14, 0.14, 0.14, 0.93)
_BG_HOVER  = (0.20, 0.20, 0.20, 0.97)
_GREEN     = (0.176, 0.718, 0.514, 1.0)   # #2DB783 — bars + checkmark stroke

# ── Pill geometry ──────────────────────────────────────────────────────────────
_H        = 64
_CORNER   = _H / 2

_ICON_SIZE    = 38.0
_ICON_X       = 13.0
_ICON_GAP     = 14.0

_NUM_BARS     = 10
_BAR_W        = 8.0
_BAR_GAP      = 10.0
_BAR_MIN_H    = 4.0
_BAR_MAX_H    = 32.0
_BAR_START_X  = _ICON_X + _ICON_SIZE + _ICON_GAP          # 65
_BARS_END_X   = _BAR_START_X + _NUM_BARS * _BAR_W + (_NUM_BARS - 1) * _BAR_GAP  # 235

# ── Button geometry (right of bars) ───────────────────────────────────────────
_BTN_R        = 14.0                                       # button radius
_BTN_CY       = _H / 2                                     # vertically centred
_DIVIDER_X    = _BARS_END_X + 14                           # 249 — thin separator
_CANCEL_CX    = _DIVIDER_X + 12 + _BTN_R                  # 275 — X button centre
_CONFIRM_CX   = _CANCEL_CX + _BTN_R * 2 + 10              # 313 — ✓ button centre
_PAD_RIGHT    = 14
_W            = _CONFIRM_CX + _BTN_R + _PAD_RIGHT          # 341

# ── Animation ─────────────────────────────────────────────────────────────────
_SMOOTH    = 0.25
_FPS       = 30.0
_WIN_LEVEL = 26   # above NSStatusBarWindowLevel (25)

_FREQS  = [1.1, 2.3, 1.7, 2.9, 1.4, 2.1, 1.8, 2.6, 1.3, 2.4]
_PHASES = [i * 0.65 for i in range(_NUM_BARS)]

_DRAG_THRESHOLD = 4.0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _in_circle(px, py, cx, cy, r):
    return (px - cx) ** 2 + (py - cy) ** 2 <= r ** 2


# ── NSView ─────────────────────────────────────────────────────────────────────

class _WaveformView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._bars        = [0.0] * _NUM_BARS
        self._level       = 0.0
        self._hovered     = False
        self._mic         = NSImage.alloc().initWithContentsOfFile_(_MIC)
        self.confirm_cb   = None
        self.cancel_cb    = None
        self._click_offset = None
        self._down_screen  = None
        return self

    # ── drawing ───────────────────────────────────────────────────────────────

    def isOpaque(self):
        return False

    def drawRect_(self, _rect):
        bounds = self.bounds()
        h = bounds.size.height

        # clear
        NSColor.clearColor().set()
        NSBezierPath.fillRect_(bounds)

        # pill background
        bg = _BG_HOVER if self._hovered else _BG
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*bg).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, _CORNER, _CORNER
        ).fill()

        # mic icon
        if self._mic:
            icon_y = (h - _ICON_SIZE) / 2
            self._mic.drawInRect_(NSMakeRect(_ICON_X, icon_y, _ICON_SIZE, _ICON_SIZE))

        # waveform bars
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*_GREEN).setFill()
        bw2 = _BAR_W / 2
        for i, v in enumerate(self._bars):
            bar_h = _BAR_MIN_H + (_BAR_MAX_H - _BAR_MIN_H) * v
            x = _BAR_START_X + i * (_BAR_W + _BAR_GAP)
            y = (h - bar_h) / 2
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, _BAR_W, bar_h), bw2, bw2
            ).fill()

        # thin divider
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.18).setFill()
        div_h = 34.0
        NSBezierPath.fillRect_(NSMakeRect(_DIVIDER_X, (h - div_h) / 2, 1, div_h))

        # ── Cancel button  ✕  (outline circle + X, white, secondary) ──────────
        self._draw_cancel_btn()

        # ── Confirm button  ✓  (filled circle + checkmark, primary) ───────────
        self._draw_confirm_btn()

    def _draw_cancel_btn(self):
        cx, cy, r = _CANCEL_CX, _BTN_CY, _BTN_R

        # circle outline
        circle = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - r, cy - r, r * 2, r * 2)
        )
        circle.setLineWidth_(1.8)
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.75).setStroke()
        circle.stroke()

        # X lines
        off = r * 0.33
        x_path = NSBezierPath.bezierPath()
        x_path.moveToPoint_(NSMakePoint(cx - off, cy - off))
        x_path.lineToPoint_(NSMakePoint(cx + off, cy + off))
        x_path.moveToPoint_(NSMakePoint(cx + off, cy - off))
        x_path.lineToPoint_(NSMakePoint(cx - off, cy + off))
        x_path.setLineWidth_(1.8)
        x_path.setLineCapStyle_(1)   # NSRoundLineCapStyle
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.75).setStroke()
        x_path.stroke()

    def _draw_confirm_btn(self):
        cx, cy, r = _CONFIRM_CX, _BTN_CY, _BTN_R

        # filled white circle
        circle = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - r, cy - r, r * 2, r * 2)
        )
        NSColor.whiteColor().setFill()
        circle.fill()

        # green checkmark inside
        s = r * 0.52
        check = NSBezierPath.bezierPath()
        check.moveToPoint_(NSMakePoint(cx - s * 0.95, cy - s * 0.05))
        check.lineToPoint_(NSMakePoint(cx - s * 0.22, cy - s * 0.80))
        check.lineToPoint_(NSMakePoint(cx + s * 0.95, cy + s * 0.72))
        check.setLineWidth_(2.3)
        check.setLineCapStyle_(1)   # NSRoundLineCapStyle
        check.setLineJoinStyle_(1)  # NSRoundLineJoinStyle
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*_GREEN).setStroke()
        check.stroke()

    # ── cursor ────────────────────────────────────────────────────────────────

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.pointingHandCursor())

    # ── hover tracking ────────────────────────────────────────────────────────

    def mouseEntered_(self, _event):
        self._hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, _event):
        self._hovered = False
        self.setNeedsDisplay_(True)

    def updateTrackingAreas(self):
        objc.super(_WaveformView, self).updateTrackingAreas()
        for area in self.trackingAreas():
            self.removeTrackingArea_(area)
        opts = (
            0x01 |  # NSTrackingMouseEnteredAndExited
            0x20    # NSTrackingActiveAlways
        )
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None
        )
        self.addTrackingArea_(area)

    # ── mouse — click to act, drag to move ────────────────────────────────────

    def mouseDown_(self, event):
        win    = self.window()
        loc    = event.locationInWindow()
        origin = win.frame().origin
        self._click_offset = loc
        self._down_screen  = (origin.x + loc.x, origin.y + loc.y)

    def mouseDragged_(self, event):
        if self._click_offset is None:
            return
        win    = self.window()
        loc    = event.locationInWindow()
        origin = win.frame().origin
        screen_x = origin.x + loc.x
        screen_y = origin.y + loc.y
        win.setFrameOrigin_(NSMakePoint(
            screen_x - self._click_offset.x,
            screen_y - self._click_offset.y,
        ))

    def mouseUp_(self, event):
        if self._down_screen is not None:
            win    = self.window()
            loc    = event.locationInWindow()
            origin = win.frame().origin
            up_x   = origin.x + loc.x
            up_y   = origin.y + loc.y
            dx     = up_x - self._down_screen[0]
            dy     = up_y - self._down_screen[1]

            if abs(dx) < _DRAG_THRESHOLD and abs(dy) < _DRAG_THRESHOLD:
                # It was a tap — decide action by where the user tapped
                tap_x = loc.x   # view-local x
                tap_y = loc.y   # view-local y (y-up)

                if _in_circle(tap_x, tap_y, _CANCEL_CX, _BTN_CY, _BTN_R + 6):
                    if self.cancel_cb:
                        self.cancel_cb()
                elif _in_circle(tap_x, tap_y, _CONFIRM_CX, _BTN_CY, _BTN_R + 6):
                    if self.confirm_cb:
                        self.confirm_cb()
                else:
                    # tap on bars / mic area → confirm (same as ✓)
                    if self.confirm_cb:
                        self.confirm_cb()

        self._click_offset = None
        self._down_screen  = None


# ── Ticker ─────────────────────────────────────────────────────────────────────

class _Ticker(NSObject):
    def initWithView_(self, view):
        self = objc.super(_Ticker, self).init()
        if self is None:
            return None
        self._view = view
        return self

    def tick_(self, _timer):
        v     = self._view
        level = v._level
        t     = time.monotonic()
        for i in range(_NUM_BARS):
            osc    = 0.5 + 0.5 * math.sin(2 * math.pi * _FREQS[i] * t + _PHASES[i])
            target = min(1.0, level * (0.2 + 0.8 * osc) * 2.6 + 0.08 * osc)
            v._bars[i] = _SMOOTH * target + (1.0 - _SMOOTH) * v._bars[i]
        v.setNeedsDisplay_(True)


# ── Screen helper ──────────────────────────────────────────────────────────────

def _active_screen():
    pt = NSEvent.mouseLocation()
    for s in NSScreen.screens():
        f = s.frame()
        if (f.origin.x <= pt.x < f.origin.x + f.size.width and
                f.origin.y <= pt.y < f.origin.y + f.size.height):
            return s
    return NSScreen.mainScreen()


# ── Public API ─────────────────────────────────────────────────────────────────

class RecordingOverlay:
    """
    Floating HUD shown while recording.
      ✕  (outline)  → cancel_callback  — stop + discard
      ✓  (filled)   → confirm_callback — stop + transcribe
      drag           → freely reposition
    show() / hide() must run on the main thread.
    """

    def __init__(self, recorder, confirm_callback, cancel_callback):
        self._recorder    = recorder
        self._confirm_cb  = confirm_callback
        self._cancel_cb   = cancel_callback
        self._window      = None
        self._view        = None
        self._ticker      = None
        self._timer       = None

    def show(self):
        if self._window:
            return

        screen = _active_screen()
        sf     = screen.frame()
        x      = sf.origin.x + (sf.size.width - _W) / 2
        y      = sf.origin.y + 32

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, _W, _H),
            0,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(_WIN_LEVEL)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setOpaque_(False)
        self._window.setHasShadow_(True)
        self._window.setAcceptsMouseMovedEvents_(True)
        self._window.setCollectionBehavior_(
            (1 << 3) |   # NSWindowCollectionBehaviorCanJoinAllSpaces
            (1 << 9)     # NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        self._view             = _WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, _W, _H))
        self._view.confirm_cb  = self._confirm_cb
        self._view.cancel_cb   = self._cancel_cb
        self._window.setContentView_(self._view)
        self._window.orderFrontRegardless()

        self._ticker = _Ticker.alloc().initWithView_(self._view)
        self._timer  = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / _FPS, self._ticker, "tick:", None, True
        )

    def hide(self):
        if self._timer:
            self._timer.invalidate()
            self._timer = None
        self._ticker = None
        if self._window:
            self._window.orderOut_(None)
            self._window = None
        self._view = None

    def update_level(self):
        if self._view:
            self._view._level = self._recorder.current_level

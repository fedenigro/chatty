import time

import pyperclip
from Cocoa import NSEvent
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

# Virtual key code for 'v'
_KEY_V = 0x09


def paste_text(text: str) -> None:
    """Copy text to clipboard and paste it into the currently focused field."""
    pyperclip.copy(text)
    time.sleep(0.05)  # small delay so clipboard is ready
    _cmd_v()


def _cmd_v() -> None:
    """Send Cmd+V via CGEvent (works system-wide, no Accessibility UI blocking)."""
    key_down = CGEventCreateKeyboardEvent(None, _KEY_V, True)
    key_up = CGEventCreateKeyboardEvent(None, _KEY_V, False)
    CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
    CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, key_down)
    CGEventPost(kCGHIDEventTap, key_up)

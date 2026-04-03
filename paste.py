import time

import pyperclip
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)
from ApplicationServices import AXIsProcessTrusted

# Virtual key code for 'v'
_KEY_V = 0x09


def paste_text(text: str) -> None:
    """Copy text to clipboard, then paste it into the currently focused field."""
    pyperclip.copy(text)
    time.sleep(0.15)   # let clipboard settle + previous app regain focus
    if AXIsProcessTrusted():
        _cmd_v()
    # If not trusted, text is still in the clipboard — user can Cmd+V manually.
    # The status bar will show "Pasted:" because the text is ready to paste.


def _cmd_v() -> None:
    """Send Cmd+V via CGEvent at the session level."""
    key_down = CGEventCreateKeyboardEvent(None, _KEY_V, True)
    key_up   = CGEventCreateKeyboardEvent(None, _KEY_V, False)
    CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
    CGEventSetFlags(key_up,   kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, key_down)
    CGEventPost(kCGHIDEventTap, key_up)

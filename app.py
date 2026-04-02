#!/usr/bin/env python3
"""
Chatty — macOS menu bar dictation app.

Press the configured shortcut (default: Cmd+Shift+Space) to start/stop recording.
Transcribed text is pasted into the currently focused field.

First run:
    brew install ffmpeg
    pip install -r requirements.txt
    python app.py
Then grant Accessibility + Microphone permissions when prompted.
"""

import os
import threading
import time

import rumps

import config
import paste
from overlay import RecordingOverlay
from recorder import Recorder
from transcriber import AVAILABLE_MODELS, Transcriber

_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_IDLE      = os.path.join(_DIR, "assets", "mic_off.png")
ICON_RECORDING = os.path.join(_DIR, "assets", "mic_on.png")


class ChattyApp(rumps.App):
    def __init__(self, cfg: dict):
        super().__init__("Chatty", icon=ICON_IDLE, template=True, quit_button=None)
        self.cfg = cfg

        self.recorder    = Recorder()
        self.transcriber = Transcriber(cfg["model"])
        self.overlay     = RecordingOverlay(
            self.recorder,
            confirm_callback=self._stop_recording,
            cancel_callback=self._cancel_recording,
        )

        # Flags set from any thread; acted on by the main-thread poll timer
        self._want_show_overlay = False
        self._want_hide_overlay = False

        # Poll timer: runs on the main thread at ~30 fps.
        # Used to (a) show/hide the overlay safely and (b) push audio level.
        self._poll = rumps.Timer(self._main_thread_tick, 1 / 30)
        self._poll.start()

        # --- menu items ---
        self.toggle_item = rumps.MenuItem("Start Recording", callback=self.toggle)
        self.status_item = rumps.MenuItem("Status: Idle")
        self.status_item.set_callback(None)

        settings_menu = rumps.MenuItem("Settings")

        shortcut_display = self._fmt_hotkey(cfg["hotkey"])
        self.shortcut_item = rumps.MenuItem(
            f"Keyboard Shortcut: {shortcut_display}",
            callback=self._change_shortcut,
        )

        # Keep direct references — avoids fragile nested menu navigation
        self._model_items: dict[str, rumps.MenuItem] = {}
        model_menu = rumps.MenuItem("Whisper Model")
        for m in AVAILABLE_MODELS:
            item = rumps.MenuItem(
                f"✓  {m}" if m == cfg["model"] else m,
                callback=self._make_model_cb(m),
            )
            model_menu.add(item)
            self._model_items[m] = item

        settings_menu.add(self.shortcut_item)
        settings_menu.add(model_menu)

        self.menu = [
            self.toggle_item,
            None,
            self.status_item,
            None,
            settings_menu,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        # Load Whisper model in background
        threading.Thread(target=self._load_model, daemon=True).start()

        # Start global hotkey listener
        self._hotkey_stop   = threading.Event()
        self._hotkey_thread = None
        self._start_hotkey_listener(self.cfg["hotkey"])

    # ------------------------------------------------------------------
    # Main-thread poll tick (safe for all Cocoa/overlay operations)
    # ------------------------------------------------------------------

    def _main_thread_tick(self, _timer):
        if self._want_show_overlay:
            self._want_show_overlay = False
            self.overlay.show()
        if self._want_hide_overlay:
            self._want_hide_overlay = False
            self.overlay.hide()
        # Keep the level in the view fresh while recording
        if self.recorder.is_recording:
            self.overlay.update_level()

    # ------------------------------------------------------------------
    # Hotkey listener
    # ------------------------------------------------------------------

    def _start_hotkey_listener(self, hotkey: str):
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_stop.set()
            self._hotkey_thread.join(timeout=2)
            self._hotkey_stop.clear()

        def run():
            from pynput import keyboard
            with keyboard.GlobalHotKeys({hotkey: self._on_hotkey}):
                while not self._hotkey_stop.is_set():
                    time.sleep(0.5)

        self._hotkey_thread = threading.Thread(target=run, daemon=True)
        self._hotkey_thread.start()

    def _on_hotkey(self):
        self.toggle(None)

    # ------------------------------------------------------------------
    # Recording toggle
    # ------------------------------------------------------------------

    @rumps.clicked("Start Recording")
    def toggle(self, _):
        if self.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.icon = ICON_RECORDING
        self.template = False   # keep green colour on recording icon
        self.toggle_item.title = "Stop Recording"
        self._set_status("Recording…")
        self.recorder.start()
        self._want_show_overlay = True

    def _stop_recording(self):
        """Confirm — stop, transcribe, paste."""
        self.icon = ICON_IDLE
        self.template = True    # back to adaptive template icon
        self.toggle_item.title = "Start Recording"
        self._set_status("Transcribing…")
        self._want_hide_overlay = True
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _cancel_recording(self):
        """Cancel — stop and discard audio, no transcription."""
        self.icon = ICON_IDLE
        self.template = True
        self.toggle_item.title = "Start Recording"
        self._set_status("Cancelled.")
        self._want_hide_overlay = True
        threading.Thread(target=self.recorder.stop, daemon=True).start()

    def _transcribe(self):
        audio_buf = self.recorder.stop()
        if audio_buf is None:
            self._set_status("No audio captured.")
            return

        try:
            text = self.transcriber.transcribe(audio_buf, self.cfg.get("language"))
        except Exception as exc:
            self._set_status(f"Error: {exc}")
            return

        if text:
            paste.paste_text(text)
            self._set_status(f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}")
        else:
            self._set_status("Nothing transcribed.")

    # ------------------------------------------------------------------
    # Settings — keyboard shortcut
    # ------------------------------------------------------------------

    def _change_shortcut(self, _):
        from AppKit import NSApp
        current = self.cfg["hotkey"]
        window = rumps.Window(
            message=(
                "Enter a new keyboard shortcut in pynput format.\n\n"
                "Examples:\n"
                "  <cmd>+<shift>+<space>\n"
                "  <ctrl>+<alt>+d\n"
                "  <cmd>+<shift>+r\n\n"
                f"Current: {current}"
            ),
            title="Change Keyboard Shortcut",
            default_text=current,
            ok="Save",
            cancel="Cancel",
            dimensions=(340, 24),
        )
        # Bring the app forward so the dialog is visible
        NSApp.activateIgnoringOtherApps_(True)
        response = window.run()
        if response.clicked == 1 and response.text.strip():
            new_hotkey = response.text.strip()
            self.cfg["hotkey"] = new_hotkey
            config.save(self.cfg)
            self._start_hotkey_listener(new_hotkey)
            self.shortcut_item.title = f"Keyboard Shortcut: {self._fmt_hotkey(new_hotkey)}"
            self._set_status("Shortcut updated.")

    # ------------------------------------------------------------------
    # Settings — Whisper model
    # ------------------------------------------------------------------

    def _make_model_cb(self, model_name: str):
        def cb(_):
            self.cfg["model"] = model_name
            config.save(self.cfg)
            self._set_status(f"Loading {model_name} model…")
            threading.Thread(
                target=lambda: self._reload_model(model_name), daemon=True
            ).start()
            # Update checkmarks via direct references — no menu tree navigation
            for name, item in self._model_items.items():
                item.title = f"✓  {name}" if name == model_name else name
        return cb

    def _load_model(self):
        self._set_status(f"Loading {self.cfg['model']} model…")
        self.transcriber.load()
        self._set_status("Ready.")

    def _reload_model(self, model_name: str):
        self.transcriber.reload(model_name)
        self._set_status("Ready.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.status_item.title = f"Status: {msg}"

    @staticmethod
    def _fmt_hotkey(hotkey: str) -> str:
        return hotkey.replace("<", "").replace(">", "").replace("+", " + ")


def main():
    cfg = config.load()
    app = ChattyApp(cfg)
    app.run()


if __name__ == "__main__":
    main()

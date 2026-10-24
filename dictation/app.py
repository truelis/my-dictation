"""Menu bar app: hold the hotkey, speak, release, and the cleaned-up text is pasted."""

from __future__ import annotations

import queue
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import rumps

from dictation import audio, config, macos, setup
from dictation.groq_api import GroqClient, GroqError, ModelUnavailable, pick_cleanup_model
from dictation.setup import log

ICONS = {"idle": "🎙", "recording": "🔴", "working": "⏳"}
STATUS = {
    "idle": "Hold {key} to dictate",
    "recording": "Listening…",
    "working": "Transcribing…",
}
KEY_NAMES = {
    "right_option": "Right Option ⌥",
    "right_command": "Right Command ⌘",
    "right_control": "Right Control ⌃",
    "fn": "Fn",
}
# Holds shorter than this are treated as accidental taps.
MIN_SECONDS = 0.3


class DictationApp(rumps.App):
    def __init__(self, settings: config.Config):
        super().__init__("My Dictation", title=ICONS["idle"], quit_button="Quit")
        self.config = settings
        self.recorder = audio.Recorder()
        # One worker thread runs recording, uploads and API calls in order, off the main thread.
        self.worker = ThreadPoolExecutor(max_workers=1)
        # The worker hands results back here; the main thread does all UI and pasting.
        self.results: queue.Queue = queue.Queue()
        self.state = "idle"
        self.pressed_at = 0.0
        self.last_text = ""
        self.restore = None  # (when, previous clipboard text)

        self.status_item = rumps.MenuItem("")
        self.copy_item = rumps.MenuItem("Copy last dictation", callback=self.copy_last)
        self.cleanup_item = rumps.MenuItem("AI cleanup", callback=self.toggle_cleanup)
        self.cleanup_item.state = self.config.cleanup_enabled
        self.hotkey_menu = rumps.MenuItem("Hotkey")
        for key, name in KEY_NAMES.items():
            item = rumps.MenuItem(name, callback=self.choose_hotkey)
            item.key_name = key
            item.state = key == self.config.hotkey
            self.hotkey_menu.add(item)
        self.menu = [
            self.status_item,
            None,
            self.copy_item,
            self.cleanup_item,
            self.hotkey_menu,
            rumps.MenuItem("Set Groq API key…", callback=self.ask_api_key),
            rumps.MenuItem("Open settings file", callback=self.open_settings),
            None,
        ]
        self.set_state("idle")

        key_code, flag_mask = self.config.hotkey_spec()
        self.listener = macos.HoldKeyListener(
            key_code, flag_mask, self.on_press, self.on_release, self.on_cancel
        )
        # Keep a reference: rumps only holds timers weakly.
        self.tick_timer = rumps.Timer(self.tick, 0.05)
        self.tick_timer.start()

    # --- menu ---------------------------------------------------------------

    def ask_api_key(self, _):
        macos.bring_to_front()
        window = rumps.Window(
            message="Paste your Groq API key. Get one free at console.groq.com/keys.",
            title="Groq API key",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(320, 24),
            secure=True,
        )
        response = window.run()
        if response.clicked and response.text.strip():
            self.config.groq_api_key = response.text.strip()
            config.save(self.config)
            log("Saved the new Groq API key.")

    def open_settings(self, _):
        config.save(self.config)
        subprocess.run(["open", "-t", str(config.CONFIG_PATH)])

    def toggle_cleanup(self, item):
        item.state = not item.state
        self.config.cleanup_enabled = bool(item.state)
        config.save(self.config)

    def choose_hotkey(self, item):
        for other in self.hotkey_menu.values():
            other.state = other is item
        self.config.hotkey = item.key_name
        config.save(self.config)
        self.listener.key_code, self.listener.flag_mask = self.config.hotkey_spec()
        self.set_state(self.state)

    def copy_last(self, _):
        if self.last_text:
            macos.set_clipboard(self.last_text)

    def set_state(self, state):
        self.state = state
        self.title = ICONS[state]
        self.status_item.title = STATUS[state].format(key=KEY_NAMES[self.config.hotkey])

    # --- hold-to-talk (called on the main thread by the key listener) --------

    def on_press(self):
        if self.state != "idle":
            return
        self.pressed_at = time.monotonic()
        self.set_state("recording")
        self.sound("Tink")
        log("Listening…")
        self.worker.submit(self.start_recording)

    def on_release(self):
        if self.state != "recording":
            return
        held = time.monotonic() - self.pressed_at
        self.set_state("working")
        self.sound("Pop")
        self.worker.submit(self.finish_recording, held)

    def on_cancel(self):
        if self.state != "recording":
            return
        self.set_state("idle")
        log("Cancelled (another key was pressed).")
        self.worker.submit(self.recorder.stop)

    def sound(self, name):
        if self.config.play_sounds:
            macos.play(name)

    # --- worker thread ------------------------------------------------------

    def start_recording(self):
        try:
            self.recorder.start()
        except Exception as e:  # e.g. no microphone permission
            self.results.put(("error", f"Could not start the microphone: {e}"))

    def finish_recording(self, held):
        try:
            self.results.put(self.process(held))
        except Exception as e:
            # Never leave the app stuck on ⏳.
            self.results.put(("error", f"Unexpected error: {e!r}"))

    def process(self, held):
        samples = self.recorder.stop()
        if held < MIN_SECONDS:
            log("Too short, ignored. Hold the key while you speak.")
            return ("done", None)
        if samples.size and not samples.any():
            return ("error", "The microphone only gave silence. " + setup.MICROPHONE_HINT)
        if audio.is_silent(samples):
            log("Didn't hear anything, ignored.")
            return ("done", None)
        log(f"Transcribing {len(samples) / audio.SAMPLE_RATE:.1f}s of audio…")
        try:
            client = GroqClient(self.config.api_key())
            text = client.transcribe(
                audio.to_wav(samples),
                self.config.transcription_model,
                self.config.language,
                self.config.vocabulary,
            )
        except GroqError as e:
            return ("error", str(e))
        log(f"Heard: {text}")
        if text and self.config.cleanup_enabled:
            try:
                text = self.clean_up(client, text)
                log(f"Cleaned: {text}")
            except GroqError as e:
                # Still paste the raw transcript; it's better than losing what was said.
                self.results.put(("warning", f"AI cleanup failed, pasted the raw text. {e}"))
        return ("paste", text)

    def clean_up(self, client, text):
        try:
            return client.clean_up(text, self.config.cleanup_model, self.config.vocabulary)
        except ModelUnavailable:
            # Groq retires models from time to time; switch to one that's available now.
            replacement = pick_cleanup_model(client.list_models())
            if not replacement or replacement == self.config.cleanup_model:
                raise
            log(f"Cleanup model {self.config.cleanup_model} is no longer available, switching to {replacement}.")
            self.config.cleanup_model = replacement
            config.save(self.config)
            return client.clean_up(text, replacement, self.config.vocabulary)

    # --- main thread --------------------------------------------------------

    def tick(self, _):
        if self.restore and time.monotonic() >= self.restore[0]:
            macos.set_clipboard(self.restore[1])
            self.restore = None
        while True:
            try:
                kind, value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "paste":
                self.paste(value)
                self.set_state("idle")
            elif kind == "done":
                self.set_state("idle")
            elif kind == "error":
                self.set_state("idle")
                self.notify(value, error=True)
            elif kind == "warning":
                self.notify(value)

    def notify(self, message, error=False):
        log(("Error: " if error else "Note: ") + message)
        if error:
            self.title = "⚠️"
            self.status_item.title = message[:80]
        try:
            rumps.notification("My Dictation", "", message)
        except Exception:
            # Notifications need an app bundle identifier; the menu still shows the message.
            pass

    def paste(self, text):
        if not text:
            return
        self.last_text = text
        self.copy_item.title = "Copy last: " + (text[:40] + "…" if len(text) > 40 else text)
        previous = macos.get_clipboard()
        macos.set_clipboard(text, transient=True)
        macos.press_paste()
        if self.config.restore_clipboard and previous is not None:
            # Give the target app a moment to read the clipboard before putting it back.
            self.restore = (time.monotonic() + 0.5, previous)


def main():
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped.")


def run():
    settings = config.load()
    print("My Dictation\n")
    if not setup.claim_single_instance():
        print("My Dictation is already running (look for 🎙 in the menu bar). Quit that one first:")
        print("click 🎙 → Quit, or run:  pkill -f 'm dictation'")
        sys.exit(1)
    if not setup.ensure_api_key(settings) or not setup.ensure_permissions():
        sys.exit(1)
    app = DictationApp(settings)
    if not app.listener.start():
        print(setup.RESTART_HINT)
        sys.exit(1)
    log(f"Ready. Click into any text box, hold {KEY_NAMES[settings.hotkey]}, speak, then let go.")
    log("Press Ctrl+C here (or choose Quit in the 🎙 menu) to stop.")
    app.run()

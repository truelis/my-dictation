"""First-run checks done in the Terminal before the menu bar app starts."""

from __future__ import annotations

import fcntl
import getpass
import subprocess
import time

from dictation import config, macos
from dictation.groq_api import GroqClient, GroqError

SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_"
TERMINAL = "your terminal app (Terminal, iTerm or whichever you ran ./run.sh from)"
RESTART_HINT = (
    "\nCould not watch the keyboard. In System Settings → Privacy & Security, make sure "
    f"{TERMINAL} is on under Accessibility and Input Monitoring.\n"
    "Then quit the terminal app completely (Cmd+Q), open it again and run ./run.sh."
)
MICROPHONE_HINT = (
    f"Turn on {TERMINAL} in System Settings → Privacy & Security → Microphone, "
    "then quit the terminal app (Cmd+Q) and run ./run.sh again."
)


_lock_file = None


def claim_single_instance() -> bool:
    """False if another copy is running (several copies would each paste the text)."""
    global _lock_file
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _lock_file = open(config.CONFIG_DIR / "app.lock", "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def ensure_api_key(settings: config.Config) -> bool:
    if settings.api_key():
        return True
    print("You need a Groq API key (free): https://console.groq.com/keys")
    print("Click 'Create API Key', copy it, and paste it here.")
    print("(Nothing shows while you paste; that's normal. Press Enter after.)\n")
    while True:
        key = getpass.getpass("Groq API key: ").strip()
        if not key:
            print("No key entered, stopping.")
            return False
        try:
            GroqClient(key).check_key()
        except GroqError as e:
            print(f"That key didn't work: {e}\nTry again, or press Enter to stop.\n")
            continue
        settings.groq_api_key = key
        config.save(settings)
        print(f"Key works. Saved in {config.CONFIG_PATH}\n")
        return True


def ensure_permissions() -> bool:
    missing = []
    if not macos.has_input_monitoring():
        macos.request_input_monitoring()
        missing.append(("Input Monitoring", "ListenEvent", "notice when you hold the dictation key"))
    if not macos.has_accessibility():
        macos.request_accessibility()
        missing.append(("Accessibility", "Accessibility", "paste the text for you"))

    microphone = macos.microphone_status()
    if microphone == "unknown":
        print("macOS will ask to use the microphone. Click Allow.")
        microphone = macos.request_microphone()
    if microphone != "granted":
        missing.append(("Microphone", "Microphone", "hear you"))

    if not missing:
        return True
    print("My Dictation needs a few permissions first.\n")
    print(f"In System Settings → Privacy & Security, turn on {TERMINAL} under:")
    for name, _, reason in missing:
        print(f"  • {name}: to {reason}")
    print("\nIf it isn't in the list, click +, then pick it from Applications (Utilities folder for Terminal).")
    print("Then quit the terminal app completely (Cmd+Q), open it again and run ./run.sh.\n")
    subprocess.run(["open", SETTINGS + missing[0][1]])
    return False

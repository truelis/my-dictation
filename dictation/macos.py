"""macOS plumbing: the global hold-to-talk key, the clipboard, pasting and sounds."""

from __future__ import annotations

import time
from typing import Callable, Optional

import Quartz
from AppKit import NSApplication, NSPasteboard, NSPasteboardTypeString, NSSound

V_KEY = 9
# Clipboard managers skip items marked with this type, so dictations don't flood their history.
TRANSIENT_TYPE = "org.nspasteboard.TransientType"


class HoldKeyListener:
    """Watches a single modifier key system-wide and reports when it is held and released.

    Pressing any other key while holding it reports a cancel instead, so shortcuts like
    Option+E still work normally. Needs the Accessibility permission.
    """

    def __init__(
        self,
        key_code: int,
        flag_mask: int,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_cancel: Callable[[], None],
    ):
        self.key_code = key_code
        self.flag_mask = flag_mask
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.held = False
        self._tap = None

    def start(self) -> bool:
        """Install the event tap on the main run loop. Returns False without permission."""
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged) | Quartz.CGEventMaskBit(
            Quartz.kCGEventKeyDown
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._handle,
            None,
        )
        if self._tap is None:
            return False
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        return True

    def _handle(self, proxy, event_type, event, refcon):
        if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            # macOS switches taps off if they are ever slow; switch it straight back on.
            Quartz.CGEventTapEnable(self._tap, True)
        elif event_type == Quartz.kCGEventKeyDown:
            if self.held:
                self.held = False
                self.on_cancel()
        elif event_type == Quartz.kCGEventFlagsChanged:
            code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if code == self.key_code:
                down = bool(Quartz.CGEventGetFlags(event) & self.flag_mask)
                if down and not self.held:
                    self.held = True
                    self.on_press()
                elif not down and self.held:
                    self.held = False
                    self.on_release()
            elif self.held:
                # Another modifier joined in, so this is a shortcut, not dictation.
                self.held = False
                self.on_cancel()
        return event


def get_clipboard() -> Optional[str]:
    return NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)


def set_clipboard(text: str, transient: bool = False) -> None:
    board = NSPasteboard.generalPasteboard()
    board.clearContents()
    board.setString_forType_(text, NSPasteboardTypeString)
    if transient:
        board.setString_forType_("", TRANSIENT_TYPE)


def press_paste() -> None:
    """Send Cmd+V to whichever app has focus. Needs the Accessibility permission."""
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(source, V_KEY, down)
        Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def play(name: str) -> None:
    sound = NSSound.soundNamed_(name)
    if sound is not None:
        sound.play()


def bring_to_front() -> None:
    """Menu bar apps start in the background; without this, popups open hidden behind other windows."""
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


# --- permissions (checks are skipped on old PyObjC versions that lack them) ---

def _call(name: str, default: bool = True) -> bool:
    function = getattr(Quartz, name, None)
    return bool(function()) if function else default


def has_input_monitoring() -> bool:
    return _call("CGPreflightListenEventAccess")


def request_input_monitoring() -> None:
    _call("CGRequestListenEventAccess")


def has_accessibility() -> bool:
    return _call("CGPreflightPostEventAccess")


def request_accessibility() -> None:
    _call("CGRequestPostEventAccess")


def microphone_status() -> str:
    """'granted', 'denied' or 'unknown' (not asked yet)."""
    from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
    return {3: "granted", 1: "denied", 2: "denied"}.get(status, "unknown")


def request_microphone(timeout: float = 60) -> str:
    """Show macOS's microphone prompt and wait for the answer."""
    from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

    AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, lambda granted: None)
    deadline = time.monotonic() + timeout
    while microphone_status() == "unknown" and time.monotonic() < deadline:
        time.sleep(0.2)
    return microphone_status()

"""Settings stored in ~/.my-dictation/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional, Tuple

CONFIG_DIR = Path.home() / ".my-dictation"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Keys you can hold to dictate: macOS key code and the modifier flag that is set while it is held.
HOTKEYS = {
    "right_option": (61, 0x40),
    "right_command": (54, 0x10),
    "right_control": (62, 0x2000),
    "fn": (63, 0x800000),
}


@dataclass
class Config:
    groq_api_key: str = ""
    # Which key to hold while speaking (one of HOTKEYS).
    hotkey: str = "right_option"
    # Speech-to-text model on Groq.
    transcription_model: str = "whisper-large-v3-turbo"
    # Language code like "en" or "el". Empty means auto-detect.
    language: str = ""
    # Run the transcript through an AI model to remove filler words and fix punctuation.
    cleanup_enabled: bool = True
    cleanup_model: str = "openai/gpt-oss-120b"
    # Names and terms the transcriber often gets wrong, e.g. ["Groq", "Kubernetes"].
    vocabulary: List[str] = field(default_factory=list)
    # Put back whatever was on the clipboard before the dictation was pasted.
    restore_clipboard: bool = True
    play_sounds: bool = True

    def api_key(self) -> str:
        return os.environ.get("GROQ_API_KEY") or self.groq_api_key

    def hotkey_spec(self) -> Tuple[int, int]:
        return HOTKEYS.get(self.hotkey, HOTKEYS["right_option"])


def modified_time(path: Optional[Path] = None) -> float:
    path = path or CONFIG_PATH
    return path.stat().st_mtime if path.exists() else 0.0


def load(path: Optional[Path] = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        return Config()
    data = json.loads(path.read_text())
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def save(config: Config, path: Optional[Path] = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n")
    # The file holds the API key, so only you can read it.
    path.chmod(0o600)

# My Dictation

Hold a key, speak, let go, and clean text appears wherever your cursor is: in any
app (Mail, Slack, Notes, your browser, your code editor).

It lives in your Mac's menu bar as 🎙. Your speech is turned into text by
[Groq](https://groq.com/) (Whisper), then an AI model removes "um"s and false
starts and fixes punctuation before it's pasted.

## Install (Apple Silicon Mac)

You need Git and Python 3. If you've never installed developer tools, run this
first and click **Install** in the popup:

```bash
xcode-select --install
```

Then download and start the app:

```bash
git clone https://github.com/truelis/my-dictation.git
cd my-dictation
./run.sh
```

The first run takes about a minute to install. After that, `./run.sh` starts it
immediately.

### 1. Get a Groq API key

1. Sign up at [console.groq.com](https://console.groq.com/).
2. Go to [API Keys](https://console.groq.com/keys) and click **Create API Key**.
3. Copy it. My Dictation asks for it on first start (or use
   **🎙 → Set Groq API key…**).

### 2. Grant permissions

macOS asks for these the first time. They go to **Terminal** (or whichever app
you ran `./run.sh` from), because that's what runs My Dictation.

In **System Settings → Privacy & Security**, turn Terminal on under:

- **Microphone**: to hear you.
- **Accessibility**: to paste the text for you.
- **Input Monitoring**: to notice when you hold the dictation key.

After changing these, stop the app (Ctrl+C in Terminal) and run `./run.sh` again.

## Use it

1. Click into any text field.
2. **Hold Right Option ⌥**, speak, and let go.
3. The icon turns 🔴 while listening, ⏳ while transcribing, and the text is pasted.

Tips:

- Pressing another key while holding Right Option cancels, so shortcuts like
  ⌥+E still work.
- Say "new line" or "new paragraph" for line breaks, and correct yourself
  naturally ("at 3, no, at 4").
- Your clipboard is put back the way it was after pasting. **Copy last** in the
  menu copies your latest dictation if it ended up in the wrong place.

## Menu

| Item                 | What it does                                                    |
| -------------------- | --------------------------------------------------------------- |
| AI cleanup           | Turn off to paste exactly what Whisper heard.                   |
| Hotkey               | Hold Right Option, Right Command, Right Control or Fn instead.  |
| Set Groq API key…    | Change your key.                                                |
| Open settings file   | Edit all settings (below).                                      |

## Settings

Settings are saved in `~/.my-dictation/config.json` (only your user can read
it, since it holds your API key). Restart the app after editing it by hand.

| Setting               | Default                  | Meaning                                                              |
| --------------------- | ------------------------ | -------------------------------------------------------------------- |
| `hotkey`              | `right_option`           | `right_option`, `right_command`, `right_control` or `fn`             |
| `language`            | `""` (auto-detect)       | Language code, e.g. `"en"` or `"el"`. Setting it improves accuracy.  |
| `vocabulary`          | `[]`                     | Names and terms to spell right, e.g. `["Groq", "Kubernetes"]`        |
| `cleanup_enabled`     | `true`                   | AI cleanup on or off                                                 |
| `transcription_model` | `whisper-large-v3-turbo` | Groq speech-to-text model                                            |
| `cleanup_model`       | `llama-3.3-70b-versatile`| Groq chat model used for cleanup                                     |
| `restore_clipboard`   | `true`                   | Put your previous clipboard back after pasting                       |
| `play_sounds`         | `true`                   | Sounds when recording starts and stops                               |

If Groq retires a model, pick a current one from
[console.groq.com/docs/models](https://console.groq.com/docs/models). If cleanup
fails, the raw transcript is still pasted.

## Cost and privacy

Your recording is sent to Groq for transcription and the text to Groq for
cleanup. Nothing else leaves your Mac. Groq's free tier covers normal personal
use; paid usage is a fraction of a cent per minute of speech.

## Troubleshooting

- **Nothing happens when I hold the key**: check Accessibility and Input
  Monitoring for Terminal, then restart the app.
- **🎙 turns ⚠️**: open the menu to read the error (e.g. an invalid API key).
- **Text is transcribed but not pasted**: Accessibility permission is missing.
  Use **Copy last** and paste it yourself meanwhile.
- **Fn opens the emoji picker**: set **System Settings → Keyboard → Press 🌐 key
  to** "Do Nothing", or choose another hotkey.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

| File                    | Role                                                        |
| ----------------------- | ----------------------------------------------------------- |
| `dictation/app.py`      | Menu bar app and the record → transcribe → paste flow       |
| `dictation/macos.py`    | Global hold-to-talk key, clipboard, Cmd+V, sounds           |
| `dictation/audio.py`    | Microphone recording and WAV encoding                       |
| `dictation/groq_api.py` | Groq transcription and cleanup calls                        |
| `dictation/config.py`   | Settings file                                               |

# GARGI

**Generally A Really Good Interface**

Terminal-native AI companion with animated ASCII face, voice output, and personality that shifts with time of day.

## What it does

- Animated 60×32 ASCII portrait (blinks, talks, thinks)
- Streaming chat with NVIDIA NIM API (free, no credit card)
- Voice output via TTS (Windows SAPI / macOS say / espeak)
- Time-aware mood system
- Slash commands (`/mood`, `/voice`, `/model`, `/setup`, etc.)
- Full keyboard shortcuts

## Quick start

### Direct USAGE
Download the latest release and open gargi.exe

If Windows blocks the executable:
1. Open Windows Security.
2. Go to App & browser control.
3. Open Smart App Control settings.
4. Turn it off.
5. Launch the application again.
6. It will open in CMD/Powershell.

   
### Use by Source Code

```bash
git clone https://github.com/lakshyabuilds/gargi.git
cd gargi
pip install textual rich openai
python gargi.py
```

First run asks for NVIDIA NIM API key. Get one free at [build.nvidia.com](https://build.nvidia.com).

## Build standalone exe

```bash
python build.py pyinstaller     # onedir mode (fast, ~30s)
python build.py nuitka          # compile to C (slower, fewer AV flags)
```

Windows: double-click `build_exe.bat`.

Output in `dist_exe/<method>/gargi/`. No Python needed on target machine.

## Structure

```
gargi/
├── gargi.py              # entry point
├── gargi_app/
│   ├── tui.py            # Textual TUI
│   ├── agent.py          # NIM client
│   ├── persona.py        # personality
│   ├── ascii_art.py      # animated face
│   └── voice.py          # TTS engine
├── build.py              # exe builder
├── build_exe.bat         # Windows one-click
└── requirements.txt
```

## Commands

```
/setup      connect/replace API key
/models     list free models
/model <n>  switch model
/voice      toggle TTS
/mood       show current vibe
/face <m>   lock expression
/name <you> set your name
/reset      clear memory
/clear      clear screen
/help       show all
/quit       exit
```

Keyboard: `Ctrl+Q` quit · `Ctrl+R` reset · `Ctrl+T` voice · `Ctrl+S` stop · `Ctrl+F` cycle face · `Esc` focus input.

## Tech

- **UI**: Textual (terminal UI framework)
- **AI**: NVIDIA NIM (free LLM API, OpenAI-compatible)
- **Voice**: Windows SAPI / macOS say / espeak
- **Pure Python** — no Rust, no Docker, no native deps

Default model: `nvidia/llama-3.3-nemotron-super-49b-v1.5`. Switch with `/model`.

## Terminal requirements

- ~90 cols × ~36 rows minimum
- Windows Terminal, PowerShell 7, or `chcp 65001` on legacy cmd.exe
- Python 3.10+

## License

MIT

"""GARGI's voice - zero-dependency TTS."""

import os
import re
import sys
import shutil
import tempfile
import platform
import subprocess
import threading

_NO_WINDOW = 0
if sys.platform == "win32":
    _NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_CHARS = re.compile(r"[*_#>|~\[\]()]")
_URL = re.compile(r"https?://\S+")
_EMOJI = re.compile(
    r"["
    r"\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F1E6-\U0001F1FF"
    r"\U00002190-\U000021FF"
    r"\U00002B00-\U00002BFF"
    r"]+",
    flags=re.UNICODE,
)


def clean_for_speech(text: str, max_chars: int = 420) -> str:
    t = _CODE_BLOCK.sub(" ... code block ... ", text)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _URL.sub(" link ", t)
    t = _EMOJI.sub("", t)
    t = _MD_CHARS.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        for sep in (". ", "! ", "? "):
            idx = cut.rfind(sep)
            if idx > max_chars * 0.5:
                return cut[: idx + 1]
        return cut + "..."
    return t


class Voice:
    def __init__(self, enabled: bool = False, rate: int = 2):
        self.rate = rate
        self._proc = None
        self._lock = threading.Lock()
        self._tmp_files = []
        self.backend = self._detect_backend()
        self.available = self.backend is not None
        self.enabled = enabled and self.available

    def _detect_backend(self):
        system = platform.system()
        if system == "Windows":
            return "sapi"
        if system == "Darwin":
            return "say" if shutil.which("say") else None
        if shutil.which("spd-say"):
            return "spd-say"
        if shutil.which("espeak-ng"):
            return "espeak-ng"
        if shutil.which("espeak"):
            return "espeak"
        return None

    @property
    def backend_name(self) -> str:
        names = {
            "sapi": "Windows SAPI",
            "say": "macOS say",
            "spd-say": "speech-dispatcher",
            "espeak-ng": "espeak-ng",
            "espeak": "espeak",
        }
        return names.get(self.backend, "none")

    def toggle(self) -> bool:
        if not self.available:
            return False
        self.enabled = not self.enabled
        if not self.enabled:
            self.stop()
        return self.enabled

    def stop(self):
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    @staticmethod
    def _unlink(path):
        if not path:
            return
        try:
            os.unlink(path)
        except Exception:
            pass

    def speak(self, text: str):
        if not self.enabled or not self.available:
            return
        cleaned = clean_for_speech(text)
        if not cleaned:
            return
        self.stop()
        threading.Thread(target=self._speak_worker, args=(cleaned,), daemon=True).start()

    def _speak_worker(self, text: str):
        tmp = None
        try:
            if self.backend == "sapi":
                cmd, tmp = self._sapi_command(text)
            elif self.backend == "say":
                cmd = ["say", "-r", str(170 + self.rate * 10), text]
            elif self.backend == "spd-say":
                cmd = ["spd-say", "-w", "-r", str(self.rate * 10), text]
            else:
                cmd = [self.backend, "-s", str(165 + self.rate * 10), text]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
            )
            with self._lock:
                self._proc = proc
            proc.wait()
        except Exception:
            pass
        finally:
            with self._lock:
                self._proc = None
            self._unlink(tmp)

    def _sapi_command(self, text: str):
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="gargi_tts_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)

        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {self.rate}; "
            "$s.Volume = 100; "
            "try { $s.SelectVoiceByHints('Female') } catch {}; "
            f"$t = [IO.File]::ReadAllText('{path}', [Text.Encoding]::UTF8); "
            "$s.Speak($t); $s.Dispose()"
        )
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", ps,
        ]
        return cmd, path

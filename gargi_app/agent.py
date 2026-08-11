"""GARGI's AI engine - NVIDIA NIM API client."""

import os
import re
import json
from pathlib import Path
from typing import Optional, Generator, List, Dict

from openai import OpenAI

from .persona import build_system_prompt

CONFIG_DIR = Path.home() / ".gargi"
CONFIG_FILE = CONFIG_DIR / "config.json"

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

MODELS = [
    ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "NVIDIA's own, great all-rounder (default)"),
    ("meta/llama-3.1-70b-instruct", "Meta, solid + very reliable"),
    ("meta/llama-3.3-70b-instruct", "Meta, newer and chattier"),
    ("qwen/qwen2.5-coder-32b-instruct", "best for pure coding help"),
    ("mistralai/mistral-large-2-instruct", "strong reasoning + code"),
    ("deepseek-ai/deepseek-r1-distill-llama-8b", "fast + lightweight"),
]

MAX_HISTORY_MESSAGES = 24

# Strip reasoning traces some models emit
_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    text = _THINK_TAG.sub("", text)
    text = _OPEN_THINK.sub("", text)
    return text.strip()


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> dict:
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict):
    ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


def get_api_key() -> Optional[str]:
    env_key = os.environ.get("NVIDIA_NIM_API_KEY") or os.environ.get("GARGI_API_KEY")
    if env_key:
        return env_key.strip()
    return get_config().get("api_key")


def save_api_key(api_key: str):
    cfg = get_config()
    cfg["api_key"] = api_key.strip()
    cfg.setdefault("model", DEFAULT_MODEL)
    save_config(cfg)


def get_saved_model() -> str:
    return get_config().get("model", DEFAULT_MODEL)


def get_user_name() -> str:
    return get_config().get("user_name", "bestie")


def save_user_name(name: str):
    cfg = get_config()
    cfg["user_name"] = name
    save_config(cfg)


def format_api_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "401" in msg or "unauthorized" in low or "invalid api key" in low:
        return "NIM 401: invalid API key; run /setup"
    if "402" in msg or "credit" in low or "quota" in low:
        return "NIM 402: quota exceeded; try /models or wait for quota reset"
    if "403" in msg:
        return "NIM 403: model access denied; try /models"
    if "404" in msg or "model_not_found" in low:
        return "NIM 404: model not found; try /models"
    if "429" in msg or "rate limit" in low:
        return "NIM 429: rate limit; retry in 30 seconds"
    if "timeout" in low or "timed out" in low:
        return "NIM timeout: request exceeded 90 seconds"
    if "connection" in low or "network" in low or "getaddrinfo" in low:
        return "NIM connection error: check network access"
    return f"NIM error: {type(exc).__name__}: {msg[:200]}"


class GargiAgent:
    def __init__(self, api_key: str, model: Optional[str] = None, user_name: str = "bestie"):
        self.api_key = api_key
        self.model = model or get_saved_model()
        self.user_name = user_name
        self.client = OpenAI(
            base_url=NIM_BASE_URL,
            api_key=api_key,
            timeout=90.0,
            max_retries=1,
        )
        self.history: List[Dict[str, str]] = []
        self.last_error = None

    def _system_message(self) -> Dict[str, str]:
        return {"role": "system", "content": build_system_prompt(self.user_name)}

    def _messages(self) -> List[Dict[str, str]]:
        return [self._system_message()] + self.history[-MAX_HISTORY_MESSAGES:]

    def reset_conversation(self):
        self.history = []

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self.history if m["role"] == "user")

    def chat_stream(self, message: str) -> Generator[str, None, None]:
        self.history.append({"role": "user", "content": message})

        full = ""
        in_think = False
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=self._messages(),
                temperature=0.85,
                top_p=0.95,
                max_tokens=1024,
                stream=True,
            )

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if not piece:
                    continue

                full += piece

                if "<think>" in piece.lower():
                    in_think = True
                    continue
                if in_think:
                    if "</think>" in piece.lower():
                        in_think = False
                    continue

                yield piece

            cleaned = _strip_think(full)
            self.history.append({"role": "assistant", "content": cleaned or full})

        except Exception as exc:
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            yield f"\n\n[!] {format_api_error(exc)}"

    def validate_key(self) -> tuple:
        """
        Ping the API with a 1-token request.

        Returns (ok, friendly_message). The unmodified exception is kept on
        self.last_error so --check can print the real traceback text instead
        of the chat-facing wording.
        """
        self.last_error = None
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                temperature=0,
                max_tokens=1,
                stream=False,
            )
            return True, f"connected to {self.model}"
        except Exception as exc:
            self.last_error = exc
            return False, format_api_error(exc)

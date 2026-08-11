#!/usr/bin/env python3
"""GARGI - Terminal AI companion launcher."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def fix_windows_console():
    if sys.platform != "win32":
        return
    try:
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    except Exception:
        pass


fix_windows_console()


def check_dependencies(verbose: bool = False) -> bool:
    required = {"textual": "textual", "rich": "rich", "openai": "openai"}
    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
            if verbose:
                print(f"  [ok]      {pkg}")
        except ImportError:
            missing.append(pkg)
            if verbose:
                print(f"  [MISSING] {pkg}")

    if missing:
        print()
        print("=" * 58)
        print("  GARGI needs these packages:")
        print("=" * 58)
        print(f"\n  {', '.join(missing)}\n")
        print(f"  pip install {' '.join(missing)}")
        print()
        return False
    return True


def cmd_setup():
    from gargi_app.agent import get_api_key, save_api_key
    existing = get_api_key()
    if existing:
        print(f"  current: {existing[:12]}...{existing[-4:]}")
        if input("  replace? (y/N): ").strip().lower() != "y":
            return
    print("\n  Get key at https://build.nvidia.com")
    print("  Settings -> API Keys -> Generate\n")
    key = input("  paste (nvapi-...): ").strip()
    if key.startswith("nvapi-") and len(key) > 20:
        save_api_key(key)
        print("\n  saved. run: python gargi.py\n")
        return True
    print("\n  invalid key: expected nvapi- prefix\n")
    return False


def cmd_check():
    print("\n  GARGI system check")
    print("  " + "-" * 40)
    print("\n  dependencies:")
    if not check_dependencies(verbose=True):
        return False

    print("\n  voice:")
    from gargi_app.voice import Voice
    v = Voice()
    if v.available:
        print(f"  [ok]      {v.backend_name}")
    else:
        print("  [none]    no TTS engine (install espeak-ng on linux)")

    print("\n  api key:")
    from gargi_app.agent import get_api_key, get_saved_model, GargiAgent
    key = get_api_key()
    if not key:
        print("  [MISSING] run: python gargi.py --setup")
        return False
    print(f"  [found]   {key[:12]}...{key[-4:]}")
    print(f"  [model]   {get_saved_model()}")
    print("\n  pinging NIM...")

    agent = GargiAgent(key, get_saved_model())
    ok, msg = agent.validate_key()
    print(f"  [{'ok' if ok else 'FAIL'}]      {msg}")
    if not ok and agent.last_error is not None:
        # Diagnostics get the real exception, not the chat wording.
        err = agent.last_error
        print(f"  [raw]     {type(err).__name__}: {err}")
    print()
    return ok


def main():
    args = [a.lower() for a in sys.argv[1:]]

    if "--help" in args or "-h" in args:
        print("Usage: python gargi.py [option]")
        print("  --setup    set API key")
        print("  --check    system diagnostic")
        print("  (no args)  launch GARGI")
        return

    if "--setup" in args or "-s" in args:
        if not check_dependencies():
            sys.exit(1)
        sys.exit(0 if cmd_setup() else 1)

    if "--check" in args or "-c" in args:
        sys.exit(0 if cmd_check() else 1)

    if not check_dependencies():
        sys.exit(1)

    from gargi_app.ascii_art import BOOT_BANNER
    from gargi_app.tui import GargiApp

    print(BOOT_BANNER)
    print("  booting...\n")

    try:
        GargiApp().run()
    except KeyboardInterrupt:
        # 130 is the conventional shell code for SIGINT.
        sys.exit(130)


if __name__ == "__main__":
    main()

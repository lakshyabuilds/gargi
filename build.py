"""Build GARGI into standalone executable."""

import sys
import shutil
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
ENTRY = ROOT / "gargi.py"
DIST = ROOT / "dist_exe"

IS_WIN = sys.platform == "win32"
EXE_SUFFIX = ".exe" if IS_WIN else ""
EXE_NAME = "gargi" + EXE_SUFFIX

ICON = ROOT / "gargi.ico"


def run(cmd):
    print("  $", " ".join(str(c) for c in cmd), "\n")
    subprocess.check_call([str(c) for c in cmd])


def pip_install(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", *pkgs])


def human_size(p):
    if p.is_dir():
        total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    else:
        total = p.stat().st_size
    return f"{total / (1024 * 1024):.1f} MB"


def write_spec_file(spec_path):
    entry_str = str(ENTRY).replace("\\", "\\\\")
    root_str = str(ROOT).replace("\\", "\\\\")
    icon_str = str(ICON).replace("\\", "\\\\") if ICON.exists() else ""

    hidden = [
        "gargi_app", "gargi_app.tui", "gargi_app.agent",
        "gargi_app.persona", "gargi_app.ascii_art", "gargi_app.voice",
        "textual.widgets._button", "textual.widgets._header",
        "textual.widgets._footer", "textual.widgets._static",
        "textual.widgets._input", "textual.widgets._label",
        "textual.widgets._rich_log", "textual.widgets._loading_indicator",
        "textual.widgets._tab_pane", "textual.widgets._tabs",
        "httpx", "httpcore", "httpcore._async", "httpcore._sync",
        "anyio", "anyio._backends", "anyio._backends._asyncio",
        "sniffio", "h11", "idna", "certifi", "distro",
        "pydantic", "pydantic_core", "annotated_types",
        "typing_extensions", "jiter", "tqdm",
    ]
    hidden_str = repr(hidden)

    icon_line = f"    icon=r'{icon_str}'," if icon_str else ""

    spec = f"""\
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

textual_datas = collect_data_files('textual')
rich_datas = collect_data_files('rich')
textual_hidden = collect_submodules('textual')
rich_hidden = collect_submodules('rich')
openai_hidden = collect_submodules('openai')

a = Analysis(
    [r'{entry_str}'],
    pathex=[r'{root_str}'],
    binaries=[],
    datas=textual_datas + rich_datas,
    hiddenimports={hidden_str} + textual_hidden + rich_hidden + openai_hidden,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='gargi',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
{icon_line}
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='gargi',
)
"""
    spec_path.write_text(spec, encoding="utf-8")


def build_pyinstaller():
    print("\n  === PyInstaller (onedir) ===\n")
    out_dir = DIST / "pyinstaller"
    work_dir = DIST / "_work"
    spec_path = DIST / "gargi.spec"

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_spec_file(spec_path)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(out_dir), "--workpath", str(work_dir), str(spec_path)])

    return out_dir / "gargi" / EXE_NAME


def build_nuitka():
    print("\n  === Nuitka ===\n")
    out_dir = DIST / "nuitka"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone", "--onefile",
        f"--output-dir={out_dir}",
        f"--output-filename={EXE_NAME}",
        "--assume-yes-for-downloads",
        "--include-package=gargi_app",
        "--include-package=textual",
        "--include-package=rich",
        "--include-package=openai",
        "--include-package=httpx",
        "--include-package=httpcore",
        "--include-package=anyio",
        "--include-package=pydantic",
        "--include-package=pydantic_core",
        "--include-package-data=textual",
        "--include-package-data=rich",
        "--product-name=GARGI",
        "--product-version=1.2.0",
        "--remove-output",
    ]

    if IS_WIN and ICON.exists():
        cmd.append(f"--windows-icon-from-ico={ICON}")

    cmd.append(str(ENTRY))
    run(cmd)
    return out_dir / EXE_NAME


def create_launcher(exe_dir):
    bat = exe_dir.parent / "Run GARGI.bat"
    bat.write_text(
        '@echo off\r\n'
        'chcp 65001 >nul 2>&1\r\n'
        'title GARGI\r\n'
        'cd /d "%~dp0gargi"\r\n'
        'gargi.exe %*\r\n'
        'pause\r\n',
        encoding="utf-8",
    )
    return bat


def main():
    method = "pyinstaller"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().lstrip("-")
        if arg in ("nuitka", "n"):
            method = "nuitka"
        elif arg in ("pyinstaller", "pyi", "py"):
            method = "pyinstaller"
        elif arg in ("help", "h", "?"):
            print(__doc__)
            return
        else:
            print(f"unknown build method: {sys.argv[1]}")
            sys.exit(2)

    print(f"\n  GARGI build - {method}\n")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {platform.system()} {platform.machine()}\n")

    if not ENTRY.exists():
        print(f"  ERROR: {ENTRY} not found")
        sys.exit(1)

    pip_install("textual", "rich", "openai")
    if method == "pyinstaller":
        pip_install("pyinstaller")
    else:
        pip_install("nuitka", "ordered-set", "zstandard")

    try:
        if method == "pyinstaller":
            exe = build_pyinstaller()
        else:
            exe = build_nuitka()
    except subprocess.CalledProcessError as e:
        print(f"\n  BUILD FAILED (exit {e.returncode})")
        sys.exit(1)

    if not exe.exists():
        print(f"\n  ERROR: {exe} not found")
        sys.exit(1)

    bat = None
    if method == "pyinstaller":
        bat = create_launcher(exe.parent)

    work = DIST / "_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    for f in DIST.glob("*.spec"):
        f.unlink(missing_ok=True)

    folder = exe.parent if method == "pyinstaller" else exe
    size = human_size(folder)

    print("\n" + "=" * 50)
    print("  SUCCESS")
    print("=" * 50)
    print(f"\n  exe:  {exe}")
    print(f"  size: {size}\n")

    if method == "pyinstaller":
        print(f"  Folder: {folder}")
        print(f"  Zip the folder to distribute")
        if bat:
            print(f"  Launcher: {bat}")
    else:
        print(f"  Single file. Copy anywhere.")

    print("\n  No Python needed on target machine")
    print(f"  Get API key: https://build.nvidia.com\n")


if __name__ == "__main__":
    main()

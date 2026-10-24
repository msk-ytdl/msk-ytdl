"""
Dependency diagnostics and environment health checking for MSK-YTDL.

Verifies Python version, yt-dlp, yt-dlp-ejs, Rich, FFmpeg, FFprobe,
and JavaScript runtimes (Deno, Node.js) with structured reporting.
"""

import importlib.metadata
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from youtube_downloader.config import ensure_directory_writable, load_config


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class DiagnosticItem:
    name: str
    required: bool
    status: CheckStatus
    version: Optional[str]
    details: str
    remediation: Optional[str] = None


def _run_cmd_get_first_line(args: List[str], timeout: int = 5) -> Tuple[bool, str]:
    """Execute command safely without shell=True and return first output line."""
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False
        )
        output = (proc.stdout or proc.stderr or "").strip()
        first_line = output.splitlines()[0] if output else ""
        return proc.returncode == 0, first_line
    except Exception as e:
        return False, str(e)


def check_python() -> DiagnosticItem:
    """Check Python version (must be >= 3.11)."""
    major, minor, micro = sys.version_info[:3]
    version_str = f"{major}.{minor}.{micro}"
    if sys.version_info >= (3, 11):
        return DiagnosticItem(
            name="Python Interpreter",
            required=True,
            status=CheckStatus.PASS,
            version=version_str,
            details=f"Executable: {sys.executable}"
        )
    return DiagnosticItem(
        name="Python Interpreter",
        required=True,
        status=CheckStatus.FAIL,
        version=version_str,
        details="Python 3.11 or later is required.",
        remediation="Install Python 3.11 or newer from https://www.python.org/downloads/."
    )


def check_module(module_name: str, package_name: Optional[str] = None, required: bool = True) -> DiagnosticItem:
    """Check if a Python package is installed and retrievable."""
    pkg_name = package_name or module_name
    try:
        ver = importlib.metadata.version(pkg_name)
        return DiagnosticItem(
            name=f"Python package: {pkg_name}",
            required=required,
            status=CheckStatus.PASS,
            version=ver,
            details="Installed and accessible in the current Python environment."
        )
    except importlib.metadata.PackageNotFoundError:
        return DiagnosticItem(
            name=f"Python package: {pkg_name}",
            required=required,
            status=CheckStatus.FAIL if required else CheckStatus.WARN,
            version=None,
            details="Not installed in current environment.",
            remediation=f"Run: pip install {pkg_name}"
        )


def find_ffmpeg_executable() -> Optional[str]:
    """
    Locate ffmpeg executable in:
    1. sys._MEIPASS (PyInstaller onefile extraction directory)
    2. Directory adjacent to sys.executable (PyInstaller onedir or portable folder)
    3. Directory adjacent to current working script or bin subfolder
    4. System PATH via shutil.which
    """
    binary_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"

    # 1. Check if frozen by PyInstaller
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / binary_name
            if cand.is_file():
                return str(cand)
        exe_dir = Path(sys.executable).parent
        cand_exe = exe_dir / binary_name
        if cand_exe.is_file():
            return str(cand_exe)
        cand_exe_bin = exe_dir / "bin" / binary_name
        if cand_exe_bin.is_file():
            return str(cand_exe_bin)

    # 2. Check adjacent to current working directory or bin folder
    cwd_bin = Path.cwd() / binary_name
    if cwd_bin.is_file():
        return str(cwd_bin)
    cwd_subbin = Path.cwd() / "bin" / binary_name
    if cwd_subbin.is_file():
        return str(cwd_subbin)

    # 3. Check system PATH
    return shutil.which("ffmpeg")


def find_ffprobe_executable() -> Optional[str]:
    """
    Locate ffprobe executable in:
    1. sys._MEIPASS (PyInstaller onefile extraction directory)
    2. Directory adjacent to sys.executable (PyInstaller onedir or portable folder)
    3. Directory adjacent to current working script or bin subfolder
    4. System PATH via shutil.which
    """
    binary_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"

    # 1. Check if frozen by PyInstaller
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / binary_name
            if cand.is_file():
                return str(cand)
        exe_dir = Path(sys.executable).parent
        cand_exe = exe_dir / binary_name
        if cand_exe.is_file():
            return str(cand_exe)
        cand_exe_bin = exe_dir / "bin" / binary_name
        if cand_exe_bin.is_file():
            return str(cand_exe_bin)

    # 2. Check adjacent to current working directory or bin folder
    cwd_bin = Path.cwd() / binary_name
    if cwd_bin.is_file():
        return str(cwd_bin)
    cwd_subbin = Path.cwd() / "bin" / binary_name
    if cwd_subbin.is_file():
        return str(cwd_subbin)

    # 3. Check system PATH
    return shutil.which("ffprobe")


def check_ffmpeg() -> DiagnosticItem:
    """Check whether FFmpeg executable is present and working."""
    path = find_ffmpeg_executable()
    if not path:
        return DiagnosticItem(
            name="FFmpeg (Media Merger & Converter)",
            required=True,
            status=CheckStatus.FAIL,
            version=None,
            details="ffmpeg.exe not found on system PATH or in application bundle.",
            remediation=(
                "FFmpeg is required to merge separate video/audio streams and convert to MP3.\n"
                "Install on Windows via: winget install Gyan.FFmpeg\n"
                "Or download from: https://www.gyan.dev/ffmpeg/builds/"
            )
        )

    ok, line = _run_cmd_get_first_line([path, "-version"])
    version_str = line.split(" Copyright")[0] if "ffmpeg version" in line else line
    return DiagnosticItem(
        name="FFmpeg (Media Merger & Converter)",
        required=True,
        status=CheckStatus.PASS if ok else CheckStatus.WARN,
        version=version_str or "Detected",
        details=f"Path: {path}"
    )


def check_ffprobe() -> DiagnosticItem:
    """Check whether FFprobe executable is present and working."""
    path = find_ffprobe_executable()
    if not path:
        return DiagnosticItem(
            name="FFprobe (Stream Analyzer)",
            required=False,
            status=CheckStatus.WARN,
            version=None,
            details="ffprobe.exe not found on system PATH or in application bundle.",
            remediation="Install FFprobe (bundled with FFmpeg) to assist format detection."
        )

    ok, line = _run_cmd_get_first_line([path, "-version"])
    version_str = line.split(" Copyright")[0] if "ffprobe version" in line else line
    return DiagnosticItem(
        name="FFprobe (Stream Analyzer)",
        required=False,
        status=CheckStatus.PASS if ok else CheckStatus.WARN,
        version=version_str or "Detected",
        details=f"Path: {path}"
    )


def check_js_runtime() -> DiagnosticItem:
    """
    Check for a supported JavaScript runtime (Deno or Node.js) for YouTube challenge solving.
    """
    # 1. Check Deno (preferred by yt-dlp)
    deno_path = shutil.which("deno")
    if deno_path:
        ok, line = _run_cmd_get_first_line(["deno", "--version"])
        ver = line.replace("deno", "").strip() if ok else "Detected"
        return DiagnosticItem(
            name="JavaScript Runtime (Deno)",
            required=False,
            status=CheckStatus.PASS,
            version=ver,
            details=f"Path: {deno_path} (Preferred runtime for yt-dlp EJS)"
        )

    # 2. Check Node.js
    node_path = shutil.which("node")
    if node_path:
        ok, line = _run_cmd_get_first_line(["node", "--version"])
        ver = line.strip() if ok else "Detected"
        return DiagnosticItem(
            name="JavaScript Runtime (Node.js)",
            required=False,
            status=CheckStatus.PASS,
            version=ver,
            details=f"Path: {node_path} (Supported runtime for yt-dlp EJS)"
        )

    # 3. Check Bun
    bun_path = shutil.which("bun")
    if bun_path:
        ok, line = _run_cmd_get_first_line(["bun", "--version"])
        ver = line.strip() if ok else "Detected"
        return DiagnosticItem(
            name="JavaScript Runtime (Bun)",
            required=False,
            status=CheckStatus.PASS,
            version=ver,
            details=f"Path: {bun_path}"
        )

    return DiagnosticItem(
        name="JavaScript Runtime (Deno / Node.js)",
        required=False,
        status=CheckStatus.WARN,
        version=None,
        details="No external JavaScript engine found on PATH.",
        remediation=(
            "YouTube signature challenges frequently require an external JS runtime.\n"
            "Recommended: Install Deno via PowerShell: irm https://deno.land/install.ps1 | iex\n"
            "Or install Node.js: winget install OpenJS.NodeJS.LTS"
        )
    )


def check_download_directory() -> DiagnosticItem:
    """Check configuration and write permissions for the download directory."""
    try:
        cfg = load_config()
        path = cfg.get_resolved_download_path()
        ensure_directory_writable(path)
        return DiagnosticItem(
            name="Download Directory",
            required=True,
            status=CheckStatus.PASS,
            version=None,
            details=f"Path: {path} (Writable)"
        )
    except Exception as e:
        return DiagnosticItem(
            name="Download Directory",
            required=True,
            status=CheckStatus.FAIL,
            version=None,
            details=f"Failed to access or write to download folder: {e}",
            remediation="Change the download directory in the configuration to an accessible folder."
        )


def run_all_checks() -> List[DiagnosticItem]:
    """Execute all diagnostic checks and return structured results."""
    items: List[DiagnosticItem] = []
    items.append(check_python())
    items.append(check_module("yt_dlp", "yt-dlp", required=True))
    items.append(check_module("yt_dlp_ejs", "yt-dlp-ejs", required=True))
    items.append(check_module("rich", "rich", required=True))
    items.append(check_ffmpeg())
    items.append(check_ffprobe())
    items.append(check_js_runtime())
    items.append(check_download_directory())
    return items


# Reconfigure stdout/stderr for Unicode/UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_diagnostic_report(console: Optional[Console] = None) -> bool:
    """
    Render a polished Rich table report of diagnostic checks.

    Returns:
        True if all required components passed, False if any required component failed.
    """
    c = console or Console()
    items = run_all_checks()

    table = Table(
        title="[bold cyan]MSK-YTDL System & Dependency Health Check[/bold cyan]",
        title_justify="left",
        show_header=True,
        header_style="bold magenta",
        expand=True
    )

    table.add_column("Component", style="bold", ratio=3)
    table.add_column("Type", justify="center", ratio=1)
    table.add_column("Status", justify="center", ratio=1)
    table.add_column("Version", justify="center", ratio=2)
    table.add_column("Details & Recommendations", ratio=6)

    all_passed = True
    warnings = 0

    for item in items:
        req_label = "Required" if item.required else "Optional"

        if item.status == CheckStatus.PASS:
            status_display = "[bold green][PASS][/bold green]"
        elif item.status == CheckStatus.WARN:
            status_display = "[bold yellow][WARN][/bold yellow]"
            warnings += 1
        else:
            status_display = "[bold red][FAIL][/bold red]"
            if item.required:
                all_passed = False

        details_text = item.details
        if item.remediation:
            details_text += f"\n[bold yellow]Remedy:[/bold yellow] {item.remediation}"

        table.add_row(
            item.name,
            req_label,
            status_display,
            item.version or "-",
            details_text
        )

    c.print()
    c.print(table)
    c.print()

    if not all_passed:
        c.print(Panel(
            "[bold red]System Diagnostics: Missing Critical Dependencies[/bold red]\n"
            "One or more required components are missing or unsupported. Please resolve the "
            "failures highlighted above before running download operations.",
            border_style="red"
        ))
    elif warnings > 0:
        c.print(Panel(
            "[bold yellow]System Diagnostics: Ready with Warnings[/bold yellow]\n"
            "All essential tools are ready. However, optional recommendations above "
            "(such as installing Deno or FFprobe) may enhance reliability.",
            border_style="yellow"
        ))
    else:
        c.print(Panel(
            "[bold green]System Diagnostics: All Systems Ready[/bold green]\n"
            "Your environment has passed all checks and is fully equipped for downloading.",
            border_style="green"
        ))

    return all_passed

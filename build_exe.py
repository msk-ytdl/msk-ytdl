"""
Build script for MSK-YTDL: Generates a standalone Windows Executable (.exe),
bundles FFmpeg/FFprobe binaries, and packages a ready-to-share ZIP file.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(force_terminal=True, legacy_windows=False)

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PORTABLE_DIR = DIST_DIR / "MSK-YTDL-Portable"
ZIP_OUTPUT = DIST_DIR / "MSK-YTDL-Windows-x64.zip"


def find_system_ffmpeg_binaries() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Search for ffmpeg.exe and ffprobe.exe on the system.
    Checks WinGet locations, PATH, and local directories.
    """
    ffmpeg_path: Optional[Path] = None
    ffprobe_path: Optional[Path] = None

    # 1. Check PATH via shutil.which
    which_ffmpeg = shutil.which("ffmpeg")
    which_ffprobe = shutil.which("ffprobe")
    if which_ffmpeg:
        ffmpeg_path = Path(which_ffmpeg).resolve()
    if which_ffprobe:
        ffprobe_path = Path(which_ffprobe).resolve()

    # 2. Check WinGet packages if not found or if which returned a shim/link
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for exe in winget_dir.glob("**/ffmpeg.exe"):
                ffmpeg_path = exe.resolve()
                break
            for exe in winget_dir.glob("**/ffprobe.exe"):
                ffprobe_path = exe.resolve()
                break

    return ffmpeg_path, ffprobe_path


def ensure_pyinstaller() -> bool:
    """Ensure PyInstaller is installed in the active environment."""
    try:
        import PyInstaller
        return True
    except ImportError:
        console.print("[yellow]PyInstaller is not installed in the current environment.[/yellow]")
        console.print("[cyan]Installing PyInstaller via pip...[/cyan]")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=False)
        return result.returncode == 0


def create_portable_launcher(target_dir: Path) -> None:
    """Create a convenient batch launcher for double-clicking in Windows."""
    launcher_content = (
        "@echo off\r\n"
        "title MSK-YTDL - Reliable YouTube Downloader\r\n"
        "cd /d \"%~dp0\"\r\n"
        "start \"\" \"MSK-YTDL.exe\"\r\n"
    )
    launcher_file = target_dir / "Start_MSK_YTDL.bat"
    launcher_file.write_text(launcher_content, encoding="ascii")


def create_readme(target_dir: Path, has_ffmpeg: bool) -> None:
    """Create an informative README for end users receiving the portable package."""
    ffmpeg_status = "BUNDLED (Ready out-of-the-box)" if has_ffmpeg else "Requires external FFmpeg"
    readme_text = f"""===================================================================
  MSK YTDL: Reliable YouTube Video & Audio Downloader
  Publisher: MSK Software Solutions
===================================================================

Thank you for choosing MSK YTDL by MSK Software Solutions!
This is a self-contained portable package. Zero Python or pip setup required!

QUICK START:
  1. Double-click "Start_MSK_YTDL.bat" or "MSK-YTDL.exe".
  2. Follow the numbered menu in the console window.
  3. Enter any YouTube video or playlist link.
  4. Files will be saved into your Windows "Downloads/YouTube" folder!

WINDOWS SMARTSCREEN / SECURITY NOTICE:
  MSK YTDL is 100% safe, open-source software with zero ads or tracking.
  If Windows displays "Windows protected your PC":
    1. Click "More info".
    2. Click "Run anyway".
  To permanently trust the publisher on this PC, right-click:
    "Install_MSK_Certificate.bat" -> "Run as administrator".

FFMPEG STATUS:
  {ffmpeg_status}
  FFmpeg enables merging high-resolution video streams (1080p, 1440p, 4K),
  converting audio to 320kbps MP3, and embedding album artwork.

COMMAND LINE USAGE:
  You can also run MSK YTDL from PowerShell or Command Prompt:
    .\\MSK-YTDL.exe --url "https://www.youtube.com/watch?v=..." --mode video
    .\\MSK-YTDL.exe --url "https://www.youtube.com/watch?v=..." --mode audio --audio-quality 320
    .\\MSK-YTDL.exe --check

LEGAL & AUTHORIZED USE NOTICE:
  This tool is strictly intended for downloading videos you own,
  have explicit permission to save, or are authorized under applicable terms.
"""
    (target_dir / "README.txt").write_text(readme_text, encoding="utf-8")


def build_executable(onefile: bool = False) -> bool:
    """Run PyInstaller build."""
    entry_point = PROJECT_ROOT / "youtube_downloader" / "__main__.py"
    if not entry_point.exists():
        console.print(f"[bold red]Error: Entry point {entry_point} not found.[/bold red]")
        return False

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "MSK-YTDL",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--collect-all", "yt_dlp",
        "--collect-all", "yt_dlp_ejs",
        "--collect-all", "rich",
        "--hidden-import", "youtube_downloader",
        "--hidden-import", "mutagen",
        "--hidden-import", "urllib3",
        "--console",
    ]

    web_dir = PROJECT_ROOT / "youtube_downloader" / "web"
    if web_dir.exists():
        cmd.extend(["--add-data", f"{web_dir};youtube_downloader/web"])

    version_file = PROJECT_ROOT / "windows_version_info.txt"
    if version_file.exists():
        cmd.extend(["--version-file", str(version_file)])

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    cmd.append(str(entry_point))

    console.print(f"[cyan]Running PyInstaller command:[/cyan] {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    return proc.returncode == 0


def package_distribution(onefile: bool = False) -> Optional[Path]:
    """
    Bundle the compiled executable, FFmpeg binaries, launchers,
    and compress into a shareable ZIP package.
    """
    ffmpeg_exe, ffprobe_exe = find_system_ffmpeg_binaries()

    if PORTABLE_DIR.exists():
        shutil.rmtree(PORTABLE_DIR, ignore_errors=True)
    PORTABLE_DIR.mkdir(parents=True, exist_ok=True)

    if onefile:
        built_exe = DIST_DIR / "MSK-YTDL.exe"
        if not built_exe.exists():
            console.print("[bold red]Error: MSK-YTDL.exe was not created in dist/[/bold red]")
            return None
        shutil.copy2(built_exe, PORTABLE_DIR / "MSK-YTDL.exe")
    else:
        built_folder = DIST_DIR / "MSK-YTDL"
        if not built_folder.exists():
            console.print("[bold red]Error: MSK-YTDL directory was not created in dist/[/bold red]")
            return None
        # Move or copy built folder contents into PORTABLE_DIR
        for item in built_folder.iterdir():
            dest = PORTABLE_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Copy bundled FFmpeg and FFprobe alongside the executable
    has_ffmpeg = False
    if ffmpeg_exe and ffmpeg_exe.is_file():
        console.print(f"[green]Bundling FFmpeg:[/green] {ffmpeg_exe}")
        shutil.copy2(ffmpeg_exe, PORTABLE_DIR / "ffmpeg.exe")
        has_ffmpeg = True
    else:
        console.print("[yellow]Warning: ffmpeg.exe not found on system. FFmpeg will not be bundled.[/yellow]")

    if ffprobe_exe and ffprobe_exe.is_file():
        console.print(f"[green]Bundling FFprobe:[/green] {ffprobe_exe}")
        shutil.copy2(ffprobe_exe, PORTABLE_DIR / "ffprobe.exe")

    # Run Authenticode Code Signing for MSK Software Solutions
    sign_script = PROJECT_ROOT / "scripts" / "sign_windows_exe.ps1"
    if sign_script.exists():
        console.print("[cyan]Applying MSK Software Solutions digital signature...[/cyan]")
        for exe_target in [PORTABLE_DIR / "MSK-YTDL.exe", DIST_DIR / "MSK-YTDL.exe"]:
            if exe_target.exists():
                try:
                    subprocess.run(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(sign_script), "-ExePath", str(exe_target)],
                        check=False,
                    )
                except Exception as e:
                    console.print(f"[yellow]Signing warning for {exe_target.name}: {e}[/yellow]")

    # Create batch launcher and README
    create_portable_launcher(PORTABLE_DIR)
    create_readme(PORTABLE_DIR, has_ffmpeg=has_ffmpeg)

    # Ensure certificate installer and public certificate are in portable folder
    cert_file = PROJECT_ROOT / "MSK_Software_Solutions.cer"
    if cert_file.exists():
        shutil.copy2(cert_file, PORTABLE_DIR / "MSK_Software_Solutions.cer")

    # Compress into a shareable ZIP archive
    console.print(f"[cyan]Compressing portable folder into {ZIP_OUTPUT.name}...[/cyan]")
    if ZIP_OUTPUT.exists():
        ZIP_OUTPUT.unlink()

    with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(PORTABLE_DIR):
            for file in files:
                file_path = Path(root) / file
                archive_name = file_path.relative_to(DIST_DIR)
                zip_file.write(file_path, arcname=archive_name)

    return ZIP_OUTPUT


def main() -> int:
    console.print(
        Panel(
            "[bold cyan]MSK-YTDL Windows Executable & Portable Packager[/bold cyan]\n"
            "Builds a standalone, zero-dependency distribution you can share with friends and network.",
            border_style="cyan",
        )
    )

    if not ensure_pyinstaller():
        console.print("[bold red]Failed to ensure PyInstaller availability.[/bold red]")
        return 1

    # Check for --onefile flag in command line
    onefile = "--onefile" in sys.argv

    console.print("\n[bold cyan][Step 1/2][/bold cyan] Building Windows executable with PyInstaller...")
    build_success = build_executable(onefile=onefile)
    if not build_success:
        console.print("[bold red]Build process failed. Check output above for details.[/bold red]")
        return 2

    console.print("\n[bold cyan][Step 2/2][/bold cyan] Bundling FFmpeg, launchers, and creating ZIP package...")
    zip_path = package_distribution(onefile=onefile)
    if not zip_path or not zip_path.exists():
        console.print("[bold red]Packaging failed.[/bold red]")
        return 3

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)

    summary_table = Table(title="Build & Packaging Summary", border_style="green")
    summary_table.add_column("Artifact", style="bold white")
    summary_table.add_column("Location / Details", style="cyan")
    summary_table.add_column("Size", style="yellow")

    summary_table.add_row(
        "Portable Folder",
        str(PORTABLE_DIR),
        "Ready to run directly",
    )
    summary_table.add_row(
        "Shareable ZIP Archive",
        str(zip_path),
        f"{zip_size_mb:.1f} MB",
    )

    console.print("\n", summary_table)
    console.print(
        Panel(
            f"[bold green]SUCCESS![/bold green] Ready to share with your friends and network:\n\n"
            f"[bold white]File to share:[/bold white] [cyan]{zip_path}[/cyan]\n"
            f"[bold white]How friends use it:[/bold white]\n"
            f"  1. Send them the [cyan]{zip_path.name}[/cyan] file (via WhatsApp, Telegram, Google Drive, or email).\n"
            f"  2. They extract the zip.\n"
            f"  3. They double-click [bold white]Start_MSK_YTDL.bat[/bold white] or [bold white]MSK-YTDL.exe[/bold white].\n"
            f"  4. Works immediately on their PC with zero Python or FFmpeg installation required!",
            border_style="green",
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

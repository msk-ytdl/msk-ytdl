"""
Command-Line Interface and Interactive Terminal Menu for MSK-YTDL.

Provides both an interactive terminal menu for beginners and a complete,
scriptable command-line interface with argparse for advanced users.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from youtube_downloader import __version__
from youtube_downloader.config import (
    AppConfig,
    ensure_directory_writable,
    get_config_file_path,
    load_config,
    save_config,
)
from youtube_downloader.diagnostics import print_diagnostic_report
from youtube_downloader.downloader import (
    BatchDownloadResult,
    PlaylistDownloadResult,
    PlaylistMetadata,
    YoutubeDownloader,
)
from youtube_downloader.errors import (
    DependencyMissingError,
    DownloadInterruptedError,
    ValidationError,
    YTDLError,
)
from youtube_downloader.validators import (
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_AUDIO_QUALITIES,
    SUPPORTED_VIDEO_QUALITIES,
    parse_batch_urls_input,
    read_urls_from_file,
    validate_and_sanitize_youtube_url,
    validate_audio_format,
    validate_audio_quality,
    validate_video_quality,
    validate_youtube_playlist_url,
)

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

console = Console()

LEGAL_REMINDER = (
    "[bold yellow][AUTHORIZED USE REMINDER][/bold yellow]\n"
    "This application is strictly for downloading videos you own, have explicit permission to save, "
    "or are authorized under applicable service terms and copyright laws. "
    "No DRM circumvention or unauthorized access features are implemented."
)


def confirm_authorization_prompt(interactive: bool = True, flag_confirmed: bool = False) -> bool:
    """
    Ensure the user explicitly confirms authorization before a download begins.
    """
    if flag_confirmed:
        return True

    if not interactive or not sys.stdin.isatty():
        console.print(
            "[bold red]Permission confirmation required:[/bold red] "
            "In non-interactive mode, pass '--confirm-authorized' to confirm you have permission to download this content."
        )
        return False

    console.print(Panel(LEGAL_REMINDER, border_style="yellow"))
    try:
        confirmed = Confirm.ask(
            "[bold cyan]Do you confirm that you own this content or have explicit permission to download it?[/bold cyan]",
            default=False,
            console=console
        )
        return confirmed
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operation cancelled.[/yellow]")
        return False


def display_video_info(downloader: YoutubeDownloader, url: str) -> None:
    """Retrieve and display metadata in a rich format without downloading media."""
    try:
        with console.status("[bold cyan]Fetching video metadata from YouTube...[/bold cyan]"):
            meta = downloader.get_video_info(url)

        table = Table(title=f"[bold green]Video Information: {meta.title}[/bold green]", expand=True)
        table.add_column("Property", style="bold cyan", ratio=2)
        table.add_column("Details", ratio=5)

        table.add_row("Title", meta.title)
        table.add_row("Video ID", meta.video_id)
        table.add_row("Uploader", meta.uploader)
        table.add_row("Duration", meta.duration_formatted)
        table.add_row("Upload Date", meta.upload_date_formatted)
        table.add_row("Available Resolutions", ", ".join(meta.available_resolutions) or "Unknown")
        if meta.thumbnail_url:
            table.add_row("Thumbnail URL", meta.thumbnail_url)
        if meta.description_preview:
            table.add_row("Description Preview", meta.description_preview)

        console.print()
        console.print(table)
        console.print()
    except YTDLError as e:
        console.print(e.format_user_message())
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")


def display_formats_table(downloader: YoutubeDownloader, url: str) -> None:
    """Retrieve and display available formats table without downloading media."""
    try:
        with console.status("[bold cyan]Querying available media formats...[/bold cyan]"):
            formats = downloader.list_available_formats(url)

        table = Table(title="[bold green]Available Formats[/bold green]", show_header=True, expand=True)
        table.add_column("Format ID", style="bold", justify="center")
        table.add_column("Ext", justify="center")
        table.add_column("Resolution", justify="center")
        table.add_column("FPS", justify="center")
        table.add_column("Video Codec")
        table.add_column("Audio Codec")
        table.add_column("File Size", justify="right")
        table.add_column("Note")

        for f in formats:
            table.add_row(
                f.format_id,
                f.ext,
                f.resolution,
                str(f.fps) if f.fps else "-",
                f.vcodec,
                f.acodec,
                f.filesize_formatted,
                f.note
            )

        console.print()
        console.print(table)
        console.print()
    except YTDLError as e:
        console.print(e.format_user_message())
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")


def display_playlist_info(downloader: YoutubeDownloader, url: str) -> None:
    """Retrieve and display playlist overview and preview items without downloading."""
    try:
        with console.status("[bold cyan]Fetching playlist information from YouTube...[/bold cyan]"):
            meta = downloader.get_playlist_info(url)

        overview = Table(title=f"[bold green]Playlist Overview: {meta.title}[/bold green]", expand=True)
        overview.add_column("Property", style="bold cyan", ratio=2)
        overview.add_column("Details", ratio=5)

        overview.add_row("Title", meta.title)
        overview.add_row("Playlist ID", meta.playlist_id)
        overview.add_row("Uploader / Channel", meta.uploader)
        overview.add_row("Total Video Entries", str(meta.entries_count))

        console.print()
        console.print(overview)
        console.print()

        # Display preview table for first 15 items
        preview_count = min(15, len(meta.entries))
        if preview_count > 0:
            preview_table = Table(
                title=f"[bold cyan]Playlist Preview (First {preview_count} of {meta.entries_count} Videos)[/bold cyan]",
                expand=True
            )
            preview_table.add_column("#", justify="center", style="bold")
            preview_table.add_column("Video Title", ratio=4)
            preview_table.add_column("Duration", justify="center", ratio=1)
            preview_table.add_column("Video ID", justify="center", ratio=1)

            for entry in meta.entries[:preview_count]:
                preview_table.add_row(
                    str(entry.index),
                    entry.title,
                    entry.duration_formatted,
                    entry.video_id
                )

            console.print(preview_table)
            console.print()
    except YTDLError as e:
        console.print(e.format_user_message())
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")


def open_folder_in_explorer(folder_path: Path) -> None:
    """Open folder in Windows Explorer or default system file manager."""
    try:
        import subprocess
        resolved = folder_path.resolve()
        if sys.platform == "win32":
            subprocess.run(["explorer", str(resolved)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(resolved)], check=False)
        else:
            subprocess.run(["xdg-open", str(resolved)], check=False)
        console.print(f"[green]Opened folder in File Explorer:[/green] [underline]{resolved}[/underline]")
    except Exception as e:
        console.print(f"[yellow]Could not open folder:[/yellow] {e}")


def print_playlist_summary_table(result: PlaylistDownloadResult) -> None:
    """Render a clean summary panel for completed playlist downloads."""
    summary_text = (
        f"[bold]Playlist:[/bold] {result.title}\n"
        f"[bold]Total Videos in Playlist:[/bold] {result.total_entries}\n"
        f"[bold green]Downloaded in this run:[/bold green] {result.downloaded_count}\n"
        f"[bold]Target Directory:[/bold] {result.output_directory}"
    )
    if result.skipped_count > 0:
        summary_text += f"\n[bold cyan]Skipped (Already in Archive):[/bold cyan] {result.skipped_count}"
    if result.failed_count > 0:
        summary_text += f"\n[bold yellow]Failed / Unavailable Items:[/bold yellow] {result.failed_count}"

    console.print()
    console.print(Panel(
        summary_text,
        title="[bold green][PLAYLIST DOWNLOAD SUMMARY][/bold green]",
        border_style="green" if result.failed_count == 0 else "yellow"
    ))
    console.print()


def print_batch_summary_table(result: BatchDownloadResult) -> None:
    """Render a structured summary table for batch download results."""
    table = Table(title="[bold green]Batch Download Summary[/bold green]", expand=True)
    table.add_column("#", justify="center", style="bold", ratio=1)
    table.add_column("Status", justify="center", ratio=1)
    table.add_column("Title / Target URL", ratio=4)
    table.add_column("Details", ratio=4)

    for item in result.results:
        if item.skipped:
            status_badge = "[bold yellow][SKIPPED][/bold yellow]"
            detail = "Already recorded in download archive"
        elif item.success:
            status_badge = "[bold green][SUCCESS][/bold green]"
            detail = str(item.filepath) if item.filepath else "Saved"
        else:
            status_badge = "[bold red][FAILED][/bold red]"
            detail = item.error or "Unknown error"
        title_or_url = item.title or item.url
        table.add_row(str(item.index), status_badge, title_or_url, detail)

    console.print()
    console.print(table)
    console.print(
        f"[bold]Total:[/bold] {result.total} | "
        f"[bold green]Succeeded:[/bold green] {result.succeeded} | "
        f"[bold yellow]Skipped (Archived):[/bold yellow] {result.skipped} | "
        f"[bold red]Failed:[/bold red] {result.failed}\n"
    )


def interactive_resolution_choice() -> str:
    """Prompt user to choose maximum resolution."""
    console.print("\n[bold]Select Maximum Video Resolution:[/bold]")
    console.print("  1. Best available (Source Quality)")
    console.print("  2. 2160p (4K UHD)")
    console.print("  3. 1440p (2K QHD)")
    console.print("  4. 1080p (Full HD)")
    console.print("  5. 720p (HD)")
    console.print("  6. 480p (SD)")
    console.print("  7. 360p")

    choices = {
        "1": "best",
        "2": "2160p",
        "3": "1440p",
        "4": "1080p",
        "5": "720p",
        "6": "480p",
        "7": "360p",
    }
    ans = Prompt.ask("Enter resolution option [1-7]", default="1", choices=list(choices.keys()))
    return choices[ans]


def interactive_audio_quality_choice() -> str:
    """Prompt user to choose MP3 audio quality / bitrate."""
    console.print("\n[bold]Select MP3 Audio Bitrate:[/bold]")
    console.print("  1. 320 kbps (Very High)")
    console.print("  2. 256 kbps (High)")
    console.print("  3. 192 kbps (Standard / Recommended)")
    console.print("  4. 128 kbps (Compact)")

    choices = {
        "1": "320",
        "2": "256",
        "3": "192",
        "4": "128",
    }
    ans = Prompt.ask("Enter bitrate option [1-4]", default="3", choices=list(choices.keys()))
    return choices[ans]


def view_configuration(config: AppConfig) -> None:
    """Display current active configuration in a table."""
    table = Table(title="[bold green]MSK-YTDL Current Configuration[/bold green]", expand=True)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value")

    table.add_row("Config File Location", str(get_config_file_path()))
    table.add_row("Download Directory", config.download_directory)
    table.add_row("Resolved Path", str(config.get_resolved_download_path()))
    table.add_row("Default Video Quality", config.default_video_quality)
    table.add_row("Default Audio Format", config.default_audio_format)
    table.add_row("Default Audio Bitrate", f"{config.default_audio_quality} kbps")
    table.add_row("Show Progress Indicator", str(config.show_progress))
    table.add_row("Max Retries", str(config.max_retries))
    table.add_row("Create Playlist Subfolder", str(config.create_playlist_subfolder))
    table.add_row("Playlist Prompt Threshold", f"{config.max_playlist_items_prompt} videos")

    archive_status = "Enabled" if config.use_download_archive else "Disabled"
    table.add_row("Smart Download Archive", f"{archive_status} ({config.get_resolved_archive_path()})")
    thumb_status = "Enabled (Embedded into MP3/audio)" if config.embed_thumbnail else "Disabled"
    table.add_row("Audio Album Artwork", thumb_status)
    meta_status = "Enabled (ID3 tags / chapters)" if config.embed_metadata else "Disabled"
    table.add_row("Audio & Video Metadata", meta_status)

    console.print()
    console.print(table)
    console.print()


def change_download_folder(config: AppConfig) -> None:
    """Prompt user to enter and validate a new download folder."""
    console.print(f"\nCurrent download folder: [cyan]{config.download_directory}[/cyan]")
    new_dir = Prompt.ask("Enter new download directory path (or press Enter to cancel)", default="")
    if not new_dir.strip():
        console.print("[yellow]Folder change cancelled.[/yellow]")
        return

    try:
        resolved = Path(os.path.expanduser(new_dir.strip())).resolve()
        ensure_directory_writable(resolved)
        config.download_directory = str(resolved)
        save_config(config)
        console.print(f"[bold green][SUCCESS] Download folder updated to:[/bold green] {resolved}")
    except Exception as e:
        console.print(f"[bold red]Failed to update folder:[/bold red] {e}")


def show_packaging_menu() -> None:
    """Display sharing, EXE packaging, and Android APK deployment options."""
    while True:
        console.print()
        console.print(Panel(
            "[bold cyan]Share & Install MSK-YTDL on Other Devices[/bold cyan]\n"
            "Create standalone packages so your friends and network can run MSK-YTDL.",
            border_style="cyan"
        ))
        console.print("  [bold]1.[/bold] Build Standalone Windows Portable Package (.EXE & .ZIP)")
        console.print("  [bold]2.[/bold] Android: How to Build & Install Android APK (.APK)")
        console.print("  [bold]3.[/bold] Android: 1-Click Termux Mobile Setup (Instant)")
        console.print("  [bold]0.[/bold] Back to Main Menu")
        console.print()

        try:
            p_choice = Prompt.ask("[bold]Select an option[/bold]", choices=["0", "1", "2", "3"])
        except (KeyboardInterrupt, EOFError):
            break

        if p_choice == "0":
            break
        elif p_choice == "1":
            console.print("\n[cyan]Starting Windows Standalone Packager...[/cyan]")
            try:
                build_script = Path(__file__).resolve().parent.parent / "build_exe.py"
                if build_script.exists():
                    subprocess.run([sys.executable, str(build_script)], check=False)
                else:
                    console.print("[bold red]build_exe.py not found in project root.[/bold red]")
            except Exception as e:
                console.print(f"[bold red]Failed to execute packager:[/bold red] {e}")
        elif p_choice == "2":
            console.print(Panel(
                "[bold green]Android APK (.APK) Generation Guide[/bold green]\n\n"
                "1. Push this project to GitHub (or your own repo).\n"
                "2. In GitHub, go to [bold]Actions[/bold] -> [bold]Build Android APK[/bold].\n"
                "3. Click [bold]Run workflow[/bold] (takes ~5 minutes in the cloud for free).\n"
                "4. Download the generated [cyan]MSK-YTDL-Android-APK.zip[/cyan] under Artifacts.\n"
                "5. Send the [bold].apk[/bold] file to your phone and tap to install!\n\n"
                "[dim]For complete details, see docs/MOBILE_AND_APK_GUIDE.md[/dim]",
                border_style="green"
            ))
        elif p_choice == "3":
            console.print(Panel(
                "[bold yellow]Android 1-Click Termux Setup (Fastest - No Build Needed)[/bold yellow]\n\n"
                "Your friends can run MSK-YTDL natively on any Android phone:\n"
                "1. Install [bold]Termux[/bold] from F-Droid (free).\n"
                "2. Open Termux and run:\n"
                "   [cyan]curl -sSL https://raw.githubusercontent.com/.../install_android.sh | bash[/cyan]\n"
                "   (Or copy the script: [bold]scripts/install_android_termux.sh[/bold])\n"
                "3. Downloads will automatically save into [bold]/sdcard/Download/YouTube[/bold]!\n"
                "4. Videos and MP3s will show up directly in Android Gallery and Music players.",
                border_style="yellow"
            ))

        try:
            Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")
        except (KeyboardInterrupt, EOFError):
            break


def interactive_menu(config: AppConfig, debug: bool = False) -> None:
    """Run interactive terminal menu loop."""
    downloader = YoutubeDownloader(config=config, console=console, debug=debug)
    menu_choices = [str(i) for i in range(16)]

    while True:
        console.print()
        console.print(Panel(
            f"[bold cyan]MSK-YTDL: Reliable YouTube Downloader v{__version__}[/bold cyan]\n"
            "[italic white]Download only content you own or are authorized to save.[/italic white]",
            border_style="cyan"
        ))
        console.print("  [bold]1.[/bold] Download Video - Best Available Quality")
        console.print("  [bold]2.[/bold] Download Video - Select Maximum Resolution")
        console.print("  [bold]3.[/bold] Download Audio - MP3 (With Album Art & Metadata)")
        console.print("  [bold]4.[/bold] Download Audio - Best Available Original Format")
        console.print("  [bold]5.[/bold] Download Playlist - Video (Best Quality or Resolution)")
        console.print("  [bold]6.[/bold] Download Playlist - Audio (MP3 or Original)")
        console.print("  [bold]7.[/bold] Batch Download - Multiple URLs or From File")
        console.print("  [bold]8.[/bold] Show Video or Playlist Information")
        console.print("  [bold]9.[/bold] List Available Formats")
        console.print("  [bold]10.[/bold] Check Application and Dependency Health")
        console.print("  [bold]11.[/bold] View Configuration")
        console.print("  [bold]12.[/bold] Change Download Folder")
        console.print("  [bold]13.[/bold] Open Download Folder in File Explorer")
        console.print("  [bold]14.[/bold] Package for Friends (Windows .EXE / Android APK Guide)")
        console.print("  [bold]15.[/bold] Launch Web UI (VidMate-Style Mobile/Browser App)")
        console.print("  [bold]0.[/bold] Exit")
        console.print()

        try:
            choice = Prompt.ask("[bold]Select an option[/bold]", choices=menu_choices)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting MSK-YTDL. Goodbye![/yellow]")
            break

        if choice == "0":
            console.print("[green]Exiting. Thank you for using MSK-YTDL![/green]")
            break

        elif choice in ("1", "2"):
            try:
                url = Prompt.ask("\nEnter YouTube Video URL")
                quality = "best" if choice == "1" else interactive_resolution_choice()

                if not confirm_authorization_prompt(interactive=True):
                    console.print("[yellow]Download aborted: Authorization not confirmed.[/yellow]")
                    continue

                console.print(f"\n[cyan]Starting download (Quality: {quality})...[/cyan]")
                saved_path = downloader.download_video(url, quality=quality)
                if saved_path:
                    console.print(f"\n[bold green][SUCCESS] Download successful![/bold green]")
                    console.print(f"[green]Saved to:[/green] {saved_path}")
                else:
                    console.print("\n[bold yellow][SKIPPED][/bold yellow] Video already recorded in download archive.")

            except (KeyboardInterrupt, DownloadInterruptedError):
                console.print("\n[yellow]Download was cancelled.[/yellow]")
            except YTDLError as e:
                console.print(f"\n{e.format_user_message()}")
            except Exception as e:
                console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")

        elif choice in ("3", "4"):
            try:
                url = Prompt.ask("\nEnter YouTube Video URL")
                if choice == "3":
                    audio_fmt = "mp3"
                    bitrate = interactive_audio_quality_choice()
                else:
                    audio_fmt = "best"
                    bitrate = "192"

                if not confirm_authorization_prompt(interactive=True):
                    console.print("[yellow]Download aborted: Authorization not confirmed.[/yellow]")
                    continue

                console.print(f"\n[cyan]Starting audio extraction ({audio_fmt.upper()})...[/cyan]")
                saved_path = downloader.download_audio(url, audio_format=audio_fmt, audio_quality=bitrate)
                if saved_path:
                    console.print(f"\n[bold green][SUCCESS] Audio download successful![/bold green]")
                    console.print(f"[green]Saved to:[/green] {saved_path}")
                else:
                    console.print("\n[bold yellow][SKIPPED][/bold yellow] Audio already recorded in download archive.")

            except (KeyboardInterrupt, DownloadInterruptedError):
                console.print("\n[yellow]Audio download was cancelled.[/yellow]")
            except YTDLError as e:
                console.print(f"\n{e.format_user_message()}")
            except Exception as e:
                console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")

        elif choice in ("5", "6"):
            try:
                url = Prompt.ask("\nEnter YouTube Playlist URL")
                with console.status("[cyan]Retrieving playlist overview...[/cyan]"):
                    meta = downloader.get_playlist_info(url)

                console.print(f"\n[bold]Detected Playlist:[/bold] [green]{meta.title}[/green]")
                console.print(f"[bold]Channel / Uploader:[/bold] {meta.uploader}")
                console.print(f"[bold]Total Videos in Playlist:[/bold] {meta.entries_count}")

                if meta.entries_count > config.max_playlist_items_prompt:
                    if not Confirm.ask(
                        f"\n[yellow]This playlist contains {meta.entries_count} videos. Do you wish to continue?[/yellow]",
                        default=True
                    ):
                        console.print("[yellow]Playlist download cancelled.[/yellow]")
                        continue

                scope_choice = Prompt.ask(
                    "\nDownload scope: 1. All videos in playlist, 2. Range (e.g. 1 to 10)",
                    choices=["1", "2"],
                    default="1"
                )
                pl_start, pl_end = None, None
                if scope_choice == "2":
                    try:
                        pl_start = int(Prompt.ask("Enter start index (e.g. 1)", default="1"))
                        pl_end = int(Prompt.ask(f"Enter end index (max {meta.entries_count})", default=str(min(meta.entries_count, 10))))
                    except ValueError:
                        console.print("[yellow]Invalid indices provided, downloading all videos.[/yellow]")
                        pl_start, pl_end = None, None

                if choice == "5":
                    mode = "video"
                    quality = interactive_resolution_choice()
                    audio_fmt, bitrate = "mp3", "192"
                else:
                    mode = "audio"
                    quality = "best"
                    audio_type_choice = Prompt.ask(
                        "Audio format: 1. MP3 conversion, 2. Best original stream",
                        choices=["1", "2"],
                        default="1"
                    )
                    if audio_type_choice == "1":
                        audio_fmt = "mp3"
                        bitrate = interactive_audio_quality_choice()
                    else:
                        audio_fmt = "best"
                        bitrate = "192"

                if not confirm_authorization_prompt(interactive=True):
                    console.print("[yellow]Download aborted: Authorization not confirmed.[/yellow]")
                    continue

                console.print(f"\n[cyan]Starting playlist download for '{meta.title}'...[/cyan]")
                res = downloader.download_playlist(
                    url,
                    mode=mode,
                    quality=quality,
                    audio_format=audio_fmt,
                    audio_quality=bitrate,
                    playlist_start=pl_start,
                    playlist_end=pl_end
                )
                print_playlist_summary_table(res)

            except (KeyboardInterrupt, DownloadInterruptedError):
                console.print("\n[yellow]Playlist download was cancelled.[/yellow]")
            except YTDLError as e:
                console.print(f"\n{e.format_user_message()}")
            except Exception as e:
                console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")

        elif choice == "7":
            try:
                batch_type = Prompt.ask(
                    "\nBatch Input Option:\n  1. Enter multiple URLs directly\n  2. Load URLs from a text file\nSelect",
                    choices=["1", "2"],
                    default="1"
                )
                urls: List[str] = []
                if batch_type == "1":
                    raw_input_text = Prompt.ask("\nEnter YouTube URLs (separated by spaces or commas)")
                    urls = parse_batch_urls_input(raw_input_text)
                else:
                    file_path = Prompt.ask("\nEnter path to text file containing URLs")
                    urls = read_urls_from_file(file_path)

                if not urls:
                    console.print("[yellow]No valid URLs provided. Aborting batch download.[/yellow]")
                    continue

                console.print(f"\n[bold green]Found {len(urls)} URLs to download.[/bold green]")
                for idx, u in enumerate(urls, 1):
                    console.print(f"  {idx}. {u}")

                batch_mode_choice = Prompt.ask("\nSelect Mode: 1. Video, 2. Audio", choices=["1", "2"], default="1")
                if batch_mode_choice == "1":
                    b_mode = "video"
                    b_quality = interactive_resolution_choice()
                    b_audio_fmt, b_bitrate = "mp3", "192"
                else:
                    b_mode = "audio"
                    b_quality = "best"
                    b_audio_fmt = "mp3"
                    b_bitrate = interactive_audio_quality_choice()

                if not confirm_authorization_prompt(interactive=True):
                    console.print("[yellow]Download aborted: Authorization not confirmed.[/yellow]")
                    continue

                console.print(f"\n[cyan]Starting batch download of {len(urls)} items...[/cyan]")
                b_res = downloader.download_batch(
                    urls,
                    mode=b_mode,
                    quality=b_quality,
                    audio_format=b_audio_fmt,
                    audio_quality=b_bitrate
                )
                print_batch_summary_table(b_res)

            except (KeyboardInterrupt, DownloadInterruptedError):
                console.print("\n[yellow]Batch download was cancelled.[/yellow]")
            except YTDLError as e:
                console.print(f"\n{e.format_user_message()}")
            except Exception as e:
                console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")

        elif choice == "8":
            try:
                url = Prompt.ask("\nEnter YouTube Video or Playlist URL")
                if "list=" in url or "/playlist" in url:
                    display_playlist_info(downloader, url)
                else:
                    display_video_info(downloader, url)
            except (KeyboardInterrupt, EOFError):
                pass

        elif choice == "9":
            try:
                url = Prompt.ask("\nEnter YouTube Video URL")
                display_formats_table(downloader, url)
            except (KeyboardInterrupt, EOFError):
                pass

        elif choice == "10":
            print_diagnostic_report(console)

        elif choice == "11":
            view_configuration(config)

        elif choice == "12":
            change_download_folder(config)

        elif choice == "13":
            open_folder_in_explorer(config.get_resolved_download_path())

        elif choice == "14":
            show_packaging_menu()

        elif choice == "15":
            from youtube_downloader.web_server import run_web_server
            run_web_server()

        # Allow user to pause and view result before returning to menu
        if choice != "0":
            try:
                Prompt.ask("\n[dim]Press Enter to return to main menu...[/dim]", default="")
            except (KeyboardInterrupt, EOFError):
                pass


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="youtube_downloader",
        description="MSK-YTDL: Reliable Python CLI-Based YouTube Video Downloader for authorized media."
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run system and dependency health checks without downloading."
    )
    parser.add_argument(
        "--package-windows",
        action="store_true",
        help="Build standalone Windows executable (.exe) and shareable ZIP archive."
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the local VidMate-style browser web application."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8899,
        help="Port to bind the local web application server to (default: 8899)."
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        help="YouTube video or playlist URL to process."
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        help="Multiple YouTube video URLs to download in batch."
    )
    parser.add_argument(
        "--batch-file", "-b",
        type=str,
        help="Path to a text file containing YouTube URLs (one per line)."
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Process the target URL as a full playlist."
    )
    parser.add_argument(
        "--playlist-start",
        type=int,
        help="Playlist start index (1-based)."
    )
    parser.add_argument(
        "--playlist-end",
        type=int,
        help="Playlist end index (1-based)."
    )
    parser.add_argument(
        "--playlist-items",
        type=str,
        help="Playlist item indices or ranges to download (e.g. '1,3-5,8')."
    )
    parser.add_argument(
        "--no-subfolder",
        action="store_true",
        help="Do not create a dedicated subfolder for playlist downloads."
    )
    parser.add_argument(
        "--archive-file",
        type=str,
        help="Custom path to download archive file to record downloaded video IDs."
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Disable download archive check (force re-download previously downloaded videos)."
    )
    parser.add_argument(
        "--no-embed-thumbnail",
        action="store_true",
        help="Disable embedding video thumbnail as album cover art into audio files."
    )
    parser.add_argument(
        "--no-embed-metadata",
        action="store_true",
        help="Disable embedding ID3 tags, chapters, and metadata."
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["video", "audio"],
        default="video",
        help="Download mode: 'video' (default) or 'audio'."
    )
    parser.add_argument(
        "--quality", "-q",
        choices=SUPPORTED_VIDEO_QUALITIES,
        default="best",
        help=f"Maximum video resolution limit. Choices: {', '.join(SUPPORTED_VIDEO_QUALITIES)}."
    )
    parser.add_argument(
        "--audio-format",
        choices=SUPPORTED_AUDIO_FORMATS,
        default="mp3",
        help="Audio format: 'mp3' or 'best' (original stream)."
    )
    parser.add_argument(
        "--audio-quality",
        choices=SUPPORTED_AUDIO_QUALITIES,
        default="192",
        help="MP3 audio bitrate in kbps. Choices: 128, 192, 256, 320."
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        help="Custom destination directory for downloaded files."
    )
    parser.add_argument(
        "--info", "-i",
        action="store_true",
        help="Fetch and display video or playlist metadata only (no media downloaded)."
    )
    parser.add_argument(
        "--list-formats", "-l",
        action="store_true",
        help="List available video and audio streams (no media downloaded)."
    )
    parser.add_argument(
        "--confirm-authorized", "--yes", "-y",
        action="store_true",
        help="Explicitly confirm authorization to download under applicable terms."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debugging output."
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for MSK-YTDL CLI application.

    Returns exit code:
      0: Success
      1: Download / extraction failure
      2: Argument validation error
      3: Dependency check failure
      4: User cancelled or authorization denied
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 1. Health check flag
    if args.check:
        passed = print_diagnostic_report(console)
        return 0 if passed else 3

    # 2. Package Windows flag
    if args.package_windows:
        try:
            from build_exe import main as build_main
            return build_main()
        except Exception as e:
            console.print(f"[bold red]Packaging error:[/bold red] {e}")
            return 1

    # 3. Web UI flag
    if args.web:
        try:
            from youtube_downloader.web_server import run_web_server
            run_web_server(port=args.port)
            return 0
        except Exception as e:
            console.print(f"[bold red]Web server error:[/bold red] {e}")
            return 1

    config = load_config()
    debug = args.debug

    # Smart archive and embedding overrides from CLI flags
    use_archive = False if args.no_archive else None
    archive_path = Path(os.path.expanduser(args.archive_file)).resolve() if args.archive_file else None
    embed_thumbnail = False if args.no_embed_thumbnail else None
    embed_metadata = False if args.no_embed_metadata else None

    # Determine batch URLs if provided via flag or file
    batch_urls: Optional[List[str]] = None
    if args.batch_file:
        try:
            batch_urls = read_urls_from_file(args.batch_file)
        except Exception as e:
            console.print(f"[bold red]Batch File Error:[/bold red] {e}")
            return 2
    elif args.urls:
        batch_urls = args.urls

    # Check if running in non-interactive CLI argument mode
    is_cli_mode = bool(args.url or batch_urls or args.info or args.list_formats)

    if not is_cli_mode:
        # If no arguments provided and interactive terminal, launch menu
        if sys.stdin.isatty():
            interactive_menu(config=config, debug=debug)
            return 0
        else:
            parser.print_help()
            return 0

    # Determine custom output directory
    target_dir: Optional[Path] = None
    if args.output_dir:
        try:
            target_dir = Path(os.path.expanduser(args.output_dir)).resolve()
            ensure_directory_writable(target_dir)
        except Exception as e:
            console.print(f"[bold red]Output Directory Error:[/bold red] {e}")
            return 2

    downloader = YoutubeDownloader(config=config, console=console, debug=debug)

    # 2. Batch download execution
    if batch_urls:
        if not confirm_authorization_prompt(interactive=sys.stdin.isatty(), flag_confirmed=args.confirm_authorized):
            return 4

        try:
            console.print(f"[cyan]Processing batch download of {len(batch_urls)} items...[/cyan]")
            batch_res = downloader.download_batch(
                batch_urls,
                mode=args.mode,
                quality=args.quality,
                audio_format=args.audio_format,
                audio_quality=args.audio_quality,
                output_dir=target_dir,
                use_archive=use_archive,
                archive_path=archive_path,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
            )
            print_batch_summary_table(batch_res)
            return 0 if batch_res.failed == 0 else 1
        except (KeyboardInterrupt, DownloadInterruptedError):
            console.print("\n[yellow]Batch operation cancelled by user.[/yellow]")
            return 4
        except Exception as e:
            console.print(f"\n[bold red]Batch failure:[/bold red] {e}")
            return 1

    # Single URL operations require --url
    if not args.url:
        console.print("[bold red]Argument Error:[/bold red] '--url', '--urls', or '--batch-file' is required.")
        return 2

    # Check if target is a playlist
    is_playlist = args.playlist or ("/playlist?" in args.url and "list=" in args.url)

    # Info-only mode
    if args.info:
        if is_playlist:
            display_playlist_info(downloader, args.url)
        else:
            display_video_info(downloader, args.url)
        return 0

    # List formats mode (single video only)
    if args.list_formats:
        display_formats_table(downloader, args.url)
        return 0

    # Confirmation before download
    is_interactive = sys.stdin.isatty()
    confirmed = confirm_authorization_prompt(interactive=is_interactive, flag_confirmed=args.confirm_authorized)
    if not confirmed:
        return 4

    try:
        if is_playlist:
            console.print(f"[cyan]Starting playlist download in {args.mode} mode...[/cyan]")
            pl_res = downloader.download_playlist(
                args.url,
                mode=args.mode,
                quality=args.quality,
                audio_format=args.audio_format,
                audio_quality=args.audio_quality,
                playlist_start=args.playlist_start,
                playlist_end=args.playlist_end,
                playlist_items=args.playlist_items,
                output_dir=target_dir,
                create_subfolder=not args.no_subfolder,
                use_archive=use_archive,
                archive_path=archive_path,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
            )
            print_playlist_summary_table(pl_res)
            return 0 if pl_res.failed_count == 0 else 1

        elif args.mode == "video":
            quality = validate_video_quality(args.quality)
            console.print(f"[cyan]Downloading video at max quality '{quality}'...[/cyan]")
            saved_path = downloader.download_video(
                args.url,
                quality=quality,
                output_dir=target_dir,
                use_archive=use_archive,
                archive_path=archive_path,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
            )
            if saved_path:
                console.print(f"[bold green][SUCCESS] Download complete:[/bold green] {saved_path}")
            else:
                console.print("[bold yellow][SKIPPED][/bold yellow] Video already recorded in download archive.")
            return 0

        elif args.mode == "audio":
            audio_fmt = validate_audio_format(args.audio_format)
            audio_quality = validate_audio_quality(args.audio_quality)
            console.print(f"[cyan]Downloading audio ({audio_fmt}, {audio_quality} kbps)...[/cyan]")
            saved_path = downloader.download_audio(
                args.url,
                audio_format=audio_fmt,
                audio_quality=audio_quality,
                output_dir=target_dir,
                use_archive=use_archive,
                archive_path=archive_path,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
            )
            if saved_path:
                console.print(f"[bold green][SUCCESS] Audio download complete:[/bold green] {saved_path}")
            else:
                console.print("[bold yellow][SKIPPED][/bold yellow] Audio already recorded in download archive.")
            return 0

        else:
            console.print(f"[bold red]Invalid mode:[/bold red] {args.mode}")
            return 2

    except (KeyboardInterrupt, DownloadInterruptedError):
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        return 4
    except YTDLError as e:
        console.print(f"\n{e.format_user_message()}")
        if debug:
            console.print_exception()
        return 1
    except Exception as e:
        console.print(f"\n[bold red]Unhandled error:[/bold red] {e}")
        if debug:
            console.print_exception()
        return 1


if __name__ == "__main__":
    sys.exit(main())

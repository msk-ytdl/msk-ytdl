"""
Rich progress bar integration and custom logger for yt-dlp in MSK-YTDL.

Provides smooth, non-duplicating terminal progress displays, handling unknown totals,
calculating speeds, and tracking FFmpeg post-processing stages safely.
"""

from typing import Any, Dict, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


class YTDLLogger:
    """
    Custom logger for yt-dlp to route messages cleanly through Rich Console.

    Suppresses noisy extraction traces in standard mode while preserving
    detailed diagnostic output when debug mode is enabled.
    """

    def __init__(self, console: Optional[Console] = None, debug: bool = False):
        self.console = console or Console()
        self.debug_mode = debug
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.archived_ids: list[str] = []

    def debug(self, msg: str) -> None:
        """Handle debug messages from yt-dlp."""
        if "has already been recorded in the archive" in msg or "has already been downloaded and recorded in the archive" in msg:
            self.archived_ids.append(msg.strip())
        if self.debug_mode:
            # Strip carriage returns and sanitize
            cleaned = msg.strip()
            if cleaned:
                self.console.print(f"[dim grey]{cleaned}[/dim grey]")

    def info(self, msg: str) -> None:
        """Handle informational messages from yt-dlp."""
        if "has already been recorded in the archive" in msg or "has already been downloaded and recorded in the archive" in msg:
            self.archived_ids.append(msg.strip())
        if self.debug_mode:
            cleaned = msg.strip()
            if cleaned:
                self.console.print(f"[blue]{cleaned}[/blue]")

    def warning(self, msg: str) -> None:
        """Handle warnings from yt-dlp."""
        cleaned = msg.strip()
        if cleaned:
            self.warnings.append(cleaned)
            if self.debug_mode:
                self.console.print(f"[bold yellow]Warning:[/bold yellow] {cleaned}")

    def error(self, msg: str) -> None:
        """Handle errors from yt-dlp."""
        cleaned = msg.strip()
        if cleaned:
            self.errors.append(cleaned)
            if self.debug_mode:
                self.console.print(f"[bold red]Error:[/bold red] {cleaned}")


class DownloadProgressManager:
    """
    Manages Rich Progress lifecycle connected to yt-dlp progress and postprocessor hooks.
    """

    def __init__(self, console: Optional[Console] = None, enabled: bool = True):
        self.console = console or Console()
        self.enabled = enabled
        self.progress: Optional[Progress] = None
        self.task_id: Optional[TaskID] = None
        self._finished = False
        self.current_filename: Optional[str] = None

    def __enter__(self) -> "DownloadProgressManager":
        if self.enabled:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}[/bold cyan]"),
                BarColumn(bar_width=35),
                TaskProgressColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                TextColumn("[yellow]{task.fields[stage]}[/yellow]"),
                console=self.console,
                transient=True,
            )
            self.progress.start()
            self.task_id = self.progress.add_task(
                "Starting download...",
                total=None,
                stage=""
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.progress:
            try:
                self.progress.stop()
            except Exception:
                pass
            self.progress = None

    def progress_hook(self, d: Dict[str, Any]) -> None:
        """
        yt-dlp download progress callback hook.

        Safely handles missing values, unknown total sizes, and state transitions
        without raising exceptions.
        """
        if not self.enabled or not self.progress or self.task_id is None:
            return

        try:
            status = d.get("status")

            if status == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                # Some streams supply total_bytes, others total_bytes_estimate
                total = d.get("total_bytes") or d.get("total_bytes_estimate")

                filename = d.get("filename", "")
                if filename and filename != self.current_filename:
                    self.current_filename = filename
                    self.progress.reset(self.task_id)

                display_filename = filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                if len(display_filename) > 35:
                    display_filename = display_filename[:32] + "..."

                description = f"Downloading {display_filename}" if display_filename else "Downloading video..."

                # Safely update progress without dividing by zero
                self.progress.update(
                    self.task_id,
                    description=description,
                    completed=downloaded,
                    total=total,
                    stage="Streaming"
                )

            elif status == "finished":
                self._finished = True
                self.progress.update(
                    self.task_id,
                    description="Download complete",
                    stage="Processing"
                )

        except Exception:
            # Crucial: Progress hook errors must never crash the download process
            pass

    def postprocessor_hook(self, d: Dict[str, Any]) -> None:
        """
        yt-dlp post-processor callback hook (for FFmpeg audio extraction/merging).
        """
        if not self.enabled or not self.progress or self.task_id is None:
            return

        try:
            status = d.get("status")
            pp_name = d.get("postprocessor", "FFmpeg")

            if status == "started":
                self.progress.update(
                    self.task_id,
                    description=f"Processing with {pp_name}...",
                    stage="Post-processing"
                )
            elif status == "finished":
                self.progress.update(
                    self.task_id,
                    description="Post-processing complete",
                    stage="Finalizing"
                )
        except Exception:
            pass

"""
Core download engine integrating yt-dlp for MSK-YTDL.

Handles metadata extraction, format resolution expressions, safe stream merging,
audio conversion via FFmpeg, resumable downloads, and comprehensive error mapping.
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yt_dlp
from rich.console import Console

from youtube_downloader.config import AppConfig, ensure_directory_writable, load_config
from youtube_downloader.diagnostics import find_ffmpeg_executable
from youtube_downloader.errors import (
    DependencyMissingError,
    DownloadInterruptedError,
    OutputDirectoryError,
    YTDLError,
    classify_ytdl_error,
)
from youtube_downloader.progress import DownloadProgressManager, YTDLLogger
from youtube_downloader.validators import (
    validate_and_sanitize_youtube_url,
    validate_audio_format,
    validate_audio_quality,
    validate_video_quality,
    validate_youtube_playlist_url,
)

# Output filename templates incorporating video ID and character boundary protection
OUTPUT_FILENAME_TEMPLATE = "%(title).180B [%(id)s].%(ext)s"
PLAYLIST_FILENAME_TEMPLATE = "%(playlist_index|0)02d - %(title).150B [%(id)s].%(ext)s"


def sanitize_folder_name(name: str) -> str:
    """Sanitize directory name for Windows filesystem compliance."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')
    return cleaned[:100] if cleaned else "Playlist"


@dataclass
class VideoMetadata:
    """Structured container for video metadata."""
    video_id: str
    title: str
    uploader: str
    channel_url: Optional[str]
    duration_seconds: Optional[int]
    duration_formatted: str
    upload_date_formatted: str
    thumbnail_url: Optional[str]
    description_preview: str
    available_resolutions: List[str]
    raw_info: Dict[str, Any]


@dataclass
class PlaylistEntryPreview:
    """Preview summary for a single item in a playlist."""
    index: int
    title: str
    video_id: str
    url: str
    duration_formatted: str


@dataclass
class PlaylistMetadata:
    """Structured container for playlist metadata."""
    playlist_id: str
    title: str
    uploader: str
    entries_count: int
    entries: List[PlaylistEntryPreview]
    raw_info: Dict[str, Any]


@dataclass
class ItemDownloadResult:
    """Download result for a single item in a batch."""
    index: int
    url: str
    title: Optional[str]
    success: bool
    filepath: Optional[Path] = None
    error: Optional[str] = None
    skipped: bool = False


@dataclass
class BatchDownloadResult:
    """Consolidated summary for a batch download run."""
    total: int
    succeeded: int
    failed: int
    results: List[ItemDownloadResult]
    skipped: int = 0


@dataclass
class PlaylistDownloadResult:
    """Consolidated summary for a playlist download run."""
    playlist_id: str
    title: str
    total_entries: int
    downloaded_count: int
    failed_count: int
    output_directory: Path
    failed_items: List[Tuple[int, str, str]]
    skipped_count: int = 0


@dataclass
class FormatEntry:
    """Structured container for format listing details."""
    format_id: str
    ext: str
    resolution: str
    vcodec: str
    acodec: str
    filesize_formatted: str
    fps: Optional[float]
    note: str


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS string."""
    if not seconds or seconds < 0:
        return "Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_bytes(num_bytes: Optional[int]) -> str:
    """Format byte count to human-readable string (KiB, MiB, GiB)."""
    if not num_bytes or num_bytes <= 0:
        return "Unknown"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PiB"


def get_video_format_selector(max_resolution: str) -> str:
    """
    Construct yt-dlp format selector for video downloads.

    If a maximum resolution is chosen (e.g. 1080p), the selector limits height
    while prioritizing the best video stream plus best audio stream, falling back
    gracefully to combined streams or lower resolutions.
    """
    res = max_resolution.lower().strip()
    if res == "best":
        return "bestvideo*+bestaudio/best"

    # Extract integer height (e.g. '1080p' -> 1080)
    height_str = res.rstrip("p")
    try:
        height = int(height_str)
        # bestvideo*[height<=?{height}]+bestaudio/best[height<=?{height}]/best
        return f"bestvideo*[height<=?{height}]+bestaudio/best[height<=?{height}]/best"
    except ValueError:
        return "bestvideo*+bestaudio/best"


class YoutubeDownloader:
    """
    Primary interface for fetching metadata, listing formats, and downloading YouTube content.
    """

    def __init__(self, config: Optional[AppConfig] = None, console: Optional[Console] = None, debug: bool = False):
        self.config = config or load_config()
        self.console = console or Console()
        self.debug = debug

    def _build_base_ydl_opts(
        self,
        output_dir: Path,
        progress_manager: Optional[DownloadProgressManager] = None,
        logger: Optional[YTDLLogger] = None,
        is_playlist: bool = False,
        filename_template: Optional[str] = None,
        use_archive: Optional[bool] = None,
        archive_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Construct standard base yt-dlp options enforcing reliability and security."""
        template = filename_template or (PLAYLIST_FILENAME_TEMPLATE if is_playlist else OUTPUT_FILENAME_TEMPLATE)
        outtmpl_path = str(output_dir / template)

        opts: Dict[str, Any] = {
            "outtmpl": outtmpl_path,
            "outtmpl_na_placeholder": "NA",
            "noplaylist": not is_playlist,
            "continuedl": True,  # Support resuming interrupted downloads
            "nooverwrites": False,  # Allow resume or safe re-check
            "windowsfilenames": True,  # Sanitize filenames for Windows filesystem
            "retries": self.config.max_retries,
            "fragment_retries": self.config.max_retries,
            "socket_timeout": 30,
            "quiet": not self.debug,
            "no_warnings": not self.debug,
            "cachedir": False,  # Prevent stale cache issues
            "js_runtimes": {"deno": {}, "node": {}},
            # Speed & throughput optimizations (multi-connection fragments & 1MB buffer)
            "concurrent_fragment_downloads": 6,
            "buffersize": 1048576,
            "http_chunk_size": 10485760,
        }

        # Configure FFmpeg location if bundled or found
        ffmpeg_bin = find_ffmpeg_executable()
        if ffmpeg_bin:
            opts["ffmpeg_location"] = str(Path(ffmpeg_bin).parent)

        # Configure Smart Download Archive
        archive_enabled = self.config.use_download_archive if use_archive is None else use_archive
        if archive_enabled:
            resolved_archive = archive_path or self.config.get_resolved_archive_path()
            try:
                resolved_archive.parent.mkdir(parents=True, exist_ok=True)
                opts["download_archive"] = str(resolved_archive)
            except Exception:
                pass

        if is_playlist:
            opts["ignoreerrors"] = True

        if logger:
            opts["logger"] = logger

        if progress_manager and progress_manager.enabled:
            opts["progress_hooks"] = [progress_manager.progress_hook]
            opts["postprocessor_hooks"] = [progress_manager.postprocessor_hook]

        return opts

    def get_video_info(self, url: str) -> VideoMetadata:
        """
        Retrieve metadata for a video without downloading media files.

        Returns:
            VideoMetadata dataclass.
        """
        canonical_url, video_id = validate_and_sanitize_youtube_url(url)
        logger = YTDLLogger(console=self.console, debug=self.debug)

        ydl_opts = {
            "extract_flat": False,
            "noplaylist": True,
            "quiet": not self.debug,
            "no_warnings": not self.debug,
            "logger": logger,
            "socket_timeout": 30,
            "js_runtimes": {"deno": {}, "node": {}},
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
                if not info:
                    raise YTDLError(f"Unable to retrieve information for video ID: {video_id}")

            title = info.get("title", "Unknown Title")
            uploader = info.get("uploader") or info.get("channel") or "Unknown Uploader"
            channel_url = info.get("uploader_url") or info.get("channel_url")
            duration_secs = info.get("duration")
            upload_date = info.get("upload_date")  # YYYYMMDD
            if upload_date and len(upload_date) == 8:
                formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            else:
                formatted_date = upload_date or "Unknown"

            thumbnail = info.get("thumbnail")
            description = (info.get("description") or "").strip()
            desc_preview = (description[:250] + "...") if len(description) > 250 else description

            # Collect unique available resolutions
            formats = info.get("formats", [])
            resolutions = set()
            for f in formats:
                h = f.get("height")
                if h:
                    resolutions.add(f"{h}p")
            sorted_res = sorted(resolutions, key=lambda x: int(x.rstrip("p")), reverse=True)

            return VideoMetadata(
                video_id=video_id,
                title=title,
                uploader=uploader,
                channel_url=channel_url,
                duration_seconds=duration_secs,
                duration_formatted=format_duration(duration_secs),
                upload_date_formatted=formatted_date,
                thumbnail_url=thumbnail,
                description_preview=desc_preview,
                available_resolutions=sorted_res,
                raw_info=info,
            )
        except Exception as e:
            raise classify_ytdl_error(e)

    def list_available_formats(self, url: str) -> List[FormatEntry]:
        """
        Inspect and list available media formats in a structured format table.
        """
        metadata = self.get_video_info(url)
        formats = metadata.raw_info.get("formats", [])
        results: List[FormatEntry] = []

        for f in formats:
            fid = str(f.get("format_id", "-"))
            ext = str(f.get("ext", "-"))
            w = f.get("width")
            h = f.get("height")
            if h and w:
                resolution = f"{w}x{h}"
            elif h:
                resolution = f"{h}p"
            elif f.get("vcodec") == "none":
                resolution = "audio only"
            else:
                resolution = f.get("format_note") or "Unknown"

            vcodec = f.get("vcodec") or "-"
            acodec = f.get("acodec") or "-"

            filesize = f.get("filesize") or f.get("filesize_approx")
            size_str = format_bytes(filesize) if filesize else "Unknown"

            fps = f.get("fps")
            note = f.get("format_note") or ""

            results.append(FormatEntry(
                format_id=fid,
                ext=ext,
                resolution=resolution,
                vcodec=vcodec,
                acodec=acodec,
                filesize_formatted=size_str,
                fps=fps,
                note=note
            ))

        return results

    def download_video(
        self,
        url: str,
        quality: str = "best",
        output_dir: Optional[Path] = None,
        use_archive: Optional[bool] = None,
        archive_path: Optional[Path] = None,
        embed_metadata: Optional[bool] = None,
        embed_thumbnail: Optional[bool] = None,
    ) -> Optional[Path]:
        """
        Download a video at the best quality or user-selected maximum resolution.

        Returns:
            Path to the downloaded video file, or None if skipped via download archive.
        """
        canonical_url, video_id = validate_and_sanitize_youtube_url(url)
        selected_quality = validate_video_quality(quality)

        target_dir = output_dir or self.config.get_resolved_download_path()
        ensure_directory_writable(target_dir)

        # Check FFmpeg if separate stream merge is required
        if not shutil.which("ffmpeg"):
            self.console.print(
                "[bold yellow]Notice:[/bold yellow] FFmpeg not found on PATH. "
                "yt-dlp will fall back to single pre-merged streams if available, "
                "which may limit maximum available resolution."
            )

        format_selector = get_video_format_selector(selected_quality)
        logger = YTDLLogger(console=self.console, debug=self.debug)

        with DownloadProgressManager(console=self.console, enabled=self.config.show_progress) as pm:
            ydl_opts = self._build_base_ydl_opts(
                target_dir,
                progress_manager=pm,
                logger=logger,
                use_archive=use_archive,
                archive_path=archive_path,
            )
            ydl_opts["format"] = format_selector

            should_embed_meta = self.config.embed_metadata if embed_metadata is None else embed_metadata
            should_embed_thumb = self.config.embed_thumbnail if embed_thumbnail is None else embed_thumbnail

            pps = []
            if should_embed_thumb and shutil.which("ffmpeg"):
                ydl_opts["writethumbnail"] = True
                pps.append({
                    "key": "FFmpegThumbnailsConvertor",
                    "format": "jpg",
                })
            if should_embed_meta and shutil.which("ffmpeg"):
                pps.append({"key": "FFmpegMetadata", "add_chapters": True})
            if should_embed_thumb and shutil.which("ffmpeg"):
                pps.append({
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                })
            if pps:
                ydl_opts["postprocessors"] = pps

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=True)
                    if not info:
                        if logger.archived_ids:
                            candidates = list(target_dir.glob(f"*{video_id}*"))
                            return candidates[0] if candidates else None
                        raise YTDLError("Download failed: yt-dlp did not return media information.")

                    # Determine final target path
                    downloaded_path: Optional[Path] = None
                    if "requested_downloads" in info and info["requested_downloads"]:
                        fp = info["requested_downloads"][0].get("filepath")
                        if fp and Path(fp).exists():
                            downloaded_path = Path(fp)

                    if not downloaded_path:
                        prepared = ydl.prepare_filename(info)
                        if Path(prepared).exists():
                            downloaded_path = Path(prepared)

                    if not downloaded_path or not downloaded_path.exists():
                        # Search target directory for matching video ID
                        candidates = list(target_dir.glob(f"*{info.get('id')}*"))
                        if candidates:
                            downloaded_path = candidates[0]
                        else:
                            raise YTDLError(
                                "Download reported completion, but the output file could not be verified on disk."
                            )

                    return downloaded_path

            except KeyboardInterrupt:
                raise DownloadInterruptedError("Download was cancelled by the user.")
            except Exception as e:
                if isinstance(e, YTDLError):
                    raise
                raise classify_ytdl_error(e)

    def download_audio(
        self,
        url: str,
        audio_format: str = "mp3",
        audio_quality: str | int = "192",
        output_dir: Optional[Path] = None,
        use_archive: Optional[bool] = None,
        archive_path: Optional[Path] = None,
        embed_metadata: Optional[bool] = None,
        embed_thumbnail: Optional[bool] = None,
    ) -> Optional[Path]:
        """
        Download audio track (either best original format or converted to MP3 via FFmpeg),
        with optional album artwork thumbnail embedding and ID3 tag metadata.

        Returns:
            Path to the downloaded audio file, or None if skipped via download archive.
        """
        canonical_url, video_id = validate_and_sanitize_youtube_url(url)
        fmt = validate_audio_format(audio_format)
        bitrate = validate_audio_quality(audio_quality)

        target_dir = output_dir or self.config.get_resolved_download_path()
        ensure_directory_writable(target_dir)

        # MP3 conversion requires FFmpeg
        if fmt == "mp3":
            if not shutil.which("ffmpeg"):
                raise DependencyMissingError(
                    "FFmpeg is required to convert audio to MP3.",
                    guidance=(
                        "Install FFmpeg via 'winget install Gyan.FFmpeg' or download from https://www.gyan.dev/ffmpeg/builds/.\n"
                        "Alternatively, choose 'best available original format' to download without conversion."
                    )
                )

        logger = YTDLLogger(console=self.console, debug=self.debug)

        with DownloadProgressManager(console=self.console, enabled=self.config.show_progress) as pm:
            ydl_opts = self._build_base_ydl_opts(
                target_dir,
                progress_manager=pm,
                logger=logger,
                use_archive=use_archive,
                archive_path=archive_path,
            )
            ydl_opts["format"] = "bestaudio/best"

            should_embed_meta = self.config.embed_metadata if embed_metadata is None else embed_metadata
            should_embed_thumb = self.config.embed_thumbnail if embed_thumbnail is None else embed_thumbnail

            pps = []
            if fmt == "mp3":
                if should_embed_thumb and shutil.which("ffmpeg"):
                    ydl_opts["writethumbnail"] = True
                    pps.append({
                        "key": "FFmpegThumbnailsConvertor",
                        "format": "jpg",
                    })

                pps.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate),
                })

                if should_embed_meta and shutil.which("ffmpeg"):
                    pps.append({
                        "key": "FFmpegMetadata",
                        "add_chapters": True,
                    })

                if should_embed_thumb and shutil.which("ffmpeg"):
                    pps.append({
                        "key": "EmbedThumbnail",
                        "already_have_thumbnail": False,
                    })
            elif should_embed_meta and shutil.which("ffmpeg"):
                pps.append({"key": "FFmpegMetadata", "add_chapters": True})

            if pps:
                ydl_opts["postprocessors"] = pps

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=True)
                    if not info:
                        if logger.archived_ids:
                            candidates = list(target_dir.glob(f"*{video_id}*"))
                            return candidates[0] if candidates else None
                        raise YTDLError("Download failed: yt-dlp did not return media information.")

                    downloaded_path: Optional[Path] = None
                    if "requested_downloads" in info and info["requested_downloads"]:
                        fp = info["requested_downloads"][0].get("filepath")
                        if fp and Path(fp).exists():
                            downloaded_path = Path(fp)

                    if not downloaded_path:
                        prepared = ydl.prepare_filename(info)
                        if fmt == "mp3":
                            mp3_path = Path(prepared).with_suffix(".mp3")
                            if mp3_path.exists():
                                downloaded_path = mp3_path
                        elif Path(prepared).exists():
                            downloaded_path = Path(prepared)

                    if not downloaded_path or not downloaded_path.exists():
                        candidates = list(target_dir.glob(f"*{info.get('id')}*"))
                        if candidates:
                            downloaded_path = candidates[0]
                        else:
                            raise YTDLError(
                                "Audio download reported completion, but the output file could not be verified on disk."
                            )

                    return downloaded_path

            except KeyboardInterrupt:
                raise DownloadInterruptedError("Audio download was cancelled by the user.")
            except Exception as e:
                if isinstance(e, YTDLError):
                    raise
                raise classify_ytdl_error(e)

    def get_playlist_info(self, url: str) -> PlaylistMetadata:
        """
        Retrieve metadata and item previews for a playlist without downloading media files.

        Returns:
            PlaylistMetadata dataclass.
        """
        canonical_url, playlist_id = validate_youtube_playlist_url(url)
        logger = YTDLLogger(console=self.console, debug=self.debug)

        ydl_opts = {
            "extract_flat": "in_playlist",
            "quiet": not self.debug,
            "no_warnings": not self.debug,
            "logger": logger,
            "socket_timeout": 30,
            "js_runtimes": {"deno": {}, "node": {}},
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
                if not info:
                    raise YTDLError(f"Unable to retrieve playlist information for ID: {playlist_id}")

            title = info.get("title") or f"Playlist {playlist_id}"
            uploader = info.get("uploader") or info.get("channel") or "Unknown Uploader"
            raw_entries = info.get("entries") or []
            entries_list = list(raw_entries)

            previews: List[PlaylistEntryPreview] = []
            for idx, entry in enumerate(entries_list, start=1):
                if not isinstance(entry, dict):
                    continue
                e_id = entry.get("id", "")
                e_title = entry.get("title") or f"Video {idx}"
                e_dur = entry.get("duration")
                e_url = entry.get("url") or f"https://www.youtube.com/watch?v={e_id}"
                previews.append(PlaylistEntryPreview(
                    index=idx,
                    title=e_title,
                    video_id=e_id,
                    url=e_url,
                    duration_formatted=format_duration(e_dur)
                ))

            return PlaylistMetadata(
                playlist_id=playlist_id,
                title=title,
                uploader=uploader,
                entries_count=len(previews),
                entries=previews,
                raw_info=info,
            )
        except Exception as e:
            if isinstance(e, YTDLError):
                raise
            raise classify_ytdl_error(e)

    def download_playlist(
        self,
        url: str,
        mode: str = "video",
        quality: str = "best",
        audio_format: str = "mp3",
        audio_quality: str | int = "192",
        playlist_start: Optional[int] = None,
        playlist_end: Optional[int] = None,
        playlist_items: Optional[str] = None,
        output_dir: Optional[Path] = None,
        create_subfolder: Optional[bool] = None,
        use_archive: Optional[bool] = None,
        archive_path: Optional[Path] = None,
        embed_metadata: Optional[bool] = None,
        embed_thumbnail: Optional[bool] = None,
    ) -> PlaylistDownloadResult:
        """
        Download all or selected items in a YouTube playlist as video or audio.

        Returns:
            PlaylistDownloadResult summarizing completed downloads, skipped items, and any failures.
        """
        canonical_url, playlist_id = validate_youtube_playlist_url(url)
        meta = self.get_playlist_info(canonical_url)

        base_dir = output_dir or self.config.get_resolved_download_path()
        use_subfolder = self.config.create_playlist_subfolder if create_subfolder is None else create_subfolder

        if use_subfolder:
            safe_folder = sanitize_folder_name(meta.title)
            target_dir = base_dir / safe_folder
        else:
            target_dir = base_dir

        ensure_directory_writable(target_dir)

        if mode == "audio" and audio_format == "mp3":
            if not shutil.which("ffmpeg"):
                raise DependencyMissingError(
                    "FFmpeg is required to convert playlist audio to MP3.",
                    guidance="Install FFmpeg via 'winget install Gyan.FFmpeg' or choose original audio format."
                )

        logger = YTDLLogger(console=self.console, debug=self.debug)

        with DownloadProgressManager(console=self.console, enabled=self.config.show_progress) as pm:
            ydl_opts = self._build_base_ydl_opts(
                target_dir,
                progress_manager=pm,
                logger=logger,
                is_playlist=True,
                use_archive=use_archive,
                archive_path=archive_path,
            )

            should_embed_meta = self.config.embed_metadata if embed_metadata is None else embed_metadata
            should_embed_thumb = self.config.embed_thumbnail if embed_thumbnail is None else embed_thumbnail

            if mode == "video":
                selected_quality = validate_video_quality(quality)
                ydl_opts["format"] = get_video_format_selector(selected_quality)
                pps = []
                if should_embed_thumb and shutil.which("ffmpeg"):
                    ydl_opts["writethumbnail"] = True
                    pps.append({
                        "key": "FFmpegThumbnailsConvertor",
                        "format": "jpg",
                    })
                if should_embed_meta and shutil.which("ffmpeg"):
                    pps.append({"key": "FFmpegMetadata", "add_chapters": True})
                if should_embed_thumb and shutil.which("ffmpeg"):
                    pps.append({
                        "key": "EmbedThumbnail",
                        "already_have_thumbnail": False,
                    })
                if pps:
                    ydl_opts["postprocessors"] = pps
            else:
                fmt = validate_audio_format(audio_format)
                bitrate = validate_audio_quality(audio_quality)
                ydl_opts["format"] = "bestaudio/best"
                pps = []
                if fmt == "mp3":
                    if should_embed_thumb and shutil.which("ffmpeg"):
                        ydl_opts["writethumbnail"] = True
                        pps.append({
                            "key": "FFmpegThumbnailsConvertor",
                            "format": "jpg",
                        })

                    pps.append({
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": str(bitrate),
                    })

                    if should_embed_meta and shutil.which("ffmpeg"):
                        pps.append({
                            "key": "FFmpegMetadata",
                            "add_chapters": True,
                        })

                    if should_embed_thumb and shutil.which("ffmpeg"):
                        pps.append({
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False,
                        })
                elif should_embed_meta and shutil.which("ffmpeg"):
                    pps.append({"key": "FFmpegMetadata", "add_chapters": True})

                if pps:
                    ydl_opts["postprocessors"] = pps

            if playlist_start:
                ydl_opts["playliststart"] = int(playlist_start)
            if playlist_end:
                ydl_opts["playlistend"] = int(playlist_end)
            if playlist_items:
                ydl_opts["playlist_items"] = str(playlist_items).strip()

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=True)
            except KeyboardInterrupt:
                raise DownloadInterruptedError("Playlist download was cancelled by the user.")
            except Exception as e:
                if isinstance(e, YTDLError):
                    raise
                raise classify_ytdl_error(e)

        downloaded_count = 0
        raw_entries = info.get("entries") if isinstance(info, dict) else None
        if raw_entries is not None:
            try:
                entries_list = list(raw_entries)
                downloaded_count = sum(1 for e in entries_list if e is not None)
            except Exception:
                downloaded_count = len([f for f in target_dir.glob("*") if f.is_file()])
        else:
            downloaded_count = len([f for f in target_dir.glob("*") if f.is_file()])

        failed_count = len(logger.errors)
        skipped_count = len(logger.archived_ids)

        return PlaylistDownloadResult(
            playlist_id=playlist_id,
            title=meta.title,
            total_entries=meta.entries_count,
            downloaded_count=downloaded_count,
            failed_count=failed_count,
            output_directory=target_dir,
            failed_items=[(0, "Item", err) for err in logger.errors],
            skipped_count=skipped_count,
        )

    def download_batch(
        self,
        urls: List[str],
        mode: str = "video",
        quality: str = "best",
        audio_format: str = "mp3",
        audio_quality: str | int = "192",
        output_dir: Optional[Path] = None,
        use_archive: Optional[bool] = None,
        archive_path: Optional[Path] = None,
        embed_metadata: Optional[bool] = None,
        embed_thumbnail: Optional[bool] = None,
    ) -> BatchDownloadResult:
        """
        Download multiple individual YouTube videos sequentially with error isolation.

        Returns:
            BatchDownloadResult summarizing successes, skips, and failures.
        """
        target_dir = output_dir or self.config.get_resolved_download_path()
        ensure_directory_writable(target_dir)

        results: List[ItemDownloadResult] = []
        succeeded = 0
        failed = 0
        skipped = 0

        for i, raw_url in enumerate(urls, start=1):
            self.console.print(f"\n[bold cyan]Batch Item [{i}/{len(urls)}]:[/bold cyan] [underline]{raw_url}[/underline]")
            try:
                if mode == "video":
                    saved_path = self.download_video(
                        raw_url,
                        quality=quality,
                        output_dir=target_dir,
                        use_archive=use_archive,
                        archive_path=archive_path,
                        embed_metadata=embed_metadata,
                        embed_thumbnail=embed_thumbnail,
                    )
                else:
                    saved_path = self.download_audio(
                        raw_url,
                        audio_format=audio_format,
                        audio_quality=audio_quality,
                        output_dir=target_dir,
                        use_archive=use_archive,
                        archive_path=archive_path,
                        embed_metadata=embed_metadata,
                        embed_thumbnail=embed_thumbnail,
                    )

                if saved_path:
                    succeeded += 1
                    results.append(ItemDownloadResult(
                        index=i,
                        url=raw_url,
                        title=saved_path.stem,
                        success=True,
                        filepath=saved_path,
                        skipped=False,
                    ))
                    self.console.print(f"[bold green][SUCCESS][/bold green] Saved: {saved_path.name}")
                else:
                    skipped += 1
                    results.append(ItemDownloadResult(
                        index=i,
                        url=raw_url,
                        title=None,
                        success=True,
                        filepath=None,
                        skipped=True,
                    ))
                    self.console.print("[bold yellow][SKIPPED][/bold yellow] Video already recorded in download archive.")

            except Exception as e:
                failed += 1
                error_msg = str(e)
                results.append(ItemDownloadResult(
                    index=i,
                    url=raw_url,
                    title=None,
                    success=False,
                    error=error_msg,
                    skipped=False,
                ))
                self.console.print(f"[bold red][FAILED][/bold red] {error_msg}")

        return BatchDownloadResult(
            total=len(urls),
            succeeded=succeeded,
            failed=failed,
            results=results,
            skipped=skipped,
        )

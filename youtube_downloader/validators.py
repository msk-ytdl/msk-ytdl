"""
URL and user input validation for MSK-YTDL.

Provides robust domain-boundary validation, video ID extraction,
playlist-stripping safety, and parameter verification.
"""

import re
import urllib.parse
from typing import Optional, Tuple
from youtube_downloader.errors import ValidationError

# Supported video resolution choices
SUPPORTED_VIDEO_QUALITIES = ("best", "2160p", "1440p", "1080p", "720p", "480p", "360p")

# Supported audio format choices
SUPPORTED_AUDIO_FORMATS = ("mp3", "best")

# Supported MP3 audio bitrate options (kbps)
SUPPORTED_AUDIO_QUALITIES = ("128", "192", "256", "320")

# Canonical YouTube base domains
_ALLOWED_YOUTUBE_ROOT_DOMAINS = ("youtube.com", "youtu.be")

# Standard YouTube 11-character video ID pattern
_VIDEO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def is_valid_youtube_host(hostname: Optional[str]) -> bool:
    """
    Validate that the hostname strictly belongs to YouTube or youtu.be.

    Uses boundary checks to prevent domain spoofing like 'fakeyoutube.com'
    or 'youtube.com.attacker.com'.
    """
    if not hostname:
        return False

    hostname = hostname.lower().strip()
    # Strip port if present
    if ":" in hostname:
        hostname = hostname.split(":", 1)[0]

    for root_domain in _ALLOWED_YOUTUBE_ROOT_DOMAINS:
        if hostname == root_domain or hostname.endswith("." + root_domain):
            return True

    return False


def validate_and_sanitize_youtube_url(url: str) -> Tuple[str, str]:
    """
    Validate a YouTube URL and extract its canonical single-video URL and video ID.

    Ensures that playlist parameters are stripped so that single-video downloading
    is strictly preserved. Rejects pure playlist URLs with actionable guidance.

    Returns:
        (sanitized_url, video_id)

    Raises:
        ValidationError: If the URL is empty, malformed, non-YouTube, or a pure playlist.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise ValidationError("URL cannot be empty.", guidance="Please enter a valid YouTube video URL.")

    url = url.strip()

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        raise ValidationError(f"Malformed URL: {url}", details=str(e))

    # Validate scheme
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValidationError(
            f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are supported.",
            guidance="Include 'https://' at the start of your URL."
        )

    # Validate hostname boundary
    if not is_valid_youtube_host(parsed.hostname):
        raise ValidationError(
            f"Unsupported host '{parsed.hostname}'. This application is specifically for YouTube.",
            guidance="Provide a valid canonical YouTube URL (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)."
        )

    hostname = (parsed.hostname or "").lower()
    path = parsed.path
    query_params = urllib.parse.parse_qs(parsed.query)

    video_id: Optional[str] = None

    # Case 1: Pure playlist URL (e.g. /playlist?list=...)
    if path.rstrip("/").endswith("/playlist"):
        raise ValidationError(
            "The provided URL points to a full playlist, not a single video.",
            guidance=(
                "Single-video downloading is the default safety policy. "
                "Please provide a URL pointing directly to an individual video."
            )
        )

    # Case 2: Shortened youtu.be URL (https://youtu.be/VIDEO_ID)
    if hostname == "youtu.be" or hostname.endswith(".youtu.be"):
        path_parts = [p for p in path.split("/") if p]
        if path_parts:
            candidate_id = path_parts[0]
            if _VIDEO_ID_PATTERN.match(candidate_id):
                video_id = candidate_id

    # Case 3: Standard watch URL (https://www.youtube.com/watch?v=VIDEO_ID)
    elif "v" in query_params:
        candidates = query_params.get("v", [])
        if candidates and _VIDEO_ID_PATTERN.match(candidates[0]):
            video_id = candidates[0]

    # Case 4: Shorts, Embed, Live paths (/shorts/ID, /embed/ID, /live/ID)
    else:
        for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
            if path.startswith(prefix):
                candidate_id = path[len(prefix):].split("/")[0].split("?")[0]
                if _VIDEO_ID_PATTERN.match(candidate_id):
                    video_id = candidate_id
                    break

    if not video_id:
        raise ValidationError(
            f"Could not extract a valid 11-character YouTube video ID from: {url}",
            guidance="Ensure the URL points to a standard video, Short, or live stream (e.g. https://www.youtube.com/watch?v=...)."
        )

    # Construct clean canonical single-video URL without playlist or extra tracking params
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    return canonical_url, video_id


def validate_video_quality(quality: str) -> str:
    """Validate and normalize a video quality option."""
    q = (quality or "").lower().strip()
    if q not in SUPPORTED_VIDEO_QUALITIES:
        valid_options = ", ".join(SUPPORTED_VIDEO_QUALITIES)
        raise ValidationError(
            f"Invalid video quality '{quality}'.",
            guidance=f"Supported quality choices: {valid_options}"
        )
    return q


def validate_audio_format(audio_format: str) -> str:
    """Validate and normalize an audio format option."""
    fmt = (audio_format or "").lower().strip()
    if fmt not in SUPPORTED_AUDIO_FORMATS:
        valid_options = ", ".join(SUPPORTED_AUDIO_FORMATS)
        raise ValidationError(
            f"Invalid audio format '{audio_format}'.",
            guidance=f"Supported audio formats: {valid_options}"
        )
    return fmt


def validate_audio_quality(quality: str | int) -> str:
    """Validate and normalize an audio quality / bitrate option."""
    q = str(quality).strip()
    if q not in SUPPORTED_AUDIO_QUALITIES:
        valid_options = ", ".join(SUPPORTED_AUDIO_QUALITIES)
        raise ValidationError(
            f"Invalid audio bitrate '{quality}'.",
            guidance=f"Supported MP3 bitrates (kbps): {valid_options}"
        )
    return q


_PLAYLIST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,128}$")


def validate_youtube_playlist_url(url: str) -> Tuple[str, str]:
    """
    Validate a YouTube playlist URL and extract its canonical playlist URL and playlist ID.

    Accepts standard playlist URLs (e.g., https://www.youtube.com/playlist?list=PL...),
    watch URLs containing playlist parameters (e.g., https://www.youtube.com/watch?v=...&list=PL...),
    and YouTube Music or mobile shortened playlist links.

    Returns:
        (canonical_playlist_url, playlist_id)

    Raises:
        ValidationError: If the URL is invalid or does not contain a valid playlist ID.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise ValidationError("Playlist URL cannot be empty.", guidance="Please enter a valid YouTube playlist URL.")

    url = url.strip()

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        raise ValidationError(f"Malformed URL: {url}", details=str(e))

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValidationError(
            f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are supported.",
            guidance="Include 'https://' at the start of your URL."
        )

    if not is_valid_youtube_host(parsed.hostname):
        raise ValidationError(
            f"Unsupported host '{parsed.hostname}'. This application is specifically for YouTube.",
            guidance="Provide a valid YouTube playlist URL (e.g., https://www.youtube.com/playlist?list=...)."
        )

    query_params = urllib.parse.parse_qs(parsed.query)
    list_param = query_params.get("list")

    playlist_id: Optional[str] = None
    if list_param and list_param[0]:
        playlist_id = list_param[0].strip()
    else:
        m_list = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url)
        if m_list:
            playlist_id = m_list.group(1).strip()

    if not playlist_id:
        raise ValidationError(
            "The provided URL does not contain a playlist 'list=' parameter.",
            guidance="Ensure your URL contains '?list=...' (e.g., https://www.youtube.com/playlist?list=PL...)."
        )

    if not _PLAYLIST_ID_PATTERN.match(playlist_id):
        raise ValidationError(
            f"Invalid playlist ID format '{playlist_id}'.",
            guidance="Ensure the playlist ID is a valid alphanumeric YouTube playlist identifier."
        )

    canonical_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    return canonical_url, playlist_id


def parse_batch_urls_input(input_text: str) -> list[str]:
    """
    Parse a string containing multiple URLs separated by newlines, commas, or spaces.

    Returns:
        List of distinct, non-empty candidate URL strings.
    """
    if not input_text or not isinstance(input_text, str):
        return []

    raw_candidates = re.split(r"[\r\n,]+", input_text)
    urls = []
    seen = set()

    for item in raw_candidates:
        trimmed = item.strip()
        if trimmed and not trimmed.startswith("#"):
            # Further split if multiple URLs on a line separated by space
            space_parts = trimmed.split()
            for part in space_parts:
                p = part.strip()
                if p and p not in seen:
                    seen.add(p)
                    urls.append(p)

    return urls


def read_urls_from_file(file_path: str) -> list[str]:
    """
    Read URLs from a text file (one URL per line or space/comma separated).

    Ignores blank lines and comment lines starting with '#'.

    Raises:
        ValidationError: If file does not exist or cannot be read.
    """
    import os
    resolved = os.path.expanduser(file_path.strip())
    if not os.path.exists(resolved):
        raise ValidationError(
            f"Batch file '{file_path}' was not found.",
            guidance="Verify the file path and ensure the text file exists on disk."
        )

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(resolved, "r", encoding="latin-1") as f:
                content = f.read()
        except Exception as e:
            raise ValidationError(f"Failed to read file '{file_path}': {e}")
    except Exception as e:
        raise ValidationError(f"Failed to read file '{file_path}': {e}")

    urls = parse_batch_urls_input(content)
    if not urls:
        raise ValidationError(
            f"No valid URLs found in file '{file_path}'.",
            guidance="Add one or more YouTube URLs into the file."
        )

    return urls


"""
Error classifications and user-friendly diagnostics for MSK-YTDL.

Provides structured exception classes and mapping from low-level yt-dlp
and system errors to actionable, clear explanations.
"""

from typing import Optional


class YTDLError(Exception):
    """Base exception for all MSK-YTDL errors."""

    def __init__(self, message: str, details: Optional[str] = None, guidance: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.guidance = guidance

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message

    def format_user_message(self) -> str:
        """Format a clear, multi-line user-facing message."""
        lines = [f"[bold red]Error:[/bold red] {self.message}"]
        if self.details:
            lines.append(f"[yellow]Details:[/yellow] {self.details}")
        if self.guidance:
            lines.append(f"[cyan]Recommendation:[/cyan] {self.guidance}")
        return "\n".join(lines)


class ValidationError(YTDLError):
    """Raised when URL or user input validation fails."""
    pass


class ConfigurationError(YTDLError):
    """Raised when loading, parsing, or saving configuration fails."""
    pass


class DependencyMissingError(YTDLError):
    """Raised when a required external executable or library is missing."""
    pass


class OutputDirectoryError(YTDLError):
    """Raised when the target output directory is inaccessible, unwritable, or invalid."""
    pass


class AccessRestrictedError(YTDLError):
    """Raised when YouTube video access is restricted (private, member-only, geo-blocked, login required)."""
    pass


class VideoUnavailableError(YTDLError):
    """Raised when a video is deleted, removed, or unavailable."""
    pass


class NetworkError(YTDLError):
    """Raised when connection drops, times out, or fails to resolve."""
    pass


class ExtractionError(YTDLError):
    """Raised when YouTube structure changes or yt-dlp extractor fails."""
    pass


class PostProcessingError(YTDLError):
    """Raised when FFmpeg audio conversion or merging fails."""
    pass


class DownloadInterruptedError(YTDLError):
    """Raised when a download is cancelled or interrupted before completion."""
    pass


def classify_ytdl_error(error: Exception) -> YTDLError:
    """
    Classify a yt-dlp or runtime exception into a structured, user-friendly YTDLError.

    Analyzes error message patterns to provide specific guidance rather than generic failure alerts.
    """
    error_msg = str(error)
    error_lower = error_msg.lower()

    # 1. FFmpeg post-processing / conversion errors
    if any(k in error_lower for k in ["ffmpeg", "ffprobe", "postprocessing", "unable to run ffmpeg"]):
        return PostProcessingError(
            message="Post-processing or audio conversion failed via FFmpeg.",
            details=error_msg,
            guidance=(
                "Ensure FFmpeg and FFprobe are properly installed and accessible in your system PATH. "
                "Run 'python -m youtube_downloader --check' to verify your installation."
            )
        )

    # 2. JavaScript Challenge / EJS errors
    if any(k in error_lower for k in ["js challenge", "ejs", "javascript runtime", "n-sig", "signature"]):
        return ExtractionError(
            message="YouTube JavaScript signature challenge extraction failed.",
            details=error_msg,
            guidance=(
                "YouTube frequently updates signature algorithms. Ensure 'yt-dlp-ejs' is installed "
                "and a supported JS runtime (such as Node.js or Deno) is available on your PATH. "
                "Try updating yt-dlp: 'pip install -U yt-dlp yt-dlp-ejs'."
            )
        )

    # 3. Access restrictions (private, members-only, sign-in, premium)
    if any(k in error_lower for k in [
        "private video", "sign in if you've been granted access",
        "members-only", "join this channel", "requires payment",
        "this video is only available to", "login required"
    ]):
        return AccessRestrictedError(
            message="This video is private, members-only, or access-restricted.",
            details=error_msg,
            guidance=(
                "This application does not bypass access restrictions or collect credentials. "
                "Please use YouTube's authorized website or YouTube Premium offline features "
                "if you are the owner or an authorized member."
            )
        )

    # 4. Geo-restriction
    if "not available in your country" in error_lower or "georestricted" in error_lower:
        return AccessRestrictedError(
            message="This video is geographically restricted in your region.",
            details=error_msg,
            guidance="The publisher has limited access to specific geographic regions."
        )

    # 5. Video deleted, removed, or not found (HTTP 404)
    if any(k in error_lower for k in ["video unavailable", "does not exist", "has been removed", "terminated", "404", "http error 404"]):
        return VideoUnavailableError(
            message="The requested video is unavailable or has been removed from YouTube.",
            details=error_msg,
            guidance="Verify that the video URL and ID are correct and that the video is publicly accessible."
        )

    # 6. Network / Connection errors
    if any(k in error_lower for k in [
        "timed out", "timeout", "connection reset", "connection refused",
        "name or service not known", "getaddrinfo failed", "network is unreachable"
    ]):
        return NetworkError(
            message="A network error occurred while communicating with YouTube.",
            details=error_msg,
            guidance="Check your internet connection, DNS configuration, and retry the request."
        )

    # 7. Generic Extractor / Unsupported URL
    if "unsupported url" in error_lower:
        return ValidationError(
            message="The provided URL is not supported by the YouTube extractor.",
            details=error_msg,
            guidance="Please supply a valid canonical YouTube video URL."
        )

    # Default fallback
    return YTDLError(
        message="An unexpected error occurred during YouTube extraction or download.",
        details=error_msg,
        guidance=(
            "Run 'python -m youtube_downloader --check' to test your environment, or "
            "run with '--debug' for detailed diagnostic output."
        )
    )

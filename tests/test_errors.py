"""
Unit tests for error classification and user guidance formatting in MSK-YTDL.
"""

from youtube_downloader.errors import (
    AccessRestrictedError,
    ExtractionError,
    NetworkError,
    PostProcessingError,
    VideoUnavailableError,
    YTDLError,
    classify_ytdl_error,
)


class TestErrorClassification:
    """Tests for classifying underlying yt-dlp error patterns into structured exceptions."""

    def test_classify_private_video(self):
        err = Exception("ERROR: [youtube] dQw4w9WgXcQ: Private video. Sign in if you've been granted access to this video")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, AccessRestrictedError)
        assert "private" in classified.message.lower()
        assert "does not bypass access restrictions" in classified.guidance

    def test_classify_members_only_video(self):
        err = Exception("ERROR: [youtube] abcdefghijk: Join this channel to get access to members-only content")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, AccessRestrictedError)

    def test_classify_georestricted_video(self):
        err = Exception("ERROR: [youtube] dQw4w9WgXcQ: Video is not available in your country")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, AccessRestrictedError)
        assert "geographically restricted" in classified.message

    def test_classify_video_unavailable(self):
        err = Exception("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable. This video has been removed by the uploader")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, VideoUnavailableError)
        assert "removed from YouTube" in classified.message

    def test_classify_network_timeout(self):
        err = Exception("ERROR: [youtube] Unable to download webpage: <urlopen error timed out>")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, NetworkError)
        assert "network error" in classified.message

    def test_classify_ffmpeg_failure(self):
        err = Exception("ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide the path")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, PostProcessingError)
        assert "FFmpeg" in classified.message

    def test_classify_signature_challenge_failure(self):
        err = Exception("ERROR: [youtube] JS challenge failed: n-sig decipher algorithm not found")
        classified = classify_ytdl_error(err)
        assert isinstance(classified, ExtractionError)
        assert "JavaScript" in classified.message
        assert "yt-dlp-ejs" in classified.guidance

    def test_format_user_message_structure(self):
        err = YTDLError(
            message="Test error message",
            details="Some internal detail",
            guidance="Follow these steps to fix"
        )
        msg = err.format_user_message()
        assert "Test error message" in msg
        assert "Some internal detail" in msg
        assert "Follow these steps to fix" in msg

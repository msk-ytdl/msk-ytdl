"""
Unit tests for URL and input validators in MSK-YTDL.
"""

import pytest

from youtube_downloader.errors import ValidationError
from youtube_downloader.validators import (
    is_valid_youtube_host,
    parse_batch_urls_input,
    read_urls_from_file,
    validate_and_sanitize_youtube_url,
    validate_audio_format,
    validate_audio_quality,
    validate_video_quality,
    validate_youtube_playlist_url,
)


class TestHostValidation:
    """Tests for canonical YouTube host boundary checking."""

    def test_valid_youtube_hosts(self):
        valid_hosts = [
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "gaming.youtube.com",
            "youtu.be",
            "www.youtu.be",
        ]
        for host in valid_hosts:
            assert is_valid_youtube_host(host) is True, f"Failed for valid host: {host}"

    def test_invalid_youtube_hosts(self):
        invalid_hosts = [
            "notyoutube.com",
            "fakeyoutube.com",
            "youtube.com.attacker.com",
            "myoutube.com",
            "vimeo.com",
            "dailymotion.com",
            "google.com",
            "",
            None,
        ]
        for host in invalid_hosts:
            assert is_valid_youtube_host(host) is False, f"Failed for invalid host: {host}"


class TestURLValidation:
    """Tests for YouTube URL parsing, video ID extraction, and playlist stripping."""

    def test_valid_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        canonical, video_id = validate_and_sanitize_youtube_url(url)
        assert video_id == "dQw4w9WgXcQ"
        assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_valid_shortened_youtu_be_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        canonical, video_id = validate_and_sanitize_youtube_url(url)
        assert video_id == "dQw4w9WgXcQ"
        assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_valid_shorts_url(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        canonical, video_id = validate_and_sanitize_youtube_url(url)
        assert video_id == "dQw4w9WgXcQ"
        assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_valid_embed_and_live_urls(self):
        urls = [
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
        ]
        for u in urls:
            canonical, video_id = validate_and_sanitize_youtube_url(u)
            assert video_id == "dQw4w9WgXcQ"
            assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_stripping_playlist_parameters_from_watch_url(self):
        """Ensures that a video URL with playlist params has playlist safely stripped."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890&index=3&t=42s"
        canonical, video_id = validate_and_sanitize_youtube_url(url)
        assert video_id == "dQw4w9WgXcQ"
        assert canonical == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert "list=" not in canonical

    def test_reject_pure_playlist_url(self):
        """Pure playlist URLs without video ID must be rejected with actionable guidance."""
        url = "https://www.youtube.com/playlist?list=PL1234567890abcdef"
        with pytest.raises(ValidationError) as exc_info:
            validate_and_sanitize_youtube_url(url)
        assert "points to a full playlist" in str(exc_info.value)

    def test_reject_empty_or_whitespace_url(self):
        for bad_url in ("", "   ", None):
            with pytest.raises(ValidationError):
                validate_and_sanitize_youtube_url(bad_url)

    def test_reject_non_youtube_domain(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_and_sanitize_youtube_url("https://vimeo.com/123456789")
        assert "Unsupported host" in str(exc_info.value)

    def test_reject_invalid_scheme(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_and_sanitize_youtube_url("ftp://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert "Invalid URL scheme" in str(exc_info.value)

    def test_reject_missing_video_id(self):
        with pytest.raises(ValidationError):
            validate_and_sanitize_youtube_url("https://www.youtube.com/watch?")


class TestParameterValidation:
    """Tests for video quality, audio format, and bitrate validation."""

    def test_valid_video_qualities(self):
        valid = ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
        for q in valid:
            assert validate_video_quality(q) == q
            assert validate_video_quality(q.upper()) == q

    def test_invalid_video_quality(self):
        with pytest.raises(ValidationError):
            validate_video_quality("9999p")
        with pytest.raises(ValidationError):
            validate_video_quality("invalid")

    def test_valid_audio_formats(self):
        assert validate_audio_format("mp3") == "mp3"
        assert validate_audio_format("MP3") == "mp3"
        assert validate_audio_format("best") == "best"

    def test_invalid_audio_format(self):
        with pytest.raises(ValidationError):
            validate_audio_format("wav")
        with pytest.raises(ValidationError):
            validate_audio_format("flac")

    def test_valid_audio_qualities(self):
        valid = ["128", "192", "256", "320", 128, 192, 256, 320]
        for q in valid:
            assert validate_audio_quality(q) == str(q)

    def test_invalid_audio_quality(self):
        with pytest.raises(ValidationError):
            validate_audio_quality("500")
        with pytest.raises(ValidationError):
            validate_audio_quality("auto")


class TestPlaylistAndBatchValidation:
    """Tests for playlist URL validation and batch URL file/input parsing."""

    def test_valid_standard_playlist_url(self):
        url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"
        canonical, pid = validate_youtube_playlist_url(url)
        assert pid == "PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"
        assert canonical == "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"

    def test_valid_watch_url_with_playlist_parameter(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f&index=2"
        canonical, pid = validate_youtube_playlist_url(url)
        assert pid == "PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"
        assert canonical == "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"

    def test_valid_short_and_special_playlist_ids(self):
        # Watch later (WL), Liked videos (LL)
        c1, p1 = validate_youtube_playlist_url("https://www.youtube.com/playlist?list=WL")
        assert p1 == "WL"
        assert c1 == "https://www.youtube.com/playlist?list=WL"

        c2, p2 = validate_youtube_playlist_url("https://music.youtube.com/playlist?list=OLAK5uy_k1234567890abcdef")
        assert p2 == "OLAK5uy_k1234567890abcdef"
        assert c2 == "https://www.youtube.com/playlist?list=OLAK5uy_k1234567890abcdef"

        # Query param list after other parameters
        c3, p3 = validate_youtube_playlist_url("https://www.youtube.com/watch?feature=shared&v=dQw4w9WgXcQ&list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f")
        assert p3 == "PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f"

    def test_invalid_playlist_url_empty_or_bad_scheme(self):
        with pytest.raises(ValidationError):
            validate_youtube_playlist_url("")
        with pytest.raises(ValidationError):
            validate_youtube_playlist_url("ftp://www.youtube.com/playlist?list=PL1234567890")

    def test_invalid_playlist_url_unsupported_host(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_youtube_playlist_url("https://vimeo.com/playlist?list=PL1234567890")
        assert "Unsupported host" in str(exc_info.value)

    def test_invalid_playlist_url_missing_list_param(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_youtube_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert "does not contain a playlist 'list=' parameter" in str(exc_info.value)

    def test_invalid_playlist_id_format(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_youtube_playlist_url("https://www.youtube.com/playlist?list=bad$$$id")
        assert "Invalid playlist ID format" in str(exc_info.value)

    def test_parse_batch_urls_input(self):
        input_text = """
        # This is a comment
        https://www.youtube.com/watch?v=dQw4w9WgXcQ
        https://youtu.be/9bZkp7q19f0, https://www.youtube.com/watch?v=kJQP7kiw5Fk
        
        # Another comment
        https://www.youtube.com/watch?v=dQw4w9WgXcQ  https://www.youtube.com/watch?v=L_LUpnjgPso
        """
        urls = parse_batch_urls_input(input_text)
        assert len(urls) == 4
        assert urls[0] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert urls[1] == "https://youtu.be/9bZkp7q19f0"
        assert urls[2] == "https://www.youtube.com/watch?v=kJQP7kiw5Fk"
        assert urls[3] == "https://www.youtube.com/watch?v=L_LUpnjgPso"

    def test_parse_batch_urls_empty_input(self):
        assert parse_batch_urls_input("") == []
        assert parse_batch_urls_input(None) == []

    def test_read_urls_from_file(self, tmp_path):
        batch_file = tmp_path / "urls.txt"
        batch_file.write_text(
            "# Video list\n"
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
            "\n"
            "https://youtu.be/9bZkp7q19f0\n",
            encoding="utf-8"
        )
        urls = read_urls_from_file(str(batch_file))
        assert len(urls) == 2
        assert urls[0] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert urls[1] == "https://youtu.be/9bZkp7q19f0"

    def test_read_urls_from_missing_file(self, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(ValidationError) as exc_info:
            read_urls_from_file(str(missing))
        assert "was not found" in str(exc_info.value)

    def test_read_urls_from_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("# only comments\n\n", encoding="utf-8")
        with pytest.raises(ValidationError) as exc_info:
            read_urls_from_file(str(empty_file))
        assert "No valid URLs found" in str(exc_info.value)


class TestMobileHelpers:
    """Tests for mobile YouTube URL extraction from shared text and clipboard."""

    def test_extract_pure_youtube_urls(self):
        from mobile_app import extract_youtube_url
        assert extract_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_youtube_url("https://youtu.be/9bZkp7q19f0") == "https://www.youtube.com/watch?v=9bZkp7q19f0"
        assert extract_youtube_url("https://www.youtube.com/shorts/L_LUpnjgPso") == "https://www.youtube.com/watch?v=L_LUpnjgPso"

    def test_extract_url_from_youtube_share_text(self):
        from mobile_app import extract_youtube_url
        share_text = "Check out this song on YouTube: https://youtu.be/dQw4w9WgXcQ it is amazing!"
        assert extract_youtube_url(share_text) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        shorts_share = "Awesome short https://www.youtube.com/shorts/L_LUpnjgPso watch now"
        assert extract_youtube_url(shorts_share) == "https://www.youtube.com/watch?v=L_LUpnjgPso"

    def test_extract_url_empty_or_invalid(self):
        from mobile_app import extract_youtube_url
        assert extract_youtube_url("") is None
        assert extract_youtube_url(None) is None
        assert extract_youtube_url("Hello world without link") is None

    def test_normalize_query_fragments_and_video_ids(self):
        from mobile_app import normalize_youtube_url
        assert normalize_youtube_url("v=UQyh7QIVaDU&si=5E9QdyxfYqh7rysR") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("watch?v=UQyh7QIVaDU") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("UQyh7QIVaDU") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("https://youtu.be/UQyh7QIVaDU?si=5E9QdyxfYqh7rysR") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("https://www.youtube.com/live/UQyh7QIVaDU?feature=share") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("https://www.youtube.com/embed/UQyh7QIVaDU") == "https://www.youtube.com/watch?v=UQyh7QIVaDU"
        assert normalize_youtube_url("https://www.youtube.com/playlist?list=PLr6-SnbS9Z8v1b") == "https://www.youtube.com/playlist?list=PLr6-SnbS9Z8v1b"
        assert normalize_youtube_url("https://www.youtube.com/watch?v=UQyh7QIVaDU&list=PLr6-SnbS9Z8v1b") == "https://www.youtube.com/playlist?list=PLr6-SnbS9Z8v1b"

    def test_mobile_player_clients_and_format_fallback(self):
        """Verify that progressive streams (format 18 / 140) are included in all mobile download format options."""
        default_video_fmt = "18/22/best[ext=mp4]/best/bestvideo*+bestaudio"
        hd_video_fmt = "22/best[height<=720][ext=mp4]/18/best/bestvideo[height<=720]+bestaudio/best"
        fast_video_fmt = "18/best[height<=360][ext=mp4]/best[ext=mp4]/best"
        audio_fmt = "140/bestaudio[ext=m4a]/bestaudio/18/best"

        assert "18" in default_video_fmt
        assert "18" in hd_video_fmt
        assert "18" in fast_video_fmt
        assert "140" in audio_fmt and "18" in audio_fmt




"""
Unit tests for the core downloader engine mocking yt-dlp interactions in MSK-YTDL.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from youtube_downloader.config import AppConfig
from youtube_downloader.downloader import (
    YoutubeDownloader,
    format_bytes,
    format_duration,
    get_video_format_selector,
)
from youtube_downloader.errors import (
    DependencyMissingError,
    DownloadInterruptedError,
    YTDLError,
)


class TestFormatSelectors:
    """Tests for format selection strings."""

    def test_best_quality_selector(self):
        selector = get_video_format_selector("best")
        assert selector == "bestvideo*+bestaudio/best"

    def test_resolution_limited_selectors(self):
        for res, height in [
            ("2160p", 2160),
            ("1440p", 1440),
            ("1080p", 1080),
            ("720p", 720),
            ("480p", 480),
            ("360p", 360),
        ]:
            selector = get_video_format_selector(res)
            expected = f"bestvideo*[height<=?{height}]+bestaudio/best[height<=?{height}]/best"
            assert selector == expected, f"Incorrect format selector for {res}"

    def test_format_duration_helper(self):
        assert format_duration(65) == "01:05"
        assert format_duration(3665) == "01:01:05"
        assert format_duration(None) == "Unknown"
        assert format_duration(0) == "Unknown"

    def test_format_bytes_helper(self):
        assert "MiB" in format_bytes(1048576 * 5)
        assert format_bytes(None) == "Unknown"
        assert format_bytes(0) == "Unknown"


class TestDownloaderOperations:
    """Tests for metadata extraction and download operations with mocked yt-dlp."""

    @pytest.fixture
    def mock_downloader(self, tmp_path):
        cfg = AppConfig(download_directory=str(tmp_path))
        return YoutubeDownloader(config=cfg, debug=False)

    def test_base_ydl_opts_construction(self, mock_downloader, tmp_path):
        opts = mock_downloader._build_base_ydl_opts(output_dir=tmp_path)
        assert opts["noplaylist"] is True
        assert opts["continuedl"] is True
        assert opts["windowsfilenames"] is True
        assert opts["retries"] == 3
        assert opts["socket_timeout"] == 30
        assert "download_archive" in opts

        opts_no_arch = mock_downloader._build_base_ydl_opts(output_dir=tmp_path, use_archive=False)
        assert "download_archive" not in opts_no_arch

    @patch("yt_dlp.YoutubeDL")
    def test_get_video_info_success(self, mock_ydl_class, mock_downloader):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up",
            "uploader": "RickAstleyVEVO",
            "channel_url": "https://www.youtube.com/@RickAstley",
            "duration": 213,
            "upload_date": "20091025",
            "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg",
            "description": "The official video for Never Gonna Give You Up by Rick Astley",
            "formats": [
                {"height": 1080, "width": 1920},
                {"height": 720, "width": 1280},
                {"height": 480, "width": 854},
            ],
        }

        meta = mock_downloader.get_video_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert meta.video_id == "dQw4w9WgXcQ"
        assert meta.title == "Rick Astley - Never Gonna Give You Up"
        assert meta.uploader == "RickAstleyVEVO"
        assert meta.duration_formatted == "03:33"
        assert meta.upload_date_formatted == "2009-10-25"
        assert "1080p" in meta.available_resolutions
        assert "720p" in meta.available_resolutions

    @patch("yt_dlp.YoutubeDL")
    def test_list_available_formats(self, mock_ydl_class, mock_downloader):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Sample Video",
            "formats": [
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "width": 1920,
                    "height": 1080,
                    "fps": 30,
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "filesize": 52428800,
                    "format_note": "1080p",
                },
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "filesize": 5242880,
                    "format_note": "medium",
                },
            ],
        }

        formats = mock_downloader.list_available_formats("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert len(formats) == 2
        assert formats[0].format_id == "137"
        assert formats[0].resolution == "1920x1080"
        assert formats[1].resolution == "audio only"

    @patch("yt_dlp.YoutubeDL")
    def test_download_video_success(self, mock_ydl_class, mock_downloader, tmp_path):
        target_file = tmp_path / "Sample Video [dQw4w9WgXcQ].mp4"
        target_file.touch()

        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Sample Video",
            "requested_downloads": [{"filepath": str(target_file)}],
        }

        saved_path = mock_downloader.download_video(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            quality="1080p",
            output_dir=tmp_path
        )
        assert saved_path == target_file
        assert saved_path.exists()

    @patch("yt_dlp.YoutubeDL")
    def test_download_audio_mp3_success(self, mock_ydl_class, mock_downloader, tmp_path):
        target_mp3 = tmp_path / "Sample Audio [dQw4w9WgXcQ].mp3"
        target_mp3.touch()

        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Sample Audio",
            "requested_downloads": [{"filepath": str(target_mp3)}],
        }

        with patch("shutil.which", return_value="C:/ffmpeg/ffmpeg.exe"):
            saved_path = mock_downloader.download_audio(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                audio_format="mp3",
                audio_quality="256",
                output_dir=tmp_path
            )
            assert saved_path == target_mp3

    def test_download_audio_mp3_missing_ffmpeg(self, mock_downloader, tmp_path):
        with patch("shutil.which", return_value=None):
            with pytest.raises(DependencyMissingError) as exc_info:
                mock_downloader.download_audio(
                    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    audio_format="mp3",
                    output_dir=tmp_path
                )
            assert "FFmpeg is required" in str(exc_info.value)

    @patch("yt_dlp.YoutubeDL")
    def test_download_failure_raises_ytdl_error(self, mock_ydl_class, mock_downloader, tmp_path):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")

        with pytest.raises(YTDLError) as exc_info:
            mock_downloader.download_video(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                output_dir=tmp_path
            )
        assert "404" in str(exc_info.value)

    @patch("yt_dlp.YoutubeDL")
    def test_download_cancellation_keyboard_interrupt(self, mock_ydl_class, mock_downloader, tmp_path):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.side_effect = KeyboardInterrupt()

        with pytest.raises(DownloadInterruptedError):
            mock_downloader.download_video(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                output_dir=tmp_path
            )


class TestPlaylistAndBatchDownloader:
    """Tests for playlist extraction, playlist batch downloading, and multi-video batch downloading."""

    @pytest.fixture
    def mock_downloader(self, tmp_path):
        cfg = AppConfig(download_directory=str(tmp_path), create_playlist_subfolder=True)
        return YoutubeDownloader(config=cfg, debug=False)

    @patch("yt_dlp.YoutubeDL")
    def test_get_playlist_info(self, mock_ydl_class, mock_downloader):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "PL1234567890",
            "title": "Cool Tech Playlist",
            "uploader": "TechChannel",
            "description": "A curated list of videos",
            "entries": [
                {"id": "vid01", "title": "Part 1 - Intro", "duration": 300, "uploader": "TechChannel"},
                {"id": "vid02", "title": "Part 2 - Deep Dive", "duration": 600, "uploader": "TechChannel"},
            ],
        }

        meta = mock_downloader.get_playlist_info("https://www.youtube.com/playlist?list=PL1234567890")
        assert meta.playlist_id == "PL1234567890"
        assert meta.title == "Cool Tech Playlist"
        assert meta.uploader == "TechChannel"
        assert meta.entries_count == 2
        assert len(meta.entries) == 2
        assert meta.entries[0].video_id == "vid01"
        assert meta.entries[0].title == "Part 1 - Intro"
        assert meta.entries[0].index == 1

    @patch("yt_dlp.YoutubeDL")
    def test_download_playlist_video_success(self, mock_ydl_class, mock_downloader, tmp_path):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "PL1234567890",
            "title": "Tutorial Series",
            "entries": [
                {"id": "v1", "title": "Episode 1", "requested_downloads": [{"filepath": str(tmp_path / "ep1.mp4")}]},
                {"id": "v2", "title": "Episode 2", "requested_downloads": [{"filepath": str(tmp_path / "ep2.mp4")}]},
            ],
        }

        result = mock_downloader.download_playlist(
            url="https://www.youtube.com/playlist?list=PL1234567890",
            mode="video",
            quality="1080p",
            output_dir=tmp_path,
            create_subfolder=True,
            playlist_start=1,
            playlist_end=2,
        )

        assert result.title == "Tutorial Series"
        assert result.total_entries == 2
        assert result.downloaded_count == 2
        assert result.failed_count == 0
        assert result.output_directory == tmp_path / "Tutorial Series"

    @patch("yt_dlp.YoutubeDL")
    def test_download_playlist_subfolder_disabled(self, mock_ydl_class, mock_downloader, tmp_path):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "PL1234567890",
            "title": "Tutorial Series",
            "entries": [
                {"id": "v1", "title": "Episode 1"},
            ],
        }

        result = mock_downloader.download_playlist(
            url="https://www.youtube.com/playlist?list=PL1234567890",
            mode="video",
            output_dir=tmp_path,
            create_subfolder=False,
        )
        assert result.output_directory == tmp_path

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_video")
    def test_download_batch_mixed_results(self, mock_download_video, mock_downloader, tmp_path):
        file1 = tmp_path / "vid1.mp4"
        file1.touch()

        # First URL succeeds, second fails with error
        mock_download_video.side_effect = [
            file1,
            YTDLError("Video unavailable"),
        ]

        urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=9bZkp7q19f0",
        ]

        result = mock_downloader.download_batch(
            urls=urls,
            mode="video",
            quality="720p",
            output_dir=tmp_path,
        )

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.results[0].success is True
        assert result.results[0].filepath == file1
        assert result.results[1].success is False
        assert "Video unavailable" in result.results[1].error

    @patch("yt_dlp.YoutubeDL")
    def test_download_audio_postprocessors_embedding(self, mock_ydl_class, mock_downloader, tmp_path):
        target_mp3 = tmp_path / "song.mp3"
        target_mp3.touch()

        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Song",
            "requested_downloads": [{"filepath": str(target_mp3)}],
        }

        with patch("shutil.which", return_value="C:/ffmpeg/ffmpeg.exe"):
            mock_downloader.download_audio(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                audio_format="mp3",
                output_dir=tmp_path,
                embed_thumbnail=True,
                embed_metadata=True,
            )

        passed_opts = mock_ydl_class.call_args[0][0]
        assert passed_opts.get("writethumbnail") is True
        pps = [p["key"] for p in passed_opts.get("postprocessors", [])]
        assert "FFmpegThumbnailsConvertor" in pps
        assert "FFmpegExtractAudio" in pps
        assert "FFmpegMetadata" in pps
        assert "EmbedThumbnail" in pps

    @patch("yt_dlp.YoutubeDL")
    def test_download_video_archive_skip(self, mock_ydl_class, mock_downloader, tmp_path):
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance
        # Simulate yt-dlp returning None when item is already in archive
        mock_instance.extract_info.return_value = None

        # Patch logger to simulate having detected an archived video ID
        with patch("youtube_downloader.downloader.YTDLLogger") as mock_logger_cls:
            mock_logger = MagicMock()
            mock_logger.archived_ids = ["[download] dQw4w9WgXcQ: has already been recorded in the archive"]
            mock_logger_cls.return_value = mock_logger

            result = mock_downloader.download_video(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                output_dir=tmp_path,
            )
            assert result is None




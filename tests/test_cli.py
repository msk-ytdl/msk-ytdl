"""
Unit tests for CLI argument parsing, interactive menu helpers, and main command runner in MSK-YTDL.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from youtube_downloader.cli import build_arg_parser, main


class TestCLIArgumentParser:
    """Tests for argparse configuration and default options."""

    def test_default_arguments(self):
        parser = build_arg_parser()
        args = parser.parse_args([])
        assert args.check is False
        assert args.url is None
        assert args.mode == "video"
        assert args.quality == "best"
        assert args.audio_format == "mp3"
        assert args.audio_quality == "192"
        assert args.output_dir is None
        assert args.info is False
        assert args.list_formats is False
        assert args.confirm_authorized is False
        assert args.debug is False

    def test_custom_arguments_parsing(self):
        parser = build_arg_parser()
        args = parser.parse_args([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--mode", "audio",
            "--quality", "1080p",
            "--audio-format", "best",
            "--audio-quality", "320",
            "--output-dir", "D:/Downloads",
            "--confirm-authorized",
            "--debug"
        ])
        assert args.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert args.mode == "audio"
        assert args.quality == "1080p"
        assert args.audio_format == "best"
        assert args.audio_quality == "320"
        assert args.output_dir == "D:/Downloads"
        assert args.confirm_authorized is True
        assert args.debug is True


class TestMainExecution:
    """Tests for main entrypoint execution paths."""

    @patch("youtube_downloader.cli.print_diagnostic_report", return_value=True)
    def test_main_check_flag_success(self, mock_report):
        exit_code = main(["--check"])
        assert exit_code == 0
        mock_report.assert_called_once()

    @patch("youtube_downloader.cli.print_diagnostic_report", return_value=False)
    def test_main_check_flag_failure(self, mock_report):
        exit_code = main(["--check"])
        assert exit_code == 3

    def test_main_cli_mode_missing_url(self):
        # Passing info flag without URL
        exit_code = main(["--info"])
        assert exit_code == 2

    def test_main_download_without_authorization_in_non_interactive_mode(self):
        # Non-interactive stdin without confirmation flag
        with patch("sys.stdin.isatty", return_value=False):
            exit_code = main([
                "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "--mode", "video",
            ])
            # Authorization denied / unconfirmed
            assert exit_code == 4

    @patch("youtube_downloader.cli.display_video_info")
    def test_main_info_flag(self, mock_display_info):
        exit_code = main([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--info",
        ])
        assert exit_code == 0
        mock_display_info.assert_called_once()

    @patch("youtube_downloader.cli.display_formats_table")
    def test_main_list_formats_flag(self, mock_display_formats):
        exit_code = main([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--list-formats",
        ])
        assert exit_code == 0
        mock_display_formats.assert_called_once()

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_video")
    def test_main_download_video_success(self, mock_download, tmp_path):
        mock_download.return_value = tmp_path / "video.mp4"
        exit_code = main([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--mode", "video",
            "--quality", "1080p",
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download.assert_called_once()

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_audio")
    def test_main_download_audio_success(self, mock_download_audio, tmp_path):
        mock_download_audio.return_value = tmp_path / "audio.mp3"
        exit_code = main([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--mode", "audio",
            "--audio-format", "mp3",
            "--audio-quality", "320",
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download_audio.assert_called_once()

    def test_cli_playlist_and_batch_arguments_parsing(self):
        parser = build_arg_parser()
        args = parser.parse_args([
            "--playlist",
            "--playlist-start", "2",
            "--playlist-end", "5",
            "--playlist-items", "2,3,4,5",
            "--no-subfolder",
            "--urls", "https://youtu.be/a", "https://youtu.be/b",
            "--batch-file", "urls.txt",
        ])
        assert args.playlist is True
        assert args.playlist_start == 2
        assert args.playlist_end == 5
        assert args.playlist_items == "2,3,4,5"
        assert args.no_subfolder is True
        assert "https://youtu.be/a" in args.urls
        assert "https://youtu.be/b" in args.urls
        assert args.batch_file == "urls.txt"

    @patch("youtube_downloader.cli.display_playlist_info")
    def test_main_playlist_info_flag(self, mock_display_playlist_info):
        exit_code = main([
            "--url", "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f",
            "--playlist",
            "--info",
        ])
        assert exit_code == 0
        mock_display_playlist_info.assert_called_once()

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_playlist")
    def test_main_playlist_download_success(self, mock_download_playlist, tmp_path):
        from youtube_downloader.downloader import PlaylistDownloadResult
        mock_download_playlist.return_value = PlaylistDownloadResult(
            playlist_id="PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f",
            title="Test Playlist",
            total_entries=2,
            downloaded_count=2,
            failed_count=0,
            output_directory=tmp_path,
            failed_items=[],
        )
        exit_code = main([
            "--url", "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f",
            "--playlist",
            "--mode", "video",
            "--quality", "720p",
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download_playlist.assert_called_once()

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_batch")
    def test_main_batch_urls_download_success(self, mock_download_batch):
        from youtube_downloader.downloader import BatchDownloadResult
        mock_download_batch.return_value = BatchDownloadResult(
            total=2,
            succeeded=2,
            failed=0,
            results=[],
        )
        exit_code = main([
            "--urls", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=9bZkp7q19f0",
            "--mode", "video",
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download_batch.assert_called_once()

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_batch")
    def test_main_batch_file_download_success(self, mock_download_batch, tmp_path):
        from youtube_downloader.downloader import BatchDownloadResult
        batch_file = tmp_path / "urls.txt"
        batch_file.write_text("https://www.youtube.com/watch?v=dQw4w9WgXcQ\n", encoding="utf-8")

        mock_download_batch.return_value = BatchDownloadResult(
            total=1,
            succeeded=1,
            failed=0,
            results=[],
        )
        exit_code = main([
            "--batch-file", str(batch_file),
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download_batch.assert_called_once()

    def test_archive_and_embedding_arguments_parsing(self):
        parser = build_arg_parser()
        args = parser.parse_args([
            "--archive-file", "my_archive.txt",
            "--no-archive",
            "--no-embed-thumbnail",
            "--no-embed-metadata",
        ])
        assert args.archive_file == "my_archive.txt"
        assert args.no_archive is True
        assert args.no_embed_thumbnail is True
        assert args.no_embed_metadata is True

    @patch("youtube_downloader.downloader.YoutubeDownloader.download_audio")
    def test_main_download_audio_with_archive_flags(self, mock_download_audio, tmp_path):
        mock_download_audio.return_value = tmp_path / "song.mp3"
        exit_code = main([
            "--url", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--mode", "audio",
            "--archive-file", str(tmp_path / "archive.txt"),
            "--no-embed-thumbnail",
            "--no-embed-metadata",
            "--confirm-authorized",
        ])
        assert exit_code == 0
        mock_download_audio.assert_called_once()
        call_kwargs = mock_download_audio.call_args[1]
        assert call_kwargs.get("embed_thumbnail") is False
        assert call_kwargs.get("embed_metadata") is False

    def test_package_windows_arg_parsing(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--package-windows"])
        assert args.package_windows is True

    @patch("build_exe.main", return_value=0)
    def test_main_package_windows_execution(self, mock_build_main):
        exit_code = main(["--package-windows"])
        assert exit_code == 0
        mock_build_main.assert_called_once()

    def test_web_arg_parsing(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--web", "--port", "9000"])
        assert args.web is True
        assert args.port == 9000

    @patch("youtube_downloader.web_server.run_web_server")
    def test_main_web_execution(self, mock_run_web):
        exit_code = main(["--web", "--port", "8899"])
        assert exit_code == 0
        mock_run_web.assert_called_once_with(port=8899)



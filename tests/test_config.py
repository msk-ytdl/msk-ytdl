"""
Unit tests for configuration loading, saving, validation, and directory checks in MSK-YTDL.
"""

import json
from pathlib import Path

import pytest

from youtube_downloader.config import (
    AppConfig,
    ensure_directory_writable,
    load_config,
    save_config,
    validate_config_dict,
)
from youtube_downloader.errors import OutputDirectoryError


class TestConfigManagement:
    """Tests for application settings validation and persistence."""

    def test_default_config_values(self):
        cfg = AppConfig()
        assert cfg.default_video_quality == "best"
        assert cfg.default_audio_format == "mp3"
        assert cfg.default_audio_quality == "192"
        assert cfg.show_progress is True
        assert cfg.max_retries == 3
        assert cfg.use_download_archive is True
        assert cfg.archive_file_path is None
        assert cfg.embed_thumbnail is True
        assert cfg.embed_metadata is True
        assert "YouTube" in cfg.download_directory
        assert "archive.txt" in str(cfg.get_resolved_archive_path())

    def test_custom_archive_and_embedding_config(self):
        data = {
            "use_download_archive": False,
            "archive_file_path": "D:/MyArchives/archive.txt",
            "embed_thumbnail": False,
            "embed_metadata": False,
        }
        cfg = validate_config_dict(data)
        assert cfg.use_download_archive is False
        assert cfg.archive_file_path == "D:/MyArchives/archive.txt"
        assert cfg.embed_thumbnail is False
        assert cfg.embed_metadata is False
        assert "MyArchives" in str(cfg.get_resolved_archive_path())

    def test_validate_config_dict_with_valid_data(self):
        data = {
            "download_directory": "D:/MyVideos",
            "default_video_quality": "1080p",
            "default_audio_format": "best",
            "default_audio_quality": "320",
            "show_progress": False,
            "max_retries": 5,
        }
        cfg = validate_config_dict(data)
        assert cfg.download_directory == "D:/MyVideos"
        assert cfg.default_video_quality == "1080p"
        assert cfg.default_audio_format == "best"
        assert cfg.default_audio_quality == "320"
        assert cfg.show_progress is False
        assert cfg.max_retries == 5

    def test_validate_config_dict_replaces_invalid_fields_with_defaults(self):
        data = {
            "download_directory": "",
            "default_video_quality": "unsupported_res",
            "default_audio_format": "unsupported_format",
            "default_audio_quality": "999",
            "show_progress": "not_a_bool",
            "max_retries": "invalid_num",
        }
        cfg = validate_config_dict(data)
        assert cfg.default_video_quality == "best"
        assert cfg.default_audio_format == "mp3"
        assert cfg.default_audio_quality == "192"
        assert cfg.max_retries == 3

    def test_save_and_load_config_atomic(self, tmp_path, monkeypatch):
        test_config_file = tmp_path / ".msk_ytdl" / "config.json"
        monkeypatch.setattr("youtube_downloader.config.get_config_dir", lambda: tmp_path / ".msk_ytdl")
        monkeypatch.setattr("youtube_downloader.config.get_config_file_path", lambda: test_config_file)

        # 1. Load when file does not exist -> creates default
        cfg = load_config()
        assert test_config_file.exists()
        assert cfg.default_video_quality == "best"

        # 2. Modify and save
        cfg.default_video_quality = "720p"
        save_config(cfg)

        # 3. Reload and verify
        reloaded = load_config()
        assert reloaded.default_video_quality == "720p"

    def test_recover_from_corrupted_config(self, tmp_path, monkeypatch):
        test_config_file = tmp_path / ".msk_ytdl" / "config.json"
        test_config_file.parent.mkdir(parents=True, exist_ok=True)
        test_config_file.write_text("{ corrupted invalid json ...", encoding="utf-8")

        monkeypatch.setattr("youtube_downloader.config.get_config_dir", lambda: tmp_path / ".msk_ytdl")
        monkeypatch.setattr("youtube_downloader.config.get_config_file_path", lambda: test_config_file)

        # Loading corrupted file should recover with defaults and create a .bak file
        cfg = load_config()
        assert cfg.default_video_quality == "best"

        # Check backup file existence
        backup_files = list(test_config_file.parent.glob("config.json.corrupted.*.bak"))
        assert len(backup_files) == 1

    def test_ensure_directory_writable_success(self, tmp_path):
        target_dir = tmp_path / "downloads" / "youtube"
        resolved = ensure_directory_writable(target_dir)
        assert resolved.exists()
        assert resolved.is_dir()

    def test_ensure_directory_writable_failure(self, monkeypatch, tmp_path):
        target_dir = tmp_path / "forbidden"

        def mock_mkdir(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        with pytest.raises(OutputDirectoryError) as exc_info:
            ensure_directory_writable(target_dir)
        assert "Failed to create download directory" in str(exc_info.value)

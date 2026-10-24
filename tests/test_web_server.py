"""
Unit tests for the MSK-YTDL local web server and REST API.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from youtube_downloader.web_server import (
    JobManager,
    MSKWebRequestHandler,
    get_local_ip,
    get_web_dir,
)


class TestWebComponents:
    """Tests for job manager and utility functions."""

    def test_job_manager_lifecycle(self):
        jm = JobManager()
        job = jm.create_job(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="video",
            quality="1080p",
            audio_format="mp3",
            audio_quality="320"
        )
        assert job.job_id is not None
        assert job.status == "queued"

        retrieved = jm.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

        jobs_list = jm.list_jobs()
        assert len(jobs_list) == 1
        assert jobs_list[0]["id"] == job.job_id
        assert jobs_list[0]["mode"] == "video"

    def test_get_local_ip(self):
        ip = get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_get_web_dir(self):
        web_dir = get_web_dir()
        assert web_dir.exists()
        assert (web_dir / "index.html").exists()


class TestWebRequestHandler:
    """Tests for HTTP API endpoints using mocked handler."""

    @patch("youtube_downloader.web_server.load_config")
    def test_api_status_endpoint(self, mock_load_config):
        from youtube_downloader.config import AppConfig

        mock_load_config.return_value = AppConfig()
        handler = MagicMock()
        MSKWebRequestHandler.handle_api_status(handler)

        handler.send_json.assert_called_once()
        args = handler.send_json.call_args[0][0]
        assert "version" in args
        assert "download_directory" in args
        assert "host_ip" in args

    def test_api_inspect_missing_url(self):
        handler = MagicMock()
        MSKWebRequestHandler.handle_api_inspect(handler, {})
        handler.send_json.assert_called_once()
        status = handler.send_json.call_args[1].get("status")
        assert status == 400

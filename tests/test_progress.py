"""
Unit tests for Rich progress hook callbacks and logger handling in MSK-YTDL.
"""

from youtube_downloader.progress import DownloadProgressManager, YTDLLogger


class TestProgressHooks:
    """Tests for progress hooks with known, unknown, and completed stages."""

    def test_progress_hook_with_known_total(self):
        with DownloadProgressManager(enabled=True) as pm:
            # Simulate downloading callback with known total bytes
            payload = {
                "status": "downloading",
                "downloaded_bytes": 5242880,
                "total_bytes": 10485760,
                "speed": 1048576,
                "eta": 5,
                "filename": "C:/Downloads/test.mp4",
            }
            # Must execute without exception
            pm.progress_hook(payload)
            assert pm.task_id is not None
            task = pm.progress.tasks[pm.task_id]
            assert task.completed == 5242880
            assert task.total == 10485760

    def test_progress_hook_with_unknown_total(self):
        with DownloadProgressManager(enabled=True) as pm:
            # Simulate streaming download where total size is unknown / None
            payload = {
                "status": "downloading",
                "downloaded_bytes": 1048576,
                "total_bytes": None,
                "total_bytes_estimate": None,
                "speed": None,
                "eta": None,
                "filename": "live_stream.mp4",
            }
            pm.progress_hook(payload)
            task = pm.progress.tasks[pm.task_id]
            assert task.completed == 1048576
            assert task.total is None

    def test_progress_hook_finished(self):
        with DownloadProgressManager(enabled=True) as pm:
            payload = {
                "status": "finished",
                "filename": "finished.mp4",
            }
            pm.progress_hook(payload)
            assert pm._finished is True

    def test_postprocessor_hook_lifecycle(self):
        with DownloadProgressManager(enabled=True) as pm:
            # Postprocessor started
            pm.postprocessor_hook({
                "status": "started",
                "postprocessor": "FFmpegExtractAudio",
            })
            task = pm.progress.tasks[pm.task_id]
            assert "FFmpegExtractAudio" in task.description

            # Postprocessor finished
            pm.postprocessor_hook({
                "status": "finished",
                "postprocessor": "FFmpegExtractAudio",
            })
            task = pm.progress.tasks[pm.task_id]
            assert task.fields["stage"] == "Finalizing"

    def test_progress_hook_exception_resilience(self):
        """Ensures that unexpected malformed data in hook does not crash application."""
        with DownloadProgressManager(enabled=True) as pm:
            pm.progress_hook("corrupted payload")
            pm.postprocessor_hook(None)


class TestYTDLLogger:
    """Tests for custom yt-dlp logger output routing."""

    def test_logger_warning_and_error_capture(self):
        logger = YTDLLogger(debug=False)
        logger.warning("Test warning message")
        logger.error("Test error message")
        assert len(logger.warnings) == 1
        assert "Test warning" in logger.warnings[0]
        assert len(logger.errors) == 1
        assert "Test error" in logger.errors[0]

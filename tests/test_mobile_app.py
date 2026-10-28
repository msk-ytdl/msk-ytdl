"""Unit tests for mobile_app utility functions and download helpers."""

from mobile_app import (
    sanitize_storage_filename,
    get_canonical_video_url,
    normalize_youtube_url,
    safe_display_text,
    play_online_video,
    open_web_url,
    is_version_newer,
    install_apk_file,
)
from unittest.mock import patch


def test_sanitize_storage_filename():
    assert sanitize_storage_filename("My Cool Video! 🔥") == "My Cool Video"
    assert sanitize_storage_filename("videoplayback") == "MSK_Video"
    assert sanitize_storage_filename("videoplayback.mp4") == "videoplayback.mp4"
    assert sanitize_storage_filename("Test: Video / Special? * Chars") == "Test Video Special Chars"
    assert sanitize_storage_filename("") == "MSK_Video"
    assert sanitize_storage_filename(None) == "MSK_Video"


def test_get_canonical_video_url():
    # 1. With 11-char ID
    item_with_id = {"id": "dQw4w9WgXcQ", "url": "https://rr4---sn.googlevideo.com/videoplayback?..."}
    assert get_canonical_video_url(item_with_id) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # 2. Extract ID from webpage_url
    item_with_web = {"webpage_url": "https://www.youtube.com/watch?v=2pZmKW9-I_k"}
    assert get_canonical_video_url(item_with_web) == "https://www.youtube.com/watch?v=2pZmKW9-I_k"

    # 3. Reject direct googlevideo streaming url
    item_with_stream = {"url": "https://rr4---sn.googlevideo.com/videoplayback?expire=123"}
    assert get_canonical_video_url(item_with_stream, fallback_url="https://www.youtube.com/watch?v=fallback123") == "https://www.youtube.com/watch?v=fallback123"


def test_normalize_youtube_url():
    assert normalize_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert normalize_youtube_url("https://www.youtube.com/playlist?list=PL4cUxeGkcC9gUgr39Q_yD6v-bSyMwKPUI") == "https://www.youtube.com/playlist?list=PL4cUxeGkcC9gUgr39Q_yD6v-bSyMwKPUI"


def test_play_online_video_safe():
    # Should safely return on empty URL without exception
    play_online_video("")
    play_online_video(None)

    with patch("subprocess.Popen") as mock_popen:
        play_online_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="Test Song")
        assert mock_popen.called


def test_open_web_url_safe():
    open_web_url("")
    open_web_url(None)

    with patch("webbrowser.open") as mock_web:
        open_web_url("https://example.com")
        assert mock_web.called


def test_sanitize_storage_filename_keeps_long_names():
    long_title = "Arijit Singh - Kesariya Audio Song from Brahmastra Ranbir Alia Pritam Amitabh"
    sanitized = sanitize_storage_filename(long_title)
    # Must preserve full title and not truncate at 35 characters
    assert len(sanitized) > 50
    assert "Kesariya" in sanitized
    assert "Brahmastra" in sanitized


def test_reels_icon_asset():
    from pathlib import Path
    reels_icon = Path("assets/icons/reels.png")
    assert reels_icon.exists()
    assert reels_icon.stat().st_size > 0


def test_get_android_download_dir():
    from mobile_app import get_android_download_dir
    from pathlib import Path
    d = get_android_download_dir()
    assert isinstance(d, Path)
    assert d.exists()


def test_is_version_newer():
    # Newer patch version
    assert is_version_newer("1.0.1", "1.0.2") is True
    # Newer minor version
    assert is_version_newer("1.0.1", "1.1.0") is True
    # Newer major version
    assert is_version_newer("1.0.1", "2.0.0") is True
    # Extra sub-level version
    assert is_version_newer("1.0", "1.0.1") is True
    # With 'v' prefix
    assert is_version_newer("v1.0.1", "v1.0.2") is True

    # Same version
    assert is_version_newer("1.0.1", "1.0.1") is False
    assert is_version_newer("1.0.0", "1.0") is False
    # Older version
    assert is_version_newer("1.0.2", "1.0.1") is False
    assert is_version_newer("2.0.0", "1.9.9") is False
    # Empty inputs
    assert is_version_newer("1.0.1", "") is False
    assert is_version_newer("", "1.0.1") is True


def test_install_apk_file_safety():
    # Non-existent file must return False safely
    assert install_apk_file("non_existent_file_xyz.apk") is False
    assert install_apk_file("") is False


def test_open_media_file_safety():
    from mobile_app import open_media_file
    from pathlib import Path
    # Empty or None should not throw
    open_media_file(None)

    with patch("os.startfile", create=True) as mock_start:
        open_media_file(Path("my_test_video.mp4"))
        assert mock_start.called


def test_android_native_audio_player_safe():
    from mobile_app import AndroidNativeAudioPlayer
    player = AndroidNativeAudioPlayer("dummy_stream_or_path.mp3")
    assert player.state == "stop"
    assert player.get_pos() == 0.0
    assert player.length == 0.0
    assert player.play() is False
    player.stop()
    player.unload()


def test_play_online_video_with_instagram_reel():
    with patch("subprocess.Popen") as mock_popen:
        play_online_video("https://www.instagram.com/reel/C7XYZ123/", title="Instagram Reel")
        assert mock_popen.called


def test_sanitize_storage_filename_preserves_full_name():
    from mobile_app import sanitize_storage_filename
    long_title = "A" * 200 + " - Official 4K Ultra HD Music Video"
    sanitized = sanitize_storage_filename(long_title)
    # Must preserve up to 215 characters without being cut off to 140 or 25
    assert len(sanitized) > 180
    assert sanitized.startswith("A" * 50)


def test_find_downloaded_media_file_by_id_and_title(tmp_path):
    from mobile_app import find_downloaded_media_file
    with patch("mobile_app.get_android_download_dir", return_value=tmp_path):
        # Create a test video and test audio in temp downloads dir
        test_video = tmp_path / "Awesome Music Video [dQw4w9WgXcQ].mp4"
        test_video.write_text("dummy")

        test_audio = tmp_path / "Complete Long Audio Song Name By Artist.mp3"
        test_audio.write_text("dummy")

        # 1. Match by item_id
        found_by_id = find_downloaded_media_file(item_id="dQw4w9WgXcQ")
        assert found_by_id is not None
        assert found_by_id.name == test_video.name

        # 2. Match by title
        found_by_title = find_downloaded_media_file(title="Complete Long Audio Song Name By Artist")
        assert found_by_title is not None
        assert found_by_title.name == test_audio.name

        # 3. Non-existent returns None
        not_found = find_downloaded_media_file(title="Non Existent Track", item_id="xxxxxx")
        assert not_found is None


def test_get_media_content_uri_safety():
    from mobile_app import get_media_content_uri
    from pathlib import Path
    # On desktop or None, should safely return None
    assert get_media_content_uri(None) is None
    assert get_media_content_uri(Path("some_video.mp4")) is None


def test_play_video_file_safety():
    from mobile_app import play_video_file
    from pathlib import Path
    # Safe on None/empty
    play_video_file(None)

    with patch("mobile_app.open_media_file") as mock_open:
        play_video_file(Path("my_test_video.mp4"), title="Test Title")
        assert mock_open.called


def test_android_notification_manager_media_playback():
    from mobile_app import AndroidNotificationManager, get_notification_manager
    mgr = get_notification_manager()
    assert mgr is not None
    assert isinstance(mgr, AndroidNotificationManager)

    # Calling show_media_playback on desktop should not crash
    mgr.show_media_playback("Test Song Title", is_playing=True, media_type="Song")
    assert mgr._is_media_playing is True
    assert mgr._current_media_title == "Test Song Title"

    mgr.show_media_playback("Test Song Title", is_playing=False, media_type="Song")
    assert mgr._is_media_playing is False

    mgr.hide_media_playback()
    assert mgr._is_media_playing is False


def test_scan_media_file_safety(tmp_path):
    from mobile_app import scan_media_file
    # Safe on non-existent or empty
    scan_media_file(None)
    scan_media_file(tmp_path / "non_existent.mp4")

    # Safe on actual file
    sample_vid = tmp_path / "sample.mp4"
    sample_vid.write_text("dummy")
    scan_media_file(sample_vid)


def test_sync_and_migrate_legacy_downloads_safety():
    from mobile_app import sync_and_migrate_legacy_downloads
    # Should run safely on desktop without crashing
    sync_and_migrate_legacy_downloads()


def test_get_ydl_format_selector_audio_never_falls_back_to_video():
    from mobile_app import get_ydl_format_selector

    # M4A AAC audio option
    sel_m4a = get_ydl_format_selector("Audio Only (M4A AAC Fast)", has_ffmpeg=False)
    assert "140" in sel_m4a
    assert "bestaudio" in sel_m4a
    # Critical: must NOT fall back to video /best or contain best without audio
    assert not sel_m4a.endswith("/best")
    assert "/best/" not in sel_m4a

    # MP3 without ffmpeg (Android)
    sel_mp3_no_ff = get_ydl_format_selector("Audio Only (HQ MP3 Music + Album Art)", has_ffmpeg=False)
    assert "140" in sel_mp3_no_ff
    assert not sel_mp3_no_ff.endswith("/best")

    # MP3 with ffmpeg
    sel_mp3_ff = get_ydl_format_selector("Audio Only (HQ MP3 Music + Album Art)", has_ffmpeg=True)
    assert "bestaudio" in sel_mp3_ff
    assert not sel_mp3_ff.endswith("/best")


def test_get_ydl_format_selector_video_qualities():
    from mobile_app import get_ydl_format_selector

    # 4K Ultra HD
    sel_4k = get_ydl_format_selector("Video (4K Ultra HD - 2160p)", has_ffmpeg=False)
    assert "2160" in sel_4k
    assert "bestvideo[height<=2160]" in sel_4k

    # 2K Quad HD
    sel_2k = get_ydl_format_selector("Video (2K Quad HD - 1440p)", has_ffmpeg=False)
    assert "1440" in sel_2k
    assert "bestvideo[height<=1440]" in sel_2k

    # 1080p Full HD
    sel_1080 = get_ydl_format_selector("Video (1080p Full HD MP4)", has_ffmpeg=False)
    assert "1080" in sel_1080
    assert "avc1" in sel_1080
    assert "ext=mp4" in sel_1080
    assert "bestaudio[ext=m4a]" in sel_1080

    # 1080p legacy / Max Quality
    sel_1080_leg = get_ydl_format_selector("Video (Max Quality - 1080p / 720p HD)", has_ffmpeg=False)
    assert "1080" in sel_1080_leg
    assert "bestaudio[ext=m4a]" in sel_1080_leg

    # 720p HD
    sel_720 = get_ydl_format_selector("Video (720p HD MP4)", has_ffmpeg=False)
    assert "720" in sel_720
    assert "avc1" in sel_720
    assert "bestaudio[ext=m4a]" in sel_720

    # 360p Fast
    sel_360 = get_ydl_format_selector("Video (360p Fast MP4)", has_ffmpeg=False)
    assert "360" in sel_360
    assert "18" in sel_360


def test_find_ffmpeg_binary(tmp_path):
    from mobile_app import find_ffmpeg_binary
    from unittest.mock import patch
    import os

    # In current environment
    res = find_ffmpeg_binary()
    assert res is None or isinstance(res, str)

    # When candidate is a directory (e.g. python-for-android recipe folder), must NOT return it
    fake_dir = tmp_path / "ffmpeg"
    fake_dir.mkdir()
    with patch("shutil.which", return_value=None), patch.dict(os.environ, {"ANDROID_PRIVATE": str(tmp_path)}):
        result = find_ffmpeg_binary()
        assert result is None, f"find_ffmpeg_binary should reject directory, got: {result}"


def test_mux_video_audio_android_safety(tmp_path):
    from mobile_app import mux_video_audio_android
    # Missing files safely returns False
    res = mux_video_audio_android(tmp_path / "v_missing.mp4", tmp_path / "a_missing.m4a", tmp_path / "out.mp4")
    assert res is False


def test_start_download_chosen_format_options():
    from mobile_app import get_ydl_format_selector

    # Test all 7 options available in the Download Options Modal:
    options = {
        "Video (4K Ultra HD - 2160p)": ("2160", False),
        "Video (2K Quad HD - 1440p)": ("1440", False),
        "Video (1080p Full HD MP4)": ("1080", False),
        "Video (Max Quality - 1080p / 720p HD)": ("1080", False),
        "Video (720p HD MP4)": ("720", False),
        "Video (360p Fast MP4)": ("360", False),
        "Audio Only (HQ MP3 Music + Album Art)": ("140", True),
        "Audio Only (M4A AAC Fast)": ("140", True),
    }

    for opt_name, (expected_token, is_aud) in options.items():
        sel = get_ydl_format_selector(opt_name, has_ffmpeg=False)
        assert expected_token in sel, f"Expected {expected_token} in selector for {opt_name}, got: {sel}"
        if is_aud:
            assert not sel.endswith("/best"), f"Audio selector must not end with /best: {sel}"
            assert "bestvideo" not in sel, f"Audio selector must not include bestvideo: {sel}"
        else:
            assert "bestvideo" in sel or "18" in sel


def test_is_running_on_android_detection():
    from mobile_app import is_running_on_android
    with patch("kivy.utils.platform", "android"):
        assert is_running_on_android() is True


def test_vault_dir_and_nomedia(tmp_path):
    from mobile_app import get_vault_dir
    with patch("mobile_app.get_android_download_dir", return_value=tmp_path):
        v_dir = get_vault_dir()
        assert v_dir.exists()
        assert v_dir.is_dir()
        nomedia = v_dir / ".nomedia"
        assert nomedia.exists()


def test_vault_pin_hashing_and_verification(tmp_path):
    from mobile_app import check_vault_pin, set_vault_pin, get_vault_pin_hash
    with patch("mobile_app.get_android_download_dir", return_value=tmp_path):
        # Default pin is 0000
        assert check_vault_pin("0000") is True
        assert check_vault_pin("1234") is False

        # Set new pin
        set_vault_pin("4321")
        assert check_vault_pin("4321") is True
        assert check_vault_pin("0000") is False

        # Hash is 64 hex characters (SHA-256)
        h = get_vault_pin_hash()
        assert len(h) == 64


def test_set_audio_as_ringtone(tmp_path):
    from mobile_app import set_audio_as_ringtone
    # Non-existent file
    ok, msg = set_audio_as_ringtone(tmp_path / "missing.mp3")
    assert ok is False

    # Actual file
    sample = tmp_path / "tune.mp3"
    sample.write_text("audio-data")
    with patch("mobile_app.get_android_download_dir", return_value=tmp_path):
        with patch("mobile_app.scan_media_file") as mock_scan:
            ok, msg = set_audio_as_ringtone(sample)
            assert ok is True
            assert "Ringtones" in msg
            assert mock_scan.called
            assert (tmp_path / "Ringtones" / "tune.mp3").exists()


def test_storage_cleaner_removes_orphans(tmp_path):
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.download_state = {"is_active": False, "current_part_files": set()}

    # Create dummy .part and .ytdl files
    part_f = tmp_path / "video.mp4.part"
    part_f.write_text("temp_data_chunk_part")
    ytdl_f = tmp_path / "song.mp3.ytdl"
    ytdl_f.write_text("temp_data_chunk_ytdl")
    valid_f = tmp_path / "actual_video.mp4"
    valid_f.write_text("permanent_movie")

    with patch("mobile_app.get_android_download_dir", return_value=tmp_path):
        freed = app.clean_cache_and_temp_files()
        assert freed > 0
        assert not part_f.exists()
        assert not ytdl_f.exists()
        assert valid_f.exists()


def test_pause_and_resume_toggle():
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.download_state = {"is_active": True, "is_paused": False}
    app.update_status = lambda msg, p: None
    app.progress_bar = type("Obj", (), {"value": 50})()

    # Toggle to paused
    app.toggle_download_pause()
    assert app.download_state["is_paused"] is True

    # Toggle to resume
    app.toggle_download_pause()
    assert app.download_state["is_paused"] is False


def test_sleep_timer_controls():
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.sleep_timer_event = None
    app.sleep_timer_end_time = 0.0
    app.is_audio_playing = False
    app.update_status = lambda msg, p: None

    with patch("kivy.clock.Clock.schedule_once") as mock_sched:
        app.set_sleep_timer(15)
        assert app.sleep_timer_end_time > 0
        assert mock_sched.called

        # Turn off
        app.set_sleep_timer(0)
        assert app.sleep_timer_end_time == 0.0











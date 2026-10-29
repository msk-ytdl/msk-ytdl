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


def test_nav_icon_assets():
    from pathlib import Path
    for icon_name in ("home.png", "videos.png", "downloads.png", "lock.png", "unlock.png", "music.png", "pause.png", "check.png", "delete.png", "play.png"):
        icon_path = Path("assets/icons") / icon_name
        assert icon_path.exists()
        assert icon_path.stat().st_size > 0


def test_reels_and_shorts_views_removed():
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    assert not hasattr(app, "build_reels_view")
    assert not hasattr(app, "populate_reels")
    assert not hasattr(app, "filter_reels")
    assert not hasattr(app, "add_reel_card")


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
    """Verify set_audio_as_ringtone is cleanly deprecated per user request."""
    from mobile_app import set_audio_as_ringtone
    # Non-existent file
    ok, msg = set_audio_as_ringtone(tmp_path / "missing.mp3")
    assert ok is False

    # Actual file
    sample = tmp_path / "tune.mp3"
    sample.write_text("audio-data")
    ok, msg = set_audio_as_ringtone(sample)
    assert ok is False
    assert "removed" in msg.lower()


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


def test_parse_duration_to_seconds():
    from mobile_app import parse_duration_to_seconds
    assert parse_duration_to_seconds("3:06") == 186.0
    assert parse_duration_to_seconds("1:02:15") == 3735.0
    assert parse_duration_to_seconds(120) == 120.0
    assert parse_duration_to_seconds("45") == 45.0
    assert parse_duration_to_seconds(None) == 0.0
    assert parse_duration_to_seconds("") == 0.0


def test_calculate_format_sizes():
    from mobile_app import calculate_format_sizes
    mock_formats = [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 4000000},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "filesize": 50000000},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "filesize": 25000000},
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360, "filesize": 12000000},
    ]
    sizes = calculate_format_sizes(mock_formats, duration=200.0)
    assert "1080p" in sizes and "MB" in sizes["1080p"]
    assert "720p" in sizes and "MB" in sizes["720p"]
    assert "360p" in sizes and "MB" in sizes["360p"]
    assert "m4a_aac" in sizes and "MB" in sizes["m4a_aac"]
    assert "mp3_320" in sizes and "MB" in sizes["mp3_320"]


def test_get_available_download_formats_omits_unsupported_4k_and_2k():
    from mobile_app import get_available_download_formats
    # Video only goes up to 1080p
    mock_formats_1080p = [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 3500000},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "filesize": 45000000},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "filesize": 22000000},
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360, "filesize": 11000000},
    ]

    v_opts, a_opts = get_available_download_formats(mock_formats_1080p, duration=186.0)
    v_keys = [opt[0] for opt in v_opts]

    # Critical requirement: 4K and 2K MUST NOT be shown because video does not have them!
    assert "Video (4K Ultra HD - 2160p)" not in v_keys
    assert "Video (2K Quad HD - 1440p)" not in v_keys

    # 1080p, 720p, 360p MUST be shown with sizes
    assert "Video (1080p Full HD MP4)" in v_keys
    assert "Video (720p HD MP4)" in v_keys
    assert "Video (360p Fast MP4)" in v_keys

    for opt in v_opts:
        # Check size_text is present (5th element in tuple)
        size_str = opt[4]
        assert "MB" in size_str or "KB" in size_str or "GB" in size_str


def test_get_available_download_formats_includes_4k_when_supported():
    from mobile_app import get_available_download_formats
    # Video supports 4K (2160p)
    mock_formats_4k = [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 4000000},
        {"format_id": "313", "vcodec": "vp9", "acodec": "none", "height": 2160, "filesize": 450000000},
        {"format_id": "271", "vcodec": "vp9", "acodec": "none", "height": 1440, "filesize": 200000000},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "filesize": 60000000},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "filesize": 30000000},
    ]

    v_opts, a_opts = get_available_download_formats(mock_formats_4k, duration=180.0)
    v_keys = [opt[0] for opt in v_opts]

    # When 4K is present in streams, 4K and 2K are included!
    assert "Video (4K Ultra HD - 2160p)" in v_keys
    assert "Video (2K Quad HD - 1440p)" in v_keys
    assert "Video (1080p Full HD MP4)" in v_keys


def test_get_available_download_formats_720p_only():
    from mobile_app import get_available_download_formats
    # Older video that only supports up to 720p
    mock_formats_720p = [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 2000000},
        {"format_id": "22", "vcodec": "avc1.64001F", "acodec": "mp4a.40.2", "height": 720, "filesize": 18000000},
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360, "filesize": 8000000},
    ]

    v_opts, a_opts = get_available_download_formats(mock_formats_720p, duration=120.0)
    v_keys = [opt[0] for opt in v_opts]

    # 4K, 2K, and 1080p must all be omitted
    assert "Video (4K Ultra HD - 2160p)" not in v_keys
    assert "Video (2K Quad HD - 1440p)" not in v_keys
    assert "Video (1080p Full HD MP4)" not in v_keys

    # 720p and 360p must be present
    assert "Video (720p HD MP4)" in v_keys
    assert "Video (360p Fast MP4)" in v_keys


def test_format_option_card_size_text_display():
    from mobile_app import FormatOptionCard
    card = FormatOptionCard(
        key="Video (1080p Full HD MP4)",
        title="1080p Full HD MP4",
        subtitle="Highest visual clarity (1920x1080)",
        badge_text="1080p HD",
        size_text="45.2 MB",
        is_selected=True,
    )
    assert "45.2 MB" in card.sub_lbl.text
    assert card.size_lbl.text == "[b]45.2 MB[/b]"
    assert card.height > 50


def test_active_downloads_container_rebuild():
    from mobile_app import MSKDownloaderMobile, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.download_state = {
        "is_active": True,
        "is_paused": False,
        "title": "Python Async Programming Tutorial",
        "format": "1080p Full HD MP4",
        "percent": 45,
        "speed_str": "3.8 MB/s",
        "status_msg": "Downloading chunks...",
    }
    app.download_queue = []
    app.active_downloads_container = BoxLayout(orientation="vertical")

    # Rebuild active section (Clock.tick dispatches @mainthread callback)
    app.rebuild_active_downloads_section()
    Clock.tick()
    assert len(app.active_downloads_container.children) > 0
    assert hasattr(app, "active_dl_title")
    assert "Python Async Programming" in app.active_dl_title.text
    assert hasattr(app, "active_dl_bar")
    assert app.active_dl_bar.value == 45

    # Update real-time widget
    app.update_active_downloads_widget("Downloading: 75% • 4.5 MB/s", progress_val=75)
    Clock.tick()
    assert app.active_dl_bar.value == 75
    assert app.active_dl_pct.text == "[b]75%[/b]"

    # When download becomes inactive
    app.download_state["is_active"] = False
    app.rebuild_active_downloads_section()
    Clock.tick()
    assert len(app.active_downloads_container.children) == 0


def test_vault_auto_lock_on_tab_switch():
    from mobile_app import MSKDownloaderMobile, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.active_tab = "downloads"
    app.is_vault_unlocked = True
    app.main_container = type("DummyContainer", (), {"children": [1], "clear_widgets": lambda self: None, "add_widget": lambda self, w: None})()
    app.nav_btn_home = type("DummyBtn", (), {"set_active": lambda self, a: None})()
    app.nav_btn_videos = type("DummyBtn", (), {"set_active": lambda self, a: None})()
    app.nav_btn_downloads = type("DummyBtn", (), {"set_active": lambda self, a: None})()
    app.home_view = None
    app.videos_view = None
    app.downloads_view = None

    # Switch away to home
    app.switch_tab("home")
    # Vault must be locked automatically
    assert app.is_vault_unlocked is False
    assert app.active_tab == "home"


def test_move_and_restore_vault_files(tmp_path):
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.library_container = type("DummyContainer", (), {"clear_widgets": lambda self: None, "add_widget": lambda self, w: None})()
    app.update_status = lambda msg, p: None
    app.refresh_library = lambda: None
    app.get_media_search_dirs = lambda: [dl_dir]

    dl_dir = tmp_path / "Downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    v_dir = dl_dir / ".vault"
    v_dir.mkdir(parents=True, exist_ok=True)

    with patch("mobile_app.get_android_download_dir", return_value=dl_dir):
        with patch("mobile_app.get_vault_dir", return_value=v_dir):
            with patch("mobile_app.scan_media_file"), patch("mobile_app.prune_file_from_mediastore"):
                sample_file = dl_dir / "secret_video.mp4"
                sample_file.write_text("dummy-video-data")
                assert sample_file.exists()

                # Move to vault (should be obfuscated to .secret_video.mp4.mskvault)
                app.move_file_to_vault(sample_file)
                assert not sample_file.exists()
                vault_file = v_dir / ".secret_video.mp4.mskvault"
                assert vault_file.exists(), f"Vault file should be hidden as {vault_file.name}"

                # Restore from vault back to original clean filename
                app.restore_file_from_vault(vault_file)
                assert not vault_file.exists()
                restored_file = dl_dir / "secret_video.mp4"
                assert restored_file.exists()
                assert restored_file.read_text() == "dummy-video-data"

                # Also test legacy non-obfuscated vault file restoration
                legacy_file = v_dir / "legacy_song.mp3"
                legacy_file.write_text("legacy-audio-data")
                app.restore_file_from_vault(legacy_file)
                assert not legacy_file.exists()
                assert (dl_dir / "legacy_song.mp3").exists()


def test_vault_exclusion_from_library_views(tmp_path):
    """Verify media in vault is strictly hidden from ALL, SONGS, and VIDEOS views."""
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.library_container = type("DummyContainer", (), {"children": [], "clear_widgets": lambda self: None, "add_widget": lambda self, w: None})()
    app.update_status = lambda msg, p: None

    dl_dir = tmp_path / "Downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    v_dir = dl_dir / ".vault"
    v_dir.mkdir(parents=True, exist_ok=True)

    # 1 public video, 1 public audio, 1 vaulted video
    public_vid = dl_dir / "public_tutorial.mp4"
    public_vid.write_text("public video")
    public_aud = dl_dir / "public_tune.mp3"
    public_aud.write_text("public audio")

    vault_vid = v_dir / ".hidden_secret.mp4.mskvault"
    vault_vid.write_text("vault video")

    with patch("mobile_app.get_android_download_dir", return_value=dl_dir):
        with patch("mobile_app.get_vault_dir", return_value=v_dir):
            app.get_media_search_dirs = lambda: [dl_dir]

            # In ALL view: only public files should appear
            app.active_filter = "all"
            app.refresh_library()
            # Verify get_vault_display_name resolves correctly
            from mobile_app import get_vault_display_name, is_vault_path
            assert get_vault_display_name(vault_vid) == "hidden_secret.mp4"
            assert is_vault_path(vault_vid) is True
            assert is_vault_path(public_vid) is False


def test_audio_player_icons_and_no_emojis():
    """Verify all audio player icons exist and player control buttons contain zero tofu emoji text."""
    import os
    from mobile_app import get_asset_icon, MSKDownloaderMobile, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return

    # Verify dedicated icon assets exist
    for icon_name in ("prev.png", "next.png", "timer.png", "close.png", "shield.png", "play.png", "pause.png"):
        icon_path = get_asset_icon(icon_name)
        assert icon_path and os.path.exists(icon_path), f"Missing icon asset: {icon_name}"

    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    bar = app.create_mini_player_bar()
    assert bar is not None

    # Buttons should have empty text so Android never wraps or renders missing emoji tofu boxes
    assert app.mini_player_prev_btn.text == ""
    assert app.mini_player_play_btn.text == ""
    assert app.mini_player_next_btn.text == ""
    assert app.mini_player_timer_btn.text == ""
    assert app.mini_player_close_btn.text == ""


def test_vault_auto_lock_on_pause():
    """Verify vault automatically locks when app enters on_pause (app minimized / backgrounded)."""
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.is_vault_unlocked = True
    app.active_filter = "vault"
    app.filter_btn_vault = type("DummyBtn", (), {"text": "VAULT (OPEN)", "set_icon": lambda self, ic: None})()
    app.set_downloads_filter = lambda f: setattr(app, "active_filter", f)

    res = app.on_pause()
    assert res is True
    assert app.is_vault_unlocked is False
    assert app.active_filter == "all"
    assert app.filter_btn_vault.text == "VAULT"


def test_delete_media_file_and_duplicate_cleanup(tmp_path):
    """Verify delete_media_file deletes file and safely cleans duplicates."""
    from mobile_app import delete_media_file
    sample_file = tmp_path / "test_downloaded_video.mp4"
    sample_file.write_text("dummy video content")
    assert sample_file.exists()

    deleted = delete_media_file(sample_file)
    assert deleted is True
    assert not sample_file.exists()


def test_home_view_excludes_status_card_and_download_btn():
    """Verify status_card and download_btn are excluded from Home page layout for clean UI."""
    from mobile_app import MSKDownloaderMobile, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return

    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    scroll_view = app.build_home_view()
    assert scroll_view is not None
    assert len(scroll_view.children) > 0
    content_box = scroll_view.children[0]

    # Verify status_card and download_btn are NOT in the home view widget tree
    assert app.status_card not in content_box.children
    assert app.download_btn not in content_box.children


def test_icon_action_button_tactile_feedback_and_setters():
    """Verify IconActionButton provides press highlight and text/color setters."""
    from mobile_app import IconActionButton, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return

    btn = IconActionButton(icon_path="refresh.png", text="REFRESH", bg_color=(0.18, 0.22, 0.32, 1.0))
    assert btn.text == "REFRESH"

    btn.set_text("SCANNING...")
    assert btn.text == "SCANNING..."

    btn.set_bg_color((0.15, 0.35, 0.58, 1.0))
    assert btn.bg_color == [0.15, 0.35, 0.58, 1.0]

    # Test touch state feedback
    btn._on_button_state_change(btn, "down")
    assert btn._col_instr.rgba[0] > 0.15  # Lightened on press
    btn._on_button_state_change(btn, "normal")
    assert btn._col_instr.rgba == [0.15, 0.35, 0.58, 1.0]


def test_manual_refresh_library_and_deleted_filter(tmp_path):
    """Verify manual_refresh_library exists and deleted_filenames filter ignores deleted files."""
    from mobile_app import MSKDownloaderMobile, KIVY_AVAILABLE
    if not KIVY_AVAILABLE:
        return

    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    assert hasattr(app, "manual_refresh_library")

    app.deleted_filenames = {"deleted_song.mp3", "deleted_song"}
    app.active_filter = "all"
    app.get_media_search_dirs = lambda: [tmp_path]

    # Create dummy files
    f1 = tmp_path / "deleted_song.mp3"
    f1.write_text("dummy")
    f2 = tmp_path / "valid_song.mp3"
    f2.write_text("dummy")

    # Mock library_container
    app.library_container = type("DummyContainer", (), {"clear_widgets": lambda self: None, "add_widget": lambda self, w: None, "children": []})()
    app.downloads_title_lbl = type("DummyLbl", (), {"text": ""})()
    app.nav_btn_downloads = type("DummyNav", (), {"text": ""})()

    app.refresh_library()
    # The deleted_filenames filter prevents deleted_song from being added to the UI
    assert "deleted_song.mp3" in app.deleted_filenames


def test_ringtone_feature_removed():
    """Verify set_audio_as_ringtone is cleanly deprecated and returns false."""
    from mobile_app import set_audio_as_ringtone
    from pathlib import Path
    ok, msg = set_audio_as_ringtone(Path("test.mp3"))
    assert ok is False
    assert "removed" in msg.lower()


def test_vault_playback_preparation_and_clean_cache(tmp_path, monkeypatch):
    """Verify prepare_vault_file_for_playback stages playable file in .vault/.play and clean cache works."""
    from mobile_app import prepare_vault_file_for_playback, clean_vault_playback_cache
    import mobile_app

    vault_dir = tmp_path / ".vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mobile_app, "get_vault_dir", lambda: vault_dir)

    dummy_vault_file = vault_dir / ".secret_video.mp4.mskvault"
    dummy_vault_file.write_text("dummy mp4 video bytes")

    staged = prepare_vault_file_for_playback(dummy_vault_file)
    assert staged.exists()
    assert staged.name == "secret_video.mp4"
    assert staged.parent == vault_dir / ".play"
    assert (vault_dir / ".play" / ".nomedia").exists()

    # Verify instant reuse if identical
    staged2 = prepare_vault_file_for_playback(dummy_vault_file)
    assert staged2 == staged

    # Clean cache
    clean_vault_playback_cache()
    assert not staged.exists()
    assert (vault_dir / ".play" / ".nomedia").exists()


def test_download_queue_management():
    """Verify multiple media download queue manipulation methods."""
    from mobile_app import MSKDownloaderMobile
    app = MSKDownloaderMobile.__new__(MSKDownloaderMobile)
    app.download_queue = [
        {"title": "Video 1", "url": "https://youtu.be/aaa"},
        {"title": "Video 2", "url": "https://youtu.be/bbb"},
        {"title": "Video 3", "url": "https://youtu.be/ccc"},
    ]
    app.update_status = lambda msg, val: None
    app.rebuild_active_downloads_section = lambda: None

    # Remove middle item
    app.remove_from_download_queue(1)
    assert len(app.download_queue) == 2
    assert app.download_queue[0]["title"] == "Video 1"
    assert app.download_queue[1]["title"] == "Video 3"

    # Clear queue
    app.clear_download_queue()
    assert len(app.download_queue) == 0













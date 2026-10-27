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






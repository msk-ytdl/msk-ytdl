"""Unit tests for mobile_app utility functions and download helpers."""

from mobile_app import (
    sanitize_storage_filename,
    get_canonical_video_url,
    normalize_youtube_url,
    safe_display_text,
)


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

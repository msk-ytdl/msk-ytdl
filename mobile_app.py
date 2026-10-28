"""
Mobile graphical interface entry point for MSK YTDL on Android.
Publisher: MSK Software Solutions
Designed for touchscreen navigation, phone storage permissions, background downloading,
modern dark aesthetics, real-time video previews, offline library manager,
HQ MP3 album art & ID3 embedding, smart clipboard auto-detection, playlist support,
bottom footer navigation bar (Home, Downloads, Videos), and direct integration
with Android's "Share from YouTube" SEND Intent.
"""

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

# Safe standard stream wrapper to protect against Android Logcat / Kivy buffer crashes
class SafeLogStream:
    def __init__(self, original_stream):
        self._orig = original_stream

    def write(self, msg):
        if not msg:
            return
        try:
            if self._orig and hasattr(self._orig, "write") and not isinstance(self._orig, str):
                self._orig.write(str(msg))
            else:
                print(str(msg).rstrip())
        except Exception:
            pass

    def flush(self):
        try:
            if self._orig and hasattr(self._orig, "flush"):
                self._orig.flush()
        except Exception:
            pass

    @property
    def buffer(self):
        return self


# Wrap sys.stdout and sys.stderr if missing .write or if .buffer is a string
if not hasattr(sys.stdout, "write") or isinstance(getattr(sys.stdout, "buffer", None), str):
    sys.stdout = SafeLogStream(sys.stdout)
if not hasattr(sys.stderr, "write") or isinstance(getattr(sys.stderr, "buffer", None), str):
    sys.stderr = SafeLogStream(sys.stderr)

# Guarantee SSL certificates are loaded on Android environments
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

try:
    from kivy.app import App
    from kivy.clock import Clock, mainthread
    from kivy.core.audio import SoundLoader
    from kivy.core.clipboard import Clipboard
    from kivy.core.text import LabelBase
    from kivy.core.window import Window
    from kivy.graphics import Color, RoundedRectangle
    from kivy.metrics import dp
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import AsyncImage, Image
    from kivy.uix.label import Label
    from kivy.uix.modalview import ModalView
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False


class DownloadCancelledException(Exception):
    """Raised when user cancels an active download via UI."""
    pass


class AndroidYTDLLogger:
    """Safe custom logger for yt-dlp that routes messages without calling standard error streams."""
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg, only_once=False):
        pass

    def error(self, msg):
        try:
            print(f"[MSK-YTDL Log] {msg}")
        except Exception:
            pass


def detect_media_platform(url: str) -> str:
    """Identify target social media or video platform from URL."""
    if not url or not isinstance(url, str):
        return "Unknown"
    low = url.lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "YouTube"
    if "instagram.com" in low or "instagr.am" in low:
        return "Instagram"
    if "facebook.com" in low or "fb.watch" in low or "fb.com" in low:
        return "Facebook"
    if "tiktok.com" in low:
        return "TikTok"
    if "twitter.com" in low or "x.com" in low or "t.co" in low:
        return "Twitter / X"
    if "pinterest.com" in low or "pin.it" in low:
        return "Pinterest"
    if "reddit.com" in low or "redd.it" in low:
        return "Reddit"
    if low.startswith("http://") or low.startswith("https://"):
        return "Web Media"
    return "Unknown"


def normalize_media_url(text: str) -> Optional[str]:
    """
    Robustly extract and canonicalize media links across multiple platforms:
    YouTube, Instagram (Reels & Posts), Facebook, TikTok, Twitter/X, and web video links.
    """
    if not text:
        return None
    raw = text.strip()

    # 1. Direct YouTube playlist URL: youtube.com/playlist?list=...
    match_plist = re.search(
        r"https?://(?:www\.|m\.)?youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)",
        raw,
    )
    if match_plist:
        return f"https://www.youtube.com/playlist?list={match_plist.group(1)}"

    # 2. Check for playlist parameter (list=PL...) inside watch or youtu.be URL
    match_list_param = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", raw)
    plist_id = match_list_param.group(1) if match_list_param else None

    # 3. Full YouTube watch, youtu.be, shorts, live, or embed URL with video ID
    match_yt = re.search(
        r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})|youtu\.be/([a-zA-Z0-9_-]{11})|youtube\.com/shorts/([a-zA-Z0-9_-]{11})|youtube\.com/live/([a-zA-Z0-9_-]{11})|youtube\.com/embed/([a-zA-Z0-9_-]{11}))",
        raw,
    )
    if match_yt:
        vid = (
            match_yt.group(1)
            or match_yt.group(2)
            or match_yt.group(3)
            or match_yt.group(4)
            or match_yt.group(5)
        )
        if plist_id and not plist_id.startswith("RD") and not plist_id.startswith("TL"):
            return f"https://www.youtube.com/playlist?list={plist_id}"
        return f"https://www.youtube.com/watch?v={vid}"

    # 4. Standalone playlist query: 'list=PL...'
    if plist_id and not plist_id.startswith("RD"):
        return f"https://www.youtube.com/playlist?list={plist_id}"

    # 5. Query fragment: 'v=UQyh7QIVaDU' or 'watch?v=UQyh7QIVaDU'
    match_query = re.search(r"(?:watch\?)?v=([a-zA-Z0-9_-]{11})", raw)
    if match_query:
        return f"https://www.youtube.com/watch?v={match_query.group(1)}"

    # 6. Raw 11-character YouTube video ID alone (e.g. 'UQyh7QIVaDU')
    match_raw_id = re.match(r"^[a-zA-Z0-9_-]{11}$", raw)
    if match_raw_id:
        return f"https://www.youtube.com/watch?v={raw}"

    # 7. Instagram Reels & Posts
    match_ig = re.search(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/([a-zA-Z0-9_-]+)", raw)
    if match_ig:
        sub_type = "reel" if "/reel" in raw else ("p" if "/p/" in raw else "tv")
        return f"https://www.instagram.com/{sub_type}/{match_ig.group(1)}/"

    # 8. TikTok (Video & VM/VT shortlinks)
    match_tt = re.search(r"https?://(?:(?:www|vm|vt)\.)?tiktok\.com/(?:@[a-zA-Z0-9_.-]+/video/(\d+)|([a-zA-Z0-9_-]+))", raw)
    if match_tt:
        m_full = re.search(r"(https?://[^\s]+)", raw)
        return m_full.group(1).split("?")[0] if m_full else raw

    # 9. Facebook Videos & Reels (including fb.watch)
    match_fb = re.search(r"https?://(?:www\.|m\.)?(?:facebook\.com|fb\.watch)/[^\s]+", raw)
    if match_fb:
        clean_fb = match_fb.group(0)
        return clean_fb if "watch" in clean_fb else clean_fb.split("?")[0]

    # 10. Twitter / X Posts & Videos
    match_tw = re.search(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/(\d+)", raw)
    if match_tw:
        return f"https://x.com/i/status/{match_tw.group(1)}"

    # 11. General web link fallback
    match_gen = re.search(r"(https?://[^\s]+)", raw)
    if match_gen:
        return match_gen.group(1)

    return None


def normalize_youtube_url(text: str) -> Optional[str]:
    """Compatibility alias for normalize_media_url."""
    return normalize_media_url(text)


def extract_youtube_url(text: str) -> Optional[str]:
    """Compatibility alias for normalize_media_url."""
    return normalize_media_url(text)


def sanitize_storage_filename(title: Optional[str], default_name: str = "MSK_Video") -> str:
    """Sanitize title for filesystem: strip forbidden chars and preserve full readable name up to 215 chars."""
    if not title:
        return default_name
    clean = safe_display_text(title)
    # Strip forbidden filesystem chars
    clean = re.sub(r'[\\/*?:"<>|#%&{}\\<>*?/$!\'":@]', "", clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean or clean.lower() == "videoplayback":
        clean = default_name
    return clean[:215].strip()



def get_canonical_video_url(item: Dict[str, Any], fallback_url: str = "") -> str:
    """
    Ensure yt-dlp receives a canonical watch URL for YouTube or original clean URL for other platforms.
    """
    # 1. If valid 11-char YouTube ID is present, format canonical YouTube watch URL
    vid_id = item.get("id")
    if vid_id and len(str(vid_id)) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", str(vid_id)):
        return f"https://www.youtube.com/watch?v={vid_id}"

    # 2. Extract ID from webpage_url, url, or fallback_url
    for cand in (item.get("webpage_url"), item.get("url"), fallback_url):
        if cand and isinstance(cand, str):
            m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})", cand)
            if m:
                return f"https://www.youtube.com/watch?v={m.group(1)}"

    # 3. For non-YouTube platforms, return original webpage_url or clean url
    target_plat = detect_media_platform(fallback_url or item.get("webpage_url", "") or item.get("url", ""))
    if target_plat != "YouTube":
        return item.get("webpage_url") or item.get("url") or fallback_url

    # 4. If it's a playlist URL or non-CDN URL, return it directly
    for cand in (fallback_url, item.get("webpage_url"), item.get("url")):
        if cand and isinstance(cand, str) and "googlevideo.com" not in cand and "videoplayback" not in cand:
            return cand

    return fallback_url




def safe_display_text(text: Optional[str]) -> str:
    """
    Sanitize text to render cleanly on Android Kivy without missing-glyph tofu square boxes [].
    Strips raw emojis and unrenderable control characters while preserving readable text.
    """
    if not text:
        return ""
    raw = str(text)
    # Strip supplementary plane emojis (Surrogate pairs)
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', raw)
    # Strip miscellaneous symbols & emojis
    cleaned = re.sub(r'[\u2600-\u27bf\u2b50-\u2b55\u2300-\u23ff\u2190-\u21ff\u2900-\u297f\u25a0-\u25ff]', '', cleaned)
    # Collapse multiple spaces
    return re.sub(r'\s+', ' ', cleaned).strip()


def format_bytes(num_bytes: Optional[float]) -> str:
    """Format speed / byte count to human-readable string."""
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS."""
    if not seconds or seconds <= 0:
        return "Video"
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes}:{rem_secs:02d}"


def get_asset_icon(icon_name: str) -> str:
    """Safely locate icon PNG in assets/icons, assets, or workspace directories."""
    if not icon_name:
        return ""
    clean_name = os.path.basename(icon_name)
    candidates = [
        Path(__file__).resolve().parent / "assets" / "icons" / clean_name,
        Path("assets/icons") / clean_name,
        Path(__file__).resolve().parent / "assets" / clean_name,
        Path("assets") / clean_name,
        Path(__file__).resolve().parent / clean_name,
        Path(clean_name),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])


def get_app_version() -> str:
    """Dynamically retrieve version from Android PackageManager or fallback."""
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity:
            package_info = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0)
            if package_info and package_info.versionName:
                return str(package_info.versionName)
    except Exception:
        pass
    try:
        import youtube_downloader
        return getattr(youtube_downloader, "__version__", "1.0.1")
    except Exception:
        return "1.0.1"


def is_version_newer(current_version: str, remote_version: str) -> bool:
    """Compare semver-like strings and return True if remote_version is strictly newer."""
    if not remote_version:
        return False
    if not current_version:
        return True

    rem_clean = remote_version.lstrip("vV").strip()
    curr_clean = current_version.lstrip("vV").strip()

    rem_nums = [int(x) for x in re.findall(r"\d+", rem_clean)]
    curr_nums = [int(x) for x in re.findall(r"\d+", curr_clean)]

    if not rem_nums:
        return False
    if not curr_nums:
        return True

    for r, c in zip(rem_nums, curr_nums):
        if r > c:
            return True
        elif r < c:
            return False

    if len(rem_nums) > len(curr_nums) and rem_nums[:len(curr_nums)] == curr_nums:
        return any(x > 0 for x in rem_nums[len(curr_nums):])

    return False


def install_apk_file(apk_path: Union[str, Path]) -> bool:
    """Prompt the Android Package Installer or OS to install a downloaded APK file."""
    if not apk_path:
        return False
    apk_path = Path(apk_path)
    if not str(apk_path).strip() or not apk_path.is_file():
        return False
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        Build = autoclass("android.os.Build")

        activity = PythonActivity.mActivity
        file_obj = File(str(apk_path.resolve()))
        intent = Intent(Intent.ACTION_VIEW)

        if Build.VERSION.SDK_INT >= 24:
            try:
                FileProvider = autoclass("androidx.core.content.FileProvider")
                package_name = activity.getPackageName()
                uri = FileProvider.getUriForFile(activity, f"{package_name}.fileprovider", file_obj)
                intent.setDataAndType(uri, "application/vnd.android.package-archive")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            except Exception:
                uri = Uri.fromFile(file_obj)
                intent.setDataAndType(uri, "application/vnd.android.package-archive")
        else:
            uri = Uri.fromFile(file_obj)
            intent.setDataAndType(uri, "application/vnd.android.package-archive")

        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(intent)
        return True
    except Exception as e:
        print(f"[AutoUpdate] Native install intent notice: {e}")
        try:
            open_media_file(apk_path)
            return True
        except Exception:
            return False


def request_android_permissions():
    """Request runtime storage & notification permissions on Android (API 21 through 35)."""
    try:
        from android.permissions import Permission, request_permissions
        perms = [
            Permission.INTERNET,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE,
        ]
        # On Android 13+ (API 33+), granular media & notification permissions apply
        for p in ("READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "READ_MEDIA_IMAGES", "POST_NOTIFICATIONS", "WAKE_LOCK"):
            if hasattr(Permission, p):
                perms.append(getattr(Permission, p))
        request_permissions(perms)
    except Exception as e:
        print(f"[Android] Permission request notice: {e}")


def is_running_on_android() -> bool:
    """Detect if running inside an Android runtime environment."""
    try:
        from kivy.utils import platform
        if platform == "android":
            return True
    except Exception:
        pass
    return (
        "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_ROOT" in os.environ
        or "ANDROID_BOOTLOGO" in os.environ
        or Path("/system/build.prop").exists()
    )


def get_android_download_dir() -> Path:
    """
    Resolve public writable destination directory on Android.
    Prefers public Downloads/Movies folders so downloaded files are immediately visible
    in the phone Gallery, Google Photos, Files, and third-party media players.
    Falls back to app-specific external storage if public directory is blocked.
    """
    if not is_running_on_android():
        desktop_dir = Path.home() / "Downloads" / "YouTube"
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            return desktop_dir
        except Exception:
            return Path.home() / "Downloads"

    candidates = []

    # 1. Primary on Android: Public standard Download directory via Environment
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        pub_dl = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if pub_dl:
            candidates.append(Path(pub_dl.getAbsolutePath()))
    except Exception:
        pass

    # 2. Standard public Android paths (guaranteed gallery indexing)
    candidates.extend([
        Path("/storage/emulated/0/Download"),
        Path("/sdcard/Download"),
        Path("/storage/emulated/0/Download/YouTube"),
        Path("/sdcard/Download/YouTube"),
        Path("/storage/emulated/0/Movies"),
        Path("/sdcard/Movies"),
    ])

    # 3. Public Movies directory via Environment
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        pub_mov = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES)
        if pub_mov:
            candidates.append(Path(pub_mov.getAbsolutePath()))
    except Exception:
        pass

    # 4. Fallback: App's private external files directory if public storage is permission-blocked
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Environment = autoclass("android.os.Environment")
        context = PythonActivity.mActivity
        if context:
            ext_dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            if ext_dir:
                candidates.append(Path(ext_dir.getAbsolutePath()))
    except Exception:
        pass

    # 5. App user_data_dir fallback
    try:
        if KIVY_AVAILABLE:
            from kivy.app import App
            running = App.get_running_app()
            if running and getattr(running, "user_data_dir", None):
                candidates.append(Path(running.user_data_dir) / "Downloads")
    except Exception:
        pass

    candidates.append(Path.home() / "Downloads")

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / f".msk_test_{os.getpid()}"
            test_file.write_text("ok")
            test_file.unlink(missing_ok=True)
            return path
        except Exception:
            continue

    return Path.home()


def sync_and_migrate_legacy_downloads():
    """
    Migrate media files previously downloaded to the app-private directory
    (/Android/data/.../files/Download) to the public Downloads folder so they
    immediately appear in the phone Gallery and system media players.
    """
    if not is_running_on_android():
        return
    try:
        from jnius import autoclass
        import shutil
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Environment = autoclass("android.os.Environment")
        context = PythonActivity.mActivity
        if not context:
            return
        ext_dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
        if not ext_dir:
            return
        private_path = Path(ext_dir.getAbsolutePath())
        if not private_path.exists():
            return

        target_dir = get_android_download_dir()
        if not target_dir or target_dir == private_path:
            return

        media_exts = ("*.mp4", "*.m4a", "*.mp3", "*.mkv", "*.webm", "*.wav", "*.ogg", "*.opus", "*.flac")
        for ext in media_exts:
            for f in private_path.glob(ext):
                if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl"):
                    target_file = target_dir / f.name
                    try:
                        if not target_file.exists():
                            shutil.copy2(str(f), str(target_file))
                            f.unlink(missing_ok=True)
                            print(f"[StorageMigration] Migrated {f.name} to public storage: {target_file}")
                        scan_media_file(target_file)
                    except Exception as me:
                        print(f"[StorageMigration] Migration notice for {f.name}: {me}")
    except Exception as e:
        print(f"[StorageMigration] Migration error: {e}")


def scan_media_file(filepath: Path):
    """Notify Android's MediaScanner and MediaStore so the file immediately appears in phone Gallery/Music apps."""
    if not filepath or not filepath.exists():
        return
    try:
        if is_running_on_android():
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            MediaScannerConnection = autoclass("android.media.MediaScannerConnection")
            ctx = PythonActivity.mActivity
            if ctx:
                path_str = str(filepath.resolve())
                ext = filepath.suffix.lower()

                # Determine accurate MIME type for Android Gallery / Music index
                mime = None
                if ext in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".3gp"):
                    mime = "video/mp4" if ext == ".mp4" else f"video/{ext.lstrip('.')}"
                elif ext in (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"):
                    mime = "audio/mpeg" if ext == ".mp3" else f"audio/{ext.lstrip('.')}"

                # 1. MediaScannerConnection scanFile
                try:
                    MediaScannerConnection.scanFile(
                        ctx,
                        [path_str],
                        [mime] if mime else None,
                        None
                    )
                    print(f"[Android] MediaScannerConnection synced: {filepath.name} ({mime})")
                except Exception as se:
                    print(f"[Android] MediaScannerConnection notice: {se}")

                # 2. Broadcast ACTION_MEDIA_SCANNER_SCAN_FILE (Supported on all Android versions and OEM ROMs)
                try:
                    Intent = autoclass("android.content.Intent")
                    Uri = autoclass("android.net.Uri")
                    File = autoclass("java.io.File")
                    scan_intent = Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
                    scan_intent.setData(Uri.fromFile(File(path_str)))
                    ctx.sendBroadcast(scan_intent)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Android] MediaScanner notice: {e}")


def mux_video_audio_android(video_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Natively merge separate video (H.264/MP4) and audio (AAC/M4A) streams into a single MP4
    container using Android's native android.media.MediaMuxer & MediaExtractor APIs via PyJnius.
    Ensures chronological presentation timestamp (PTS) interleaving across tracks as strictly
    mandated by Android MediaMuxer. Falls back to system FFmpeg if available on non-Android platforms.
    """
    if not video_path.exists() or not audio_path.exists():
        print(f"[MediaMuxer] Input file missing: v={video_path.exists()}, a={audio_path.exists()}")
        return False

    # Attempt native Android MediaMuxer via PyJnius
    if is_running_on_android():
        v_fis = None
        a_fis = None
        fos = None
        muxer = None
        v_extractor = None
        a_extractor = None
        try:
            from jnius import autoclass
            MediaExtractor = autoclass("android.media.MediaExtractor")
            MediaMuxer = autoclass("android.media.MediaMuxer")
            MediaCodec_BufferInfo = autoclass("android.media.MediaCodec$BufferInfo")
            ByteBuffer = autoclass("java.nio.ByteBuffer")
            FileInputStream = autoclass("java.io.FileInputStream")
            FileOutputStream = autoclass("java.io.FileOutputStream")
            File = autoclass("java.io.File")

            # 1. Open video extractor via FileDescriptor (bypasses Scoped Storage / Stagefright path limits)
            v_file = File(str(video_path.resolve()))
            v_fis = FileInputStream(v_file)
            v_extractor = MediaExtractor()
            v_extractor.setDataSource(v_fis.getFD(), 0, v_file.length())

            # 2. Open audio extractor via FileDescriptor
            a_file = File(str(audio_path.resolve()))
            a_fis = FileInputStream(a_file)
            a_extractor = MediaExtractor()
            a_extractor.setDataSource(a_fis.getFD(), 0, a_file.length())

            tmp_output = output_path
            if tmp_output.resolve() in (video_path.resolve(), audio_path.resolve()):
                tmp_output = output_path.with_name(f"merged_{output_path.name}")

            out_file = File(str(tmp_output.resolve()))
            if out_file.exists():
                out_file.delete()
            fos = FileOutputStream(out_file)

            try:
                muxer = MediaMuxer(fos.getFD(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            except Exception:
                muxer = MediaMuxer(str(tmp_output.resolve()), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)

            # 3. Select and add Video Track
            video_track_idx = -1
            for i in range(v_extractor.getTrackCount()):
                format_obj = v_extractor.getTrackFormat(i)
                mime = None
                try:
                    mime = format_obj.getString("mime")
                except Exception:
                    pass
                if mime and mime.startswith("video/"):
                    v_extractor.selectTrack(i)
                    video_track_idx = muxer.addTrack(format_obj)
                    break

            # 4. Select and add Audio Track
            audio_track_idx = -1
            for i in range(a_extractor.getTrackCount()):
                format_obj = a_extractor.getTrackFormat(i)
                mime = None
                try:
                    mime = format_obj.getString("mime")
                except Exception:
                    pass
                if mime and mime.startswith("audio/"):
                    a_extractor.selectTrack(i)
                    audio_track_idx = muxer.addTrack(format_obj)
                    break

            if video_track_idx < 0 or audio_track_idx < 0:
                print(f"[MediaMuxer] Track error: video={video_track_idx}, audio={audio_track_idx}")
                return False

            muxer.start()

            # 5. Allocate 4MB direct ByteBuffer for high-bitrate keyframes
            buf_size = 4 * 1024 * 1024
            buf = ByteBuffer.allocateDirect(buf_size)
            buffer_info = MediaCodec_BufferInfo()

            # 6. Interleaved sample writing across tracks by presentation timestamp (PTS)
            while True:
                v_time = v_extractor.getSampleTime()
                a_time = a_extractor.getSampleTime()

                if v_time < 0 and a_time < 0:
                    break

                if v_time >= 0 and (a_time < 0 or v_time <= a_time):
                    buf.clear()
                    sample_size = v_extractor.readSampleData(buf, 0)
                    if sample_size > 0:
                        buffer_info.set(0, sample_size, v_time, v_extractor.getSampleFlags())
                        muxer.writeSampleData(video_track_idx, buf, buffer_info)
                    v_extractor.advance()
                elif a_time >= 0:
                    buf.clear()
                    sample_size = a_extractor.readSampleData(buf, 0)
                    if sample_size > 0:
                        buffer_info.set(0, sample_size, a_time, a_extractor.getSampleFlags())
                        muxer.writeSampleData(audio_track_idx, buf, buffer_info)
                    a_extractor.advance()

            try:
                muxer.stop()
            except Exception as se:
                print(f"[MediaMuxer] muxer.stop note: {se}")

            if tmp_output != output_path:
                if output_path.exists():
                    output_path.unlink()
                tmp_output.rename(output_path)

            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f"[MediaMuxer] Android native mux successful -> {output_path.name} ({output_path.stat().st_size} bytes)")
                return True
            return False
        except Exception as e:
            print(f"[MediaMuxer] Native Android muxing notice: {e}")
        finally:
            if muxer:
                try:
                    muxer.release()
                except Exception:
                    pass
            if v_extractor:
                try:
                    v_extractor.release()
                except Exception:
                    pass
            if a_extractor:
                try:
                    a_extractor.release()
                except Exception:
                    pass
            if v_fis:
                try:
                    v_fis.close()
                except Exception:
                    pass
            if a_fis:
                try:
                    a_fis.close()
                except Exception:
                    pass
            if fos:
                try:
                    fos.close()
                except Exception:
                    pass

    # Fallback: system FFmpeg if available
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            import subprocess
            cmd = [
                ffmpeg_bin, "-y",
                "-i", str(video_path.resolve()),
                "-i", str(audio_path.resolve()),
                "-c", "copy",
                "-shortest",
                str(output_path.resolve())
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if res.returncode == 0 and output_path.exists():
                print(f"[MediaMuxer] System FFmpeg mux successful -> {output_path.name}")
                return True
        except Exception as fe:
            print(f"[MediaMuxer] FFmpeg mux notice: {fe}")

    return False


def get_ydl_format_selector(selected_format: str, has_ffmpeg: bool = False) -> str:
    """
    Generate the precise yt-dlp format selector string based on user's chosen quality/audio option.
    Ensures:
      - Audio selections NEVER fall back to video streams (/best is omitted).
      - 1080p / 720p prioritizes universal H.264 (avc1) + AAC (m4a) DASH streams for flawless muxing & playback.
      - 360p selects fast lightweight progressive (18) or 360p streams.
    """
    is_audio = "Audio" in selected_format

    if is_audio:
        if "MP3" in selected_format and has_ffmpeg:
            return "bestaudio/bestaudio[ext=m4a]/140/ba"
        # Direct AAC M4A audio stream (format 140 is high-quality 128k AAC audio on YouTube)
        # CRITICAL: Do NOT append /best, as that would fallback to video format 18!
        return "140/bestaudio[ext=m4a]/bestaudio[acodec!=none]/bestaudio/ba"

    # Video options
    if "1080p" in selected_format or "Max Quality" in selected_format:
        # 1080p Full HD (Max Quality)
        return "bestvideo[height<=1080][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/bestvideo[height<=720][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/22/best[height<=1080]/18/best"
    elif "720p" in selected_format:
        # 720p HD MP4
        return "bestvideo[height<=720][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/22/best[height<=720]/18/best"
    elif "360p" in selected_format:
        # 360p Fast MP4
        return "18/bestvideo[height<=360][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best"
    else:
        # Fallback to high quality
        return "bestvideo[height<=1080][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/bestvideo[height<=720][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/22/best[height<=1080]/18/best"


class AndroidNativeAudioPlayer:
    """Wrapper around android.media.MediaPlayer for Android with background & screen-off playback support."""
    def __init__(self, source_path_or_url: str):
        self.state = "stop"
        self._mp = None
        self._source = source_path_or_url
        self._duration = 0.0
        try:
            from jnius import autoclass
            MediaPlayer = autoclass("android.media.MediaPlayer")
            AudioAttributes = autoclass("android.media.AudioAttributes")
            AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")

            self._mp = MediaPlayer()
            attrs = AudioAttributesBuilder() \
                .setUsage(AudioAttributes.USAGE_MEDIA) \
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC) \
                .build()
            self._mp.setAudioAttributes(attrs)
            self._mp.setDataSource(str(source_path_or_url))
            self._mp.prepare()
            dur = self._mp.getDuration()
            if dur and dur > 0:
                self._duration = dur / 1000.0
        except Exception as e:
            print(f"[AndroidNativeAudioPlayer] Init notice: {e}")
            if self._mp:
                try:
                    self._mp.release()
                except Exception:
                    pass
                self._mp = None

    def play(self):
        if self._mp:
            try:
                self._mp.start()
                self.state = "play"
                return True
            except Exception as e:
                print(f"[AndroidNativeAudioPlayer] Play notice: {e}")
        return False

    def stop(self):
        if self._mp:
            try:
                if self._mp.isPlaying():
                    self._mp.pause()
                self.state = "stop"
            except Exception as e:
                print(f"[AndroidNativeAudioPlayer] Stop notice: {e}")

    def unload(self):
        if self._mp:
            try:
                self._mp.stop()
                self._mp.release()
            except Exception:
                pass
            self._mp = None
            self.state = "stop"

    @property
    def is_playing(self) -> bool:
        if self._mp:
            try:
                return bool(self._mp.isPlaying())
            except Exception:
                return False
        return False

    def get_pos(self):
        if self._mp:
            try:
                pos = (self._mp.getCurrentPosition() or 0) / 1000.0
                if self.state == "play" and not self._mp.isPlaying():
                    if self._duration > 0 and pos >= (self._duration - 0.6):
                        self.state = "stop"
                return pos
            except Exception:
                return 0.0
        return 0.0

    @property
    def length(self):
        if self._mp:
            try:
                dur = self._mp.getDuration()
                if dur and dur > 0:
                    self._duration = dur / 1000.0
            except Exception:
                pass
        return self._duration


def get_media_content_uri(filepath: Path):
    """Resolve a content:// URI from Android MediaStore or FileProvider so external players can open it."""
    if not is_running_on_android() or not filepath:
        return None
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if not activity:
            return None

        path_str = str(filepath.resolve())
        ext = filepath.suffix.lower()
        is_video = ext in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".3gp")
        is_audio = ext in (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac")

        # 1. Query Android MediaStore for existing content URI
        try:
            MediaStore = autoclass("android.provider.MediaStore")
            ContentUris = autoclass("android.content.ContentUris")
            resolver = activity.getContentResolver()

            table_uri = None
            if is_video:
                table_uri = MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            elif is_audio:
                table_uri = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
            else:
                table_uri = MediaStore.Files.getContentUri("external")

            cursor = resolver.query(
                table_uri,
                ["_id"],
                "_data = ?",
                [path_str],
                None
            )
            if cursor:
                try:
                    if cursor.moveToFirst():
                        id_idx = cursor.getColumnIndexOrThrow("_id")
                        row_id = cursor.getLong(id_idx)
                        content_uri = ContentUris.withAppendedId(table_uri, row_id)
                        cursor.close()
                        return content_uri
                finally:
                    try:
                        cursor.close()
                    except Exception:
                        pass
        except Exception as me:
            print(f"[ContentURI] MediaStore query notice: {me}")

        # 2. Try FileProvider if configured
        try:
            FileProvider = autoclass("androidx.core.content.FileProvider")
            File = autoclass("java.io.File")
            pkg = activity.getPackageName()
            file_uri = FileProvider.getUriForFile(activity, f"{pkg}.fileprovider", File(path_str))
            if file_uri:
                return file_uri
        except Exception:
            pass

    except Exception as e:
        print(f"[ContentURI] Resolution notice: {e}")
    return None


def open_media_file(filepath: Path):
    """Launch downloaded video, song, or APK in default external player or installer."""
    if not filepath:
        return
    try:
        if is_running_on_android():
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            activity = PythonActivity.mActivity

            path_str = str(filepath.resolve())
            file_obj = File(path_str)
            intent = Intent(Intent.ACTION_VIEW)

            ext = filepath.suffix.lower()
            if ext in (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"):
                mime_type = "audio/*"
            elif ext in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".3gp"):
                mime_type = "video/*"
            elif ext == ".apk":
                mime_type = "application/vnd.android.package-archive"
            else:
                mime_type = "*/*"

            # 1. Resolve content:// URI from MediaStore / FileProvider
            target_uri = get_media_content_uri(filepath)

            # 2. Fallback to file:// with StrictMode bypass if content URI unavailable
            if target_uri is None:
                try:
                    StrictMode = autoclass("android.os.StrictMode")
                    builder = autoclass("android.os.StrictMode$VmPolicy$Builder")()
                    StrictMode.setVmPolicy(builder.build())
                except Exception:
                    pass
                target_uri = Uri.fromFile(file_obj)

            intent.setDataAndType(target_uri, mime_type)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)

            # Grant explicit URI permissions to resolving apps
            try:
                pm = activity.getPackageManager()
                matches = pm.queryIntentActivities(intent, 65536)
                if matches:
                    for i in range(matches.size()):
                        target_pkg = matches.get(i).activityInfo.packageName
                        activity.grantUriPermission(target_pkg, target_uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            except Exception as ge:
                print(f"[OpenMedia] Grant permission notice: {ge}")

            try:
                activity.startActivity(intent)
            except Exception:
                chooser = Intent.createChooser(intent, "Play media with...")
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                activity.startActivity(chooser)
        else:
            # Desktop fallback (Windows / macOS / Linux)
            path_str = str(filepath.resolve())
            if sys.platform == "win32":
                try:
                    os.startfile(path_str)
                except Exception:
                    import subprocess
                    subprocess.Popen(["explorer", path_str])
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path_str])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path_str])
    except Exception as e:
        print(f"[OpenMedia] Error opening file {filepath.name}: {e}")


def play_video_file(filepath: Path, title: Optional[str] = None):
    """
    Play downloaded video file smoothly.
    On Android:
      Launches a high-performance in-app hardware-accelerated VideoView Dialog with
      MediaController (play, pause, seekbar, duration), [EXTERNAL PLAYER] launcher,
      and shows live media playback notification in the notification bar.
    On Desktop:
      Launches system video player and updates media notification.
    """
    if not filepath:
        return

    clean_title = safe_display_text(title or filepath.stem)
    notif_mgr = get_notification_manager()

    if is_running_on_android():
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            @run_on_ui_thread
            def _launch_android_local_video_player():
                try:
                    PythonActivity = autoclass("org.kivy.android.PythonActivity")
                    activity = PythonActivity.mActivity
                    Dialog = autoclass("android.app.Dialog")
                    VideoView = autoclass("android.widget.VideoView")
                    MediaController = autoclass("android.widget.MediaController")
                    LinearLayout = autoclass("android.widget.LinearLayout")
                    FrameLayout = autoclass("android.widget.FrameLayout")
                    TextView = autoclass("android.widget.TextView")
                    Button = autoclass("android.widget.Button")
                    Gravity = autoclass("android.view.Gravity")
                    Color = autoclass("android.graphics.Color")
                    LayoutParams = autoclass("android.widget.LinearLayout$LayoutParams")
                    FrameLayoutParams = autoclass("android.widget.FrameLayout$LayoutParams")
                    Window = autoclass("android.view.Window")
                    WindowManagerLayoutParams = autoclass("android.view.WindowManager$LayoutParams")

                    dialog = Dialog(activity)
                    try:
                        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
                    except Exception:
                        pass

                    root = LinearLayout(activity)
                    root.setOrientation(LinearLayout.VERTICAL)
                    root.setBackgroundColor(Color.BLACK)

                    # Top bar: Title + [🌐 EXTERNAL] + [✕ CLOSE]
                    header = LinearLayout(activity)
                    header.setOrientation(LinearLayout.HORIZONTAL)
                    header.setBackgroundColor(Color.parseColor("#171D27"))
                    header.setGravity(Gravity.CENTER_VERTICAL)
                    h_params = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                    header.setLayoutParams(h_params)
                    header.setPadding(24, 14, 24, 14)

                    tv = TextView(activity)
                    disp_t = (clean_title[:32] + "...") if len(clean_title) > 34 else clean_title
                    tv.setText(f"🎬 {disp_t}")
                    tv.setTextColor(Color.parseColor("#FFD54F"))
                    tv.setTextSize(14)
                    tv_params = LayoutParams(0, LayoutParams.WRAP_CONTENT, 1.0)
                    tv.setLayoutParams(tv_params)
                    header.addView(tv)

                    # External player button
                    open_ext_btn = Button(activity)
                    open_ext_btn.setText("🌐 EXTERNAL")
                    open_ext_btn.setTextColor(Color.WHITE)
                    open_ext_btn.setTextSize(11)
                    open_ext_btn.setBackgroundColor(Color.parseColor("#1976D2"))
                    open_ext_btn.setPadding(16, 6, 16, 6)
                    ext_params = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT)
                    ext_params.setMargins(0, 0, 12, 0)
                    open_ext_btn.setLayoutParams(ext_params)

                    close_btn = Button(activity)
                    close_btn.setText("✕ CLOSE")
                    close_btn.setTextColor(Color.WHITE)
                    close_btn.setTextSize(11)
                    close_btn.setBackgroundColor(Color.parseColor("#E53935"))
                    close_btn.setPadding(16, 6, 16, 6)
                    close_btn.setLayoutParams(LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

                    header.addView(open_ext_btn)
                    header.addView(close_btn)
                    root.addView(header)

                    # Video container
                    video_frame = FrameLayout(activity)
                    f_params = LayoutParams(LayoutParams.MATCH_PARENT, 0, 1.0)
                    video_frame.setLayoutParams(f_params)

                    video_view = VideoView(activity)
                    vv_params = FrameLayoutParams(FrameLayoutParams.MATCH_PARENT, FrameLayoutParams.MATCH_PARENT)
                    vv_params.gravity = Gravity.CENTER
                    video_view.setLayoutParams(vv_params)

                    mc = MediaController(activity)
                    mc.setAnchorView(video_view)
                    video_view.setMediaController(mc)

                    path_str = str(filepath.resolve())
                    video_view.setVideoPath(path_str)
                    video_frame.addView(video_view)
                    root.addView(video_frame)

                    dialog.setContentView(root)

                    win = dialog.getWindow()
                    if win:
                        win.setLayout(
                            WindowManagerLayoutParams.MATCH_PARENT,
                            WindowManagerLayoutParams.MATCH_PARENT
                        )

                    from jnius import PythonJavaClass, java_method

                    class _VideoDialogListener(PythonJavaClass):
                        __javainterfaces__ = ["android/view/View$OnClickListener"]

                        def __init__(self, action):
                            super().__init__()
                            self.action = action

                        @java_method("(Landroid/view/View;)V")
                        def onClick(self, view):
                            if self.action == "close":
                                try:
                                    video_view.stopPlayback()
                                except Exception:
                                    pass
                                notif_mgr.hide_media_playback()
                                dialog.dismiss()
                            elif self.action == "external":
                                try:
                                    video_view.pause()
                                except Exception:
                                    pass
                                open_media_file(filepath)

                    dialog._close_listener = _VideoDialogListener("close")
                    close_btn.setOnClickListener(dialog._close_listener)

                    dialog._ext_listener = _VideoDialogListener("external")
                    open_ext_btn.setOnClickListener(dialog._ext_listener)

                    class _VideoDismissListener(PythonJavaClass):
                        __javainterfaces__ = ["android/content/DialogInterface$OnDismissListener"]

                        @java_method("(Landroid/content/DialogInterface;)V")
                        def onDismiss(self, d):
                            try:
                                video_view.stopPlayback()
                            except Exception:
                                pass
                            notif_mgr.hide_media_playback()

                    dialog._dismiss_listener = _VideoDismissListener()
                    dialog.setOnDismissListener(dialog._dismiss_listener)

                    # Show media notification in notification bar!
                    notif_mgr.show_media_playback(clean_title, is_playing=True, media_type="Video")

                    video_view.start()
                    dialog.show()

                except Exception as inner_e:
                    print(f"[LocalVideoPlayer] Inner launch error: {inner_e}")
                    open_media_file(filepath)

            _launch_android_local_video_player()
        except Exception as e:
            print(f"[LocalVideoPlayer] Error: {e}")
            open_media_file(filepath)
    else:
        # Desktop
        notif_mgr.show_media_playback(clean_title, is_playing=True, media_type="Video")
        open_media_file(filepath)


def find_downloaded_media_file(title: Optional[str] = None, item_id: Optional[str] = None) -> Optional[Path]:
    """Check if the media file has already been downloaded into the storage directory."""
    try:
        target_dir = get_android_download_dir()
        if not target_dir or not target_dir.exists():
            return None

        # 1. Match by item_id (YouTube 11-char ID or platform ID)
        if item_id and len(str(item_id)) >= 6:
            candidates = [
                p for p in target_dir.glob(f"*{item_id}*")
                if p.is_file() and not p.name.endswith(".part") and not p.name.endswith(".ytdl")
            ]
            if candidates:
                return candidates[0]

        # 2. Match by sanitized title
        if title:
            clean_title = sanitize_storage_filename(title)
            if clean_title and clean_title != "MSK_Video":
                clean_low = clean_title.lower()
                for f in target_dir.iterdir():
                    if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl"):
                        f_stem_low = f.stem.lower()
                        if clean_low in f_stem_low or f_stem_low in clean_low:
                            return f
                        # Prefix match for long titles
                        pfx = clean_low[:32].strip()
                        if len(pfx) >= 10 and pfx in f_stem_low:
                            return f
    except Exception as e:
        print(f"[FindMedia] Notice: {e}")
    return None


def open_web_url(target_url: str):
    """Open an external URL in the system browser or Android web intent."""
    if not target_url:
        return
    clean_url = str(target_url).strip()
    try:
        if is_running_on_android():
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            activity = PythonActivity.mActivity
            web_intent = Intent(Intent.ACTION_VIEW, Uri.parse(clean_url))
            web_intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(web_intent)
        else:
            import webbrowser
            webbrowser.open(clean_url)
    except Exception as e:
        print(f"[Web] Error opening url {clean_url}: {e}")


def play_online_video(video_url: str, title: str = "Video Player"):
    """
    Play online video stream inside the app without redirecting to external YouTube app.
    On Android:
      Opens a high-performance in-app Dialog with hardware-accelerated WebView rendering
      the responsive YouTube / social media player with touch controls, pause, play, seek,
      direct in-app external app launcher button, and an in-app Close button.
    On Desktop:
      Launches a dedicated in-app companion player window via pywebview (with fallback to browser).
    """
    if not video_url:
        return
    clean_url = str(video_url).strip()
    vid_id = None
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})", clean_url)
    if m:
        vid_id = m.group(1)

    clean_title = safe_display_text(title or "MSK Video Player")
    if vid_id:
        embed_url = f"https://www.youtube.com/embed/{vid_id}?autoplay=1&playsinline=1&enablejsapi=1&origin=https://www.youtube.com"
        watch_url = f"https://www.youtube.com/watch?v={vid_id}"
    else:
        embed_url = clean_url
        watch_url = clean_url

    if is_running_on_android():
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            @run_on_ui_thread
            def _launch_android_inapp_player():
                try:
                    PythonActivity = autoclass("org.kivy.android.PythonActivity")
                    activity = PythonActivity.mActivity
                    Dialog = autoclass("android.app.Dialog")
                    WebView = autoclass("android.webkit.WebView")
                    WebChromeClient = autoclass("android.webkit.WebChromeClient")
                    WebViewClient = autoclass("android.webkit.WebViewClient")
                    LinearLayout = autoclass("android.widget.LinearLayout")
                    TextView = autoclass("android.widget.TextView")
                    Button = autoclass("android.widget.Button")
                    Gravity = autoclass("android.view.Gravity")
                    Color = autoclass("android.graphics.Color")
                    LayoutParams = autoclass("android.widget.LinearLayout$LayoutParams")
                    Window = autoclass("android.view.Window")
                    WindowManagerLayoutParams = autoclass("android.view.WindowManager$LayoutParams")
                    View = autoclass("android.view.View")
                    Intent = autoclass("android.content.Intent")
                    Uri = autoclass("android.net.Uri")

                    dialog = Dialog(activity)
                    try:
                        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
                    except Exception:
                        pass

                    root = LinearLayout(activity)
                    root.setOrientation(LinearLayout.VERTICAL)
                    root.setBackgroundColor(Color.parseColor("#0F141C"))

                    # Top header bar: Title + Open External Button + Close Button
                    header = LinearLayout(activity)
                    header.setOrientation(LinearLayout.HORIZONTAL)
                    header.setBackgroundColor(Color.parseColor("#171D27"))
                    header.setGravity(Gravity.CENTER_VERTICAL)
                    h_params = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                    header.setLayoutParams(h_params)
                    header.setPadding(24, 14, 24, 14)

                    tv = TextView(activity)
                    disp_title = (clean_title[:32] + "...") if len(clean_title) > 34 else clean_title
                    tv.setText(f"▶ {disp_title}")
                    tv.setTextColor(Color.parseColor("#FFD54F"))
                    tv.setTextSize(14)
                    tv_params = LayoutParams(0, LayoutParams.WRAP_CONTENT, 1.0)
                    tv.setLayoutParams(tv_params)
                    header.addView(tv)

                    # External app button [🌐 OPEN]
                    open_app_btn = Button(activity)
                    open_app_btn.setText("🌐 OPEN")
                    open_app_btn.setTextColor(Color.WHITE)
                    open_app_btn.setTextSize(12)
                    open_app_btn.setBackgroundColor(Color.parseColor("#1976D2"))
                    open_app_btn.setPadding(16, 6, 16, 6)
                    open_params = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT)
                    open_params.setMargins(0, 0, 12, 0)
                    open_app_btn.setLayoutParams(open_params)

                    close_btn = Button(activity)
                    close_btn.setText("✕ CLOSE")
                    close_btn.setTextColor(Color.WHITE)
                    close_btn.setTextSize(12)
                    close_btn.setBackgroundColor(Color.parseColor("#E53935"))
                    close_btn.setPadding(16, 6, 16, 6)
                    btn_params = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT)
                    close_btn.setLayoutParams(btn_params)

                    webview = WebView(activity)
                    settings = webview.getSettings()
                    settings.setJavaScriptEnabled(True)
                    settings.setDomStorageEnabled(True)
                    settings.setDatabaseEnabled(True)
                    settings.setMediaPlaybackRequiresUserGesture(False)
                    settings.setSupportZoom(True)
                    settings.setBuiltInZoomControls(False)
                    settings.setAllowFileAccess(True)
                    settings.setAllowContentAccess(True)
                    # Use standard mobile Chrome User-Agent so YouTube never blocks embedded playback with wv token
                    settings.setUserAgentString("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")

                    try:
                        webview.setLayerType(View.LAYER_TYPE_HARDWARE, None)
                    except Exception:
                        pass

                    webview.setWebChromeClient(WebChromeClient())
                    webview.setWebViewClient(WebViewClient())
                    webview.setBackgroundColor(Color.BLACK)

                    from jnius import PythonJavaClass, java_method

                    class _PlayerButtonListener(PythonJavaClass):
                        __javainterfaces__ = ["android/view/View$OnClickListener"]

                        def __init__(self, action_type, d, wv, target_u):
                            super().__init__()
                            self.action_type = action_type
                            self.d = d
                            self.wv = wv
                            self.target_u = target_u

                        @java_method("(Landroid/view/View;)V")
                        def onClick(self, v):
                            if self.action_type == "close":
                                try:
                                    self.wv.loadUrl("about:blank")
                                except Exception:
                                    pass
                                get_notification_manager().hide_media_playback()
                                self.d.dismiss()
                            elif self.action_type == "open":
                                try:
                                    open_intent = Intent(Intent.ACTION_VIEW, Uri.parse(self.target_u))
                                    open_intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    activity.startActivity(open_intent)
                                except Exception as err:
                                    print(f"[Player] Open external error: {err}")

                    # Retain strong references on the dialog object to prevent GC crashes
                    dialog._close_listener = _PlayerButtonListener("close", dialog, webview, watch_url)
                    close_btn.setOnClickListener(dialog._close_listener)

                    dialog._open_listener = _PlayerButtonListener("open", dialog, webview, watch_url)
                    open_app_btn.setOnClickListener(dialog._open_listener)

                    class _OnlineDismissListener(PythonJavaClass):
                        __javainterfaces__ = ["android/content/DialogInterface$OnDismissListener"]

                        @java_method("(Landroid/content/DialogInterface;)V")
                        def onDismiss(self, d):
                            try:
                                webview.loadUrl("about:blank")
                            except Exception:
                                pass
                            get_notification_manager().hide_media_playback()

                    dialog._dismiss_listener = _OnlineDismissListener()
                    dialog.setOnDismissListener(dialog._dismiss_listener)

                    header.addView(open_app_btn)
                    header.addView(close_btn)
                    root.addView(header)

                    wv_params = LayoutParams(LayoutParams.MATCH_PARENT, 0, 1.0)
                    webview.setLayoutParams(wv_params)
                    root.addView(webview)

                    if vid_id:
                        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }}
        .video-container {{ position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }}
        iframe {{ width: 100%; height: 100%; border: none; }}
    </style>
</head>
<body>
    <div class="video-container">
        <iframe src="{embed_url}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
    </div>
</body>
</html>"""
                        webview.loadDataWithBaseURL("https://www.youtube.com", html_content, "text/html", "UTF-8", None)
                    else:
                        webview.loadUrl(embed_url)

                    dialog.setContentView(root)
                    w = dialog.getWindow()
                    if w:
                        w.setLayout(WindowManagerLayoutParams.MATCH_PARENT, WindowManagerLayoutParams.MATCH_PARENT)

                    # Show media notification in notification drawer
                    get_notification_manager().show_media_playback(clean_title, is_playing=True, media_type="Online Video")
                    dialog.show()
                except Exception as inner_e:
                    print(f"[Player] Android native dialog error: {inner_e}")
                    try:
                        open_web_url(watch_url)
                    except Exception as fb_err:
                        print(f"[Player] Android fallback error: {fb_err}")

            _launch_android_inapp_player()
            return
        except Exception as e:
            print(f"[Player] Android in-app player setup notice: {e}")

    # Desktop In-App Player (Windows / macOS / Linux)
    get_notification_manager().show_media_playback(clean_title, is_playing=True, media_type="Online Video")
    try:
        import subprocess
        safe_t = re.sub(r'["\'\\]', '', clean_title)[:55]
        target_play_url = embed_url if vid_id else clean_url
        fallback_url = watch_url
        runner_code = f"""
import sys
try:
    import webview
    html_page = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{safe_t}</title>
<style>
body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0b0e14; overflow: hidden; }}
iframe {{ width: 100%; height: 100%; border: none; }}
</style>
</head>
<body>
<iframe src="{target_play_url}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
</body>
</html>'''
    win = webview.create_window('{safe_t} - MSK Player', html=html_page, width=880, height=530, background_color='#0b0e14')
    webview.start()
except Exception:
    import webbrowser
    webbrowser.open('{fallback_url}')
"""
        subprocess.Popen([sys.executable, "-c", runner_code])
    except Exception as d_err:
        print(f"[Player] Desktop player launch notice: {d_err}")
        import webbrowser
        webbrowser.open(watch_url)


def delete_media_file(filepath: Path) -> bool:
    """
    Robustly delete a media file from Android/desktop storage.
    Bypasses Android FUSE/scoped storage permission blocks by combining:
      1. Java java.io.File(path).delete() via PyJnius
      2. Android ContentResolver / MediaStore deletion
      3. Python os.remove / filepath.unlink()
    """
    path_str = str(filepath.resolve())
    deleted = False

    # 1. Java File.delete() via PyJnius (Most reliable on Android 10-15 FUSE storage)
    if is_running_on_android():
        try:
            from jnius import autoclass
            File = autoclass("java.io.File")
            jfile = File(path_str)
            if jfile.exists():
                deleted = bool(jfile.delete())
                print(f"[DeleteMedia] PyJnius File.delete result: {deleted}")
        except Exception as je:
            print(f"[DeleteMedia] PyJnius File.delete notice: {je}")

    # 2. Python standard os.remove & unlink
    if not deleted:
        try:
            if filepath.exists():
                filepath.unlink(missing_ok=True)
                deleted = True
            elif os.path.exists(path_str):
                os.remove(path_str)
                deleted = True
        except Exception as pe:
            print(f"[DeleteMedia] Python unlink notice: {pe}")

    # 3. Android MediaStore ContentResolver deletion
    if is_running_on_android():
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            if activity:
                MediaStore = autoclass("android.provider.MediaStore")
                content_resolver = activity.getContentResolver()
                files_uri = MediaStore.Files.getContentUri("external")
                count = content_resolver.delete(files_uri, "_data = ?", [path_str])
                if count and count > 0:
                    deleted = True
                    print(f"[DeleteMedia] MediaStore deleted records: {count}")
        except Exception as me:
            print(f"[DeleteMedia] MediaStore notice: {me}")

    # 4. Fallback verification: Check if file truly no longer exists
    if not filepath.exists() and not os.path.exists(path_str):
        deleted = True

    # Sync MediaStore gallery index
    try:
        scan_media_file(filepath)
    except Exception:
        pass

    return deleted


def embed_audio_metadata(audio_path: Path, title: str, uploader: str, thumbnail_url: Optional[str] = None):
    """Embed high-resolution thumbnail and ID3/M4A metadata tags into audio files."""
    try:
        thumb_data = None
        if thumbnail_url:
            try:
                import urllib.request
                req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    thumb_data = resp.read()
            except Exception as te:
                print(f"[Thumbnail Fetch] Notice: {te}")

        ext = audio_path.suffix.lower()
        if ext == ".mp3":
            try:
                from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, error
                from mutagen.mp3 import MP3
                audio = MP3(str(audio_path), ID3=ID3)
                try:
                    audio.add_tags()
                except error:
                    pass
                clean_title = safe_display_text(title)
                clean_uploader = safe_display_text(uploader)
                if clean_title:
                    audio.tags.add(TIT2(encoding=3, text=clean_title))
                if clean_uploader:
                    audio.tags.add(TPE1(encoding=3, text=clean_uploader))
                audio.tags.add(TALB(encoding=3, text="MSK YTDL Downloads"))
                if thumb_data:
                    audio.tags.add(APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # Cover front
                        desc="Cover",
                        data=thumb_data,
                    ))
                audio.save(v2_version=3)
                print(f"[Metadata] Embedded MP3 ID3 tags & Album Art into {audio_path.name}")
            except Exception as me:
                print(f"[Metadata] MP3 tag notice: {me}")

        elif ext in (".m4a", ".mp4"):
            try:
                from mutagen.mp4 import MP4, MP4Cover
                audio = MP4(str(audio_path))
                clean_title = safe_display_text(title)
                clean_uploader = safe_display_text(uploader)
                if clean_title:
                    audio["\xa9nam"] = [clean_title]
                if clean_uploader:
                    audio["\xa9ART"] = [clean_uploader]
                audio["\xa9alb"] = ["MSK YTDL Downloads"]
                if thumb_data:
                    audio["covr"] = [MP4Cover(thumb_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()
                print(f"[Metadata] Embedded M4A tags & Album Art into {audio_path.name}")
            except Exception as me:
                print(f"[Metadata] M4A tag notice: {me}")
    except Exception as e:
        print(f"[Metadata] Embed notice: {e}")


class AndroidNotificationManager:
    """Manages ongoing/completed download notifications and media playback notifications in the Android notification drawer."""
    def __init__(self):
        self.channel_id = "msk_ytdl_downloads"
        self.media_channel_id = "msk_ytdl_playback"
        self.notification_id = 4242
        self.media_notification_id = 7878
        self.manager = None
        self.context = None
        self._init_done = False
        self._current_media_title = ""
        self._is_media_playing = False

    def _init_android(self) -> bool:
        if self._init_done:
            return True
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            self.context = PythonActivity.mActivity
            if not self.context:
                return False
            self.manager = self.context.getSystemService(Context.NOTIFICATION_SERVICE)

            # Android 8.0+ (API 26+) NotificationChannel setup
            Build_VERSION = autoclass("android.os.Build$VERSION")
            if Build_VERSION.SDK_INT >= 26:
                NotificationChannel = autoclass("android.app.NotificationChannel")

                # 1. Channel for downloads
                channel_name = autoclass("java.lang.String")("MSK YTDL Downloads")
                importance_low = 2  # IMPORTANCE_LOW for quiet ongoing updates
                dl_channel = NotificationChannel(self.channel_id, channel_name, importance_low)
                dl_channel.setDescription("Progress and status for YouTube downloads")
                self.manager.createNotificationChannel(dl_channel)

                # 2. Channel for media playback controls
                media_name = autoclass("java.lang.String")("MSK Media Playback")
                media_channel = NotificationChannel(self.media_channel_id, media_name, importance_low)
                media_channel.setDescription("Displays playback status and controls for active songs and videos")
                try:
                    media_channel.setShowBadge(False)
                except Exception:
                    pass
                self.manager.createNotificationChannel(media_channel)

            self._init_done = True
            return True
        except Exception as e:
            print(f"[Notification] Init notice: {e}")
            return False

    def show_progress(self, title: str, percent: int, speed_str: str = ""):
        try:
            if not self._init_android():
                return
            from jnius import autoclass
            NotificationBuilder = autoclass("android.app.Notification$Builder")
            builder = NotificationBuilder(self.context, self.channel_id)
            clean_title = safe_display_text(title)
            builder.setContentTitle(f"Downloading: {clean_title}")
            builder.setContentText(f"{percent}%{speed_str}")
            builder.setSmallIcon(self.context.getApplicationInfo().icon)
            builder.setProgress(100, percent, False)
            builder.setOngoing(True)
            self.manager.notify(self.notification_id, builder.build())
        except Exception as e:
            print(f"[Notification] Progress notice: {e}")

    def show_finished(self, title: str, filename: str):
        try:
            if not self._init_android():
                return
            from jnius import autoclass
            NotificationBuilder = autoclass("android.app.Notification$Builder")
            builder = NotificationBuilder(self.context, self.channel_id)
            clean_fname = safe_display_text(filename)
            builder.setContentTitle("Download Complete!")
            builder.setContentText(f"Saved: {clean_fname}")
            builder.setSmallIcon(self.context.getApplicationInfo().icon)
            builder.setProgress(0, 0, False)
            builder.setOngoing(False)
            builder.setAutoCancel(True)
            self.manager.notify(self.notification_id, builder.build())
        except Exception as e:
            print(f"[Notification] Finished notice: {e}")

    def cancel(self):
        try:
            if self._init_android() and self.manager:
                self.manager.cancel(self.notification_id)
        except Exception:
            pass

    def show_media_playback(self, title: str, is_playing: bool = True, media_type: str = "Audio"):
        """Display media playback status in the Android notification bar with return-to-app action."""
        self._current_media_title = title
        self._is_media_playing = is_playing
        try:
            if not self._init_android():
                state_str = "Playing" if is_playing else "Paused"
                print(f"[Notification] Media ({media_type}) {state_str}: {safe_display_text(title)}")
                return

            from jnius import autoclass
            NotificationBuilder = autoclass("android.app.Notification$Builder")
            Build_VERSION = autoclass("android.os.Build$VERSION")
            Intent = autoclass("android.content.Intent")
            PendingIntent = autoclass("android.app.PendingIntent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            if Build_VERSION.SDK_INT >= 26:
                builder = NotificationBuilder(self.context, self.media_channel_id)
            else:
                builder = NotificationBuilder(self.context)

            clean_title = safe_display_text(title)
            state_text = f"▶ Playing • MSK {media_type} Player" if is_playing else f"⏸ Paused • MSK {media_type} Player"

            builder.setContentTitle(clean_title)
            builder.setContentText(state_text)
            builder.setSmallIcon(self.context.getApplicationInfo().icon)
            builder.setOngoing(is_playing)
            builder.setAutoCancel(not is_playing)

            # Public lock screen visibility (1 = VISIBILITY_PUBLIC)
            try:
                builder.setVisibility(1)
            except Exception:
                pass

            # Tap notification in drawer to bring app back to the front
            try:
                app_intent = Intent(self.context, PythonActivity)
                app_intent.setAction(Intent.ACTION_MAIN)
                app_intent.addCategory(Intent.CATEGORY_LAUNCHER)
                app_intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)

                flags = 0x08000000  # FLAG_UPDATE_CURRENT
                if Build_VERSION.SDK_INT >= 23:
                    flags |= 0x04000000  # FLAG_IMMUTABLE

                pending_intent = PendingIntent.getActivity(self.context, 0, app_intent, flags)
                builder.setContentIntent(pending_intent)
            except Exception as pe:
                print(f"[Notification] PendingIntent notice: {pe}")

            # MediaStyle if available
            try:
                MediaStyle = autoclass("android.app.Notification$MediaStyle")
                builder.setStyle(MediaStyle())
            except Exception:
                pass

            self.manager.notify(self.media_notification_id, builder.build())
        except Exception as e:
            print(f"[Notification] Media playback notice: {e}")

    def hide_media_playback(self):
        """Dismiss media playback notification when playback is stopped or closed."""
        self._is_media_playing = False
        try:
            if self._init_android() and self.manager:
                self.manager.cancel(self.media_notification_id)
        except Exception:
            pass


_GLOBAL_NOTIFICATION_MANAGER: Optional[AndroidNotificationManager] = None

def get_notification_manager() -> AndroidNotificationManager:
    """Retrieve shared global notification manager instance."""
    global _GLOBAL_NOTIFICATION_MANAGER
    if _GLOBAL_NOTIFICATION_MANAGER is None:
        _GLOBAL_NOTIFICATION_MANAGER = AndroidNotificationManager()
    return _GLOBAL_NOTIFICATION_MANAGER


if KIVY_AVAILABLE:
    class StyledCard(BoxLayout):
        """Card widget with rounded background and subtle dark-mode styling."""
        def __init__(self, bg_color=(0.10, 0.12, 0.18, 1.0), radius=12, **kwargs):
            super().__init__(**kwargs)
            self.bg_color = bg_color
            self.radius = radius
            with self.canvas.before:
                Color(*self.bg_color)
                self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(self.radius)])
            self.bind(pos=self._update_rect, size=self._update_rect)

        def _update_rect(self, *args):
            self.rect.pos = self.pos
            self.rect.size = self.size


    class IconActionButton(ButtonBehavior, BoxLayout):
        """Action button combining a crisp PNG icon and readable text label."""
        def __init__(
            self,
            icon_path: str = "",
            text: str = "",
            bg_color=(0.18, 0.22, 0.32, 1.0),
            text_color=(1.0, 1.0, 1.0, 1.0),
            font_size="11sp",
            icon_size=(dp(16), dp(16)),
            radius=8,
            **kwargs,
        ):
            super().__init__(**kwargs)
            self.orientation = "horizontal"
            self.spacing = dp(5)
            self.padding = [dp(8), dp(4)]
            self.bg_color = list(bg_color)
            self.radius = radius

            with self.canvas.before:
                self._col_instr = Color(*self.bg_color)
                self._rect_instr = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(self.radius)])
            self.bind(pos=self._update_geom, size=self._update_geom)

            resolved_icon = get_asset_icon(icon_path)
            if resolved_icon and os.path.exists(resolved_icon):
                self.icon_img = Image(
                    source=resolved_icon,
                    size_hint=(None, None),
                    size=icon_size,
                    allow_stretch=True,
                    keep_ratio=True,
                )
                self.add_widget(self.icon_img)

            if text:
                self.label = Label(
                    text=text,
                    font_size=font_size,
                    bold=True,
                    color=text_color,
                    halign="center",
                    valign="middle",
                )
                self.label.bind(size=self.label.setter("text_size"))
                self.add_widget(self.label)

        def _update_geom(self, *args):
            self._rect_instr.pos = self.pos
            self._rect_instr.size = self.size

        def set_bg_color(self, rgba):
            self._col_instr.rgba = rgba

        @property
        def text(self):
            return self.label.text if hasattr(self, "label") and self.label else ""

        @text.setter
        def text(self, val):
            if hasattr(self, "label") and self.label:
                self.label.text = str(val)


    class NavTabItem(ButtonBehavior, BoxLayout):
        """Bottom navigation tab item with crisp icon and bold title."""
        def __init__(self, tab_name: str, icon_name: str, label_text: str, is_active=False, **kwargs):
            super().__init__(**kwargs)
            self.orientation = "vertical"
            self.tab_name = tab_name
            self.spacing = dp(2)
            self.padding = [dp(4), dp(4)]
            self.is_active = is_active

            with self.canvas.before:
                self._bg_col = Color(0.18, 0.22, 0.32, 1.0 if is_active else 0.0)
                self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            self.bind(pos=self._update_geom, size=self._update_geom)

            icon_path = get_asset_icon(icon_name)
            self.icon_img = Image(
                source=icon_path,
                size_hint=(None, None),
                size=(dp(22), dp(22)),
                allow_stretch=True,
                keep_ratio=True,
                pos_hint={"center_x": 0.5},
            )
            self.add_widget(self.icon_img)

            active_col = (1.0, 0.72, 0.0, 1.0)
            inactive_col = (0.65, 0.70, 0.80, 1.0)
            self.label = Label(
                text=label_text,
                font_size="10.5sp",
                bold=True,
                color=active_col if is_active else inactive_col,
                size_hint_y=None,
                height=dp(14),
                halign="center",
                valign="middle",
            )
            self.label.bind(size=self.label.setter("text_size"))
            self.add_widget(self.label)

        def _update_geom(self, *args):
            self._rect.pos = self.pos
            self._rect.size = self.size

        def set_active(self, active: bool):
            self.is_active = active
            self._bg_col.rgba = (0.18, 0.22, 0.32, 1.0) if active else (0.09, 0.11, 0.16, 1.0)
            self.label.color = (1.0, 0.72, 0.0, 1.0) if active else (0.65, 0.70, 0.80, 1.0)

        @property
        def text(self):
            return self.label.text

        @text.setter
        def text(self, val):
            self.label.text = val


    class DownloadActionButton(ButtonBehavior, BoxLayout):
        """Full-width primary download button with animated arrow icon."""
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.orientation = "horizontal"
            self.spacing = dp(8)
            self.padding = [dp(16), dp(10)]
            self.size_hint_y = None
            self.height = dp(52)

            with self.canvas.before:
                self._col_instr = Color(1.0, 0.65, 0.0, 1.0)
                self._rect_instr = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            self.bind(pos=self._update_geom, size=self._update_geom)

            icon_path = get_asset_icon("download_arrow.png")
            self.icon_img = Image(
                source=icon_path,
                size_hint=(None, None),
                size=(dp(24), dp(24)),
                allow_stretch=True,
                keep_ratio=True,
            )
            self.add_widget(self.icon_img)

            self.label = Label(
                text="DOWNLOAD NOW",
                font_size="15sp",
                bold=True,
                color=(0.04, 0.05, 0.08, 1.0),
                halign="center",
                valign="middle",
            )
            self.label.bind(size=self.label.setter("text_size"))
            self.add_widget(self.label)

        def _update_geom(self, *args):
            self._rect_instr.pos = self.pos
            self._rect_instr.size = self.size

        @property
        def text(self):
            return self.label.text

        @text.setter
        def text(self, val):
            self.label.text = val

        @property
        def disabled(self):
            return super().disabled

        @disabled.setter
        def disabled(self, val):
            super(DownloadActionButton, type(self)).disabled.__set__(self, val)
            if val:
                self._col_instr.rgba = (0.35, 0.35, 0.40, 1.0)
            else:
                self._col_instr.rgba = (1.0, 0.65, 0.0, 1.0)


    class SettingsIconButton(ButtonBehavior, BoxLayout):
        """Header circular button with settings gear icon."""
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.size_hint = (None, None)
            self.size = (dp(40), dp(40))
            self.padding = [dp(8), dp(8)]
            with self.canvas.before:
                self._col_instr = Color(0.16, 0.19, 0.28, 1.0)
                self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(20)])
            self.bind(pos=self._update_geom, size=self._update_geom)
            icon_path = get_asset_icon("settings.png")
            self.icon_img = Image(
                source=icon_path,
                size_hint=(None, None),
                size=(dp(24), dp(24)),
                allow_stretch=True,
                keep_ratio=True,
            )
            self.add_widget(self.icon_img)

        def _update_geom(self, *args):
            self.rect.pos = self.pos
            self.rect.size = self.size


    class FormatOptionCard(ButtonBehavior, BoxLayout):
        """Selectable format/quality row inside the Download Options Modal."""
        def __init__(
            self,
            key: str,
            title: str,
            subtitle: str,
            badge_text: str = "",
            is_selected: bool = False,
            on_select_cb=None,
            **kwargs,
        ):
            super().__init__(**kwargs)
            self.orientation = "horizontal"
            self.size_hint_y = None
            self.height = dp(52)
            self.spacing = dp(8)
            self.padding = [dp(10), dp(6)]
            self.key = key
            self.is_selected = is_selected
            self.on_select_cb = on_select_cb

            with self.canvas.before:
                self._col_instr = Color(
                    *( (0.22, 0.28, 0.44, 1.0) if is_selected else (0.11, 0.13, 0.20, 1.0) )
                )
                self._rect_instr = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            self.bind(pos=self._update_geom, size=self._update_geom)

            # Indicator dot / radio
            self.indicator_lbl = Label(
                text="[b][color=#FFB300]●[/color][/b]" if is_selected else "[color=#607D8B]○[/color]",
                markup=True,
                font_size="16sp",
                size_hint=(None, 1.0),
                width=dp(22),
                halign="center",
                valign="middle",
            )
            self.indicator_lbl.bind(size=self.indicator_lbl.setter("text_size"))
            self.add_widget(self.indicator_lbl)

            # Title and Subtitle column
            info_col = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=1.0)
            self.title_lbl = Label(
                text=f"[b]{title}[/b]",
                markup=True,
                font_size="12sp",
                color=(1.0, 0.85, 0.20, 1.0) if is_selected else (0.95, 0.95, 1.0, 1.0),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(18),
            )
            self.title_lbl.bind(size=self.title_lbl.setter("text_size"))
            info_col.add_widget(self.title_lbl)

            self.sub_lbl = Label(
                text=subtitle,
                font_size="10sp",
                color=(0.65, 0.70, 0.82, 1.0),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(16),
            )
            self.sub_lbl.bind(size=self.sub_lbl.setter("text_size"))
            info_col.add_widget(self.sub_lbl)
            self.add_widget(info_col)

            # Optional badge
            if badge_text:
                is_gold = "1080p" in badge_text or "MP3" in badge_text or "PLAYLIST" in badge_text
                badge_bg = (0.28, 0.20, 0.08, 1.0) if is_gold else (0.13, 0.18, 0.28, 1.0)
                badge_fg = (1.0, 0.80, 0.20, 1.0) if is_gold else (0.40, 0.82, 1.0, 1.0)
                badge_card = StyledCard(
                    size_hint=(None, None),
                    size=(dp(68), dp(24)),
                    bg_color=badge_bg,
                    radius=6,
                    pos_hint={"center_y": 0.5},
                )
                badge_lbl = Label(
                    text=badge_text,
                    font_size="9.5sp",
                    bold=True,
                    color=badge_fg,
                    halign="center",
                    valign="middle",
                )
                badge_lbl.bind(size=badge_lbl.setter("text_size"))
                badge_card.add_widget(badge_lbl)
                self.add_widget(badge_card)

            self.bind(on_press=self._on_pressed)

        def _update_geom(self, *args):
            self._rect_instr.pos = self.pos
            self._rect_instr.size = self.size

        def set_selected(self, selected: bool):
            self.is_selected = selected
            if selected:
                self._col_instr.rgba = (0.22, 0.28, 0.44, 1.0)
                self.indicator_lbl.text = "[b][color=#FFB300]●[/color][/b]"
                self.title_lbl.color = (1.0, 0.85, 0.20, 1.0)
            else:
                self._col_instr.rgba = (0.11, 0.13, 0.20, 1.0)
                self.indicator_lbl.text = "[color=#607D8B]○[/color]"
                self.title_lbl.color = (0.95, 0.95, 1.0, 1.0)

        def _on_pressed(self, *args):
            if self.on_select_cb:
                self.on_select_cb(self.key)


    class PlaylistItemRow(ButtonBehavior, BoxLayout):
        """Interactive row widget representing an individual video entry in a playlist with a checkbox toggle."""
        def __init__(self, index: int, title: str, duration: str = "", is_checked: bool = True, on_toggle_cb=None, **kwargs):
            super().__init__(**kwargs)
            self.orientation = "horizontal"
            self.spacing = dp(8)
            self.padding = [dp(8), dp(4)]
            self.size_hint_y = None
            self.height = dp(42)
            self.index = index
            self.is_checked = is_checked
            self.on_toggle_cb = on_toggle_cb

            with self.canvas.before:
                self._bg_col = Color(0.12, 0.15, 0.22, 1.0 if is_checked else 0.45)
                self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            self.bind(pos=self._update_geom, size=self._update_geom)

            # Checkbox label [✔] or [○]
            self.check_lbl = Label(
                text="[b][color=#00E676]✔[/color][/b]" if is_checked else "[color=#607D8B]○[/color]",
                markup=True,
                font_size="13sp",
                size_hint=(None, None),
                size=(dp(24), dp(24)),
                pos_hint={"center_y": 0.5},
            )
            self.add_widget(self.check_lbl)

            # Sequence Number
            self.idx_lbl = Label(
                text=f"#{index}",
                font_size="10.5sp",
                bold=True,
                color=(0.50, 0.70, 0.95, 1.0),
                size_hint=(None, None),
                size=(dp(28), dp(24)),
                pos_hint={"center_y": 0.5},
            )
            self.add_widget(self.idx_lbl)

            # Clean Title
            clean_t = safe_display_text(title)
            if len(clean_t) > 36:
                clean_t = clean_t[:33] + "..."
            self.title_lbl = Label(
                text=f"[b]{clean_t}[/b]",
                markup=True,
                font_size="11sp",
                color=(0.95, 0.95, 1.0, 1.0 if is_checked else 0.50),
                size_hint_x=1.0,
                halign="left",
                valign="middle",
            )
            self.title_lbl.bind(size=self.title_lbl.setter("text_size"))
            self.add_widget(self.title_lbl)

            # Duration badge
            if duration:
                self.dur_lbl = Label(
                    text=duration,
                    font_size="9.5sp",
                    color=(0.40, 0.80, 1.0, 0.85),
                    size_hint=(None, None),
                    size=(dp(44), dp(24)),
                    pos_hint={"center_y": 0.5},
                )
                self.add_widget(self.dur_lbl)

            self.bind(on_press=self._on_row_pressed)

        def _update_geom(self, *args):
            self._rect.pos = self.pos
            self._rect.size = self.size

        def set_checked(self, checked: bool):
            self.is_checked = checked
            self.check_lbl.text = "[b][color=#00E676]✔[/color][/b]" if checked else "[color=#607D8B]○[/color]"
            self._bg_col.rgba = (0.12, 0.15, 0.22, 1.0) if checked else (0.08, 0.10, 0.14, 0.45)
            self.title_lbl.color = (0.95, 0.95, 1.0, 1.0 if checked else 0.50)

        def _on_row_pressed(self, *args):
            new_val = not self.is_checked
            self.set_checked(new_val)
            if self.on_toggle_cb:
                self.on_toggle_cb(self.index - 1, new_val)


    class MSKDownloaderMobile(App):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.download_state = {
                "is_active": False,
                "cancel_requested": False,
                "current_part_files": set(),
            }
            self.current_sound = None
            self.current_track_path: Optional[Path] = None
            self.is_audio_playing = False
            self.audio_playlist: List[Path] = []
            self.audio_index = 0
            self.player_clock_event = None
            self.selected_platform = "ALL"
            self.current_preview_url = ""
            self.current_preview_info: Optional[Dict[str, Any]] = None
            self.last_clipboard_text = ""
            self.last_notif_time = 0.0
            self.active_tab = "home"
            self.active_filter = "all"

        def build(self):
            self.title = "MSK YTDL"
            Window.clearcolor = (0.05, 0.06, 0.09, 1.0)  # Deep obsidian dark mode

            # Attempt to register system fallback font for native Devanagari & international glyphs
            try:
                if is_running_on_android():
                    for sys_font in (
                        "/system/fonts/NotoSansDevanagari-Regular.ttf",
                        "/system/fonts/DroidSansFallback.ttf",
                        "/system/fonts/NotoSans-Regular.ttf",
                        "/system/fonts/Roboto-Regular.ttf",
                    ):
                        if os.path.exists(sys_font):
                            LabelBase.register(name="Roboto", fn_regular=sys_font)
                            break
            except Exception:
                pass

            self.notification_manager = get_notification_manager()
            self.current_preview_url = ""
            self.current_preview_info: Optional[Dict[str, Any]] = None
            self.last_clipboard_text = ""
            self.last_notif_time = 0.0
            self.active_tab = "home"
            self.active_filter = "all"
            self.selected_platform = "ALL"

            # Download queue & active state tracking
            self.download_state = {
                "is_active": False,
                "cancel_requested": False,
                "current_part_files": set(),
            }

            # Floating Mini Music Player state
            self.current_sound = None
            self.current_track_path: Optional[Path] = None
            self.is_audio_playing = False
            self.audio_playlist: List[Path] = []
            self.audio_index = 0
            self.player_clock_event = None

            # Default quality spinner for preferences
            self.quality_spinner = Spinner(
                text="Video (Max Quality - 1080p / 720p HD)",
                values=(
                    "Video (Max Quality - 1080p / 720p HD)",
                    "Video (720p HD MP4)",
                    "Video (360p Fast MP4)",
                    "Audio Only (HQ MP3 Music + Album Art)",
                    "Audio Only (M4A AAC Fast)",
                ),
                size_hint_y=None,
                height=dp(42),
            )

            # Request Android storage & notification permissions on startup
            request_android_permissions()

            # Listen for Android "Share from YouTube" intents (warm start)
            try:
                import android.activity
                android.activity.bind(on_new_intent=self.on_new_intent)
            except Exception:
                pass

            # Root vertical container: [Pinned Header] + [Dynamic Main View] + [Floating Mini Player] + [Pinned Bottom Footer Nav]
            root = BoxLayout(orientation="vertical")

            # -------------------------------------------------------------
            # Top App Header (Logo + Brand + Dynamic Version)
            # -------------------------------------------------------------
            header_card = self.create_header_card()
            root.add_widget(header_card)

            # -------------------------------------------------------------
            # Dynamic Main Screen Container
            # -------------------------------------------------------------
            self.main_container = BoxLayout(orientation="vertical", size_hint_y=1.0)
            root.add_widget(self.main_container)

            # Build all 4 Tab Views
            self.home_view = self.build_home_view()
            self.reels_view = self.build_reels_view()
            self.downloads_view = self.build_downloads_view()
            self.videos_view = self.build_videos_view()

            # Start on Home view
            self.main_container.add_widget(self.home_view)

            # -------------------------------------------------------------
            # Floating Mini Music Player Bar (Feature 3)
            # -------------------------------------------------------------
            self.mini_player_bar = self.create_mini_player_bar()
            root.add_widget(self.mini_player_bar)

            # -------------------------------------------------------------
            # Bottom Navigation Footer Bar (Home / Downloads / Videos)
            # -------------------------------------------------------------
            self.nav_footer = self.create_bottom_nav()
            root.add_widget(self.nav_footer)

            # Initial startup tasks
            Clock.schedule_once(self.check_initial_intent, 0.4)
            Clock.schedule_once(lambda dt: self.refresh_library(), 0.6)
            Clock.schedule_once(lambda dt: sync_and_migrate_legacy_downloads(), 1.0)
            Clock.schedule_once(lambda dt: self.populate_home_recommendations(), 0.5)
            Clock.schedule_interval(self.check_clipboard, 2.5)

            # Feature 6: Silent GitHub update check in background
            Clock.schedule_once(lambda dt: self.check_for_updates(user_triggered=False), 5.0)

            return root

        # -----------------------------------------------------------------
        # Header Card Builder & Settings Modal
        # -----------------------------------------------------------------
        def create_header_card(self) -> BoxLayout:
            header_card = StyledCard(
                orientation="horizontal",
                padding=[dp(12), dp(8)],
                spacing=dp(10),
                size_hint_y=None,
                height=dp(60),
                bg_color=(0.08, 0.10, 0.15, 1.0),
            )

            # Resolve logo file path
            logo_path = ""
            for candidate in (
                Path(__file__).resolve().parent / "icon.png",
                Path("icon.png"),
                Path("assets/logo.png"),
            ):
                if candidate.exists():
                    logo_path = str(candidate)
                    break

            if logo_path:
                app_logo = Image(
                    source=logo_path,
                    size_hint=(None, None),
                    size=(dp(44), dp(44)),
                    allow_stretch=True,
                    keep_ratio=True,
                )
                header_card.add_widget(app_logo)

            header_text_box = BoxLayout(orientation="vertical", spacing=dp(1), size_hint_x=1.0)
            app_version = get_app_version()
            brand_label = Label(
                text=f"[b][color=#FFB300]MSK[/color] YTDL[/b]  [size=12sp][color=#00E676]v{app_version}[/color][/size]",
                markup=True,
                font_size="20sp",
                size_hint_y=None,
                height=dp(24),
                halign="left",
                valign="middle",
            )
            brand_label.bind(size=brand_label.setter("text_size"))

            tagline = Label(
                text="Fast Video & Audio Downloader • by MSK Software Solutions",
                font_size="10.5sp",
                color=(0.68, 0.73, 0.84, 1.0),
                size_hint_y=None,
                height=dp(16),
                halign="left",
                valign="middle",
            )
            tagline.bind(size=tagline.setter("text_size"))

            header_text_box.add_widget(brand_label)
            header_text_box.add_widget(tagline)
            header_card.add_widget(header_text_box)

            # Settings Icon Button (Gear Icon)
            self.settings_btn = SettingsIconButton()
            self.settings_btn.bind(on_press=lambda ins: self.open_settings_modal())
            header_card.add_widget(self.settings_btn)

            return header_card

        def open_settings_modal(self):
            """Open in-app Settings modal for quality preference, clipboard toggle, storage info, and app details."""
            modal = ModalView(size_hint=(0.92, 0.78), auto_dismiss=True)

            content = StyledCard(
                orientation="vertical",
                padding=[dp(16), dp(16)],
                spacing=dp(12),
                bg_color=(0.08, 0.10, 0.16, 1.0),
                radius=16,
            )

            # Header Row
            header_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(32))
            settings_icon_path = get_asset_icon("settings.png")
            if settings_icon_path:
                header_row.add_widget(
                    Image(source=settings_icon_path, size_hint=(None, None), size=(dp(26), dp(26)), allow_stretch=True, keep_ratio=True)
                )
            modal_title = Label(
                text="[b]App Settings & Preferences[/b]",
                markup=True,
                font_size="16sp",
                color=(1.0, 0.75, 0.0, 1.0),
                halign="left",
                valign="middle",
            )
            modal_title.bind(size=modal_title.setter("text_size"))
            header_row.add_widget(modal_title)
            content.add_widget(header_row)

            # Scrollable body in case of small phone screens
            scroll_body = ScrollView(do_scroll_x=False, do_scroll_y=True)
            body_layout = BoxLayout(orientation="vertical", spacing=dp(12), size_hint_y=None)
            body_layout.bind(minimum_height=body_layout.setter("height"))

            # Section 1: Default Video & Audio Quality
            q_card = StyledCard(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(6), size_hint_y=None, height=dp(88), bg_color=(0.11, 0.13, 0.20, 1.0))
            q_lbl = Label(
                text="[b]Default Download Quality[/b]\n[size=10.5sp][color=#90CAF9]Choose default resolution for new downloads[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                size_hint_y=None,
                height=dp(30),
            )
            q_lbl.bind(size=q_lbl.setter("text_size"))
            q_card.add_widget(q_lbl)

            q_spinner = Spinner(
                text=self.quality_spinner.text,
                values=self.quality_spinner.values,
                size_hint_y=None,
                height=dp(38),
                background_color=(0.16, 0.20, 0.30, 1.0),
                color=(1, 1, 1, 1),
                font_size="12sp",
            )
            def on_pref_quality_changed(spinner, text):
                self.quality_spinner.text = text
            q_spinner.bind(text=on_pref_quality_changed)
            q_card.add_widget(q_spinner)
            body_layout.add_widget(q_card)

            # Section 2: Smart Clipboard Detection Toggle
            clip_card = StyledCard(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(6), size_hint_y=None, height=dp(78), bg_color=(0.11, 0.13, 0.20, 1.0))
            clip_lbl = Label(
                text="[b]Smart Clipboard Auto-Detect[/b]\n[size=10.5sp][color=#90CAF9]Notify when YouTube links are copied outside the app[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                size_hint_y=None,
                height=dp(30),
            )
            clip_lbl.bind(size=clip_lbl.setter("text_size"))
            clip_card.add_widget(clip_lbl)

            is_clip_on = getattr(self, "clipboard_detection_enabled", True)
            clip_btn = Button(
                text="Auto-Detect: ENABLED" if is_clip_on else "Auto-Detect: DISABLED",
                font_size="11.5sp",
                bold=True,
                size_hint_y=None,
                height=dp(32),
                background_color=(0.10, 0.45, 0.22, 1.0) if is_clip_on else (0.35, 0.15, 0.15, 1.0),
                color=(1, 1, 1, 1),
            )
            def toggle_clip(ins):
                current = getattr(self, "clipboard_detection_enabled", True)
                new_state = not current
                self.clipboard_detection_enabled = new_state
                if new_state:
                    ins.text = "Auto-Detect: ENABLED"
                    ins.background_color = (0.10, 0.45, 0.22, 1.0)
                else:
                    ins.text = "Auto-Detect: DISABLED"
                    ins.background_color = (0.35, 0.15, 0.15, 1.0)
                    self.clipboard_banner.height = 0
                    self.clipboard_banner.opacity = 0
            clip_btn.bind(on_press=toggle_clip)
            clip_card.add_widget(clip_btn)
            body_layout.add_widget(clip_card)

            # Section 3: Storage Location
            store_card = StyledCard(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(4), size_hint_y=None, height=dp(66), bg_color=(0.11, 0.13, 0.20, 1.0))
            store_lbl = Label(
                text=f"[b]Download Destination[/b]\n[size=10.5sp][color=#B0BEC5]{get_android_download_dir()}[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                size_hint_y=None,
                height=dp(46),
            )
            store_lbl.bind(size=store_lbl.setter("text_size"))
            store_card.add_widget(store_lbl)
            body_layout.add_widget(store_card)

            # Section 4: About App
            app_ver = get_app_version()
            about_card = StyledCard(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(3), size_hint_y=None, height=dp(72), bg_color=(0.11, 0.13, 0.20, 1.0))
            about_lbl = Label(
                text=f"[b]MSK YTDL v{app_ver}[/b]\n[size=10.5sp][color=#78909C]Developed by MSK Software Solutions\nWebsite: mskinstitute.in[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                size_hint_y=None,
                height=dp(52),
            )
            about_lbl.bind(size=about_lbl.setter("text_size"))
            about_card.add_widget(about_lbl)
            body_layout.add_widget(about_card)

            # Section 5: Software Updates (Feature 6)
            update_card = StyledCard(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(6), size_hint_y=None, height=dp(86), bg_color=(0.11, 0.13, 0.20, 1.0))
            up_lbl = Label(
                text="[b]Software Updates[/b]\n[size=10.5sp][color=#90CAF9]Check GitHub releases for latest features & fixes[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                size_hint_y=None,
                height=dp(30),
            )
            up_lbl.bind(size=up_lbl.setter("text_size"))
            update_card.add_widget(up_lbl)

            chk_up_btn = IconActionButton(
                icon_path="settings.png",
                text="CHECK FOR UPDATES",
                font_size="11.5sp",
                size_hint_y=None,
                height=dp(34),
                bg_color=(0.20, 0.28, 0.44, 1.0),
                text_color=(1, 1, 1, 1),
            )
            def on_chk_updates_pressed(ins):
                modal.dismiss()
                self.check_for_updates(user_triggered=True)
            chk_up_btn.bind(on_press=on_chk_updates_pressed)
            update_card.add_widget(chk_up_btn)
            body_layout.add_widget(update_card)

            scroll_body.add_widget(body_layout)
            content.add_widget(scroll_body)

            # Close Button
            close_btn = Button(
                text="SAVE & CLOSE",
                font_size="13sp",
                bold=True,
                size_hint_y=None,
                height=dp(42),
                background_color=(1.0, 0.68, 0.0, 1.0),
                color=(0.04, 0.05, 0.08, 1.0),
            )
            close_btn.bind(on_press=modal.dismiss)
            content.add_widget(close_btn)

            modal.add_widget(content)
            modal.open()

        # -----------------------------------------------------------------
        # Bottom Navigation Footer Bar Builder (Home / Reels / Videos / Downloads)
        # -----------------------------------------------------------------
        def create_bottom_nav(self) -> BoxLayout:
            nav_bar = StyledCard(
                orientation="horizontal",
                padding=[dp(4), dp(3)],
                spacing=dp(4),
                size_hint_y=None,
                height=dp(56),
                bg_color=(0.07, 0.08, 0.13, 1.0),
            )

            self.nav_btn_home = NavTabItem("home", "home.png", "HOME", is_active=True)
            self.nav_btn_home.bind(on_press=lambda ins: self.switch_tab("home"))
            nav_bar.add_widget(self.nav_btn_home)

            self.nav_btn_reels = NavTabItem("reels", "reels.png", "REELS", is_active=False)
            self.nav_btn_reels.bind(on_press=lambda ins: self.switch_tab("reels"))
            nav_bar.add_widget(self.nav_btn_reels)

            self.nav_btn_videos = NavTabItem("videos", "videos.png", "VIDEOS", is_active=False)
            self.nav_btn_videos.bind(on_press=lambda ins: self.switch_tab("videos"))
            nav_bar.add_widget(self.nav_btn_videos)

            self.nav_btn_downloads = NavTabItem("downloads", "downloads.png", "DOWNLOADS", is_active=False)
            self.nav_btn_downloads.bind(on_press=lambda ins: self.switch_tab("downloads"))
            nav_bar.add_widget(self.nav_btn_downloads)

            return nav_bar

        # -----------------------------------------------------------------
        # Tab Switching Logic
        # -----------------------------------------------------------------
        def switch_tab(self, tab_name: str):
            if self.active_tab == tab_name and self.main_container.children:
                return

            self.active_tab = tab_name
            self.main_container.clear_widgets()

            self.nav_btn_home.set_active(tab_name == "home")
            if hasattr(self, "nav_btn_reels"):
                self.nav_btn_reels.set_active(tab_name == "reels")
            self.nav_btn_videos.set_active(tab_name == "videos")
            self.nav_btn_downloads.set_active(tab_name == "downloads")

            if tab_name == "home":
                self.main_container.add_widget(self.home_view)
            elif tab_name == "reels":
                self.main_container.add_widget(self.reels_view)
                Clock.schedule_once(lambda dt: self.populate_reels(), 0.05)
            elif tab_name == "downloads":
                self.main_container.add_widget(self.downloads_view)
                Clock.schedule_once(lambda dt: self.refresh_library(), 0.05)
            elif tab_name == "videos":
                self.main_container.add_widget(self.videos_view)
                Clock.schedule_once(lambda dt: self.populate_recommendations(), 0.05)

        # -----------------------------------------------------------------
        # View 1: Home View (Input, Preview, Format, Download, Progress)
        # -----------------------------------------------------------------
        def build_home_view(self) -> ScrollView:
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
            content = BoxLayout(
                orientation="vertical",
                padding=[dp(12), dp(10), dp(12), dp(24)],
                spacing=dp(10),
                size_hint_y=None,
            )
            content.bind(minimum_height=content.setter("height"))

            # Smart Clipboard Auto-Detect Banner
            self.clipboard_banner = Button(
                text="YouTube link detected in clipboard! Tap to load",
                font_size="12sp",
                bold=True,
                size_hint_y=None,
                height=0,
                opacity=0,
                background_color=(1.0, 0.72, 0.0, 1.0),
                color=(0.05, 0.07, 0.12, 1.0),
            )
            self.clipboard_banner.bind(on_press=self.on_clipboard_banner_clicked)
            content.add_widget(self.clipboard_banner)

            # Multi-Platform Quick Selector Bar (Feature 2)
            plat_scroll = ScrollView(do_scroll_x=True, do_scroll_y=False, size_hint_y=None, height=dp(34))
            plat_box = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_x=None)
            plat_box.bind(minimum_width=plat_box.setter("width"))

            self.platform_chips = {}
            platforms = [
                ("ALL", (1.0, 0.72, 0.0, 1.0)),
                ("YOUTUBE", (0.85, 0.15, 0.15, 1.0)),
                ("INSTAGRAM", (0.88, 0.18, 0.45, 1.0)),
                ("FACEBOOK", (0.09, 0.47, 0.95, 1.0)),
                ("TIKTOK", (0.00, 0.85, 0.85, 1.0)),
                ("TWITTER / X", (0.35, 0.40, 0.50, 1.0)),
            ]
            for p_name, p_col in platforms:
                is_active = (p_name == getattr(self, "selected_platform", "ALL"))
                btn = Button(
                    text=p_name,
                    font_size="10.5sp",
                    bold=True,
                    size_hint=(None, None),
                    size=(dp(92) if "/" in p_name else dp(78), dp(30)),
                    background_color=p_col if is_active else (0.12, 0.15, 0.22, 1.0),
                    color=(0.05, 0.07, 0.12, 1.0) if is_active else (0.75, 0.80, 0.90, 1.0),
                )
                btn.bind(on_press=lambda ins, name=p_name: self.on_platform_chip_clicked(name))
                self.platform_chips[p_name] = btn
                plat_box.add_widget(btn)

            plat_scroll.add_widget(plat_box)
            content.add_widget(plat_scroll)

            # Unified Input Card: Video/Playlist Link or Search Query
            input_card = StyledCard(
                orientation="vertical",
                padding=[dp(12), dp(10)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(136),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            input_title = Label(
                text="[b]Search Video, Playlist, or Paste Link[/b]",
                markup=True,
                font_size="13sp",
                color=(0.95, 0.95, 1.0, 1.0),
                size_hint_y=None,
                height=dp(20),
                halign="left",
            )
            input_title.bind(size=input_title.setter("text_size"))
            input_card.add_widget(input_title)

            self.url_input = TextInput(
                hint_text="Search YouTube or paste video/playlist link...",
                multiline=False,
                font_size="13sp",
                size_hint_y=None,
                height=dp(42),
                background_color=(0.14, 0.16, 0.24, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.75, 0, 1),
                padding=[dp(10), dp(10)],
            )
            self.url_input.bind(text=self.on_url_input_changed)
            self.url_input.bind(on_text_validate=self.on_home_search_validate)
            input_card.add_widget(self.url_input)

            # Action Buttons Row: [PASTE] [SEARCH] [CLEAR]
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
            paste_btn = IconActionButton(
                icon_path="paste.png",
                text="PASTE",
                bg_color=(0.20, 0.26, 0.40, 1.0),
                text_color=(1, 0.75, 0, 1),
                font_size="11.5sp",
            )
            paste_btn.bind(on_press=self.on_paste_clicked)

            home_search_btn = IconActionButton(
                icon_path="search.png",
                text="SEARCH",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                font_size="11.5sp",
            )
            home_search_btn.bind(on_press=lambda ins: self.on_home_search_clicked())

            clear_btn = IconActionButton(
                icon_path="clear.png",
                text="CLEAR",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.80, 0.85, 0.95, 1.0),
                font_size="11.5sp",
            )
            clear_btn.bind(on_press=self.on_clear_clicked)

            btn_row.add_widget(paste_btn)
            btn_row.add_widget(home_search_btn)
            btn_row.add_widget(clear_btn)
            input_card.add_widget(btn_row)
            content.add_widget(input_card)

            # Active Media Preview Card
            self.preview_card = StyledCard(
                orientation="horizontal",
                padding=[dp(10), dp(8)],
                spacing=dp(10),
                size_hint_y=None,
                height=0,
                opacity=0,
                bg_color=(0.11, 0.14, 0.22, 1.0),
            )
            self.preview_thumb = AsyncImage(
                size_hint=(None, None),
                size=(dp(96), dp(62)),
                allow_stretch=True,
                keep_ratio=True,
            )
            self.preview_card.add_widget(self.preview_thumb)

            preview_info_col = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=1.0)
            self.preview_title = Label(
                text="Loading title...",
                markup=True,
                font_size="12sp",
                bold=True,
                color=(1, 1, 1, 1),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(34),
            )
            self.preview_title.bind(size=self.preview_title.setter("text_size"))
            preview_info_col.add_widget(self.preview_title)

            self.preview_meta = Label(
                text="Channel • Duration",
                markup=True,
                font_size="10.5sp",
                color=(0.7, 0.75, 0.88, 1.0),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(18),
            )
            self.preview_meta.bind(size=self.preview_meta.setter("text_size"))
            preview_info_col.add_widget(self.preview_meta)
            self.preview_card.add_widget(preview_info_col)

            # Preview actions: [PLAY] and [GET]
            preview_btn_col = BoxLayout(orientation="vertical", spacing=dp(4), size_hint=(None, None), size=(dp(68), dp(62)))
            prev_play_btn = IconActionButton(
                icon_path="play.png",
                text="PLAY",
                bg_color=(0.18, 0.24, 0.38, 1.0),
                text_color=(0.40, 0.85, 1.0, 1.0),
                font_size="10.5sp",
                size_hint_y=0.5,
            )
            def on_home_preview_play(ins):
                media_info = self.current_preview_info or {"url": self.url_input.text, "title": self.preview_title.text}
                local_file = find_downloaded_media_file(
                    title=media_info.get("title"),
                    item_id=media_info.get("id")
                )
                if local_file and local_file.exists():
                    is_aud = local_file.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac")
                    if is_aud:
                        self.play_audio_track(local_file)
                    else:
                        self.play_video_file(local_file)
                else:
                    self.open_video_player_modal(media_info)

            prev_play_btn.bind(on_press=on_home_preview_play)

            prev_dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="GET",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                font_size="10.5sp",
                size_hint_y=0.5,
            )
            prev_dl_btn.bind(on_press=lambda ins: self.open_download_modal(self.current_preview_info))

            preview_btn_col.add_widget(prev_play_btn)
            preview_btn_col.add_widget(prev_dl_btn)
            self.preview_card.add_widget(preview_btn_col)
            content.add_widget(self.preview_card)

            # Status & Progress Card
            self.status_card = StyledCard(
                orientation="vertical",
                padding=[dp(12), dp(10)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(72),
                bg_color=(0.08, 0.10, 0.16, 1.0),
            )
            self.progress_bar = ProgressBar(
                max=100,
                value=0,
                size_hint_y=None,
                height=dp(8),
            )
            self.status_card.add_widget(self.progress_bar)

            self.status_label = Label(
                text="Ready. Paste video/playlist link or search above.",
                markup=True,
                font_size="11.5sp",
                color=(0.8, 0.85, 0.92, 1.0),
                size_hint_y=None,
                height=dp(26),
                halign="center",
            )
            self.status_label.bind(size=self.status_label.setter("text_size"))
            self.status_card.add_widget(self.status_label)

            # Active Download Cancellation Button (Feature 4)
            self.cancel_download_btn = IconActionButton(
                icon_path="clear.png",
                text="CANCEL DOWNLOAD",
                font_size="11sp",
                size_hint_y=None,
                height=0,
                opacity=0,
                bg_color=(0.48, 0.12, 0.15, 1.0),
                text_color=(1.0, 0.9, 0.9, 1.0),
            )
            self.cancel_download_btn.disabled = True
            self.cancel_download_btn.bind(on_press=lambda ins: self.cancel_active_download())
            self.status_card.add_widget(self.cancel_download_btn)

            content.add_widget(self.status_card)

            # Prominent DOWNLOAD NOW Action Button (Opens download pop-up)
            self.download_btn = DownloadActionButton()
            self.download_btn.bind(on_press=self.on_main_download_clicked)
            content.add_widget(self.download_btn)

            # Category Chips (Horizontal scrollable chips)
            chip_scroll = ScrollView(do_scroll_x=True, do_scroll_y=False, size_hint_y=None, height=dp(34))
            chip_box = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_x=None)
            chip_box.bind(minimum_width=chip_box.setter("width"))

            self.home_category_chips = {}
            categories = [
                ("🔥 ALL", "Trending Videos 2026"),
                ("🎵 MUSIC", "Top Bollywood English Music Hits"),
                ("😂 COMEDY", "Trending Comedy Standup"),
                ("🎬 MOVIES", "Latest Movie Trailers Teasers"),
                ("⚡ SHORTS", "Popular Viral Shorts"),
                ("🎮 GAMING", "Trending Gaming Highlights"),
                ("📻 LO-FI", "Relaxing LoFi Chill Beats"),
                ("💻 TECH", "Latest Tech & AI News"),
            ]
            for cat_name, cat_query in categories:
                btn = Button(
                    text=cat_name,
                    font_size="10.5sp",
                    bold=True,
                    size_hint=(None, None),
                    size=(dp(82), dp(32)),
                    background_color=(0.13, 0.16, 0.23, 1.0),
                    color=(0.75, 0.80, 0.90, 1.0),
                )
                btn.bind(on_press=lambda ins, q=cat_query, n=cat_name: self.on_home_category_chip_clicked(n, q))
                self.home_category_chips[cat_name] = btn
                chip_box.add_widget(btn)

            chip_scroll.add_widget(chip_box)
            content.add_widget(chip_scroll)

            # Results Section Header
            self.home_results_header_lbl = Label(
                text="[b]Trending & Recommended[/b]",
                markup=True,
                font_size="13sp",
                color=(0.95, 0.95, 1.0, 1.0),
                size_hint_y=None,
                height=dp(22),
                halign="left",
            )
            self.home_results_header_lbl.bind(size=self.home_results_header_lbl.setter("text_size"))
            content.add_widget(self.home_results_header_lbl)

            # Dynamic Video Results Container on Home
            self.home_recommendations_container = BoxLayout(
                orientation="vertical",
                spacing=dp(10),
                size_hint_y=None,
            )
            self.home_recommendations_container.bind(minimum_height=self.home_recommendations_container.setter("height"))
            content.add_widget(self.home_recommendations_container)

            # Storage Destination Note
            dest_card = StyledCard(
                orientation="horizontal",
                padding=[dp(12), dp(6)],
                size_hint_y=None,
                height=dp(34),
                bg_color=(0.07, 0.08, 0.13, 1.0),
            )
            self.storage_note = Label(
                text="Storage: Phone Storage > Download > YouTube",
                font_size="11sp",
                color=(0.55, 0.60, 0.70, 1.0),
            )
            dest_card.add_widget(self.storage_note)
            content.add_widget(dest_card)

            scroll.add_widget(content)
            return scroll

        # -----------------------------------------------------------------
        # View 2: Downloads View (Dedicated Offline Library Manager)
        # -----------------------------------------------------------------
        def build_downloads_view(self) -> ScrollView:
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
            content = BoxLayout(
                orientation="vertical",
                padding=[dp(14), dp(10), dp(14), dp(20)],
                spacing=dp(10),
                size_hint_y=None,
            )
            content.bind(minimum_height=content.setter("height"))

            # Header Card
            lib_header_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(94),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            top_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(28))
            self.downloads_title_lbl = Label(
                text="[b]Offline Media & Playlists[/b]",
                markup=True,
                font_size="13sp",
                color=(0.95, 0.95, 1.0, 1.0),
                halign="left",
            )
            self.downloads_title_lbl.bind(size=self.downloads_title_lbl.setter("text_size"))
            top_row.add_widget(self.downloads_title_lbl)

            play_all_btn = IconActionButton(
                icon_path="play.png",
                text="▶ PLAY ALL",
                font_size="10.5sp",
                size_hint=(None, None),
                size=(dp(90), dp(28)),
                bg_color=(0.10, 0.55, 0.28, 1.0),
                text_color=(1.0, 1.0, 1.0, 1.0),
            )
            play_all_btn.bind(on_press=lambda ins: self.play_all_playlist())
            top_row.add_widget(play_all_btn)

            refresh_btn = IconActionButton(
                icon_path="shuffle.png",
                text="REFRESH",
                font_size="10.5sp",
                size_hint=(None, None),
                size=(dp(84), dp(28)),
                bg_color=(0.18, 0.22, 0.32, 1.0),
                text_color=(1.0, 0.75, 0.0, 1.0),
            )
            refresh_btn.bind(on_press=lambda ins: self.refresh_library())
            top_row.add_widget(refresh_btn)
            lib_header_card.add_widget(top_row)

            # Filter Row: [📂 ALL] [🎵 SONGS (PLAYLIST)] [🎬 VIDEOS]
            filter_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(30))
            self.filter_btn_all = Button(
                text="📂 ALL",
                font_size="10.5sp",
                bold=True,
                background_color=(0.18, 0.24, 0.36, 1.0),
                color=(1, 0.75, 0, 1),
            )
            self.filter_btn_all.bind(on_press=lambda ins: self.set_downloads_filter("all"))

            self.filter_btn_audio = Button(
                text="🎵 SONGS (PLAYLIST)",
                font_size="10sp",
                bold=True,
                background_color=(0.12, 0.14, 0.20, 1.0),
                color=(0.7, 0.75, 0.85, 1),
            )
            self.filter_btn_audio.bind(on_press=lambda ins: self.set_downloads_filter("audio"))

            self.filter_btn_videos = Button(
                text="🎬 VIDEOS",
                font_size="10.5sp",
                bold=True,
                background_color=(0.12, 0.14, 0.20, 1.0),
                color=(0.7, 0.75, 0.85, 1),
            )
            self.filter_btn_videos.bind(on_press=lambda ins: self.set_downloads_filter("videos"))

            filter_row.add_widget(self.filter_btn_all)
            filter_row.add_widget(self.filter_btn_audio)
            filter_row.add_widget(self.filter_btn_videos)
            lib_header_card.add_widget(filter_row)

            content.add_widget(lib_header_card)

            # Downloaded Files Container
            self.library_container = BoxLayout(
                orientation="vertical",
                spacing=dp(8),
                size_hint_y=None,
            )
            self.library_container.bind(minimum_height=self.library_container.setter("height"))
            content.add_widget(self.library_container)

            scroll.add_widget(content)
            return scroll

        def play_all_playlist(self):
            """Start continuous offline playback of all downloaded audio tracks."""
            target_dir = get_android_download_dir()
            audio_files = []
            for ext in ("*.mp3", "*.m4a", "*.wav", "*.ogg", "*.opus", "*.flac", "*.aac"):
                audio_files.extend(target_dir.glob(ext))
            audio_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            if not audio_files:
                self.update_status("[color=#FFB300]No audio tracks found! Download audio to build playlist.[/color]", 0)
                return
            self.audio_playlist = audio_files
            self.audio_index = 0
            self.play_audio_track(self.audio_playlist[0])
            self.update_status(f"[color=#00E676]Playing in Playlist:[/color] {safe_display_text(self.audio_playlist[0].stem)}", 0)

        def set_downloads_filter(self, filter_type: str):
            self.active_filter = filter_type
            inactive_bg = (0.12, 0.14, 0.20, 1.0)
            inactive_col = (0.7, 0.75, 0.85, 1.0)
            active_bg = (0.18, 0.24, 0.36, 1.0)
            active_col = (1.0, 0.75, 0.0, 1.0)

            self.filter_btn_all.background_color = active_bg if filter_type == "all" else inactive_bg
            self.filter_btn_all.color = active_col if filter_type == "all" else inactive_col

            self.filter_btn_audio.background_color = active_bg if filter_type == "audio" else inactive_bg
            self.filter_btn_audio.color = active_col if filter_type == "audio" else inactive_col

            self.filter_btn_videos.background_color = active_bg if filter_type == "videos" else inactive_bg
            self.filter_btn_videos.color = active_col if filter_type == "videos" else inactive_col

            self.refresh_library()

        # -----------------------------------------------------------------
        # View 3: Videos View (Search YouTube & Dynamic Trending Picks)
        # -----------------------------------------------------------------
        def build_videos_view(self) -> ScrollView:
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
            content = BoxLayout(
                orientation="vertical",
                padding=[dp(14), dp(10), dp(14), dp(20)],
                spacing=dp(10),
                size_hint_y=None,
            )
            content.bind(minimum_height=content.setter("height"))

            # Header Card
            rec_header_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(10)],
                spacing=dp(2),
                size_hint_y=None,
                height=dp(56),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            rec_title = Label(
                text="[b]Discover & Search YouTube[/b]",
                markup=True,
                font_size="14sp",
                color=(0.95, 0.95, 1.0, 1.0),
                size_hint_y=None,
                height=dp(20),
                halign="left",
            )
            rec_title.bind(size=rec_title.setter("text_size"))

            rec_subtitle = Label(
                text="Search any song, artist, video or tap category chips below",
                font_size="10.5sp",
                color=(0.65, 0.70, 0.80, 1.0),
                size_hint_y=None,
                height=dp(16),
                halign="left",
            )
            rec_subtitle.bind(size=rec_subtitle.setter("text_size"))

            rec_header_card.add_widget(rec_title)
            rec_header_card.add_widget(rec_subtitle)
            content.add_widget(rec_header_card)

            # Search Box Card
            search_card = StyledCard(
                orientation="vertical",
                padding=[dp(12), dp(10)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(94),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            self.video_search_input = TextInput(
                hint_text="Search YouTube videos, songs, artists...",
                multiline=False,
                font_size="13sp",
                size_hint_y=None,
                height=dp(40),
                background_color=(0.14, 0.16, 0.24, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.75, 0, 1),
                padding=[dp(10), dp(10)],
            )
            self.video_search_input.bind(on_text_validate=lambda ins: self.on_search_clicked())
            search_card.add_widget(self.video_search_input)

            # Search Action Buttons: [SEARCH] [CLEAR] [SHUFFLE] with icons
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(34))
            self.search_btn = IconActionButton(
                icon_path="search.png",
                text="SEARCH",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                font_size="11sp",
            )
            self.search_btn.bind(on_press=lambda ins: self.on_search_clicked())

            clear_search_btn = IconActionButton(
                icon_path="clear.png",
                text="CLEAR",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.80, 0.85, 0.95, 1.0),
                font_size="11sp",
            )
            clear_search_btn.bind(on_press=lambda ins: self.on_search_clear_clicked())

            shuffle_btn = IconActionButton(
                icon_path="shuffle.png",
                text="SHUFFLE",
                bg_color=(0.18, 0.24, 0.38, 1.0),
                text_color=(0.40, 0.85, 1.0, 1.0),
                font_size="11sp",
            )
            shuffle_btn.bind(on_press=lambda ins: self.on_shuffle_trending())

            btn_row.add_widget(self.search_btn)
            btn_row.add_widget(clear_search_btn)
            btn_row.add_widget(shuffle_btn)
            search_card.add_widget(btn_row)
            content.add_widget(search_card)

            # Category Chips
            chip_scroll = ScrollView(do_scroll_x=True, do_scroll_y=False, size_hint_y=None, height=dp(34))
            chip_box = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_x=None)
            chip_box.bind(minimum_width=chip_box.setter("width"))

            self.category_chips = {}
            categories = [
                ("TRENDING", "Trending Videos 2026"),
                ("MUSIC", "Top Music Hits 2026"),
                ("GAMING", "Trending Gaming Highlights"),
                ("TECH", "Latest Tech & AI News"),
                ("SHORTS", "Popular YouTube Shorts"),
                ("LO-FI", "Relaxing LoFi Beats Chill"),
            ]
            for cat_name, cat_query in categories:
                btn = Button(
                    text=cat_name,
                    font_size="10.5sp",
                    bold=True,
                    size_hint=(None, None),
                    size=(dp(82), dp(32)),
                    background_color=(0.13, 0.16, 0.23, 1.0),
                    color=(0.75, 0.80, 0.90, 1.0),
                )
                btn.bind(on_press=lambda ins, q=cat_query, n=cat_name: self.on_category_chip_clicked(n, q))
                self.category_chips[cat_name] = btn
                chip_box.add_widget(btn)

            chip_scroll.add_widget(chip_box)
            content.add_widget(chip_scroll)

            # Results Section Title
            self.results_header_lbl = Label(
                text="[b]Trending & Recommended[/b]",
                markup=True,
                font_size="13sp",
                color=(0.95, 0.95, 1.0, 1.0),
                size_hint_y=None,
                height=dp(22),
                halign="left",
            )
            self.results_header_lbl.bind(size=self.results_header_lbl.setter("text_size"))
            content.add_widget(self.results_header_lbl)

            # Recommendations & Search Results Container
            self.recommendations_container = BoxLayout(
                orientation="vertical",
                spacing=dp(10),
                size_hint_y=None,
            )
            self.recommendations_container.bind(minimum_height=self.recommendations_container.setter("height"))
            content.add_widget(self.recommendations_container)

            scroll.add_widget(content)
            return scroll

        # -----------------------------------------------------------------
        # View 4: Reels & Shorts Vertical Feed View
        # -----------------------------------------------------------------
        def build_reels_view(self) -> ScrollView:
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
            content = BoxLayout(
                orientation="vertical",
                padding=[dp(12), dp(10), dp(12), dp(24)],
                spacing=dp(12),
                size_hint_y=None,
            )
            content.bind(minimum_height=content.setter("height"))

            # Header Card
            reels_header = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(10)],
                spacing=dp(3),
                size_hint_y=None,
                height=dp(58),
                bg_color=(0.12, 0.09, 0.20, 1.0),
            )
            r_title = Label(
                text="[b]🔥 Trending Reels & Shorts[/b]",
                markup=True,
                font_size="15sp",
                color=(1.0, 0.45, 0.65, 1.0),
                size_hint_y=None,
                height=dp(20),
                halign="left",
            )
            r_title.bind(size=r_title.setter("text_size"))
            r_sub = Label(
                text="Vertical video stream • Watch In-App • 1-Tap Download & Background Audio",
                font_size="10.5sp",
                color=(0.80, 0.75, 0.90, 1.0),
                size_hint_y=None,
                height=dp(16),
                halign="left",
            )
            r_sub.bind(size=r_sub.setter("text_size"))
            reels_header.add_widget(r_title)
            reels_header.add_widget(r_sub)
            content.add_widget(reels_header)

            # Reels Category Filter Chips
            reels_cat_scroll = ScrollView(do_scroll_x=True, do_scroll_y=False, size_hint_y=None, height=dp(34))
            reels_cat_box = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_x=None)
            reels_cat_box.bind(minimum_width=reels_cat_box.setter("width"))

            reel_categories = [
                ("🔥 Trending", "trending"),
                ("😂 Comedy", "comedy"),
                ("🎵 Music Reels", "music"),
                ("🕺 Dance Beats", "dance"),
                ("⚡ Viral Hacks", "viral"),
                ("📱 Tech Shorts", "tech"),
            ]
            self.reels_chips = {}
            self.active_reels_category = "trending"

            for label, cat_key in reel_categories:
                btn = Button(
                    text=label,
                    font_size="11sp",
                    bold=True,
                    size_hint=(None, None),
                    size=(dp(len(label) * 9 + 20), dp(30)),
                    background_color=(0.40, 0.15, 0.50, 1.0) if cat_key == "trending" else (0.13, 0.14, 0.22, 1.0),
                    color=(1, 1, 1, 1) if cat_key == "trending" else (0.75, 0.80, 0.90, 1.0),
                )
                btn.bind(on_press=lambda ins, k=cat_key: self.filter_reels(k))
                self.reels_chips[cat_key] = btn
                reels_cat_box.add_widget(btn)

            reels_cat_scroll.add_widget(reels_cat_box)
            content.add_widget(reels_cat_scroll)

            # Vertical Feed Container for Reels
            self.reels_feed_container = BoxLayout(
                orientation="vertical",
                spacing=dp(14),
                size_hint_y=None,
            )
            self.reels_feed_container.bind(minimum_height=self.reels_feed_container.setter("height"))
            content.add_widget(self.reels_feed_container)

            scroll.add_widget(content)
            return scroll

        def filter_reels(self, cat_key: str):
            """Filter reels feed by category key."""
            self.active_reels_category = cat_key
            for k, btn in self.reels_chips.items():
                if k == cat_key:
                    btn.background_color = (0.40, 0.15, 0.50, 1.0)
                    btn.color = (1.0, 1.0, 1.0, 1.0)
                else:
                    btn.background_color = (0.13, 0.14, 0.22, 1.0)
                    btn.color = (0.75, 0.80, 0.90, 1.0)
            self.populate_reels(category=cat_key)

        def populate_reels(self, category: str = "trending"):
            """Load vertical reel video items for the selected category."""
            if not hasattr(self, "reels_feed_container"):
                return
            self.reels_feed_container.clear_widgets()

            all_reels = [
                {
                    "title": "When Mom Finds Your Secret Stash 😂 #Shorts #Comedy",
                    "channel": "Comedy King",
                    "duration": "0:38",
                    "url": "https://www.youtube.com/shorts/q6EoRBvdVPQ",
                    "thumb": "https://i.ytimg.com/vi/q6EoRBvdVPQ/hqdefault.jpg",
                    "category": "comedy",
                },
                {
                    "title": "Viral Indian Street Food Magic! 🇮🇳 #StreetFood #Shorts",
                    "channel": "Foodie India",
                    "duration": "0:45",
                    "url": "https://www.youtube.com/shorts/60ItHLz5WEA",
                    "thumb": "https://i.ytimg.com/vi/60ItHLz5WEA/hqdefault.jpg",
                    "category": "viral",
                },
                {
                    "title": "Insane Flute Performance in Public 🔥 #Music #Viral",
                    "channel": "Flute Melodies",
                    "duration": "0:52",
                    "url": "https://www.youtube.com/shorts/AOeY-nDp7hI",
                    "thumb": "https://i.ytimg.com/vi/AOeY-nDp7hI/hqdefault.jpg",
                    "category": "music",
                },
                {
                    "title": "Fastest Dance Moves You Never Seen 🕺 #Dance #Trending",
                    "channel": "Dance Craze",
                    "duration": "0:32",
                    "url": "https://www.youtube.com/shorts/JGwWNGJdvx8",
                    "thumb": "https://i.ytimg.com/vi/JGwWNGJdvx8/hqdefault.jpg",
                    "category": "dance",
                },
                {
                    "title": "3 Incredible Smartphone Camera Tricks 📸 #Tech #Shorts",
                    "channel": "Gadget Hacks",
                    "duration": "0:58",
                    "url": "https://www.youtube.com/shorts/_uQrJ0TkZlc",
                    "thumb": "https://i.ytimg.com/vi/_uQrJ0TkZlc/hqdefault.jpg",
                    "category": "tech",
                },
                {
                    "title": "Mind-Blowing Science Experiment at Home ⚡ #Science #Shorts",
                    "channel": "Science Lab",
                    "duration": "0:41",
                    "url": "https://www.youtube.com/shorts/aircAruvnKk",
                    "thumb": "https://i.ytimg.com/vi/aircAruvnKk/hqdefault.jpg",
                    "category": "viral",
                },
            ]

            selected = [r for r in all_reels if category == "trending" or r["category"] == category]
            if not selected:
                selected = all_reels

            for item in selected:
                self.add_reel_card(item)

        def add_reel_card(self, reel_item: Dict[str, Any]):
            card = StyledCard(
                orientation="vertical",
                padding=[dp(12), dp(10)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(305),
                bg_color=(0.09, 0.10, 0.16, 1.0),
                radius=14,
            )

            # 1. Creator Info Row
            top_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(26))
            chan_name = safe_display_text(reel_item.get("channel", "Creator"))
            chan_lbl = Label(
                text=f"[color=#FF4081]●[/color] [b]{chan_name[:24]}[/b]",
                markup=True,
                font_size="12sp",
                color=(1.0, 1.0, 1.0, 1.0),
                halign="left",
                valign="middle",
                size_hint_x=1.0,
            )
            chan_lbl.bind(size=chan_lbl.setter("text_size"))
            top_row.add_widget(chan_lbl)

            tag_badge = Label(
                text="[b]#SHORTS[/b]",
                markup=True,
                font_size="10sp",
                color=(1.0, 0.40, 0.65, 1.0),
                size_hint=(None, None),
                size=(dp(60), dp(22)),
            )
            top_row.add_widget(tag_badge)
            card.add_widget(top_row)

            # 2. Thumbnail Preview with Tap to Play In-App
            thumb_box = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(165),
            )
            thumb_url = reel_item.get("thumb") or ""
            thumb_img = AsyncImage(
                source=thumb_url,
                size_hint=(1.0, 1.0),
                allow_stretch=True,
                keep_ratio=True,
            )
            def on_rthumb_err(instance, *args):
                for cand in ("icon.png", "assets/logo.png"):
                    if os.path.exists(cand):
                        instance.source = cand
                        break
                instance.opacity = 0.7
            thumb_img.bind(on_error=on_rthumb_err)
            thumb_box.add_widget(thumb_img)

            clean_title = safe_display_text(reel_item.get("title", "Viral Reel"))
            def on_thumb_touch_down(instance, touch):
                if instance.collide_point(*touch.pos):
                    touch.ud[f"reel_thumb_{id(instance)}"] = (touch.x, touch.y)
                return False

            def on_thumb_touch_up(instance, touch):
                k = f"reel_thumb_{id(instance)}"
                if k in touch.ud and instance.collide_point(*touch.pos):
                    sx, sy = touch.ud[k]
                    if abs(touch.x - sx) < dp(14) and abs(touch.y - sy) < dp(14):
                        play_online_video(reel_item.get("url", ""), title=clean_title)
                        return True
                return False

            thumb_box.bind(on_touch_down=on_thumb_touch_down, on_touch_up=on_thumb_touch_up)
            card.add_widget(thumb_box)

            # 3. Reel Title & Hashtags
            title_lbl = Label(
                text=f"[b]{clean_title[:65]}[/b]",
                markup=True,
                font_size="12sp",
                color=(0.95, 0.95, 1.0, 1.0),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(30),
            )
            title_lbl.bind(size=title_lbl.setter("text_size"))
            card.add_widget(title_lbl)

            # 4. Action Buttons: [▶ WATCH] [⬇ GET] [🎧 AUDIO]
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(36))

            watch_btn = IconActionButton(
                icon_path="play.png",
                text="WATCH",
                font_size="11sp",
                bg_color=(0.14, 0.50, 0.90, 1.0),
                text_color=(1, 1, 1, 1),
                size_hint_x=0.35,
            )
            watch_btn.bind(on_press=lambda ins, it=reel_item, t=clean_title: play_online_video(it.get("url", ""), title=t))
            btn_row.add_widget(watch_btn)

            dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="GET",
                font_size="11sp",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                size_hint_x=0.35,
            )
            dl_btn.bind(on_press=lambda ins, it=reel_item: self.open_download_modal(it))
            btn_row.add_widget(dl_btn)

            audio_btn = IconActionButton(
                icon_path="play.png",
                text="AUDIO",
                font_size="11sp",
                bg_color=(0.45, 0.20, 0.65, 1.0),
                text_color=(1, 1, 1, 1),
                size_hint_x=0.30,
            )
            audio_btn.bind(on_press=lambda ins, it=reel_item: self.play_audio_in_background(it))
            btn_row.add_widget(audio_btn)

            card.add_widget(btn_row)
            self.reels_feed_container.add_widget(card)

        def play_audio_in_background(self, media_item: Optional[Dict[str, Any]] = None):
            """Play video's audio track in background using mini player engine with screen-off support."""
            if not media_item:
                return
            url = media_item.get("url")
            raw_title = media_item.get("title", "Audio Stream")
            title = safe_display_text(raw_title)
            self.update_status(f"Buffering background audio: {title[:25]}...", 20)

            # Show mini player bar immediately
            self.mini_player_bar.height = dp(56)
            self.mini_player_bar.opacity = 1.0
            self.mini_player_bar.disabled = False
            self.mini_player_title.text = f"[b]🎧 {title[:28]}[/b]"
            self.mini_player_time.text = "Starting audio playback..."
            self.mini_player_play_btn.text = "⏸"

            def worker():
                try:
                    import yt_dlp
                    ydl_opts = {
                        "format": "140/bestaudio[ext=m4a]/bestaudio/18/best",
                        "quiet": True,
                        "no_warnings": True,
                    }
                    stream_url = None
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        stream_url = info.get("url")
                        if not stream_url and "formats" in info:
                            for f in info["formats"]:
                                if f.get("acodec") != "none":
                                    stream_url = f.get("url")
                                    break

                    if stream_url:
                        def start_stream(dt):
                            if self.current_sound:
                                try:
                                    self.current_sound.stop()
                                    self.current_sound.unload()
                                except Exception:
                                    pass
                                self.current_sound = None

                            if is_running_on_android():
                                try:
                                    native_p = AndroidNativeAudioPlayer(stream_url)
                                    if native_p._mp:
                                        self.current_sound = native_p
                                except Exception as ne:
                                    print(f"[BackgroundAudio] Android native stream notice: {ne}")

                            if not self.current_sound:
                                try:
                                    self.current_sound = SoundLoader.load(stream_url)
                                except Exception as le:
                                    print(f"[SoundLoader] Stream notice: {le}")
                                    self.current_sound = None

                            if self.current_sound:
                                self.is_audio_playing = True
                                self.current_sound.play()
                                self.notification_manager.show_media_playback(title, is_playing=True, media_type="Background Audio")
                                if not self.player_clock_event:
                                    self.player_clock_event = Clock.schedule_interval(self._update_player_progress, 0.4)
                                self.update_status("[color=#00E676]🎧 Background audio active![/color]", 100)
                            else:
                                play_online_video(url, title=title)

                        Clock.schedule_once(start_stream)
                    else:
                        Clock.schedule_once(lambda dt: play_online_video(url, title=title))
                except Exception as ex:
                    print(f"[BackgroundAudio] Notice: {ex}")
                    Clock.schedule_once(lambda dt: play_online_video(url, title=title))

            threading.Thread(target=worker, daemon=True).start()


        # -----------------------------------------------------------------
        # Videos Search & Recommendation Helpers
        # -----------------------------------------------------------------
        def on_search_clicked(self):
            """Execute in-app YouTube search."""
            query = self.video_search_input.text.strip()
            if not query:
                return
            self.search_youtube(query)

        def on_search_clear_clicked(self):
            """Reset search input and restore default trending picks."""
            self.video_search_input.text = ""
            for btn in self.category_chips.values():
                btn.background_color = (0.13, 0.16, 0.23, 1.0)
                btn.color = (0.75, 0.80, 0.90, 1.0)
            self.populate_recommendations()

        def on_category_chip_clicked(self, cat_name: str, cat_query: str):
            """Filter by selected category chip."""
            for name, btn in self.category_chips.items():
                if name == cat_name:
                    btn.background_color = (0.20, 0.28, 0.44, 1.0)
                    btn.color = (1.0, 0.75, 0.0, 1.0)
                else:
                    btn.background_color = (0.13, 0.16, 0.23, 1.0)
                    btn.color = (0.75, 0.80, 0.90, 1.0)
            self.video_search_input.text = cat_query
            self.search_youtube(cat_query, section_title=f"{cat_name} Picks")

        def on_shuffle_trending(self):
            """Shuffle random popular topic and search instantly."""
            import random
            topics = [
                "Trending Bollywood Songs",
                "Top Electronic Dance Music",
                "Viral YouTube Shorts",
                "AI Animation Filmmaking",
                "Python Coding Projects",
                "Best LoFi Study Beats",
                "Grand Theft Auto 6 Highlights",
                "NoCopyrightSounds Mix",
            ]
            picked = random.choice(topics)
            self.video_search_input.text = picked
            self.search_youtube(picked, section_title="Shuffled Picks")

        def search_youtube(self, query: str, section_title: Optional[str] = None):
            """Search YouTube via yt-dlp flat extraction without requiring API keys."""
            title = section_title or f"Results for: {query[:25]}"
            self.results_header_lbl.text = f"[b]{title}[/b]"
            self.recommendations_container.clear_widgets()

            # Loading indicator
            loading_card = StyledCard(
                orientation="vertical",
                padding=[dp(16), dp(16)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(70),
                bg_color=(0.08, 0.10, 0.15, 1.0),
            )
            loading_lbl = Label(
                text=f"Searching YouTube for \"{query[:28]}\"...\nPlease wait.",
                font_size="12sp",
                color=(1.0, 0.75, 0.0, 1.0),
                halign="center",
            )
            loading_lbl.bind(size=loading_lbl.setter("text_size"))
            loading_card.add_widget(loading_lbl)
            self.recommendations_container.add_widget(loading_card)

            def worker():
                results = []
                try:
                    import yt_dlp
                    safe_logger = AndroidYTDLLogger()
                    ydl_opts = {
                        "extract_flat": True,
                        "skip_download": True,
                        "logger": safe_logger,
                        "quiet": True,
                        "no_warnings": True,
                        "socket_timeout": 15,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        res = ydl.extract_info(f"ytsearch10:{query}", download=False)
                        if res and "entries" in res:
                            for entry in res["entries"]:
                                if not entry:
                                    continue
                                vid_id = entry.get("id")
                                vid_title = entry.get("title") or "YouTube Video"
                                vid_uploader = entry.get("uploader") or entry.get("channel") or "YouTube"
                                dur_sec = entry.get("duration")
                                vid_duration = format_duration(dur_sec) if dur_sec else "Video"
                                vid_thumb = entry.get("thumbnail") or (
                                    f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ""
                                )
                                vid_url = entry.get("url") or entry.get("webpage_url") or (
                                    f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""
                                )
                                results.append({
                                    "title": vid_title,
                                    "channel": vid_uploader,
                                    "duration": vid_duration,
                                    "url": vid_url,
                                    "thumb": vid_thumb,
                                    "category": "YouTube",
                                })
                except Exception as e:
                    print(f"[Search] YouTube search error: {e}")

                Clock.schedule_once(lambda dt, r=results, q=query: self.render_video_results(r, q))

            threading.Thread(target=worker, daemon=True).start()

        @mainthread
        def render_video_results(self, results: List[Dict[str, Any]], query: str):
            """Display live YouTube search results."""
            self.recommendations_container.clear_widgets()
            if not results:
                empty_card = StyledCard(
                    orientation="vertical",
                    padding=[dp(16), dp(16)],
                    spacing=dp(6),
                    size_hint_y=None,
                    height=dp(80),
                    bg_color=(0.08, 0.10, 0.15, 1.0),
                )
                empty_lbl = Label(
                    text=f"No results found for \"{query[:25]}\".\nCheck connection or try another search term.",
                    font_size="11.5sp",
                    color=(0.70, 0.75, 0.85, 1.0),
                    halign="center",
                )
                empty_lbl.bind(size=empty_lbl.setter("text_size"))
                empty_card.add_widget(empty_lbl)
                self.recommendations_container.add_widget(empty_card)
                return

            for item in results:
                self.add_video_result_card(item)

        def add_video_result_card(self, item: Dict[str, Any], container: Optional[BoxLayout] = None):
            """Create a video card with safe thumbnail, in-app PLAY modal, and 1-tap GET/Download popup."""
            card = StyledCard(
                orientation="horizontal",
                padding=[dp(10), dp(8)],
                spacing=dp(10),
                size_hint_y=None,
                height=dp(88),
                bg_color=(0.10, 0.12, 0.18, 1.0),
            )

            # Thumbnail with safe error fallback to prevent red cross X
            thumb_url = item.get("thumb") or ""
            thumb = AsyncImage(
                source=thumb_url,
                size_hint=(None, None),
                size=(dp(96), dp(64)),
                allow_stretch=True,
                keep_ratio=True,
            )
            def on_thumb_error(instance, *args):
                for candidate in ("icon.png", "assets/logo.png"):
                    if os.path.exists(candidate):
                        instance.source = candidate
                        break
                instance.opacity = 0.6
            thumb.bind(on_error=on_thumb_error)
            card.add_widget(thumb)

            # Info column
            info_col = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=1.0)
            clean_t = safe_display_text(item.get("title", ""))
            t_lbl = Label(
                text=f"[b]{clean_t[:42]}[/b]",
                markup=True,
                font_size="11.5sp",
                color=(0.95, 0.95, 1.0, 1.0),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(32),
            )
            t_lbl.bind(size=t_lbl.setter("text_size"))
            info_col.add_widget(t_lbl)

            channel_name = safe_display_text(item.get("channel", "YouTube"))
            dur_str = item.get("duration", "Video")
            meta_lbl = Label(
                text=f"{dur_str} • {channel_name[:22]}",
                font_size="10sp",
                color=(0.65, 0.70, 0.82, 1.0),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(16),
            )
            meta_lbl.bind(size=meta_lbl.setter("text_size"))
            info_col.add_widget(meta_lbl)
            card.add_widget(info_col)

            # Action Buttons Column: [PLAY] and [GET]
            btn_col = BoxLayout(orientation="vertical", spacing=dp(4), size_hint=(None, None), size=(dp(68), dp(68)))

            play_btn = IconActionButton(
                icon_path="play.png",
                text="PLAY",
                font_size="10.5sp",
                size_hint_y=0.5,
                bg_color=(0.18, 0.24, 0.38, 1.0),
                text_color=(0.40, 0.85, 1.0, 1.0),
            )
            def on_card_play(ins, it=item):
                dl_file = find_downloaded_media_file(title=it.get("title"), item_id=it.get("id"))
                if dl_file and dl_file.exists():
                    open_media_file(dl_file)
                else:
                    self.open_video_player_modal(it)

            play_btn.bind(on_press=on_card_play)
            btn_col.add_widget(play_btn)

            dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="GET",
                font_size="10.5sp",
                size_hint_y=0.5,
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
            )
            dl_btn.bind(on_press=lambda ins, it=item: self.open_download_modal(it))
            btn_col.add_widget(dl_btn)

            card.add_widget(btn_col)

            target_container = container if container is not None else self.recommendations_container
            target_container.add_widget(card)

        @mainthread
        def populate_recommendations(self):
            """Display curated and shuffled trending videos with permanent working thumbnails."""
            self.results_header_lbl.text = "[b]Trending & Recommended[/b]"
            self.recommendations_container.clear_widgets()

            catalog = [
                {
                    "title": "Alan Walker - Faded (Official Music Video)",
                    "channel": "Alan Walker",
                    "duration": "3:32",
                    "url": "https://www.youtube.com/watch?v=60ItHLz5WEA",
                    "thumb": "https://i.ytimg.com/vi/60ItHLz5WEA/mqdefault.jpg",
                    "category": "Music HQ",
                },
                {
                    "title": "Python Programming Full Course for Beginners",
                    "channel": "freeCodeCamp",
                    "duration": "4:26:52",
                    "url": "https://www.youtube.com/watch?v=_uQrJ0TkZlc",
                    "thumb": "https://i.ytimg.com/vi/_uQrJ0TkZlc/mqdefault.jpg",
                    "category": "Coding & Tech",
                },
                {
                    "title": "1,000 Termites vs. House (Full Documentary)",
                    "channel": "AntsCanada",
                    "duration": "12:13",
                    "url": "https://www.youtube.com/watch?v=UqmP868N59w",
                    "thumb": "https://i.ytimg.com/vi/UqmP868N59w/mqdefault.jpg",
                    "category": "Documentary",
                },
                {
                    "title": "Alan Walker - The Spectre (NCS Official)",
                    "channel": "NoCopyrightSounds",
                    "duration": "3:13",
                    "url": "https://www.youtube.com/watch?v=AOeY-nDp7hI",
                    "thumb": "https://i.ytimg.com/vi/AOeY-nDp7hI/mqdefault.jpg",
                    "category": "Gaming Music",
                },
                {
                    "title": "How to Create AI Movies & Animation with Free Tools",
                    "channel": "AI Creators",
                    "duration": "14:48",
                    "url": "https://www.youtube.com/watch?v=aircAruvnKk",
                    "thumb": "https://i.ytimg.com/vi/aircAruvnKk/mqdefault.jpg",
                    "category": "Tech & AI",
                },
                {
                    "title": "Ed Sheeran - Shape of You (Official Music Video)",
                    "channel": "Ed Sheeran",
                    "duration": "4:23",
                    "url": "https://www.youtube.com/watch?v=JGwWNGJdvx8",
                    "thumb": "https://i.ytimg.com/vi/JGwWNGJdvx8/mqdefault.jpg",
                    "category": "Pop Music",
                },
            ]

            import random
            random.shuffle(catalog)
            for item in catalog:
                self.add_video_result_card(item)

        def load_recommended_video(self, video_url: str):
            """Load a video from search/recommendations into Home tab with live preview and modal."""
            self.url_input.text = video_url
            self.switch_tab("home")
            self.fetch_preview(video_url, auto_open_modal=True)
            self.update_status("[color=#FFB300]Loaded video![/color] Select format to download.", 0)

        # -----------------------------------------------------------------
        # Home Page Search & Recommendations Logic
        # -----------------------------------------------------------------
        def on_main_download_clicked(self, instance):
            """Trigger download options modal for currently entered URL or active preview."""
            url = self.url_input.text.strip()
            if not url:
                self.update_status("[color=#FF5252]Paste a YouTube link or search first![/color]", 0)
                return
            normalized = normalize_youtube_url(url)
            if not normalized:
                self.search_youtube_home(url)
                return
            if hasattr(self, "current_preview_info") and self.current_preview_info and self.current_preview_info.get("url") == normalized:
                self.open_download_modal(self.current_preview_info)
            else:
                self.fetch_preview(normalized, auto_open_modal=True)

        def on_home_search_validate(self, instance):
            """Triggered when Enter or Search key is pressed inside Home input box."""
            self.on_home_search_clicked()

        def on_home_search_clicked(self):
            """Handle SEARCH button click on Home page."""
            query = self.url_input.text.strip()
            if not query:
                return
            normalized = normalize_youtube_url(query)
            if normalized:
                self.current_preview_url = normalized
                self.fetch_preview(normalized, auto_open_modal=True)
            else:
                self.search_youtube_home(query)

        def on_home_category_chip_clicked(self, cat_name: str, cat_query: str):
            """Filter Home discover feed by category chip."""
            for name, btn in self.home_category_chips.items():
                if name == cat_name:
                    btn.background_color = (0.20, 0.28, 0.44, 1.0)
                    btn.color = (1.0, 0.75, 0.0, 1.0)
                else:
                    btn.background_color = (0.13, 0.16, 0.23, 1.0)
                    btn.color = (0.75, 0.80, 0.90, 1.0)
            if hasattr(self, "url_input"):
                self.url_input.hint_text = f"Browsing {cat_name}... Paste link or search"
            if cat_name in ("🔥 ALL", "TRENDING"):
                self.populate_home_recommendations()
            else:
                self.search_youtube_home(cat_query, section_title=f"{cat_name} Feed")

        def search_youtube_home(self, query: str, section_title: Optional[str] = None):
            """Search YouTube and display cards directly on Home page."""
            title = section_title or f"Results for: {query[:25]}"
            self.home_results_header_lbl.text = f"[b]{title}[/b]"
            self.home_recommendations_container.clear_widgets()

            loading_card = StyledCard(
                orientation="vertical",
                padding=[dp(16), dp(14)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(70),
                bg_color=(0.08, 0.10, 0.15, 1.0),
            )
            loading_lbl = Label(
                text=f"Searching YouTube for \"{query[:28]}\"...\nPlease wait.",
                font_size="12sp",
                color=(1.0, 0.75, 0.0, 1.0),
                halign="center",
            )
            loading_lbl.bind(size=loading_lbl.setter("text_size"))
            loading_card.add_widget(loading_lbl)
            self.home_recommendations_container.add_widget(loading_card)

            def worker():
                results = []
                try:
                    import yt_dlp
                    safe_logger = AndroidYTDLLogger()
                    ydl_opts = {
                        "extract_flat": True,
                        "skip_download": True,
                        "logger": safe_logger,
                        "quiet": True,
                        "no_warnings": True,
                        "socket_timeout": 15,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        res = ydl.extract_info(f"ytsearch10:{query}", download=False)
                        if res and "entries" in res:
                            for entry in res["entries"]:
                                if not entry:
                                    continue
                                vid_id = entry.get("id")
                                vid_title = entry.get("title") or "YouTube Video"
                                vid_uploader = entry.get("uploader") or entry.get("channel") or "YouTube"
                                dur_sec = entry.get("duration")
                                vid_duration = format_duration(dur_sec) if dur_sec else "Video"
                                vid_thumb = entry.get("thumbnail") or (
                                    f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ""
                                )
                                vid_url = entry.get("url") or entry.get("webpage_url") or (
                                    f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""
                                )
                                results.append({
                                    "title": vid_title,
                                    "channel": vid_uploader,
                                    "duration": vid_duration,
                                    "url": vid_url,
                                    "thumb": vid_thumb,
                                    "category": "YouTube",
                                })
                except Exception as e:
                    print(f"[Home Search] YouTube search error: {e}")

                Clock.schedule_once(lambda dt, r=results, q=query: self.render_home_video_results(r, q))

            threading.Thread(target=worker, daemon=True).start()

        @mainthread
        def render_home_video_results(self, results: List[Dict[str, Any]], query: str):
            """Display live search results on Home page."""
            self.home_recommendations_container.clear_widgets()
            if not results:
                empty_card = StyledCard(
                    orientation="vertical",
                    padding=[dp(16), dp(16)],
                    spacing=dp(6),
                    size_hint_y=None,
                    height=dp(80),
                    bg_color=(0.08, 0.10, 0.15, 1.0),
                )
                empty_lbl = Label(
                    text=f"No results found for \"{query[:25]}\".\nCheck connection or try another search term.",
                    font_size="11.5sp",
                    color=(0.70, 0.75, 0.85, 1.0),
                    halign="center",
                )
                empty_lbl.bind(size=empty_lbl.setter("text_size"))
                empty_card.add_widget(empty_lbl)
                self.home_recommendations_container.add_widget(empty_card)
                return

            for item in results:
                self.add_video_result_card(item, container=self.home_recommendations_container)

        @mainthread
        def populate_home_recommendations(self):
            """Populate curated and trending picks on Home page."""
            if not hasattr(self, "home_recommendations_container"):
                return
            self.home_results_header_lbl.text = "[b]Trending & Recommended[/b]"
            self.home_recommendations_container.clear_widgets()

            catalog = [
                {
                    "title": "Alan Walker - Faded (Official Music Video)",
                    "channel": "Alan Walker",
                    "duration": "3:32",
                    "url": "https://www.youtube.com/watch?v=60ItHLz5WEA",
                    "thumb": "https://i.ytimg.com/vi/60ItHLz5WEA/mqdefault.jpg",
                    "category": "Music HQ",
                },
                {
                    "title": "Python Programming Full Course for Beginners",
                    "channel": "freeCodeCamp",
                    "duration": "4:26:52",
                    "url": "https://www.youtube.com/watch?v=_uQrJ0TkZlc",
                    "thumb": "https://i.ytimg.com/vi/_uQrJ0TkZlc/mqdefault.jpg",
                    "category": "Coding & Tech",
                },
                {
                    "title": "Alan Walker - The Spectre (NCS Official)",
                    "channel": "NoCopyrightSounds",
                    "duration": "3:13",
                    "url": "https://www.youtube.com/watch?v=AOeY-nDp7hI",
                    "thumb": "https://i.ytimg.com/vi/AOeY-nDp7hI/mqdefault.jpg",
                    "category": "Gaming Music",
                },
                {
                    "title": "How to Create AI Movies & Animation with Free Tools",
                    "channel": "AI Creators",
                    "duration": "14:48",
                    "url": "https://www.youtube.com/watch?v=aircAruvnKk",
                    "thumb": "https://i.ytimg.com/vi/aircAruvnKk/mqdefault.jpg",
                    "category": "Tech & AI",
                },
                {
                    "title": "Ed Sheeran - Shape of You (Official Music Video)",
                    "channel": "Ed Sheeran",
                    "duration": "4:23",
                    "url": "https://www.youtube.com/watch?v=JGwWNGJdvx8",
                    "thumb": "https://i.ytimg.com/vi/JGwWNGJdvx8/mqdefault.jpg",
                    "category": "Pop Music",
                },
                {
                    "title": "1,000 Termites vs. House (Full Documentary)",
                    "channel": "AntsCanada",
                    "duration": "12:13",
                    "url": "https://www.youtube.com/watch?v=UqmP868N59w",
                    "thumb": "https://i.ytimg.com/vi/UqmP868N59w/mqdefault.jpg",
                    "category": "Documentary",
                },
            ]
            import random
            random.shuffle(catalog)
            for item in catalog:
                self.add_video_result_card(item, container=self.home_recommendations_container)

        # -----------------------------------------------------------------
        # In-App Video Player & Download Options Modals
        # -----------------------------------------------------------------
        def open_video_player_modal(self, media_item: Optional[Dict[str, Any]] = None):
            """
            In-App Video Player modal allowing video preview and instant launch in YouTube Player.
            """
            if not media_item:
                return

            modal = ModalView(size_hint=(0.94, None), height=dp(465), auto_dismiss=True)
            content = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(10),
                bg_color=(0.08, 0.10, 0.16, 0.98),
                radius=16,
            )

            # Header row: Icon + Title + Close [X]
            header_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(30))
            play_icon_path = get_asset_icon("play.png")
            if play_icon_path:
                header_row.add_widget(
                    Image(source=play_icon_path, size_hint=(None, None), size=(dp(22), dp(22)), allow_stretch=True, keep_ratio=True)
                )
            player_title = Label(
                text="[b]In-App Video Player[/b]",
                markup=True,
                font_size="14sp",
                color=(1.0, 0.75, 0.0, 1.0),
                halign="left",
                valign="middle",
                size_hint_x=1.0,
            )
            player_title.bind(size=player_title.setter("text_size"))
            header_row.add_widget(player_title)

            close_x = Button(
                text="✕",
                font_size="16sp",
                bold=True,
                size_hint=(None, None),
                size=(dp(30), dp(30)),
                background_color=(0.20, 0.22, 0.30, 1.0),
                color=(1, 1, 1, 1),
            )
            close_x.bind(on_press=modal.dismiss)
            header_row.add_widget(close_x)
            content.add_widget(header_row)

            # Video Title & Details
            raw_title = media_item.get("title") or "YouTube Video"
            clean_title = safe_display_text(raw_title)

            # Check if media item has already been downloaded offline
            downloaded_file = find_downloaded_media_file(
                title=clean_title,
                item_id=media_item.get("id")
            )

            # Thumbnail & Player Display Box (Tap to play directly)
            player_box = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(170),
            )
            thumb_url = media_item.get("thumb") or ""
            thumb_img = AsyncImage(
                source=thumb_url,
                size_hint=(1.0, 1.0),
                allow_stretch=True,
                keep_ratio=True,
            )
            def on_pthumb_error(instance, *args):
                for candidate in ("icon.png", "assets/logo.png"):
                    if os.path.exists(candidate):
                        instance.source = candidate
                        break
                instance.opacity = 0.7
            thumb_img.bind(on_error=on_pthumb_error)
            player_box.add_widget(thumb_img)

            # Tap thumbnail to play in device player if downloaded, else in-app online
            def on_thumb_click(instance, touch):
                if instance.collide_point(*touch.pos):
                    if downloaded_file and downloaded_file.exists():
                        modal.dismiss()
                        is_aud = downloaded_file.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac")
                        if is_aud:
                            self.play_audio_track(downloaded_file)
                        else:
                            self.play_video_file(downloaded_file)
                    else:
                        play_online_video(media_item.get("url", ""), title=clean_title)
                    return True
                return False
            player_box.bind(on_touch_down=on_thumb_click)
            content.add_widget(player_box)

            t_lbl = Label(
                text=f"[b]{clean_title}[/b]",
                markup=True,
                font_size="12.5sp",
                color=(1.0, 1.0, 1.0, 1.0),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(34),
                shorten=True,
                shorten_from="right",
            )
            t_lbl.bind(size=t_lbl.setter("text_size"))
            content.add_widget(t_lbl)

            channel_name = safe_display_text(media_item.get("channel", "YouTube"))
            dur_str = media_item.get("duration", "Video")
            meta_lbl = Label(
                text=f"[color=#FFB300]Duration:[/color] {dur_str}   •   [color=#81D4FA]{channel_name[:25]}[/color]",
                markup=True,
                font_size="11sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(18),
            )
            meta_lbl.bind(size=meta_lbl.setter("text_size"))
            content.add_widget(meta_lbl)

            # Player Action Buttons: [▶ PLAY NOW] + [🎧 PLAY IN BACKGROUND] + [⬇ DOWNLOAD / CLOSE]
            btn_col = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(130))

            if downloaded_file and downloaded_file.exists():
                is_aud = downloaded_file.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac")
                btn_txt = "▶ PLAY OFFLINE (AUDIO)" if is_aud else "▶ PLAY OFFLINE (VIDEO)"
                play_inapp_btn = IconActionButton(
                    icon_path="play.png",
                    text=btn_txt,
                    bg_color=(0.08, 0.55, 0.25, 1.0),
                    text_color=(1, 1, 1, 1),
                    font_size="11.5sp",
                    size_hint_y=None,
                    height=dp(38),
                )
                def on_modal_play_offline(ins, f=downloaded_file, aud=is_aud):
                    modal.dismiss()
                    if aud:
                        self.play_audio_track(f)
                    else:
                        self.play_video_file(f)
                play_inapp_btn.bind(on_press=on_modal_play_offline)
            else:
                play_inapp_btn = IconActionButton(
                    icon_path="play.png",
                    text="▶ PLAY NOW (ONLINE)",
                    bg_color=(0.12, 0.55, 0.95, 1.0),
                    text_color=(1, 1, 1, 1),
                    font_size="12sp",
                    size_hint_y=None,
                    height=dp(38),
                )
                play_inapp_btn.bind(on_press=lambda ins, u=media_item.get("url", ""), t=clean_title: play_online_video(u, title=t))
            btn_col.add_widget(play_inapp_btn)

            bg_audio_btn = IconActionButton(
                icon_path="music.png",
                text="🎧 PLAY IN BACKGROUND (SCREEN-OFF MODE)",
                bg_color=(0.16, 0.65, 0.38, 1.0),
                text_color=(1, 1, 1, 1),
                font_size="11sp",
                size_hint_y=None,
                height=dp(38),
            )
            def on_bg_audio_click(ins):
                modal.dismiss()
                self.play_audio_in_background(media_item)
            bg_audio_btn.bind(on_press=on_bg_audio_click)
            btn_col.add_widget(bg_audio_btn)

            dl_action_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
            dl_opts_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="DOWNLOAD OPTIONS",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.05, 0.07, 0.12, 1.0),
                font_size="11.5sp",
                size_hint_x=0.7,
            )
            def on_dl_from_player(ins):
                modal.dismiss()
                self.open_download_modal(media_item)
            dl_opts_btn.bind(on_press=on_dl_from_player)
            dl_action_row.add_widget(dl_opts_btn)

            close_btn = IconActionButton(
                icon_path="clear.png",
                text="CLOSE",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.80, 0.85, 0.95, 1.0),
                font_size="11.5sp",
                size_hint_x=0.3,
            )
            close_btn.bind(on_press=modal.dismiss)
            dl_action_row.add_widget(close_btn)

            btn_col.add_widget(dl_action_row)
            content.add_widget(btn_col)

            modal.add_widget(content)
            modal.open()

        def open_download_modal(self, media_item: Optional[Dict[str, Any]] = None):
            """
            Open interactive Download Pop-up Modal allowing format and audio/video selection.
            Defaults to 1080p Full HD MP4.
            """
            if not media_item:
                if hasattr(self, "current_preview_info") and self.current_preview_info:
                    media_item = dict(self.current_preview_info)
                else:
                    url = self.url_input.text.strip()
                    if not url:
                        self.update_status("[color=#FF5252]Paste a YouTube link or search first![/color]", 0)
                        return
                    media_item = {
                        "title": "YouTube Media",
                        "url": normalize_youtube_url(url) or url,
                        "thumb": "",
                        "channel": "YouTube",
                        "duration": "Media",
                        "is_playlist": "playlist" in url.lower() or "list=" in url.lower(),
                        "count": 1,
                    }

            is_plist = bool(media_item.get("is_playlist", False) or "playlist" in media_item.get("url", "").lower() or "list=" in media_item.get("url", "").lower())
            count = media_item.get("count", 1)

            modal = ModalView(size_hint=(0.94, 0.84), auto_dismiss=True)
            content = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(10),
                bg_color=(0.08, 0.10, 0.16, 0.98),
                radius=16,
            )

            # Header Row
            header_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(30))
            dl_icon_path = get_asset_icon("download_arrow.png")
            if dl_icon_path:
                header_row.add_widget(
                    Image(source=dl_icon_path, size_hint=(None, None), size=(dp(22), dp(22)), allow_stretch=True, keep_ratio=True)
                )
            m_title = Label(
                text="[b]Select Download Format[/b]" if not is_plist else f"[b]Download Playlist ({count} Videos)[/b]",
                markup=True,
                font_size="14sp",
                color=(1.0, 0.75, 0.0, 1.0),
                halign="left",
                valign="middle",
                size_hint_x=1.0,
            )
            m_title.bind(size=m_title.setter("text_size"))
            header_row.add_widget(m_title)

            close_x = Button(
                text="✕",
                font_size="16sp",
                bold=True,
                size_hint=(None, None),
                size=(dp(30), dp(30)),
                background_color=(0.20, 0.22, 0.30, 1.0),
                color=(1, 1, 1, 1),
            )
            close_x.bind(on_press=modal.dismiss)
            header_row.add_widget(close_x)
            content.add_widget(header_row)

            # Media Info Mini Card
            mini_card = StyledCard(
                orientation="horizontal",
                padding=[dp(8), dp(6)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(58),
                bg_color=(0.11, 0.14, 0.22, 1.0),
            )
            m_thumb = AsyncImage(
                source=media_item.get("thumb") or "",
                size_hint=(None, None),
                size=(dp(76), dp(46)),
                allow_stretch=True,
                keep_ratio=True,
            )
            def on_mthumb_error(ins, *args):
                for candidate in ("icon.png", "assets/logo.png"):
                    if os.path.exists(candidate):
                        ins.source = candidate
                        break
            m_thumb.bind(on_error=on_mthumb_error)
            mini_card.add_widget(m_thumb)

            minfo_col = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=1.0)
            raw_t = media_item.get("title") or "YouTube Media"
            m_tlbl = Label(
                text=f"[b]{safe_display_text(raw_t)[:48]}[/b]",
                markup=True,
                font_size="11.5sp",
                color=(1, 1, 1, 1),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(26),
            )
            m_tlbl.bind(size=m_tlbl.setter("text_size"))
            minfo_col.add_widget(m_tlbl)

            uploader_str = safe_display_text(media_item.get("channel") or media_item.get("uploader") or "YouTube")
            type_tag = f"[color=#FFB300]PLAYLIST ({count} videos)[/color]" if is_plist else f"[color=#38BDF8]VIDEO[/color] • {media_item.get('duration', 'Media')}"
            m_sublbl = Label(
                text=f"{type_tag} • {uploader_str[:22]}",
                markup=True,
                font_size="10sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(16),
            )
            m_sublbl.bind(size=m_sublbl.setter("text_size"))
            minfo_col.add_widget(m_sublbl)
            mini_card.add_widget(minfo_col)
            content.add_widget(mini_card)

            # Scrollable Options List
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, size_hint_y=1.0)
            opts_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
            opts_box.bind(minimum_height=opts_box.setter("height"))

            selected_state = {"format": "Video (Max Quality - 1080p / 720p HD)"}
            option_cards: Dict[str, Any] = {}

            def on_option_picked(key):
                selected_state["format"] = key
                for k, c in option_cards.items():
                    c.set_selected(k == key)
                if is_plist and "update_sel_ui" in locals():
                    update_sel_ui()

            if is_plist:
                raw_entries = list(media_item.get("entries") or [])
                entries = [e for e in raw_entries if e]
                total_entries = len(entries) if entries else count

                # 1. Format Selection Header
                fmt_sec_lbl = Label(
                    text="[b][color=#FFB300]1. CHOOSE PLAYLIST FORMAT[/color][/b]",
                    markup=True,
                    font_size="11sp",
                    size_hint_y=None,
                    height=dp(20),
                    halign="left",
                )
                fmt_sec_lbl.bind(size=fmt_sec_lbl.setter("text_size"))
                opts_box.add_widget(fmt_sec_lbl)

                plist_options = [
                    ("Video (Max Quality - 1080p / 720p HD)", "1080p Full HD MP4", "High Definition Video (1920x1080)", "1080p HD"),
                    ("Video (720p HD MP4)", "720p HD MP4", "Standard High Definition (1280x720)", "720p HD"),
                    ("Video (360p Fast MP4)", "360p Fast MP4", "Compact file size, data saver", "360p"),
                    ("Audio Only (HQ MP3 Music + Album Art)", "HQ MP3 (320kbps + Album Art)", "Studio quality music with cover & ID3 tags", "MP3 320k"),
                    ("Audio Only (M4A AAC Fast)", "M4A AAC Fast Audio", "Fast AAC audio stream", "M4A AAC"),
                ]
                for key, title, sub, badge in plist_options:
                    is_sel = (key == selected_state["format"])
                    c = FormatOptionCard(key, title, sub, badge, is_selected=is_sel, on_select_cb=on_option_picked)
                    option_cards[key] = c
                    opts_box.add_widget(c)

                # 2. Item Selection Header (Select All / Clear All & Counter)
                items_sec_lbl = Label(
                    text="[b][color=#38BDF8]2. SELECT VIDEOS TO DOWNLOAD[/color][/b]",
                    markup=True,
                    font_size="11sp",
                    size_hint_y=None,
                    height=dp(24),
                    halign="left",
                )
                items_sec_lbl.bind(size=items_sec_lbl.setter("text_size"))
                opts_box.add_widget(items_sec_lbl)

                sel_header = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(32))
                sel_count_lbl = Label(
                    text=f"[b]Selected: {total_entries} of {total_entries}[/b]",
                    markup=True,
                    font_size="11.5sp",
                    color=(0.95, 0.95, 1.0, 1.0),
                    halign="left",
                    valign="middle",
                    size_hint_x=1.0,
                )
                sel_count_lbl.bind(size=sel_count_lbl.setter("text_size"))
                sel_header.add_widget(sel_count_lbl)

                sel_all_btn = IconActionButton(
                    text="✔ ALL",
                    font_size="10.5sp",
                    size_hint=(None, None),
                    size=(dp(72), dp(30)),
                    bg_color=(0.12, 0.45, 0.22, 1.0),
                    text_color=(1, 1, 1, 1),
                )
                sel_header.add_widget(sel_all_btn)

                clear_all_btn = IconActionButton(
                    icon_path="clear.png",
                    text="CLEAR",
                    font_size="10.5sp",
                    size_hint=(None, None),
                    size=(dp(76), dp(30)),
                    bg_color=(0.28, 0.12, 0.15, 1.0),
                    text_color=(1, 0.8, 0.8, 1),
                )
                sel_header.add_widget(clear_all_btn)
                opts_box.add_widget(sel_header)

                # Items checklist
                selected_map = {i: True for i in range(total_entries)}
                row_widgets = []

                def update_sel_ui():
                    num_sel = sum(1 for v in selected_map.values() if v)
                    sel_count_lbl.text = f"[b]Selected: {num_sel} of {total_entries}[/b]"
                    is_audio = "Audio" in selected_state["format"]
                    noun = "TRACKS" if is_audio else "VIDEOS"
                    if num_sel > 0:
                        start_dl_btn.text = f"DOWNLOAD SELECTED ({num_sel} {noun})"
                        start_dl_btn.disabled = False
                        start_dl_btn.set_bg_color((1.0, 0.68, 0.0, 1.0))
                    else:
                        start_dl_btn.text = "SELECT AT LEAST 1 ITEM"
                        start_dl_btn.disabled = True
                        start_dl_btn.set_bg_color((0.25, 0.25, 0.30, 1.0))

                def on_item_toggle(item_idx, is_chk):
                    selected_map[item_idx] = is_chk
                    update_sel_ui()

                def on_select_all_pressed(ins):
                    for k in selected_map:
                        selected_map[k] = True
                    for rw in row_widgets:
                        rw.set_checked(True)
                    update_sel_ui()

                def on_clear_all_pressed(ins):
                    for k in selected_map:
                        selected_map[k] = False
                    for rw in row_widgets:
                        rw.set_checked(False)
                    update_sel_ui()

                sel_all_btn.bind(on_press=on_select_all_pressed)
                clear_all_btn.bind(on_press=on_clear_all_pressed)

                if entries:
                    for i, entry in enumerate(entries):
                        dur = format_duration(entry.get("duration")) if entry.get("duration") else ""
                        item_t = entry.get("title") or f"Playlist Video #{i+1}"
                        row_w = PlaylistItemRow(
                            index=i + 1,
                            title=item_t,
                            duration=dur,
                            is_checked=True,
                            on_toggle_cb=on_item_toggle,
                        )
                        row_widgets.append(row_w)
                        opts_box.add_widget(row_w)
                else:
                    empty_hint = Label(
                        text="[color=#90CAF9]Extracting playlist items... All videos will be included.[/color]",
                        markup=True,
                        font_size="11sp",
                        size_hint_y=None,
                        height=dp(30),
                        halign="left",
                    )
                    empty_hint.bind(size=empty_hint.setter("text_size"))
                    opts_box.add_widget(empty_hint)
            else:
                # Video formats header
                v_sec_lbl = Label(
                    text="[b][color=#38BDF8]VIDEO FORMATS (MP4)[/color][/b]",
                    markup=True,
                    font_size="11sp",
                    size_hint_y=None,
                    height=dp(20),
                    halign="left",
                )
                v_sec_lbl.bind(size=v_sec_lbl.setter("text_size"))
                opts_box.add_widget(v_sec_lbl)

                video_options = [
                    ("Video (Max Quality - 1080p / 720p HD)", "1080p Full HD MP4", "Highest visual clarity (1920x1080)", "1080p HD"),
                    ("Video (720p HD MP4)", "720p HD MP4", "High Definition MP4 (1280x720)", "720p HD"),
                    ("Video (360p Fast MP4)", "360p Fast MP4", "Lightweight file, data saver mode", "360p"),
                ]
                for key, title, sub, badge in video_options:
                    is_sel = (key == "Video (Max Quality - 1080p / 720p HD)")
                    c = FormatOptionCard(key, title, sub, badge, is_selected=is_sel, on_select_cb=on_option_picked)
                    option_cards[key] = c
                    opts_box.add_widget(c)

                # Audio formats header
                a_sec_lbl = Label(
                    text="[b][color=#FFB300]AUDIO FORMATS (MP3 / M4A)[/color][/b]",
                    markup=True,
                    font_size="11sp",
                    size_hint_y=None,
                    height=dp(22),
                    halign="left",
                )
                a_sec_lbl.bind(size=a_sec_lbl.setter("text_size"))
                opts_box.add_widget(a_sec_lbl)

                audio_options = [
                    ("Audio Only (HQ MP3 Music + Album Art)", "HQ MP3 (320kbps + Album Art)", "Studio quality music with embedded ID3 tags & cover", "MP3 320k"),
                    ("Audio Only (M4A AAC Fast)", "M4A AAC Fast Audio", "Fast AAC audio direct stream", "M4A AAC"),
                ]
                for key, title, sub, badge in audio_options:
                    c = FormatOptionCard(key, title, sub, badge, is_selected=False, on_select_cb=on_option_picked)
                    option_cards[key] = c
                    opts_box.add_widget(c)

            scroll.add_widget(opts_box)
            content.add_widget(scroll)

            # Bottom Action Buttons
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))

            start_dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text=f"DOWNLOAD PLAYLIST ({total_entries} VIDEOS)" if is_plist else "START DOWNLOAD",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                font_size="12sp",
                size_hint_x=0.7,
            )
            def on_start_clicked(ins):
                fmt = selected_state["format"]
                modal.dismiss()
                target_url = media_item.get("url")
                if target_url:
                    self.url_input.text = target_url

                if hasattr(self, "quality_spinner"):
                    self.quality_spinner.text = fmt

                chosen_indices = None
                if is_plist and "selected_map" in locals():
                    chosen_indices = [k for k, v in selected_map.items() if v]

                self.start_download(
                    target_url=target_url,
                    chosen_format=fmt,
                    is_playlist=is_plist,
                    selected_indices=chosen_indices,
                    entries=entries if is_plist and entries else None,
                )

            start_dl_btn.bind(on_press=on_start_clicked)
            btn_row.add_widget(start_dl_btn)

            cancel_btn = IconActionButton(
                icon_path="clear.png",
                text="CANCEL",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.80, 0.85, 0.95, 1.0),
                font_size="12sp",
                size_hint_x=0.3,
            )
            cancel_btn.bind(on_press=modal.dismiss)
            btn_row.add_widget(cancel_btn)

            content.add_widget(btn_row)
            modal.add_widget(content)
            modal.open()

        # -----------------------------------------------------------------
        # Clipboard Auto-Detect Logic
        # -----------------------------------------------------------------
        def check_clipboard(self, dt=None):
            """Poll clipboard safely if enabled; if YouTube URL found and not already loaded, show banner."""
            if not getattr(self, "clipboard_detection_enabled", True):
                return
            try:
                clip = Clipboard.paste()
                if clip and clip != self.last_clipboard_text:
                    normalized = normalize_youtube_url(clip.strip())
                    if normalized and normalized != self.url_input.text.strip():
                        self.last_clipboard_text = clip
                        self.detected_clipboard_url = normalized
                        self.clipboard_banner.height = dp(34)
                        self.clipboard_banner.opacity = 1.0
                        return
                if not clip or (clip == self.url_input.text.strip()):
                    self.clipboard_banner.height = 0
                    self.clipboard_banner.opacity = 0.0
            except Exception:
                pass

        def on_clipboard_banner_clicked(self, instance):
            """User tapped the clipboard prompt banner; auto-paste and load preview."""
            if hasattr(self, "detected_clipboard_url") and self.detected_clipboard_url:
                self.url_input.text = self.detected_clipboard_url
                self.clipboard_banner.height = 0
                self.clipboard_banner.opacity = 0.0
                self.update_status("[color=#00E676]Link loaded from clipboard![/color] Tap DOWNLOAD NOW.", 0)

        def on_paste_clicked(self, instance):
            """Handle PASTE button press from Android system clipboard."""
            try:
                clip_text = Clipboard.paste()
                if clip_text:
                    normalized = normalize_youtube_url(clip_text.strip()) or clip_text.strip()
                    self.url_input.text = normalized
                    self.clipboard_banner.height = 0
                    self.clipboard_banner.opacity = 0.0
                    self.update_status("[color=#FFB300]Link pasted![/color] Fetching video details...", 0)
                else:
                    self.update_status("Clipboard is empty.", 0)
            except Exception as e:
                self.update_status(f"Paste notice: {e}", 0)

        def on_clear_clicked(self, instance):
            """Clear input, preview card, and reset status."""
            self.url_input.text = ""
            self.current_preview_url = ""
            self.current_preview_info = None
            self.download_btn.text = "DOWNLOAD NOW"
            self.preview_card.height = 0
            self.preview_card.opacity = 0.0
            self.clipboard_banner.height = 0
            self.clipboard_banner.opacity = 0.0
            self.update_status("Ready. Paste video/playlist link or search above.", 0)
            self.populate_home_recommendations()

        def on_url_input_changed(self, instance, text):
            """Trigger real-time preview when user pastes or edits a valid YouTube link."""
            clean = text.strip()
            normalized = normalize_youtube_url(clean)
            if normalized and normalized != self.current_preview_url:
                self.current_preview_url = normalized
                self.fetch_preview(normalized, auto_open_modal=False)

        def fetch_preview(self, url: str, auto_open_modal: bool = False):
            """Fetch video or playlist thumbnail and details in a background thread with multi-platform support."""
            def preview_worker():
                try:
                    import yt_dlp
                    safe_logger = AndroidYTDLLogger()
                    plat = detect_media_platform(url)

                    ydl_opts = {
                        "extract_flat": "in_playlist",
                        "skip_download": True,
                        "logger": safe_logger,
                        "socket_timeout": 18,
                        "quiet": True,
                        "no_warnings": True,
                    }

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            return

                        is_playlist = info.get("_type") == "playlist" or "entries" in info
                        raw_title = info.get("title") or f"{plat} Media"
                        clean_title = safe_display_text(raw_title)
                        uploader = safe_display_text(info.get("uploader") or info.get("channel") or plat)
                        thumb = info.get("thumbnail") or ""

                        if is_playlist:
                            raw_entries = list(info.get("entries") or [])
                            entries = [e for e in raw_entries if e]
                            count = len(entries)
                            meta_str = f"Playlist ({count} videos) • {uploader}"
                            dur_str = f"{count} Videos"
                            if entries and not thumb:
                                first_entry = entries[0]
                                if first_entry:
                                    thumb = first_entry.get("thumbnail") or (
                                        f"https://i.ytimg.com/vi/{first_entry.get('id')}/mqdefault.jpg" if first_entry.get("id") else ""
                                    )
                            btn_text = f"DOWNLOAD PLAYLIST ({count} VIDEOS)" if count > 1 else "DOWNLOAD NOW"
                        else:
                            entries = []
                            count = 1
                            dur_str = format_duration(info.get("duration"))
                            plat_tag = f"[color=#FFB300]{plat.upper()}[/color]" if plat != "YouTube" else f"[color=#38BDF8]VIDEO[/color]"
                            meta_str = f"{plat_tag} • {dur_str} • {uploader}"
                            btn_text = "DOWNLOAD NOW"

                        self.current_preview_info = {
                            "title": clean_title,
                            "url": url,
                            "thumb": thumb,
                            "channel": uploader,
                            "uploader": uploader,
                            "duration": dur_str,
                            "is_playlist": is_playlist,
                            "count": count,
                            "entries": entries,
                            "platform": plat,
                        }

                        Clock.schedule_once(
                            lambda dt, t=clean_title, m=meta_str, th=thumb, b=btn_text: self.update_preview_ui(t, m, th, b)
                        )
                        if auto_open_modal:
                            Clock.schedule_once(lambda dt: self.open_download_modal(self.current_preview_info), 0.2)
                except Exception as e:
                    print(f"[Preview] Fetch notice: {e}")
                    plat = detect_media_platform(url)
                    self.current_preview_info = {
                        "title": f"{plat} Media",
                        "url": url,
                        "thumb": "",
                        "channel": plat,
                        "uploader": plat,
                        "duration": "Media",
                        "is_playlist": "playlist" in url.lower() or "list=" in url.lower(),
                        "count": 1,
                        "entries": [],
                        "platform": plat,
                    }
                    Clock.schedule_once(
                        lambda dt: self.update_preview_ui(f"{plat} Media", "Ready to download", "", "DOWNLOAD NOW")
                    )
                    if auto_open_modal:
                        Clock.schedule_once(lambda dt: self.open_download_modal(self.current_preview_info), 0.2)

            threading.Thread(target=preview_worker, daemon=True).start()

        @mainthread
        def update_preview_ui(self, title: str, meta: str, thumb_url: str, btn_text: str = "DOWNLOAD NOW"):
            """Update the preview card on the main Kivy UI thread."""
            clean_title = title if len(title) <= 55 else title[:52] + "..."
            self.preview_title.text = f"[b]{clean_title}[/b]"
            self.preview_meta.text = meta
            self.download_btn.text = btn_text

            # Bind safe thumbnail fallback so missing thumbnail never renders red cross
            def on_preview_thumb_error(instance, *args):
                for candidate in ("icon.png", "assets/logo.png"):
                    if os.path.exists(candidate):
                        instance.source = candidate
                        break
                instance.opacity = 0.6
            self.preview_thumb.bind(on_error=on_preview_thumb_error)

            if thumb_url:
                self.preview_thumb.source = thumb_url
                self.preview_thumb.opacity = 1.0
            else:
                for candidate in ("icon.png", "assets/logo.png"):
                    if os.path.exists(candidate):
                        self.preview_thumb.source = candidate
                        self.preview_thumb.opacity = 0.6
                        break

            self.preview_card.height = dp(84)
            self.preview_card.opacity = 1.0

        # -----------------------------------------------------------------
        # Android YouTube Share Intent Listeners
        # -----------------------------------------------------------------
        @mainthread
        def on_new_intent(self, intent):
            """Handle warm-start SEND intent when sharing from YouTube while app is open."""
            try:
                self.handle_intent_payload(intent)
            except Exception as e:
                print(f"[Android] Error in on_new_intent: {e}")

        def check_initial_intent(self, dt=None):
            """Handle cold-start SEND intent when app was launched directly from YouTube Share."""
            try:
                from jnius import autoclass
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                activity = PythonActivity.mActivity
                if activity:
                    intent = activity.getIntent()
                    if intent:
                        self.handle_intent_payload(intent)
            except Exception as e:
                print(f"[Android] Initial intent notice: {e}")

        def handle_intent_payload(self, intent):
            """Extract and populate YouTube URL from an Android Intent."""
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")

                action = intent.getAction()
                type_ = intent.getType()

                # Case 1: SEND Intent from YouTube Share button
                if action == Intent.ACTION_SEND and type_ and "text" in type_:
                    shared_text = intent.getStringExtra(Intent.EXTRA_TEXT)
                    if shared_text:
                        normalized = normalize_youtube_url(shared_text)
                        if normalized:
                            self.switch_tab("home")
                            self.url_input.text = normalized
                            self.update_status(
                                "[color=#00E676]Received from YouTube![/color] Tap DOWNLOAD NOW.", 0
                            )
                            return

                # Case 2: VIEW Intent (User clicked YouTube link)
                if action == Intent.ACTION_VIEW:
                    data = intent.getData()
                    if data:
                        normalized = normalize_youtube_url(data.toString())
                        if normalized:
                            self.switch_tab("home")
                            self.url_input.text = normalized
                            self.update_status(
                                "[color=#00E676]Received YouTube link![/color] Tap DOWNLOAD NOW.", 0
                            )
            except Exception as e:
                print(f"[Android] handle_intent_payload error: {e}")

        def update_status(self, text: str, progress_val: Optional[float] = None):
            if hasattr(self, "status_label") and self.status_label:
                self.status_label.text = text
            if progress_val is not None and hasattr(self, "progress_bar") and self.progress_bar:
                self.progress_bar.value = progress_val

        # -----------------------------------------------------------------
        # Offline Library Manager Logic (Downloads Tab)
        # -----------------------------------------------------------------
        @mainthread
        def refresh_library(self):
            """Scan download folder and populate the offline library card with Play and Delete actions."""
            try:
                self.library_container.clear_widgets()
                target_dir = get_android_download_dir()
                if not target_dir.exists():
                    target_dir.mkdir(parents=True, exist_ok=True)

                search_dirs = [target_dir]
                if is_running_on_android():
                    try:
                        from jnius import autoclass
                        PythonActivity = autoclass("org.kivy.android.PythonActivity")
                        Environment = autoclass("android.os.Environment")
                        ctx = PythonActivity.mActivity
                        if ctx:
                            ext_d = ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                            if ext_d:
                                p_d = Path(ext_d.getAbsolutePath())
                                if p_d.exists() and p_d not in search_dirs:
                                    search_dirs.append(p_d)
                    except Exception:
                        pass
                    for std_dir in ("/storage/emulated/0/Download", "/storage/emulated/0/Movies", "/storage/emulated/0/Music", "/sdcard/Download"):
                        sp = Path(std_dir)
                        if sp.exists() and sp not in search_dirs:
                            search_dirs.append(sp)

                # Scan media files
                scanned_names = set()
                all_files: List[Path] = []
                media_exts = ("*.mp4", "*.m4a", "*.mp3", "*.mkv", "*.webm", "*.wav", "*.ogg", "*.opus", "*.flac", "*.avi", "*.mov")
                for d in search_dirs:
                    if d and d.exists():
                        for ext in media_exts:
                            for p in d.glob(ext):
                                if p.is_file() and not p.name.endswith(".part") and not p.name.endswith(".ytdl"):
                                    if p.name not in scanned_names:
                                        scanned_names.add(p.name)
                                        all_files.append(p)

                # Sort newest first
                all_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

                # Update bottom nav badge
                self.nav_btn_downloads.text = f"DOWNLOADS ({len(all_files)})"

                # Apply active filter
                if self.active_filter == "videos":
                    media_files = [p for p in all_files if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".3gp")]
                elif self.active_filter == "audio":
                    media_files = [p for p in all_files if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac")]
                else:
                    media_files = all_files

                if hasattr(self, "downloads_title_lbl"):
                    self.downloads_title_lbl.text = f"[b]Downloaded Media ({len(media_files)})[/b]"

                if not media_files:
                    empty_card = StyledCard(
                        orientation="vertical",
                        padding=[dp(16), dp(18)],
                        spacing=dp(8),
                        size_hint_y=None,
                        height=dp(94),
                        bg_color=(0.08, 0.10, 0.15, 1.0),
                    )
                    empty_lbl = Label(
                        text="No downloaded files found in this category.\nVideos downloaded from Home will appear here!",
                        font_size="11.5sp",
                        color=(0.60, 0.65, 0.75, 1.0),
                        halign="center",
                    )
                    empty_lbl.bind(size=empty_lbl.setter("text_size"))
                    empty_card.add_widget(empty_lbl)
                    self.library_container.add_widget(empty_card)
                    return

                # Render each downloaded item
                for media_path in media_files[:100]:
                    size_bytes = media_path.stat().st_size if media_path.exists() else 0
                    size_str = format_bytes(size_bytes)
                    is_audio_file = media_path.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac")
                    tag_str = "[AUDIO]" if is_audio_file else "[VIDEO]"
                    tag_color = "#FFA000" if is_audio_file else "#00E676"
                    player_mode_str = "Mini Music Player" if is_audio_file else "In-App Video Player"

                    row = StyledCard(
                        orientation="horizontal",
                        padding=[dp(10), dp(6)],
                        spacing=dp(8),
                        size_hint_y=None,
                        height=dp(58),
                        bg_color=(0.10, 0.12, 0.18, 1.0),
                    )

                    clean_name = safe_display_text(media_path.stem)

                    item_lbl = Label(
                        text=f"[b][color={tag_color}]{tag_str}[/color] {clean_name}[/b]\n[size=10sp][color=#90CAF9]{size_str}[/color] • [color=#78909C]{media_path.suffix.upper()}[/color] • [color=#81D4FA]{player_mode_str}[/color][/size]",
                        markup=True,
                        font_size="11.5sp",
                        color=(0.92, 0.94, 0.98, 1.0),
                        size_hint_x=1.0,
                        halign="left",
                        valign="middle",
                        shorten=True,
                        shorten_from="right",
                    )
                    item_lbl.bind(size=item_lbl.setter("text_size"))
                    def on_item_click(instance, touch, p=media_path, is_aud=is_audio_file):
                        if instance.collide_point(*touch.pos):
                            if is_aud:
                                self.play_audio_track(p)
                            else:
                                self.play_video_file(p)
                            return True
                        return False
                    item_lbl.bind(on_touch_down=on_item_click)
                    row.add_widget(item_lbl)

                    # PLAY BUTTON with icon - Plays audio in mini player, videos in native video player
                    if is_audio_file:
                        play_btn = IconActionButton(
                            icon_path="play.png",
                            text="PLAY",
                            font_size="11sp",
                            size_hint=(None, None),
                            size=(dp(72), dp(34)),
                            bg_color=(0.10, 0.55, 0.28, 1.0),
                            text_color=(1, 1, 1, 1),
                        )
                        play_btn.bind(on_press=lambda ins, p=media_path: self.play_audio_track(p))
                    else:
                        play_btn = IconActionButton(
                            icon_path="play.png",
                            text="PLAY",
                            font_size="11sp",
                            size_hint=(None, None),
                            size=(dp(72), dp(34)),
                            bg_color=(0.08, 0.50, 0.24, 1.0),
                            text_color=(1, 1, 1, 1),
                        )
                        play_btn.bind(on_press=lambda ins, p=media_path: self.play_video_file(p))
                    row.add_widget(play_btn)

                    # DELETE BUTTON with icon
                    del_btn = IconActionButton(
                        icon_path="delete.png",
                        text="DEL",
                        font_size="11sp",
                        size_hint=(None, None),
                        size=(dp(64), dp(34)),
                        bg_color=(0.60, 0.12, 0.12, 1.0),
                        text_color=(1, 1, 1, 1),
                    )
                    del_btn.bind(on_press=lambda ins, p=media_path, r=row: self.on_delete_clicked(p, r))
                    row.add_widget(del_btn)

                    self.library_container.add_widget(row)

            except Exception as e:
                print(f"[Library] Refresh error: {e}")

        def on_delete_clicked(self, file_path: Path, row_widget: Optional[Any] = None):
            """Delete file from device and refresh list with instant visual feedback."""
            # Immediate UI removal so user sees instant response
            if row_widget and row_widget in self.library_container.children:
                self.library_container.remove_widget(row_widget)

            def async_delete():
                success = delete_media_file(file_path)
                Clock.schedule_once(lambda dt: self.refresh_library(), 0.15)
                clean_deleted_name = safe_display_text(file_path.name)
                if success:
                    Clock.schedule_once(
                        lambda dt, n=clean_deleted_name: self.update_status(f"[color=#00E676]Deleted:[/color] {n}", 0)
                    )
                else:
                    Clock.schedule_once(
                        lambda dt, n=clean_deleted_name: self.update_status(f"[color=#FFB300]Removed from list:[/color] {n}", 0)
                    )

            threading.Thread(target=async_delete, daemon=True).start()

        def on_platform_chip_clicked(self, platform_name: str):
            """Handle platform chip selection and update contextual placeholder."""
            self.selected_platform = platform_name
            for name, btn in getattr(self, "platform_chips", {}).items():
                if name == platform_name:
                    btn.background_color = (1.0, 0.72, 0.0, 1.0)
                    btn.color = (0.05, 0.07, 0.12, 1.0)
                else:
                    btn.background_color = (0.12, 0.15, 0.22, 1.0)
                    btn.color = (0.75, 0.80, 0.90, 1.0)

            hints = {
                "ALL": "Search YouTube or paste any video/playlist link...",
                "YOUTUBE": "Paste YouTube link or search videos & playlists...",
                "INSTAGRAM": "Paste Instagram Reel or Post link...",
                "FACEBOOK": "Paste Facebook video or reel link...",
                "TIKTOK": "Paste TikTok video link...",
                "TWITTER / X": "Paste Twitter / X video link...",
            }
            if hasattr(self, "url_input"):
                self.url_input.hint_text = hints.get(platform_name, "Paste video or audio link...")

        def cancel_active_download(self):
            """Trigger immediate cancellation of running download and partial file cleanup (Feature 4)."""
            if not self.download_state.get("is_active"):
                return
            self.download_state["cancel_requested"] = True
            self.update_status("[color=#FFB300]Cancelling download...[/color]", 0)
            if hasattr(self, "cancel_download_btn"):
                self.cancel_download_btn.disabled = True

        def create_mini_player_bar(self) -> BoxLayout:
            """Persistent mini audio player bar floating directly above footer navigation (Feature 3)."""
            bar = StyledCard(
                orientation="vertical",
                padding=[dp(8), dp(4), dp(8), dp(4)],
                spacing=dp(3),
                size_hint_y=None,
                height=0,
                opacity=0,
                bg_color=(0.10, 0.12, 0.20, 0.98),
                radius=12,
            )
            bar.disabled = True

            # Row 1: Thin playback progress bar
            self.mini_player_progress = ProgressBar(
                max=100,
                value=0,
                size_hint_y=None,
                height=dp(3),
            )
            bar.add_widget(self.mini_player_progress)

            # Row 2: Controls & Info
            ctrl_row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(42))

            play_icon_path = get_asset_icon("play.png")
            if play_icon_path:
                ctrl_row.add_widget(
                    Image(
                        source=play_icon_path,
                        size_hint=(None, None),
                        size=(dp(24), dp(24)),
                        allow_stretch=True,
                        keep_ratio=True,
                        pos_hint={"center_y": 0.5},
                    )
                )

            info_col = BoxLayout(orientation="vertical", spacing=dp(1), size_hint_x=1.0)
            self.mini_player_title = Label(
                text="[b]No Track Selected[/b]",
                markup=True,
                font_size="11sp",
                color=(1, 1, 1, 1),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(20),
            )
            self.mini_player_title.bind(size=self.mini_player_title.setter("text_size"))
            info_col.add_widget(self.mini_player_title)

            self.mini_player_time = Label(
                text="0:00 / 0:00 • Offline Music",
                font_size="9.5sp",
                color=(0.55, 0.75, 1.0, 0.9),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(14),
            )
            self.mini_player_time.bind(size=self.mini_player_time.setter("text_size"))
            info_col.add_widget(self.mini_player_time)
            ctrl_row.add_widget(info_col)

            self.mini_player_prev_btn = IconActionButton(
                text="⏮",
                font_size="13sp",
                size_hint=(None, None),
                size=(dp(32), dp(32)),
                bg_color=(0.14, 0.18, 0.28, 1.0),
                text_color=(0.9, 0.9, 1.0, 1.0),
                pos_hint={"center_y": 0.5},
            )
            self.mini_player_prev_btn.bind(on_press=lambda ins: self.play_prev_audio())
            ctrl_row.add_widget(self.mini_player_prev_btn)

            self.mini_player_play_btn = IconActionButton(
                icon_path="play.png",
                text="⏸",
                font_size="12sp",
                size_hint=(None, None),
                size=(dp(46), dp(32)),
                bg_color=(1.0, 0.72, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                pos_hint={"center_y": 0.5},
            )
            self.mini_player_play_btn.bind(on_press=lambda ins: self.toggle_audio_playback())
            ctrl_row.add_widget(self.mini_player_play_btn)

            self.mini_player_next_btn = IconActionButton(
                text="⏭",
                font_size="13sp",
                size_hint=(None, None),
                size=(dp(32), dp(32)),
                bg_color=(0.14, 0.18, 0.28, 1.0),
                text_color=(0.9, 0.9, 1.0, 1.0),
                pos_hint={"center_y": 0.5},
            )
            self.mini_player_next_btn.bind(on_press=lambda ins: self.play_next_audio())
            ctrl_row.add_widget(self.mini_player_next_btn)

            self.mini_player_close_btn = IconActionButton(
                icon_path="clear.png",
                text="✕",
                font_size="11sp",
                size_hint=(None, None),
                size=(dp(30), dp(32)),
                bg_color=(0.28, 0.10, 0.12, 1.0),
                text_color=(1.0, 0.7, 0.7, 1.0),
                pos_hint={"center_y": 0.5},
            )
            self.mini_player_close_btn.bind(on_press=lambda ins: self.close_mini_player())
            ctrl_row.add_widget(self.mini_player_close_btn)

            bar.add_widget(ctrl_row)
            return bar

        def play_video_file(self, file_path: Path, title: Optional[str] = None):
            """Play downloaded local video file with native hardware acceleration and live notification support."""
            if not file_path or not file_path.exists():
                return
            clean_title = safe_display_text(title or file_path.stem)
            self.update_status(f"[color=#00E676]Playing Video:[/color] {clean_title}", 0)
            play_video_file(file_path, title=clean_title)

        def play_audio_track(self, file_path: Path):
            """Load and play local audio file in the built-in mini music player."""
            if not file_path or not file_path.exists():
                return

            # Refresh local audio playlist
            target_dir = get_android_download_dir()
            audio_files = []
            for ext in ("*.mp3", "*.m4a", "*.wav", "*.ogg", "*.opus", "*.flac", "*.aac"):
                audio_files.extend(target_dir.glob(ext))
            audio_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            self.audio_playlist = audio_files
            if file_path in self.audio_playlist:
                self.audio_index = self.audio_playlist.index(file_path)

            if self.current_sound:
                try:
                    self.current_sound.stop()
                    self.current_sound.unload()
                except Exception:
                    pass
                self.current_sound = None

            resolved_path = str(file_path.resolve())

            # 1. On Android, try native MediaPlayer first for guaranteed format & scoped storage support
            if is_running_on_android():
                try:
                    native_p = AndroidNativeAudioPlayer(resolved_path)
                    if native_p._mp:
                        self.current_sound = native_p
                except Exception as ne:
                    print(f"[AudioPlayer] Android native notice: {ne}")

            # 2. Try Kivy SoundLoader
            if not self.current_sound:
                try:
                    self.current_sound = SoundLoader.load(resolved_path)
                except Exception as e:
                    print(f"[SoundLoader] Error loading {file_path.name}: {e}")
                    self.current_sound = None

            if not self.current_sound:
                open_media_file(file_path)
                return

            self.current_track_path = file_path
            self.is_audio_playing = True
            self.mini_player_bar.height = dp(56)
            self.mini_player_bar.opacity = 1.0
            self.mini_player_bar.disabled = False

            clean_t = safe_display_text(file_path.stem)
            if len(clean_t) > 32:
                clean_t = clean_t[:29] + "..."
            self.mini_player_title.text = f"[b]{clean_t}[/b]"
            self.mini_player_play_btn.text = "⏸"
            self.mini_player_progress.value = 0

            self.current_sound.play()

            # Show Media Notification in Android notification bar
            self.notification_manager.show_media_playback(file_path.stem, is_playing=True, media_type="Song")

            if not self.player_clock_event:
                self.player_clock_event = Clock.schedule_interval(self._update_player_progress, 0.4)

        def toggle_audio_playback(self):
            """Toggle play / pause on current active audio track and sync notification state."""
            if not self.current_sound:
                return
            track_title = safe_display_text(self.current_track_path.stem if self.current_track_path else "Song Track")
            if self.current_sound.state == "play":
                self.current_sound.stop()
                self.is_audio_playing = False
                self.mini_player_play_btn.text = "▶"
                self.notification_manager.show_media_playback(track_title, is_playing=False, media_type="Song")
            else:
                self.current_sound.play()
                self.is_audio_playing = True
                self.mini_player_play_btn.text = "⏸"
                self.notification_manager.show_media_playback(track_title, is_playing=True, media_type="Song")

        def play_next_audio(self):
            """Play next audio track in library queue."""
            if not self.audio_playlist:
                return
            self.audio_index = (self.audio_index + 1) % len(self.audio_playlist)
            self.play_audio_track(self.audio_playlist[self.audio_index])

        def play_prev_audio(self):
            """Play previous audio track in library queue."""
            if not self.audio_playlist:
                return
            self.audio_index = (self.audio_index - 1) % len(self.audio_playlist)
            self.play_audio_track(self.audio_playlist[self.audio_index])

        def close_mini_player(self):
            """Stop playback, unload audio engine, collapse mini player bar, and dismiss notification."""
            if self.current_sound:
                try:
                    self.current_sound.stop()
                    self.current_sound.unload()
                except Exception:
                    pass
                self.current_sound = None

            if self.player_clock_event:
                self.player_clock_event.cancel()
                self.player_clock_event = None

            self.is_audio_playing = False
            self.mini_player_bar.height = 0
            self.mini_player_bar.opacity = 0
            self.mini_player_bar.disabled = True
            self.notification_manager.hide_media_playback()

        def _update_player_progress(self, dt):
            """Update mini player progress bar and elapsed/duration label."""
            if not self.current_sound:
                return
            if self.current_sound.state == "play":
                pos = self.current_sound.get_pos()
                length = self.current_sound.length or 0
                if length > 0:
                    pct = (pos / length) * 100
                    self.mini_player_progress.value = min(100, max(0, pct))
                    self.mini_player_time.text = f"{format_duration(pos)} / {format_duration(length)} • Playing"
                else:
                    self.mini_player_time.text = f"{format_duration(pos)} • Playing"
            elif self.current_sound.state == "stop" and self.is_audio_playing:
                pos = self.current_sound.get_pos()
                length = self.current_sound.length or 0
                if length > 0 and pos >= (length - 1.0):
                    self.play_next_audio()
                return
            if self.current_sound.state == "play":
                pos = self.current_sound.get_pos()
                length = self.current_sound.length or 0
                if length > 0:
                    pct = (pos / length) * 100
                    self.mini_player_progress.value = min(100, max(0, pct))
                    self.mini_player_time.text = f"{format_duration(pos)} / {format_duration(length)} • Playing"
                else:
                    self.mini_player_time.text = f"{format_duration(pos)} • Playing"
            elif self.current_sound.state == "stop" and self.is_audio_playing:
                pos = self.current_sound.get_pos()
                length = self.current_sound.length or 0
                if length > 0 and pos >= (length - 1.0):
                    self.play_next_audio()

        def check_for_updates(self, user_triggered: bool = True):
            """Query GitHub Releases API for new updates and display modal if newer version found."""
            if user_triggered:
                self.update_status("Checking GitHub for app updates...", 25)

            def worker():
                try:
                    import urllib.request
                    import json
                    api_url = "https://api.github.com/repos/msk-ytdl/msk-ytdl/releases/latest"
                    req = urllib.request.Request(
                        api_url,
                        headers={"User-Agent": "MSK-YTDL-App", "Accept": "application/vnd.github.v3+json"},
                    )
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            tag = data.get("tag_name", "").lstrip("v")
                            curr_ver = get_app_version()

                            if is_version_newer(curr_ver, tag):
                                release_name = data.get("name") or f"MSK YTDL v{tag}"
                                body = data.get("body") or "New release with performance enhancements and bug fixes."
                                html_url = data.get("html_url") or "https://github.com/msk-ytdl/msk-ytdl/releases"
                                apk_url = None
                                for asset in data.get("assets", []):
                                    if asset.get("name", "").endswith(".apk"):
                                        apk_url = asset.get("browser_download_url")
                                        break
                                Clock.schedule_once(
                                    lambda dt: self.open_update_modal(tag, release_name, body, html_url, apk_url=apk_url)
                                )
                                Clock.schedule_once(
                                    lambda dt: self.update_status(f"[color=#00E676]New Update Available:[/color] v{tag}", 100)
                                )
                            else:
                                if user_triggered:
                                    Clock.schedule_once(
                                        lambda dt: self.update_status(f"[color=#00E676]Up to date![/color] (v{curr_ver} is latest)", 100)
                                    )
                except Exception as e:
                    print(f"[UpdateChecker] Notice: {e}")
                    if user_triggered:
                        Clock.schedule_once(
                            lambda dt: self.update_status("[color=#FFB300]Update check skipped: network unavailable[/color]", 0)
                        )

            threading.Thread(target=worker, daemon=True).start()

        def open_update_modal(
            self,
            new_version: str,
            release_title: str,
            changelog: str,
            download_url: str,
            apk_url: Optional[str] = None,
        ):
            """Open in-app Auto-Updater modal with progress bar and 1-tap direct APK download & install."""
            modal = ModalView(size_hint=(0.94, 0.78), auto_dismiss=True)
            content = StyledCard(
                orientation="vertical",
                padding=[dp(16), dp(14)],
                spacing=dp(8),
                bg_color=(0.08, 0.10, 0.16, 0.98),
                radius=16,
            )

            # Header Row
            header_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(32))
            settings_icon = get_asset_icon("settings.png")
            if settings_icon:
                header_row.add_widget(
                    Image(source=settings_icon, size_hint=(None, None), size=(dp(24), dp(24)), allow_stretch=True, keep_ratio=True)
                )
            h_title = Label(
                text="[b][color=#FFB300]New Update Available![/color][/b]",
                markup=True,
                font_size="15sp",
                halign="left",
                valign="middle",
                size_hint_x=1.0,
            )
            h_title.bind(size=h_title.setter("text_size"))
            header_row.add_widget(h_title)

            close_btn = Button(
                text="✕",
                font_size="15sp",
                bold=True,
                size_hint=(None, None),
                size=(dp(28), dp(28)),
                background_color=(0.20, 0.22, 0.30, 1.0),
                color=(1, 1, 1, 1),
            )
            close_btn.bind(on_press=modal.dismiss)
            header_row.add_widget(close_btn)
            content.add_widget(header_row)

            # Version comparison card
            curr_v = get_app_version()
            v_card = StyledCard(
                orientation="horizontal",
                padding=[dp(12), dp(8)],
                spacing=dp(10),
                size_hint_y=None,
                height=dp(52),
                bg_color=(0.12, 0.15, 0.24, 1.0),
            )
            v_info = Label(
                text=f"[b]Version {new_version}[/b]  [color=#00E676]● LATEST[/color]\n[size=10sp][color=#90CAF9]Current installed: v{curr_v}[/color][/size]",
                markup=True,
                font_size="12sp",
                halign="left",
                valign="middle",
                size_hint_x=1.0,
            )
            v_info.bind(size=v_info.setter("text_size"))
            v_card.add_widget(v_info)
            content.add_widget(v_card)

            # Changelog Label & ScrollView
            content.add_widget(
                Label(
                    text="[b]Release Notes & What's New:[/b]",
                    markup=True,
                    font_size="11.5sp",
                    color=(0.85, 0.88, 0.95, 1.0),
                    size_hint_y=None,
                    height=dp(18),
                    halign="left",
                )
            )
            ch_scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, size_hint_y=1.0)
            ch_lbl = Label(
                text=safe_display_text(changelog) or "Bug fixes, performance improvements, and new features.",
                font_size="11sp",
                color=(0.75, 0.80, 0.90, 1.0),
                size_hint_y=None,
                halign="left",
                valign="top",
            )
            ch_lbl.bind(width=lambda ins, w: setattr(ins, "text_size", (w, None)))
            ch_lbl.bind(texture_size=lambda ins, ts: setattr(ins, "height", max(dp(50), ts[1] + dp(10))))
            ch_scroll.add_widget(ch_lbl)
            content.add_widget(ch_scroll)

            # In-App Auto-Update Download Progress Box
            up_progress_box = BoxLayout(orientation="vertical", spacing=dp(3), size_hint_y=None, height=dp(28))
            up_progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(6))
            up_status_lbl = Label(
                text="Tap below to auto-download and install update.",
                font_size="10.5sp",
                color=(0.75, 0.85, 0.95, 1.0),
                size_hint_y=None,
                height=dp(18),
                halign="center",
            )
            up_status_lbl.bind(size=up_status_lbl.setter("text_size"))
            up_progress_box.add_widget(up_progress_bar)
            up_progress_box.add_widget(up_status_lbl)
            content.add_widget(up_progress_box)

            # Action Buttons Row
            btn_col = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=dp(86))

            target_apk_url = apk_url or (download_url if download_url.endswith(".apk") else None)
            download_state = {"downloaded_file": None, "is_downloading": False}

            auto_dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="⚡ AUTO-DOWNLOAD & INSTALL NOW" if target_apk_url else "⬇ DOWNLOAD UPDATE (BROWSER)",
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
                font_size="11.5sp",
                size_hint_y=None,
                height=dp(40),
            )

            def start_auto_update_download(ins):
                if download_state.get("downloaded_file") and Path(download_state["downloaded_file"]).exists():
                    up_status_lbl.text = "[color=#00E676]Launching Package Installer...[/color]"
                    install_apk_file(download_state["downloaded_file"])
                    return

                if not target_apk_url:
                    modal.dismiss()
                    open_web_url(download_url)
                    return

                if download_state.get("is_downloading"):
                    return

                download_state["is_downloading"] = True
                auto_dl_btn.disabled = True
                up_status_lbl.text = f"Connecting to GitHub for v{new_version}..."

                def download_worker():
                    try:
                        import urllib.request
                        dest_dir = get_android_download_dir()
                        apk_dest = dest_dir / f"MSK_YTDL_v{new_version}.apk"

                        req = urllib.request.Request(
                            target_apk_url,
                            headers={"User-Agent": "MSK-YTDL-App", "Accept": "*/*"}
                        )
                        with urllib.request.urlopen(req, timeout=30) as response:
                            total_bytes = int(response.headers.get("Content-Length", 0))
                            downloaded = 0
                            block_size = 65536
                            with open(apk_dest, "wb") as f_out:
                                while True:
                                    chunk = response.read(block_size)
                                    if not chunk:
                                        break
                                    f_out.write(chunk)
                                    downloaded += len(chunk)
                                    if total_bytes > 0:
                                        pct = (downloaded / total_bytes) * 100
                                        mb_curr = downloaded / (1024 * 1024)
                                        mb_tot = total_bytes / (1024 * 1024)
                                        def update_ui(p=pct, c=mb_curr, t=mb_tot):
                                            up_progress_bar.value = p
                                            up_status_lbl.text = f"Downloading update: {p:.0f}% ({c:.1f}/{t:.1f} MB)"
                                        Clock.schedule_once(lambda dt: update_ui())

                        download_state["downloaded_file"] = str(apk_dest)
                        download_state["is_downloading"] = False

                        def on_success():
                            up_progress_bar.value = 100
                            up_status_lbl.text = "[color=#00E676]✓ Download Complete! Launching Installer...[/color]"
                            auto_dl_btn.disabled = False
                            auto_dl_btn.text = "🚀 TAP TO INSTALL NOW"
                            auto_dl_btn.bg_color = (0.10, 0.65, 0.30, 1.0)
                            auto_dl_btn.text_color = (1, 1, 1, 1)
                            install_apk_file(apk_dest)
                            self.update_status(f"[color=#00E676]Update v{new_version} ready to install![/color]", 100)

                        Clock.schedule_once(lambda dt: on_success())

                    except Exception as err:
                        print(f"[AutoUpdate] Download error: {err}")
                        download_state["is_downloading"] = False
                        def on_fail():
                            auto_dl_btn.disabled = False
                            auto_dl_btn.text = "🌐 OPEN GITHUB RELEASE (FALLBACK)"
                            up_status_lbl.text = "[color=#FF5252]Download failed. Tap to open in browser.[/color]"
                            auto_dl_btn.bind(on_press=lambda i: open_web_url(download_url))
                        Clock.schedule_once(lambda dt: on_fail())

                threading.Thread(target=download_worker, daemon=True).start()

            auto_dl_btn.bind(on_press=start_auto_update_download)
            btn_col.add_widget(auto_dl_btn)

            sub_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(36))
            github_btn = IconActionButton(
                icon_path="settings.png",
                text="GITHUB RELEASES",
                bg_color=(0.14, 0.18, 0.28, 1.0),
                text_color=(0.80, 0.88, 1.0, 1.0),
                font_size="11sp",
                size_hint_x=0.6,
            )
            github_btn.bind(on_press=lambda ins: open_web_url(download_url))
            sub_row.add_widget(github_btn)

            later_btn = IconActionButton(
                icon_path="clear.png",
                text="LATER",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.80, 0.85, 0.95, 1.0),
                font_size="11sp",
                size_hint_x=0.4,
            )
            later_btn.bind(on_press=modal.dismiss)
            sub_row.add_widget(later_btn)
            btn_col.add_widget(sub_row)

            content.add_widget(btn_col)
            modal.add_widget(content)
            modal.open()

        # -----------------------------------------------------------------
        # Download Execution Logic (Multi-Platform, Pause/Cancel, Playlist Multi-Select)
        # -----------------------------------------------------------------
        def start_download(
            self,
            instance=None,
            target_url: Optional[str] = None,
            chosen_format: Optional[str] = None,
            is_playlist: Optional[bool] = None,
            selected_indices: Optional[List[int]] = None,
            entries: Optional[List[Dict[str, Any]]] = None,
        ):
            """Validate inputs and launch background download thread with pause/cancel queue support."""
            url = target_url or self.url_input.text.strip()
            if not url:
                self.update_status("[color=#FF5252]Please paste a video or audio link first![/color]", 0)
                return

            normalized = normalize_media_url(url)
            if not normalized:
                self.update_status("[color=#FF5252]Invalid link. Paste a valid URL.[/color]", 0)
                return

            url = normalized
            selected_format = chosen_format or (self.quality_spinner.text if hasattr(self, "quality_spinner") else "Video (Max Quality - 1080p / 720p HD)")
            is_audio = "Audio" in selected_format
            plat = detect_media_platform(url)

            # Update active download state (Feature 4)
            self.download_state["is_active"] = True
            self.download_state["cancel_requested"] = False
            self.download_state["current_part_files"].clear()

            self.download_btn.disabled = True
            if hasattr(self, "cancel_download_btn"):
                self.cancel_download_btn.disabled = False
                self.cancel_download_btn.height = dp(32)
                self.cancel_download_btn.opacity = 1.0
            if hasattr(self, "status_card"):
                self.status_card.height = dp(112)

            self.update_status(f"Starting {plat} download engine...", 5)

            def worker():
                try:
                    import yt_dlp

                    target_dir = get_android_download_dir()
                    target_dir.mkdir(parents=True, exist_ok=True)

                    Clock.schedule_once(
                        lambda dt: self.update_status("Resolving streams & metadata...", 12)
                    )

                    current_item_meta = {"index": 1, "total": 1, "title": "Video"}

                    def progress_hook(d):
                        if self.download_state.get("cancel_requested"):
                            raise DownloadCancelledException("Download cancelled by user.")

                        if d.get("status") == "downloading":
                            fn = d.get("filename")
                            if fn:
                                self.download_state["current_part_files"].add(str(fn))

                            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                            downloaded = d.get("downloaded_bytes") or 0
                            if total > 0:
                                pct = int((downloaded / total) * 100)
                                speed = d.get("speed")
                                speed_str = f" • {format_bytes(speed)}/s" if speed else ""
                                tot = current_item_meta["total"]
                                cur_i = current_item_meta["index"]
                                cur_t = current_item_meta["title"]

                                if tot > 1:
                                    overall_pct = int(((cur_i - 1) / tot) * 100) + int(pct / tot)
                                    status_msg = f"[{cur_i}/{tot}] {overall_pct}% ({pct}%) • {safe_display_text(cur_t)}{speed_str}"
                                    notif_pct = overall_pct
                                else:
                                    overall_pct = pct
                                    status_msg = f"Downloading: {pct}%{speed_str}"
                                    notif_pct = pct

                                Clock.schedule_once(
                                    lambda dt, msg=status_msg, p=overall_pct: self.update_status(msg, p)
                                )

                                now = time.time()
                                if (now - self.last_notif_time) > 1.2 or pct >= 99:
                                    self.last_notif_time = now
                                    notif_title = f"[{cur_i}/{tot}] {cur_t}" if tot > 1 else f"Downloading: {cur_t}"
                                    self.notification_manager.show_progress(notif_title, notif_pct, speed_str)

                        elif d.get("status") == "finished":
                            Clock.schedule_once(
                                lambda dt: self.update_status("Processing & saving media to storage...", 95)
                            )

                    has_ffmpeg = bool(shutil.which("ffmpeg"))
                    safe_logger = AndroidYTDLLogger()

                    base_ydl_opts = {
                        "windowsfilenames": True,
                        "trim_file_name": 215,
                        "paths": {"home": str(target_dir), "temp": str(target_dir)},
                        "progress_hooks": [progress_hook],
                        "logger": safe_logger,
                        "socket_timeout": 35,
                        "nocheckcertificate": False,
                        "quiet": True,
                        "no_warnings": True,
                        "no_color": True,
                        "nooverwrites": False,
                        "continuedl": False,
                        "noplaylist": True,
                        "concurrent_fragment_downloads": 4,
                        "buffersize": 1048576,
                        "http_chunk_size": 10485760,
                    }

                    # Format selector resolution
                    base_ydl_opts["format"] = get_ydl_format_selector(selected_format, has_ffmpeg=has_ffmpeg)

                    if is_audio:
                        if "MP3" in selected_format and has_ffmpeg:
                            base_ydl_opts["postprocessors"] = [{
                                "key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "320" if "320" in selected_format else "192",
                            }]
                    else:
                        if not has_ffmpeg:
                            base_ydl_opts["allow_unplayable_formats"] = True

                    # Resolve items list
                    active_entries = []
                    if entries:
                        active_entries = list(entries)
                    else:
                        flat_opts = {
                            "extract_flat": "in_playlist",
                            "skip_download": True,
                            "logger": safe_logger,
                            "socket_timeout": 25,
                            "quiet": True,
                            "no_warnings": True,
                        }
                        with yt_dlp.YoutubeDL(flat_opts) as flat_ydl:
                            media_meta = flat_ydl.extract_info(url, download=False)
                            if not media_meta:
                                raise RuntimeError("Could not retrieve media details.")
                            is_pl = media_meta.get("_type") == "playlist" or "entries" in media_meta
                            raw_list = list(media_meta.get("entries") or []) if is_pl else [media_meta]
                            active_entries = [e for e in raw_list if e]

                    # Filter to selected indices if provided (Feature 1)
                    if selected_indices is not None and len(selected_indices) > 0:
                        active_entries = [active_entries[i] for i in selected_indices if i < len(active_entries)]

                    total_count = len(active_entries) if active_entries else 1
                    current_item_meta["total"] = total_count

                    if total_count > 1:
                        Clock.schedule_once(
                            lambda dt, cnt=total_count: self.update_status(
                                f"[color=#FFB300]Queue Ready:[/color] Starting download of {cnt} items...", 5
                            )
                        )

                    saved_files: List[Path] = []
                    skipped_count = 0

                    for idx, item in enumerate(active_entries, start=1):
                        if self.download_state.get("cancel_requested"):
                            raise DownloadCancelledException("Download cancelled by user.")

                        raw_item_title = item.get("title") or f"Item {idx}"
                        clean_title = sanitize_storage_filename(raw_item_title, f"Video_{idx}")
                        item_id = item.get("id") or ""
                        if not item_id:
                            for cand in (item.get("webpage_url"), item.get("url")):
                                if cand and isinstance(cand, str):
                                    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})", cand)
                                    if m:
                                        item_id = m.group(1)
                                        break

                        item_url = get_canonical_video_url(item, fallback_url=url)
                        item_thumb = item.get("thumbnail") or (f"https://i.ytimg.com/vi/{item_id}/hqdefault.jpg" if item_id else None)
                        item_uploader = item.get("uploader") or item.get("channel") or plat

                        current_item_meta["index"] = idx
                        current_item_meta["title"] = raw_item_title

                        if total_count > 1:
                            overall_start_pct = int(((idx - 1) / total_count) * 100)
                            Clock.schedule_once(
                                lambda dt, i=idx, tot=total_count, t=raw_item_title, p=overall_start_pct: self.update_status(
                                    f"Starting [{i}/{tot}]: {safe_display_text(t)}...", p
                                )
                            )
                            self.notification_manager.show_progress(f"[{idx}/{total_count}] {raw_item_title}", overall_start_pct)

                        item_opts = dict(base_ydl_opts)
                        if total_count > 1:
                            item_opts["outtmpl"] = str(target_dir / f"[{idx:02d}] %(title)s.%(ext)s")
                        else:
                            item_opts["outtmpl"] = str(target_dir / "%(title)s.%(ext)s")

                        try:
                            with yt_dlp.YoutubeDL(item_opts) as ydl:
                                info = ydl.extract_info(item_url, download=True)
                        except DownloadCancelledException:
                            raise
                        except Exception as dl_err:
                            err_str = str(dl_err)
                            if "File name too long" in err_str or "Errno 36" in err_str:
                                print(f"[Download] Retrying with clean short filename due to: {err_str}")
                                fallback_opts = dict(item_opts)
                                fallback_opts["outtmpl"] = str(target_dir / "%(title).180s.%(ext)s")
                                with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                                    info = ydl_fb.extract_info(item_url, download=True)
                            elif total_count > 1:
                                print(f"[Queue] Skipping item #{idx} ({raw_item_title}) due to: {dl_err}")
                                skipped_count += 1
                                Clock.schedule_once(
                                    lambda dt, i=idx, tot=total_count: self.update_status(
                                        f"[color=#FFA000]Skipped unplayable item {i}/{tot}[/color]", int((i / tot) * 100)
                                    )
                                )
                                continue
                            else:
                                raise

                        if not info:
                            continue

                        saved_path: Optional[Path] = None

                        # Check for separate DASH video + audio streams needing native Android / system muxing
                        if not has_ffmpeg and not is_audio and info:
                            v_track: Optional[Path] = None
                            a_track: Optional[Path] = None
                            cand_files: List[Path] = []

                            if "requested_downloads" in info and info["requested_downloads"]:
                                for rd in info["requested_downloads"]:
                                    fp = rd.get("filepath")
                                    if fp and Path(fp).is_file():
                                        cand_files.append(Path(fp))

                            if len(cand_files) < 2 and "requested_formats" in info:
                                for rf in info["requested_formats"]:
                                    fid = rf.get("format_id")
                                    if fid:
                                        for cp in target_dir.glob(f"*.f{fid}.*"):
                                            if cp.is_file() and cp not in cand_files:
                                                cand_files.append(cp)

                            for cp in cand_files:
                                suf = cp.suffix.lower()
                                if suf in (".mp4", ".mkv", ".webm") and not v_track:
                                    v_track = cp
                                elif suf in (".m4a", ".aac", ".mp3", ".webm", ".opus") and not a_track:
                                    a_track = cp

                            if v_track and a_track and v_track.is_file() and a_track.is_file():
                                final_mp4 = target_dir / (f"[{idx:02d}] {clean_title}.mp4" if total_count > 1 else f"{clean_title}.mp4")
                                merged_ok = mux_video_audio_android(v_track, a_track, final_mp4)
                                if merged_ok and final_mp4.is_file() and final_mp4.stat().st_size > 1024:
                                    saved_path = final_mp4
                                    try:
                                        v_track.unlink(missing_ok=True)
                                        a_track.unlink(missing_ok=True)
                                    except Exception:
                                        pass
                                else:
                                    print("[Mux] DASH muxing did not produce valid MP4. Falling back to guaranteed stream with audio...")
                                    try:
                                        v_track.unlink(missing_ok=True)
                                        a_track.unlink(missing_ok=True)
                                        if final_mp4.exists():
                                            final_mp4.unlink(missing_ok=True)
                                    except Exception:
                                        pass

                                    # Guaranteed fallback: fetch stream with synchronized audio
                                    fb_opts = dict(item_opts)
                                    fb_opts["format"] = "22/best[height<=720][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/18/best"
                                    fb_opts.pop("allow_unplayable_formats", None)
                                    fb_opts["extractor_args"] = {"youtube": {"player_client": ["android", "web"]}}
                                    try:
                                        with yt_dlp.YoutubeDL(fb_opts) as ydl_fb:
                                            fb_info = ydl_fb.extract_info(item_url, download=True)
                                            if fb_info:
                                                if "requested_downloads" in fb_info and fb_info["requested_downloads"]:
                                                    fb_fp = fb_info["requested_downloads"][0].get("filepath")
                                                    if fb_fp and Path(fb_fp).is_file():
                                                        saved_path = Path(fb_fp)
                                                if not saved_path:
                                                    try:
                                                        fb_prep = ydl_fb.prepare_filename(fb_info)
                                                        if Path(fb_prep).is_file():
                                                            saved_path = Path(fb_prep)
                                                    except Exception:
                                                        pass
                                    except Exception as fb_err:
                                        print(f"[Mux Fallback] Notice: {fb_err}")
                            elif v_track and not a_track:
                                print("[Download] Only silent video track found. Re-downloading with guaranteed audio stream...")
                                try:
                                    v_track.unlink(missing_ok=True)
                                except Exception:
                                    pass
                                fb_opts = dict(item_opts)
                                fb_opts["format"] = "22/best[height<=720][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/18/best"
                                fb_opts.pop("allow_unplayable_formats", None)
                                fb_opts["extractor_args"] = {"youtube": {"player_client": ["android", "web"]}}
                                try:
                                    with yt_dlp.YoutubeDL(fb_opts) as ydl_fb:
                                        fb_info = ydl_fb.extract_info(item_url, download=True)
                                        if fb_info:
                                            if "requested_downloads" in fb_info and fb_info["requested_downloads"]:
                                                fb_fp = fb_info["requested_downloads"][0].get("filepath")
                                                if fb_fp and Path(fb_fp).is_file():
                                                    saved_path = Path(fb_fp)
                                            if not saved_path:
                                                try:
                                                    fb_prep = ydl_fb.prepare_filename(fb_info)
                                                    if Path(fb_prep).is_file():
                                                        saved_path = Path(fb_prep)
                                                except Exception:
                                                    pass
                                except Exception as fb_err:
                                    print(f"[Fallback] Notice: {fb_err}")

                        if not saved_path and "requested_downloads" in info and info["requested_downloads"]:
                            fp = info["requested_downloads"][0].get("filepath")
                            if fp and Path(fp).is_file():
                                saved_path = Path(fp)

                        if not saved_path:
                            try:
                                prepared = ydl.prepare_filename(info)
                                if Path(prepared).is_file():
                                    saved_path = Path(prepared)
                            except Exception:
                                pass

                        if not saved_path and item_id:
                            candidates = [c for c in target_dir.glob(f"*{item_id}*") if c.is_file()]
                            if candidates:
                                saved_path = candidates[0]

                        # Check if file was saved as 'videoplayback' and rename
                        if not saved_path or "videoplayback" in saved_path.name.lower():
                            for p in target_dir.glob("*videoplayback*"):
                                if p.is_file():
                                    ext = p.suffix or (".mp4" if not is_audio else ".m4a")
                                    fixed_name = f"[{idx:02d}] {clean_title}{ext}" if total_count > 1 else f"{clean_title}{ext}"
                                    renamed_file = target_dir / fixed_name
                                    try:
                                        if not renamed_file.exists():
                                            p.rename(renamed_file)
                                            saved_path = renamed_file
                                        else:
                                            saved_path = p
                                    except Exception:
                                        saved_path = p
                                    break

                        # For audio downloads: ensure correct audio extension and clean any .f<id> artifacts
                        if saved_path and saved_path.is_file() and is_audio:
                            audio_target_ext = ".mp3" if ("MP3" in selected_format and has_ffmpeg) else ".m4a"
                            if ".f" in saved_path.name or saved_path.suffix.lower() not in (".m4a", ".mp3", ".aac", ".opus", ".ogg"):
                                proper_audio_name = f"[{idx:02d}] {clean_title}{audio_target_ext}" if total_count > 1 else f"{clean_title}{audio_target_ext}"
                                proper_audio_path = target_dir / proper_audio_name
                                try:
                                    if not proper_audio_path.exists():
                                        saved_path.rename(proper_audio_path)
                                        saved_path = proper_audio_path
                                except Exception:
                                    pass

                        if saved_path and saved_path.exists():
                            if is_audio:
                                embed_audio_metadata(saved_path, raw_item_title, item_uploader, item_thumb)
                            scan_media_file(saved_path)
                            saved_files.append(saved_path)

                    if saved_files:
                        last_file = saved_files[-1]
                        if total_count > 1:
                            msg = f"[color=#00E676]Download Complete![/color] {len(saved_files)} of {total_count} saved."
                            self.notification_manager.show_finished(f"MSK YTDL {plat}", f"{len(saved_files)} items saved")
                        else:
                            clean_fname = safe_display_text(last_file.name)
                            msg = f"[color=#00E676]Done![/color] Saved: {clean_fname}"
                            self.notification_manager.show_finished(f"MSK YTDL {plat}", clean_fname)

                        Clock.schedule_once(lambda dt, m=msg: self.update_status(m, 100))
                    else:
                        Clock.schedule_once(
                            lambda dt: self.update_status("[color=#00E676]Download completed![/color]", 100)
                        )

                    Clock.schedule_once(lambda dt: self.refresh_library(), 0.5)

                except DownloadCancelledException:
                    print("[MSK-YTDL] Download cancelled by user.")
                    self.notification_manager.cancel()
                    # Clean up partial fragments
                    try:
                        for pf in list(self.download_state.get("current_part_files", [])):
                            if os.path.exists(pf):
                                try:
                                    os.remove(pf)
                                except Exception:
                                    pass
                        if target_dir.exists():
                            for p in target_dir.glob("*.part"):
                                try:
                                    if time.time() - p.stat().st_mtime < 120:
                                        p.unlink(missing_ok=True)
                                except Exception:
                                    pass
                            for y in target_dir.glob("*.ytdl"):
                                try:
                                    if time.time() - y.stat().st_mtime < 120:
                                        y.unlink(missing_ok=True)
                                except Exception:
                                    pass
                    except Exception as ce:
                        print(f"[Cleanup] Error removing partial files: {ce}")
                    Clock.schedule_once(
                        lambda dt: self.update_status("[color=#FFA000]Download Cancelled.[/color]", 0)
                    )

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.notification_manager.cancel()
                    err_msg = str(e)
                    if "File name too long" in err_msg or "Errno 36" in err_msg:
                        user_friendly_err = "Storage filename error. Please try downloading again."
                    elif "Requested format is not available" in err_msg:
                        user_friendly_err = "Selected format not available for this media."
                    elif "Video unavailable" in err_msg or "Private video" in err_msg:
                        user_friendly_err = "Media is private or unavailable."
                    elif "Sign in to confirm" in err_msg or "age-restricted" in err_msg:
                        user_friendly_err = "Age-restricted media: sign-in required."
                    elif "getaddrinfo failed" in err_msg or "timed out" in err_msg or "Network is unreachable" in err_msg:
                        user_friendly_err = "Network error. Check internet connection."
                    elif "ExtractorError" in err_msg or "not a valid URL" in err_msg:
                        user_friendly_err = "Invalid URL or platform link. Please check."
                    else:
                        clean_err = err_msg.replace("ERROR: ", "").strip()
                        user_friendly_err = clean_err if clean_err else "Download failed."
                    if len(user_friendly_err) > 75:
                        user_friendly_err = user_friendly_err[:72] + "..."
                    Clock.schedule_once(
                        lambda dt, err=user_friendly_err: self.update_status(
                            f"[color=#FF5252]Error:[/color] {err}", 0
                        )
                    )
                finally:
                    self.download_state["is_active"] = False
                    self.download_state["cancel_requested"] = False
                    self.download_state["current_part_files"].clear()
                    def reset_ui_state(dt=None):
                        self.download_btn.disabled = False
                        self.download_btn.text = "DOWNLOAD NOW"
                        self.current_preview_url = ""
                        if hasattr(self, "cancel_download_btn"):
                            self.cancel_download_btn.disabled = True
                            self.cancel_download_btn.height = 0
                            self.cancel_download_btn.opacity = 0
                        if hasattr(self, "status_card"):
                            self.status_card.height = dp(72)
                    Clock.schedule_once(reset_ui_state)

            threading.Thread(target=worker, daemon=True).start()


def main():
    if not KIVY_AVAILABLE:
        print("[Notice] Kivy framework is not installed in this desktop Python environment.")
        print("To run the Android touch UI on desktop for testing:")
        print("    pip install kivy")
        print("\nAlternatively, build the APK via GitHub Actions or run in Termux:")
        print("    bash scripts/install_android_termux.sh")
        return 1

    app = MSKDownloaderMobile()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

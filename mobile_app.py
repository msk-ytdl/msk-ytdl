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
from typing import Optional, Dict, Any, List

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


def normalize_youtube_url(text: str) -> Optional[str]:
    """
    Robustly extract and canonicalize any YouTube link, playlist, query fragment, or video ID.
    Handles:
      - 'https://www.youtube.com/playlist?list=PL...'
      - 'https://www.youtube.com/watch?v=UQyh7QIVaDU&list=PL...'
      - 'https://youtu.be/UQyh7QIVaDU?list=PL...'
      - 'v=UQyh7QIVaDU&si=...'
      - 'watch?v=UQyh7QIVaDU'
      - 'UQyh7QIVaDU' (raw 11-char ID)
      - 'https://youtu.be/UQyh7QIVaDU?si=...'
      - 'https://www.youtube.com/watch?v=UQyh7QIVaDU'
      - 'https://www.youtube.com/shorts/UQyh7QIVaDU'
      - Text containing links shared from YouTube app
    """
    if not text:
        return None
    raw = text.strip()

    # 1. Direct playlist URL: youtube.com/playlist?list=...
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
    match_full = re.search(
        r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})|youtu\.be/([a-zA-Z0-9_-]{11})|youtube\.com/shorts/([a-zA-Z0-9_-]{11})|youtube\.com/live/([a-zA-Z0-9_-]{11})|youtube\.com/embed/([a-zA-Z0-9_-]{11}))",
        raw,
    )
    if match_full:
        vid = (
            match_full.group(1)
            or match_full.group(2)
            or match_full.group(3)
            or match_full.group(4)
            or match_full.group(5)
        )
        # If it belongs to a true user/channel playlist (not radio mix RD... or top list TL...), treat as playlist
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

    # 6. Raw 11-character video ID alone (e.g. 'UQyh7QIVaDU')
    match_raw_id = re.match(r"^[a-zA-Z0-9_-]{11}$", raw)
    if match_raw_id:
        return f"https://www.youtube.com/watch?v={raw}"

    # 7. General web link fallback
    match_gen = re.search(r"(https?://[^\s]+)", raw)
    if match_gen:
        return match_gen.group(1)

    return None


def extract_youtube_url(text: str) -> Optional[str]:
    """Compatibility alias for normalize_youtube_url."""
    return normalize_youtube_url(text)


def sanitize_storage_filename(title: Optional[str], default_name: str = "MSK_Video") -> str:
    """Sanitize title for Android filesystem: strip non-ASCII, emojis, symbols, and length-cap to 35 chars."""
    if not title:
        return default_name
    clean = safe_display_text(title)
    # Strip forbidden filesystem chars
    clean = re.sub(r'[\\/*?:"<>|#%&{}\\<>*?/$!\'":@]', "", clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean or clean.lower() == "videoplayback":
        clean = default_name
    return clean[:35].strip()


def get_canonical_video_url(item: Dict[str, Any], fallback_url: str = "") -> str:
    """
    Ensure yt-dlp receives a canonical watch URL (with 11-char ID)
    so it invokes the proper YouTube extractor and never downloads as 'videoplayback.mp4'.
    """
    vid_id = item.get("id")
    if vid_id and len(str(vid_id)) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", str(vid_id)):
        return f"https://www.youtube.com/watch?v={vid_id}"

    # Extract ID from webpage_url, url, or fallback_url
    for cand in (item.get("webpage_url"), item.get("url"), fallback_url):
        if not cand or not isinstance(cand, str):
            continue
        m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([a-zA-Z0-9_-]{11})", cand)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"

    # If it's a playlist URL or non-YouTube URL, return it directly if not a direct CDN stream
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
        for p in ("READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "READ_MEDIA_IMAGES", "POST_NOTIFICATIONS"):
            if hasattr(Permission, p):
                perms.append(getattr(Permission, p))
        request_permissions(perms)
    except Exception as e:
        print(f"[Android] Permission request notice: {e}")


def is_running_on_android() -> bool:
    """Detect if running inside an Android runtime environment."""
    return (
        "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_ROOT" in os.environ
        or "ANDROID_BOOTLOGO" in os.environ
        or Path("/system/build.prop").exists()
    )


def get_android_download_dir() -> Path:
    """
    Resolve a guaranteed writable destination directory on Android.
    Prefers public Downloads folder; falls back to app-specific external storage.
    If running on desktop during testing/development, uses user's Downloads/YouTube directory.
    """
    if not is_running_on_android():
        desktop_dir = Path.home() / "Downloads" / "YouTube"
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            return desktop_dir
        except Exception:
            return Path.home() / "Downloads"

    candidates = [
        Path("/storage/emulated/0/Download/YouTube"),
        Path("/sdcard/Download/YouTube"),
        Path("/storage/emulated/0/Download"),
        Path("/sdcard/Download"),
    ]

    # Try app's private external files directory via PyJnius (always 100% writable on all Android versions)
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Environment = autoclass("android.os.Environment")
        context = PythonActivity.mActivity
        ext_dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
        if ext_dir:
            candidates.append(Path(ext_dir.getAbsolutePath()))
    except Exception:
        pass

    # App user_data_dir fallback
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


def scan_media_file(filepath: Path):
    """Notify Android's MediaScannerConnection so the file appears or is removed from Gallery/Music players."""
    try:
        if is_running_on_android():
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            MediaScannerConnection = autoclass("android.media.MediaScannerConnection")
            ctx = PythonActivity.mActivity
            if ctx:
                MediaScannerConnection.scanFile(ctx, [str(filepath.resolve())], None, None)
                print(f"[Android] MediaScannerConnection synced: {filepath.name}")
    except Exception as e:
        print(f"[Android] MediaScanner notice: {e}")


def open_media_file(filepath: Path):
    """Launch the downloaded video or song in the default Android or desktop player."""
    try:
        if is_running_on_android():
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            activity = PythonActivity.mActivity

            # Disable strict mode URI exposed checks on modern Android
            try:
                StrictMode = autoclass("android.os.StrictMode")
                builder = autoclass("android.os.StrictMode$VmPolicy$Builder")()
                StrictMode.setVmPolicy(builder.build())
            except Exception:
                pass

            file_obj = File(str(filepath.resolve()))
            file_uri = Uri.fromFile(file_obj)
            intent = Intent(Intent.ACTION_VIEW)

            ext = filepath.suffix.lower()
            if ext in (".mp3", ".m4a", ".aac", ".ogg", ".opus"):
                mime_type = "audio/*"
            else:
                mime_type = "video/*"

            intent.setDataAndType(file_uri, mime_type)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            activity.startActivity(intent)
        else:
            # Desktop fallback (Windows / macOS / Linux)
            if sys.platform == "win32":
                os.startfile(str(filepath.resolve()))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(filepath.resolve())])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(filepath.resolve())])
    except Exception as e:
        print(f"[OpenMedia] Error opening file {filepath.name}: {e}")


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
    """Manages ongoing and completed download notifications in the Android notification drawer."""
    def __init__(self):
        self.channel_id = "msk_ytdl_downloads"
        self.notification_id = 4242
        self.manager = None
        self.context = None
        self._init_done = False

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
                channel_name = autoclass("java.lang.String")("MSK YTDL Downloads")
                importance_low = 2  # IMPORTANCE_LOW for quiet ongoing updates
                channel = NotificationChannel(self.channel_id, channel_name, importance_low)
                channel.setDescription("Progress and status for YouTube downloads")
                self.manager.createNotificationChannel(channel)

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
            builder.setContentTitle(f"Downloading: {clean_title[:38]}")
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
            builder.setContentTitle("Download Complete!")
            builder.setContentText(f"Saved: {filename[:42]}")
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


    class MSKDownloaderMobile(App):
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

            self.notification_manager = AndroidNotificationManager()
            self.current_preview_url = ""
            self.last_clipboard_text = ""
            self.last_notif_time = 0.0
            self.active_tab = "home"
            self.active_filter = "all"

            # Request Android storage & notification permissions on startup
            request_android_permissions()

            # Listen for Android "Share from YouTube" intents (warm start)
            try:
                import android.activity
                android.activity.bind(on_new_intent=self.on_new_intent)
            except Exception:
                pass

            # Root vertical container: [Pinned Header] + [Dynamic Main View] + [Pinned Bottom Footer Nav]
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

            # Build all 3 Tab Views
            self.home_view = self.build_home_view()
            self.downloads_view = self.build_downloads_view()
            self.videos_view = self.build_videos_view()

            # Start on Home view
            self.main_container.add_widget(self.home_view)

            # -------------------------------------------------------------
            # Bottom Navigation Footer Bar (Home / Downloads / Videos)
            # -------------------------------------------------------------
            self.nav_footer = self.create_bottom_nav()
            root.add_widget(self.nav_footer)

            # Initial startup tasks
            Clock.schedule_once(self.check_initial_intent, 0.4)
            Clock.schedule_once(lambda dt: self.refresh_library(), 0.6)
            Clock.schedule_interval(self.check_clipboard, 2.5)

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
        # Bottom Navigation Footer Bar Builder (Home / Videos / Downloads)
        # -----------------------------------------------------------------
        def create_bottom_nav(self) -> BoxLayout:
            nav_bar = StyledCard(
                orientation="horizontal",
                padding=[dp(6), dp(3)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(56),
                bg_color=(0.07, 0.08, 0.13, 1.0),
            )

            self.nav_btn_home = NavTabItem("home", "home.png", "HOME", is_active=True)
            self.nav_btn_home.bind(on_press=lambda ins: self.switch_tab("home"))
            nav_bar.add_widget(self.nav_btn_home)

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
            self.nav_btn_videos.set_active(tab_name == "videos")
            self.nav_btn_downloads.set_active(tab_name == "downloads")

            if tab_name == "home":
                self.main_container.add_widget(self.home_view)
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
                padding=[dp(14), dp(10), dp(14), dp(16)],
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

            # URL Input Card with PASTE and CLEAR Buttons
            input_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(138),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            input_title = Label(
                text="[b]YouTube Video or Playlist Link[/b]",
                markup=True,
                font_size="13sp",
                color=(0.9, 0.9, 0.95, 1.0),
                size_hint_y=None,
                height=dp(20),
                halign="left",
            )
            input_title.bind(size=input_title.setter("text_size"))
            input_card.add_widget(input_title)

            self.url_input = TextInput(
                hint_text="Paste YouTube link here or tap Share in YouTube...",
                multiline=False,
                font_size="13.5sp",
                size_hint_y=None,
                height=dp(42),
                background_color=(0.14, 0.16, 0.24, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.75, 0, 1),
                padding=[dp(10), dp(10)],
            )
            self.url_input.bind(text=self.on_url_input_changed)
            input_card.add_widget(self.url_input)

            # Action Buttons Row: PASTE & CLEAR with crisp PNG icons
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(38))
            paste_btn = IconActionButton(
                icon_path="paste.png",
                text="PASTE LINK",
                bg_color=(0.20, 0.26, 0.40, 1.0),
                text_color=(1, 0.75, 0, 1),
                font_size="12sp",
            )
            paste_btn.bind(on_press=self.on_paste_clicked)

            clear_btn = IconActionButton(
                icon_path="clear.png",
                text="CLEAR",
                bg_color=(0.18, 0.20, 0.28, 1.0),
                text_color=(0.8, 0.85, 0.95, 1),
                font_size="12sp",
            )
            clear_btn.bind(on_press=self.on_clear_clicked)

            btn_row.add_widget(paste_btn)
            btn_row.add_widget(clear_btn)
            input_card.add_widget(btn_row)
            content.add_widget(input_card)

            # Real-Time Video Preview Card
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
                size=(dp(104), dp(60)),
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
                height=dp(36),
            )
            self.preview_title.bind(size=self.preview_title.setter("text_size"))
            preview_info_col.add_widget(self.preview_title)

            self.preview_meta = Label(
                text="Channel • Duration",
                markup=True,
                font_size="11sp",
                color=(0.7, 0.75, 0.88, 1.0),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(18),
            )
            self.preview_meta.bind(size=self.preview_meta.setter("text_size"))
            preview_info_col.add_widget(self.preview_meta)

            self.preview_card.add_widget(preview_info_col)
            content.add_widget(self.preview_card)

            # Format & Quality Selector Card
            format_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(92),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            format_title = Label(
                text="[b]Select Format & Quality[/b]",
                markup=True,
                font_size="13sp",
                color=(0.9, 0.9, 0.95, 1.0),
                size_hint_y=None,
                height=dp(20),
                halign="left",
            )
            format_title.bind(size=format_title.setter("text_size"))
            format_card.add_widget(format_title)

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
                background_color=(0.16, 0.19, 0.28, 1.0),
                color=(1, 1, 1, 1),
                font_size="13sp",
            )
            format_card.add_widget(self.quality_spinner)
            content.add_widget(format_card)

            # Status & Progress Card
            status_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(78),
                bg_color=(0.08, 0.10, 0.16, 1.0),
            )
            self.progress_bar = ProgressBar(
                max=100,
                value=0,
                size_hint_y=None,
                height=dp(10),
            )
            status_card.add_widget(self.progress_bar)

            self.status_label = Label(
                text="Ready. Paste a link or tap 'Share' from YouTube.",
                markup=True,
                font_size="12sp",
                color=(0.8, 0.85, 0.92, 1.0),
                size_hint_y=None,
                height=dp(28),
                halign="center",
            )
            self.status_label.bind(size=self.status_label.setter("text_size"))
            status_card.add_widget(self.status_label)
            content.add_widget(status_card)

            # Prominent DOWNLOAD NOW Action Button with animated arrow icon
            self.download_btn = DownloadActionButton()
            self.download_btn.bind(on_press=self.start_download)
            content.add_widget(self.download_btn)

            # Storage Destination Card
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
                height=dp(88),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28))
            self.downloads_title_lbl = Label(
                text="[b]Downloaded Media Library[/b]",
                markup=True,
                font_size="14sp",
                color=(0.95, 0.95, 1.0, 1.0),
                halign="left",
            )
            self.downloads_title_lbl.bind(size=self.downloads_title_lbl.setter("text_size"))
            top_row.add_widget(self.downloads_title_lbl)

            refresh_btn = IconActionButton(
                icon_path="shuffle.png",
                text="REFRESH",
                font_size="11sp",
                size_hint=(None, None),
                size=(dp(96), dp(28)),
                bg_color=(0.18, 0.22, 0.32, 1.0),
                text_color=(1.0, 0.75, 0.0, 1.0),
            )
            refresh_btn.bind(on_press=lambda ins: self.refresh_library())
            top_row.add_widget(refresh_btn)
            lib_header_card.add_widget(top_row)

            # Filter Row: [ALL] [VIDEOS] [AUDIO]
            filter_row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(30))
            self.filter_btn_all = Button(
                text="ALL",
                font_size="11sp",
                bold=True,
                background_color=(0.18, 0.24, 0.36, 1.0),
                color=(1, 0.75, 0, 1),
            )
            self.filter_btn_all.bind(on_press=lambda ins: self.set_downloads_filter("all"))

            self.filter_btn_videos = Button(
                text="VIDEOS (.mp4)",
                font_size="11sp",
                bold=True,
                background_color=(0.12, 0.14, 0.20, 1.0),
                color=(0.7, 0.75, 0.85, 1),
            )
            self.filter_btn_videos.bind(on_press=lambda ins: self.set_downloads_filter("videos"))

            self.filter_btn_audio = Button(
                text="AUDIO (.mp3)",
                font_size="11sp",
                bold=True,
                background_color=(0.12, 0.14, 0.20, 1.0),
                color=(0.7, 0.75, 0.85, 1),
            )
            self.filter_btn_audio.bind(on_press=lambda ins: self.set_downloads_filter("audio"))

            filter_row.add_widget(self.filter_btn_all)
            filter_row.add_widget(self.filter_btn_videos)
            filter_row.add_widget(self.filter_btn_audio)
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

        def set_downloads_filter(self, filter_type: str):
            self.active_filter = filter_type
            inactive_bg = (0.12, 0.14, 0.20, 1.0)
            inactive_col = (0.7, 0.75, 0.85, 1.0)
            active_bg = (0.18, 0.24, 0.36, 1.0)
            active_col = (1.0, 0.75, 0.0, 1.0)

            self.filter_btn_all.background_color = active_bg if filter_type == "all" else inactive_bg
            self.filter_btn_all.color = active_col if filter_type == "all" else inactive_col

            self.filter_btn_videos.background_color = active_bg if filter_type == "videos" else inactive_bg
            self.filter_btn_videos.color = active_col if filter_type == "videos" else inactive_col

            self.filter_btn_audio.background_color = active_bg if filter_type == "audio" else inactive_bg
            self.filter_btn_audio.color = active_col if filter_type == "audio" else inactive_col

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

        def add_video_result_card(self, item: Dict[str, Any]):
            """Create a video recommendation card with safe thumbnail and 1-tap GET button."""
            card = StyledCard(
                orientation="horizontal",
                padding=[dp(10), dp(8)],
                spacing=dp(10),
                size_hint_y=None,
                height=dp(86),
                bg_color=(0.10, 0.12, 0.18, 1.0),
            )

            # Thumbnail with safe error fallback to prevent red cross X
            thumb_url = item.get("thumb") or ""
            thumb = AsyncImage(
                source=thumb_url,
                size_hint=(None, None),
                size=(dp(96), dp(62)),
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

            # 1-Tap GET Button with download icon
            dl_btn = IconActionButton(
                icon_path="download_arrow.png",
                text="GET",
                font_size="11sp",
                size_hint=(None, None),
                size=(dp(68), dp(38)),
                bg_color=(1.0, 0.68, 0.0, 1.0),
                text_color=(0.04, 0.05, 0.08, 1.0),
            )
            dl_btn.bind(on_press=lambda ins, u=item["url"]: self.load_recommended_video(u))
            card.add_widget(dl_btn)

            self.recommendations_container.add_widget(card)

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
            """Load a video from search/recommendations into Home tab with live preview."""
            self.url_input.text = video_url
            self.switch_tab("home")
            self.fetch_preview(video_url)
            self.update_status("[color=#FFB300]Loaded from Videos![/color] Tap DOWNLOAD NOW.", 0)

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
            self.download_btn.text = "DOWNLOAD NOW"
            self.preview_card.height = 0
            self.preview_card.opacity = 0.0
            self.clipboard_banner.height = 0
            self.clipboard_banner.opacity = 0.0
            self.update_status("Ready. Paste a link or tap 'Share' from YouTube.", 0)

        def on_url_input_changed(self, instance, text):
            """Trigger real-time preview when user pastes or edits a valid YouTube link."""
            clean = text.strip()
            normalized = normalize_youtube_url(clean)
            if normalized and normalized != self.current_preview_url:
                self.current_preview_url = normalized
                self.fetch_preview(normalized)

        def fetch_preview(self, url: str):
            """Fetch video or playlist thumbnail and details in a background thread."""
            def preview_worker():
                try:
                    import yt_dlp
                    safe_logger = AndroidYTDLLogger()
                    ydl_opts = {
                        "extract_flat": "in_playlist",
                        "skip_download": True,
                        "logger": safe_logger,
                        "socket_timeout": 15,
                        "quiet": True,
                        "no_warnings": True,
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android", "web"]
                            }
                        },
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            return

                        is_playlist = info.get("_type") == "playlist" or "entries" in info
                        raw_title = info.get("title") or "YouTube Media"
                        clean_title = safe_display_text(raw_title)
                        uploader = safe_display_text(info.get("uploader") or info.get("channel") or "YouTube")
                        thumb = info.get("thumbnail") or ""

                        if is_playlist:
                            raw_entries = list(info.get("entries") or [])
                            entries = [e for e in raw_entries if e]
                            count = len(entries)
                            meta_str = f"Playlist ({count} videos) • {uploader}"
                            if entries and not thumb:
                                first_entry = entries[0]
                                if first_entry:
                                    thumb = first_entry.get("thumbnail") or (
                                        f"https://i.ytimg.com/vi/{first_entry.get('id')}/mqdefault.jpg" if first_entry.get("id") else ""
                                    )
                            btn_text = f"DOWNLOAD PLAYLIST ({count} VIDEOS)" if count > 1 else "DOWNLOAD NOW"
                        else:
                            dur = format_duration(info.get("duration"))
                            meta_str = f"{dur} • {uploader}"
                            btn_text = "DOWNLOAD NOW"

                        Clock.schedule_once(
                            lambda dt, t=clean_title, m=meta_str, th=thumb, b=btn_text: self.update_preview_ui(t, m, th, b)
                        )
                except Exception as e:
                    print(f"[Preview] Fetch notice: {e}")
                    Clock.schedule_once(
                        lambda dt: self.update_preview_ui("YouTube Media", "Ready to download", "", "DOWNLOAD NOW")
                    )

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

            self.preview_card.height = dp(76)
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
            self.status_label.text = text
            if progress_val is not None:
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

                # Scan media files
                all_files: List[Path] = []
                for ext in ("*.mp4", "*.m4a", "*.mp3", "*.mkv", "*.webm"):
                    all_files.extend(target_dir.glob(ext))

                # Sort newest first
                all_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

                # Update bottom nav badge
                self.nav_btn_downloads.text = f"DOWNLOADS ({len(all_files)})"

                # Apply active filter
                if self.active_filter == "videos":
                    media_files = [p for p in all_files if p.suffix.lower() in (".mp4", ".mkv", ".webm")]
                elif self.active_filter == "audio":
                    media_files = [p for p in all_files if p.suffix.lower() in (".mp3", ".m4a")]
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
                for media_path in media_files[:30]:
                    size_bytes = media_path.stat().st_size if media_path.exists() else 0
                    size_str = format_bytes(size_bytes)
                    is_audio_file = media_path.suffix.lower() in (".mp3", ".m4a")
                    tag_str = "[AUDIO]" if is_audio_file else "[VIDEO]"
                    tag_color = "#FFA000" if is_audio_file else "#00E676"

                    row = StyledCard(
                        orientation="horizontal",
                        padding=[dp(10), dp(6)],
                        spacing=dp(8),
                        size_hint_y=None,
                        height=dp(52),
                        bg_color=(0.10, 0.12, 0.18, 1.0),
                    )

                    clean_name = safe_display_text(media_path.stem)
                    if len(clean_name) > 28:
                        clean_name = clean_name[:25] + "..."

                    item_lbl = Label(
                        text=f"[b][color={tag_color}]{tag_str}[/color] {clean_name}[/b]\n[size=10sp][color=#90CAF9]{size_str}[/color] • [color=#78909C]{media_path.suffix.upper()}[/color][/size]",
                        markup=True,
                        font_size="11.5sp",
                        color=(0.92, 0.94, 0.98, 1.0),
                        size_hint_x=1.0,
                        halign="left",
                        valign="middle",
                    )
                    item_lbl.bind(size=item_lbl.setter("text_size"))
                    row.add_widget(item_lbl)

                    # PLAY BUTTON with icon
                    play_btn = IconActionButton(
                        icon_path="play.png",
                        text="PLAY",
                        font_size="11sp",
                        size_hint=(None, None),
                        size=(dp(72), dp(34)),
                        bg_color=(0.08, 0.50, 0.24, 1.0),
                        text_color=(1, 1, 1, 1),
                    )
                    play_btn.bind(on_press=lambda ins, p=media_path: open_media_file(p))
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
                if success:
                    Clock.schedule_once(
                        lambda dt: self.update_status(f"[color=#00E676]Deleted:[/color] {file_path.name[:25]}", 0)
                    )
                else:
                    Clock.schedule_once(
                        lambda dt: self.update_status(f"[color=#FFB300]Removed from list:[/color] {file_path.name[:25]}", 0)
                    )

            threading.Thread(target=async_delete, daemon=True).start()

        # -----------------------------------------------------------------
        # Download Execution Logic (Strict Filename Truncation + Auto-Fallback)
        # -----------------------------------------------------------------
        def start_download(self, instance):
            """Validate inputs and launch background download thread."""
            url = self.url_input.text.strip()
            if not url:
                self.update_status("[color=#FF5252]Please paste a YouTube link first![/color]", 0)
                return

            normalized = normalize_youtube_url(url)
            if not normalized:
                self.update_status("[color=#FF5252]Invalid link. Paste a valid YouTube URL.[/color]", 0)
                return

            url = normalized
            selected_format = self.quality_spinner.text
            is_audio = "Audio" in selected_format

            self.download_btn.disabled = True
            self.update_status("Starting download engine...", 5)

            def worker():
                try:
                    import yt_dlp

                    target_dir = get_android_download_dir()
                    target_dir.mkdir(parents=True, exist_ok=True)

                    Clock.schedule_once(
                        lambda dt: self.update_status("Resolving streams & metadata...", 12)
                    )

                    current_item_meta = {"index": 1, "total": 1, "title": "Video"}

                    # Progress callback to animate Kivy ProgressBar and Android Notification Bar
                    def progress_hook(d):
                        if d.get("status") == "downloading":
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
                                    status_msg = f"[{cur_i}/{tot}] {overall_pct}% ({pct}%) • {cur_t[:18]}...{speed_str}"
                                    notif_pct = overall_pct
                                else:
                                    overall_pct = pct
                                    status_msg = f"Downloading: {pct}%{speed_str}"
                                    notif_pct = pct

                                Clock.schedule_once(
                                    lambda dt, msg=status_msg, p=overall_pct: self.update_status(msg, p)
                                )

                                # Update Android notification bar at throttled interval
                                now = time.time()
                                if (now - self.last_notif_time) > 1.2 or pct >= 99:
                                    self.last_notif_time = now
                                    notif_title = f"[{cur_i}/{tot}] {cur_t[:30]}" if tot > 1 else f"Downloading: {cur_t[:30]}"
                                    self.notification_manager.show_progress(notif_title, notif_pct, speed_str)

                        elif d.get("status") == "finished":
                            Clock.schedule_once(
                                lambda dt: self.update_status("Processing & saving media to storage...", 95)
                            )

                    has_ffmpeg = bool(shutil.which("ffmpeg"))
                    safe_logger = AndroidYTDLLogger()

                    # Base options for downloading individual media items cleanly
                    base_ydl_opts = {
                        "restrictfilenames": True,      # Replaces non-ASCII & special characters to prevent Android Errno 36
                        "windowsfilenames": True,       # Strips forbidden filesystem characters across all filesystems
                        "trim_file_name": 45,           # Hard caps filename length to 45 chars
                        "progress_hooks": [progress_hook],
                        "logger": safe_logger,
                        "socket_timeout": 35,
                        "nocheckcertificate": False,
                        "quiet": True,
                        "no_warnings": True,
                        "no_color": True,
                        "nooverwrites": False,          # Prevent silent skip when downloading new videos
                        "continuedl": False,            # Clean download stream
                        "noplaylist": True,             # In per-item loop, download single video without re-extracting playlist
                        "concurrent_fragment_downloads": 4,
                        "buffersize": 1048576,
                        "http_chunk_size": 10485760,
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android", "web"]
                            }
                        },
                    }

                    if is_audio:
                        if "MP3" in selected_format:
                            if has_ffmpeg:
                                base_ydl_opts["format"] = "bestaudio/best"
                                base_ydl_opts["postprocessors"] = [{
                                    "key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3",
                                    "preferredquality": "192",
                                }]
                            else:
                                base_ydl_opts["format"] = "140/bestaudio[ext=m4a]/bestaudio/18/best"
                        else:
                            # Fast M4A AAC
                            base_ydl_opts["format"] = "140/bestaudio[ext=m4a]/bestaudio/best"
                    else:
                        if "360p" in selected_format:
                            # Explicit 360p fast mode
                            base_ydl_opts["format"] = "18/best[height<=360][vcodec!=none][acodec!=none]/best"
                        elif "720p" in selected_format:
                            # Explicit 720p HD mode
                            if has_ffmpeg:
                                base_ydl_opts["format"] = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/22/best[height<=720]/18/best"
                            else:
                                base_ydl_opts["format"] = "22/best[height<=720][vcodec!=none][acodec!=none]/18/best"
                        else:
                            # Max Quality: 1080p Full HD -> 720p HD -> 360p (Max to Min priority)
                            if has_ffmpeg:
                                base_ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/22/best[height<=1080]/best[height<=720]/18/best"
                            else:
                                base_ydl_opts["format"] = "22/best[height<=1080][vcodec!=none][acodec!=none]/best[height<=720][vcodec!=none][acodec!=none]/18/best"

                    # 1. Fast metadata extraction (without format restrictions) to inspect playlist vs single video
                    flat_opts = {
                        "extract_flat": "in_playlist",
                        "skip_download": True,
                        "logger": safe_logger,
                        "socket_timeout": 25,
                        "quiet": True,
                        "no_warnings": True,
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android", "web"]
                            }
                        },
                    }
                    with yt_dlp.YoutubeDL(flat_opts) as flat_ydl:
                        media_meta = flat_ydl.extract_info(url, download=False)

                    if not media_meta:
                        raise RuntimeError("Could not retrieve media details.")

                    is_playlist = media_meta.get("_type") == "playlist" or "entries" in media_meta
                    raw_entries = list(media_meta.get("entries") or []) if is_playlist else [media_meta]
                    entries = [e for e in raw_entries if e]
                    total_count = len(entries) if entries else 1

                    current_item_meta["total"] = total_count

                    if is_playlist and total_count > 1:
                        Clock.schedule_once(
                            lambda dt, cnt=total_count: self.update_status(
                                f"[color=#FFB300]Playlist Detected:[/color] Starting download of {cnt} videos...", 5
                            )
                        )

                    saved_files: List[Path] = []
                    skipped_count = 0

                    # 2. Iterate through items and download each with canonical watch URL and unique ID
                    for idx, item in enumerate(entries, start=1):
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

                        # CRITICAL: Always resolve canonical watch URL so yt-dlp uses YouTube extractor, not generic videoplayback
                        item_url = get_canonical_video_url(item, fallback_url=url)
                        item_thumb = item.get("thumbnail") or (f"https://i.ytimg.com/vi/{item_id}/hqdefault.jpg" if item_id else None)
                        item_uploader = item.get("uploader") or item.get("channel") or media_meta.get("uploader") or "MSK YTDL"

                        current_item_meta["index"] = idx
                        current_item_meta["title"] = raw_item_title

                        if total_count > 1:
                            overall_start_pct = int(((idx - 1) / total_count) * 100)
                            Clock.schedule_once(
                                lambda dt, i=idx, tot=total_count, t=raw_item_title, p=overall_start_pct: self.update_status(
                                    f"Starting [{i}/{tot}]: {safe_display_text(t)[:28]}...", p
                                )
                            )
                            self.notification_manager.show_progress(f"[{idx}/{total_count}] {raw_item_title}", overall_start_pct)

                        # Set individual item output template with clean title and unique ID
                        item_opts = dict(base_ydl_opts)
                        if total_count > 1:
                            item_opts["outtmpl"] = str(target_dir / f"[{idx:02d}] %(title).35s [%(id)s].%(ext)s")
                        else:
                            item_opts["outtmpl"] = str(target_dir / "%(title).40s [%(id)s].%(ext)s")

                        try:
                            with yt_dlp.YoutubeDL(item_opts) as ydl:
                                info = ydl.extract_info(item_url, download=True)
                        except Exception as dl_err:
                            err_str = str(dl_err)
                            if "File name too long" in err_str or "Errno 36" in err_str:
                                print(f"[Download] Retrying with short ID filename due to: {err_str}")
                                fallback_opts = dict(item_opts)
                                fallback_opts["outtmpl"] = str(target_dir / "%(id)s.%(ext)s")
                                with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                                    info = ydl_fb.extract_info(item_url, download=True)
                            elif total_count > 1:
                                print(f"[Playlist] Skipping item #{idx} ({raw_item_title}) due to: {dl_err}")
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

                        # Locate saved file
                        saved_path: Optional[Path] = None
                        if "requested_downloads" in info and info["requested_downloads"]:
                            fp = info["requested_downloads"][0].get("filepath")
                            if fp and Path(fp).exists():
                                saved_path = Path(fp)

                        if not saved_path:
                            try:
                                prepared = ydl.prepare_filename(info)
                                if Path(prepared).exists():
                                    saved_path = Path(prepared)
                            except Exception:
                                pass

                        if not saved_path and item_id:
                            candidates = list(target_dir.glob(f"*{item_id}*"))
                            if candidates:
                                saved_path = candidates[0]

                        # Critical safety: Check if file was saved as 'videoplayback' and rename immediately
                        if not saved_path or "videoplayback" in saved_path.name.lower():
                            for p in target_dir.glob("*videoplayback*"):
                                if p.is_file():
                                    ext = p.suffix or (".mp4" if not is_audio else ".m4a")
                                    fixed_name = f"[{idx:02d}] {clean_title} [{item_id}]{ext}" if total_count > 1 else f"{clean_title} [{item_id}]{ext}"
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

                        if saved_path and saved_path.exists():
                            # Embed HQ Album Art & ID3 Tags for Audio
                            if is_audio:
                                embed_audio_metadata(saved_path, raw_item_title, item_uploader, item_thumb)

                            # Register in Android MediaStore Gallery / Music library
                            scan_media_file(saved_path)
                            saved_files.append(saved_path)

                    # Download Complete Actions
                    if saved_files:
                        last_file = saved_files[-1]
                        if total_count > 1:
                            msg = f"[color=#00E676]Playlist Complete![/color] {len(saved_files)} of {total_count} saved."
                            self.notification_manager.show_finished("MSK YTDL Playlist", f"{len(saved_files)} videos saved")
                        else:
                            msg = f"[color=#00E676]Done![/color] Saved: {last_file.name[:32]}"
                            self.notification_manager.show_finished("MSK YTDL", last_file.name[:32])

                        Clock.schedule_once(lambda dt, m=msg: self.update_status(m, 100))
                    else:
                        Clock.schedule_once(
                            lambda dt: self.update_status("[color=#00E676]Download completed![/color]", 100)
                        )

                    # Refresh offline library listing and badge
                    Clock.schedule_once(lambda dt: self.refresh_library(), 0.5)

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.notification_manager.cancel()
                    err_msg = str(e)
                    if "File name too long" in err_msg or "Errno 36" in err_msg:
                        user_friendly_err = "Storage filename error. Please try downloading again."
                    elif "Requested format is not available" in err_msg:
                        user_friendly_err = "Selected format not available for this video."
                    elif "Video unavailable" in err_msg or "Private video" in err_msg:
                        user_friendly_err = "Video is private or unavailable."
                    elif "Sign in to confirm" in err_msg or "age-restricted" in err_msg:
                        user_friendly_err = "Age-restricted video: sign-in required."
                    elif "getaddrinfo failed" in err_msg or "timed out" in err_msg or "Network is unreachable" in err_msg:
                        user_friendly_err = "Network error. Check internet connection."
                    elif "ExtractorError" in err_msg or "not a valid URL" in err_msg:
                        user_friendly_err = "Invalid YouTube URL. Please check the link."
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
                    def reset_ui_state(dt=None):
                        self.download_btn.disabled = False
                        self.download_btn.text = "DOWNLOAD NOW"
                        self.current_preview_url = ""
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

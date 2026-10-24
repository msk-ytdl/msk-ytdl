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
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import AsyncImage, Image
    from kivy.uix.label import Label
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
    Robustly extract and canonicalize any YouTube link, query fragment, or video ID.
    Handles:
      - 'v=UQyh7QIVaDU&si=...'
      - 'watch?v=UQyh7QIVaDU'
      - 'UQyh7QIVaDU' (raw 11-char ID)
      - 'https://youtu.be/UQyh7QIVaDU?si=...'
      - 'https://www.youtube.com/watch?v=UQyh7QIVaDU'
      - 'https://www.youtube.com/shorts/UQyh7QIVaDU'
      - 'https://www.youtube.com/playlist?list=PL...'
      - Text containing links shared from YouTube app
    """
    if not text:
        return None
    raw = text.strip()

    # 1. Full YouTube watch, youtu.be, shorts, live, or embed URL with video ID
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
        return f"https://www.youtube.com/watch?v={vid}"

    # 2. Playlist URL
    match_plist = re.search(
        r"(https?://(?:www\.|m\.)?youtube\.com/playlist\?list=[a-zA-Z0-9_-]+)",
        raw,
    )
    if match_plist:
        return match_plist.group(1)

    # 3. Query fragment: 'v=UQyh7QIVaDU' or 'watch?v=UQyh7QIVaDU'
    match_query = re.search(r"(?:watch\?)?v=([a-zA-Z0-9_-]{11})", raw)
    if match_query:
        return f"https://www.youtube.com/watch?v={match_query.group(1)}"

    # 4. Raw 11-character video ID alone (e.g. 'UQyh7QIVaDU')
    match_raw_id = re.match(r"^[a-zA-Z0-9_-]{11}$", raw)
    if match_raw_id:
        return f"https://www.youtube.com/watch?v={raw}"

    # 5. General web link fallback
    match_gen = re.search(r"(https?://[^\s]+)", raw)
    if match_gen:
        return match_gen.group(1)

    return None


def extract_youtube_url(text: str) -> Optional[str]:
    """Compatibility alias for normalize_youtube_url."""
    return normalize_youtube_url(text)


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
    """Notify Android's MediaScannerConnection so the file appears in Gallery/Music players."""
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        MediaScannerConnection = autoclass("android.media.MediaScannerConnection")
        ctx = PythonActivity.mActivity
        MediaScannerConnection.scanFile(ctx, [str(filepath.resolve())], None, None)
        print(f"[Android] MediaScannerConnection indexed: {filepath.name}")
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
    """Delete a media file from storage and update Android MediaStore."""
    try:
        if filepath.exists():
            filepath.unlink()
            scan_media_file(filepath)
            return True
    except Exception as e:
        print(f"[DeleteMedia] Error deleting file: {e}")
    return False


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
        # Header Card Builder
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

            header_text_box = BoxLayout(orientation="vertical", spacing=dp(1))
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
            return header_card

        # -----------------------------------------------------------------
        # Bottom Navigation Footer Bar Builder
        # -----------------------------------------------------------------
        def create_bottom_nav(self) -> BoxLayout:
            nav_bar = StyledCard(
                orientation="horizontal",
                padding=[dp(6), dp(4)],
                spacing=dp(6),
                size_hint_y=None,
                height=dp(52),
                bg_color=(0.07, 0.08, 0.13, 1.0),
            )

            self.nav_btn_home = Button(
                text="HOME",
                font_size="12sp",
                bold=True,
                background_color=(0.18, 0.22, 0.32, 1.0),
                color=(1.0, 0.72, 0.0, 1.0),  # Active amber
            )
            self.nav_btn_home.bind(on_press=lambda ins: self.switch_tab("home"))
            nav_bar.add_widget(self.nav_btn_home)

            self.nav_btn_downloads = Button(
                text="DOWNLOADS",
                font_size="12sp",
                bold=True,
                background_color=(0.09, 0.11, 0.16, 1.0),
                color=(0.65, 0.70, 0.80, 1.0),
            )
            self.nav_btn_downloads.bind(on_press=lambda ins: self.switch_tab("downloads"))
            nav_bar.add_widget(self.nav_btn_downloads)

            self.nav_btn_videos = Button(
                text="VIDEOS",
                font_size="12sp",
                bold=True,
                background_color=(0.09, 0.11, 0.16, 1.0),
                color=(0.65, 0.70, 0.80, 1.0),
            )
            self.nav_btn_videos.bind(on_press=lambda ins: self.switch_tab("videos"))
            nav_bar.add_widget(self.nav_btn_videos)

            return nav_bar

        # -----------------------------------------------------------------
        # Tab Switching Logic
        # -----------------------------------------------------------------
        def switch_tab(self, tab_name: str):
            if self.active_tab == tab_name and self.main_container.children:
                return

            self.active_tab = tab_name
            self.main_container.clear_widgets()

            # Colors
            inactive_bg = (0.09, 0.11, 0.16, 1.0)
            inactive_col = (0.65, 0.70, 0.80, 1.0)
            active_bg = (0.18, 0.22, 0.32, 1.0)
            active_col = (1.0, 0.72, 0.0, 1.0)

            # Reset buttons
            self.nav_btn_home.background_color = inactive_bg
            self.nav_btn_home.color = inactive_col
            self.nav_btn_downloads.background_color = inactive_bg
            self.nav_btn_downloads.color = inactive_col
            self.nav_btn_videos.background_color = inactive_bg
            self.nav_btn_videos.color = inactive_col

            if tab_name == "home":
                self.nav_btn_home.background_color = active_bg
                self.nav_btn_home.color = active_col
                self.main_container.add_widget(self.home_view)
            elif tab_name == "downloads":
                self.nav_btn_downloads.background_color = active_bg
                self.nav_btn_downloads.color = active_col
                self.main_container.add_widget(self.downloads_view)
                Clock.schedule_once(lambda dt: self.refresh_library(), 0.05)
            elif tab_name == "videos":
                self.nav_btn_videos.background_color = active_bg
                self.nav_btn_videos.color = active_col
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

            # Action Buttons Row: PASTE & CLEAR
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(36))
            paste_btn = Button(
                text="PASTE LINK",
                font_size="12sp",
                bold=True,
                background_color=(0.20, 0.26, 0.40, 1.0),
                color=(1, 0.75, 0, 1),
            )
            paste_btn.bind(on_press=self.on_paste_clicked)

            clear_btn = Button(
                text="CLEAR",
                font_size="12sp",
                bold=True,
                background_color=(0.18, 0.20, 0.28, 1.0),
                color=(0.8, 0.85, 0.95, 1),
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
                text="Video (MP4 - Best Available)",
                values=(
                    "Video (MP4 - Best Available)",
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

            # Prominent DOWNLOAD NOW Action Button
            self.download_btn = Button(
                text="DOWNLOAD NOW",
                font_size="16sp",
                bold=True,
                background_color=(1.0, 0.65, 0.0, 1.0),  # Vivid Amber Gold
                color=(0.04, 0.05, 0.08, 1.0),
                size_hint_y=None,
                height=dp(52),
            )
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

            refresh_btn = Button(
                text="REFRESH",
                font_size="11sp",
                bold=True,
                size_hint=(None, None),
                size=(dp(84), dp(28)),
                background_color=(0.18, 0.22, 0.32, 1.0),
                color=(1.0, 0.75, 0.0, 1.0),
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
        # View 3: Videos View (Recommended Videos Based on Downloads)
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
                padding=[dp(14), dp(12)],
                spacing=dp(3),
                size_hint_y=None,
                height=dp(64),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            rec_title = Label(
                text="[b]Recommended Videos & Music[/b]",
                markup=True,
                font_size="14sp",
                color=(0.95, 0.95, 1.0, 1.0),
                size_hint_y=None,
                height=dp(22),
                halign="left",
            )
            rec_title.bind(size=rec_title.setter("text_size"))

            rec_subtitle = Label(
                text="Trending & recommended based on your recent downloads",
                font_size="11sp",
                color=(0.65, 0.70, 0.80, 1.0),
                size_hint_y=None,
                height=dp(18),
                halign="left",
            )
            rec_subtitle.bind(size=rec_subtitle.setter("text_size"))

            rec_header_card.add_widget(rec_title)
            rec_header_card.add_widget(rec_subtitle)
            content.add_widget(rec_header_card)

            # Recommendations Container
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
        # Populate Recommendations Logic
        # -----------------------------------------------------------------
        @mainthread
        def populate_recommendations(self):
            """Generate curated and dynamic recommendations based on previously downloaded files."""
            self.recommendations_container.clear_widgets()

            # Analyze downloaded files to find context keywords
            target_dir = get_android_download_dir()
            past_titles = []
            if target_dir.exists():
                for f in target_dir.glob("*.*"):
                    if f.suffix.lower() in (".mp4", ".mp3", ".m4a", ".webm"):
                        past_titles.append(f.stem.lower())

            # Curated catalog of high-interest videos across categories
            catalog = [
                {
                    "title": "1,000 Termites vs. House (Full Documentary)",
                    "channel": "AntsCanada",
                    "duration": "12:13",
                    "url": "https://www.youtube.com/watch?v=UqmP868N59w",
                    "thumb": "https://i.ytimg.com/vi/UqmP868N59w/mqdefault.jpg",
                    "category": "Documentary",
                },
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
                    "category": "Education & Coding",
                },
                {
                    "title": "Relaxing Lofi Beats for Study & Focus",
                    "channel": "Lofi Girl",
                    "duration": "Live / Music",
                    "url": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
                    "thumb": "https://i.ytimg.com/vi/jfKfPfyJRdk/mqdefault.jpg",
                    "category": "Music Lo-Fi",
                },
                {
                    "title": "How to Create AI Movies & Animation with Free Tools",
                    "channel": "AI Creators",
                    "duration": "14:48",
                    "url": "https://www.youtube.com/watch?v=tF4DML7FIWk",
                    "thumb": "https://i.ytimg.com/vi/tF4DML7FIWk/mqdefault.jpg",
                    "category": "Tech & AI",
                },
                {
                    "title": "Best Royalty Free Gaming Music Mix (NCS)",
                    "channel": "NoCopyrightSounds",
                    "duration": "32:15",
                    "url": "https://www.youtube.com/watch?v=7tNtU5X-q_0",
                    "thumb": "https://i.ytimg.com/vi/7tNtU5X-q_0/mqdefault.jpg",
                    "category": "Music Mix",
                },
            ]

            # Render recommendation cards
            for item in catalog:
                card = StyledCard(
                    orientation="horizontal",
                    padding=[dp(10), dp(8)],
                    spacing=dp(10),
                    size_hint_y=None,
                    height=dp(86),
                    bg_color=(0.10, 0.12, 0.18, 1.0),
                )

                # Thumbnail image
                thumb = AsyncImage(
                    source=item["thumb"],
                    size_hint=(None, None),
                    size=(dp(96), dp(62)),
                    allow_stretch=True,
                    keep_ratio=True,
                )
                card.add_widget(thumb)

                # Info column
                info_col = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=1.0)
                clean_t = safe_display_text(item["title"])
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

                meta_lbl = Label(
                    text=f"{item['duration']} • {item['category']}",
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

                # 1-Tap Download Button
                dl_btn = Button(
                    text="GET",
                    font_size="11sp",
                    bold=True,
                    size_hint=(None, None),
                    size=(dp(54), dp(40)),
                    background_color=(1.0, 0.68, 0.0, 1.0),
                    color=(0.04, 0.05, 0.08, 1.0),
                )
                # Binds download button to load link into Home tab and trigger download
                dl_btn.bind(on_press=lambda ins, u=item["url"]: self.load_recommended_video(u))
                card.add_widget(dl_btn)

                self.recommendations_container.add_widget(card)

        def load_recommended_video(self, video_url: str):
            """Load a video from recommendations into the Home tab."""
            self.url_input.text = video_url
            self.switch_tab("home")
            self.update_status("[color=#FFB300]Loaded recommended video![/color] Tap DOWNLOAD NOW.", 0)

        # -----------------------------------------------------------------
        # Clipboard Auto-Detect Logic
        # -----------------------------------------------------------------
        def check_clipboard(self, dt=None):
            """Poll clipboard safely; if YouTube URL found and not already loaded, show banner."""
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
            """Fetch video thumbnail and details in a background thread."""
            def preview_worker():
                try:
                    import yt_dlp
                    safe_logger = AndroidYTDLLogger()
                    ydl_opts = {
                        "extract_flat": True,
                        "skip_download": True,
                        "logger": safe_logger,
                        "socket_timeout": 15,
                        "quiet": True,
                        "no_warnings": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            return

                        is_playlist = info.get("_type") == "playlist" or "entries" in info
                        raw_title = info.get("title") or "YouTube Video"
                        clean_title = safe_display_text(raw_title)
                        uploader = safe_display_text(info.get("uploader") or info.get("channel") or "YouTube")
                        thumb = info.get("thumbnail") or ""

                        if is_playlist:
                            entries = list(info.get("entries") or [])
                            count = len(entries)
                            meta_str = f"Playlist ({count} items) • {uploader}"
                            if entries and not thumb:
                                thumb = entries[0].get("thumbnail") or ""
                        else:
                            dur = format_duration(info.get("duration"))
                            meta_str = f"{dur} • {uploader}"

                        Clock.schedule_once(
                            lambda dt, t=clean_title, m=meta_str, th=thumb: self.update_preview_ui(t, m, th)
                        )
                except Exception as e:
                    print(f"[Preview] Fetch notice: {e}")
                    Clock.schedule_once(
                        lambda dt: self.update_preview_ui("YouTube Media", "Ready to download", "")
                    )

            threading.Thread(target=preview_worker, daemon=True).start()

        @mainthread
        def update_preview_ui(self, title: str, meta: str, thumb_url: str):
            """Update the preview card on the main Kivy UI thread."""
            clean_title = title if len(title) <= 55 else title[:52] + "..."
            self.preview_title.text = f"[b]{clean_title}[/b]"
            self.preview_meta.text = meta
            if thumb_url:
                self.preview_thumb.source = thumb_url
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

                    # PLAY BUTTON
                    play_btn = Button(
                        text="PLAY",
                        font_size="11sp",
                        bold=True,
                        size_hint=(None, None),
                        size=(dp(58), dp(34)),
                        background_color=(0.08, 0.50, 0.24, 1.0),
                        color=(1, 1, 1, 1),
                    )
                    play_btn.bind(on_press=lambda ins, p=media_path: open_media_file(p))
                    row.add_widget(play_btn)

                    # DELETE BUTTON
                    del_btn = Button(
                        text="DEL",
                        font_size="11sp",
                        bold=True,
                        size_hint=(None, None),
                        size=(dp(48), dp(34)),
                        background_color=(0.60, 0.12, 0.12, 1.0),
                        color=(1, 1, 1, 1),
                    )
                    del_btn.bind(on_press=lambda ins, p=media_path: self.on_delete_clicked(p))
                    row.add_widget(del_btn)

                    self.library_container.add_widget(row)

            except Exception as e:
                print(f"[Library] Refresh error: {e}")

        def on_delete_clicked(self, file_path: Path):
            """Delete file from device and refresh list."""
            if delete_media_file(file_path):
                self.refresh_library()
                self.update_status(f"[color=#00E676]Deleted:[/color] {file_path.name[:30]}", 0)

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

                    # Progress callback to animate Kivy ProgressBar and Android Notification Bar
                    def progress_hook(d):
                        if d.get("status") == "downloading":
                            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                            downloaded = d.get("downloaded_bytes") or 0
                            if total > 0:
                                pct = int((downloaded / total) * 100)
                                speed = d.get("speed")
                                speed_str = f" • {format_bytes(speed)}/s" if speed else ""
                                Clock.schedule_once(
                                    lambda dt, p=pct, s=speed_str: self.update_status(
                                        f"Downloading: {p}%{s}", p
                                    )
                                )

                                # Update Android notification bar at throttled interval
                                now = time.time()
                                if (now - self.last_notif_time) > 1.2 or pct >= 99:
                                    self.last_notif_time = now
                                    self.notification_manager.show_progress("MSK YTDL", pct, speed_str)

                        elif d.get("status") == "finished":
                            Clock.schedule_once(
                                lambda dt: self.update_status("Processing & saving media to storage...", 95)
                            )

                    has_ffmpeg = bool(shutil.which("ffmpeg"))

                    # Safe filename template (limited to 40 chars + ASCII restricted to prevent [Errno 36])
                    safe_outtmpl = str(target_dir / "%(title).40s [%(id)s].%(ext)s")
                    safe_logger = AndroidYTDLLogger()

                    ydl_opts = {
                        "outtmpl": safe_outtmpl,
                        "restrictfilenames": True,      # CRITICAL: Replaces non-ASCII & special chars to prevent Android FUSE Errno 36
                        "windowsfilenames": True,       # CRITICAL: Strips forbidden characters across all filesystems
                        "trim_file_name": 50,           # CRITICAL: Hard caps filename length to 50 chars
                        "progress_hooks": [progress_hook],
                        "logger": safe_logger,
                        "socket_timeout": 35,
                        "nocheckcertificate": False,
                        "quiet": True,
                        "no_warnings": True,
                        "no_color": True,
                        "concurrent_fragment_downloads": 4,
                        "buffersize": 1048576,
                        "http_chunk_size": 10485760,
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android", "ios", "web", "mweb"]
                            }
                        },
                    }

                    if is_audio:
                        if has_ffmpeg:
                            ydl_opts["format"] = "bestaudio/best"
                            ydl_opts["postprocessors"] = [{
                                "key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "192",
                            }]
                        else:
                            ydl_opts["format"] = "140/bestaudio[ext=m4a]/bestaudio/18/best"
                    else:
                        if "720p" in selected_format:
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                            else:
                                ydl_opts["format"] = "22/best[height<=720][ext=mp4]/18/best/bestvideo[height<=720]+bestaudio/best"
                        elif "360p" in selected_format:
                            ydl_opts["format"] = "18/best[height<=360][ext=mp4]/best[ext=mp4]/best"
                        else:
                            # Best Available
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo*+bestaudio/22/18/best"
                            else:
                                ydl_opts["format"] = "18/22/best[ext=mp4]/best/bestvideo*+bestaudio"

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Extract info first to check for playlists
                        media_meta = ydl.extract_info(url, download=False)
                        if not media_meta:
                            raise RuntimeError("Could not retrieve media details.")

                        is_playlist = media_meta.get("_type") == "playlist" or "entries" in media_meta
                        entries = list(media_meta.get("entries") or []) if is_playlist else [media_meta]
                        total_count = len(entries) if entries else 1

                        if is_playlist and total_count > 1:
                            Clock.schedule_once(
                                lambda dt, cnt=total_count: self.update_status(
                                    f"[color=#FFB300]Playlist Detected:[/color] Downloading {cnt} videos...", 10
                                )
                            )

                        saved_files: List[Path] = []

                        # Download items (handles both single video and multi-item playlist)
                        for idx, item in enumerate(entries, start=1):
                            item_title = item.get("title") or f"Item {idx}"
                            item_url = item.get("url") or item.get("webpage_url") or (f"https://www.youtube.com/watch?v={item.get('id')}" if item.get('id') else url)
                            item_thumb = item.get("thumbnail") or media_meta.get("thumbnail")
                            item_uploader = item.get("uploader") or item.get("channel") or media_meta.get("uploader") or "MSK YTDL"

                            if total_count > 1:
                                Clock.schedule_once(
                                    lambda dt, i=idx, tot=total_count, t=item_title: self.update_status(
                                        f"Item {i}/{tot}: {t[:35]}...", int((i - 1) / tot * 100)
                                    )
                                )
                                self.notification_manager.show_progress(f"[{idx}/{total_count}] {item_title}", int((idx - 1) / total_count * 100))

                            # Execute download with automatic fallback if filename too long occurs
                            try:
                                info = ydl.extract_info(item_url, download=True)
                            except Exception as dl_err:
                                err_str = str(dl_err)
                                if "File name too long" in err_str or "Errno 36" in err_str:
                                    print(f"[Download] Retrying with short ID filename due to: {err_str}")
                                    fallback_opts = dict(ydl_opts)
                                    fallback_opts["outtmpl"] = str(target_dir / "%(id)s.%(ext)s")
                                    with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                                        info = ydl_fb.extract_info(item_url, download=True)
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
                                prepared = ydl.prepare_filename(info)
                                if Path(prepared).exists():
                                    saved_path = Path(prepared)
                                else:
                                    candidates = list(target_dir.glob(f"*{info.get('id')}*"))
                                    if candidates:
                                        saved_path = candidates[0]

                            if saved_path and saved_path.exists():
                                # Feature 5: Embed High-Quality Album Art & Tags for MP3/M4A
                                if is_audio:
                                    embed_audio_metadata(saved_path, item_title, item_uploader, item_thumb)

                                # Register in Android MediaStore Gallery / Music library
                                scan_media_file(saved_path)
                                saved_files.append(saved_path)

                        # Download Complete Actions
                        if saved_files:
                            last_file = saved_files[-1]
                            # Completion Notification
                            self.notification_manager.show_finished("MSK YTDL", last_file.name)

                            msg = (
                                f"[color=#00E676]Playlist Done![/color] {len(saved_files)} items saved."
                                if total_count > 1
                                else f"[color=#00E676]Done![/color] Saved: {last_file.name}"
                            )
                            Clock.schedule_once(lambda dt, m=msg: self.update_status(m, 100))
                        else:
                            Clock.schedule_once(
                                lambda dt: self.update_status("[color=#00E676]Download completed![/color]", 100)
                            )

                        # Refresh library listing and update tab badge automatically
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
                    Clock.schedule_once(lambda dt: setattr(self.download_btn, "disabled", False))

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

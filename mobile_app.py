"""
Mobile graphical interface entry point for MSK YTDL on Android.
Publisher: MSK Software Solutions
Designed for touchscreen navigation, phone storage permissions, background downloading,
modern dark aesthetics, and direct integration with Android's "Share from YouTube" SEND Intent.
"""

import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

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
    from kivy.core.window import Window
    from kivy.graphics import Color, RoundedRectangle
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
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
      - Text containing links shared from YouTube app
    """
    if not text:
        return None
    raw = text.strip()

    # 1. Full YouTube watch, youtu.be, or shorts URL with video ID
    match_full = re.search(
        r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})|youtu\.be/([a-zA-Z0-9_-]{11})|youtube\.com/shorts/([a-zA-Z0-9_-]{11}))",
        raw,
    )
    if match_full:
        vid = match_full.group(1) or match_full.group(2) or match_full.group(3)
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


def format_bytes(num_bytes: Optional[float]) -> str:
    """Format speed / byte count to human-readable string."""
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def request_android_permissions():
    """Request runtime storage permissions on Android (API 21 through 35)."""
    try:
        from android.permissions import Permission, request_permissions
        perms = [
            Permission.INTERNET,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE,
        ]
        # On Android 13+ (API 33+), granular media permissions replace external storage
        for p in ("READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "READ_MEDIA_IMAGES"):
            if hasattr(Permission, p):
                perms.append(getattr(Permission, p))
        request_permissions(perms)
    except Exception as e:
        print(f"[Android] Permission request notice: {e}")


def get_android_download_dir() -> Path:
    """
    Resolve a guaranteed writable destination directory on Android.
    Prefers public Downloads folder; falls back to app-specific external storage.
    """
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

            # Request Android storage permissions on startup
            request_android_permissions()

            # Listen for Android "Share from YouTube" intents (warm start)
            try:
                import android.activity
                android.activity.bind(on_new_intent=self.on_new_intent)
            except Exception:
                pass

            # Root ScrollView to ensure all screen sizes render with perfect spacing
            scroll_root = ScrollView(do_scroll_x=False, do_scroll_y=True)

            content = BoxLayout(
                orientation="vertical",
                padding=[dp(16), dp(20), dp(16), dp(24)],
                spacing=dp(14),
                size_hint_y=None,
            )
            content.bind(minimum_height=content.setter("height"))

            # -------------------------------------------------------------
            # 1. Header Card (MSK YTDL Branding)
            # -------------------------------------------------------------
            header_card = StyledCard(
                orientation="vertical",
                padding=[dp(16), dp(16)],
                spacing=dp(4),
                size_hint_y=None,
                height=dp(80),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            brand_label = Label(
                text="[b][color=#FFB300]MSK[/color] YTDL[/b]",
                markup=True,
                font_size="24sp",
                size_hint_y=None,
                height=dp(32),
            )
            tagline = Label(
                text="YouTube Downloader by MSK Software Solutions",
                font_size="12sp",
                color=(0.7, 0.75, 0.85, 1.0),
                size_hint_y=None,
                height=dp(20),
            )
            header_card.add_widget(brand_label)
            header_card.add_widget(tagline)
            content.add_widget(header_card)

            # -------------------------------------------------------------
            # 2. URL Input Card with PASTE and CLEAR Buttons
            # -------------------------------------------------------------
            input_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(14)],
                spacing=dp(10),
                size_hint_y=None,
                height=dp(146),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            input_title = Label(
                text="[b]YouTube Video Link[/b]",
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
                font_size="14sp",
                size_hint_y=None,
                height=dp(46),
                background_color=(0.14, 0.16, 0.24, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.75, 0, 1),
                padding=[dp(10), dp(12)],
            )
            input_card.add_widget(self.url_input)

            # Button Actions Row: PASTE & CLEAR
            btn_row = BoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(38))
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

            # -------------------------------------------------------------
            # 3. Format & Quality Selector Card
            # -------------------------------------------------------------
            format_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(14)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(95),
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
                    "Audio Only (M4A / MP3 Music)",
                ),
                size_hint_y=None,
                height=dp(42),
                background_color=(0.16, 0.19, 0.28, 1.0),
                color=(1, 1, 1, 1),
                font_size="13sp",
            )
            format_card.add_widget(self.quality_spinner)
            content.add_widget(format_card)

            # -------------------------------------------------------------
            # 4. Progress & Status Card
            # -------------------------------------------------------------
            status_card = StyledCard(
                orientation="vertical",
                padding=[dp(14), dp(12)],
                spacing=dp(8),
                size_hint_y=None,
                height=dp(88),
                bg_color=(0.09, 0.11, 0.17, 1.0),
            )
            self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(14))
            status_card.add_widget(self.progress_bar)

            self.status_label = Label(
                text="Ready. Paste a link or tap 'Share' from YouTube.",
                markup=True,
                font_size="12sp",
                color=(0.85, 0.88, 0.95, 1.0),
                size_hint_y=None,
                height=dp(42),
                halign="center",
            )
            self.status_label.bind(size=self.status_label.setter("text_size"))
            status_card.add_widget(self.status_label)
            content.add_widget(status_card)

            # -------------------------------------------------------------
            # 5. Prominent DOWNLOAD NOW Action Button
            # -------------------------------------------------------------
            self.download_btn = Button(
                text="DOWNLOAD NOW",
                font_size="16sp",
                bold=True,
                background_color=(1.0, 0.65, 0.0, 1.0),  # Vivid Amber Gold
                color=(0.04, 0.05, 0.08, 1.0),
                size_hint_y=None,
                height=dp(54),
            )
            self.download_btn.bind(on_press=self.start_download)
            content.add_widget(self.download_btn)

            # -------------------------------------------------------------
            # 6. Storage Destination Card
            # -------------------------------------------------------------
            download_dir = get_android_download_dir()
            dest_card = StyledCard(
                orientation="horizontal",
                padding=[dp(12), dp(8)],
                size_hint_y=None,
                height=dp(38),
                bg_color=(0.07, 0.08, 0.13, 1.0),
            )
            self.storage_note = Label(
                text="Storage: Phone Storage > Download > YouTube",
                font_size="11sp",
                color=(0.55, 0.60, 0.70, 1.0),
            )
            dest_card.add_widget(self.storage_note)
            content.add_widget(dest_card)

            scroll_root.add_widget(content)

            # Check for incoming YouTube Share intent on cold startup
            Clock.schedule_once(self.check_initial_intent, 0.4)

            return scroll_root

        def on_paste_clicked(self, instance):
            """Handle PASTE button press from Android system clipboard."""
            try:
                clip_text = Clipboard.paste()
                if clip_text:
                    normalized = normalize_youtube_url(clip_text.strip()) or clip_text.strip()
                    self.url_input.text = normalized
                    self.update_status("[color=#FFB300]Link pasted & cleaned![/color] Tap DOWNLOAD NOW.", 0)
                else:
                    self.update_status("Clipboard is empty.", 0)
            except Exception as e:
                self.update_status(f"Paste notice: {e}", 0)

        def on_clear_clicked(self, instance):
            """Clear input and reset status."""
            self.url_input.text = ""
            self.update_status("Ready. Paste a link or tap 'Share' from YouTube.", 0)

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
                            self.url_input.text = normalized
                            self.update_status(
                                "[color=#FFB300]Received from YouTube![/color] Tap DOWNLOAD NOW.", 0
                            )
                            return

                # Case 2: VIEW Intent (User clicked YouTube link)
                if action == Intent.ACTION_VIEW:
                    data = intent.getData()
                    if data:
                        normalized = normalize_youtube_url(data.toString())
                        if normalized:
                            self.url_input.text = normalized
                            self.update_status(
                                "[color=#FFB300]Received YouTube link![/color] Tap DOWNLOAD NOW.", 0
                            )
            except Exception as e:
                print(f"[Android] handle_intent_payload error: {e}")

        def update_status(self, text: str, progress_val: Optional[float] = None):
            self.status_label.text = text
            if progress_val is not None:
                self.progress_bar.value = progress_val

        def start_download(self, instance):
            raw_text = self.url_input.text.strip()
            # Normalize URL to handle 'v=...', 'watch?v=...', raw IDs, and share messages
            url = normalize_youtube_url(raw_text)
            if not url:
                self.update_status("[color=#FF5252]Please enter a valid YouTube link or video ID![/color]")
                return

            # Keep input updated with normalized URL
            self.url_input.text = url

            self.download_btn.disabled = True
            self.update_status("Connecting to video stream...", 5)

            selected_format = self.quality_spinner.text
            is_audio = "Audio" in selected_format

            def worker():
                try:
                    import yt_dlp

                    target_dir = get_android_download_dir()
                    target_dir.mkdir(parents=True, exist_ok=True)

                    Clock.schedule_once(
                        lambda dt: self.update_status("Resolving streams & metadata...", 15)
                    )

                    # Progress callback to animate Kivy ProgressBar
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
                        elif d.get("status") == "finished":
                            Clock.schedule_once(
                                lambda dt: self.update_status("Saving media to storage...", 95)
                            )

                    has_ffmpeg = bool(shutil.which("ffmpeg"))

                    # Safe output template without special shell characters
                    outtmpl = str(target_dir / "%(title).80B [%(id)s].%(ext)s")

                    # Configure yt-dlp with safe custom logger to prevent Android buffer write errors
                    safe_logger = AndroidYTDLLogger()
                    ydl_opts = {
                        "outtmpl": outtmpl,
                        "progress_hooks": [progress_hook],
                        "logger": safe_logger,
                        "socket_timeout": 35,
                        "nocheckcertificate": False,
                        "quiet": True,
                        "no_warnings": True,
                        "restrictfilenames": False,
                        "no_color": True,
                        # Request android and web player clients to ensure YouTube serves
                        # progressive formats (format 18 360p / format 22 720p) that have
                        # audio and video in a single stream without requiring FFmpeg muxing.
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android", "web", "mweb"]
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
                            # Format 140 is YouTube 128k AAC M4A audio stream (plays natively on Android)
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
                            # Best Available: Prioritize progressive MP4 (format 18 / 22) for instant playback
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo*+bestaudio/22/18/best"
                            else:
                                ydl_opts["format"] = "18/22/best[ext=mp4]/best/bestvideo*+bestaudio"

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if not info:
                            raise RuntimeError("Could not retrieve media details.")

                        # Determine downloaded file location
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
                            # Trigger Android Media Scanner to index in Gallery/Music
                            scan_media_file(saved_path)
                            Clock.schedule_once(
                                lambda dt, name=saved_path.name: self.update_status(
                                    f"[color=#00E676]Done![/color] Saved: {name}", 100
                                )
                            )
                        else:
                            Clock.schedule_once(
                                lambda dt: self.update_status(
                                    "[color=#00E676]Download completed![/color]", 100
                                )
                            )

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    err_msg = str(e)
                    if "Requested format is not available" in err_msg:
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

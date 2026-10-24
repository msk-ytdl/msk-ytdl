"""
Mobile graphical interface entry point for MSK-YTDL on Android.
Designed for touchscreen navigation, phone storage permissions, background downloading,
and direct integration with Android's "Share from YouTube" SEND Intent.
"""

import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

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
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False


def extract_youtube_url(text: str) -> Optional[str]:
    """Extract canonical YouTube link from raw shared text or clipboard."""
    if not text:
        return None
    # 1. Look for standard YouTube video, shorts, or playlist links
    yt_regex = r"(https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=[^&\s]+|youtu\.be/[^?\s]+|youtube\.com/shorts/[^?\s]+|youtube\.com/playlist\?list=[^&\s]+))"
    match = re.search(yt_regex, text)
    if match:
        return match.group(1)

    # 2. Fallback to any general web URL in the text
    general_match = re.search(r"(https?://[^\s]+)", text)
    return general_match.group(1) if general_match else None


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
    class MSKDownloaderMobile(App):
        def build(self):
            self.title = "MSK Video Downloader"
            Window.clearcolor = (0.05, 0.06, 0.09, 1.0)  # Sleek dark VidMate background

            # Request Android storage permissions on startup
            request_android_permissions()

            # Listen for Android "Share from YouTube" intents (warm start)
            try:
                import android.activity
                android.activity.bind(on_new_intent=self.on_new_intent)
            except Exception:
                pass

            root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

            # Header / Logo Title
            header = Label(
                text="[b][color=#FFB300]MSK[/color] Video Downloader[/b]",
                markup=True,
                font_size="22sp",
                size_hint_y=None,
                height=dp(44),
            )
            root.add_widget(header)

            subtitle = Label(
                text="Paste link or tap 'Share' in YouTube to download",
                font_size="12sp",
                color=(0.65, 0.68, 0.75, 1.0),
                size_hint_y=None,
                height=dp(20),
            )
            root.add_widget(subtitle)

            # URL Input Box with PASTE & CLEAR Buttons
            url_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(6))
            self.url_input = TextInput(
                hint_text="Paste YouTube URL here...",
                multiline=False,
                font_size="14sp",
                size_hint_x=0.72,
                background_color=(0.12, 0.14, 0.20, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.7, 0, 1),
            )
            paste_btn = Button(
                text="PASTE",
                font_size="12sp",
                bold=True,
                size_hint_x=0.28,
                background_color=(0.20, 0.24, 0.35, 1.0),
                color=(1, 0.75, 0, 1),
            )
            paste_btn.bind(on_press=self.on_paste_clicked)
            url_row.add_widget(self.url_input)
            url_row.add_widget(paste_btn)
            root.add_widget(url_row)

            # Format / Quality Selector
            selector_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
            selector_label = Label(text="Format:", size_hint_x=0.32, font_size="13sp", color=(0.8, 0.8, 0.8, 1))
            self.quality_spinner = Spinner(
                text="Video (Best MP4)",
                values=(
                    "Video (Best MP4)",
                    "Video (720p HD)",
                    "Video (1080p Full HD)",
                    "Audio (Music / Song)",
                ),
                size_hint_x=0.68,
                background_color=(0.18, 0.20, 0.28, 1.0),
                color=(1, 1, 1, 1),
            )
            selector_box.add_widget(selector_label)
            selector_box.add_widget(self.quality_spinner)
            root.add_widget(selector_box)

            # Progress Bar
            self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(16))
            root.add_widget(self.progress_bar)

            # Status Message Card
            self.status_label = Label(
                text="Ready. Paste a link or share from YouTube.",
                markup=True,
                font_size="12sp",
                color=(0.85, 0.85, 0.85, 1.0),
                size_hint_y=None,
                height=dp(50),
            )
            root.add_widget(self.status_label)

            # Download Action Button
            self.download_btn = Button(
                text="DOWNLOAD NOW",
                font_size="16sp",
                bold=True,
                background_color=(1.0, 0.65, 0.0, 1.0),  # Vivid Amber
                color=(0.05, 0.05, 0.05, 1.0),
                size_hint_y=None,
                height=dp(50),
            )
            self.download_btn.bind(on_press=self.start_download)
            root.add_widget(self.download_btn)

            # Destination note
            download_dir = get_android_download_dir()
            self.storage_note = Label(
                text=f"Destination: {download_dir.name}",
                font_size="11sp",
                color=(0.5, 0.55, 0.65, 1.0),
                size_hint_y=None,
                height=dp(24),
            )
            root.add_widget(self.storage_note)

            # Check for incoming YouTube Share intent on cold startup
            Clock.schedule_once(self.check_initial_intent, 0.4)

            return root

        def on_paste_clicked(self, instance):
            """Handle PASTE button press from Android system clipboard."""
            try:
                clip_text = Clipboard.paste()
                if clip_text:
                    url = extract_youtube_url(clip_text.strip()) or clip_text.strip()
                    self.url_input.text = url
                    self.update_status("[color=#FFB300]Link pasted![/color] Tap DOWNLOAD NOW.", 0)
                else:
                    self.update_status("Clipboard is empty.", 0)
            except Exception as e:
                self.update_status(f"Paste notice: {e}", 0)

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
                        url = extract_youtube_url(shared_text)
                        if url:
                            self.url_input.text = url
                            self.update_status(
                                "[color=#FFB300]Received from YouTube![/color] Tap DOWNLOAD NOW.", 0
                            )
                            return

                # Case 2: VIEW Intent (User clicked YouTube link)
                if action == Intent.ACTION_VIEW:
                    data = intent.getData()
                    if data:
                        url = extract_youtube_url(data.toString())
                        if url:
                            self.url_input.text = url
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
            url = extract_youtube_url(raw_text) or raw_text
            if not url:
                self.update_status("[color=#FF5252]Please enter or paste a YouTube link![/color]")
                return

            self.download_btn.disabled = True
            self.update_status("Starting connection...", 5)

            selected_format = self.quality_spinner.text
            is_audio = "Audio" in selected_format

            def worker():
                try:
                    import yt_dlp

                    target_dir = get_android_download_dir()
                    target_dir.mkdir(parents=True, exist_ok=True)

                    Clock.schedule_once(
                        lambda dt: self.update_status(f"Resolving video stream...", 15)
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

                    # Template output filename
                    outtmpl = str(target_dir / "%(title).100B [%(id)s].%(ext)s")

                    # Configure yt-dlp options specifically tailored for Android stability
                    ydl_opts = {
                        "outtmpl": outtmpl,
                        "progress_hooks": [progress_hook],
                        "socket_timeout": 30,
                        "nocheckcertificate": False,
                        "quiet": True,
                        "no_warnings": True,
                        "restrictfilenames": False,
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
                            # Native M4A / AAC (plays natively on all Android devices without FFmpeg)
                            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
                    else:
                        if "720p" in selected_format:
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                            else:
                                ydl_opts["format"] = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
                        elif "1080p" in selected_format:
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
                            else:
                                ydl_opts["format"] = "best[ext=mp4]/best"
                        else:
                            # Best quality: if no FFmpeg, prioritize pre-merged MP4 for instant playback
                            if has_ffmpeg:
                                ydl_opts["format"] = "bestvideo*+bestaudio/best"
                            else:
                                ydl_opts["format"] = "best[ext=mp4]/best"

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
                    if len(err_msg) > 70:
                        err_msg = err_msg[:67] + "..."
                    Clock.schedule_once(
                        lambda dt, err=err_msg: self.update_status(
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

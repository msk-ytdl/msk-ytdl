"""
Mobile graphical interface entry point for MSK-YTDL on Android.
Designed for touchscreen navigation, phone storage permissions, and background downloading.
"""

import sys
import threading
from pathlib import Path
from typing import Optional

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.graphics import Color, RoundedRectangle
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


def request_android_permissions():
    """Request runtime storage permissions on modern Android versions."""
    try:
        from android.permissions import Permission, request_permissions
        request_permissions([
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE,
            Permission.INTERNET,
        ])
    except Exception:
        pass


if KIVY_AVAILABLE:
    class MSKDownloaderMobile(App):
        def build(self):
            self.title = "MSK Video Downloader"
            Window.clearcolor = (0.08, 0.08, 0.10, 1.0)

            # Request Android storage permissions on startup
            request_android_permissions()

            root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(15))

            # Header / Logo Title
            header = Label(
                text="[b][color=#FFB300]MSK[/color] Video Downloader[/b]",
                markup=True,
                font_size="24sp",
                size_hint_y=None,
                height=dp(50),
            )
            root.add_widget(header)

            subtitle = Label(
                text="Paste authorized YouTube video or playlist link below",
                font_size="13sp",
                color=(0.7, 0.7, 0.7, 1.0),
                size_hint_y=None,
                height=dp(25),
            )
            root.add_widget(subtitle)

            # URL Input Box
            self.url_input = TextInput(
                hint_text="https://www.youtube.com/watch?v=...",
                multiline=False,
                font_size="15sp",
                size_hint_y=None,
                height=dp(48),
                background_color=(0.15, 0.15, 0.18, 1.0),
                foreground_color=(1, 1, 1, 1),
                cursor_color=(1, 0.7, 0, 1),
            )
            root.add_widget(self.url_input)

            # Format / Quality Selector
            selector_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(10))
            selector_label = Label(text="Select Quality:", size_hint_x=0.4, font_size="14sp")
            self.quality_spinner = Spinner(
                text="Video (Best Quality)",
                values=(
                    "Video (Best Quality)",
                    "Video (1080p Full HD)",
                    "Video (720p HD)",
                    "Audio (MP3 320 kbps)",
                    "Audio (MP3 192 kbps)",
                ),
                size_hint_x=0.6,
                background_color=(0.2, 0.2, 0.25, 1.0),
                color=(1, 1, 1, 1),
            )
            selector_box.add_widget(selector_label)
            selector_box.add_widget(self.quality_spinner)
            root.add_widget(selector_box)

            # Progress Bar
            self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(20))
            root.add_widget(self.progress_bar)

            # Status Message
            self.status_label = Label(
                text="Ready. Enter a URL to begin.",
                font_size="13sp",
                color=(0.8, 0.8, 0.8, 1.0),
                size_hint_y=None,
                height=dp(40),
            )
            root.add_widget(self.status_label)

            # Download Action Button
            self.download_btn = Button(
                text="DOWNLOAD",
                font_size="16sp",
                bold=True,
                background_color=(1.0, 0.65, 0.0, 1.0),  # Amber gold
                color=(0, 0, 0, 1),
                size_hint_y=None,
                height=dp(52),
            )
            self.download_btn.bind(on_press=self.start_download)
            root.add_widget(self.download_btn)

            # Destination note
            storage_note = Label(
                text="Saved to: /sdcard/Download/YouTube",
                font_size="11sp",
                color=(0.5, 0.5, 0.5, 1.0),
                size_hint_y=None,
                height=dp(30),
            )
            root.add_widget(storage_note)

            return root

        def update_status(self, text: str, progress_val: Optional[float] = None):
            self.status_label.text = text
            if progress_val is not None:
                self.progress_bar.value = progress_val

        def start_download(self, instance):
            url = self.url_input.text.strip()
            if not url:
                self.update_status("Please enter a valid YouTube URL first!")
                return

            self.download_btn.disabled = True
            self.update_status("Starting download in background...", 10)

            mode = "audio" if "Audio" in self.quality_spinner.text else "video"
            quality = "best"
            if "1080p" in self.quality_spinner.text:
                quality = "1080p"
            elif "720p" in self.quality_spinner.text:
                quality = "720p"

            bitrate = "320" if "320" in self.quality_spinner.text else "192"

            def worker():
                try:
                    from youtube_downloader.config import AppConfig
                    from youtube_downloader.downloader import YoutubeDownloader

                    # On Android, default to public storage
                    target_dir = Path("/sdcard/Download/YouTube")
                    if not target_dir.exists():
                        try:
                            target_dir.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            target_dir = Path.home() / "Downloads"

                    cfg = AppConfig(download_directory=str(target_dir))
                    dl = YoutubeDownloader(config=cfg, debug=False)

                    Clock.schedule_once(lambda dt: self.update_status("Downloading stream...", 40))
                    if mode == "audio":
                        res = dl.download_audio(url, audio_format="mp3", audio_quality=bitrate)
                    else:
                        res = dl.download_video(url, quality=quality)

                    if res:
                        Clock.schedule_once(
                            lambda dt: self.update_status(f"Done! Saved: {res.name}", 100)
                        )
                    else:
                        Clock.schedule_once(
                            lambda dt: self.update_status("Download skipped (already in archive)", 100)
                        )
                except Exception as e:
                    Clock.schedule_once(lambda dt: self.update_status(f"Error: {e}", 0))
                finally:
                    Clock.schedule_once(lambda dt: setattr(self.download_btn, "disabled", False))

            threading.Thread(target=worker, daemon=True).start()


def main():
    if not KIVY_AVAILABLE:
        print("[Notice] Kivy framework is not installed in this environment.")
        print("To run the Android touch UI on desktop for testing, install kivy:")
        print("    pip install kivy")
        print("\nAlternatively, build the APK via GitHub Actions or run in Termux:")
        print("    bash scripts/install_android_termux.sh")
        return 1

    app = MSKDownloaderMobile()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

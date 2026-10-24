"""
Built-in local web server and REST API for MSK-YTDL.
Provides a responsive VidMate-style browser interface accessible on PC and mobile devices over Wi-Fi.
"""

import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from youtube_downloader.config import AppConfig, load_config
from youtube_downloader.downloader import YoutubeDownloader
from youtube_downloader.errors import YTDLError

console = Console()

def get_web_dir() -> Path:
    """Resolve directory containing web assets, supporting PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "youtube_downloader" / "web"
            if cand.exists():
                return cand
        exe_dir = Path(sys.executable).parent
        cand_exe = exe_dir / "_internal" / "youtube_downloader" / "web"
        if cand_exe.exists():
            return cand_exe
        cand_adjacent = exe_dir / "web"
        if cand_adjacent.exists():
            return cand_adjacent
    return Path(__file__).resolve().parent / "web"


WEB_DIR = get_web_dir()


def get_local_ip() -> str:
    """Retrieve host machine's primary local LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class DownloadJob:
    """Represents an active or completed background download task."""

    def __init__(self, job_id: str, url: str, mode: str, quality: str, audio_format: str, audio_quality: str):
        self.job_id = job_id
        self.url = url
        self.mode = mode
        self.quality = quality
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.status = "queued"  # queued, downloading, converting, completed, skipped, failed
        self.progress = 0.0
        self.speed_str = "0 KB/s"
        self.eta_str = "--:--"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.title: Optional[str] = None
        self.thumbnail: Optional[str] = None
        self.filename: Optional[str] = None
        self.filepath: Optional[str] = None
        self.error: Optional[str] = None
        self.start_time = time.time()
        self.end_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.job_id,
            "url": self.url,
            "mode": self.mode,
            "quality": self.quality,
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "status": self.status,
            "progress": round(self.progress, 1),
            "speed": self.speed_str,
            "eta": self.eta_str,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "title": self.title,
            "thumbnail": self.thumbnail,
            "filename": self.filename,
            "filepath": self.filepath,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class JobManager:
    """Thread-safe manager for download jobs."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: Dict[str, DownloadJob] = {}

    def create_job(self, url: str, mode: str, quality: str, audio_format: str, audio_quality: str) -> DownloadJob:
        with self.lock:
            job_id = str(uuid.uuid4())[:8]
            job = DownloadJob(job_id, url, mode, quality, audio_format, audio_quality)
            self.jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        with self.lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [job.to_dict() for job in sorted(self.jobs.values(), key=lambda j: j.start_time, reverse=True)]


JOB_MANAGER = JobManager()


class MSKWebRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving MSK-YTDL Web UI and REST endpoints."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self.serve_index()
        elif path == "/api/status":
            self.handle_api_status()
        elif path == "/api/jobs":
            self.handle_api_jobs()
        elif path == "/api/progress":
            job_id = query.get("id", [""])[0]
            self.handle_api_progress(job_id)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            payload = {}

        if path == "/api/inspect":
            self.handle_api_inspect(payload)
        elif path == "/api/download":
            self.handle_api_download(payload)
        elif path == "/api/open-folder":
            self.handle_api_open_folder()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def serve_index(self):
        index_file = WEB_DIR / "index.html"
        if not index_file.exists():
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>MSK-YTDL Web UI loading...</h1>")
            return

        content = index_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def handle_api_status(self):
        config = load_config()
        from youtube_downloader import __version__
        from youtube_downloader.diagnostics import find_ffmpeg_executable

        ffmpeg_path = find_ffmpeg_executable()
        self.send_json({
            "version": __version__,
            "download_directory": str(config.get_resolved_download_path()),
            "ffmpeg_ready": bool(ffmpeg_path),
            "ffmpeg_path": ffmpeg_path,
            "host_ip": get_local_ip(),
            "use_download_archive": config.use_download_archive,
            "embed_thumbnail": config.embed_thumbnail,
            "embed_metadata": config.embed_metadata,
        })

    def handle_api_jobs(self):
        self.send_json({"jobs": JOB_MANAGER.list_jobs()})

    def handle_api_progress(self, job_id: str):
        job = JOB_MANAGER.get_job(job_id)
        if not job:
            self.send_json({"error": "Job not found"}, status=404)
            return
        self.send_json(job.to_dict())

    def handle_api_inspect(self, payload: Dict[str, Any]):
        url = payload.get("url", "").strip()
        if not url:
            self.send_json({"success": False, "error": "URL is required"}, status=400)
            return

        config = load_config()
        downloader = YoutubeDownloader(config=config, debug=False)

        try:
            if "list=" in url or "/playlist" in url:
                info = downloader.get_playlist_info(url)
                self.send_json({
                    "success": True,
                    "is_playlist": True,
                    "title": info.title,
                    "uploader": info.uploader,
                    "entries_count": info.entries_count,
                    "webpage_url": info.webpage_url,
                    "preview_entries": [
                        {"title": e.title, "duration": e.duration_formatted, "id": e.video_id}
                        for e in info.entries[:10]
                    ],
                })
            else:
                meta = downloader.get_video_info(url)
                self.send_json({
                    "success": True,
                    "is_playlist": False,
                    "id": meta.video_id,
                    "title": meta.title,
                    "uploader": meta.uploader,
                    "duration": meta.duration_formatted,
                    "thumbnail": meta.thumbnail_url,
                    "upload_date": meta.upload_date_formatted,
                    "available_resolutions": meta.available_resolutions,
                })
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, status=400)

    def handle_api_download(self, payload: Dict[str, Any]):
        url = payload.get("url", "").strip()
        if not url:
            self.send_json({"success": False, "error": "URL is required"}, status=400)
            return

        mode = payload.get("mode", "video")
        quality = payload.get("quality", "best")
        audio_format = payload.get("audio_format", "mp3")
        audio_quality = payload.get("audio_quality", "192")

        job = JOB_MANAGER.create_job(
            url=url,
            mode=mode,
            quality=quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
        )

        # Launch download in background thread
        thread = threading.Thread(target=self._execute_download_job, args=(job,), daemon=True)
        thread.start()

        self.send_json({"success": True, "job_id": job.job_id})

    def _execute_download_job(self, job: DownloadJob):
        config = load_config()
        downloader = YoutubeDownloader(config=config, debug=False)

        # Progress hook updater
        def progress_hook(d: Dict[str, Any]):
            status = d.get("status")
            if status == "downloading":
                job.status = "downloading"
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0

                job.downloaded_bytes = downloaded
                job.total_bytes = total
                if total > 0:
                    job.progress = min(99.0, (downloaded / total) * 100.0)

                # Format speed
                if speed > 1048576:
                    job.speed_str = f"{speed / 1048576:.1f} MB/s"
                elif speed > 1024:
                    job.speed_str = f"{speed / 1024:.0f} KB/s"

                # Format ETA
                if eta:
                    m, s = divmod(int(eta), 60)
                    job.eta_str = f"{m:02d}:{s:02d}"

                # Update filename if available
                filename = d.get("filename")
                if filename and not job.filename:
                    job.filename = Path(filename).name

            elif status == "finished":
                job.status = "converting"
                job.progress = 99.0

        try:
            job.status = "downloading"
            if job.mode == "audio":
                # Download audio
                result_path = downloader.download_audio(
                    url=job.url,
                    audio_format=job.audio_format,
                    audio_quality=job.audio_quality,
                )
            else:
                result_path = downloader.download_video(
                    url=job.url,
                    quality=job.quality,
                )

            if result_path:
                job.status = "completed"
                job.progress = 100.0
                job.filepath = str(result_path)
                job.filename = result_path.name
            else:
                job.status = "skipped"
                job.progress = 100.0

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        finally:
            job.end_time = time.time()

    def handle_api_open_folder(self):
        config = load_config()
        path = config.get_resolved_download_path()
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
            self.send_json({"success": True, "path": str(path)})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, status=500)

    def log_message(self, format, *args):
        # Silence verbose standard console logging from BaseHTTPRequestHandler
        pass


def run_web_server(port: int = 8899, open_browser: bool = True) -> None:
    """Start the MSK-YTDL Web UI server."""
    local_ip = get_local_ip()
    server_address = ("0.0.0.0", port)

    try:
        httpd = ThreadingHTTPServer(server_address, MSKWebRequestHandler)
    except OSError as e:
        console.print(f"[bold red]Could not bind to port {port}:[/bold red] {e}")
        return

    local_url = f"http://localhost:{port}"
    network_url = f"http://{local_ip}:{port}"

    console.print()
    console.print("=" * 64)
    console.print("[bold yellow]  MSK-YTDL: VidMate-Style Modern Web GUI[/bold yellow]")
    console.print("=" * 64)
    console.print(f"  [bold green]Local PC Access:[/bold green]     {local_url}")
    console.print(f"  [bold cyan]Mobile / Wi-Fi Access:[/bold cyan] {network_url}")
    console.print("  [dim]Open this Wi-Fi link on your Android phone, tablet, or laptop![/dim]")
    console.print("  [dim]Press Ctrl+C to stop the web server.[/dim]")
    console.print("=" * 64)
    console.print()

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(local_url)).start()

    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]Stopping MSK-YTDL Web Server. Goodbye![/yellow]")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8899
    run_web_server(port=port_arg)

# MSK YTDL: Reliable YouTube Video & Audio Downloader
Developed by **MSK Software Solutions**

A robust, production-quality application built with Python, [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), and [`Rich`](https://github.com/Textualize/rich). Designed for reliability, clear diagnostics, error recovery, and seamless Android and Windows support.

---

## ⚠️ Legal and Authorized-Use Notice

**This application is strictly designed for downloading videos you own, have explicit written permission to download, or are otherwise authorized to save under applicable terms of service and copyright laws.**

* **No DRM Circumvention:** Encrypted or DRM-protected streams are not supported.
* **No Authentication or Cookie Theft:** Does not store passwords, capture browser session cookies, or bypass access restrictions (such as private videos, members-only posts, paywalled streams, or age gates).
* **No CAPTCHA Automation or Proxy Rotation:** Respects rate limits and platform controls.
* **Mandatory Permission Confirmation:** Users are prompted to verify ownership or authorization before initiating any download.

If access to media is restricted, please use the platform's authorized website, export tools, or YouTube Premium offline features.

---

## Key Features

* **Triple Interface:** Polished interactive terminal menu with 15 numbered options, modern MSK YTDL browser web application, and direct CLI flags for power users and automation.
* **Local MSK YTDL Web App:** Built-in web server (`run_web.bat` or `--web`) that launches a responsive dark-mode browser UI accessible on your PC (`http://localhost:8899`) or across your local Wi-Fi on Android phones and tablets!
* **Standalone Windows Executable & Portable Packager:** 1-click builder (`build_exe.bat` or Option 14) that compiles a standalone `MSK-YTDL.exe` signed by **MSK Software Solutions**, bundles `ffmpeg.exe` and `ffprobe.exe`, and generates a ready-to-share `MSK-YTDL-Windows-x64.zip` file for friends (no Python or FFmpeg installation needed on their PC).
* **Automated Multi-Platform Release CI/CD:** Automated GitHub Actions workflow (`.github/workflows/release.yml`) that compiles and signs both Android `.apk` (v1/v2/v3 scheme) and Windows `.exe` / `.zip`, automatically publishing a GitHub Release with download assets on every push.
* **Full Playlist Downloads:** Download complete YouTube playlists as video or MP3 audio with automatic folder organization (`<Playlist Title>/`), configurable item ranges (`--playlist-start`, `--playlist-end`), or custom item selectors (`--playlist-items '1,3-5,8'`).
* **Multi-Video Batch Downloading:** Process multiple individual video URLs in a single run with per-item error isolation via CLI arguments (`--urls ...`) or from a plain text file (`--batch-file urls.txt`).
* **Smart Archive (Skip Already Downloaded Videos):** Automatically keeps track of completed downloads in a persistent archive file (`~/.msk_ytdl/archive.txt`), instantly skipping already-fetched items during playlist and batch runs.
* **Audio Album Artwork & Metadata Embedding:** Automatically downloads thumbnails, converts them to JPEG, and embeds them directly into MP3 files along with ID3 metadata tags (Artist, Title, Album, and Chapter markers).
* **Adaptive Video Quality:** Download at best source quality (`bestvideo*+bestaudio/best`) or constrain to maximum user-selected resolutions (4K / 2160p, 1440p, 1080p, 720p, 480p, 360p).
* **High-Quality Audio & MP3 Conversion:** Download best available original audio streams or convert directly to MP3 with selectable bitrates (128, 192, 256, or 320 kbps) via FFmpeg.
* **Metadata & Format Inspection (Zero Download):** Inspect video and playlist information (uploader, duration, item counts, preview tracks, available resolution tiers) without downloading media bytes.
* **Rich Live Progress & Clean Terminal Rendering:** Transient, flicker-free progress bars displaying transferred bytes, speed, and ETA without terminal ghost lines, followed by color-coded completion summary tables.
* **Resumable Downloads & Conservative Retries:** Resumes interrupted partial downloads (`continuedl`) and applies bounded network/fragment retry policies (default 3 retries).
* **Windows Explorer Integration:** One-click / one-key command (Option 13) to reveal and open the active download folder directly in Windows File Explorer.
* **Automated Dependency Health Diagnostics:** One-step diagnostic command (`--check` or menu item 10) that verifies Python, `yt-dlp`, `yt-dlp-ejs`, `rich`, `ffmpeg`, `ffprobe`, JavaScript runtimes (Deno/Node.js), and write permissions.
* **Atomic JSON Configuration:** Persistent settings stored in `~/.msk_ytdl/config.json` with schema validation, corrupted file backup, and atomic file writes.

---

## System Requirements

| Component | Minimum Version | Recommended / Current |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 / 11 | Windows 11 (PowerShell or Command Prompt) |
| **Python** | 3.11 or later | Python 3.11, 3.12, or 3.13 |
| **yt-dlp** | >= 2026.10.21 | Latest official release |
| **yt-dlp-ejs** | >= 0.8.0 | External JavaScript solver package |
| **Rich** | >= 13.9 | Terminal rendering and progress bars |
| **FFmpeg & FFprobe** | 5.0+ | FFmpeg 8.1+ full build (with libmp3lame) |
| **JavaScript Engine** | Node.js (>= 18) or Deno | Deno (preferred) or Node.js |

> [!NOTE]
> FFmpeg refers to the actual external system executable (`ffmpeg.exe`), not a Python wrapper package.

---

## Windows Installation Guide

### Option 1: Automated Windows Setup (Recommended)

1. Clone or download this repository into your chosen folder:
   ```powershell
   git clone https://github.com/your-username/msk-ytdl.git
   cd msk-ytdl
   ```
2. Double-click or run `setup_windows.bat` from Command Prompt or PowerShell:
   ```cmd
   setup_windows.bat
   ```
   The setup script automatically:
   * Checks that Python 3.11+ is installed on PATH.
   * Creates a dedicated virtual environment in `.venv`.
   * Upgrades `pip` and installs the project and dependencies in editable mode (`pip install -e .`).
   * Detects FFmpeg, FFprobe, and JavaScript runtimes (Deno or Node.js).
   * Displays clear remediation instructions for missing system dependencies.

### Option 2: Manual Installation via PowerShell

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install package
python -m pip install --upgrade pip
python -m pip install -e .
```

---

## Installing External System Dependencies

### 1. FFmpeg & FFprobe (Required for stream merging and MP3 conversion)
Install via Windows Package Manager (**winget**):
```powershell
winget install Gyan.FFmpeg
```
Alternatively, download the release build directly from [Gyan.dev FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/) and add its `bin/` directory to your Windows System `PATH`.

### 2. JavaScript Runtime: Deno or Node.js (Required for YouTube Challenge Support)
YouTube frequently serves signature challenges requiring external JS execution.

* **Deno (Preferred by yt-dlp):**
  Install via PowerShell:
  ```powershell
  irm https://deno.land/install.ps1 | iex
  ```
* **Node.js (Supported fallback):**
  Install via winget:
  ```powershell
  winget install OpenJS.NodeJS.LTS
  ```

---

## How to Run the Application

### 1. Interactive Menu (Beginner-Friendly)

Simply run:
```cmd
run.bat
```
Or with PowerShell:
```powershell
.\.venv\Scripts\python.exe -m youtube_downloader
```

You will be greeted by the interactive terminal interface:
```
=================================================
  MSK-YTDL: Reliable YouTube Downloader v1.0.0
  Download only content you own or are authorized to save.
=================================================
  1. Download video - Best Available Quality
  2. Download video - Select Maximum Resolution
  3. Download Audio - MP3
  4. Download Audio - Best Available Original Format
  5. Download Playlist - Video (Whole / Range / Selection)
  6. Download Playlist - Audio / MP3 (Whole / Range / Selection)
  7. Download Multiple Videos (Batch input or Text File)
  8. Show Video or Playlist Information
  9. List Available Video Formats
  10. Check Application & Dependency Health
  11. View Configuration
  12. Change Download Folder
  13. Open Download Folder in File Explorer
  14. Package for Friends (Windows .EXE / Android APK Guide)
  15. Launch Web UI (MSK YTDL Mobile/Browser App)
  0. Exit

Select an option:
```

### 2. Direct Command-Line Interface (Advanced / Scripting)

Run operations directly using command-line arguments:

#### A. Run Dependency Health Check
```powershell
run.bat --check
```

#### B. Download Video (Best Available Quality)
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode video --quality best --confirm-authorized
```

#### C. Download Video Constrained to Maximum Resolution (e.g., 1080p)
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode video --quality 1080p --confirm-authorized
```
*Supported video qualities:* `best`, `2160p`, `1440p`, `1080p`, `720p`, `480p`, `360p`.

#### D. Download Audio Converted to MP3 (e.g., 320 kbps)
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode audio --audio-format mp3 --audio-quality 320 --confirm-authorized
```
*Supported MP3 bitrates:* `128`, `192`, `256`, `320` kbps.

#### E. Download Audio in Best Available Original Format (No Transcoding)
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode audio --audio-format best --confirm-authorized
```

#### F. Download Full YouTube Playlist
```powershell
# Download entire playlist as video into a dedicated subfolder
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --mode video --quality 1080p --confirm-authorized

# Download playlist as MP3 audio files
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --mode audio --audio-format mp3 --audio-quality 320 --confirm-authorized
```

#### G. Download Specific Playlist Range or Selected Items
```powershell
# Download items 1 through 10
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --playlist-start 1 --playlist-end 10 --confirm-authorized

# Download specific items (e.g. items 1, 3, 5 through 8) without creating a subfolder
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --playlist-items "1,3,5-8" --no-subfolder --confirm-authorized
```

#### H. Download Multiple Videos in Batch (Inline Arguments)
```powershell
run.bat --urls "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "https://www.youtube.com/watch?v=9bZkp7q19f0" --mode video --quality 720p --confirm-authorized
```

#### I. Download Multiple Videos from a Text File
```powershell
# Read URLs from a text file (supports comments starting with '#', blank lines, commas, spaces)
run.bat --batch-file "D:/my_links.txt" --mode audio --audio-format mp3 --confirm-authorized
```

#### J. View Video or Playlist Metadata (Zero Media Downloaded)
```powershell
# Video metadata
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --info

# Playlist preview metadata and entry summary
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --info
```

#### K. List Available Media Streams (Zero Media Downloaded)
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --list-formats
```

#### L. Smart Archive Control (Skip Already Downloaded Videos)
By default, MSK-YTDL automatically records downloaded video IDs in `~/.msk_ytdl/archive.txt`. When fetching playlists or batch lists, already-downloaded videos are instantly skipped.
```powershell
# Disable archive tracking for a specific run (re-download everything)
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --no-archive --confirm-authorized

# Use a custom project-specific archive file
run.bat --url "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9f5QVVV4g7f" --playlist --archive-file "D:/my_project_archive.txt" --confirm-authorized
```

#### M. Audio Cover Art & Metadata Tagging Control
By default, audio downloads automatically fetch video thumbnails, convert them to JPEG, embed them into the MP3 ID3 header as album art, and write Artist/Title/Album/Chapter metadata.
```powershell
# Download MP3 audio without embedding cover artwork
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode audio --no-embed-thumbnail --confirm-authorized

# Download MP3 audio without writing metadata tags
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mode audio --no-embed-metadata --confirm-authorized
```

#### N. Specify Custom Download Output Directory & Debugging
```powershell
run.bat --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --output-dir "D:/ArchivedVideos" --debug --confirm-authorized
```

#### O. Build Standalone Windows Executable & Shareable ZIP Archive
```powershell
run.bat --package-windows
```

#### P. Launch Local Web UI (MSK YTDL Mobile/Browser App)
Start the built-in local server and open your browser at `http://localhost:8899` (or open the displayed Wi-Fi URL on your Android phone/tablet):
```powershell
# Double-click or run the batch launcher:
run_web.bat

# Or launch via Python CLI flags:
run.bat --web --port 8899
```

---

## Packaging & Sharing with Friends (Windows .EXE & Android .APK)

For detailed step-by-step documentation, see: **[docs/MOBILE_AND_APK_GUIDE.md](docs/MOBILE_AND_APK_GUIDE.md)**.

### 1. Windows Standalone Executable (.EXE & .ZIP)
Compile a zero-dependency portable folder and compressed ZIP archive containing `MSK-YTDL.exe` and bundled `ffmpeg.exe`:
```cmd
build_exe.bat
```
* **Output Artifact:** `dist/MSK-YTDL-Windows-x64.zip`
* **Sharing:** Send the ZIP to friends (via WhatsApp, Google Drive, Telegram, email). They extract it and double-click `Start_MSK_YTDL.bat`. No Python or FFmpeg installation required on their PC!

### 2. Android APK (.APK) Cloud Build via GitHub Actions
* Push this repository to GitHub.
* In your GitHub repo, go to **Actions** -> **Build Android APK** -> **Run workflow**.
* GitHub compiles the native Android `.apk` for free in the cloud (~5 minutes).
* Download the compiled `.apk` under **Artifacts** and install it on your phone!

### 3. Android 1-Click Termux Setup (Instant Native Mobile CLI)
On any Android device, open Termux and run:
```bash
bash install_android.sh
```
Downloads save directly to your phone's public `/sdcard/Download/YouTube` folder and appear in your phone's Gallery and Music apps.

---

## Configuration System

Configuration settings are stored in standard JSON at:
`%USERPROFILE%\.msk_ytdl\config.json`

Example configuration:
```json
{
  "download_directory": "C:\\Users\\Username\\Downloads\\YouTube",
  "default_video_quality": "best",
  "default_audio_format": "mp3",
  "default_audio_quality": "192",
  "show_progress": true,
  "max_retries": 3,
  "create_playlist_subfolder": true,
  "max_playlist_items_prompt": 50,
  "use_download_archive": true,
  "archive_file_path": null,
  "embed_thumbnail": true,
  "embed_metadata": true
}
```

* **`use_download_archive`**: Enables persistent download history (`true` by default) to automatically skip already-downloaded videos in playlists.
* **`archive_file_path`**: Path to a custom archive file (defaults to `~/.msk_ytdl/archive.txt` when `null`).
* **`embed_thumbnail`**: Automatically converts YouTube thumbnails to JPEG and embeds them into MP3 audio as album cover art (`true` by default).
* **`embed_metadata`**: Writes ID3 artist, title, album, and chapter tags into MP3 files (`true` by default).
* **Safe Fallbacks:** If the configuration file is absent, safe defaults are generated automatically.
* **Corruption Recovery:** If the file becomes malformed, the application backs up the corrupted version as `config.json.corrupted.<timestamp>.bak` and restores defaults.
* **Atomic Writes:** Updates are written to a temporary probe file before atomic replacement to prevent file corruption during power interruptions.

---

## Maintenance & Updating Dependencies

YouTube frequently modifies its player scripts, extraction mechanisms, and signature challenge logic. Maintain application health with these commands:

### 1. Update yt-dlp and yt-dlp-ejs to the latest release
```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp yt-dlp-ejs
```

### 2. Verify Installed Component Versions
```powershell
run.bat --check
```

### 3. Reinstall Dependencies in a Broken Environment
```powershell
.\.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements.txt
```

---

## Running Automated Tests

The test suite contains 95 deterministic unit tests that run independently of live YouTube access using mocks:

```powershell
# Run the complete test suite
.\.venv\Scripts\pytest -v
```

Test coverage includes:
* **Canonical URL validation:** Domain boundary verification, shorts, embed, live, shortened `youtu.be` links.
* **Playlist URL validation & sanitization:** Safe playlist parameter stripping for single video mode; dedicated playlist ID validation.
* **Batch input parsing:** Newline, comma, and space separated URLs; comments and blank lines; file reading with fallback encoding.
* **Malicious and non-YouTube URL rejection:** Preventing spoofed domains (`fakeyoutube.com`, `attacker.com`).
* **Configuration persistence:** Atomic writes, path expansion, and corrupted file recovery.
* **Smart archive & skip mechanics:** Checking record logs, handling archive hits without failure, custom archive path routing.
* **Audio cover art & metadata pipeline:** FFmpeg thumbnail conversion (`webp` -> `jpg`), `EmbedThumbnail`, `FFmpegMetadata`, ID3 tagging.
* **Standalone packager & CLI:** `--package-windows` argument parsing and runner integration, bundled FFmpeg fallback detection.
* **MSK YTDL Web Application & REST API:** Thread-safe job manager, status diagnostics, inspection endpoints, local IP resolution, and static asset serving.
* **Downloader mechanics:** Format selector generation for all resolution tiers, yt-dlp option dictionaries, resume support.
* **Playlist & Batch engine:** Error isolation, range filtering, subfolder generation, progress tracking, and tabular reporting.
* **Audio conversion:** MP3 postprocessor options, missing FFmpeg detection.
* **Error translation:** Mapping underlying exceptions (private, geo-restricted, 404, network timeouts, signature challenges).
* **Progress hooks:** Indeterminate streams, known byte totals, transient rendering, and post-processor stages.
* **CLI execution:** Argument parsing, batch/playlist flags, archive/embedding flags, interactive/non-interactive permission confirmation, exit codes.

---

## Troubleshooting Common Errors

### 1. `Post-processing or audio conversion failed via FFmpeg`
* **Cause:** FFmpeg or FFprobe is missing or not reachable on your system PATH.
* **Fix:** Install FFmpeg via `winget install Gyan.FFmpeg` or download from Gyan.dev, and ensure `ffmpeg.exe` is in your PATH.

### 2. `This video is private, members-only, or access-restricted`
* **Cause:** The video requires account authentication, channel membership, or payment.
* **Fix:** This application adheres to legal boundaries and does not collect credentials or bypass access controls. Use the platform's authorized website or YouTube Premium offline features.

### 3. `YouTube JavaScript signature challenge extraction failed`
* **Cause:** YouTube updated player JavaScript, or no JS runtime (Deno/Node.js) was detected.
* **Fix:** Run `run.bat --check`. Ensure `yt-dlp-ejs` is installed, install Deno or Node.js, and upgrade yt-dlp (`pip install -U yt-dlp yt-dlp-ejs`).

### 4. `The provided URL points to a full playlist, not a single video`
* **Cause:** A playlist URL was provided (`/playlist?list=...`).
* **Fix:** Supply a URL pointing directly to an individual video. If you pasted a watch URL with playlist parameters (`&list=...`), MSK-YTDL will automatically sanitize and download only the single target video.

### 5. Android: `Harmful app blocked` or `Blocked by Play Protect`
* **Cause:** Google Play Store policies do not allow YouTube downloaders. Therefore, Google Play Protect displays a generic warning when sideloading direct APKs.
* **Fix:** In the Play Protect popup, tap **"More details"** (or "Details") and then tap **"Install anyway"**. The APK is built and signed by MSK Software Solutions with zero trackers and zero ads.

### 6. Windows: `Windows protected your PC` (Microsoft Defender SmartScreen)
* **Cause:** SmartScreen displays this alert on new open-source executables that have not yet accumulated thousands of downloads in Microsoft's telemetry database.
* **Fix:** Click **"More info"** and then click **"Run anyway"**. To permanently trust MSK Software Solutions on your PC, right-click `Install_MSK_Certificate.bat` inside the portable folder and select **Run as administrator**.

---

## Exit Codes

| Code | Meaning |
| :---: | :--- |
| `0` | Success |
| `1` | Download or extraction failure |
| `2` | Argument or input validation error |
| `3` | Dependency check failure (`--check`) |
| `4` | Operation cancelled or authorization confirmation denied |

---

## Official Technical Documentation Links

* [yt-dlp Repository](https://github.com/yt-dlp/yt-dlp)
* [yt-dlp Releases](https://github.com/yt-dlp/yt-dlp/releases)
* [yt-dlp Installation Guide](https://github.com/yt-dlp/yt-dlp/wiki/Installation)
* [yt-dlp JavaScript Challenge (EJS) Support](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
* [yt-dlp Python API Documentation](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)
* [yt-dlp-ejs Repository](https://github.com/yt-dlp/ejs)
* [FFmpeg Official Website](https://ffmpeg.org/)
* [YouTube Terms of Service](https://www.youtube.com/t/terms)

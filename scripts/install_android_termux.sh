#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# MSK-YTDL: 1-Click Android Termux Setup & Installer Script
# Allows anyone with an Android device to run MSK-YTDL natively in Termux!
# Downloads are automatically saved into your Android phone's Downloads folder.
# ==============================================================================

set -e

echo "=========================================================="
echo "  MSK-YTDL: Reliable YouTube Downloader for Android"
echo "=========================================================="
echo ""

# 1. Update Termux package mirrors and packages
echo "[1/6] Updating Termux package lists..."
pkg update -y || apt-get update -y

# 2. Install Python, FFmpeg, Git, and Node.js (for YouTube signature challenge)
echo "[2/6] Installing Python, FFmpeg, and runtime dependencies..."
pkg install -y python ffmpeg git nodejs-lts || apt-get install -y python ffmpeg git nodejs

# 3. Request Android storage permissions
echo "[3/6] Setting up Android storage access..."
echo "NOTE: Please tap 'ALLOW' on your phone when prompted for storage permissions!"
termux-setup-storage || true
sleep 2

# 4. Create default download directory in Android public storage
TARGET_DOWNLOAD_DIR="/sdcard/Download/YouTube"
mkdir -p "$TARGET_DOWNLOAD_DIR"
echo "[INFO] Download directory set to: $TARGET_DOWNLOAD_DIR"

# 5. Install Python dependencies and MSK-YTDL
echo "[4/6] Installing Python dependencies (yt-dlp, rich, etc.)..."
python -m pip install --upgrade pip
python -m pip install "yt-dlp[default]>=2026.10.21" "yt-dlp-ejs>=0.8.0" "rich>=13.9" "mutagen>=1.48.0"

# Install MSK-YTDL package from current folder or repository
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    echo "[5/6] Installing MSK-YTDL from local files ($SCRIPT_DIR)..."
    python -m pip install -e "$SCRIPT_DIR"
else
    echo "[5/6] Installing MSK-YTDL..."
    python -m pip install -e .
fi

# 6. Create global command launcher 'msk-ytdl'
LAUNCHER_PATH="$PREFIX/bin/msk-ytdl"
cat << 'EOF' > "$LAUNCHER_PATH"
#!/data/data/com.termux/files/usr/bin/bash
python -m youtube_downloader "$@"
EOF
chmod +x "$LAUNCHER_PATH"

# Setup initial configuration with Android Download path
CONFIG_DIR="$HOME/.msk_ytdl"
mkdir -p "$CONFIG_DIR"
CONFIG_FILE="$CONFIG_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
cat << EOF > "$CONFIG_FILE"
{
  "download_directory": "$TARGET_DOWNLOAD_DIR",
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
EOF
fi

echo ""
echo "=========================================================="
echo "  INSTALLATION SUCCESSFUL!"
echo "=========================================================="
echo ""
echo "To run MSK-YTDL anytime on your phone, just open Termux and type:"
echo "    msk-ytdl"
echo ""
echo "Or download a video directly:"
echo "    msk-ytdl --url \"https://youtu.be/...\" --mode video"
echo ""
echo "Downloaded videos and MP3s will appear in your phone's Gallery"
echo "and Music app under: /sdcard/Download/YouTube"
echo "=========================================================="

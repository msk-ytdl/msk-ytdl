"""
Configuration management system for MSK-YTDL.

Provides persistent, schema-validated JSON configuration in the user's home directory
with atomic writes, corrupted file backup, and safe path expansion.
"""

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from youtube_downloader.errors import ConfigurationError, OutputDirectoryError
from youtube_downloader.validators import (
    validate_audio_format,
    validate_audio_quality,
    validate_video_quality,
)

CONFIG_DIR_NAME = ".msk_ytdl"
CONFIG_FILE_NAME = "config.json"


@dataclass
class AppConfig:
    """Application configuration parameters with safe defaults."""
    download_directory: str = str(Path.home() / "Downloads" / "YouTube")
    default_video_quality: str = "best"
    default_audio_format: str = "mp3"
    default_audio_quality: str = "192"
    show_progress: bool = True
    max_retries: int = 3
    create_playlist_subfolder: bool = True
    max_playlist_items_prompt: int = 50
    use_download_archive: bool = True
    archive_file_path: Optional[str] = None
    embed_thumbnail: bool = True
    embed_metadata: bool = True

    def get_resolved_download_path(self) -> Path:
        """Return the resolved Path object with user home directory expanded."""
        expanded = os.path.expanduser(self.download_directory)
        return Path(expanded).resolve()

    def get_resolved_archive_path(self) -> Path:
        """Return the resolved Path object for the download archive file."""
        if self.archive_file_path and self.archive_file_path.strip():
            expanded = os.path.expanduser(self.archive_file_path.strip())
            return Path(expanded).resolve()
        return get_config_dir() / "archive.txt"


def get_config_dir() -> Path:
    """Return the application configuration directory path."""
    return Path.home() / CONFIG_DIR_NAME


def get_config_file_path() -> Path:
    """Return the application configuration JSON file path."""
    return get_config_dir() / CONFIG_FILE_NAME


def validate_config_dict(data: Dict[str, Any]) -> AppConfig:
    """
    Validate and coerce a dictionary of settings into an AppConfig instance.

    Replaces invalid or missing values with safe defaults.
    """
    default_cfg = AppConfig()

    # Validate download directory
    raw_dir = data.get("download_directory", default_cfg.download_directory)
    if not isinstance(raw_dir, str) or not raw_dir.strip():
        download_directory = default_cfg.download_directory
    else:
        download_directory = raw_dir.strip()

    # Validate video quality
    raw_vq = data.get("default_video_quality", default_cfg.default_video_quality)
    try:
        default_video_quality = validate_video_quality(str(raw_vq))
    except Exception:
        default_video_quality = default_cfg.default_video_quality

    # Validate audio format
    raw_af = data.get("default_audio_format", default_cfg.default_audio_format)
    try:
        default_audio_format = validate_audio_format(str(raw_af))
    except Exception:
        default_audio_format = default_cfg.default_audio_format

    # Validate audio quality
    raw_aq = data.get("default_audio_quality", default_cfg.default_audio_quality)
    try:
        default_audio_quality = validate_audio_quality(raw_aq)
    except Exception:
        default_audio_quality = default_cfg.default_audio_quality

    # Validate show_progress
    show_progress = bool(data.get("show_progress", default_cfg.show_progress))

    # Validate max_retries (1 to 10)
    raw_retries = data.get("max_retries", default_cfg.max_retries)
    try:
        max_retries = max(1, min(10, int(raw_retries)))
    except (ValueError, TypeError):
        max_retries = default_cfg.max_retries

    # Validate create_playlist_subfolder
    create_playlist_subfolder = bool(data.get("create_playlist_subfolder", default_cfg.create_playlist_subfolder))

    # Validate max_playlist_items_prompt
    raw_max_pl = data.get("max_playlist_items_prompt", default_cfg.max_playlist_items_prompt)
    try:
        max_playlist_items_prompt = max(5, int(raw_max_pl))
    except (ValueError, TypeError):
        max_playlist_items_prompt = default_cfg.max_playlist_items_prompt

    # Validate use_download_archive
    use_download_archive = bool(data.get("use_download_archive", default_cfg.use_download_archive))

    # Validate archive_file_path
    raw_archive_fp = data.get("archive_file_path", default_cfg.archive_file_path)
    if isinstance(raw_archive_fp, str) and raw_archive_fp.strip():
        archive_file_path = raw_archive_fp.strip()
    else:
        archive_file_path = None

    # Validate embed_thumbnail & embed_metadata
    embed_thumbnail = bool(data.get("embed_thumbnail", default_cfg.embed_thumbnail))
    embed_metadata = bool(data.get("embed_metadata", default_cfg.embed_metadata))

    return AppConfig(
        download_directory=download_directory,
        default_video_quality=default_video_quality,
        default_audio_format=default_audio_format,
        default_audio_quality=default_audio_quality,
        show_progress=show_progress,
        max_retries=max_retries,
        create_playlist_subfolder=create_playlist_subfolder,
        max_playlist_items_prompt=max_playlist_items_prompt,
        use_download_archive=use_download_archive,
        archive_file_path=archive_file_path,
        embed_thumbnail=embed_thumbnail,
        embed_metadata=embed_metadata,
    )


def load_config() -> AppConfig:
    """
    Load configuration from disk.

    If file does not exist, creates it with defaults.
    If corrupted, backs up corrupted file and regenerates default configuration.
    """
    config_file = get_config_file_path()

    if not config_file.exists():
        default_config = AppConfig()
        save_config(default_config)
        return default_config

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Config JSON root must be an object.")
        return validate_config_dict(data)
    except Exception as e:
        # Corrupted or malformed file: backup and reset
        timestamp = int(time.time())
        backup_file = config_file.with_name(f"{CONFIG_FILE_NAME}.corrupted.{timestamp}.bak")
        try:
            shutil.copy2(config_file, backup_file)
        except OSError:
            pass

        default_config = AppConfig()
        save_config(default_config)
        return default_config


def save_config(config: AppConfig) -> None:
    """
    Save configuration to disk atomically.

    Writes to a temporary file in the configuration directory first,
    then replaces the target file.
    """
    config_dir = get_config_dir()
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ConfigurationError(
            f"Failed to create configuration directory at '{config_dir}'",
            details=str(e)
        )

    config_file = get_config_file_path()
    temp_file = config_file.with_name(f"{CONFIG_FILE_NAME}.tmp.{os.getpid()}")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(asdict(config), f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, config_file)
    except Exception as e:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise ConfigurationError(
            f"Failed to write configuration file at '{config_file}'",
            details=str(e)
        )


def ensure_directory_writable(directory: Path) -> Path:
    """
    Ensure the directory exists and has write permissions.

    Creates the directory if missing, and verifies write access
    using a temporary test file.

    Returns:
        The verified Path.

    Raises:
        OutputDirectoryError: If creation or writing fails.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OutputDirectoryError(
            f"Failed to create download directory '{directory}'",
            details=str(e),
            guidance="Select a different download folder with valid permissions."
        )

    test_file = directory / f".write_test_{os.getpid()}_{int(time.time())}.tmp"
    try:
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
    except OSError as e:
        raise OutputDirectoryError(
            f"Download directory '{directory}' is not writable.",
            details=str(e),
            guidance="Ensure your user account has write permissions to this directory or change the download folder."
        )

    return directory

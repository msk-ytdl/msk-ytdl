"""
Execution entry point for python -m youtube_downloader.
"""

import sys
from youtube_downloader.cli import main

if __name__ == "__main__":
    sys.exit(main())

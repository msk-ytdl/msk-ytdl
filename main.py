"""
MSK Video Downloader - Android Application Entrypoint.
Delegates execution to mobile_app.main() when packaged as an Android APK via Buildozer.
"""

import sys
from mobile_app import main

if __name__ == "__main__":
    sys.exit(main())

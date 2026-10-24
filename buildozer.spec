[app]

# (str) Title of your application
title = MSK YTDL

# (str) Package name
package.name = mskytdl

# (str) Package domain (needed for android/ios packaging)
package.domain = com.msksoftwaresolutions

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json,txt,xml,ico

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

# (str) Presplash of the application
presplash.filename = %(source.dir)s/icon.png

# (list) List of directories to exclude from the APK
source.exclude_dirs = tests, bin, .venv, venv, .git, .github, build, dist, msk-ytdl-site, .pytest_cache, __pycache__, docs, scripts, .agents

# (list) List of exclusions using pattern matching (keeps APK lean and removes non-runtime files)
source.exclude_patterns = *.spec, *.cer, *.bat, *.sh, *.ps1, *.md, *.p12, *.keystore, ci-constraints.txt, pytest.ini, requirements.txt, windows_version_info.txt, build_exe.py, pyproject.toml

# (str) Application versioning (method 1)
version = 1.0.1

# (int) Numeric version code (Android versionCode)
android.numeric_version = 1

# (list) Application requirements (clean minimal runtime: removed unused requests, urllib3, rich, idna, charset-normalizer, sqlite3)
requirements = python3,kivy,openssl,certifi,yt-dlp,yt-dlp-ejs,mutagen,pyjnius

# (int) Strip debug symbols from binaries (.so files) using Android NDK llvm-strip (1 = standard, 2 = aggressive)
android.strip = 2

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) Permissions (safe standard permissions; MANAGE_EXTERNAL_STORAGE excluded to prevent Play Protect harmful warning)
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,POST_NOTIFICATIONS

# (str) XML file to include as an intent filters in <activity> tag (enables "Share from YouTube")
android.manifest.intent_filters = intent_filters.xml

# (str) launchMode to set for the main activity
android.manifest.launch_mode = singleTask

# (int) Target Android API, should be as high as possible.
android.api = 34

# (int) Minimum API your APP will support.
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (bool) If True, then skip trying to update the Android SDK
android.skip_update = False

# (bool) If True, then automatically accept SDK license
android.accept_sdk_license = True

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (str) python-for-android branch to use (master is the stable branch without broken experimental recipes)
p4a.branch = master

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

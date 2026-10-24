# MSK-YTDL: Sharing & Distributing (Windows .EXE & Android .APK)

This guide explains how to package and share **MSK-YTDL** with your friends, colleagues, and network so they can install and run it on their Windows computers or Android phones **without needing Python, Git, or FFmpeg pre-installed**.

---

## 1. Windows Executable & Portable Package (.EXE & .ZIP)

### How to Build on Windows
We provide an automated packager that compiles the app with PyInstaller, automatically bundles `ffmpeg.exe` and `ffprobe.exe`, generates a batch launcher, and compresses everything into a ready-to-share ZIP file.

1. Double-click or run:
   ```cmd
   build_exe.bat
   ```
   Or run from PowerShell:
   ```powershell
   .\.venv\Scripts\python.exe build_exe.py
   ```

2. After the build finishes, you will find your shareable package at:
   * **ZIP Archive:** `dist/MSK-YTDL-Windows-x64.zip`
   * **Portable Directory:** `dist/MSK-YTDL-Portable/`

### How Your Friends Run It on Their PC
1. Send them `MSK-YTDL-Windows-x64.zip` (via WhatsApp, Telegram, Google Drive, USB drive, or email).
2. They extract the zip file anywhere on their computer (e.g. Desktop).
3. They double-click **`Start_MSK_YTDL.bat`** or **`MSK-YTDL.exe`**.
4. **Zero Setup:** Because FFmpeg and Python are bundled together inside the portable folder, it works immediately out-of-the-box!

---

## 2. Android APK Creation (.APK) via GitHub Actions (Recommended)

Compiling an Android APK from Python with C-libraries requires Linux, Android SDK, and Android NDK. Rather than requiring you to install a 20GB Linux environment on Windows, we provide a turnkey **GitHub Actions Cloud Build workflow** that compiles the `.apk` on GitHub's cloud runners for free.

### Step-by-Step APK Generation:
1. **Push your code to GitHub:**
   ```powershell
   git add .
   git commit -m "Add Android APK and Windows packagers"
   git push origin main
   ```
2. **Open your repository on GitHub in your browser:**
   * Click on the **Actions** tab at the top.
   * Under workflows on the left, click **Build Android APK**.
   * Click the **Run workflow** dropdown button on the right, and select **Run workflow**.
3. **Download the APK:**
   * The workflow will run for ~5 to 8 minutes compiling Python, Kivy, yt-dlp, and FFmpeg targeting Android ARM64 and ARMv7.
   * When complete, click on the workflow run.
   * Under **Artifacts** at the bottom of the page, download **`MSK-YTDL-Android-APK`** (contains the compiled `.apk`).
4. **Install on Android Device:**
   * Send the `.apk` to your phone or your friends' phones.
   * On the phone, tap the `.apk` file.
   * When prompted *"Do you want to install this app from unknown sources?"*, tap **Settings** -> **Allow from this source**.
   * Tap **Install**. Open the app and start downloading!

---

## 3. Android Instant CLI via Termux (Fastest 1-Click Mobile Setup)

If you or your friends prefer running MSK-YTDL directly on an Android phone without waiting for an APK build, you can use **Termux** (the official Android terminal).

### Instructions for Friends:
1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/) (free, open-source).
2. Open Termux on the phone and run:
   ```bash
   pkg update -y && pkg install -y git
   git clone https://github.com/your-username/msk-ytdl.git ~/msk-ytdl
   cd ~/msk-ytdl && bash install_android.sh
   ```
3. When prompted, tap **ALLOW** to grant storage permission so downloads save to the phone's public storage.
4. Done! Now you can simply type:
   ```bash
   msk-ytdl
   ```
   Or download a video:
   ```bash
   msk-ytdl --url "https://youtu.be/..." --mode video
   ```
5. **Media Storage:** Downloaded videos and MP3 files are automatically saved to:
   `/sdcard/Download/YouTube/`
   They immediately appear in the phone's **Gallery**, **Google Photos**, and **Music Players**!

---

## 4. Local Wi-Fi Sharing (Use Any Phone Browser Without Installing)

You can also run MSK-YTDL on your PC and share downloads across your home/office Wi-Fi network:
* Videos downloaded to your PC can be placed in a shared network folder or streamed directly to any device connected to the same Wi-Fi network.

---

## Summary of Packaging Artifacts

| Target Device | Format | How to Build / Share | Friend's Experience |
| :--- | :--- | :--- | :--- |
| **Windows PC** | Standalone Portable ZIP (`.exe`) | Run `build_exe.bat` -> Send `dist/MSK-YTDL-Windows-x64.zip` | Unzip and double-click `Start_MSK_YTDL.bat`. Zero install. |
| **Android Phone** | Native Android App (`.apk`) | Run GitHub Actions workflow -> Download APK | Tap APK on phone, allow installation, tap Download. |
| **Android Phone** | Termux Native CLI | Run `bash install_android.sh` in Termux | Runs natively in Termux, saves directly to phone's Gallery. |

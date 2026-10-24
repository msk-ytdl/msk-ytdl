"""
Create official Android Release Keystore for MSK YTDL
Publisher: MSK Software Solutions
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

KEYSTORE_PATH = Path(__file__).resolve().parent.parent / "msk_release.keystore"
KEYSTORE_ALIAS = "mskytdl"
KEYSTORE_PASS = "msksoftwaresolutions"
DNAME = "CN=MSK YTDL, OU=Software, O=MSK Software Solutions, L=Shikohabad, ST=Uttar Pradesh, C=IN"


def main():
    print("[MSK Software Solutions] Android Release Keystore Generator")
    print("=" * 60)

    if KEYSTORE_PATH.exists():
        print(f"[OK] Release keystore already exists: {KEYSTORE_PATH}")
        return 0

    keytool = shutil.which("keytool")
    if not keytool:
        # Check standard Java locations on Windows
        java_home = os.environ.get("JAVA_HOME", "")
        if java_home:
            cand = Path(java_home) / "bin" / "keytool.exe"
            if cand.exists():
                keytool = str(cand)

    if not keytool:
        print("[Notice] 'keytool' not found in PATH or JAVA_HOME.")
        print("When Java JDK is available, generate the release keystore by running:")
        print(
            f'keytool -genkeypair -v -keystore "{KEYSTORE_PATH}" -alias {KEYSTORE_ALIAS} '
            f'-keyalg RSA -keysize 2048 -validity 10000 -dname "{DNAME}" '
            f'-storepass {KEYSTORE_PASS} -keypass {KEYSTORE_PASS}'
        )
        return 0

    cmd = [
        keytool,
        "-genkeypair",
        "-v",
        "-keystore", str(KEYSTORE_PATH),
        "-alias", KEYSTORE_ALIAS,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-dname", DNAME,
        "-storepass", KEYSTORE_PASS,
        "-keypass", KEYSTORE_PASS,
    ]

    print(f"Generating keystore: {KEYSTORE_PATH}...")
    res = subprocess.run(cmd, check=False)
    if res.returncode == 0:
        print(f"[SUCCESS] Created Android release keystore: {KEYSTORE_PATH}")
        return 0
    else:
        print(f"[ERROR] keytool failed with code {res.returncode}")
        return res.returncode


if __name__ == "__main__":
    sys.exit(main())

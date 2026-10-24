#!/bin/bash
# Convenient symlink/forwarder to scripts/install_android_termux.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/scripts/install_android_termux.sh" "$@"

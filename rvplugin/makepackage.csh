#!/bin/bash

set -e
cd "$(dirname "$0")"

rm -f filesystembrowser.zip

# Package manifest and OpenRV mode entry point
zip filesystembrowser.zip PACKAGE openrv_mode.py

# OpenRV compatibility shims (xstudio API surface for OpenRV), no bytecache
zip -r filesystembrowser.zip openrv_compat/ \
    --exclude "openrv_compat/__pycache__/*"

# Plugin source — production files only, test/debug scripts excluded
zip filesystembrowser.zip \
    filesystem_browser/__init__.py \
    filesystem_browser/filesystem_browser.py \
    filesystem_browser/scanner.py \
    filesystem_browser/config.json

# QML assets (add when the OpenRV QML panel is ready)
if [ -d filesystem_browser/qml ]; then
    zip -r filesystembrowser.zip filesystem_browser/qml/
fi

echo "Created filesystembrowser.zip"

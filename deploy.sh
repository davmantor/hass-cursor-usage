#!/bin/bash
# Deploy hass-cursor-usage to local Home Assistant config
set -e

SRC="$(dirname "$0")/custom_components/hass_cursor_usage"
DEST="/home/trick/docker-services/hass-config/custom_components/hass_cursor_usage"

sudo mkdir -p "$DEST"
sudo cp "$SRC"/__init__.py "$SRC"/config_flow.py "$SRC"/const.py "$SRC"/manifest.json "$SRC"/sensor.py "$SRC"/strings.json "$DEST"/
sudo mkdir -p "$DEST/translations"
sudo cp "$SRC"/translations/en.json "$DEST/translations/"

echo "Deployed to $DEST"

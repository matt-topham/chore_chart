#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"

sudo apt update
sudo apt install -y python3-venv python3-openpyxl chromium curl unclutter

python3 -m venv --system-site-packages "$ROOT_DIR/.venv"

sed \
  -e "s|CHORE_USER|$APP_USER|g" \
  -e "s|CHORE_PATH|$ROOT_DIR|g" \
  "$ROOT_DIR/systemd/chore-touchscreen.service" \
  | sudo tee /etc/systemd/system/chore-touchscreen.service >/dev/null

sed \
  -e "s|CHORE_USER|$APP_USER|g" \
  -e "s|CHORE_PATH|$ROOT_DIR|g" \
  "$ROOT_DIR/systemd/chore-backup.service" \
  | sudo tee /etc/systemd/system/chore-backup.service >/dev/null
sudo cp "$ROOT_DIR/systemd/chore-backup.timer" /etc/systemd/system/chore-backup.timer

mkdir -p "$HOME_DIR/.config/autostart"
cat > "$HOME_DIR/.config/autostart/chore-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Chore Touchscreen Kiosk
Exec=$ROOT_DIR/scripts/start-kiosk.sh
X-GNOME-Autostart-enabled=true
Terminal=false
EOF
chown -R "$APP_USER:$APP_USER" "$HOME_DIR/.config/autostart"

sudo systemctl daemon-reload
sudo systemctl enable --now chore-touchscreen.service
sudo systemctl enable --now chore-backup.timer

echo
echo "Installation complete."
echo "Open http://localhost:5000 or reboot to launch kiosk mode."

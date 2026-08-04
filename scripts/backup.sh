#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$ROOT_DIR/backups"
mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y-%m-%d_%H-%M-%S)"
if [[ -f "$ROOT_DIR/data/chore_touchscreen.db" ]]; then
  cp "$ROOT_DIR/data/chore_touchscreen.db" "$BACKUP_DIR/chore_touchscreen_$stamp.db"
fi
find "$BACKUP_DIR" -type f -name '*.db' -mtime +30 -delete

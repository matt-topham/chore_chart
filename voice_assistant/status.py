from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_voice_status(base_dir: Path, state: str, text: str = "") -> None:
    target = base_dir / "chore_app/static/voice-status.json"
    temporary = target.with_suffix(".tmp")
    payload = {
        "state": state,
        "text": text[:180],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        pass

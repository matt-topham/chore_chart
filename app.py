from __future__ import annotations

import os
from pathlib import Path

from chore_app.env import load_env_file
from chore_app.server import build_server

BASE_DIR = Path(__file__).resolve().parent
load_env_file(BASE_DIR / ".env")


def main() -> None:
    host = os.environ.get("CHORE_HOST", "0.0.0.0")
    port = int(os.environ.get("CHORE_PORT", "5000"))
    timezone_name = os.environ.get("CHORE_TIMEZONE", "America/Los_Angeles")
    database_path = BASE_DIR / os.environ.get("CHORE_DATABASE", "data/chore_touchscreen.db")
    workbook_path = BASE_DIR / os.environ.get("CHORE_WORKBOOK", "data/Apartment Routine.xlsx")
    upcoming_days = int(os.environ.get("CHORE_UPCOMING_DAYS", "7"))

    server = build_server(
        host,
        port,
        database_path=database_path,
        workbook_path=workbook_path,
        base_dir=BASE_DIR,
        timezone_name=timezone_name,
        upcoming_days=upcoming_days,
    )
    print(f"Chore Touchscreen running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

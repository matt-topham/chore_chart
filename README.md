# Home Dashboard

A local Raspberry Pi touchscreen household dashboard built around the apartment chore tracker. The app imports `Apartment Routine.xlsx` into SQLite, tracks chore completion history and recurrence, and now also provides weather, Google Calendar, groceries, reminders, notes, and the optional **Hey Bellamy** voice assistant.

## Included behavior

- Home dashboard with chores, calendar, weather, reminders, groceries, and notes
- Large touch-friendly chore **Done** buttons
- Due, overdue, upcoming, and completed-today sections
- Area filters such as Kitchen, Bathroom, and Bedroom
- Permanent completion history in `data/chore_touchscreen.db`
- Daily automatic database backups with 30-day retention
- Chromium kiosk launch at desktop login
- Web access from another device on the same network
- Optional local voice assistant using the wake phrase **Hey Bellamy**

## Scheduling rules

- **Daily:** next calendar day
- **Twice-Weekly / Weekly:** next named weekday from the spreadsheet
- **Bi-Weekly:** every 14 days from the initial assigned date
- **Monthly / Quarterly / Semi-Annually / Annually:** rolling interval from the actual completion date, moved forward to the preferred weekday
- A missed chore stays overdue until it is completed
- Initial long-term chores are staggered across upcoming Saturdays so the first weekend is not overloaded

The importer also corrects these source-data issues in memory:

- `Tidy Bathrrom` → `Tidy Bathroom`
- `Quaterly` → `Quarterly`
- `Vacuum Mattress` area → `Bedroom`

The original Excel file is not modified.

## Configuration

Copy the example file once:

```bash
cp config.example.env .env
```

Edit `.env` with the local weather, calendar, and voice settings. `.env` is ignored by Git and is loaded automatically by both the dashboard and Bellamy services.

## Test on a Mac or Linux computer

```bash
cd chore_chart
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open the port configured by `CHORE_PORT`, for example `http://localhost:5000`.

The main dashboard is `/`, the full chore screen is `/tasks`, and completion history is `/history`.

## Install on Raspberry Pi 5

This assumes Raspberry Pi OS with Desktop and a touchscreen already working. Copy this folder to the Pi, then run:

```bash
cd chore_chart
./scripts/install-pi.sh
sudo reboot
```

After reboot, Chromium should open full-screen at the dashboard.

## Hey Bellamy voice assistant

Bellamy can complete chores, add groceries, add reminders and household notes, and read weather, chores, groceries, and Google Calendar data. Speech recognition and spoken confirmations run locally.

Full microphone, Whisper, testing, and systemd instructions are in [`VOICE_SETUP.md`](VOICE_SETUP.md).

## Useful service commands

```bash
sudo systemctl status chore-touchscreen.service
sudo systemctl restart chore-touchscreen.service
journalctl -u chore-touchscreen.service -f

sudo systemctl status home-voice.service
sudo systemctl restart home-voice.service
journalctl -u home-voice.service -f
```

## Updating the spreadsheet

Edit `data/Apartment Routine.xlsx`, then press the reimport endpoint from the Pi:

```bash
curl -X POST http://localhost:5000/api/admin/reimport
```

Existing completion history is preserved. Existing chores are updated by matching `Task + Area`; newly added chores are inserted.

## Resetting everything

Stop the service and remove the database:

```bash
sudo systemctl stop chore-touchscreen.service
rm data/chore_touchscreen.db
sudo systemctl start chore-touchscreen.service
```

The workbook will be imported again automatically.

## Main files

- `app.py` — production server entry point
- `chore_app/server.py` — local web server and JSON API
- `chore_app/scheduler.py` — recurrence calculations
- `chore_app/importer.py` — Excel import and cleanup
- `chore_app/templates/` — touchscreen pages
- `chore_app/static/` — styling and browser logic
- `voice_assistant/` — Hey Bellamy command, audio, API, and status logic
- `scripts/install-pi.sh` — Raspberry Pi dashboard installation
- `scripts/setup_bellamy_voice.sh` — Whisper/microphone setup
- `systemd/home-voice.service` — Bellamy background service template

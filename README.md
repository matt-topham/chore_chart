# Chore Touchscreen

A local Raspberry Pi touchscreen checklist built from `Apartment Routine.xlsx`.
The app imports the spreadsheet into SQLite, shows chores that are due, records
completion history, calculates the next due date, and supports undo.

## Included behavior

- Large touch-friendly **Done** buttons
- Due, overdue, upcoming, and completed-today sections
- Area filters such as Kitchen, Bathroom, and Bedroom
- Permanent completion history in `data/chore_touchscreen.db`
- Daily automatic database backups with 30-day retention
- Chromium kiosk launch at desktop login
- Web access from another device on the same network

## Scheduling rules

- **Daily:** next calendar day
- **Twice-Weekly / Weekly:** next named weekday from the spreadsheet
- **Bi-Weekly:** every 14 days from the initial assigned date
- **Monthly / Quarterly / Semi-Annually / Annually:** rolling interval from the
  actual completion date, moved forward to the preferred weekday
- A missed chore stays overdue until it is completed
- Initial long-term chores are staggered across upcoming Saturdays so the first
  weekend is not overloaded

The importer also corrects these source-data issues in memory:

- `Tidy Bathrrom` → `Tidy Bathroom`
- `Quaterly` → `Quarterly`
- `Vacuum Mattress` area → `Bedroom`

The original Excel file is not modified.

## Test on a Mac or Linux computer

```bash
cd chore-touchscreen
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

To test from another device on the same network, open:

```text
http://COMPUTER-IP-ADDRESS:5000
```

## Install on Raspberry Pi 5

This assumes Raspberry Pi OS with Desktop and a touchscreen already working.
Copy this folder to the Pi, then run:

```bash
cd chore-touchscreen
./scripts/install-pi.sh
sudo reboot
```

After reboot, Chromium should open full-screen at the chore dashboard.

## Useful service commands

```bash
sudo systemctl status chore-touchscreen.service
sudo systemctl restart chore-touchscreen.service
journalctl -u chore-touchscreen.service -f
```

The web service listens on port `5000` by default.

## Updating the spreadsheet

Edit `data/Apartment Routine.xlsx`, then press the reimport endpoint from the Pi:

```bash
curl -X POST http://localhost:5000/api/admin/reimport
```

Existing completion history is preserved. Existing chores are updated by matching
`Task + Area`; newly added chores are inserted.

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
- `scripts/install-pi.sh` — Raspberry Pi installation

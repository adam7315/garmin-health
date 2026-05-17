"""
Fetch Garmin Connect data and merge into garmin_data.json.
Normal run: fetches last FETCH_DAYS days (default 60) and merges with existing.
Backfill:   set FETCH_DAYS=1825 (or more) to pull full history.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from garminconnect import Garmin

EMAIL      = os.environ.get("GARMIN_EMAIL",      "adam7315@gmail.com")
PASSWORD   = os.environ.get("GARMIN_PASSWORD",   "Adam7315123")
TOKEN_FILE = os.environ.get("GARMIN_TOKEN_DIR",  r"C:\Users\USER\Desktop\garmin_tokens")
DATA_FILE  = os.environ.get("GARMIN_DATA_FILE",  r"C:\Users\USER\Desktop\garmin_data.json")
FETCH_DAYS = int(os.environ.get("FETCH_DAYS", "60"))

def load_existing():
    """Load existing data as dicts keyed by date."""
    steps, sleep, hr_cal, hourly = {}, {}, {}, {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            old = json.load(f)
        for r in old.get("steps", []):
            d = r.get("calendarDate")
            if d:
                steps[d] = r
        for r in old.get("sleep", []):
            d = r.get("calendarDate")
            if d:
                sleep[d] = r
        hr_cal  = old.get("hr_cal", {})
        hourly  = old.get("steps_hourly", {})
        print(f"Loaded existing: {len(steps)} step days, {len(sleep)} sleep days")
    return steps, sleep, hr_cal, hourly

def login():
    mfa_code = sys.argv[1] if len(sys.argv) > 1 else None
    token_ok = False
    if os.path.exists(TOKEN_FILE):
        try:
            client = Garmin(EMAIL, PASSWORD)
            client.login(tokenstore=TOKEN_FILE)
            print("Token 登入成功")
            token_ok = True
        except Exception as e:
            print(f"Token 過期：{e}")
    if not token_ok:
        fn = (lambda: mfa_code) if mfa_code else (lambda: input("Garmin MFA: "))
        client = Garmin(EMAIL, PASSWORD, prompt_mfa=fn)
        client.login()
        client.client.dump(TOKEN_FILE)
    try:
        client.client.dump(TOKEN_FILE)
    except Exception:
        pass
    return client

def fetch_data():
    steps_db, sleep_db, hr_cal_db, hourly_db = load_existing()
    client = login()

    today = date.today()
    start = today - timedelta(days=FETCH_DAYS)
    print(f"Fetching {start} → {today} ({FETCH_DAYS} days)...")

    # ── Steps ────────────────────────────────────────────────
    current = start
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            daily = client.get_steps_data(date_str)
            if isinstance(daily, list):
                total = sum(s.get("steps", 0) for s in daily)
                steps_db[date_str] = {"calendarDate": date_str, "totalSteps": total}
                hourly = [0] * 24
                for iv in daily:
                    gmt = iv.get("startGMT", "")
                    s = int(iv.get("steps", 0) or 0)
                    if gmt and s > 0:
                        try:
                            h_local = (int(gmt[11:13]) + 8) % 24
                            hourly[h_local] += s
                        except Exception:
                            pass
                if any(v > 0 for v in hourly):
                    hourly_db[date_str] = hourly
            else:
                if date_str not in steps_db:
                    steps_db[date_str] = {"calendarDate": date_str, "totalSteps": 0}
        except Exception as e:
            print(f"  steps {date_str}: {e}")
            if date_str not in steps_db:
                steps_db[date_str] = {"calendarDate": date_str, "totalSteps": None}
        current += timedelta(days=1)

    # ── Sleep ────────────────────────────────────────────────
    current = start
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            s = client.get_sleep_data(date_str)
            if s and "dailySleepDTO" in s:
                dto = s["dailySleepDTO"]
                sleep_db[date_str] = {
                    "calendarDate": date_str,
                    "overallScore": dto.get("sleepScores", {}).get("overall", {}).get("value")
                                    if isinstance(dto.get("sleepScores"), dict) else None,
                    "deepSleepSeconds":  dto.get("deepSleepSeconds"),
                    "lightSleepSeconds": dto.get("lightSleepSeconds"),
                    "remSleepSeconds":   dto.get("remSleepSeconds"),
                    "awakeSleepSeconds": dto.get("awakeSleepSeconds"),
                    "sleepStartTimestampGMT": dto.get("sleepStartTimestampGMT"),
                    "sleepEndTimestampGMT":   dto.get("sleepEndTimestampGMT"),
                }
            else:
                if date_str not in sleep_db:
                    sleep_db[date_str] = {"calendarDate": date_str}
        except Exception as e:
            print(f"  sleep {date_str}: {e}")
            if date_str not in sleep_db:
                sleep_db[date_str] = {"calendarDate": date_str}
        current += timedelta(days=1)

    # ── HR / Calories (recent 30 days only) ──────────────────
    current = today - timedelta(days=30)
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            summary = client.get_user_summary(date_str)
            hr_cal_db[date_str] = {
                "restingHeartRate":    summary.get("restingHeartRate"),
                "activeKilocalories":  summary.get("activeKilocalories"),
                "totalKilocalories":   summary.get("totalKilocalories"),
            }
        except Exception:
            pass
        current += timedelta(days=1)

    # ── Save ─────────────────────────────────────────────────
    cache = {
        "fetched_at": datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M"),
        "steps":        sorted(steps_db.values(), key=lambda r: r["calendarDate"]),
        "sleep":        sorted(sleep_db.values(), key=lambda r: r["calendarDate"]),
        "hr_cal":       hr_cal_db,
        "steps_hourly": hourly_db,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Saved: {len(steps_db)} step days, {len(sleep_db)} sleep days → {DATA_FILE}")

if __name__ == "__main__":
    fetch_data()

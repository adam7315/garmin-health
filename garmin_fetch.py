"""
Fetch latest Garmin Connect data and save to local cache.
Usage: python garmin_fetch.py [MFA_CODE]
"""
import json
import os
import sys
from datetime import date, timedelta
from garminconnect import Garmin

EMAIL      = os.environ.get("GARMIN_EMAIL",      "adam7315@gmail.com")
PASSWORD   = os.environ.get("GARMIN_PASSWORD",   "Adam7315123")
CACHE_FILE = os.environ.get("GARMIN_CACHE_FILE", r"C:\Users\USER\Desktop\garmin_cache.json")
TOKEN_FILE = os.environ.get("GARMIN_TOKEN_DIR",  r"C:\Users\USER\Desktop\garmin_tokens")

def fetch_data():
    mfa_code = sys.argv[1] if len(sys.argv) > 1 else None

    print("Connecting to Garmin Connect...")

    token_ok = False
    if os.path.exists(TOKEN_FILE):
        try:
            client = Garmin(EMAIL, PASSWORD)
            client.login(tokenstore=TOKEN_FILE)
            print("Token 登入成功！")
            token_ok = True
        except Exception as e:
            print(f"Token 已過期：{e}")

    if not token_ok:
        prompt_mfa_fn = (lambda: mfa_code) if mfa_code else None
        client = Garmin(EMAIL, PASSWORD, prompt_mfa=prompt_mfa_fn)
        client.login()
        client.client.dump(TOKEN_FILE)
        print(f"Token 已存至 {TOKEN_FILE}。")

    try:
        client.client.dump(TOKEN_FILE)
    except Exception:
        pass

    print("登入成功！")

    today = date.today()
    start = today - timedelta(days=365)

    print(f"Fetching steps from {start} to {today}...")
    steps_data = []
    current = start
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            daily = client.get_steps_data(date_str)
            total = sum(s.get("steps", 0) for s in daily) if isinstance(daily, list) else 0
            steps_data.append({"calendarDate": date_str, "totalSteps": total})
        except Exception:
            steps_data.append({"calendarDate": date_str, "totalSteps": None})
        current += timedelta(days=1)

    print(f"Fetching sleep from {start} to {today}...")
    sleep_data = []
    current = start
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            s = client.get_sleep_data(date_str)
            if s and "dailySleepDTO" in s:
                dto = s["dailySleepDTO"]
                sleep_data.append({
                    "calendarDate": date_str,
                    "overallScore": dto.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(dto.get("sleepScores"), dict) else None,
                    "deepSleepSeconds": dto.get("deepSleepSeconds"),
                    "lightSleepSeconds": dto.get("lightSleepSeconds"),
                    "remSleepSeconds": dto.get("remSleepSeconds"),
                    "awakeSleepSeconds": dto.get("awakeSleepSeconds"),
                    "sleepStartTimestampGMT": dto.get("sleepStartTimestampGMT"),
                    "sleepEndTimestampGMT": dto.get("sleepEndTimestampGMT"),
                })
            else:
                sleep_data.append({"calendarDate": date_str})
        except Exception:
            sleep_data.append({"calendarDate": date_str})
        current += timedelta(days=1)

    print("Fetching user summary (HR, calories) for recent 30 days...")
    hr_cal_data = {}
    current = today - timedelta(days=30)
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        try:
            summary = client.get_user_summary(date_str)
            hr_cal_data[date_str] = {
                "restingHeartRate": summary.get("restingHeartRate"),
                "activeKilocalories": summary.get("activeKilocalories"),
                "totalKilocalories": summary.get("totalKilocalories"),
            }
        except Exception:
            pass
        current += timedelta(days=1)

    cache = {
        "fetched_at": today.isoformat(),
        "steps": steps_data,
        "sleep": sleep_data,
        "hr_cal": hr_cal_data,
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(steps_data)} step records and {len(sleep_data)} sleep records to {CACHE_FILE}")

if __name__ == "__main__":
    fetch_data()

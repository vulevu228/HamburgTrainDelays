"""
Hamburg Hbf arrival-delay collector (one-shot).

Runs ONCE per invocation: pulls the Deutsche Bahn Timetables API, joins the
planned schedule against the live change feed, and upserts one row per train
into hamburg_delays.csv. Schedule it (Task Scheduler / cron) for a growing
dataset -- see scripts/collect_and_push.ps1.

Why two endpoints:
  * /plan/{eva}/{yymmdd}/{hh}  -> the *planned* timetable for one hour
                                 (planned arrival `pt`, line `l`, category,
                                 train number, platform, origin).
  * /fchg/{eva}                -> *changes only*: current/estimated arrival
                                 `ct` and cancellation flag `cs`.
The change feed almost never restates the planned time, so on its own ~88%
of rows have no `planned_arr` and no delay can be computed. Joining the two
feeds on the stop id (`s/@id`, unique per train run) recovers it.
"""

import csv
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("DB_CLIENT_ID")
API_KEY = os.getenv("DB_API_KEY")

HAMBURG_HBF = "8002549"
BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
HEADERS = {"DB-Client-Id": CLIENT_ID, "DB-Api-Key": API_KEY, "accept": "application/xml"}

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hamburg_delays.csv")
FIELDS = [
    "check_time", "train_id", "category", "line", "train_no",
    "planned_arr", "actual_arr", "delay_min", "cancelled", "platform",
    "origin", "source",
]


def _die(msg):
    print(f"[collector] {msg}")
    sys.exit(1)


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 401:
        _die("401 Unauthorized - check DB_CLIENT_ID / DB_API_KEY and the API subscription.")
    r.raise_for_status()
    return ET.fromstring(r.content)


def _parse_ts(raw):
    """DB timestamp 'YYMMDDHHMM' -> datetime, or None."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%y%m%d%H%M")
    except ValueError:
        return None


def fetch_plan():
    """Planned timetable for the previous / current / next hour, keyed by stop id."""
    plan = {}
    now = datetime.now()
    for offset in (-1, 0, 1):
        slot = now + timedelta(hours=offset)
        try:
            root = _get(f"{BASE}/plan/{HAMBURG_HBF}/{slot:%y%m%d}/{slot:%H}")
        except requests.HTTPError as exc:
            print(f"[collector] plan {slot:%y%m%d}/{slot:%H} failed: {exc}")
            continue
        for s in root.findall("s"):
            ar = s.find("ar")
            if ar is None:
                continue
            tl = s.find("tl")
            ppth = ar.get("ppth") or ""
            plan[s.get("id")] = {
                "category": (tl.get("c") if tl is not None else "") or "",
                "line": ar.get("l") or "",
                "train_no": (tl.get("n") if tl is not None else "") or "",
                "planned_arr": ar.get("pt") or "",
                "platform": ar.get("pp") or "",
                "origin": ppth.split("|")[0] if ppth else "",
            }
    return plan


def fetch_changes():
    """Live arrival changes, keyed by stop id."""
    root = _get(f"{BASE}/fchg/{HAMBURG_HBF}")
    changes = {}
    for s in root.findall("s"):
        ar = s.find("ar")
        if ar is None:
            continue
        changes[s.get("id")] = {
            "actual_arr": ar.get("ct") or "",
            "planned_arr": ar.get("pt") or "",
            "cancelled": 1 if ar.get("cs") == "c" else 0,
            "platform": ar.get("cp") or "",
            "line": ar.get("l") or "",
        }
    return changes


def build_rows(plan, changes):
    """One row per train seen in either feed.

    Every train in the plan window is recorded; if the change feed carries no
    revised arrival for it, it counts as on-time (actual = planned, delay 0).
    Trains that appear only in the change feed (arriving outside the plan
    window) are recorded too, but without a planned time until a later run
    catches them inside the window and upserts it.
    """
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for stop_id in set(plan) | set(changes):
        base = plan.get(stop_id, {})
        chg = changes.get(stop_id, {})

        planned_dt = _parse_ts(chg.get("planned_arr") or base.get("planned_arr", ""))
        actual_dt = _parse_ts(chg.get("actual_arr"))
        cancelled = int(chg.get("cancelled", 0))

        if actual_dt is None and not cancelled:
            if planned_dt is None:
                continue          # change-feed row with no usable time yet
            actual_dt = planned_dt  # in the plan, no change reported -> on time

        delay = ""
        if planned_dt and actual_dt and not cancelled:
            delay = round((actual_dt - planned_dt).total_seconds() / 60)

        rows.append({
            "check_time": now_iso,
            "train_id": stop_id,
            "category": base.get("category", ""),
            "line": base.get("line") or chg.get("line", ""),
            "train_no": base.get("train_no", ""),
            "planned_arr": planned_dt.strftime("%Y-%m-%d %H:%M") if planned_dt else "",
            "actual_arr": actual_dt.strftime("%Y-%m-%d %H:%M") if actual_dt else "",
            "delay_min": delay,
            "cancelled": cancelled,
            "platform": chg.get("platform") or base.get("platform", ""),
            "origin": base.get("origin", ""),
            "source": "live",
        })
    return rows


def upsert(rows):
    """Merge new rows into the CSV, one row per train_id (latest observation wins)."""
    existing = {}
    if os.path.isfile(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                # tolerate the pre-migration schema by filling gaps
                existing[row.get("train_id", "")] = {k: row.get(k, "") for k in FIELDS}

    added = updated = 0
    for row in rows:
        key = row["train_id"]
        if key in existing:
            updated += 1
        else:
            added += 1
        existing[key] = row

    ordered = sorted(
        existing.values(),
        key=lambda r: (r.get("check_time", ""), r.get("planned_arr", "")),
    )
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered)
    os.replace(tmp, CSV_PATH)
    return added, updated, len(ordered)


def main():
    if not (CLIENT_ID and API_KEY):
        _die("Keys not found. Put DB_CLIENT_ID / DB_API_KEY in .env")

    plan = fetch_plan()
    changes = fetch_changes()
    rows = build_rows(plan, changes)
    added, updated, total = upsert(rows)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] plan={len(plan)} changes={len(changes)} -> +{added} new, "
          f"~{updated} updated, {total} rows total")


if __name__ == "__main__":
    main()

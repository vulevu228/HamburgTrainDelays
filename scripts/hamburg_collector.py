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
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("DB_CLIENT_ID")
API_KEY = os.getenv("DB_API_KEY")

HAMBURG_HBF = "8002549"
BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
HEADERS = {"DB-Client-Id": CLIENT_ID, "DB-Api-Key": API_KEY, "accept": "application/xml"}

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hamburg_delays.csv")
# Fields only the planned timetable knows. The change feed keeps a train for
# hours after it has left the +-1 h plan window, so a later poll often sees it
# *without* these -- they must never be blanked by such a poll.
PLAN_FIELDS = ("category", "line", "train_no", "planned_arr", "platform", "origin")

# The API's timestamps are German local time. GitHub Actions runs in UTC, so
# never rely on the machine's clock zone.
BERLIN = ZoneInfo("Europe/Berlin")

FIELDS = [
    "check_time", "train_id", "category", "line", "train_no",
    "planned_arr", "actual_arr", "delay_min", "cancelled", "platform",
    "origin", "source",
]


def _die(msg):
    print(f"[collector] {msg}")
    sys.exit(1)


def _get(url, attempts=3):
    """GET with retry: the DB API occasionally stalls past the 30 s read timeout."""
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 401:
                _die("401 Unauthorized - check DB_CLIENT_ID / DB_API_KEY and the API subscription.")
            if r.status_code == 429 or r.status_code >= 500:
                r.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            if attempt == attempts:
                raise
            print(f"[collector] {url.rsplit('/', 1)[-1]} attempt {attempt}/{attempts} failed "
                  f"({type(exc).__name__}), retrying")
            time.sleep(5 * attempt)
    r.raise_for_status()
    return ET.fromstring(r.content)


def _now():
    """Current Berlin wall-clock time (naive, to match the API's timestamps)."""
    return datetime.now(BERLIN).replace(tzinfo=None)


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
    now = _now()
    for offset in (-1, 0, 1):
        slot = now + timedelta(hours=offset)
        try:
            root = _get(f"{BASE}/plan/{HAMBURG_HBF}/{slot:%y%m%d}/{slot:%H}")
        except requests.RequestException as exc:
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
    now_iso = _now().strftime("%Y-%m-%d %H:%M")
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
            # True when this poll's change feed reported on the train. Only
            # then are actual_arr / cancelled authoritative; a plan-only
            # sighting just means "no change known right now".
            "_in_changes": stop_id in changes,
        })
    return rows


def _filled(rows, field):
    return sum(1 for r in rows if r.get(field) not in ("", None))


def merge_row(old, new):
    """Fold a new observation into the stored row without losing information.

    * plan fields: a value, once known, is kept unless the new poll has one.
    * actual_arr / cancelled: updated only from a change-feed sighting, so a
      delayed train later seen only in the plan isn't reset to "on time".
    * delay_min: recomputed from the merged times.
    """
    merged = dict(old)
    merged["train_id"] = new["train_id"]
    merged["check_time"] = new["check_time"]
    merged["source"] = new["source"]
    for f in PLAN_FIELDS:
        if new.get(f):
            merged[f] = new[f]
    if new.get("_in_changes"):
        merged["cancelled"] = new["cancelled"]
        if new.get("actual_arr"):
            merged["actual_arr"] = new["actual_arr"]
    elif not merged.get("actual_arr"):
        merged["actual_arr"] = new.get("actual_arr", "")

    planned = _parse_iso(merged.get("planned_arr"))
    actual = _parse_iso(merged.get("actual_arr"))
    if planned and actual and str(merged.get("cancelled")) != "1":
        merged["delay_min"] = round((actual - planned).total_seconds() / 60)
    else:
        merged["delay_min"] = ""
    return merged


def _parse_iso(raw):
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M") if raw else None
    except ValueError:
        return None


def upsert(rows):
    """Merge new rows into the CSV, one row per train_id (see merge_row)."""
    existing = {}
    if os.path.isfile(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row.get("train_id"):
                    continue
                # tolerate the pre-migration schema by filling gaps
                existing[row["train_id"]] = {k: row.get(k, "") for k in FIELDS}
        # Unreadable / truncated / conflict-marked file: never replace it.
        if "train_id" not in (reader.fieldnames or []) or (
                not existing and os.path.getsize(CSV_PATH) > 1024):
            _die("hamburg_delays.csv is unreadable or has no rows - refusing to overwrite it.")
    before = list(existing.values())

    added = updated = 0
    for row in rows:
        key = row["train_id"]
        if key in existing:
            updated += 1
            existing[key] = merge_row(existing[key], row)
        else:
            added += 1
            existing[key] = merge_row({k: "" for k in FIELDS}, row)

    # Data-loss guard: a poll may only add information. If the row count or
    # any field's fill count went down, something is wrong - keep the old file.
    after = list(existing.values())
    if len(after) < len(before):
        _die(f"row count would drop {len(before)} -> {len(after)} - not writing.")
    for f in PLAN_FIELDS:
        if _filled(after, f) < _filled(before, f):
            _die(f"'{f}' would lose values ({_filled(before, f)} -> {_filled(after, f)}) - not writing.")

    ordered = sorted(
        existing.values(),
        key=lambda r: (r.get("check_time", ""), r.get("planned_arr", "")),
    )
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        # Force LF: csv defaults to CRLF, which made the Windows and the
        # GitHub Actions runs disagree on every line and collide on merge.
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(ordered)
    os.replace(tmp, CSV_PATH)
    return added, updated, len(ordered)


def main():
    if not (CLIENT_ID and API_KEY):
        _die("Keys not found. Put DB_CLIENT_ID / DB_API_KEY in .env")

    plan = fetch_plan()
    try:
        changes = fetch_changes()
    except requests.RequestException as exc:
        # Retries exhausted: skip this poll rather than fail the run; the next one catches up.
        print(f"[collector] change feed unavailable, skipping this poll: {exc}")
        return
    rows = build_rows(plan, changes)
    added, updated, total = upsert(rows)
    stamp = _now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] plan={len(plan)} changes={len(changes)} -> +{added} new, "
          f"~{updated} updated, {total} rows total")


if __name__ == "__main__":
    main()

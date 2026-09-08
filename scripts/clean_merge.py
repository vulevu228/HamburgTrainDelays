"""
One-off migration: fold the legacy May/August captures into the current
hamburg_delays.csv schema.

Legacy files (raw, git-ignored under data/ or *.legacy_*.csv):
  * data/hamburg_delays.csv        - dense May 7-8 capture, ISO check_time
  * hamburg_delays.legacy_root.csv - May 8 + Aug 25, round-tripped through
                                     Excel: DD/MM/YYYY check_time and ~48% of
                                     train_ids mangled into '-8.4E+18' floats.

What this does:
  * drops rows whose train_id was destroyed by Excel's number coercion
  * normalises both timestamp styles to 'YYYY-MM-DD HH:MM'
  * converts the DB 'YYMMDDHHMM' arrival integers to real timestamps
  * collapses each capture to one row per train (last observation = final delay)
  * derives category from the line label, tags source='legacy'
  * merges under any existing live rows (live always wins on train_id)
"""

import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "hamburg_delays.csv")
LEGACY = [
    (os.path.join(ROOT, "data", "hamburg_delays.csv"), False),
    (os.path.join(ROOT, "hamburg_delays.legacy_root.csv"), True),
]
FIELDS = [
    "check_time", "train_id", "category", "line", "train_no",
    "planned_arr", "actual_arr", "delay_min", "cancelled", "platform",
    "origin", "source",
]
BAD_ID = re.compile(r"[eE]\+\d")


def _category(line):
    line = (line or "").strip()
    m = re.match(r"([A-Za-z]+)", line)
    return m.group(1).upper() if m else ""


def load_legacy(path, dayfirst):
    if not os.path.isfile(path):
        print(f"  skip (missing): {path}")
        return pd.DataFrame(columns=FIELDS)

    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    before = len(raw)
    raw = raw[~raw["train_id"].str.contains(BAD_ID, na=False)]
    dropped = before - len(raw)

    check = pd.to_datetime(raw["check_time"], dayfirst=dayfirst, errors="coerce")
    planned = pd.to_datetime(raw["planned_arr"], format="%y%m%d%H%M", errors="coerce")
    actual = pd.to_datetime(raw["actual_arr"], format="%y%m%d%H%M", errors="coerce")

    delay = (actual - planned).dt.total_seconds() / 60
    df = pd.DataFrame({
        "check_time": check.dt.strftime("%Y-%m-%d %H:%M"),
        "train_id": raw["train_id"].str.strip(),
        "category": raw["status"].map(_category),
        "line": raw["status"].str.strip(),
        "train_no": "",
        "planned_arr": planned.dt.strftime("%Y-%m-%d %H:%M"),
        "actual_arr": actual.dt.strftime("%Y-%m-%d %H:%M"),
        "delay_min": delay.round(),
        "cancelled": 0,
        "platform": "",
        "origin": "",
        "source": "legacy",
    })
    df = df.dropna(subset=["check_time"])
    df = df[df["train_id"] != ""]
    # one row per train: keep the last (most settled) observation
    df = df.sort_values("check_time").drop_duplicates("train_id", keep="last")
    print(f"  {os.path.basename(path)}: {before} rows -> {len(df)} trains "
          f"({dropped} dropped for mangled id)")
    return df[FIELDS]


def main():
    frames = [load_legacy(path, dayfirst) for path, dayfirst in LEGACY]

    live = pd.DataFrame(columns=FIELDS)
    if os.path.isfile(OUT):
        live = pd.read_csv(OUT, dtype=str, keep_default_na=False)
        if "source" not in live or live.empty:
            live = live.reindex(columns=FIELDS)
        live = live[live.get("source", "") == "live"] if "source" in live else live
        print(f"  existing live rows kept: {len(live)}")

    merged = pd.concat(frames + [live], ignore_index=True)
    merged["delay_min"] = pd.to_numeric(merged["delay_min"], errors="coerce")
    # live wins over legacy when the same train_id shows up in both
    merged["_rank"] = (merged["source"] == "live").astype(int)
    merged = (merged.sort_values(["_rank", "check_time"])
                    .drop_duplicates("train_id", keep="last")
                    .drop(columns="_rank"))
    merged = merged.sort_values(["check_time", "planned_arr"], na_position="last")

    merged.to_csv(OUT, index=False, columns=FIELDS)
    span = f"{merged['check_time'].min()} .. {merged['check_time'].max()}"
    print(f"\nwrote {len(merged)} rows -> {OUT}")
    print(f"  span         : {span}")
    print(f"  with delay   : {merged['delay_min'].notna().sum()}")
    print(f"  by source    : {merged['source'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()

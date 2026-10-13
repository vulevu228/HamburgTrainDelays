"""
One-off backfill: recover fields the old collector blanked, from git history.

Before the 2026-10-08 merge_row() fix, every poll replaced a train's whole
row, so once a train left the +-1 h /plan window its planned_arr, category,
line, train_no, platform and origin went blank (and with them delay_min).
Every earlier poll's CSV is still in git, so this replays all committed
versions of hamburg_delays.csv and, per train_id, fills each blank field in
the given CSV with the most recent non-blank value ever committed. Trains
that vanished from the file entirely are restored from their last sighting.
delay_min is then recomputed exactly as the collector does.

Usage:  python scripts/backfill_history.py [path/to/hamburg_delays.csv]
Run it on a fresh checkout of origin/main and commit the result straight
away -- the collectors rewrite the file every 15 minutes.
"""

import csv
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hamburg_collector import CSV_PATH, FIELDS, PLAN_FIELDS, _filled, _parse_iso  # noqa: E402

FILL_FIELDS = PLAN_FIELDS + ("actual_arr",)
TIME_FIELDS = ("planned_arr", "actual_arr")


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True).stdout


def history_values(repo):
    """{train_id: {field: latest non-blank value}} across every committed version."""
    commits = _git("log", "--reverse", "--format=%H", "--", "hamburg_delays.csv",
                   cwd=repo).decode().split()
    proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    known, skipped = {}, 0
    for sha in commits:
        proc.stdin.write(f"{sha}:hamburg_delays.csv\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] == "missing":
            continue
        blob = proc.stdout.read(int(header[2]))
        proc.stdout.readline()
        text = blob.decode("utf-8", errors="replace")
        if "<<<<<<<" in text or not text.startswith("check_time,train_id"):
            skipped += 1          # conflict-marked or pre-migration schema
            continue
        for row in csv.DictReader(io.StringIO(text)):
            tid = row.get("train_id")
            if not tid or "E+" in tid:
                continue          # Excel-mangled id
            seen = known.setdefault(tid, {})
            for f in FIELDS:
                v = (row.get(f) or "").strip()
                if not v:
                    continue
                if f in TIME_FIELDS and _parse_iso(v) is None:
                    continue
                seen[f] = v       # later commits overwrite earlier ones
    proc.stdin.close()
    proc.wait()
    print(f"[backfill] {len(commits)} versions read, {skipped} skipped, "
          f"{len(known)} train ids in history")
    return known


def recompute_delay(row):
    planned = _parse_iso(row.get("planned_arr"))
    actual = _parse_iso(row.get("actual_arr"))
    if planned and actual and str(row.get("cancelled")) != "1":
        row["delay_min"] = round((actual - planned).total_seconds() / 60)
    else:
        row["delay_min"] = ""


def main():
    path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    repo = os.path.dirname(path)
    known = history_values(repo)

    with open(path, newline="", encoding="utf-8") as fh:
        rows = {r["train_id"]: {k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(fh)}
    before = list(rows.values())
    before_fill = {f: _filled(before, f) for f in FIELDS}

    restored = 0
    for tid, seen in known.items():
        if tid not in rows:
            rows[tid] = {k: seen.get(k, "") for k in FIELDS}
            restored += 1
            continue
        row = rows[tid]
        for f in FILL_FIELDS:
            if not row.get(f) and seen.get(f):
                row[f] = seen[f]
    for row in rows.values():
        recompute_delay(row)

    after = list(rows.values())
    print(f"[backfill] rows {len(before)} -> {len(after)} ({restored} restored)")
    for f in FIELDS:
        b, a = before_fill[f], _filled(after, f)
        print(f"  {f:12s} {b:6d} -> {a:6d}  ({a / len(after):.0%})")
        if f in FILL_FIELDS and a < b:
            sys.exit(f"[backfill] '{f}' lost values - not writing.")

    ordered = sorted(after, key=lambda r: (r.get("check_time", ""), r.get("planned_arr", "")))
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ordered)
    os.replace(tmp, path)


if __name__ == "__main__":
    main()

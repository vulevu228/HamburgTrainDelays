"""
Summarise hamburg_delays.csv and refresh the README chart.

Reads the migrated schema (check_time, train_id, category, line, train_no,
planned_arr, actual_arr, delay_min, cancelled, platform, origin, source).
"""

import os

import matplotlib.ticker as mticker
import matplotlib.pyplot as plt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "hamburg_delays.csv")
CHART = os.path.join(ROOT, "images", "chart_preview.png")

df = pd.read_csv(CSV)
df["planned_arr"] = pd.to_datetime(df["planned_arr"], errors="coerce")
df["actual_arr"] = pd.to_datetime(df["actual_arr"], errors="coerce")

rated = df[df["cancelled"] == 0].dropna(subset=["planned_arr", "delay_min"]).copy()
rated["delay_min"] = rated["delay_min"].clip(lower=0)

print("--- HAMBURG HBF DELAY SUMMARY ---")
print(f"Rows in dataset      : {len(df)}")
print(f"Trains with a delay  : {len(rated)}")
print(f"Cancellations        : {int(df['cancelled'].sum())}")
print(f"Average delay        : {rated['delay_min'].mean():.1f} min")
print(f"On-time (<6 min)     : {(rated['delay_min'] < 6).mean() * 100:.0f}%")
print(f"Longest delay        : {rated['delay_min'].max():.0f} min")
if rated["line"].notna().any():
    worst = (rated.groupby("line")["delay_min"].mean().sort_values(ascending=False).head(5))
    print("Worst lines (avg min):")
    for line, val in worst.items():
        print(f"  {line:<6} {val:5.1f}")

hourly = rated.groupby(rated["planned_arr"].dt.hour)["delay_min"].mean().reindex(range(24))

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(10, 5.5))
colors = ["#f97316" if v and v >= 5 else "#3b82f6" for v in hourly.fillna(0)]
ax.bar(hourly.index, hourly.values, color=colors, width=0.7, zorder=3)
ax.set_title("Average Train Delay by Hour · Hamburg Hbf", fontsize=15, fontweight="bold", pad=14)
ax.set_xlabel("Hour of Day (24h)", fontsize=11)
ax.set_ylabel("Average Delay (minutes)", fontsize=11)
ax.set_xticks(range(0, 24, 2))
ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
ax.grid(axis="x", visible=False)
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.99, 0.01, "Source: Deutsche Bahn Timetables API (live)", ha="right", fontsize=8, color="gray")
plt.tight_layout()
plt.savefig(CHART, dpi=150)
print(f"\nChart saved to {os.path.relpath(CHART, ROOT)}")

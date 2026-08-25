import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# 1. Load the data
df = pd.read_csv('hamburg_delays.csv')

# 2. Convert time columns (API format: YYMMDDHHMM). Some records only carry
# an actual arrival with no planned time ("zombie" records) - drop those,
# they can't produce a delay figure.
df['planned_arr'] = pd.to_datetime(df['planned_arr'], format='%y%m%d%H%M', errors='coerce')
df['actual_arr'] = pd.to_datetime(df['actual_arr'], format='%y%m%d%H%M', errors='coerce')
df = df.dropna(subset=['planned_arr', 'actual_arr'])

# 3. Delay in minutes, clipped at 0 (early arrivals aren't "negative delay")
df['delay_min'] = (df['actual_arr'] - df['planned_arr']).dt.total_seconds() / 60
df['delay_min'] = df['delay_min'].clip(lower=0)

# 4. Filter stale ("zombie") records: planned arrival more than 12h from
# when the check ran means the API is echoing a train that never cleared.
df['check_time'] = pd.to_datetime(df['check_time'])
df = df[(df['check_time'] - df['planned_arr']).abs() < pd.Timedelta(hours=12)]

print("--- HAMBURG HBF DELAY SUMMARY ---")
print(f"Trains tracked: {len(df)}")
print(f"Average delay: {df['delay_min'].mean():.1f} min")
print(f"Longest delay: {df['delay_min'].max():.1f} min")

# 5. Average delay by hour of day - the headline chart for the README
hourly_avg = df.groupby(df['planned_arr'].dt.hour)['delay_min'].mean().reindex(range(24))

plt.style.use('seaborn-v0_8-whitegrid')
fig, ax = plt.subplots(figsize=(10, 5.5))

bar_colors = ['#f97316' if v and v >= 5 else '#3b82f6' for v in hourly_avg.fillna(0)]
ax.bar(hourly_avg.index, hourly_avg.values, color=bar_colors, width=0.7, zorder=3)

ax.set_title('Average Train Delay by Hour · Hamburg Hbf', fontsize=15, fontweight='bold', pad=14)
ax.set_xlabel('Hour of Day (24h)', fontsize=11)
ax.set_ylabel('Average Delay (minutes)', fontsize=11)
ax.set_xticks(range(0, 24, 2))
ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
ax.grid(axis='x', visible=False)
ax.spines[['top', 'right']].set_visible(False)
fig.text(0.99, 0.01, 'Source: Deutsche Bahn Timetables API (live)', ha='right', fontsize=8, color='gray')

plt.tight_layout()
plt.savefig('images/chart_preview.png', dpi=150)
print("Chart saved to images/chart_preview.png")

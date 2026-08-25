import pandas as pd
import matplotlib.pyplot as plt

# 1. Load the data
df = pd.read_csv('hamburg_delays.csv')

# 2. Convert time columns to actual "Time" objects
# The API format is YYMMDDHHMM
df['planned_arr'] = pd.to_datetime(df['planned_arr'], format='%y%m%d%H%M')
df['actual_arr'] = pd.to_datetime(df['actual_arr'], format='%y%m%d%H%M')

# 3. Calculate delay in minutes
df['delay_min'] = (df['actual_arr'] - df['planned_arr']).dt.total_seconds() / 60

# 4. Filter out 'negative' delays (trains that arrived early are usually just 0)
df['delay_min'] = df['delay_min'].apply(lambda x: x if x > 0 else 0)

# 5. Create a Summary
print("--- HAMBURG DELAY SUMMARY ---")
print(f"Total Trains Tracked: {len(df)}")
print(f"Average Delay: {df['delay_min'].mean():.2f} minutes")
print(f"Longest Delay: {df['delay_min'].max():.2f} minutes")

# 6. Create a quick chart
plt.figure(figsize=(10, 6))
df['delay_min'].hist(bins=20, color='skyblue', edgecolor='black')
plt.title('Distribution of Train Delays at Hamburg Hbf')
plt.xlabel('Minutes Late')
plt.ylabel('Number of Trains')
plt.grid(axis='y', alpha=0.75)

# Save the chart so you can upload it to GitHub!
plt.savefig('delay_analysis.png')
print("✅ Chart saved as delay_analysis.png")

# Add this to your existing script
df['hour'] = df['planned_arr'].dt.hour

# Calculate average delay per hour
hourly_avg = df.groupby('hour')['delay_min'].mean()

# Plot it
plt.figure(figsize=(10, 6))
hourly_avg.plot(kind='line', marker='o', color='red')
plt.title('Average Delay by Hour at Hamburg Hbf')
plt.xlabel('Hour of Day (24h)')
plt.ylabel('Average Delay (Minutes)')
plt.grid(True)
plt.savefig('hourly_trend.png')
print("✅ Hourly trend saved as hourly_trend.png")
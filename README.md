# 🚂 DB-Delay-Tracker: Hamburg Hbf Analysis

> **Real-time data pipeline for monitoring and visualizing train reliability at Hamburg Hauptbahnhof.**

## 📊 Project Overview
This project polls the live Deutsche Bahn Timetables API every 15 minutes, logging arrival data for Hamburg Hbf into a growing local dataset. A Python analysis pass turns that raw feed into delay statistics and tracks how conditions shift across the day — while filtering out the API's quirks (see below).

## 📈 Results
![Average delay by hour at Hamburg Hbf](images/chart_preview.png)
*Average delay by hour, generated straight from the live dataset by `scripts/analyze_delays.py`.*

---

## 🛠️ The Tech Stack
* **Python + `requests`:** Polls the DB Timetables API on a schedule and logs raw XML to CSV.
* **pandas:** Parses the API's timestamp format, computes delays, and filters bad records.
* **matplotlib:** Renders the hourly delay chart above.

---

## 🔍 Engineering Challenges & Solutions

### 1. The "Zombie Train" Problem (Data Latency)
* **Challenge:** The API occasionally reports "stale" records — trains from 12+ hours ago that never cleared the system.
* **Solution:** A **stale-record filter** compares each record's `check_time` against its `planned_arr`; anything more than 12 hours apart is dropped before it can skew the averages.

### 2. Integer-to-Datetime Time Transformation
* **Challenge:** The API returns timestamps as an integer (`YYMMDDHHMM`). Naive subtraction breaks at hour/day boundaries (e.g. `1459` to `1505` looks like a 46-unit jump instead of 6 minutes), and some records omit `planned_arr` entirely.
* **Solution:** `pandas.to_datetime(..., format='%y%m%d%H%M', errors='coerce')` parses the field directly into real datetimes (so subtraction just works), and rows that fail to parse — missing planned times — are dropped rather than crashing the pipeline.

---

## ▶️ Usage
```bash
# 1. Add DB_CLIENT_ID / DB_API_KEY to a local .env (see .gitignore — never committed)
# 2. Start the collector (polls every 15 min, appends to hamburg_delays.csv)
python scripts/hamburg_collector.py

# 3. Generate/refresh the chart from whatever data has been collected so far
python scripts/analyze_delays.py
```

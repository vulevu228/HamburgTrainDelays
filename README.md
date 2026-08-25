# 🚂 DB-Delay-Tracker: Hamburg Hbf Analysis

> **Real-time data pipeline for monitoring and visualizing train reliability at Hamburg Hauptbahnhof.**

## 📊 Project Overview
This project captures and processes live transit data from the Deutsche Bahn API. By analyzing a dataset of **18,000+ records**, the system identifies peak delay windows and tracks "delay evolution"—the process of how a train's delay status changes as it approaches the station.

## 📈 Final Results
![Hamburg Delay Trends](images/chart_preview.png)
*Note: This chart shows average hourly delays after filtering for API artifacts.*

---

## 🛠️ The Tech Stack
* **Python:** Backend data collection and CSV logging.
* **Excel & Pivot Tables:** Data transformation, cleaning, and time-series visualization.
* **Data Engineering:** Custom logic for handling API latency and non-standard timestamps.

---

## 🔍 Engineering Challenges & Solutions

### 1. The "Zombie Train" Problem (Data Latency)
* **Challenge:** The API occasionally reports "stale" records—trains from 12+ hours ago that never cleared the system.
* **Solution:** Implemented a **Stale-Record Filter**. By comparing the script execution time (`check_time`) against the scheduled arrival (`planned_arr`), I flagged records older than 2 hours as "Zombies" to ensure late-night metrics remained accurate.

### 2. Integer-to-Minute Time Transformation
* **Challenge:** The API provides time as an integer (`YYMMDDHHMM`). Standard subtraction fails at hour boundaries (e.g., `1459` to `1505` looks like a 46-unit jump rather than 6 minutes).
* **Solution:** Developed a robust Excel formula to convert integers into "Total Minutes from Midnight" to allow for accurate linear subtraction:
  ```excel
  =(INT(MOD(Actual,10000)/100)*60 + MOD(Actual,100)) - (INT(MOD(Planned,10000)/100)*60 + MOD(Planned,100))
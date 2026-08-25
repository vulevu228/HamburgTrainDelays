import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
import time
import os
from dotenv import load_dotenv

# 1. LOAD SECRETS
load_dotenv() 
ID = os.getenv("DB_CLIENT_ID")
KEY = os.getenv("DB_API_KEY")
HAMBURG_HBF = "8002549"

# 2. CHECK CONNECTION
if ID and KEY:
    print("✅ Keys loaded successfully from .env file!")
else:
    print("❌ Keys not found. Check your .env file formatting.")
    exit() # Stop the script if keys are missing

def collect_hamburg_data():
    url = f"https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1/fchg/{HAMBURG_HBF}"
    headers = {'DB-Client-Id': ID, 'DB-Api-Key': KEY, 'accept': 'application/xml'}
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 401:
            print("❌ Error 401: Unauthorized. Check your API subscription.")
            return

        root = ET.fromstring(response.content)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        delays = []

        for s in root.findall('s'):
            ar = s.find('ar')
            if ar is not None:
                planned = ar.get('pt')
                actual = ar.get('ct')
                
                if actual:
                    delays.append({
                        "check_time": timestamp,
                        "train_id": s.get('id'),
                        "planned_arr": planned,
                        "actual_arr": actual,
                        "status": ar.get('l') 
                    })

        if delays:
            df = pd.DataFrame(delays)
            # Ensure the file is saved in the same directory
            file_exists = os.path.isfile('hamburg_delays.csv')
            df.to_csv('hamburg_delays.csv', mode='a', index=False, header=not file_exists)
            print(f"[{timestamp}] Saved {len(delays)} updates for Hamburg.")
        else:
            print(f"[{timestamp}] No delays reported right now.")

    except Exception as e:
        print(f"Error: {e}")

# 3. START COLLECTION LOOP
print("Starting Hamburg Delay Monitor...")
while True:
    collect_hamburg_data()
    print("Waiting 15 minutes for next check (Keep this window open)...")
    time.sleep(900)
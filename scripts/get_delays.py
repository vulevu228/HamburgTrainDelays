import requests
import xml.etree.ElementTree as ET
import pandas as pd

ID = "YOUR_CLIENT_ID"
KEY = "YOUR_API_KEY"
EVA_ID = "8011160" # Replace with the ID you found in Phase 1

url = f"https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1/fchg/{EVA_ID}"
headers = {'DB-Client-Id': ID, 'DB-Api-Key': KEY, 'accept': 'application/xml'}

response = requests.get(url, headers=headers)
root = ET.fromstring(response.content)

data = []
for s in root.findall('s'):
    train_type = ""
    ar = s.find('ar') # Arrival info
    if ar is not None:
        planned_arrival = ar.get('pt')
        actual_arrival = ar.get('ct')
        
        # Only record if there is a difference (a delay)
        if actual_arrival and planned_arrival != actual_arrival:
            data.append({
                "Train_ID": s.get('id'),
                "Planned": planned_arrival,
                "Actual": actual_arrival
            })

df = pd.DataFrame(data)
print("--- Current Delays at Station ---")
print(df)
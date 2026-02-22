import garth
import json
import os
from garminconnect import Garmin

# 1. Setup paths
token_path = os.path.expanduser("~/.garth")
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "garmin_fields_explorer.json")

def explore_data():
    try:
        # 2. Resume session
        print(f"Connecting to Garmin via tokens in {token_path}...")
        garth.resume(token_path)
        client = Garmin()
        client.garth = garth.client
        
        # 3. Fetch recent activities (limit to 3 to see different types)
        print("Fetching your 3 most recent activities...")
        activities = client.get_activities(0, 3)
        
        if not activities:
            print("No activities found in your account.")
            return

        # 4. Save to Desktop
        with open(desktop_path, 'w', encoding='utf-8') as f:
            json.dump(activities, f, indent=4)
        
        print("-" * 30)
        print(f"✅ SUCCESS!")
        print(f"File saved to: {desktop_path}")
        print("Open this file in VS Code or Notepad++ to see every available key.")
        print("-" * 30)

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    explore_data()
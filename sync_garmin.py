import os
import json
from garminconnect import Garmin
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime, timedelta
import garth

# 1. Define the token path
token_path = os.path.expanduser("~/.garth")

try:
    # 1. Load the tokens into the garth client
    garth.resume(token_path)
    print("✅ Garth session resumed.")
    
    # 2. Initialize Garmin without credentials
    # This forces the library to use the already-resumed garth session
    garmin_client = Garmin()
    garmin_client.garth = garth.client
    garmin_client.display_name = garth.client.username
    
    # 3. Test the connection
    print(f"✅ Logged in as: {garmin_client.display_name}")

except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1) # Stop the script if login fails

# Load environment variables from .env file if it exists (for local testing)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")
        pass

def format_duration(seconds):
    """Convert seconds to minutes (rounded to 2 decimals)"""
    return round(seconds / 60, 2) if seconds else 0

def format_pace(distance_meters, duration_seconds):
    """Calculate pace in min/km"""
    if not distance_meters or not duration_seconds:
        return 0
    distance_km = distance_meters / 1000
    pace_seconds = duration_seconds / distance_km
    return round(pace_seconds / 60, 2)  # Convert to min/km

def main():
    print("Starting Garmin running activities sync...")
    
    google_creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheet_id = os.environ.get('SHEET_ID')  # Add sheet ID from environment
    
    # For local testing: try to load from credentials.json file
    if not google_creds_json and os.path.exists('credentials.json'):
        print("Loading Google credentials from credentials.json...")
        with open('credentials.json', 'r') as f:
            google_creds_json = f.read()
    
    if not all([google_creds_json, sheet_id]):
        print("❌ Missing required environment variables")
        print(f"   GOOGLE_CREDENTIALS: {'✓' if google_creds_json else '✗'}")
        print(f"   SHEET_ID: {'✓' if sheet_id else '✗'}")
        return
    
    # Get recent activities (last 7 days)
    print("Fetching recent activities...")
    try:
        activities = garmin_client.get_activities(0, 20)  # Get last 20 activities
        print(f"Found {len(activities)} total activities")
    except Exception as e:
        print(f"❌ Failed to fetch activities: {e}")
        return
    
    # Filter for running activities only
    # running_activities = [
    #    activity for activity in activities 
    #    if activity.get('activityType', {}).get('typeKey', '').lower() in ['running', 'treadmill_running', 'trail_running']
    # ]
    
    # print(f"Found {len(running_activities)} running activities")
    
    # if not running_activities:
    #    print("No running activities found in recent data")
    #    return
    
    # Connect to Google Sheets
    print("Connecting to Google Sheets...")
    try:
        creds_dict = json.loads(google_creds_json)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        client = gspread.authorize(creds)
        sheet = client.open("Garmin Data").sheet1
        print("✅ Connected to Google Sheets")
    except Exception as e:
        print(f"❌ Failed to connect to Google Sheets: {e}")
        return
    
    # Get existing dates to avoid duplicates
    try:
        existing_data = sheet.get_all_values()
        existing_dates = set()
        
        # Define headers matching the row structure
        headers = ['Date', 'Activity Name', 'Distance (km)', 'Duration (min)', 'Pace (min/km)', 
                   'Avg HR', 'Max HR', 'Calories', 'Avg Cadence', 'Elevation Gain (m)', 
                   'Type', 'Z1 (min)', 'Z2 (min)', 'Z3 (min)', 'Z4 (min)', 'Z5 (min)']

        if not existing_data:
            sheet.append_row(headers)
            print("✅ Created new sheet with headers")

        if len(existing_data) > 1:  # If there's data beyond headers
            for row in existing_data[1:]:  # Skip header row
                if row and row[0]:  # If date column exists
                    existing_dates.add(row[0])
        print(f"Found {len(existing_dates)} existing entries")
    except Exception as e:
        print(f"Warning: Could not check existing data: {e}")
        existing_dates = set()
    
    # Process each running activity
    new_entries = 0
    for activity in activities:
        try:
            # Filter allowed sports
            allowed_sports = [
                'running', 'treadmill_running', 'trail_running',
                'cycling', 'road_biking', 'mountain_biking', 'indoor_cycling', 'virtual_ride',
                'swimming', 'open_water_swimming', 'lap_swimming',
                'surfing'
            ]
            if activity.get('activityType', {}).get('typeKey') not in allowed_sports:
                continue

            # Parse activity date
            activity_date = activity.get('startTimeLocal', '')[:10]  # Get YYYY-MM-DD
            
            # Skip if already in sheet
            if activity_date in existing_dates:
                print(f"Skipping {activity_date} - already exists")
                continue
            
            # Extract metrics
            activity_name = activity.get('activityName', 'Run')
            distance_meters = activity.get('distance', 0)
            distance_km = round(distance_meters / 1000, 2) if distance_meters else 0
            duration_seconds = activity.get('duration', 0)
            duration_min = format_duration(duration_seconds)
            avg_pace = format_pace(distance_meters, duration_seconds)
            avg_hr = activity.get('averageHR', 0) or 0
            max_hr = activity.get('maxHR', 0) or 0
            calories = activity.get('calories', 0) or 0
            avg_cadence = activity.get('averageRunningCadenceInStepsPerMinute', 0) or 0
            elevation_gain = round(activity.get('elevationGain', 0), 1) if activity.get('elevationGain') else 0
            activity_type = activity.get('activityType', {}).get('typeKey', 'running')
            
            # 1. Fetch the detailed HR zone breakdown for the activity
            activity_id = activity['activityId']
            try:
                hr_zones = garmin_client.get_activity_hr_in_time_zones(activity_id)
            except Exception:
                hr_zones = []

            # 2. Extract seconds for each zone (0-4 in the list correspond to Zones 1-5)
            z1_sec = hr_zones[0].get('secsInZone', 0) if hr_zones and len(hr_zones) > 0 else 0
            z2_sec = hr_zones[1].get('secsInZone', 0) if hr_zones and len(hr_zones) > 1 else 0
            z3_sec = hr_zones[2].get('secsInZone', 0) if hr_zones and len(hr_zones) > 2 else 0
            z4_sec = hr_zones[3].get('secsInZone', 0) if hr_zones and len(hr_zones) > 3 else 0
            z5_sec = hr_zones[4].get('secsInZone', 0) if hr_zones and len(hr_zones) > 4 else 0

            # 3. Convert to minutes
            z1_min = round(z1_sec / 60, 2)
            z2_min = round(z2_sec / 60, 2)
            z3_min = round(z3_sec / 60, 2)
            z4_min = round(z4_sec / 60, 2)
            z5_min = round(z5_sec / 60, 2)

            # Prepare row
            row = [
                activity_date,
                activity_name,
                distance_km,
                duration_min,
                avg_pace,
                avg_hr,
                max_hr,
                calories,
                avg_cadence,
                elevation_gain,
                activity_type,
                z1_min, z2_min, z3_min, z4_min, z5_min
            ]
            
            # Append to sheet
            sheet.append_row(row)
            print(f"✅ Added: {activity_date} - {activity_name} ({distance_km} km)")
            new_entries += 1
            
        except Exception as e:
            print(f"❌ Error processing activity: {e}")
            continue
    
    if new_entries > 0:
        print(f"\n🎉 Successfully added {new_entries} new running activities!")
    else:
        print("\n✓ No new activities to add")

if __name__ == "__main__":
    main()

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
    
    # 3. Fetch the correct display name
    # We need the actual display name (handle), not the email, for some API calls
    try:
        user_profile = garmin_client.get_social_profile()
        garmin_client.display_name = user_profile['displayName']
    except Exception:
        # Fallback to environment variable if API call fails
        garmin_client.display_name = os.environ.get('GARMIN_DISPLAY_NAME', garth.client.username)

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
    print("Starting Garmin activities sync...")
    
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
    
    # Get recent activities (last 50 activities to ensure no gaps)
    print("Fetching recent activities...")
    try:
        activities = garmin_client.get_activities(0, 50)
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
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Open the spreadsheet
        spreadsheet = client.open_by_key(sheet_id)
        sheet = spreadsheet.sheet1
        
        # Try to open "Daily Metrics" tab, create if missing
        try:
            daily_sheet = spreadsheet.worksheet("Daily Metrics")
        except gspread.WorksheetNotFound:
            daily_sheet = spreadsheet.add_worksheet(title="Daily Metrics", rows=1000, cols=20)
            
        print("✅ Connected to Google Sheets")
    except Exception as e:
        print(f"❌ Failed to connect to Google Sheets: {e}")
        return
    
    # Get existing activity IDs to avoid duplicates
    try:
        existing_data = sheet.get_all_values()
        existing_activity_ids = set()
        sheet_headers = []

        # Define default headers
        default_headers = ['Date', 'Activity Name', 'Distance (km)', 'Duration (min)', 'Pace (min/km)', 
                           'Avg HR', 'Max HR', 'Calories', 'Avg Cadence', 'Elevation Gain (m)', 
                           'Type', 'Z1 (min)', 'Z2 (min)', 'Z3 (min)', 'Z4 (min)', 'Z5 (min)',
                           'VO2 Max', 'Avg Stress', 'Max Stress', 'Start Stress', 'End Stress', 'Stress Diff',
                           'Activity ID']

        # Check if sheet is empty or has empty header row
        if not existing_data or (len(existing_data) > 0 and not any(existing_data[0])):
            print("⚠️ Sheet is empty or missing headers. Initializing...")
            sheet.clear()
            sheet.append_row(default_headers)
            print("✅ Created new sheet with headers")
            sheet_headers = default_headers
        else:
            sheet_headers = existing_data[0]
            
            # Check for missing headers and update sheet if found
            missing_headers = [h for h in default_headers if h not in sheet_headers]
            if missing_headers:
                print(f"⚠️ Found missing headers: {missing_headers}")
                sheet_headers.extend(missing_headers)
                sheet.update(range_name='A1', values=[sheet_headers])
                print("✅ Updated sheet headers")

        # Get the index of the 'Activity ID' column for de-duplication
        try:
            activity_id_col_index = sheet_headers.index('Activity ID')
        except ValueError:
            print("❌ 'Activity ID' column not found in sheet headers. Cannot de-duplicate.")
            return

        if len(existing_data) > 1:  # If there's data beyond headers
            for row in existing_data[1:]:  # Skip header row
                if len(row) > activity_id_col_index and row[activity_id_col_index]:
                    existing_activity_ids.add(row[activity_id_col_index])
        print(f"Found {len(existing_activity_ids)} existing activity IDs in the sheet.")
    except Exception as e:
        print(f"❌ Failed to read sheet data: {e}")
        return
    
    # Process each running activity
    new_entries = 0
    for activity in activities:
        try:
            # Get activity ID for de-duplication check
            activity_id = str(activity.get('activityId') or '')
            
            # Skip if already in sheet
            if activity_id in existing_activity_ids:
                continue
            
            # Parse activity date
            activity_date = activity.get('startTimeLocal', '')[:10]  # Get YYYY-MM-DD
            
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
            
            # 1. Extract seconds for each zone directly from activity data
            z1_sec = activity.get('hrTimeInZone_1') or 0
            z2_sec = activity.get('hrTimeInZone_2') or 0
            z3_sec = activity.get('hrTimeInZone_3') or 0
            z4_sec = activity.get('hrTimeInZone_4') or 0
            z5_sec = activity.get('hrTimeInZone_5') or 0

            # 3. Convert to minutes
            z1_min = round(z1_sec / 60, 2)
            z2_min = round(z2_sec / 60, 2)
            z3_min = round(z3_sec / 60, 2)
            z4_min = round(z4_sec / 60, 2)
            z5_min = round(z5_sec / 60, 2)

            # Create a "Dictionary" of your Garmin data
            activity_data = {
                "Date": activity_date,
                "Activity Name": activity_name,
                "Distance (km)": distance_km,
                "Duration (min)": duration_min,
                "Pace (min/km)": avg_pace,
                "Avg HR": avg_hr,
                "Max HR": max_hr,
                "Calories": calories,
                "Avg Cadence": avg_cadence,
                "Elevation Gain (m)": elevation_gain,
                "Type": activity_type,
                "Activity Type": activity_type,
                "Z1 (min)": z1_min,
                "Z2 (min)": z2_min,
                "Z3 (min)": z3_min,
                "Z4 (min)": z4_min,
                "Z5 (min)": z5_min,
                "Waves": activity.get('laps') if activity_type == 'surfing' else 0,
                "VO2 Max": activity.get('vO2MaxValue'),
                "Avg Stress": activity.get('avgStress'),
                "Max Stress": activity.get('maxStress'),
                "Start Stress": activity.get('startStress'),
                "End Stress": activity.get('endStress'),
                "Stress Diff": activity.get('differenceStress'),
                "Activity ID": str(activity.get('activityId') or ''),
                "Start Time GMT": activity.get('startTimeGMT')
            }

            # Build the final row based ONLY on what headers exist in the sheet
            row = [activity_data.get(header, "") for header in sheet_headers]
            
            # Append to sheet
            sheet.append_row(row)
            print(f"✅ Added: {activity_date} - {activity_name} ({distance_km} km)")
            new_entries += 1
            
        except Exception as e:
            print(f"❌ Error processing activity: {e}")
            continue
    
    if new_entries > 0:
        print(f"\n🎉 Successfully added {new_entries} new activities!")
    else:
        print("\n✓ No new activities to add")
        
    # ---------------------------------------------------------
    # SYNC DAILY METRICS (RHR, HRV, Steps, Sleep)
    # ---------------------------------------------------------
    print("\nStarting Daily Metrics sync...")
    try:
        daily_headers = ['Date', 'Resting HR', 'HRV (ms)', 'Max Stress', 'Avg Stress', 'Total Steps', 'Sleep Score', 'Sleep Duration (hr)']
        daily_data = daily_sheet.get_all_values()
        
        # Initialize headers if empty
        if not daily_data:
            daily_sheet.append_row(daily_headers)
            daily_existing_dates = set()
        else:
            # Check if headers match, update if needed (simplified for now)
            if daily_data[0] != daily_headers:
                # For now, just ensure row 1 is correct if it's a new sheet
                pass
            daily_existing_dates = set(row[0] for row in daily_data[1:] if row)

        # Sync last 14 days (excluding today to ensure data is complete)
        today = datetime.now().date()
        days_to_sync = [(today - timedelta(days=i)).isoformat() for i in range(1, 15)]
        
        new_daily_entries = 0
        for date_str in reversed(days_to_sync): # Process oldest to newest
            if date_str in daily_existing_dates:
                continue
                
            try:
                # Fetch data
                summary = garmin_client.get_user_summary(date_str)
                hrv_data = garmin_client.get_hrv_status(date_str)
                # Fetch data (Handle HRV separately as it might not exist for all devices)
                summary = None
                hrv_data = None
                
                try:
                    summary = garmin_client.get_user_summary(date_str)
                except Exception as e:
                    print(f"   ⚠️ Could not fetch summary for {date_str}: {e}")
                
                try:
                    hrv_data = garmin_client.get_hrv_status(date_str)
                except Exception:
                    # HRV data might not be available or supported
                    pass
                
                if not summary:
                    print(f"   No summary data for {date_str}")
                    continue

                # Safe extraction for sleep duration
                sleep_sec = summary.get('sleepDuration')
                sleep_hours = round(sleep_sec / 3600, 2) if sleep_sec else ''

                row_data = [
                    date_str,
                    summary.get('restingHeartRate', ''),
                    hrv_data.get('lastNightAvg', '') if hrv_data else '',
                    summary.get('maxStressLevel', ''),
                    summary.get('averageStressLevel', ''),
                    summary.get('totalSteps', ''),
                    summary.get('sleepScore', ''),
                    sleep_hours
                ]
                
                daily_sheet.append_row(row_data)
                print(f"✅ Added Daily Stats: {date_str}")
                new_daily_entries += 1
                
            except Exception as e:
                print(f"❌ Failed to fetch daily stats for {date_str}: {e}")

    except Exception as e:
        print(f"❌ Daily Metrics Sync Failed: {e}")

if __name__ == "__main__":
    main()

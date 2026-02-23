# 🏃🏽‍♂️ Garmin Data to Google Sheets Sync

Automatically syncs Garmin Connect activities and daily metrics to Google Sheets. Runs daily via GitHub Actions.

# What this project does

*   **Activities:** Fetches your last 50 activities (Running, Cycling, Swimming, etc.)
*   **Daily Metrics:** Syncs Resting HR, HRV, Stress, Steps, and Sleep data
*   **Rich Data:** Extracts detailed metrics including:
    *   Distance, Duration, Pace
    *   Heart Rate (Avg, Max) & HR Zones (1-5)
    *   VO2 Max & Stress Levels
    *   Calories, Cadence, Elevation
*   **Smart Sync:** Avoids duplicates by checking existing Activity IDs
*   **Automation:** Runs automatically every day

# Google Sheet Setup

1.  Create a new Google Sheet.
2.  The script will automatically create headers if they don't exist.
3.  It uses the first tab for **Activities** and creates/uses a "Daily Metrics" tab for daily stats.

# Setup Instructions

### 1. Google Cloud Credentials
*   Go to [Google Cloud Console](https://console.cloud.google.com/).
*   Create a project and enable **Google Sheets API** and **Google Drive API**.
*   Create a **Service Account** (IAM & Admin > Service Accounts).
*   Create a JSON Key for the service account and download it.
*   **Share your Google Sheet** with the service account email (give "Editor" access).

### 2. Generate Garmin Tokens
This project uses `garth` for authentication, which requires a one-time login to generate session tokens.

1.  Locally, install garth: `pip install garth`
2.  Run this Python snippet to login (replace email/password):
    ```python
    import garth
    garth.login("your@email.com", "your_password")
    ```
    *This creates a `~/.garth` directory with your session tokens.*
3.  Zip and encode the tokens:
    *   **Mac/Linux:**
        ```bash
        cd ~/.garth
        zip -r garmin_tokens.zip .
        base64 garmin_tokens.zip > garmin_tokens_base64.txt
        ```
        *Copy the contents of `garmin_tokens_base64.txt`.*
    *   **Windows (PowerShell):**
        Compress the contents of `%UserProfile%\.garth` to `garmin_tokens.zip`.
        ```powershell
        [Convert]::ToBase64String([IO.File]::ReadAllBytes("garmin_tokens.zip")) | Set-Clipboard
        ```

### 3. GitHub Secrets
In your repository, go to **Settings > Secrets and variables > Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `GARMIN_TOKENS_BASE64` | The base64 string generated in Step 2. |
| `GOOGLE_CREDENTIALS` | The content of your Google Service Account JSON file. |
| `SHEET_ID` | The ID from your Google Sheet URL (e.g., `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`). |

# Testing Locally

1.  Create a `.env` file:
    ```
    GOOGLE_CREDENTIALS={"type": "service_account", ...}
    SHEET_ID=your_sheet_id
    ```
2.  Ensure you have your tokens in `~/.garth` (from Step 2 above).
3.  Run: `python sync_garmin.py`

# Customization

To sync more activities, change this line in `sync_garmin.py`:
```python
activities = garmin_client.get_activities(0, 50)  # Increase this number
```

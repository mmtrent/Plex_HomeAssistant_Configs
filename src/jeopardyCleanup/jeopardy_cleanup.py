import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SONARR_BASE = "http://192.168.88.252:8989/api/v3"
SONARR_API_KEY = os.getenv("MY_API_KEY")

TRANSMISSION_URL = "https://transmission.home.lan/transmission/rpc"


if not SONARR_API_KEY:
    raise RuntimeError("Set MY_API_KEY in your environment or .env file.")

SONARR_HEADERS = {
    "X-Api-Key": SONARR_API_KEY,
    "Content-Type": "application/json"
}

headers = {
    "X-Api-Key": SONARR_API_KEY,
    "Content-Type": "application/json"
}

series_id = 80
DAYS_THRESHOLD = 30
current_date = datetime.now()

# --- Helper: Transmission RPC Handler ---
def call_transmission(method, arguments=None, session_id=None):
    """Handles Transmission RPC requests, automatically capturing the CSRF Session ID."""
    headers = {"Content-Type": "application/json"}
    if session_id:
        headers["X-Transmission-Session-Id"] = session_id

    payload = {"method": method, "arguments": arguments or {}}

    try:
        response = requests.post(TRANSMISSION_URL, json=payload, headers=headers, timeout=10, verify=False)
        
        # Handle Transmission's CSRF token protection
        if response.status_code == 409:
            new_session_id = response.headers.get("X-Transmission-Session-Id")
            if not new_session_id:
                raise RuntimeError("Received 409 but no X-Transmission-Session-Id header found.")
            # Retry immediately with the token
            return call_transmission(method, arguments, session_id=new_session_id)
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Transmission RPC Error: {e}")
        return None

print("🔄 Querying active torrents from Transmission...")
torrent_data = call_transmission("torrent-get", {"fields": ["hashString", "name"]})
transmission_hashes = []
if torrent_data and "arguments" in torrent_data:
    transmission_hashes = [t["hashString"].lower() for t in torrent_data["arguments"].get("torrents", [])]


# 1. Fetch all episodes for Jeopardy
get_url = f"{SONARR_BASE}/episode"
response = requests.get(get_url, headers=headers, timeout=10, params={"seriesId": series_id})
response.raise_for_status()
all_episodes = response.json()

history_response = requests.get(f"{SONARR_BASE}/history/series", headers=headers, timeout=30, params={"seriesId": series_id})
history_response.raise_for_status()
history_by_episode = {}
for record in history_response.json():
    history_by_episode.setdefault(record.get("episodeId"), []).append(record)

print(f"Total episodes found for series {series_id}: {len(all_episodes)}")
print(f"Scanning for episodes older than {DAYS_THRESHOLD} days...\n")

deleted_count = 0

for episode in all_episodes:
    air_date_str = episode.get("airDate")
    
    # Skip episodes that have no release/air date yet
    if not air_date_str:
        continue
        
    try:
        # Convert Sonarr's 'YYYY-MM-DD' string to a Python datetime object
        air_date = datetime.strptime(air_date_str, "%Y-%m-%d")
    except ValueError:
        continue

    # Calculate age in days
    age_in_days = (current_date - air_date).days

    # We only care about episodes older than 30 days AND that currently have a video file
    if age_in_days > DAYS_THRESHOLD and episode.get("hasFile"):
        ep_id = episode["id"]
        file_id = episode.get("episodeFileId")
        ep_num = episode["episodeNumber"]
        season_num = episode["seasonNumber"]
        title = episode.get("title", "No Title")

        print(f"Found Old Episode: S{season_num}E{ep_num} - '{title}' (Aired: {air_date_str}, {age_in_days} days old)")

        try:
            # Step A: Unmonitor the episode
            if episode.get("monitored", True):
                episode["monitored"] = False
                put_url = f"{SONARR_BASE}/episode/{ep_id}"
                put_response = requests.put(put_url, headers=headers, timeout=5, json=episode)
                put_response.raise_for_status()
                print(f"  └─ Monitored status set to False.")

            # Step B: Delete the actual file from disk
            if file_id:
                delete_url = f"{SONARR_BASE}/episodeFile/{file_id}"
                delete_response = requests.delete(delete_url, headers=headers, timeout=5)
                delete_response.raise_for_status()
                print(f"  └─ File ID {file_id} deleted successfully.")
                deleted_count += 1

                history_items = history_by_episode.get(ep_id, [])
            
            for record in history_items:
                    # 'grabbed' or 'downloadFolderImported' entries contain downloadId
                    download_id = record.get("downloadId")
                    if download_id:
                        torrent_hash = download_id.lower()
                        
                        # Match against current Transmission active list to ensure it exists
                        if torrent_hash in transmission_hashes:
                            print(f"  └─ Transmission: Found matching hash {torrent_hash}. Issuing purge...")
                            
                            # Step 6: Command Transmission to remove the torrent payload and internal data
                            remove_args = {
                                "ids": [torrent_hash],
                                "delete-local-data": True
                            }
                            remove_res = call_transmission("torrent-remove", remove_args)
                            if remove_res and remove_res.get("result") == "success":
                                print("  └─ Transmission: Successfully purged torrent data completely.")
                                deleted_count += 1
                                # Remove from localized tracking list to prevent double execution cycles
                                transmission_hashes.remove(torrent_hash)
                
        except requests.exceptions.RequestException as e:
            print(f"Error processing episode {ep_id}: {e}")

print(f"\nCleanup complete. Total video files deleted: {deleted_count}")

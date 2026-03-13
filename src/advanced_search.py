import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from telethon import TelegramClient

# Add src to path if needed to find core_downloader
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core_downloader import (
    load_download_state,
    fetch_channel,
    download_in_batches_headless
)

# Load environment variables
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "session")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 5))

if not API_ID or not API_HASH:
    print("Error: API_ID or API_HASH not found in .env file.")
    sys.exit(1)

API_ID = int(API_ID)

# Search Criteria
CHANNEL_ID = -1003462036720
KEYWORDS = ["The 50", "Season", "1080p"]
CACHE_FILE = "search_results.json"

def normalize_text(text):
    if not text: return ""
    return text.replace(".", " ").replace("_", " ").lower()

def save_search_results(channel_id, keywords, message_ids, last_scanned_id):
    data = {
        "channel_id": channel_id,
        "keywords": keywords,
        "message_ids": sorted(list(set(message_ids)), reverse=True),
        "last_scanned_id": last_scanned_id
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)
    print(f"\nSearch results (and last scanned ID {last_scanned_id}) saved to {CACHE_FILE}")

def load_cached_results():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if data.get("channel_id") == CHANNEL_ID and data.get("keywords") == KEYWORDS:
            return data
    except Exception:
        pass
    return None

async def main():
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        print(f"Connected successfully!")
        
        try:
            channel = await fetch_channel(client, CHANNEL_ID)
            print(f"Channel: {getattr(channel, 'title', CHANNEL_ID)}")
        except Exception as e:
            print(f"Error fetching channel: {e}")
            return

        matches = []
        cached_data = load_cached_results()
        last_scanned_id = 0
        
        mode = "full"
        if cached_data:
            cached_ids = cached_data.get('message_ids', [])
            cached_last_scanned = cached_data.get('last_scanned_id', 0)
            
            print(f"\nFound {len(cached_ids)} cached matches (Last scan stopped at ID {cached_last_scanned}).")
            print("Options:")
            print(" [1] Use Cached results only (Instant)")
            print(" [2] Scan for NEW episodes only (Incremental)")
            print(" [3] Full Rescan (Checks entire history)")
            
            choice = input("\nSelect an option (1-3): ").strip()
            if choice == "1":
                mode = "hide_scan"
                ids_to_hydrate = cached_ids
                last_scanned_id = cached_last_scanned
            elif choice == "2":
                mode = "incremental"
                ids_to_hydrate = cached_ids
                last_scanned_id = cached_last_scanned
            else:
                print("Proceeding with full rescan...")
                mode = "full"
                ids_to_hydrate = []
                last_scanned_id = 0

            if ids_to_hydrate:
                print(f"Hydrating {len(ids_to_hydrate)} cached messages...")
                msgs = await client.get_messages(channel, ids=ids_to_hydrate)
                matches = [m for m in msgs if m]

        new_matches = []
        if mode != "hide_scan":
            print(f"\nScanning for: {', '.join(KEYWORDS)}...")
            if mode == "incremental":
                print(f"Stopping scan once ID {last_scanned_id} is reached.")
            
            message_count = 0
            max_id_seen = 0
            
            async for message in client.iter_messages(channel):
                message_count += 1
                if message_count == 1:
                    max_id_seen = message.id
                
                # Check if we've reached the previous scan point
                if mode == "incremental" and message.id <= last_scanned_id:
                    print(f"\nReached previously scanned message ID {last_scanned_id}. Stopping scan.")
                    break

                if message_count % 500 == 0:
                    await asyncio.sleep(0.5) 
                    sys.stdout.write(f"\rScanned {message_count} messages...")
                    sys.stdout.flush()

                if not message.video:
                    continue
                
                text = normalize_text(message.text)
                if all(normalize_text(k) in text for k in KEYWORDS):
                    file_name = "Unknown"
                    if message.file and message.file.name:
                        file_name = message.file.name
                    elif message.video:
                        for attr in message.video.attributes:
                            if hasattr(attr, 'file_name'):
                                file_name = attr.file_name
                                break
                    print(f"\n [NEW MATCH] ID: {message.id} | Name: {file_name}")
                    new_matches.append(message)
            
            # Merge and update cache
            all_matches_dict = {m.id: m for m in (matches + new_matches)}
            matches = sorted(all_matches_dict.values(), key=lambda x: x.id, reverse=True)
            
            current_max_scanned = max(max_id_seen, last_scanned_id)
            save_search_results(CHANNEL_ID, KEYWORDS, [m.id for m in matches], current_max_scanned)

        if not matches:
            print(f"\nNo videos found matching criteria.")
            return

        print(f"\nTotal matches ready: {len(matches)}")
        confirm = input("\nDo you want to download these videos? (y/n): ").strip().lower()
        if confirm != 'y':
            return

        safe_title = "".join(x for x in getattr(channel, 'title', str(CHANNEL_ID)) if x.isalnum() or x in " -_").strip()
        folder_name = os.path.join("downloads", f"{safe_title}_advanced_search")
        os.makedirs(folder_name, exist_ok=True)
        download_state = load_download_state()

        print(f"\nStarting download to: {folder_name} (Concurrency={BATCH_SIZE})")

        def progress_callback(msg_id, current, total, speed_str=""):
            percentage = (current / total * 100) if total else 0
            sys.stdout.write(f"\rDownload {msg_id}: {percentage:.1f}% | {speed_str}          ")
            sys.stdout.flush()

        def completion_callback(msg_id, paused=False, filepath=None):
            if paused:
                print(f"\nDownload {msg_id} [PAUSED]")
            else:
                print(f"\nDownload {msg_id} [COMPLETE] -> {os.path.basename(filepath) if filepath else 'Done'}")

        await download_in_batches_headless(
            matches,
            folder_name,
            batch_size=BATCH_SIZE,
            downloaded_state=download_state,
            progress_cb=progress_callback,
            complete_cb=completion_callback
        )
        print("\nAll tasks processed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        # Ignore Windows/ProactorEventLoop specific shutdown errors if they are just about closing sockets
        if "WinError 10022" in str(e) or "connection lost" in str(e).lower():
            sys.exit(0)
        print(f"\nAn error occurred: {e}")

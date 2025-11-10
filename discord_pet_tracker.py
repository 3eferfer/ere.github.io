import discord
import re
import os
import json
import asyncio
from flask import Flask, jsonify
from threading import Thread, Lock
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Configuration
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "1409208367188283556"))
PERSISTENCE_FILE = "pets_data.json"

# Flask app for API
app = Flask(__name__)

# Thread-safe storage
pet_servers: List[Dict] = []
pets_lock = Lock()

def load_pets_from_file():
    """Load previously stored pets from JSON file"""
    global pet_servers
    try:
        if os.path.exists(PERSISTENCE_FILE):
            with open(PERSISTENCE_FILE, 'r') as f:
                data = json.load(f)
                with pets_lock:
                    pet_servers = data
                print(f"Loaded {len(pet_servers)} pets from storage")
    except Exception as e:
        print(f"Error loading pets from file: {e}")
        pet_servers = []

def save_pets_to_file():
    """Save current pets to JSON file"""
    try:
        with pets_lock:
            with open(PERSISTENCE_FILE, 'w') as f:
                json.dump(pet_servers, f, indent=2)
    except Exception as e:
        print(f"Error saving pets to file: {e}")

def parse_pet_embed(embed: discord.Embed, message: discord.Message) -> Optional[Dict]:
    """
    Comprehensively parse pet embed to extract all information.
    Returns a dictionary with all pet data or None if parsing fails.
    """
    try:
        # Initialize all fields
        pet_data = {
            "name": None,
            "mutation": None,
            "dps": None,
            "money_per_sec": None,
            "tier": None,
            "generation": None,
            "traits": None,
            "jobId": None,
            "placeId": None,
            "players": None,
            "join_link": None,
            "teleport_script": None,
            "emoji": None,
            "found_at": None,  # When Discord message was posted
            "processed_at": None,  # When bot processed it
            "message_id": None,
            "raw_fields": []  # Store all fields for debugging
        }

        # Get Discord message timestamp (when it was actually posted)
        if message.created_at:
            pet_data["found_at"] = message.created_at.timestamp()
        
        # When we processed it
        pet_data["processed_at"] = datetime.now(timezone.utc).timestamp()
        pet_data["message_id"] = str(message.id)

        # Parse embed title if present
        if embed.title:
            pet_data["embed_title"] = embed.title

        # Parse embed description if present
        if embed.description:
            pet_data["embed_description"] = embed.description

        # Parse all fields from embed
        for field in embed.fields:
            field_name = field.name.lower().strip() if field.name else ""
            field_value = field.value.strip() if field.value else ""
            
            # Store raw field for debugging
            pet_data["raw_fields"].append({
                "name": field.name,
                "value": field.value,
                "inline": field.inline
            })

            # Extract name
            if "name" in field_name and "display" not in field_name:
                # Extract emoji if present
                emoji_match = re.search(r'([^\w\s]+)\s*(.+)', field_value)
                if emoji_match:
                    pet_data["emoji"] = emoji_match.group(1).strip()
                    pet_data["name"] = emoji_match.group(2).strip()
                else:
                    pet_data["name"] = field_value
            
            # Extract mutation
            elif "mutation" in field_name:
                pet_data["mutation"] = field_value
            
            # Extract generation ($ per second)
            elif "generation" in field_name or "per sec" in field_name.lower() or "per second" in field_name.lower():
                pet_data["generation"] = field_value
                pet_data["money_per_sec"] = field_value
            
            # Extract DPS/Money
            elif "money" in field_name or "dps" in field_name:
                pet_data["dps"] = field_value
            
            # Extract tier
            elif "tier" in field_name:
                pet_data["tier"] = field_value
            
            # Extract traits
            elif "trait" in field_name:
                pet_data["traits"] = field_value
            
            # Extract players
            elif "player" in field_name:
                pet_data["players"] = field_value
            
            # Extract Job ID
            elif "jobid" in field_name.replace(" ", "").lower() or "job id" in field_name.lower():
                # Extract from code block if present
                code_match = re.search(r'```(?:lua)?\s*([^\n`]+)', field_value)
                if code_match:
                    pet_data["jobId"] = code_match.group(1).strip()
                else:
                    pet_data["jobId"] = field_value
            
            # Extract Join Script
            elif "join script" in field_name.lower() or "teleport" in field_name.lower():
                pet_data["teleport_script"] = field_value
                # Try to extract placeId and jobId from script
                # Pattern: TeleportToPlaceInstance(placeId, "jobId", ...)
                m = re.search(r'TeleportToPlaceInstance\((\d+),\s*["\']([^"\']+)["\']', field_value)
                if m:
                    pet_data["placeId"] = m.group(1)
                    # Use this jobId if we don't have one yet
                    if not pet_data["jobId"]:
                        pet_data["jobId"] = m.group(2)
            
            # Extract Join Link
            elif "join" in field_name and "link" in field_name.lower():
                # Extract URL from markdown link [text](url)
                link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', field_value)
                if link_match:
                    pet_data["join_link"] = link_match.group(2)
                elif field_value.startswith("http"):
                    pet_data["join_link"] = field_value

        # Validation: Must have at least name and jobId to be valid
        if pet_data["name"] and pet_data["jobId"]:
            return pet_data
        
        # If we don't have required fields, log what we got
        print(f"Missing required fields. Name: {pet_data['name']}, JobId: {pet_data['jobId']}")
        print(f"Available fields: {[f['name'] for f in pet_data['raw_fields']]}")
        
        return None

    except Exception as e:
        print(f"Error parsing embed: {e}")
        import traceback
        traceback.print_exc()
        return None

def is_duplicate_pet(new_pet: Dict) -> bool:
    """
    Check if this pet is already in our list.
    Uses jobId + name combination for deduplication.
    This ensures multiple embeds in the same message are tracked separately.
    """
    with pets_lock:
        for existing_pet in pet_servers:
            # Check by jobId + name combination (unique identifier for a pet)
            if (existing_pet.get("jobId") == new_pet.get("jobId") and 
                existing_pet.get("name") == new_pet.get("name")):
                return True
    
    return False

def add_pet(pet: Dict):
    """Add a new pet to the list with thread safety"""
    with pets_lock:
        pet_servers.append(pet)
        
        # Keep only last 100 pets to prevent memory issues
        if len(pet_servers) > 100:
            pet_servers.pop(0)
    
    # Save to file for persistence
    save_pets_to_file()
    
    print(f"✅ Added pet: {pet['name']} | JobId: {pet['jobId']} | Found at: {datetime.fromtimestamp(pet['found_at'], tz=timezone.utc)}")

class PetClient(discord.Client):
    async def on_ready(self):
        print(f'🤖 Bot logged in as {self.user}')
        print(f'📺 Monitoring channel ID: {CHANNEL_ID}')
        print(f'✅ Ready to track pets!')

    async def on_message(self, message: discord.Message):
        """Handle incoming messages and parse pet embeds"""
        try:
            # Only process messages from the configured channel
            if message.channel.id != CHANNEL_ID:
                return

            # Check if message has embeds
            if not message.embeds:
                return

            # Process each embed in the message
            for embed in message.embeds:
                pet = parse_pet_embed(embed, message)
                
                if pet:
                    # Check for duplicates
                    if not is_duplicate_pet(pet):
                        add_pet(pet)
                    else:
                        print(f"⚠️  Skipped duplicate: {pet['name']} (JobId: {pet['jobId']})")
                else:
                    # Log when we can't parse an embed (might be a different type of embed)
                    if embed.fields:
                        print(f"ℹ️  Could not parse embed with {len(embed.fields)} fields (might not be a pet)")

        except Exception as e:
            # Never crash on error - just log it and continue
            print(f"❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()

# Flask API endpoints
@app.route('/recent-pets')
def recent_pets():
    """
    Get recent pets found in the last 15 minutes.
    Returns JSON array of pet data.
    """
    import time
    now = time.time()
    
    # Filter to pets found in last 15 minutes (900 seconds)
    with pets_lock:
        filtered = [p for p in pet_servers if now - p.get("found_at", 0) < 900]
    
    return jsonify(filtered)

@app.route('/all-pets')
def all_pets():
    """
    Get all tracked pets (up to last 100).
    Returns JSON array of pet data.
    """
    with pets_lock:
        return jsonify(pet_servers)

@app.route('/stats')
def stats():
    """Get statistics about tracked pets"""
    with pets_lock:
        return jsonify({
            "total_pets_tracked": len(pet_servers),
            "monitoring_channel": CHANNEL_ID,
            "persistence_file": PERSISTENCE_FILE
        })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "bot_ready": True})

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def main():
    """Main entry point"""
    # Check for Discord token
    if not DISCORD_TOKEN:
        print("❌ ERROR: DISCORD_TOKEN environment variable is not set!")
        print("Please set your Discord bot token in the Secrets.")
        return

    # Load previously saved pets
    load_pets_from_file()

    # Start Flask server in background thread
    print("🌐 Starting Flask API server on port 5000...")
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start Discord bot
    print("🚀 Starting Discord bot...")
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    
    client = PetClient(intents=intents)
    
    try:
        client.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Error running bot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

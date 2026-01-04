import discord
import re
import os
import json
import asyncio
from flask import Flask, jsonify
from threading import Thread, Lock
from datetime import datetime, timezone
from typing import Dict, List, Optional

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "1409208367188283556"))
PERSISTENCE_FILE = "pets_data.json"

app = Flask(__name__)

pet_servers: List[Dict] = []
pets_lock = Lock()

def load_pets_from_file():
    global pet_servers
    try:
        if os.path.exists(PERSISTENCE_FILE):
            with open(PERSISTENCE_FILE, 'r') as f:
                data = json.load(f)
                with pets_lock:
                    pet_servers = data
    except Exception:
        pet_servers = []

def save_pets_to_file():
    try:
        with pets_lock:
            with open(PERSISTENCE_FILE, 'w') as f:
                json.dump(pet_servers, f, indent=2)
    except Exception:
        pass

def parse_pet_embed(embed: discord.Embed, message: discord.Message) -> Optional[Dict]:
    try:
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
            "found_at": None,
            "processed_at": None,
            "message_id": None,
            "raw_fields": []
        }

        if message.created_at:
            pet_data["found_at"] = message.created_at.timestamp()
        
        pet_data["processed_at"] = datetime.now(timezone.utc).timestamp()
        pet_data["message_id"] = str(message.id)

        if embed.title:
            pet_data["embed_title"] = embed.title

        if embed.description:
            pet_data["embed_description"] = embed.description

        for field in embed.fields:
            field_name = field.name.lower().strip() if field.name else ""
            field_value = field.value.strip() if field.value else ""
            
            pet_data["raw_fields"].append({
                "name": field.name,
                "value": field.value,
                "inline": field.inline
            })

            if "name" in field_name and "display" not in field_name:
                emoji_match = re.search(r'([^\w\s]+)\s*(.+)', field_value)
                if emoji_match:
                    pet_data["emoji"] = emoji_match.group(1).strip()
                    pet_data["name"] = emoji_match.group(2).strip()
                else:
                    pet_data["name"] = field_value
            elif "mutation" in field_name:
                pet_data["mutation"] = field_value
            elif "generation" in field_name or "per sec" in field_name.lower() or "per second" in field_name.lower():
                pet_data["generation"] = field_value
                pet_data["money_per_sec"] = field_value
            elif "money" in field_name or "dps" in field_name:
                pet_data["dps"] = field_value
            elif "tier" in field_name:
                pet_data["tier"] = field_value
            elif "trait" in field_name:
                pet_data["traits"] = field_value
            elif "player" in field_name:
                pet_data["players"] = field_value
            elif "jobid" in field_name.replace(" ", "").lower() or "job id" in field_name.lower() or "id pc" in field_name.lower():
                code_match = re.search(r'```(?:lua)?\s*([^\n`]+)', field_value)
                if code_match:
                    pet_data["jobId"] = code_match.group(1).strip()
                else:
                    pet_data["jobId"] = field_value
            elif "join script" in field_name.lower() or "teleport" in field_name.lower() or "script pc" in field_name.lower():
                pet_data["teleport_script"] = field_value
                m = re.search(r'TeleportToPlaceInstance\((\d+),\s*["\']([^"\']+)["\']', field_value)
                if m:
                    pet_data["placeId"] = m.group(1)
                    if not pet_data["jobId"]:
                        pet_data["jobId"] = m.group(2)
            elif "join" in field_name and "link" in field_name.lower():
                link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', field_value)
                if link_match:
                    pet_data["join_link"] = link_match.group(2)
                elif field_value.startswith("http"):
                    pet_data["join_link"] = field_value

        if pet_data["name"] and pet_data["jobId"]:
            return pet_data
        
        return None
    except Exception:
        return None

def is_duplicate_pet(new_pet: Dict) -> bool:
    with pets_lock:
        for existing_pet in pet_servers:
            if (existing_pet.get("jobId") == new_pet.get("jobId") and 
                existing_pet.get("name") == new_pet.get("name")):
                return True
    return False

def add_pet(pet: Dict):
    with pets_lock:
        pet_servers.append(pet)
        if len(pet_servers) > 100:
            pet_servers.pop(0)
    save_pets_to_file()

class PetClient(discord.Client):
    async def on_ready(self):
        print(f'Bot logged in as {self.user}')

    async def on_message(self, message: discord.Message):
        try:
            if message.channel.id != CHANNEL_ID:
                return
            if not message.embeds:
                return
            for embed in message.embeds:
                pet = parse_pet_embed(embed, message)
                if pet:
                    if not is_duplicate_pet(pet):
                        add_pet(pet)
        except Exception:
            pass

@app.route('/recent-pets')
def recent_pets():
    import time
    now = time.time()
    with pets_lock:
        filtered = [p for p in pet_servers if now - p.get("found_at", 0) < 900]
    return jsonify(filtered)

@app.route('/all-pets')
def all_pets():
    with pets_lock:
        return jsonify(pet_servers)

@app.route('/stats')
def stats():
    with pets_lock:
        return jsonify({
            "total_pets_tracked": len(pet_servers),
            "monitoring_channel": CHANNEL_ID
        })

@app.route('/health')
def health():
    return jsonify({"status": "ok", "bot_ready": True})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def main():
    if not DISCORD_TOKEN:
        return
    load_pets_from_file()
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    client = PetClient(intents=intents)
    try:
        client.run(DISCORD_TOKEN)
    except Exception:
        pass

if __name__ == "__main__":
    main()

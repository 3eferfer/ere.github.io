import discord
import re
import os
from flask import Flask, jsonify
from threading import Thread

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = 1411527848585330850  # Replace with your Discord channel ID

app = Flask(__name__)
pet_servers = []

def parse_pet_embed(embed):
    # Extract fields by name
    name = None
    mutation = None
    dps = None
    tier = None
    jobId = None
    placeId = None

    for field in embed.fields:
        if "Name" in field.name:
            name = field.value.strip()
        elif "Mutation" in field.name:
            mutation = field.value.strip()
        elif "Money" in field.name or "Per Sec" in field.name:
            dps = field.value.strip()
        elif "JOBID" in field.name:
            jobId = field.value.strip()
        elif "Join Script" in field.name:
            # Example: game:GetService("TeleportService"):TeleportToPlaceInstance(109983668079237, "09f2f0bd-b9ee-44b8-9f8f-048f835bd5ee", ...)
            m = re.search(r'TeleportToPlaceInstance\((\d+),\s*"([\w-]+)', field.value)
            if m:
                placeId = m.group(1)
                jobId2 = m.group(2)
            else:
                placeId = jobId2 = None
        # add more as needed

    if name and jobId and placeId:
        return {
            "name": name,
            "mutation": mutation or "",
            "dps": dps or "",
            "jobId": jobId,
            "placeId": placeId,
            "timestamp": discord.utils.utcnow().timestamp(),
        }
    return None

class PetClient(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def on_message(self, message):
        if message.channel.id != CHANNEL_ID:
            return

        # Check embeds
        for embed in message.embeds:
            pet = parse_pet_embed(embed)
            if pet:
                if not any(p["jobId"] == pet["jobId"] and p["name"] == pet["name"] for p in pet_servers):
                    pet_servers.append(pet)
                    print(f"Added pet: {pet['name']} {pet['jobId']}")
                if len(pet_servers) > 20:
                    pet_servers.pop(0)
                break

@app.route('/recent-pets')
def recent_pets():
    import time
    now = time.time()
    filtered = [p for p in pet_servers if now - p["timestamp"] < 900]
    return jsonify(filtered)

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    intents = discord.Intents.default()
    intents.message_content = True
    client = PetClient(intents=intents)
    client.run(DISCORD_TOKEN)

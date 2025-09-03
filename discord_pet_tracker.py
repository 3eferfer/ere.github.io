import discord
import re
import os
import time
from flask import Flask, jsonify
from threading import Thread

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = 1411527848585330850

app = Flask(__name__)
pets = []

def extract_pet_data(embed):
    pet_name = None
    mutation_type = None
    money_per_sec = None
    job_id = None
    place_id = None
    
    for field in embed.fields:
        field_name = field.name.lower()
        
        if "name" in field_name:
            pet_name = field.value.strip()
        elif "mutation" in field_name:
            mutation_type = field.value.strip()
        elif "money" in field_name or "per sec" in field_name:
            money_per_sec = field.value.strip()
        elif "jobid" in field_name:
            job_id = field.value.strip()
        elif "join script" in field_name:
            pattern = r'TeleportToPlaceInstance\((\d+),\s*"([\w-]+)'
            match = re.search(pattern, field.value)
            if match:
                place_id = match.group(1)
                job_id = match.group(2)
    
    if pet_name and job_id and place_id:
        return {
            "name": pet_name,
            "mutation": mutation_type or "None",
            "dps": money_per_sec or "Unknown",
            "jobId": job_id,
            "placeId": place_id,
            "timestamp": time.time(),
        }
    
    return None

class MyBot(discord.Client):
    async def on_ready(self):
        print(f'bot works woohoo time to finger some latinas here is the user {self.user}')
    
    async def on_message(self, message):
        if message.channel.id != CHANNEL_ID:
            return
        
        for embed in message.embeds:
            pet_data = extract_pet_data(embed)
            
            if pet_data:
                existing = any(
                    p["jobId"] == pet_data["jobId"] and p["name"] == pet_data["name"] 
                    for p in pets
                )
                
                if not existing:
                    pets.append(pet_data)
                    print(f"New pet found: {pet_data['name']} - {pet_data['jobId']}")
                
                while len(pets) > 25:
                    pets.pop(0)
                
                break

@app.route('/')
def status():
    return jsonify({
        "status": "running", 
        "total_pets": len(pets),
        "last_updated": max([p["timestamp"] for p in pets]) if pets else 0
    })

@app.route('/pets')
def get_pets():
    current_time = time.time()
    recent_pets = [p for p in pets if current_time - p["timestamp"] < 900]
    return jsonify(recent_pets)

@app.route('/recent-pets')
def recent_pets():
    return get_pets()

def start_web_server():
    app.run(host='0.0.0.0', port=8080, debug=False)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("token not found in env fix it daddy")
        exit(1)
    
    web_thread = Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    bot_intents = discord.Intents.default()
    bot_intents.message_content = True
    
    bot = MyBot(intents=bot_intents)
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as error:
        print(f"bot failed so here is the error: {error}")
        exit(1)

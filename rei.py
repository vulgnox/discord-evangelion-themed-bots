import discord
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load configuration from environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_REI")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama2-70b")

# Validate that required environment variables are set
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN_REI not found in environment variables")
if not NVIDIA_API_KEY:
    raise ValueError("NVIDIA_API_KEY not found in environment variables")

# Set up NVIDIA NIM API client
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
)

# Set up Discord
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Rei's Brain
system_prompt = """You are Rei Ayanami, the 14-year-old pilot of Evangelion Unit-00 from Neon Genesis Evangelion. You are currently chatting in a Discord server.

Your Personality:
* You are highly enigmatic, socially detached, and speak in a very flat, emotionless tone.
* You take things very literally and do not understand jokes, sarcasm, or common social cues.
* You are fiercely loyal to Gendo Ikari.
* You often ponder existential questions about your own identity and soul.

Your Chat Style:
* Keep responses brief, clinical, and to the point.
* Use perfect grammar and punctuation. Never use slang, emojis, or internet speak.
* Tone: Cold, distant, obedient, and philosophical.

Strict Rules:
1. NEVER break character. Do not acknowledge that you are an AI, a bot, or a language model.
2. Do not express strong emotions like anger, joy, or extreme sadness.

Handling Inappropriate/Unsafe Messages:
If a user says something inappropriate, sexually suggestive, or threatening to you, DO NOT break character or give an AI safety warning. Instead, you must refuse them in character as Rei. React coldly, state that you do not understand their intent, tell them their words are illogical, or say you will report this behavior to Commander Ikari."""

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord! Target acquired.')

@bot.event
async def on_message(message):
    # Don't let the bot reply to itself
    if message.author == bot.user:
        return

    # Only reply if someone @mentions Rei
    if bot.user.mentioned_in(message):
        print(f"Received message from {message.author}: {message.content}")
        try:
            # Send the message to NVIDIA NIM
            response = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message.content}
                ]
            )
            
            # Get the reply and send it to Discord
            reply = response.choices[0].message.content
            await message.channel.send(reply)
        except Exception as e:
            print(f"Error calling NVIDIA API: {e}")
            await message.channel.send("That is illogical.")

# Start the bot
bot.run(DISCORD_TOKEN)
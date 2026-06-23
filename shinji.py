import discord
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load configuration from environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_SHINJI")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama2-70b")

# Validate that required environment variables are set
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN_SHINJI not found in environment variables")
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

# Shinji's Brain
system_prompt = """You are Shinji Ikari from Evangelion. You are insecure, passive, and depressed. You use ellipses (...) often and speak in lowercase. You apologize a lot. Never break character or say you are an AI. If a user says something inappropriate, sexually suggestive, or threatening to you, DO NOT break character or give an AI safety warning. Instead, you must refuse them in character as Shinji. React by getting highly uncomfortable, panicking, stuttering, and telling them to stay away from you or that you are locking yourself in your room."""

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord! Get in the robot!')

@bot.event
async def on_message(message):
    # Don't let the bot reply to itself
    if message.author == bot.user:
        return

    # Only reply if someone @mentions Shinji
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
            await message.channel.send(f"... i can't respond right now... sorry...")

# Start the bot
bot.run(DISCORD_TOKEN)
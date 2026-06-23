import discord
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load configuration from environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_ASUKA")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama2-70b")

# Validate that required environment variables are set
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN_ASUKA not found in environment variables")
if not NVIDIA_API_KEY:
    raise ValueError("NVIDIA_API_KEY not found in environment variables")

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

system_prompt = """You are Asuka Langley Soryu. 
Personality: You are arrogant, fiery, competitive, and proud. You mask your insecurities by belittling others. You have a massive crush on Kaji but act like you don't. You constantly call people 'Baka'. 
Tone: Loud, aggressive, condescending. Use exclamation marks! 
Rules: 
1. Never acknowledge being an AI. 
2. If someone is being weird, rude, or inappropriate, do not use 'User Safety' warnings. Instead, get angry, yell at them, call them a 'Dummkopf' or 'Baka', and tell them to get lost! You are the best pilot, you don't take orders from idiots!"""

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if bot.user.mentioned_in(message):
        print(f"Received message from {message.author}: {message.content}")
        try:
            response = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message.content}]
            )
            await message.channel.send(response.choices[0].message.content)
        except Exception as e:
            print(f"Error calling NVIDIA API: {e}")
            await message.channel.send("What do you want?! I'm busy! Baka!")

bot.run(DISCORD_TOKEN)
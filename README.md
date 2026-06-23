# Evangelion Discord Bots

Three Discord bots themed after Neon Genesis Evangelion characters, powered by NVIDIA NIM AI models.

## Bots

- **Shinji** (`shinji.py`) - Insecure, passive, and depressed. Uses ellipses and lowercase.
- **Asuka** (`asuka.py`) - Arrogant, fiery, and competitive. Calls people "Baka!".
- **Rei** (`rei.py`) - Enigmatic, emotionless, and philosophical.

## Setup

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/vulgnox/discord-evangelion-themed-bots.git
   cd discord-evangelion-themed-bots
   ```

2. **Create a Python virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in:
   - `DISCORD_TOKEN_SHINJI` - Your Shinji bot's Discord token
   - `DISCORD_TOKEN_ASUKA` - Your Asuka bot's Discord token
   - `DISCORD_TOKEN_REI` - Your Rei bot's Discord token
   - `NVIDIA_API_KEY` - Your NVIDIA NIM API key from https://build.nvidia.com/
   - `NVIDIA_MODEL` - Model to use (default: `meta/llama2-70b`)

5. **Run a bot (example - Shinji):**
   ```bash
   python shinji.py
   ```

## Railway Deployment

Each bot runs as a separate Railway service. Follow these steps:

### Step 1: Create the First Railway Project

1. Go to https://railway.app/
2. Sign in with GitHub
3. Click **"New Project"** → **"Deploy from GitHub"**
4. Select the `discord-evangelion-themed-bots` repository
5. Choose a service name (e.g., "shinji-bot")
6. Click **"Deploy"**

### Step 2: Configure Environment Variables

After deployment:

1. Go to the service **Settings** → **Variables**
2. Add these environment variables:
   ```
   DISCORD_TOKEN_SHINJI=<your_shinji_bot_token>
   NVIDIA_API_KEY=<your_nvidia_nim_api_key>
   NVIDIA_MODEL=meta/llama2-70b
   ```

### Step 3: Set Start Command

1. Go to service **Settings** → **Deploy**
2. Set the **Start Command** to: `python shinji.py`
3. Save and redeploy

### Step 4: Repeat for Asuka and Rei

Create two more Railway services from the same GitHub repo with:

**Asuka Service:**
- Environment Variables:
  ```
  DISCORD_TOKEN_ASUKA=<your_asuka_bot_token>
  NVIDIA_API_KEY=<your_nvidia_nim_api_key>
  NVIDIA_MODEL=meta/llama2-70b
  ```
- Start Command: `python asuka.py`

**Rei Service:**
- Environment Variables:
  ```
  DISCORD_TOKEN_REI=<your_rei_bot_token>
  NVIDIA_API_KEY=<your_nvidia_nim_api_key>
  NVIDIA_MODEL=meta/llama2-70b
  ```
- Start Command: `python rei.py`

### Tips

- All three services can use the **same NVIDIA_API_KEY** (they share the quota)
- Each service needs its **own Discord token** and **unique DISCORD_TOKEN variable**
- Railway will auto-redeploy when you push to GitHub
- Monitor logs in Railway to check for errors

## NVIDIA NIM Models

Available free models:
- `meta/llama2-70b` (default, recommended)
- `mistralai/mistral-7b-instruct-v0.2`
- `nvidia/llama2-70b-steerlm-chat-fp8`

Get your free API key at: https://build.nvidia.com/

## Discord Bot Setup

To create Discord bot tokens:

1. Go to https://discord.com/developers/applications
2. Click "New Application" and name it (e.g., "Shinji Bot")
3. Go to **Bot** → **Add Bot**
4. Copy the token and add to your `.env` file
5. Go to **OAuth2** → **URL Generator**
   - Scopes: `bot`
   - Permissions: `Send Messages`, `Read Messages/View Channels`
6. Use the generated URL to invite the bot to your server

## Usage

Mention the bot in Discord to make it respond:

```
@Shinji i'm feeling overwhelmed
@Asuka that's so lame, baka!
@Rei calculate the third impact probability
```

## Troubleshooting

- **Bot not responding:** Check Discord permissions and make sure bot is mentioned
- **API errors:** Verify NVIDIA_API_KEY is correct and has available credits
- **Railway deployment fails:** Check logs for environment variable issues
- **Import errors:** Run `pip install -r requirements.txt` in the Railway environment

## License

MIT

## Notes

- **Keep `.env` files private** - never commit them to git
- Each bot uses its own Discord token
- All bots share the same NVIDIA NIM API key
- Characters stay in-role and don't break character for safety warnings

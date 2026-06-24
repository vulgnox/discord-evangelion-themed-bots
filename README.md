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
   - `OWNER_DISCORD_ID` - Your Discord user ID, so the pilots recognize you reliably
   - `OWNER_DISPLAY_NAME` - The name the pilots should use for you
   - `OWNER_ROLE_DESCRIPTION` - Your in-universe role (default: `NERV handler coordinating pilot communications`)

5. **Run a bot (example - Shinji):**
   ```bash
   python shinji.py
   ```

## Railway Deployment

**Simple Approach: Run all 3 bots from ONE Railway service!**

### Step 1: Create ONE Railway Project

1. Go to https://railway.app/
2. Sign in with GitHub
3. Click **"New Project"** → **"Deploy from GitHub"**
4. Select the `discord-evangelion-themed-bots` repository
5. Click **"Deploy"**

### Step 2: Configure Environment Variables

After deployment, go to **Settings** → **Variables** and add:

```
DISCORD_TOKEN_SHINJI=<your_shinji_bot_token>
DISCORD_TOKEN_ASUKA=<your_asuka_bot_token>
DISCORD_TOKEN_REI=<your_rei_bot_token>
NVIDIA_API_KEY=<your_nvidia_nim_api_key>
NVIDIA_MODEL=meta/llama2-70b
OWNER_DISCORD_ID=<your_discord_user_id>
OWNER_DISPLAY_NAME=<your_display_name>
OWNER_ROLE_DESCRIPTION=NERV handler coordinating pilot communications
```

### Step 3: Set Start Command

Go to **Settings** → **Deploy** and set the **Start Command**:
```
python run_all_bots.py
```

### Step 4: Deploy!

Save and redeploy. All 3 bots will start automatically! 🤖

---

**That's it!** All 3 bots (Shinji, Asuka, Rei) will be online simultaneously from a single Railway service.

### Notes

- The launcher script (`run_all_bots.py`) runs all 3 bots in parallel using threading
- If a bot crashes, it will automatically restart after 5 seconds
- All bots share the same NVIDIA API key and Railway resources
- Much simpler to manage than 3 separate services!

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

The bots understand mentions of each other as pilots instead of raw Discord IDs. For example, if you mention `@Rei` and `@Asuka` in the same message, Rei receives the context as a message about Asuka Langley Soryu.

They can also answer another bot when directly mentioned. Bot-to-bot replies carry an invisible chain marker and stop after 3 chained replies to prevent runaway conversations.

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

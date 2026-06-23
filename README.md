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

### 1. Create Railway Projects

- Go to https://railway.app/
- Sign in with your GitHub account
- Create a new project for each bot

### 2. Connect GitHub Repository

For each Railway project:
1. Click "Deploy from GitHub"
2. Select `discord-evangelion-themed-bots` repository
3. Choose "Confirm Deploy"

### 3. Configure Environment Variables

For each Railway project, add the appropriate environment variables:

**Shinji Project:**
```
DISCORD_TOKEN_SHINJI=<your_shinji_token>
NVIDIA_API_KEY=<your_nvidia_key>
NVIDIA_MODEL=meta/llama2-70b
```

**Asuka Project:**
```
DISCORD_TOKEN_ASUKA=<your_asuka_token>
NVIDIA_API_KEY=<your_nvidia_key>
NVIDIA_MODEL=meta/llama2-70b
```

**Rei Project:**
```
DISCORD_TOKEN_REI=<your_rei_token>
NVIDIA_API_KEY=<your_nvidia_key>
NVIDIA_MODEL=meta/llama2-70b
```

### 4. Set Start Command

For each service, go to **Settings** → **Deploy** and set the **Start Command**:

- For Shinji: `python shinji.py`
- For Asuka: `python asuka.py`
- For Rei: `python rei.py`

### 5. Deploy

Railway should auto-deploy on each GitHub push. Monitor the deployment logs to ensure everything works.

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

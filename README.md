# Evangelion Discord Bots

Three Discord bots themed after Neon Genesis Evangelion characters, powered by NVIDIA NIM AI models.

## Bots

| Bot | File | Character |
|-----|------|-----------|
| **Shinji** | `shinji.py` | Insecure, passive, and depressed. Uses ellipses and lowercase. |
| **Asuka** | `asuka.py` | Arrogant, fiery, and competitive. Calls people "Baka!". |
| **Rei** | `rei.py` | Enigmatic, emotionless, and philosophical. Has admin capabilities. |

## Project Structure

```
├── base_bot.py          # Shared bot base class
├── bot_runtime.py       # LLM API handling with retry logic
├── config.py            # Centralized configuration
├── eva_context.py       # Context management and pilot profiles
├── shinji.py            # Shinji bot implementation
├── asuka.py             # Asuka bot implementation
├── rei.py               # Rei bot implementation (with admin actions)
├── run_all_bots.py      # Launcher for running all bots
├── check.py             # NVIDIA API connection test
├── tests/               # Test suite
│   ├── __init__.py
│   ├── test_eva_context.py
│   ├── test_bot_runtime.py
│   └── test_base_bot.py
└── requirements.txt
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Discord Bot Tokens
DISCORD_TOKEN_SHINJI=<your_shinji_bot_token>
DISCORD_TOKEN_ASUKA=<your_asuka_bot_token>
DISCORD_TOKEN_REI=<your_rei_bot_token>

# NVIDIA NIM API
NVIDIA_API_KEY=<your_nvidia_nim_api_key>
NVIDIA_MODEL=meta/llama2-70b

# NERV Handler (owner)
OWNER_DISCORD_ID=<your_discord_user_id>
OWNER_DISPLAY_NAME=<your_display_name>
OWNER_ROLE_DESCRIPTION=NERV handler
```

### 3. Test API Connection

```bash
python check.py
```

### 4. Run a Single Bot

```bash
python shinji.py    # Or asuka.py or rei.py
```

### 5. Run All Bots

```bash
python run_all_bots.py
```

## Railway Deployment

### Single Service Deployment

1. Create a Railway project from your GitHub repo
2. Add environment variables in Railway dashboard:
   - All Discord tokens
   - NVIDIA API key and model
   - Owner configuration
3. Set start command: `python run_all_bots.py`

The launcher script handles:
- Staggered startup (avoids rate limits)
- Automatic restart on crash
- Graceful shutdown on SIGTERM/SIGINT

## NVIDIA NIM Models

Available free models from [build.nvidia.com](https://build.nvidia.com/):
- `meta/llama2-70b` (default, recommended for character quality)
- `mistralai/mistral-7b-instruct-v0.2`
- `nvidia/llama2-70b-steerlm-chat-fp8`

## Discord Bot Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create three applications (one per bot)
3. Under **Bot** → **Add Bot**
4. Copy tokens to your `.env` file
5. Generate invite link:
   - Scopes: `bot`
   - Permissions: `View Channels`, `Send Messages`, `Read Message History`, `Add Reactions`, `Attach Files`, `Embed Links`

## Usage

### Direct Mentions

```
@Shinji I'm feeling overwhelmed
@Asuka that's so lame, baka!
@Rei what is your purpose?
```

### Cross-Pilot Communication

When you mention multiple pilots, bots can reference each other using Discord mentions:

```
@Shinji @Asuka what do you think of @Rei?
```

Bot-to-bot communication uses invisible chain markers to prevent runaway conversations (max 3 hops).

### Rei Admin Commands (Owner Only)

Rei can execute administrative actions when asked by the owner:

| Command | Action |
|---------|--------|
| `pin the previous message` | `[ACTION: pin_message]` |
| `create a channel called X` | `[ACTION: create_channel X]` |
| `rename this channel to X` | `[ACTION: rename_channel X]` |
| `delete this channel` | `[ACTION: delete_channel]` |
| `list the channels` | `[ACTION: list_channels]` |
| `summarize the last 5 messages` | `[ACTION: summarize_messages 5]` |
| `ask Shinji if he's ready` | `[ACTION: ask_pilot are you ready?]` |
| `react to the last message` | `[ACTION: react_previous]` |
| `report server status` | `[ACTION: server_status]` |

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_eva_context.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing
```

## Architecture

### Bot Flow

1. **Message received** → `on_message` in bot file
2. **Check response eligibility** → `can_respond_to_message()` / `should_spontaneously_respond()`
3. **Build context** → `build_user_prompt()` + channel state
4. **Call LLM** → `reply_with_model()` with retry logic
5. **Format response** → `format_bot_reply()` with chain marker
6. **Send reply** → Discord message + emoji reaction

### Character Parameters

Each pilot has tuned parameters:

| Character | Temperature | Read Delay | Write Speed | Spontaneous Cooldown |
|-----------|-------------|------------|-------------|---------------------|
| Shinji | 0.85 | 0.7-2.0s | 55 wpm | 90s |
| Asuka | 1.0 | 0.2-0.8s | 90 wpm | 45s |
| Rei | 0.75 | 1.2-2.8s | 45 wpm | 120s |

### State Management

All state is in-memory (no persistence):
- Recent channel context (last 20 messages)
- Conversation history (last 6 exchanges per channel)
- Pilot mood (0-1 scale)
- User interaction counts
- Channel sentiment history
- Spontaneous response cooldowns

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check Discord permissions and bot is mentioned |
| API errors | Verify NVIDIA_API_KEY at [build.nvidia.com](https://build.nvidia.com/) |
| Rate limits | Reduce message frequency; launcher has staggered startup |
| Import errors | Run `pip install -r requirements.txt` |

## Security Notes

- **Never commit `.env`** — it contains sensitive tokens
- API keys are loaded from environment, never hardcoded
- Hard moderation blocks only genuinely harmful content
- Character-appropriate responses are allowed (e.g., Asuka's insults)

## Web interface
- Fell free to check the interactive web interface for installation
- link - https://discord-eva-bots-web.onrender.com/

## License

MIT

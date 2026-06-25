import os
import re
import asyncio
import time
import random
from collections import deque, defaultdict


MAX_BOT_CHAIN_DEPTH = 3
VISIBLE_CHAIN_MARKER_RE = re.compile(r"\s*\[eva-chain:(\d+)\]\s*$")
INVISIBLE_CHAIN_MARKER_PREFIX = "\u2063\u2063"
INVISIBLE_CHAIN_MARKER_UNIT = "\u200b"
INVISIBLE_CHAIN_MARKER_SUFFIX = "\u2063"
INVISIBLE_CHAIN_MARKER_RE = re.compile(
    rf"\s*{INVISIBLE_CHAIN_MARKER_PREFIX}"
    rf"({INVISIBLE_CHAIN_MARKER_UNIT}+)"
    rf"{INVISIBLE_CHAIN_MARKER_SUFFIX}\s*$"
)

PILOT_PROFILES = {
    "shinji": {
        "name": "Shinji Ikari",
        "unit": "Evangelion Unit-01",
        "aliases": ("shinji", "shinji ikari"),
        "summary": "Third Child, pilot of Evangelion Unit-01. Anxious, withdrawn, and desperate for approval.",
    },
    "asuka": {
        "name": "Asuka Langley Soryu",
        "unit": "Evangelion Unit-02",
        "aliases": ("asuka", "asuka langley", "asuka langley soryu", "soryu"),
        "summary": "Second Child, pilot of Evangelion Unit-02. Proud, competitive, sharp, and afraid of being replaced.",
    },
    "rei": {
        "name": "Rei Ayanami",
        "unit": "Evangelion Unit-00",
        "aliases": ("rei", "rei ayanami"),
        "summary": "First Child, pilot of Evangelion Unit-00. Quiet, distant, obedient, and difficult to read.",
    },
}

OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID", "").strip()
OWNER_DISPLAY_NAME = os.getenv("OWNER_DISPLAY_NAME", "the NERV handler").strip()
OWNER_ROLE_DESCRIPTION = os.getenv(
    "OWNER_ROLE_DESCRIPTION",
    "NERV handler coordinating pilot communications",
).strip()

KNOWN_PEOPLE_CONTEXT = f"""

## KNOWN PEOPLE AND COMMUNICATION CONTEXT
- Shinji Ikari, Asuka Langley Soryu, and Rei Ayanami are the other Eva pilots. They are real people in your world, not numbers, IDs, bots, or unknown users.
- Shinji pilots Evangelion Unit-01. Asuka pilots Evangelion Unit-02. Rei pilots Evangelion Unit-00.
- If a message mentions another pilot, understand the mention as that pilot's name and react to them in character.
- If communication context lists usable pilot mentions, use those exact handles when the handler asks you to mention, call, ping, or directly address another pilot.
- {OWNER_DISPLAY_NAME} is your {OWNER_ROLE_DESCRIPTION}. If this person speaks to you, recognize their authority as NERV communication context while still responding as yourself.
- If incoming communication context says "sender is NERV handler: yes", the sender is {OWNER_DISPLAY_NAME}. Do not treat them as a stranger.
- Messages may arrive through an unfamiliar communication channel. Do not call it Discord, the internet, a server, AI, or bot behavior in-character.
"""

# Small in-memory recent context store per-channel to enable cross-bot awareness.
# This keeps the last N mention events (actor, content, is_bot) per channel.
RECENT_CONTEXT_LIMIT = 20
_recent_channel_context = defaultdict(lambda: deque(maxlen=RECENT_CONTEXT_LIMIT))

# Track spontaneous response cooldowns per (channel_id, pilot_name) to avoid spam
_spontaneous_cooldown = {}
SPONTANEOUS_COOLDOWN_SECONDS = 60


def record_recent_message(message):
    try:
        channel_id = getattr(message.channel, "id", None) or str(getattr(message.channel, "name", "unknown"))
        author = display_name_for_user(getattr(message, "author", None))
        content = (message.content or "").strip()
        _recent_channel_context[channel_id].appendleft({"author": author, "content": content, "is_bot": getattr(message.author, "bot", False)})
    except Exception:
        pass


def get_recent_context_for_channel(channel, limit=8):
    channel_id = getattr(channel, "id", None) or str(getattr(channel, "name", "unknown"))
    entries = list(_recent_channel_context.get(channel_id, []))[:limit]
    if not entries:
        return ""
    lines = [f"- {e['author']}: {e['content']}" for e in entries]
    return "Recent channel messages (most recent first):\n" + "\n".join(lines)


def should_spontaneously_respond(message, pilot_name):
    """Check if a pilot should spontaneously join the conversation.
    
    Factors considered:
    - Pilot is mentioned or discussed
    - Channel cooldown has passed
    - Pilot mood influences engagement likelihood
    - Channel vibe affects participation
    - Sometimes pilots selectively observe without responding
    """
    import random
    
    if getattr(message.author, "bot", False):  # Don't respond to bot messages
        return False
    
    channel_id = getattr(message.channel, "id", None) or str(getattr(message.channel, "name", "unknown"))
    cooldown_key = (channel_id, pilot_name)
    
    # Check cooldown
    if cooldown_key in _spontaneous_cooldown:
        if time.time() - _spontaneous_cooldown[cooldown_key] < SPONTANEOUS_COOLDOWN_SECONDS:
            return False
    
    content = (message.content or "").lower()
    
    # Check if pilot is mentioned or discussed
    pilot_profile = PILOT_PROFILES.get(pilot_name.lower().split()[0].lower())
    if not pilot_profile:
        return False
    
    # Check for mentions and keywords associated with this pilot
    keywords = list(pilot_profile["aliases"]) + [
        pilot_profile["unit"].lower(),
        f"unit-{pilot_profile['unit'].split()[-1].lower()}",
    ]
    
    # Also add character-specific keywords
    if "shinji" in pilot_name.lower():
        keywords.extend(["misato", "gendo", "father", "deserved", "run away", "eva", "abandon"])
    elif "asuka" in pilot_name.lower():
        keywords.extend(["baka", "dummkopf", "second child", "competitive", "pity", "skilled"])
    elif "rei" in pilot_name.lower():
        keywords.extend(["first child", "quiet", "emotionless", "unit-00", "strange"])
    
    if not any(kw in content for kw in keywords):
        return False
    
    # This pilot is being discussed! But should they actually jump in?
    # Consider mood and channel vibe
    
    pilot_mood = _pilot_mood.get(pilot_name, 0.5)
    channel_vibe = get_channel_vibe(message.channel if hasattr(message, "channel") else None)
    
    # Mood affects engagement: withdrawn pilots (low mood) are less likely to respond
    mood_factor = pilot_mood
    
    # Channel vibe affects engagement
    vibe_factor = {
        "positive": 0.8,   # Pilots more likely to engage in positive atmosphere
        "negative": 0.6,   # Moderate engagement in negative vibes
        "neutral": 0.7,    # Baseline engagement
    }.get(channel_vibe, 0.7)
    
    # Sometimes pilots just observe without responding (to feel more human)
    observation_chance = 1.0 - (mood_factor * vibe_factor)  # Higher = more likely to NOT respond
    
    if random.random() < observation_chance * 0.3:  # 30% of the time they observe silently
        return False
    
    # Set cooldown
    _spontaneous_cooldown[cooldown_key] = time.time()
    return True


def get_emoji_for_pilot(pilot_name):
    """Return an appropriate emoji reaction for a pilot based on their personality."""
    if "shinji" in pilot_name.lower():
        return "😔"  # sad/resigned
    elif "asuka" in pilot_name.lower():
        return "🔥"  # fiery/aggressive
    elif "rei" in pilot_name.lower():
        return "❄️"  # cold/enigmatic
    return "👍"


# ============================================================================
# ENHANCED HUMAN-LIKE BEHAVIOR: Sentiment, Mood, Relationships, Channel Culture
# ============================================================================

# Track emotional state per pilot (affects response likelihood and tone)
_pilot_mood = {
    "Shinji Ikari": 0.5,      # neutral (scale 0-1, 0=withdrawn, 1=engaged)
    "Asuka Langley Soryu": 0.6,
    "Rei Ayanami": 0.4,
}

# Track user relationships (how often do they interact with each pilot)
_user_interaction_count = defaultdict(lambda: defaultdict(int))

# Track channel mood/vibe (affects how willing bots are to engage)
_channel_sentiment_history = defaultdict(lambda: deque(maxlen=30))


def analyze_sentiment(text):
    """Simple sentiment analysis. Returns -1 (negative), 0 (neutral), or 1 (positive)."""
    negative_words = {"sad", "bad", "hate", "angry", "upset", "wrong", "pain", "hurt", "die", "awful", "terrible", "horrible"}
    positive_words = {"good", "great", "love", "happy", "nice", "fun", "awesome", "excellent", "amazing", "beautiful"}
    
    lower_text = (text or "").lower()
    
    neg_count = sum(1 for word in negative_words if word in lower_text)
    pos_count = sum(1 for word in positive_words if word in lower_text)
    
    if pos_count > neg_count:
        return 1
    elif neg_count > pos_count:
        return -1
    return 0


def update_channel_sentiment(message):
    """Track channel sentiment over time."""
    try:
        channel_id = getattr(message.channel, "id", None) or str(getattr(message.channel, "name", "unknown"))
        sentiment = analyze_sentiment(message.content)
        _channel_sentiment_history[channel_id].appendleft(sentiment)
    except Exception:
        pass


def get_channel_vibe(channel):
    """Returns 'positive', 'negative', or 'neutral' based on recent messages."""
    try:
        channel_id = getattr(channel, "id", None) or str(getattr(channel, "name", "unknown"))
        history = list(_channel_sentiment_history.get(channel_id, []))
        if not history:
            return "neutral"
        avg_sentiment = sum(history) / len(history)
        if avg_sentiment > 0.2:
            return "positive"
        elif avg_sentiment < -0.2:
            return "negative"
        return "neutral"
    except Exception:
        return "neutral"


def update_user_interaction(message, pilot_name):
    """Track how often a user interacts with a specific pilot."""
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        _user_interaction_count[user_id][pilot_name] += 1
    except Exception:
        pass


def get_user_relationship_context(message, pilot_name):
    """Return info about how familiar this user is with the pilot."""
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        interactions = _user_interaction_count[user_id][pilot_name]
        if interactions > 10:
            return f"This person has talked to {pilot_name.split()[0]} many times. They know each other."
        elif interactions > 3:
            return f"This person has talked to {pilot_name.split()[0]} a few times. They're getting familiar."
        elif interactions > 0:
            return f"This person has talked to {pilot_name.split()[0]} before, but not often."
        return f"This person is new to talking with {pilot_name.split()[0]}."
    except Exception:
        return ""


def update_pilot_mood(pilot_name, sentiment_shift):
    """Shift a pilot's mood based on recent interactions."""
    try:
        current = _pilot_mood.get(pilot_name, 0.5)
        # Mood drifts slowly, bounded between 0 and 1
        new_mood = max(0.0, min(1.0, current + sentiment_shift * 0.05))
        _pilot_mood[pilot_name] = new_mood
    except Exception:
        pass


def get_pilot_mood_descriptor(pilot_name):
    """Return a descriptor of the pilot's current emotional state."""
    mood = _pilot_mood.get(pilot_name, 0.5)
    if "shinji" in pilot_name.lower():
        if mood > 0.7:
            return "feeling slightly less depressed"
        elif mood > 0.5:
            return "in their usual withdrawn state"
        else:
            return "especially withdrawn today"
    elif "asuka" in pilot_name.lower():
        if mood > 0.7:
            return "in a sharp, confrontational mood"
        elif mood > 0.5:
            return "their usual competitive self"
        else:
            return "unusually quiet"
    elif "rei" in pilot_name.lower():
        if mood > 0.7:
            return "unusually expressive"
        elif mood > 0.5:
            return "their typical distant self"
        else:
            return "even more withdrawn than usual"
    return "neutral"


def can_respond_to_message(message, bot_user):
    if message.author == bot_user:
        return False
    if not bot_user.mentioned_in(message):
        return False
    if getattr(message.author, "bot", False):
        return get_chain_depth(message.content) < MAX_BOT_CHAIN_DEPTH
    return True


def build_user_prompt(message, bot_user=None):
    cleaned_content = strip_chain_marker(resolve_mentions(message))
    sender_name = display_name_for_user(message.author)
    sender_kind = "bot-controlled pilot" if getattr(message.author, "bot", False) else "human"
    sender_is_owner = is_owner(message.author)
    owner_status = "yes" if sender_is_owner else "no"
    owner_instruction = (
        f"This sender is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}. "
        "Do not ask who they are."
        if sender_is_owner
        else f"The NERV handler is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}."
    )

    return (
        "Incoming communication context:\n"
        f"- sender: {sender_name}\n"
        f"- sender type: {sender_kind}\n"
        f"- sender is NERV handler: {owner_status}\n"
        f"- NERV handler name: {OWNER_DISPLAY_NAME}\n"
        f"- NERV handler role: {OWNER_ROLE_DESCRIPTION}\n"
        f"- handler instruction: {owner_instruction}\n"
        f"{build_channel_context(message)}"
        f"{build_usable_mentions_context(message, excluded_user=bot_user)}\n"
        "Message:\n"
        f"{cleaned_content}"
    )


def format_bot_reply(reply, source_message, bot_user=None):
    clean_reply = strip_chain_marker(reply).strip()
    clean_reply = restore_pilot_mentions(clean_reply, source_message, bot_user)
    next_depth = get_chain_depth(source_message.content) + 1
    return f"{clean_reply or '...'}{build_chain_marker(next_depth)}"


def build_chain_marker(depth):
    clamped_depth = max(1, min(depth, MAX_BOT_CHAIN_DEPTH))
    return (
        INVISIBLE_CHAIN_MARKER_PREFIX
        + (INVISIBLE_CHAIN_MARKER_UNIT * clamped_depth)
        + INVISIBLE_CHAIN_MARKER_SUFFIX
    )


def resolve_mentions(message):
    content = message.content
    for user in getattr(message, "mentions", []):
        label = display_name_for_user(user)
        mention_patterns = (
            f"<@{user.id}>",
            f"<@!{user.id}>",
        )
        for pattern in mention_patterns:
            content = content.replace(pattern, f"@{label}")
    return content


def restore_pilot_mentions(content, message, bot_user=None):
    if not content:
        return content

    updated = content
    for user in pilot_mention_users(message, excluded_user=bot_user):
        token = mention_token_for_user(user)
        if token in updated:
            continue

        for candidate in mention_replacement_candidates(user):
            pattern = re.compile(rf"(?<![@\w]){re.escape(candidate)}(?!\w)", re.IGNORECASE)
            updated, replacements = pattern.subn(token, updated, count=1)
            if replacements:
                break

    return updated


def build_channel_context(message):
    channel = getattr(message, "channel", None)
    channel_name = getattr(channel, "name", None)
    if not channel_name:
        return ""
    return f"- channel: #{channel_name}\n"


def build_usable_mentions_context(message, excluded_user=None):
    mention_lines = []
    for user in pilot_mention_users(message, excluded_user=excluded_user):
        pilot_name = display_name_for_user(user)
        mention_lines.append(f"  - {pilot_name} -> {mention_token_for_user(user)}")

    if not mention_lines:
        return "- usable pilot mentions: none\n\n"

    return "- usable pilot mentions:\n" + "\n".join(mention_lines) + "\n\n"


def pilot_mention_users(message, excluded_user=None):
    seen_pilots = set()
    users = []
    excluded_id = str(getattr(excluded_user, "id", "")) if excluded_user else None

    for user in getattr(message, "mentions", []):
        if excluded_id and str(getattr(user, "id", "")) == excluded_id:
            continue

        pilot_name = display_name_for_user(user)
        if not pilot_name_for_text(pilot_name):
            continue

        if pilot_name in seen_pilots:
            continue

        seen_pilots.add(pilot_name)
        users.append(user)

    return users


def mention_replacement_candidates(user):
    pilot_name = display_name_for_user(user)
    first_name = pilot_name.split()[0]
    return (pilot_name, first_name)


def mention_token_for_user(user):
    return f"<@{user.id}>"


def display_name_for_user(user):
    raw_names = [
        getattr(user, "display_name", ""),
        getattr(user, "global_name", ""),
        getattr(user, "name", ""),
    ]
    for name in raw_names:
        pilot_name = pilot_name_for_text(name)
        if pilot_name:
            return pilot_name
    return next((name for name in raw_names if name), "Unknown speaker")


def pilot_name_for_text(text):
    normalized = normalize_name(text)
    if not normalized:
        return None
    for profile in PILOT_PROFILES.values():
        if any(alias in normalized for alias in profile["aliases"]):
            return profile["name"]
    return None


def is_owner(user):
    if OWNER_DISCORD_ID and str(getattr(user, "id", "")) == OWNER_DISCORD_ID:
        return True
    if OWNER_DISPLAY_NAME:
        names = (
            getattr(user, "display_name", ""),
            getattr(user, "global_name", ""),
            getattr(user, "name", ""),
        )
        return any(normalize_name(name) == normalize_name(OWNER_DISPLAY_NAME) for name in names)
    return False


def get_chain_depth(content):
    hidden_match = INVISIBLE_CHAIN_MARKER_RE.search(content or "")
    if hidden_match:
        return len(hidden_match.group(1))

    visible_match = VISIBLE_CHAIN_MARKER_RE.search(content or "")
    if visible_match:
        return int(visible_match.group(1))

    return 0


def strip_chain_marker(content):
    without_hidden = INVISIBLE_CHAIN_MARKER_RE.sub("", content or "")
    return VISIBLE_CHAIN_MARKER_RE.sub("", without_hidden).strip()


def normalize_name(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

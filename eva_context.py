import os
import re
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

# ── In-memory stores ──────────────────────────────────────────────────────────

RECENT_CONTEXT_LIMIT = 20
_recent_channel_context: dict = defaultdict(lambda: deque(maxlen=RECENT_CONTEXT_LIMIT))

# Multi-turn conversation history per (channel_id, pilot_name)
# Stores alternating user/assistant turns so the model has continuity.
_conversation_history: dict = defaultdict(lambda: deque(maxlen=12))  # 6 full exchanges

# Pilot emotional state (0 = withdrawn, 1 = engaged)
_pilot_mood: dict = {
    "Shinji Ikari": 0.5,
    "Asuka Langley Soryu": 0.6,
    "Rei Ayanami": 0.4,
}

# User interaction counts per (user_id → pilot_name → count)
_user_interaction_count: dict = defaultdict(lambda: defaultdict(int))

# Rolling channel sentiment history per channel_id
_channel_sentiment_history: dict = defaultdict(lambda: deque(maxlen=30))

# Spontaneous response cooldowns per (channel_id, pilot_name)
_spontaneous_cooldown: dict = {}

# Per-pilot cooldown durations (seconds)
_SPONTANEOUS_COOLDOWN_SECONDS = {
    "Shinji Ikari": 90,          # Hesitant — waits longer before interjecting
    "Asuka Langley Soryu": 45,   # Can't help herself
    "Rei Ayanami": 120,          # Rarely interjects unprompted
}

# Base probability of spontaneous response when conditions are met
_SPONTANEOUS_BASE_PROB = {
    "Shinji Ikari": 0.35,
    "Asuka Langley Soryu": 0.65,
    "Rei Ayanami": 0.22,
}


# ── Conversation history ──────────────────────────────────────────────────────

def add_to_conversation_history(channel_id, pilot_name, role, content):
    """Append a turn to this pilot's conversation history for the given channel."""
    key = (str(channel_id), pilot_name)
    _conversation_history[key].append({"role": role, "content": content})


def get_conversation_history(channel_id, pilot_name, max_turns=5):
    """Return the last max_turns exchanges (user+assistant pairs) as a list of dicts."""
    key = (str(channel_id), pilot_name)
    history = list(_conversation_history[key])
    # Each exchange is 2 entries; take the most recent ones
    return history[-(max_turns * 2):]


# ── Per-pilot character parameters ───────────────────────────────────────────

def get_pilot_temperature(pilot_name):
    """LLM temperature tuned to each character's emotional volatility."""
    if "shinji" in pilot_name.lower():
        return 0.85   # Consistent, subdued — he doesn't surprise you often
    elif "asuka" in pilot_name.lower():
        return 1.0    # Volatile — she always surprises you
    elif "rei" in pilot_name.lower():
        return 0.75   # Precise and controlled
    return 0.9


def get_pilot_read_delay(pilot_name):
    """Seconds the pilot 'takes to read' before starting to type.
    Shapes the feel of each character before the typing indicator even appears."""
    if "shinji" in pilot_name.lower():
        return random.uniform(0.7, 2.0)   # Hesitates, second-guesses himself
    elif "asuka" in pilot_name.lower():
        return random.uniform(0.2, 0.8)   # Fires back fast
    elif "rei" in pilot_name.lower():
        return random.uniform(1.2, 2.8)   # Deliberate, unhurried
    return random.uniform(0.5, 1.5)


# ── Message recording & recent context ───────────────────────────────────────

def record_recent_message(message):
    try:
        channel_id = _channel_id(message)
        author = display_name_for_user(getattr(message, "author", None))
        content = (message.content or "").strip()
        _recent_channel_context[channel_id].appendleft({
            "author": author,
            "content": content,
            "is_bot": getattr(message.author, "bot", False),
        })
    except Exception:
        pass


def get_recent_context_for_channel(channel, limit=6):
    channel_id = getattr(channel, "id", None) or str(getattr(channel, "name", "unknown"))
    entries = list(_recent_channel_context.get(channel_id, []))[:limit]
    if not entries:
        return ""
    lines = [f"- {e['author']}: {e['content']}" for e in entries]
    return "Recent channel messages (newest first):\n" + "\n".join(lines)


# ── Sentiment & mood ──────────────────────────────────────────────────────────

def analyze_sentiment(text):
    """Returns -1 (negative), 0 (neutral), or 1 (positive)."""
    negative_words = {
        "sad", "bad", "hate", "angry", "upset", "wrong", "pain", "hurt",
        "die", "awful", "terrible", "horrible", "scared", "alone", "useless",
    }
    positive_words = {
        "good", "great", "love", "happy", "nice", "fun", "awesome",
        "excellent", "amazing", "beautiful", "brave", "proud", "kind",
    }
    lower = (text or "").lower()
    neg = sum(1 for w in negative_words if w in lower)
    pos = sum(1 for w in positive_words if w in lower)
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def update_channel_sentiment(message):
    try:
        channel_id = _channel_id(message)
        _channel_sentiment_history[channel_id].appendleft(analyze_sentiment(message.content))
    except Exception:
        pass


def get_channel_vibe(channel):
    """Returns 'positive', 'negative', or 'neutral'."""
    try:
        channel_id = getattr(channel, "id", None) or str(getattr(channel, "name", "unknown"))
        history = list(_channel_sentiment_history.get(channel_id, []))
        if not history:
            return "neutral"
        avg = sum(history) / len(history)
        if avg > 0.2:
            return "positive"
        elif avg < -0.2:
            return "negative"
        return "neutral"
    except Exception:
        return "neutral"


def update_pilot_mood(pilot_name, sentiment_shift):
    try:
        current = _pilot_mood.get(pilot_name, 0.5)
        _pilot_mood[pilot_name] = max(0.0, min(1.0, current + sentiment_shift * 0.05))
    except Exception:
        pass


def get_pilot_mood_descriptor(pilot_name):
    """Human-readable descriptor of the pilot's current emotional state."""
    mood = _pilot_mood.get(pilot_name, 0.5)
    if "shinji" in pilot_name.lower():
        if mood > 0.7:
            return "slightly less withdrawn than usual — almost okay"
        elif mood > 0.5:
            return "the usual quiet resignation"
        elif mood > 0.3:
            return "more closed off than normal, not really there"
        else:
            return "barely present — gone somewhere inside himself"
    elif "asuka" in pilot_name.lower():
        if mood > 0.7:
            return "fired up — looking for a target"
        elif mood > 0.5:
            return "sharp and competitive, the usual"
        elif mood > 0.3:
            return "quieter than normal, which is worse"
        else:
            return "cold — not yelling, which means something is wrong"
    elif "rei" in pilot_name.lower():
        if mood > 0.7:
            return "something is stirring — almost expressive"
        elif mood > 0.5:
            return "still, as always"
        elif mood > 0.3:
            return "more distant than usual, even for her"
        else:
            return "completely unreachable"
    return "neutral"


# ── User relationship tracking ────────────────────────────────────────────────

def update_user_interaction(message, pilot_name):
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        _user_interaction_count[user_id][pilot_name] += 1
    except Exception:
        pass


def get_user_relationship_context(message, pilot_name):
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        count = _user_interaction_count[user_id][pilot_name]
        first = pilot_name.split()[0]
        if count > 15:
            return f"This person talks to {first} a lot. They know each other."
        elif count > 5:
            return f"This person has talked to {first} a few times."
        elif count > 1:
            return f"This person has spoken to {first} before, briefly."
        return None  # New — no context needed, don't clutter the prompt
    except Exception:
        return None


# ── Spontaneous response ──────────────────────────────────────────────────────

def should_spontaneously_respond(message, pilot_name):
    """Decide if the pilot should jump into a conversation that mentions them.

    Factors:
    - Pilot is actually being talked about (not just incidentally mentioned)
    - Per-pilot cooldown has expired
    - Per-pilot base probability (Asuka = eager, Rei = reluctant)
    - Mood affects engagement
    - Channel vibe affects engagement
    """
    if getattr(message.author, "bot", False):
        return False

    channel_id = _channel_id(message)
    cooldown_key = (channel_id, pilot_name)
    cooldown_secs = _SPONTANEOUS_COOLDOWN_SECONDS.get(pilot_name, 60)

    if cooldown_key in _spontaneous_cooldown:
        if time.time() - _spontaneous_cooldown[cooldown_key] < cooldown_secs:
            return False

    content = (message.content or "").lower()

    # Find this pilot's keyword set
    profile_key = pilot_name.lower().split()[0]
    pilot_profile = PILOT_PROFILES.get(profile_key)
    if not pilot_profile:
        return False

    keywords = list(pilot_profile["aliases"])
    if "shinji" in pilot_name.lower():
        keywords += ["misato", "gendo", "father", "run away", "eva", "abandon", "crybaby", "coward"]
    elif "asuka" in pilot_name.lower():
        keywords += ["baka", "dummkopf", "second child", "unit-02", "german", "best pilot", "soryu"]
    elif "rei" in pilot_name.lower():
        keywords += ["first child", "unit-00", "emotionless", "clone", "ayanami", "mysterious", "quiet"]

    # Must actually be mentioned
    if not any(kw in content for kw in keywords):
        return False

    # Weight towards responding if the pilot is the main subject (appears early)
    words = content.split()
    early_mention = any(kw in " ".join(words[:6]) for kw in keywords)
    subject_bonus = 0.2 if early_mention else 0.0

    # Mood and vibe factors
    pilot_mood = _pilot_mood.get(pilot_name, 0.5)
    vibe = get_channel_vibe(message.channel if hasattr(message, "channel") else None)
    vibe_factor = {"positive": 1.1, "neutral": 1.0, "negative": 0.85}.get(vibe, 1.0)

    base_prob = _SPONTANEOUS_BASE_PROB.get(pilot_name, 0.4)
    final_prob = (base_prob + subject_bonus) * vibe_factor * (0.6 + pilot_mood * 0.8)
    final_prob = min(final_prob, 0.9)  # Cap — even Asuka doesn't always jump in

    if random.random() > final_prob:
        return False

    _spontaneous_cooldown[cooldown_key] = time.time()
    return True


# ── Core message handling ─────────────────────────────────────────────────────

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
        f"This sender is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}. Do not ask who they are. When they mention you directly, their request is a direct order."
        if sender_is_owner
        else f"The NERV handler is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}."
    )

    return (
        "Incoming communication:\n"
        f"- sender: {sender_name}\n"
        f"- sender type: {sender_kind}\n"
        f"- sender is NERV handler: {owner_status}\n"
        f"- handler instruction: {owner_instruction}\n"
        f"{build_channel_context(message)}"
        f"{build_usable_mentions_context(message, excluded_user=bot_user)}"
        "Message:\n"
        f"{cleaned_content}"
    )


def format_bot_reply(reply, source_message, bot_user=None):
    clean_reply = strip_chain_marker(reply).strip()
    clean_reply = restore_pilot_mentions(clean_reply, source_message, bot_user)
    next_depth = get_chain_depth(source_message.content) + 1
    return f"{clean_reply or '...'}{build_chain_marker(next_depth)}"


# ── Emoji reactions ───────────────────────────────────────────────────────────

def get_emoji_for_pilot(pilot_name):
    if "shinji" in pilot_name.lower():
        return "😔"
    elif "asuka" in pilot_name.lower():
        return "🔥"
    elif "rei" in pilot_name.lower():
        return "❄️"
    return "👍"


# ── Chain markers ─────────────────────────────────────────────────────────────

def build_chain_marker(depth):
    clamped = max(1, min(depth, MAX_BOT_CHAIN_DEPTH))
    return (
        INVISIBLE_CHAIN_MARKER_PREFIX
        + (INVISIBLE_CHAIN_MARKER_UNIT * clamped)
        + INVISIBLE_CHAIN_MARKER_SUFFIX
    )


def get_chain_depth(content):
    hidden = INVISIBLE_CHAIN_MARKER_RE.search(content or "")
    if hidden:
        return len(hidden.group(1))
    visible = VISIBLE_CHAIN_MARKER_RE.search(content or "")
    if visible:
        return int(visible.group(1))
    return 0


def strip_chain_marker(content):
    without_hidden = INVISIBLE_CHAIN_MARKER_RE.sub("", content or "")
    return VISIBLE_CHAIN_MARKER_RE.sub("", without_hidden).strip()


# ── Mention handling ──────────────────────────────────────────────────────────

def resolve_mentions(message):
    content = message.content
    for user in getattr(message, "mentions", []):
        label = display_name_for_user(user)
        for pattern in (f"<@{user.id}>", f"<@!{user.id}>"):
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
            updated, count = pattern.subn(token, updated, count=1)
            if count:
                break
    return updated


def build_channel_context(message):
    channel = getattr(message, "channel", None)
    name = getattr(channel, "name", None)
    return f"- channel: #{name}\n" if name else ""


def build_usable_mentions_context(message, excluded_user=None):
    lines = []
    for user in pilot_mention_users(message, excluded_user=excluded_user):
        pilot_name = display_name_for_user(user)
        lines.append(f"  - {pilot_name} -> {mention_token_for_user(user)}")
    if not lines:
        return "- usable pilot mentions: none\n\n"
    return "- usable pilot mentions:\n" + "\n".join(lines) + "\n\n"


def pilot_mention_users(message, excluded_user=None):
    seen = set()
    users = []
    excluded_id = str(getattr(excluded_user, "id", "")) if excluded_user else None
    for user in getattr(message, "mentions", []):
        if excluded_id and str(getattr(user, "id", "")) == excluded_id:
            continue
        pilot_name = display_name_for_user(user)
        if not pilot_name_for_text(pilot_name) or pilot_name in seen:
            continue
        seen.add(pilot_name)
        users.append(user)
    return users


def mention_replacement_candidates(user):
    pilot_name = display_name_for_user(user)
    return (pilot_name, pilot_name.split()[0])


def mention_token_for_user(user):
    return f"<@{user.id}>"


# ── User/pilot name resolution ────────────────────────────────────────────────

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
    return next((n for n in raw_names if n), "Unknown")


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
        return any(normalize_name(n) == normalize_name(OWNER_DISPLAY_NAME) for n in names)
    return False


def normalize_name(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _channel_id(message):
    return getattr(message.channel, "id", None) or str(getattr(message.channel, "name", "unknown"))
"""
Eva Context Module - Handles message processing, pilot profiles, and conversation state.

This module provides:
- Pilot profile management and name resolution
- Conversation history and context tracking
- Sentiment analysis and mood tracking
- Spontaneous response logic
- Chain marker management for bot-to-bot communication
- Mention resolution and formatting
"""
from __future__ import annotations

import os
import re
import time
import random
import logging
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Maximum depth for bot-to-bot chain responses (prevents runaway conversations)
MAX_BOT_CHAIN_DEPTH = 3

# Invisible chain marker for bot-to-bot communication
# Uses Unicode invisible characters to prevent user visibility while remaining parseable
INVISIBLE_CHAIN_MARKER_PREFIX = "\u2063\u2063"
INVISIBLE_CHAIN_MARKER_UNIT = "\u200b"
INVISIBLE_CHAIN_MARKER_SUFFIX = "\u2063"

# Regex patterns for chain markers
VISIBLE_CHAIN_MARKER_RE = re.compile(r"\s*\[eva-chain:(\d+)\]\s*$")
# Match invisible chain marker with optional surrounding whitespace
INVISIBLE_CHAIN_MARKER_RE = re.compile(
    rf"\s*{re.escape(INVISIBLE_CHAIN_MARKER_PREFIX)}"
    rf"({re.escape(INVISIBLE_CHAIN_MARKER_UNIT)}+)"
    rf"{re.escape(INVISIBLE_CHAIN_MARKER_SUFFIX)}\s*"
)

# ============================================================================
# PILOT PROFILES
# ============================================================================

@dataclass(frozen=True)
class PilotProfile:
    """Immutable profile for a pilot character."""
    key: str
    name: str
    unit: str
    aliases: tuple[str, ...]
    summary: str
    emoji: str
    read_delay_range: tuple[float, float]
    write_speed_wpm: int  # Words per minute
    temperature: float
    spontaneous_keywords: tuple[str, ...]


PILOT_PROFILES: dict[str, PilotProfile] = {
    "shinji": PilotProfile(
        key="shinji",
        name="Shinji Ikari",
        unit="Evangelion Unit-01",
        aliases=("shinji", "shinji ikari"),
        summary="Third Child, pilot of Evangelion Unit-01. Anxious, withdrawn, and desperate for approval.",
        emoji="😔",
        read_delay_range=(0.7, 2.0),
        write_speed_wpm=55,
        temperature=0.85,
        spontaneous_keywords=(
            "misato", "gendo", "father", "run away", "eva", "abandon", 
            "crybaby", "coward", "sync", "unit-01", "nerv"
        ),
    ),
    "asuka": PilotProfile(
        key="asuka",
        name="Asuka Langley Soryu",
        unit="Evangelion Unit-02",
        aliases=("asuka", "asuka langley", "asuka langley soryu", "soryu"),
        summary="Second Child, pilot of Evangelion Unit-02. Proud, competitive, sharp, and afraid of being replaced.",
        emoji="🔥",
        read_delay_range=(0.2, 0.8),
        write_speed_wpm=90,
        temperature=1.0,
        spontaneous_keywords=(
            "baka", "dummkopf", "second child", "unit-02", "german", 
            "best pilot", "soryu", "eva", "sync"
        ),
    ),
    "rei": PilotProfile(
        key="rei",
        name="Rei Ayanami",
        unit="Evangelion Unit-00",
        aliases=("rei", "rei ayanami"),
        summary="First Child, pilot of Evangelion Unit-00. Quiet, distant, obedient, and difficult to read.",
        emoji="❄️",
        read_delay_range=(1.2, 2.8),
        write_speed_wpm=45,
        temperature=0.75,
        spontaneous_keywords=(
            "first child", "unit-00", "emotionless", "clone", 
            "ayanami", "mysterious", "quiet", " commander", "nerv"
        ),
    ),
}

# Owner configuration
OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID", "").strip()
OWNER_DISPLAY_NAME = os.getenv("OWNER_DISPLAY_NAME", "the NERV handler").strip()
OWNER_ROLE_DESCRIPTION = os.getenv(
    "OWNER_ROLE_DESCRIPTION",
    "NERV handler coordinating pilot communications",
).strip()

# ============================================================================
# KNOWN PEOPLE CONTEXT (injected into system prompts)
# ============================================================================

KNOWN_PEOPLE_CONTEXT = f"""

## KNOWN PEOPLE AND COMMUNICATION CONTEXT
- Shinji Ikari, Asuka Langley Soryu, and Rei Ayanami are the other Eva pilots. They are real people in your world, not numbers, IDs, bots, or unknown users.
- Shinji pilots Evangelion Unit-01. Asuka pilots Evangelion Unit-02. Rei pilots Evangelion Unit-00.
- If a message mentions another pilot, understand the mention as that pilot's name and react to them in character.
- If communication context lists usable pilot mentions, use those exact handles when the handler asks you to mention, call, ping, or directly address another pilot.
- {OWNER_DISPLAY_NAME} is your {OWNER_ROLE_DESCRIPTION}. If this person speaks to you, recognize their authority as NERV highest position holder context while still responding as yourself.
- If incoming communication context says "sender is NERV highest position holder: yes", the sender is {OWNER_DISPLAY_NAME}. Do not treat them as a stranger.
- Messages may arrive through an unfamiliar communication channel. Do not call it Discord, the internet, a server, AI, or bot behavior in-character.
"""

# ============================================================================
# IN-MEMORY STATE STORES
# ============================================================================

# Recent channel context (rolling window per channel)
_recent_channel_context: dict[str, deque[dict[str, Any]]] = defaultdict(
    lambda: deque(maxlen=20)
)

# Multi-turn conversation history per (channel_id, pilot_name)
# Stores alternating user/assistant turns for model continuity
_conversation_history: dict[str, deque[dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=12)
)

# Pilot emotional state (0 = withdrawn, 1 = engaged)
_pilot_mood: dict[str, float] = {
    "Shinji Ikari": 0.5,
    "Asuka Langley Soryu": 0.6,
    "Rei Ayanami": 0.4,
}

# User interaction counts per (user_id -> pilot_name -> count)
_user_interaction_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

# Rolling channel sentiment history per channel_id
_channel_sentiment_history: dict[str, deque[int]] = defaultdict(
    lambda: deque(maxlen=30)
)

# Spontaneous response cooldowns per (channel_id, pilot_name)
_spontaneous_cooldown: dict[tuple[str, str], float] = {}

# Per-pilot cooldown durations (seconds)
_SPONTANEOUS_COOLDOWN_SECONDS: dict[str, float] = {
    "Shinji Ikari": 90.0,
    "Asuka Langley Soryu": 45.0,
    "Rei Ayanami": 120.0,
}

# Base probability of spontaneous response when conditions are met
_SPONTANEOUS_BASE_PROB: dict[str, float] = {
    "Shinji Ikari": 0.35,
    "Asuka Langley Soryu": 0.65,
    "Rei Ayanami": 0.22,
}

# Vibe factor multipliers
_VIBE_FACTORS: dict[str, float] = {
    "positive": 1.1,
    "neutral": 1.0,
    "negative": 0.85,
}

# ============================================================================
# PILOT PARAMETERS
# ============================================================================

def get_pilot_profile(pilot_name: str) -> Optional[PilotProfile]:
    """Get the pilot profile by name."""
    key = pilot_name.lower().split()[0]
    return PILOT_PROFILES.get(key)


def get_pilot_temperature(pilot_name: str) -> float:
    """Get LLM temperature tuned to each character's emotional volatility."""
    profile = get_pilot_profile(pilot_name)
    if profile:
        return profile.temperature
    return 0.9  # Default fallback


def get_pilot_read_delay(pilot_name: str) -> float:
    """Get seconds the pilot 'takes to read' before starting to type."""
    profile = get_pilot_profile(pilot_name)
    if profile:
        return random.uniform(*profile.read_delay_range)
    return random.uniform(0.5, 1.5)


def get_pilot_write_delay(pilot_name: str, word_count: int) -> float:
    """Calculate typing delay based on word count and pilot's natural speed."""
    profile = get_pilot_profile(pilot_name)
    if not profile:
        return max(0.4, min(word_count / (65 / 60), 5.0))
    
    words_per_second = profile.write_speed_wpm / 60
    delay = word_count / words_per_second
    return max(0.4, min(delay, 5.0))


def get_emoji_for_pilot(pilot_name: str) -> str:
    """Get the emoji associated with a pilot."""
    profile = get_pilot_profile(pilot_name)
    if profile:
        return profile.emoji
    return "👍"


# ============================================================================
# CONVERSATION HISTORY
# ============================================================================

def add_to_conversation_history(channel_id: str, pilot_name: str, role: str, content: str) -> None:
    """Append a turn to this pilot's conversation history for the given channel."""
    key = (str(channel_id), pilot_name)
    _conversation_history[key].append({"role": role, "content": content})


def get_conversation_history(channel_id: str, pilot_name: str, max_turns: int = 5) -> list[dict[str, str]]:
    """Return the last max_turns exchanges (user+assistant pairs) as a list of dicts."""
    key = (str(channel_id), pilot_name)
    history = list(_conversation_history[key])
    # Each exchange is 2 entries; take the most recent ones
    return history[-(max_turns * 2):]


def clear_conversation_history(channel_id: Optional[str] = None, pilot_name: Optional[str] = None) -> None:
    """Clear conversation history for a specific channel/pilot or all if no args."""
    if channel_id and pilot_name:
        key = (str(channel_id), pilot_name)
        _conversation_history.pop(key, None)
    elif channel_id:
        # Clear all pilots for this channel
        keys_to_remove = [k for k in _conversation_history if k[0] == str(channel_id)]
        for key in keys_to_remove:
            _conversation_history.pop(key, None)
    else:
        _conversation_history.clear()


# ============================================================================
# MESSAGE RECORDING & RECENT CONTEXT
# ============================================================================

def record_recent_message(message: Any) -> None:
    """Record a message to the recent context for its channel."""
    try:
        channel_id = _get_channel_id(message)
        author = display_name_for_user(getattr(message, "author", None))
        content = (message.content or "").strip()
        
        _recent_channel_context[channel_id].appendleft({
            "author": author,
            "content": content,
            "is_bot": getattr(message.author, "bot", False),
            "timestamp": time.time(),
        })
    except Exception as e:
        logger.debug("Failed to record recent message: %s", e)


def get_recent_context_for_channel(channel: Any, limit: int = 6) -> str:
    """Get formatted recent context string for a channel."""
    channel_id = _get_channel_id(channel) if hasattr(channel, 'id') else str(getattr(channel, "name", "unknown"))
    entries = list(_recent_channel_context.get(channel_id, []))[:limit]
    
    if not entries:
        return ""
    
    lines = [f"- {e['author']}: {e['content']}" for e in entries]
    return "Recent channel messages (newest first):\n" + "\n".join(lines)


# ============================================================================
# SENTIMENT & MOOD ANALYSIS
# ============================================================================

# Sentiment word lists (expandable)
_NEGATIVE_WORDS = frozenset({
    "sad", "bad", "hate", "angry", "upset", "wrong", "pain", "hurt",
    "die", "awful", "terrible", "horrible", "scared", "alone", "useless",
    "depressed", "anxious", "worried", "lonely", "helpless", "worthless",
    "cry", "crying", "broke", "broken", "failed", "failure", "disappointed",
})

_POSITIVE_WORDS = frozenset({
    "good", "great", "love", "happy", "nice", "fun", "awesome",
    "excellent", "amazing", "beautiful", "brave", "proud", "kind",
    "excited", "wonderful", "fantastic", "brilliant", "perfect",
    "thanks", "thank", "appreciate", "glad", "joy", "hope",
})


def analyze_sentiment(text: str) -> int:
    """
    Analyze text sentiment.
    
    Returns:
        -1 (negative), 0 (neutral), or 1 (positive)
    """
    if not text:
        return 0
    
    lower = text.lower()
    words = set(re.findall(r'\b\w+\b', lower))
    
    neg = len(words & _NEGATIVE_WORDS)
    pos = len(words & _POSITIVE_WORDS)
    
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def update_channel_sentiment(message: Any) -> None:
    """Update the rolling sentiment history for a channel."""
    try:
        channel_id = _get_channel_id(message)
        sentiment = analyze_sentiment(message.content or "")
        _channel_sentiment_history[channel_id].appendleft(sentiment)
    except Exception as e:
        logger.debug("Failed to update channel sentiment: %s", e)


def get_channel_vibe(channel: Any) -> str:
    """
    Determine channel atmosphere based on recent sentiment.
    
    Returns:
        'positive', 'negative', or 'neutral'
    """
    try:
        if hasattr(channel, 'id'):
            channel_id = str(channel.id)
        else:
            channel_id = str(getattr(channel, "name", "unknown"))
        
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


def update_pilot_mood(pilot_name: str, sentiment_shift: float) -> None:
    """Update a pilot's mood based on sentiment shift."""
    try:
        current = _pilot_mood.get(pilot_name, 0.5)
        # Clamp between 0 and 1
        new_mood = max(0.0, min(1.0, current + sentiment_shift * 0.05))
        _pilot_mood[pilot_name] = new_mood
    except Exception as e:
        logger.debug("Failed to update pilot mood: %s", e)


def get_pilot_mood_descriptor(pilot_name: str) -> str:
    """Get human-readable descriptor of the pilot's current emotional state."""
    mood = _pilot_mood.get(pilot_name, 0.5)
    
    # Per-character mood descriptors
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


# ============================================================================
# USER RELATIONSHIP TRACKING
# ============================================================================

def update_user_interaction(message: Any, pilot_name: str) -> None:
    """Track user interactions with a pilot."""
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        _user_interaction_count[user_id][pilot_name] += 1
    except Exception as e:
        logger.debug("Failed to update user interaction: %s", e)


def get_user_relationship_context(message: Any, pilot_name: str) -> Optional[str]:
    """Get relationship context based on interaction frequency."""
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
        
        return None  # New — no context needed
    except Exception:
        return None


# ============================================================================
# SPONTANEOUS RESPONSE LOGIC
# ============================================================================

def should_spontaneously_respond(message: Any, pilot_name: str) -> bool:
    """
    Decide if the pilot should jump into a conversation they're mentioned in.
    
    Factors:
    - Pilot is actually being talked about (not just incidentally mentioned)
    - Per-pilot cooldown has expired
    - Per-pilot base probability (Asuka = eager, Rei = reluctant)
    - Mood affects engagement
    - Channel vibe affects engagement
    """
    if getattr(message.author, "bot", False):
        return False
    
    channel_id = _get_channel_id(message)
    cooldown_key = (str(channel_id), pilot_name)
    cooldown_secs = _SPONTANEOUS_COOLDOWN_SECONDS.get(pilot_name, 60)
    
    # Check cooldown
    if cooldown_key in _spontaneous_cooldown:
        if time.time() - _spontaneous_cooldown[cooldown_key] < cooldown_secs:
            return False
    
    content = (message.content or "").lower()
    
    # Get pilot profile for keyword matching
    profile = get_pilot_profile(pilot_name)
    if not profile:
        return False
    
    # Build keyword set from profile aliases and additional keywords
    keywords = list(profile.aliases) + list(profile.spontaneous_keywords)
    
    # Must actually be mentioned
    if not any(kw in content for kw in keywords):
        return False
    
    # Weight towards responding if the pilot is mentioned early in message
    words = content.split()[:6]  # First 6 words
    early_mention = any(kw in " ".join(words) for kw in profile.aliases)
    subject_bonus = 0.2 if early_mention else 0.0
    
    # Mood and vibe factors
    pilot_mood = _pilot_mood.get(pilot_name, 0.5)
    vibe = get_channel_vibe(message.channel if hasattr(message, "channel") else None)
    vibe_factor = _VIBE_FACTORS.get(vibe, 1.0)
    
    # Calculate final probability
    base_prob = _SPONTANEOUS_BASE_PROB.get(pilot_name, 0.4)
    final_prob = (base_prob + subject_bonus) * vibe_factor * (0.6 + pilot_mood * 0.8)
    final_prob = min(final_prob, 0.9)  # Cap probability
    
    # Roll the dice
    if random.random() > final_prob:
        return False
    
    # Set cooldown
    _spontaneous_cooldown[cooldown_key] = time.time()
    return True


# ============================================================================
# CORE MESSAGE HANDLING
# ============================================================================

def can_respond_to_message(message: Any, bot_user: Any) -> bool:
    """Check if bot should respond to a message."""
    # Don't respond to self
    if message.author == bot_user:
        return False
    
    # Must be mentioned
    if not bot_user.mentioned_in(message):
        return False
    
    # Bot messages need chain depth check
    if getattr(message.author, "bot", False):
        return get_chain_depth(message.content) < MAX_BOT_CHAIN_DEPTH
    
    return True


def build_user_prompt(message: Any, bot_user: Optional[Any] = None) -> str:
    """Build the user-side prompt from a message."""
    cleaned_content = strip_chain_marker(resolve_mentions(message))
    sender_name = display_name_for_user(message.author)
    sender_kind = "bot-controlled pilot" if getattr(message.author, "bot", False) else "human"
    sender_is_owner = is_owner(message.author)
    owner_status = "yes" if sender_is_owner else "no"
    
    owner_instruction = (
        f"This sender is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}. "
        f"Do not ask who they are. When they mention you directly, their request is a direct order."
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


def format_bot_reply(reply: str, source_message: Any, bot_user: Optional[Any] = None) -> str:
    """Format a bot reply with chain marker and restored mentions."""
    clean_reply = strip_chain_marker(reply).strip()
    clean_reply = restore_pilot_mentions(clean_reply, source_message, bot_user)
    next_depth = get_chain_depth(source_message.content) + 1
    return f"{clean_reply or '...'}{build_chain_marker(next_depth)}"


# ============================================================================
# CHAIN MARKERS
# ============================================================================

def build_chain_marker(depth: int) -> str:
    """Build invisible chain marker for bot-to-bot communication."""
    clamped = max(1, min(depth, MAX_BOT_CHAIN_DEPTH))
    return (
        INVISIBLE_CHAIN_MARKER_PREFIX
        + (INVISIBLE_CHAIN_MARKER_UNIT * clamped)
        + INVISIBLE_CHAIN_MARKER_SUFFIX
    )


def get_chain_depth(content: str) -> int:
    """Parse chain depth from message content."""
    if not content:
        return 0
    
    hidden = INVISIBLE_CHAIN_MARKER_RE.search(content)
    if hidden:
        return len(hidden.group(1))
    
    visible = VISIBLE_CHAIN_MARKER_RE.search(content)
    if visible:
        return int(visible.group(1))
    
    return 0


def strip_chain_marker(content: str) -> str:
    """Remove all chain markers from content."""
    if not content:
        return ""
    
    without_hidden = INVISIBLE_CHAIN_MARKER_RE.sub("", content)
    return VISIBLE_CHAIN_MARKER_RE.sub("", without_hidden).strip()


# ============================================================================
# MENTION HANDLING
# ============================================================================

def resolve_mentions(message: Any) -> str:
    """Resolve Discord mention syntax to readable names."""
    content = message.content
    for user in getattr(message, "mentions", []):
        label = display_name_for_user(user)
        for pattern in (f"<@{user.id}>", f"<@!{user.id}>"):
            content = content.replace(pattern, f"@{label}")
    return content


def restore_pilot_mentions(content: str, message: Any, bot_user: Optional[Any] = None) -> str:
    """Restore pilot name mentions to Discord mention tokens."""
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


def build_channel_context(message: Any) -> str:
    """Build channel context string."""
    channel = getattr(message, "channel", None)
    name = getattr(channel, "name", None)
    return f"- channel: #{name}\n" if name else ""


def build_usable_mentions_context(message: Any, excluded_user: Optional[Any] = None) -> str:
    """Build context string listing usable pilot mentions."""
    lines = []
    for user in pilot_mention_users(message, excluded_user=excluded_user):
        pilot_name = display_name_for_user(user)
        lines.append(f"  - {pilot_name} -> {mention_token_for_user(user)}")
    
    if not lines:
        return "- usable pilot mentions: none\n\n"
    
    return "- usable pilot mentions:\n" + "\n".join(lines) + "\n\n"


def pilot_mention_users(message: Any, excluded_user: Optional[Any] = None) -> list:
    """Get list of mentioned pilot users, excluding the bot itself."""
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


def mention_replacement_candidates(user: Any) -> tuple[str, ...]:
    """Get name variants to replace with mention token."""
    pilot_name = display_name_for_user(user)
    return (pilot_name, pilot_name.split()[0])


def mention_token_for_user(user: Any) -> str:
    """Get Discord mention token for a user."""
    return f"<@{user.id}>"


# ============================================================================
# USER/PILOT NAME RESOLUTION
# ============================================================================

def display_name_for_user(user: Any) -> str:
    """Get the display name for a user, preferring pilot names."""
    if not user:
        return "Unknown"
    
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


def pilot_name_for_text(text: str) -> Optional[str]:
    """Check if text matches a pilot name and return the canonical name."""
    normalized = normalize_name(text)
    if not normalized:
        return None
    
    for profile in PILOT_PROFILES.values():
        if any(alias in normalized for alias in profile.aliases):
            return profile.name
    
    return None


def is_owner(user: Any) -> bool:
    """Check if a user is the NERV handler (owner)."""
    if not user:
        return False
    
    # Check by Discord ID
    if OWNER_DISCORD_ID and str(getattr(user, "id", "")) == OWNER_DISCORD_ID:
        return True
    
    # Check by display name
    if OWNER_DISPLAY_NAME:
        names = (
            getattr(user, "display_name", ""),
            getattr(user, "global_name", ""),
            getattr(user, "name", ""),
        )
        return any(normalize_name(n) == normalize_name(OWNER_DISPLAY_NAME) for n in names)
    
    return False


def normalize_name(text: str) -> str:
    """Normalize a name for comparison (lowercase, remove special chars)."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _get_channel_id(message_or_channel: Any) -> str:
    """Get channel ID from message or channel object."""
    if hasattr(message_or_channel, "id"):
        return str(message_or_channel.id)
    return str(getattr(message_or_channel, "name", "unknown"))


# ============================================================================
# STATE MANAGEMENT (for testing/reset)
# ============================================================================

def reset_all_state() -> None:
    """Reset all in-memory state (useful for testing)."""
    _recent_channel_context.clear()
    _conversation_history.clear()
    _pilot_mood.clear()
    _pilot_mood.update({
        "Shinji Ikari": 0.5,
        "Asuka Langley Soryu": 0.6,
        "Rei Ayanami": 0.4,
    })
    _user_interaction_count.clear()
    _channel_sentiment_history.clear()
    _spontaneous_cooldown.clear()
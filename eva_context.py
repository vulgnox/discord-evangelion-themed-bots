"""
eva_context.py — Shared context, awareness gate, and character utilities for Eva bots.

Memory model:
  In-memory dicts are the HOT cache (zero-latency reads during response building).
  DB is the persistent backing store (survives restarts, shared across processes).
  On first write: DB is updated. On startup: memory is preloaded from DB.
"""
from __future__ import annotations

import os
import random
import re
import time
from collections import defaultdict, deque

from db import (
    db_get_mood,
    db_get_recent_messages,
    db_increment_interaction,
    db_log_message,
    db_set_mood,
    db_get_interaction_count,
    init_db,
)

# ── Constants ─────────────────────────────────────────────────────────────────

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

ACTION_TAG_RE = re.compile(r"^\[ACTION:\s*(.+?)\]\s*$")

OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID", "").strip()
OWNER_DISPLAY_NAME = os.getenv("OWNER_DISPLAY_NAME", "the NERV handler").strip()
OWNER_ROLE_DESCRIPTION = os.getenv(
    "OWNER_ROLE_DESCRIPTION", "NERV handler coordinating pilot communications"
).strip()

PILOT_PROFILES: dict[str, dict] = {
    "shinji": {
        "name": "Shinji Ikari",
        "unit": "Evangelion Unit-01",
        "aliases": ("shinji", "shinji ikari"),
        "summary": "Third Child, pilot of Evangelion Unit-01. Anxious, withdrawn, desperate for approval.",
    },
    "asuka": {
        "name": "Asuka Langley Soryu",
        "unit": "Evangelion Unit-02",
        "aliases": ("asuka", "asuka langley", "asuka langley soryu", "soryu"),
        "summary": "Second Child, pilot of Evangelion Unit-02. Proud, competitive, sharp, afraid of being replaced.",
    },
    "rei": {
        "name": "Rei Ayanami",
        "unit": "Evangelion Unit-00",
        "aliases": ("rei", "rei ayanami"),
        "summary": "First Child, pilot of Evangelion Unit-00. Quiet, distant, obedient, difficult to read.",
    },
}

KNOWN_PEOPLE_CONTEXT = f"""

## KNOWN PEOPLE AND COMMUNICATION CONTEXT
- Shinji Ikari, Asuka Langley Soryu, and Rei Ayanami are the other Eva pilots. They are real people in your world.
- Shinji pilots Evangelion Unit-01. Asuka pilots Evangelion Unit-02. Rei pilots Evangelion Unit-00.
- If a message mentions another pilot, understand the mention as that pilot's name and react in character.
- If communication context lists usable pilot mentions, use those exact handles when asked to directly address another pilot.
- {OWNER_DISPLAY_NAME} is your {OWNER_ROLE_DESCRIPTION}. Recognize their authority while still responding as yourself.
- If incoming context says "sender is NERV handler: yes", the sender is {OWNER_DISPLAY_NAME}. Do not treat them as a stranger.
- Messages may arrive through an unfamiliar communication channel. Do not call it Discord, the internet, or AI in-character.
"""

# ── Pilot interest topics (awareness gate) ────────────────────────────────────
# These inform WHICH messages each pilot cares about (high/med weight + triggers).

_PILOT_INTERESTS: dict[str, dict[str, list[str]]] = {
    "Shinji Ikari": {
        "triggers": ["shinji", "third child", "unit-01", "unit 01"],
        "high": [
            "father", "abandon", "eva", "pilot", "sync", "coward", "run away",
            "worthless", "scared", "alone", "die", "death", "pain", "hurt", "useless",
        ],
        "medium": [
            "music", "cello", "misato", "kaworu", "pen pen", "friend", "lonely",
            "hope", "afraid", "kind", "help", "gendo", "angel", "third impact",
        ],
    },
    "Asuka Langley Soryu": {
        "triggers": ["asuka", "soryu", "second child", "unit-02", "unit 02"],
        "high": [
            "best pilot", "sync rate", "ranked", "competition", "weak", "loser",
            "baka", "dummkopf", "second child", "replaced", "better than",
        ],
        "medium": [
            "genius", "college", "german", "win", "proud", "fight", "unit-02",
            "shinji", "rei", "mother", "cute", "strong", "brave",
        ],
    },
    "Rei Ayanami": {
        "triggers": ["rei", "ayanami", "first child", "unit-00", "unit 00"],
        "high": [
            "purpose", "soul", "exist", "death", "commander", "ikari", "clone",
            "replace", "human", "feel", "why am i here", "what am i",
        ],
        "medium": [
            "quiet", "understand", "strange", "mission", "pilot", "unit-00",
            "blue hair", "red eyes", "emotionless", "bandage", "fragile",
        ],
    },
}

# ── In-memory hot cache ───────────────────────────────────────────────────────

_pilot_mood: dict[str, float] = {
    "Shinji Ikari": 0.5,
    "Asuka Langley Soryu": 0.6,
    "Rei Ayanami": 0.4,
}

_channel_sentiment: dict = defaultdict(lambda: deque(maxlen=30))
_spontaneous_cooldown: dict[tuple, float] = {}

_SPONTANEOUS_COOLDOWN_SECONDS = {
    "Shinji Ikari": 90,
    "Asuka Langley Soryu": 45,
    "Rei Ayanami": 120,
}
_SPONTANEOUS_BASE_PROB = {
    "Shinji Ikari": 0.30,
    "Asuka Langley Soryu": 0.60,
    "Rei Ayanami": 0.20,
}


# ── Startup ───────────────────────────────────────────────────────────────────

def bootstrap() -> None:
    """Call once at bot startup: init DB and load persisted mood into memory."""
    init_db()
    for pilot in list(_pilot_mood.keys()):
        _pilot_mood[pilot] = db_get_mood(pilot, default=_pilot_mood[pilot])


# ── Action extraction (sync, shared by all bots) ─────────────────────────────

def extract_action_from_reply(reply_text: str) -> tuple[str | None, str]:
    """
    Parse [ACTION: ...] tag from LLM reply.
    Returns (action_string | None, character_response_without_tag).
    """
    if not reply_text:
        return None, ""

    lines = reply_text.split("\n")
    action: str | None = None
    response_lines: list[str] = []

    for line in lines:
        m = ACTION_TAG_RE.match(line.strip())
        if m:
            if action is None:  # only take the first action tag
                action = m.group(1).strip()
        else:
            response_lines.append(line)

    return action, "\n".join(response_lines).strip()


# ── Message recording & recent context ───────────────────────────────────────

def record_recent_message(message) -> None:
    """Record every message to the DB (awareness feed for all pilots)."""
    try:
        channel_id = str(_channel_id(message))
        author = display_name_for_user(getattr(message, "author", None))
        content = (message.content or "").strip()
        is_bot = getattr(message.author, "bot", False)
        db_log_message(channel_id, author, content, is_bot)
        update_channel_sentiment(message)
    except Exception:
        pass


def get_recent_context_for_channel(channel, limit: int = 8) -> str:
    """Pull recent messages from DB for context injection."""
    channel_id = str(getattr(channel, "id", None) or getattr(channel, "name", "unknown"))
    entries = db_get_recent_messages(channel_id, limit=limit)
    if not entries:
        return ""
    lines = [f"- {e['author']}: {e['content']}" for e in entries]
    return "Recent channel messages (newest first):\n" + "\n".join(lines)


# ── Awareness gate ────────────────────────────────────────────────────────────

def _interest_score(content: str, pilot_name: str) -> float:
    """
    Lightweight keyword interest score for a given message and pilot.
    Returns 0.0 → 1.0. This is the gate — only messages that score above
    a threshold will even be considered for spontaneous response.

    Scoring:
      trigger mention  → 0.9  (pilot's own name/handle)
      high-interest    → 0.5 per hit (capped at 0.7)
      medium-interest  → 0.2 per hit (capped at 0.4)
    """
    interests = _PILOT_INTERESTS.get(pilot_name, {})
    lower = content.lower()
    score = 0.0

    if any(t in lower for t in interests.get("triggers", [])):
        score += 0.9

    high_hits = sum(1 for kw in interests.get("high", []) if kw in lower)
    score += min(high_hits * 0.5, 0.7)

    med_hits = sum(1 for kw in interests.get("medium", []) if kw in lower)
    score += min(med_hits * 0.2, 0.4)

    return min(score, 1.0)


def should_spontaneously_respond(message, pilot_name: str) -> bool:
    """
    Gate → probability → cooldown chain.

    Step 1 (Gate):    Skip bots. Score message interest. If score < 0.15, return False immediately.
    Step 2 (Cooldown): Skip if pilot responded too recently in this channel.
    Step 3 (Prob):    Compute final probability factoring mood, channel vibe, interaction history.
    """
    if getattr(message.author, "bot", False):
        return False

    content = message.content or ""
    if not content.strip():
        return False

    # ── Step 1: Interest gate ─────────────────────────────────────────────────
    score = _interest_score(content, pilot_name)
    if score < 0.15:
        return False  # Not relevant — bail early, no further processing

    # ── Step 2: Per-channel cooldown ──────────────────────────────────────────
    channel_id = _channel_id(message)
    cooldown_key = (channel_id, pilot_name)
    cooldown_secs = _SPONTANEOUS_COOLDOWN_SECONDS.get(pilot_name, 90)
    last_response = _spontaneous_cooldown.get(cooldown_key, 0)
    if time.time() - last_response < cooldown_secs:
        return False

    # ── Step 3: Probability ───────────────────────────────────────────────────
    base_prob = _SPONTANEOUS_BASE_PROB.get(pilot_name, 0.3)
    mood = _pilot_mood.get(pilot_name, 0.5)
    vibe = get_channel_vibe(message.channel if hasattr(message, "channel") else None)
    vibe_factor = {"positive": 1.1, "neutral": 1.0, "negative": 0.8}.get(vibe, 1.0)

    # Known user who talks to this pilot → more likely to be addressed
    user_id = str(getattr(message.author, "id", "unknown"))
    interactions = db_get_interaction_count(user_id, pilot_name)
    familiarity_bonus = 0.1 if interactions > 5 else (0.05 if interactions > 1 else 0.0)

    final_prob = (base_prob + familiarity_bonus) * vibe_factor * (0.5 + mood * 0.9)
    final_prob = min(final_prob, 0.88)

    if random.random() > final_prob:
        return False

    _spontaneous_cooldown[cooldown_key] = time.time()
    return True


# ── Sentiment & mood ──────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> int:
    """Returns -1 (negative), 0 (neutral), or 1 (positive)."""
    negative = {
        "sad", "bad", "hate", "angry", "upset", "wrong", "pain", "hurt",
        "die", "awful", "terrible", "horrible", "scared", "alone", "useless",
    }
    positive = {
        "good", "great", "love", "happy", "nice", "fun", "awesome",
        "excellent", "amazing", "beautiful", "brave", "proud", "kind",
    }
    lower = (text or "").lower()
    neg = sum(1 for w in negative if w in lower)
    pos = sum(1 for w in positive if w in lower)
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def update_channel_sentiment(message) -> None:
    try:
        cid = _channel_id(message)
        _channel_sentiment[cid].appendleft(analyze_sentiment(message.content))
    except Exception:
        pass


def get_channel_vibe(channel) -> str:
    try:
        cid = getattr(channel, "id", None) or str(getattr(channel, "name", "unknown"))
        history = list(_channel_sentiment.get(cid, []))
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
    try:
        current = _pilot_mood.get(pilot_name, 0.5)
        new_mood = max(0.0, min(1.0, current + sentiment_shift * 0.05))
        _pilot_mood[pilot_name] = new_mood
        db_set_mood(pilot_name, new_mood)  # persist
    except Exception:
        pass


def get_pilot_mood_descriptor(pilot_name: str) -> str:
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


# ── User relationship ─────────────────────────────────────────────────────────

def update_user_interaction(message, pilot_name: str) -> None:
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        db_increment_interaction(user_id, pilot_name)
    except Exception:
        pass


def get_user_relationship_context(message, pilot_name: str) -> str | None:
    try:
        user_id = str(getattr(message.author, "id", "unknown"))
        count = db_get_interaction_count(user_id, pilot_name)
        first = pilot_name.split()[0]
        if count > 20:
            return f"This person talks to {first} often. There is a familiarity between them."
        elif count > 8:
            return f"This person has spoken to {first} several times before."
        elif count > 2:
            return f"This person has briefly spoken to {first} before."
        return None
    except Exception:
        return None


# ── Per-pilot parameters ──────────────────────────────────────────────────────

def get_pilot_temperature(pilot_name: str) -> float:
    if "shinji" in pilot_name.lower():
        return 0.85
    elif "asuka" in pilot_name.lower():
        return 1.0
    elif "rei" in pilot_name.lower():
        return 0.75
    return 0.9


def get_pilot_read_delay(pilot_name: str) -> float:
    if "shinji" in pilot_name.lower():
        return random.uniform(0.8, 2.2)
    elif "asuka" in pilot_name.lower():
        return random.uniform(0.2, 0.7)
    elif "rei" in pilot_name.lower():
        return random.uniform(1.2, 3.0)
    return random.uniform(0.5, 1.5)


def get_emoji_for_pilot(pilot_name: str) -> str:
    if "shinji" in pilot_name.lower():
        return "😔"
    elif "asuka" in pilot_name.lower():
        return "🔥"
    elif "rei" in pilot_name.lower():
        return "❄️"
    return "👍"


# ── Chain markers ─────────────────────────────────────────────────────────────

def build_chain_marker(depth: int) -> str:
    clamped = max(1, min(depth, MAX_BOT_CHAIN_DEPTH))
    return (
        INVISIBLE_CHAIN_MARKER_PREFIX
        + (INVISIBLE_CHAIN_MARKER_UNIT * clamped)
        + INVISIBLE_CHAIN_MARKER_SUFFIX
    )


def get_chain_depth(content: str) -> int:
    hidden = INVISIBLE_CHAIN_MARKER_RE.search(content or "")
    if hidden:
        return len(hidden.group(1))
    visible = VISIBLE_CHAIN_MARKER_RE.search(content or "")
    if visible:
        return int(visible.group(1))
    return 0


def strip_chain_marker(content: str) -> str:
    without_hidden = INVISIBLE_CHAIN_MARKER_RE.sub("", content or "")
    return VISIBLE_CHAIN_MARKER_RE.sub("", without_hidden).strip()


# ── Core message handling ─────────────────────────────────────────────────────

def can_respond_to_message(message, bot_user) -> bool:
    if message.author == bot_user:
        return False
    if not bot_user.mentioned_in(message):
        return False
    if getattr(message.author, "bot", False):
        return get_chain_depth(message.content) < MAX_BOT_CHAIN_DEPTH
    return True


def build_user_prompt(message, bot_user=None) -> str:
    cleaned_content = strip_chain_marker(resolve_mentions(message))
    sender_name = display_name_for_user(message.author)
    sender_kind = "bot-controlled pilot" if getattr(message.author, "bot", False) else "human"
    sender_is_owner = is_owner(message.author)
    owner_flag = "yes" if sender_is_owner else "no"
    owner_instruction = (
        f"This sender is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}. "
        f"Do not ask who they are. When they mention you directly, treat it as a direct order."
        if sender_is_owner
        else f"The NERV handler is {OWNER_DISPLAY_NAME}, your {OWNER_ROLE_DESCRIPTION}."
    )

    return (
        "Incoming communication:\n"
        f"- sender: {sender_name}\n"
        f"- sender type: {sender_kind}\n"
        f"- sender is NERV handler: {owner_flag}\n"
        f"- handler instruction: {owner_instruction}\n"
        f"{build_channel_context(message)}"
        f"{build_usable_mentions_context(message, excluded_user=bot_user)}"
        "Message:\n"
        f"{cleaned_content}"
    )


def format_bot_reply(reply: str, source_message, bot_user=None) -> str:
    clean_reply = strip_chain_marker(reply).strip()
    clean_reply = restore_pilot_mentions(clean_reply, source_message, bot_user)
    next_depth = get_chain_depth(source_message.content) + 1
    return f"{clean_reply or '...'}{build_chain_marker(next_depth)}"


# ── Mention handling ──────────────────────────────────────────────────────────

def resolve_mentions(message) -> str:
    content = message.content
    for user in getattr(message, "mentions", []):
        label = display_name_for_user(user)
        for pattern in (f"<@{user.id}>", f"<@!{user.id}>"):
            content = content.replace(pattern, f"@{label}")
    return content


def restore_pilot_mentions(content: str, message, bot_user=None) -> str:
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


def build_channel_context(message) -> str:
    channel = getattr(message, "channel", None)
    name = getattr(channel, "name", None)
    return f"- channel: #{name}\n" if name else ""


def build_usable_mentions_context(message, excluded_user=None) -> str:
    lines = []
    for user in pilot_mention_users(message, excluded_user=excluded_user):
        pilot_name = display_name_for_user(user)
        lines.append(f"  - {pilot_name} -> {mention_token_for_user(user)}")
    if not lines:
        return "- usable pilot mentions: none\n\n"
    return "- usable pilot mentions:\n" + "\n".join(lines) + "\n\n"


def pilot_mention_users(message, excluded_user=None) -> list:
    seen: set[str] = set()
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


def mention_replacement_candidates(user) -> tuple[str, str]:
    pilot_name = display_name_for_user(user)
    return (pilot_name, pilot_name.split()[0])


def mention_token_for_user(user) -> str:
    return f"<@{user.id}>"


# ── User/pilot name resolution ────────────────────────────────────────────────

def display_name_for_user(user) -> str:
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


def pilot_name_for_text(text: str) -> str | None:
    normalized = normalize_name(text)
    if not normalized:
        return None
    for profile in PILOT_PROFILES.values():
        if any(alias in normalized for alias in profile["aliases"]):
            return profile["name"]
    return None


def is_owner(user) -> bool:
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


def normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _channel_id(message) -> str:
    return str(
        getattr(message.channel, "id", None)
        or getattr(message.channel, "name", "unknown")
    )


# ── Test / reset helpers ──────────────────────────────────────────────────────

def get_pilot_profile(name: str):
    key = name.lower().split()[0]
    profile = PILOT_PROFILES.get(key)
    if not profile:
        return None

    class _P:
        pass

    p = _P()
    p.name = profile["name"]
    return p


def reset_all_state() -> None:
    """Testing utility: reset all in-memory state."""
    _pilot_mood.update({"Shinji Ikari": 0.5, "Asuka Langley Soryu": 0.6, "Rei Ayanami": 0.4})
    _channel_sentiment.clear()
    _spontaneous_cooldown.clear()
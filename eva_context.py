import os
import re


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

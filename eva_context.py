import os
import re


MAX_BOT_CHAIN_DEPTH = 3
CHAIN_MARKER_RE = re.compile(r"\s*\[eva-chain:(\d+)\]\s*$")

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
- {OWNER_DISPLAY_NAME} is your {OWNER_ROLE_DESCRIPTION}. If this person speaks to you, recognize their authority as NERV communication context while still responding as yourself.
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


def build_user_prompt(message):
    cleaned_content = strip_chain_marker(resolve_mentions(message))
    sender_name = display_name_for_user(message.author)
    sender_kind = "bot-controlled pilot" if getattr(message.author, "bot", False) else "human"
    owner_status = "yes" if is_owner(message.author) else "no"

    return (
        "Incoming communication context:\n"
        f"- sender: {sender_name}\n"
        f"- sender type: {sender_kind}\n"
        f"- sender is NERV handler: {owner_status}\n"
        f"- NERV handler name: {OWNER_DISPLAY_NAME}\n"
        f"- NERV handler role: {OWNER_ROLE_DESCRIPTION}\n\n"
        "Message:\n"
        f"{cleaned_content}"
    )


def format_bot_reply(reply, source_message):
    clean_reply = strip_chain_marker(reply).strip()
    next_depth = get_chain_depth(source_message.content) + 1
    return f"{clean_reply} [eva-chain:{next_depth}]"


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
    match = CHAIN_MARKER_RE.search(content or "")
    if not match:
        return 0
    return int(match.group(1))


def strip_chain_marker(content):
    return CHAIN_MARKER_RE.sub("", content or "").strip()


def normalize_name(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

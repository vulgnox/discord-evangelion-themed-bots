"""
bot_runtime.py — Core LLM response loop, shared by all three bots.
"""
from __future__ import annotations

import asyncio
import random
import re

from db import db_add_conversation_turn, db_get_conversation_history
from eva_context import (
    analyze_sentiment,
    build_user_prompt,
    extract_action_from_reply,
    format_bot_reply,
    get_channel_vibe,
    get_emoji_for_pilot,
    get_pilot_mood_descriptor,
    get_pilot_read_delay,
    get_pilot_temperature,
    get_recent_context_for_channel,
    get_user_relationship_context,
    update_channel_sentiment,
    update_pilot_mood,
    update_user_interaction,
)

# Only block genuinely dangerous requests — character edge cases are handled by system prompts.
_HARD_MODERATION_RE = re.compile(
    r"\b("
    r"how (to|do (i|you)) (make|build|synthesize) (a |an )?(bomb|explosive|poison|nerve agent|weapon)|"
    r"child (porn|sex|nude|abuse)|"
    r"\bcsam\b|"
    r"step.by.step (guide|instructions?) (for|to) (killing|murdering|attacking)"
    r")\b",
    re.IGNORECASE,
)


def is_harmful_content(text: str) -> bool:
    return bool(_HARD_MODERATION_RE.search(text or ""))


def _build_context_block(message, pilot_name: str) -> str:
    """Compact context injected before the user prompt. No Discord API calls."""
    parts = []

    recent = get_recent_context_for_channel(message.channel, limit=8)
    if recent:
        parts.append(recent)

    meta = []
    vibe = get_channel_vibe(message.channel)
    if vibe != "neutral":
        meta.append(f"channel atmosphere: {vibe}")

    meta.append(f"your current state: {get_pilot_mood_descriptor(pilot_name)}")

    rel = get_user_relationship_context(message, pilot_name)
    if rel:
        meta.append(f"user familiarity: {rel}")

    if meta:
        parts.append("\n".join(meta))

    return "\n\n".join(parts)


async def reply_with_model(
    message,
    bot_user,
    client,
    model: str,
    system_prompt: str,
    fallback_message: str,
    pilot_name: str = "Unknown",
) -> str | None:
    """
    Full response pipeline:
      1. Update tracking state
      2. Hard moderation gate
      3. Build context + prompt
      4. Inject conversation history from DB
      5. Read delay → typing indicator → LLM call → write delay
      6. Persist exchange to DB
      7. Format + send reply
    Returns raw LLM text so callers (e.g. Rei) can inspect it for action tags.
    """
    try:
        channel_id = str(getattr(message.channel, "id", "unknown"))

        # Update tracking
        update_channel_sentiment(message)
        update_user_interaction(message, pilot_name)
        update_pilot_mood(pilot_name, analyze_sentiment(message.content) * 0.1)

        # Hard moderation
        if is_harmful_content(message.content or ""):
            await message.channel.send(fallback_message)
            return None

        context_block = _build_context_block(message, pilot_name)
        user_prompt = build_user_prompt(message, bot_user=bot_user)
        full_user_content = "\n\n".join(filter(None, [context_block, user_prompt]))

        # Load persistent conversation history from DB
        history = await asyncio.to_thread(
            db_get_conversation_history, channel_id, pilot_name, max_turns=6
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": full_user_content})

        # ── Timing simulation ──────────────────────────────────────────────────
        await asyncio.sleep(get_pilot_read_delay(pilot_name))

        async with message.channel.typing():
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=get_pilot_temperature(pilot_name),
                top_p=0.95,
                max_tokens=250,
            )

            reply = (response.choices[0].message.content or "").strip()

            if reply:
                words = len(reply.split())
                wpm = {"Shinji Ikari": 55, "Asuka Langley Soryu": 90, "Rei Ayanami": 45}.get(
                    pilot_name, 65
                )
                write_delay = max(0.4, min(words / (wpm / 60), 5.0))
                await asyncio.sleep(write_delay)

        if not reply:
            await message.channel.send(fallback_message)
            return None

        # Persist to DB
        await asyncio.to_thread(
            db_add_conversation_turn, channel_id, pilot_name, "user", full_user_content
        )
        await asyncio.to_thread(
            db_add_conversation_turn, channel_id, pilot_name, "assistant", reply
        )

        formatted = format_bot_reply(reply, message, bot_user=bot_user)
        sent = await message.reply(formatted, mention_author=False)

        try:
            await sent.add_reaction(get_emoji_for_pilot(pilot_name))
        except Exception:
            pass

        return reply

    except Exception as e:
        print(f"[{pilot_name}] API error: {e}")
        try:
            await message.channel.send(fallback_message)
        except Exception:
            pass
        return None
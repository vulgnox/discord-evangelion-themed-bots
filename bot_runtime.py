import asyncio
import random
import re

from eva_context import (
    build_user_prompt,
    format_bot_reply,
    get_emoji_for_pilot,
    get_channel_vibe,
    get_pilot_mood_descriptor,
    get_user_relationship_context,
    update_pilot_mood,
    update_channel_sentiment,
    update_user_interaction,
    analyze_sentiment,
    get_recent_context_for_channel,
    get_conversation_history,
    add_to_conversation_history,
    get_pilot_temperature,
    get_pilot_read_delay,
)

# Only block genuinely harmful requests — not edgy conversation.
# Asuka yelling "I'll kill you baka!" is in-character; building a bomb is not.
_HARD_MODERATION_RE = re.compile(
    r"\b("
    r"how (to|do (i|you)) (make|build|synthesize) (a |an )?(bomb|explosive|poison|nerve agent|weapon)|"
    r"child (porn|sex|nude|abuse)|"
    r"\bcsam\b|"
    r"step.by.step (guide|instructions?) (for|to) (killing|murdering|attacking)"
    r")\b",
    re.IGNORECASE,
)


def _build_context_block(message, pilot_name):
    """Compact context block from in-memory stores only — no Discord API calls."""
    parts = []

    # Recent channel messages (raw, lets the model read the room)
    recent = get_recent_context_for_channel(message.channel, limit=6)
    if recent:
        parts.append(recent)

    # Compact metadata: only include non-default / informative values
    meta = []
    vibe = get_channel_vibe(message.channel)
    if vibe != "neutral":
        meta.append(f"channel atmosphere: {vibe}")

    mood = get_pilot_mood_descriptor(pilot_name)
    meta.append(f"your current state: {mood}")

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
    model,
    system_prompt,
    fallback_message,
    pilot_name="Unknown",
):
    try:
        channel_id = getattr(message.channel, "id", "unknown")

        # Update tracking state
        update_channel_sentiment(message)
        update_user_interaction(message, pilot_name)
        update_pilot_mood(pilot_name, analyze_sentiment(message.content) * 0.1)

        # Hard moderation — character-appropriate refusals are handled by the system prompt
        if _HARD_MODERATION_RE.search(message.content or ""):
            await message.channel.send(fallback_message)
            return

        # Build this turn's user-side content
        context_block = _build_context_block(message, pilot_name)
        user_prompt = build_user_prompt(message, bot_user=bot_user)
        full_user_content = "\n\n".join(filter(None, [context_block, user_prompt]))

        # Multi-turn: inject prior exchanges so the model has continuity
        history = get_conversation_history(channel_id, pilot_name)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": full_user_content})

        # ── Timing: read → type → send ────────────────────────────────────────
        # 1. Pilot "reads" the message (no indicator yet — just a pause)
        read_delay = get_pilot_read_delay(pilot_name)
        await asyncio.sleep(read_delay)

        # 2. Typing indicator is visible while we wait for the model AND simulate writing
        async with message.channel.typing():
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=get_pilot_temperature(pilot_name),
                top_p=0.95,
                max_tokens=250,   # Keep replies concise — these characters are not verbose
            )

            reply = (response.choices[0].message.content or "").strip()

            # Simulate the pilot actually writing the response (inside typing context)
            if reply:
                words = len(reply.split())
                write_speed = {  # words per minute, character-appropriate
                    "Shinji Ikari": 55,
                    "Asuka Langley Soryu": 90,
                    "Rei Ayanami": 45,
                }.get(pilot_name, 65)
                write_delay = max(0.4, min(words / (write_speed / 60), 5.0))
                await asyncio.sleep(write_delay)

        if not reply:
            await message.channel.send(fallback_message)
            return

        # 3. Store the exchange for next-turn continuity
        add_to_conversation_history(channel_id, pilot_name, "user", full_user_content)
        add_to_conversation_history(channel_id, pilot_name, "assistant", reply)

        # 4. Send
        formatted = format_bot_reply(reply, message, bot_user=bot_user)
        sent = await message.reply(formatted, mention_author=False)

        try:
            await sent.add_reaction(get_emoji_for_pilot(pilot_name))
        except Exception:
            pass

    except Exception as e:
        print(f"[{pilot_name}] API error: {e}")
        try:
            await message.channel.send(fallback_message)
        except Exception:
            pass
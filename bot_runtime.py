import asyncio
import time

from eva_context import (
    build_user_prompt,
    format_bot_reply,
    display_name_for_user,
    get_emoji_for_pilot,
    get_channel_vibe,
    get_pilot_mood_descriptor,
    get_user_relationship_context,
    update_pilot_mood,
    update_channel_sentiment,
    update_user_interaction,
    analyze_sentiment,
)
import re


async def _build_recent_context(message, pilot_name, limit=20):
    """Build rich context including recent messages, channel vibe, relationships, and emotional state.

    Returns a comprehensive text block for the model to understand the full situation.
    """
    try:
        entries = []
        message_count = 0
        
        # Gather more messages for deeper context
        async for m in message.channel.history(limit=limit, oldest_first=False):
            content = (m.content or "").replace("\n", " ").strip()
            if not content:
                continue
            author = display_name_for_user(getattr(m, "author", None))
            entries.append(f"- {author}: {content}")
            message_count += 1
            if message_count >= limit:
                break

        context_lines = []
        
        # Add recent conversation
        if entries:
            context_lines.append("Recent channel conversation (most recent first):")
            context_lines.extend(entries)
            context_lines.append("")
        
        # Add channel vibe analysis
        vibe = get_channel_vibe(message.channel)
        context_lines.append(f"Channel vibe: {vibe} (affects tone and engagement level)")
        
        # Add pilot mood
        mood = get_pilot_mood_descriptor(pilot_name)
        context_lines.append(f"Your current state: {mood}")
        
        # Add relationship context
        rel = get_user_relationship_context(message, pilot_name)
        if rel:
            context_lines.append(f"User context: {rel}")
        
        context_lines.append("")
        return "\n".join(context_lines)
    except Exception as e:
        print(f"Context building error: {e}")
        return ""


async def _calculate_typing_delay(response_length):
    """Simulate realistic typing delay based on response length."""
    # Rough estimate: ~40-60 words per minute typing speed
    words = len(response_length.split())
    base_delay = max(0.5, words / 50)  # At least 0.5 seconds
    return base_delay


async def reply_with_model(message, bot_user, client, model, system_prompt, fallback_message, pilot_name="Unknown"):
    try:
        # Track user interaction and channel sentiment
        update_channel_sentiment(message)
        update_user_interaction(message, pilot_name)
        sentiment = analyze_sentiment(message.content)
        update_pilot_mood(pilot_name, sentiment * 0.1)  # Small mood shift based on message tone
        
        # Build rich context including channel vibe, relationships, mood
        rich_context = await _build_recent_context(message, pilot_name)
        user_prompt = build_user_prompt(message, bot_user=bot_user)
        full_user_content = "\n\n".join([p for p in (rich_context, user_prompt) if p])

        # Lightweight moderation safeguard
        moderation_re = re.compile(r"\b(rape|sexual|incest|suicide|kill|bomb|gun)\b", re.I)
        if moderation_re.search(message.content or ""):
            await message.channel.send(fallback_message)
            return

        # Show "is typing" indicator with realistic delay
        async with message.channel.typing():
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_user_content},
                ],
                temperature=1.0,  # Use full randomness for more natural variation
                top_p=0.95,       # Slightly more controlled than pure temperature
            )

        reply = response.choices[0].message.content
        
        # Simulate realistic typing delay based on response length
        delay = await _calculate_typing_delay(reply)
        await asyncio.sleep(delay * 0.5)  # Scale down a bit so it's not too slow
        
        formatted = format_bot_reply(reply, message, bot_user=bot_user)
        sent_message = await message.reply(formatted, mention_author=False)
        
        # Add character-appropriate emoji reaction
        try:
            emoji = get_emoji_for_pilot(pilot_name)
            await sent_message.add_reaction(emoji)
        except Exception:
            pass
            
    except Exception as e:
        print(f"Error calling NVIDIA API: {e}")
        try:
            await message.channel.send(fallback_message)
        except Exception:
            pass

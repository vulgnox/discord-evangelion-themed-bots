import asyncio

from eva_context import build_user_prompt, format_bot_reply, display_name_for_user
import re


async def _build_recent_context(message, limit=8):
    """Gather a short, recent snapshot of channel messages for model context.

    Returns a small text block (newest-first) or empty string on failure.
    """
    try:
        entries = []
        async for m in message.channel.history(limit=limit, oldest_first=False):
            # include recent messages, skip empty content
            content = (m.content or "").replace("\n", " ")
            if not content:
                continue
            # display_name_for_user handles pilot name mapping and fallbacks
            author = display_name_for_user(getattr(m, "author", None))
            entries.append(f"- {author}: {content}")

        if not entries:
            return ""

        return "Recent channel messages (newest first):\n" + "\n".join(entries)
    except Exception:
        return ""


async def reply_with_model(message, bot_user, client, model, system_prompt, fallback_message):
    try:
        # Build an augmented user prompt including a short recent history
        recent_context = await _build_recent_context(message)
        user_prompt = build_user_prompt(message, bot_user=bot_user)
        full_user_content = "\n\n".join([p for p in (recent_context, user_prompt) if p])

        # Lightweight moderation safeguard (non-exhaustive). If triggered, refuse gracefully.
        # This is separate from the character system prompt and does not alter it.
        moderation_re = re.compile(r"\b(rape|sexual|incest|suicide|kill|bomb|gun)\b", re.I)
        if moderation_re.search(message.content or ""):
            await message.channel.send(fallback_message)
            return

        async with message.channel.typing():
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_user_content},
                ],
            )

        reply = response.choices[0].message.content

        # Try to create a thread and send the reply there for clearer conversation flow.
        thread = None
        try:
            thread = await message.create_thread(name=f"Thread: {message.author.display_name}", auto_archive_duration=60)
        except Exception:
            # some channels or permissions disallow creating threads; ignore and fallback
            thread = None

        formatted = format_bot_reply(reply, message, bot_user=bot_user)
        if thread:
            await thread.send(formatted)
        else:
            await message.reply(formatted, mention_author=False)
    except Exception as e:
        print(f"Error calling NVIDIA API: {e}")
        try:
            await message.channel.send(fallback_message)
        except Exception:
            pass

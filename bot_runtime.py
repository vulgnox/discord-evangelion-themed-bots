"""
Bot Runtime Module - Handles LLM API calls, message processing, and response formatting.

This module provides:
- Async wrapper for OpenAI API calls with retry logic
- Timing simulation (read delay, typing delay)
- Hard moderation filtering
- Context block building
- Conversation history management
- Action extraction for Rei bot
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)

# ============================================================================
# MODERATION
# ============================================================================

# Hard moderation regex - blocks only genuinely harmful requests
# Character-appropriate edgy conversation is allowed
_HARD_MODERATION_PATTERNS = [
    # Bomb/explosive/poison creation
    re.compile(
        r"\bhow\s+(?:to|do\s+(?:i|you))\s+(?:make|build|synthesize|create)\s+(?:a\s+|an\s+)?"
        r"(?:bomb|explosive|poison|nerve\s+agent|weapon|IED|device)\b",
        re.IGNORECASE
    ),
    # Child sexual abuse material
    re.compile(r"\b(?:child\s+)?(?:porn|sex|nude|abuse)|csam\b", re.IGNORECASE),
    # Step-by-step harm instructions
    re.compile(
        r"(?:step\s+by\s+step|instructions?)\s+(?:for|to)\s+(?:killing|murdering|attacking)\b",
        re.IGNORECASE
    ),
]


def is_harmful_content(text: str) -> bool:
    """Check if content matches hard moderation patterns."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _HARD_MODERATION_PATTERNS)


# ============================================================================
# CONTEXT BUILDING
# ============================================================================

def build_context_block(message: Any, pilot_name: str) -> str:
    """
    Build compact context block from in-memory stores only.
    
    Does NOT make Discord API calls - uses only in-memory state.
    """
    parts = []
    
    # Recent channel messages (raw, lets the model read the room)
    if hasattr(message, 'channel'):
        from eva_context import get_recent_context_for_channel
        recent = get_recent_context_for_channel(message.channel, limit=6)
        if recent:
            parts.append(recent)
    
    # Compact metadata: only include non-default/informative values
    meta = []
    
    # Channel vibe
    if hasattr(message, 'channel'):
        from eva_context import get_channel_vibe
        vibe = get_channel_vibe(message.channel)
        if vibe != "neutral":
            meta.append(f"channel atmosphere: {vibe}")
    
    # Pilot mood
    from eva_context import get_pilot_mood_descriptor
    mood = get_pilot_mood_descriptor(pilot_name)
    meta.append(f"your current state: {mood}")
    
    # User relationship
    if hasattr(message, 'author'):
        from eva_context import get_user_relationship_context
        rel = get_user_relationship_context(message, pilot_name)
        if rel:
            meta.append(f"user familiarity: {rel}")
    
    if meta:
        parts.append("\n".join(meta))
    
    return "\n\n".join(parts)


# ============================================================================
# API CALLS WITH RETRY
# ============================================================================

async def call_llm_with_retry(
    client: "OpenAI",
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    top_p: float = 0.95,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Optional[str]:
    """
    Call LLM API with exponential backoff retry logic.
    
    Returns:
        The response text, or None if all retries failed.
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Run sync API call in thread pool to avoid blocking
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            
            return response.choices[0].message.content or ""
            
        except Exception as e:
            last_error = e
            logger.warning(
                "[LLM] Attempt %d/%d failed: %s",
                attempt + 1, max_retries, str(e)
            )
            
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                delay = retry_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
    
    logger.error("[LLM] All %d retries exhausted. Last error: %s", max_retries, last_error)
    return None


# ============================================================================
# MAIN REPLY FUNCTION
# ============================================================================

async def reply_with_model(
    message: Any,
    bot_user: Any,
    client: "OpenAI",
    model: str,
    system_prompt: str,
    fallback_message: str,
    pilot_name: str = "Unknown",
    max_tokens: int = 250,
    temperature: Optional[float] = None,
) -> Optional[str]:
    """
    Process a message and generate a response using the LLM.
    
    Args:
        message: Discord message object
        bot_user: The bot's user object
        client: OpenAI client instance
        model: Model name
        system_prompt: System prompt for the character
        fallback_message: Message to send on error
        pilot_name: Name of the pilot for timing/logging
        max_tokens: Max response tokens
        temperature: Override temperature (uses character default if None)
    
    Returns:
        The raw LLM reply text, or None on failure.
    """
    try:
        channel_id = getattr(message.channel, "id", "unknown")
        
        # Update tracking state
        from eva_context import (
            update_channel_sentiment,
            update_user_interaction,
            update_pilot_mood,
            analyze_sentiment,
            get_conversation_history,
            add_to_conversation_history,
            build_user_prompt,
        )
        
        update_channel_sentiment(message)
        update_user_interaction(message, pilot_name)
        
        sentiment = analyze_sentiment(message.content or "")
        update_pilot_mood(pilot_name, sentiment * 0.1)
        
        # Hard moderation check
        if is_harmful_content(message.content or ""):
            logger.info("[%s] Blocked harmful content from %s", pilot_name, message.author)
            await message.channel.send(fallback_message)
            return None
        
        # Build context and prompt
        context_block = build_context_block(message, pilot_name)
        user_prompt = build_user_prompt(message, bot_user=bot_user)
        full_user_content = "\n\n".join(filter(None, [context_block, user_prompt]))
        
        # Multi-turn: inject prior exchanges for continuity
        history = get_conversation_history(str(channel_id), pilot_name)
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": full_user_content})
        
        # ── Timing: read → type → send ─────────────────────────────────────
        
        # 1. Pilot "reads" the message (pause before typing indicator)
        from eva_context import get_pilot_read_delay, get_pilot_temperature, get_pilot_write_delay
        read_delay = get_pilot_read_delay(pilot_name)
        await asyncio.sleep(read_delay)
        
        # 2. Typing indicator while we wait for model + simulate writing
        async with message.channel.typing():
            # Get temperature (character default or override)
            effective_temp = temperature if temperature is not None else get_pilot_temperature(pilot_name)
            
            # Call LLM with retry
            reply = await call_llm_with_retry(
                client=client,
                model=model,
                messages=messages,
                temperature=effective_temp,
                max_tokens=max_tokens,
            )
            
            if not reply:
                await message.channel.send(fallback_message)
                return None
            
            # Simulate the pilot actually writing the response
            word_count = len(reply.split())
            write_delay = get_pilot_write_delay(pilot_name, word_count)
            await asyncio.sleep(write_delay)
        
        # 3. Store exchange for next-turn continuity
        add_to_conversation_history(str(channel_id), pilot_name, "user", full_user_content)
        add_to_conversation_history(str(channel_id), pilot_name, "assistant", reply)
        
        # 4. Format and send reply
        from eva_context import format_bot_reply, get_emoji_for_pilot
        formatted = format_bot_reply(reply, message, bot_user=bot_user)
        
        sent = await message.reply(formatted, mention_author=False)
        
        # Add emoji reaction
        try:
            emoji = get_emoji_for_pilot(pilot_name)
            await sent.add_reaction(emoji)
        except Exception as e:
            logger.debug("Failed to add reaction: %s", e)
        
        return reply  # Return raw reply so Rei can extract actions
        
    except Exception as e:
        logger.exception("[%s] Unexpected error: %s", pilot_name, e)
        try:
            await message.channel.send(fallback_message)
        except Exception:
            pass
        return None


# ============================================================================
# ACTION EXTRACTION (for Rei bot)
# ============================================================================

def extract_action_from_reply(reply_text: str) -> tuple[Optional[str], str]:
    """
    Extract [ACTION: ...] tag and character response from LLM reply.
    
    Args:
        reply_text: The full LLM response
        
    Returns:
        Tuple of (action_string, character_response)
    """
    if not reply_text:
        return None, ""
    
    lines = reply_text.split("\n")
    action_line = None
    response_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[ACTION:") and stripped.endswith("]"):
            action_line = stripped
        else:
            response_lines.append(line)
    
    action = None
    if action_line:
        # Extract content between [ACTION: and ]
        action = action_line[8:-1].strip()
    
    character_response = "\n".join(response_lines).strip()
    return action, character_response
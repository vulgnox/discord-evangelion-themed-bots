"""
Base Bot Module - Shared functionality for all Evangelion bots.

This module provides:
- BaseBot class with common Discord event handling
- Graceful shutdown handling
- Centralized logging setup
- Shared message processing logic
"""
from __future__ import annotations

import logging
import signal
import sys
from abc import ABC, abstractmethod
from typing import Optional

import discord
from dotenv import load_dotenv

load_dotenv()

from bot_runtime import reply_with_model, extract_action_from_reply
from eva_context import (
    KNOWN_PEOPLE_CONTEXT,
    can_respond_to_message,
    record_recent_message,
    should_spontaneously_respond,
    is_owner,
)

logger = logging.getLogger(__name__)


class BaseBot(ABC, discord.Client):
    """
    Abstract base class for Evangelion Discord bots.
    
    Subclasses must implement:
    - pilot_name: The character's full name
    - system_prompt: The character definition
    - fallback_message: Error message when API fails
    """
    
    # Class-level properties (override in subclass)
    pilot_name: str = "Unknown"
    system_prompt: str = ""
    fallback_message: str = "..."
    
    # Discord token env var name (override in subclass)
    token_env: str = ""
    
    def __init__(self):
        """Initialize the bot with intents and setup."""
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(intents=intents)
        
        # Setup graceful shutdown
        self._setup_signal_handlers()
        
        # Client for LLM API (initialized in on_ready)
        self._llm_client = None
        
        # Action handler (override in subclass if needed)
        self._action_handler = None
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def shutdown_handler(signum, frame):
            logger.info("Shutdown signal received, closing bot...")
            self.loop.run_until_complete(self.close())
            sys.exit(0)
        
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    
    @property
    def discord_token(self) -> str:
        """Get Discord token from environment."""
        import os
        token = os.getenv(self.token_env, "").strip()
        if not token:
            raise ValueError(f"{self.token_env} not found in environment variables")
        return token
    
    @property
    def nvidia_api_key(self) -> str:
        """Get NVIDIA API key from environment."""
        import os
        key = os.getenv("NVIDIA_API_KEY", "").strip()
        if not key:
            raise ValueError("NVIDIA_API_KEY not found in environment variables")
        return key
    
    @property
    def nvidia_model(self) -> str:
        """Get NVIDIA model from environment."""
        import os
        return os.getenv("NVIDIA_MODEL", "meta/llama2-70b")
    
    def _init_llm_client(self) -> None:
        """Initialize the OpenAI client for NVIDIA NIM API."""
        from openai import OpenAI
        self._llm_client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.nvidia_api_key,
        )
    
    # ── Discord Events ──────────────────────────────────────────────────────
    
    async def on_ready(self) -> None:
        """Called when bot has connected to Discord."""
        logger.info(
            "%s (%s) has connected to Discord!",
            self.user,
            self.pilot_name
        )
        self._init_llm_client()
    
    async def on_message(self, message: discord.Message) -> None:
        """Process incoming messages."""
        # Skip self and other bots
        if message.author == self.user:
            return
        
        # Record for context tracking
        try:
            record_recent_message(message)
        except Exception as e:
            logger.debug("Failed to record message: %s", e)
        
        # Check if we should respond
        if not can_respond_to_message(message, self.user):
            return
        
        is_owner_msg = is_owner(message.author)
        
        logger.info(
            "[%s] %s message from %s: %s",
            self.pilot_name,
            "owner" if is_owner_msg else "regular",
            message.author,
            message.content[:60]
        )
        
        # Generate response
        reply_text = await reply_with_model(
            message=message,
            bot_user=self.user,
            client=self._llm_client,
            model=self.nvidia_model,
            system_prompt=self.system_prompt,
            fallback_message=self.fallback_message,
            pilot_name=self.pilot_name,
        )
        
        # Handle actions if this bot supports them (Rei)
        if reply_text and self._action_handler:
            action, character_response = extract_action_from_reply(reply_text)
            if action:
                await self._execute_action(action, message, character_response)
        
        # Spontaneous responses
        elif should_spontaneously_respond(message, self.pilot_name):
            logger.info(
                "[%s] spontaneous response to %s: %s",
                self.pilot_name,
                message.author,
                message.content[:60]
            )
            await reply_with_model(
                message=message,
                bot_user=self.user,
                client=self._llm_client,
                model=self.nvidia_model,
                system_prompt=self.system_prompt,
                fallback_message=self.fallback_message,
                pilot_name=self.pilot_name,
            )
    
    async def _execute_action(self, action: str, message: discord.Message, response_text: str) -> None:
        """Execute an action extracted from LLM response."""
        if self._action_handler:
            await self._action_handler(action, message, response_text, self)
    
    def run_bot(self) -> None:
        """Run the bot with the Discord token."""
        logger.info("Starting %s...", self.pilot_name)
        self.run(self.discord_token)


# ── Reusable Action Handlers ─────────────────────────────────────────────────

async def rei_action_handler(
    action: str,
    message: discord.Message,
    response_text: str,
    bot: BaseBot
) -> None:
    """
    Handler for Rei's administrative actions.
    
    Actions:
    - pin_message: Pin the previous user message
    - create_channel <name>: Create a text channel
    - rename_channel <name>: Rename current channel
    - delete_channel: Delete the current channel
    - list_channels: List server channels
    - summarize_messages <n>: Summarize last n messages
    - ask_pilot <question>: Ask a mentioned pilot a question
    - react_previous: React to the previous message
    - server_status: Report server stats
    """
    import re
    
    logger.info("[Rei] executing action: %s", action)
    
    if action == "pin_message":
        async for previous in message.channel.history(limit=10, before=message.created_at):
            if previous.author != bot.user and not previous.author.bot:
                try:
                    await previous.pin(reason="Ordered by NERV handler")
                except Exception as e:
                    logger.exception("Failed to pin: %s", e)
                return
        return
    
    if action.startswith("create_channel "):
        name = action[15:].strip()
        safe_name = re.sub(r"[^a-z0-9\-_]", "-", name.lower()).strip("-_")
        if safe_name and message.guild:
            try:
                await message.guild.create_text_channel(safe_name, reason="Ordered by NERV handler")
            except Exception as e:
                logger.exception("Failed to create channel: %s", e)
        return
    
    if action.startswith("rename_channel "):
        name = action[15:].strip()
        safe_name = re.sub(r"[^a-z0-9\-_]", "-", name.lower()).strip("-_")
        if safe_name:
            try:
                await message.channel.edit(name=safe_name, reason="Ordered by NERV handler")
            except Exception as e:
                logger.exception("Failed to rename: %s", e)
        return
    
    if action == "delete_channel":
        try:
            await message.channel.delete(reason="Ordered by NERV handler")
        except Exception as e:
            logger.exception("Failed to delete: %s", e)
        return
    
    if action == "list_channels":
        if message.guild:
            theme_keywords = [
                "nerv", "command", "bridge", "pilot", "laboratory", "sync",
                "geofront", "angel", "impact", "research", "clearance",
                "conference", "decree", "lexicon", "terminal"
            ]
            themed = []
            others = []
            for ch in message.guild.channels:
                name = getattr(ch, "name", "") or ""
                if any(kw in name.lower() for kw in theme_keywords):
                    themed.append(f"#{name}")
                else:
                    others.append(f"#{name}")
            
            lines = []
            if themed:
                lines.append("these channels fit the NERV theme:")
                lines.extend(themed[:25])
            if others:
                lines.append("\nthese channels are less clearly themed:")
                lines.extend(others[:25])
            
            if lines:
                await message.channel.send("\n".join(lines[:50]))
        return
    
    if action.startswith("summarize_messages "):
        try:
            count = int(action[19:].strip())
            count = min(max(count, 1), 20)
        except Exception:
            count = 5
        
        lines = []
        async for msg in message.channel.history(limit=count + 1, before=message.created_at):
            if msg.author == bot.user or msg.author.bot:
                continue
            if msg.content:
                author_name = getattr(msg.author, "display_name", None) or getattr(msg.author, "name", "unknown")
                lines.append(f"{author_name}: {msg.content.strip()}")
        
        if lines:
            await message.channel.send("i read the last messages:\n" + "\n".join(lines[:count]))
        return
    
    if action.startswith("ask_pilot "):
        question = action[10:].strip()
        target = next((user for user in message.mentions if user != bot.user), None)
        if target:
            await message.channel.send(f"{target.mention} {question}")
        return
    
    if action == "react_previous":
        async for previous in message.channel.history(limit=10, before=message.created_at):
            if previous.author != bot.user:
                try:
                    await previous.add_reaction("❄️")
                except Exception as e:
                    logger.exception("Failed to react: %s", e)
                return
        return
    
    if action == "server_status":
        if message.guild:
            member_count = message.guild.member_count
            channel_count = len(message.guild.channels)
            await message.channel.send(f"this server has {member_count} members and {channel_count} channels.")
        return
"""
Configuration module for Evangelion Discord bots.
Centralizes all settings with type hints and validation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    """Configuration for a single bot instance."""
    name: str
    token_env: str
    system_prompt_path: Optional[str] = None
    
    @property
    def token(self) -> str:
        token = os.getenv(self.token_env, "").strip()
        if not token:
            raise ValueError(f"{self.token_env} not found in environment variables")
        return token


@dataclass
class NVIDIAConfig:
    """NVIDIA NIM API configuration."""
    api_key: str = field(default="")
    model: str = "meta/llama2-70b"
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    
    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            if not self.api_key:
                raise ValueError("NVIDIA_API_KEY not found in environment variables")
    
    @property
    def base_url(self) -> str:
        return "https://integrate.api.nvidia.com/v1"


@dataclass
class OwnerConfig:
    """NERV handler (owner) configuration for authority recognition."""
    discord_id: str = ""
    display_name: str = "the NERV handler"
    role_description: str = "NERV handler coordinating pilot communications"
    
    def __post_init__(self):
        self.discord_id = os.getenv("OWNER_DISCORD_ID", "").strip()
        self.display_name = os.getenv("OWNER_DISPLAY_NAME", self.display_name).strip()
        self.role_description = os.getenv(
            "OWNER_ROLE_DESCRIPTION", 
            self.role_description
        ).strip()


@dataclass
class AppConfig:
    """Global application configuration."""
    nvidia: NVIDIAConfig = field(default_factory=NVIDIAConfig)
    owner: OwnerConfig = field(default_factory=OwnerConfig)
    
    # Bot chain depth limits
    max_bot_chain_depth: int = 3
    
    # Context limits
    recent_context_limit: int = 20
    conversation_history_limit: int = 12  # 6 full exchanges
    sentiment_history_limit: int = 30
    
    # Cooldowns (seconds)
    spontaneous_cooldowns: dict[str, float] = field(default_factory=lambda: {
        "Shinji Ikari": 90.0,
        "Asuka Langley Soryu": 45.0,
        "Rei Ayanami": 120.0,
    })
    
    # Base probabilities for spontaneous responses
    spontaneous_base_probabilities: dict[str, float] = field(default_factory=lambda: {
        "Shinji Ikari": 0.35,
        "Asuka Langley Soryu": 0.65,
        "Rei Ayanami": 0.22,
    })
    
    # LLM parameters
    default_temperature: float = 0.9
    default_max_tokens: int = 250
    default_top_p: float = 0.95
    
    # Timing parameters (seconds)
    typing_indicator_max_wait: float = 10.0
    write_delay_cap: float = 5.0
    
    @property
    def bots(self) -> list[BotConfig]:
        return [
            BotConfig(name="shinji", token_env="DISCORD_TOKEN_SHINJI"),
            BotConfig(name="asuka", token_env="DISCORD_TOKEN_ASUKA"),
            BotConfig(name="rei", token_env="DISCORD_TOKEN_REI"),
        ]


# Global config instance
config = AppConfig()
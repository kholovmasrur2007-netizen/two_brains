"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Process-wide settings. Extend as needed."""

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "3"))

    # Path to the JSON file MemoryStore mirrors its state to.
    # Empty/unset → pure in-process store, nothing written to disk.
    memory_path: str | None = os.getenv("MEMORY_PATH") or None

    # Provider selection for the two brains. Today only "deterministic"
    # is registered in app/brains/__init__.py; future values:
    # "openai", "anthropic", "local".
    planner_provider: str = os.getenv("PLANNER_PROVIDER", "deterministic")
    critic_provider:  str = os.getenv("CRITIC_PROVIDER",  "deterministic")

    # LLM provider selection. Only read by app/llm/get_llm_client() once
    # an LLM-backed brain is registered. Ignored while both brains run
    # in deterministic mode.
    llm_provider: str = os.getenv("LLM_PROVIDER", "none")

    # Credentials / endpoints — consumed by the LLM clients when they exist.
    openai_api_key:    str | None = os.getenv("OPENAI_API_KEY")    or None
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    local_llm_url:     str | None = os.getenv("LOCAL_LLM_URL")     or None


settings = Settings()
# TODO: migrate to pydantic-settings once validation rules become non-trivial.

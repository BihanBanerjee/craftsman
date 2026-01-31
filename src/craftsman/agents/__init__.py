"""Agents module for multi-agent support."""

from craftsman.agents.config import (
    AgentConfig,
    get_agent_config,
    AGENT_CONFIGS,
)
from craftsman.agents.subagents import create_subagent_tools

__all__ = [
    "AgentConfig",
    "get_agent_config",
    "AGENT_CONFIGS",
    "create_subagent_tools",
]

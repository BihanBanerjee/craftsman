"""Agent configuration for multi-agent mode.

Defines different agent modes with their tools and permissions.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any

from craftsman.tools.core import (
    read_file, write_file, grep, glob_files, TOOLS
)


# Get the prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(agent_name: str) -> str:
    """Load system prompt from file.
    
    Args:
        agent_name: Name of the agent (e.g., "coder", "researcher")

    Returns:
        System prompt text

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """

    prompt_file = PROMPTS_DIR / f"{agent_name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text().strip()


@dataclass
class AgentConfig:
    """Configuration for an agent mode.

    Attributes:
        name: Agent identifier
        description: What this agent is for
        system_prompt: Custom system prompt for this agent
        tools: List of tools available to this agent
        mode: "primary" or "subagent"
        max_steps: Maximum iterations before stopping (safety limit)
        color: Color for TUI display
    """
    name: str
    description: str
    system_prompt: str
    tools: list[Callable]
    mode: str = "primary"
    max_steps: int = 50 # Default step limit
    color: str = "blue" # Default color for UI


CODER_PROMPT = load_prompt("coder")
RESEARCHER_PROMPT = load_prompt("researcher")
PLANNER_PROMPT = load_prompt("planner")
REVIEWER_PROMPT = load_prompt("reviewer")


# Agent configurations
AGENT_CONFIGS: dict[str, AgentConfig] = {
    "coder": AgentConfig(
        name="coder",
        description="Full-access coding agent for development work",
        system_prompt=CODER_PROMPT,
        tools=TOOLS,  # All tools
        mode="primary",
        max_steps=100,  # Coder gets more steps for complex tasks
        color="green",
    ),
    "researcher": AgentConfig(
        name="researcher",
        description="Read-only agent for exploring codebases",
        system_prompt=RESEARCHER_PROMPT,
        tools=[read_file, grep, glob_files], # Read-only tools
        mode="subagent",
        max_steps=30, # Researcher should be quick
        color="cyan",
    ),
    "planner": AgentConfig(
        name="planner",
        description="Planning agent that creates implementation plans",
        system_prompt=PLANNER_PROMPT,
        tools=[read_file, write_file, glob_files],  # Limited write access
        mode="subagent",
        max_steps=20,  # Planning should be focused
        color="yellow",
    ),
    "reviewer": AgentConfig(
        name="reviewer",
        description="Code review specialist that analyzes code for bugs and improvements",
        system_prompt=REVIEWER_PROMPT,
        tools=[read_file, grep, glob_files],  # Read-only tools
        mode="subagent",
        max_steps=20,  # Review should be focused
        color="red",
    ),
}


def get_agent_config(agent_name: str) -> AgentConfig:
    """Get configuration for a specific agent.

    Args:
        agent_name: Name of the agent (coder, researcher, planner)
    
    Returns:
        AgentConfig for the specified agent
    
    Raises:
        ValueError: If agent not found
    """
    if agent_name not in AGENT_CONFIGS:
        available = ", ".join(AGENT_CONFIGS.keys())
        raise ValueError(f"Unknown agent: {agent_name}. Available: {available}")
    return AGENT_CONFIGS[agent_name]


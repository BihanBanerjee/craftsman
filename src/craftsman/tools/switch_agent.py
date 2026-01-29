"""Tool for switching primary agent mode mid-session.

Allows the user to switch from coder to researcher (or other agents)
during a conversation using LangGraph's interrupt() for coordination.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langgraph.types import interrupt

from craftsman.agents.config import AGENT_CONFIGS


class SwitchAgentInput(BaseModel):
    """Input for switch_agent tool."""
    agent_name: str = Field(
        description="Name of the agent to switch to (coder, researcher, planner, reviewer)"
    )
    reason: str = Field(
        default="",
        description="Optional reason for switching agents"
    )


@tool(args_schema=SwitchAgentInput)
def switch_agent(agent_name: str, reason: str = "") -> str:
    """Switch to a different agent mode as the primary agent.

    Use this when you need capabilities of a different agent:
    - Switch to 'researcher' for read-only exploration
    - Switch to 'planner' for creating implementation plans
    - Switch to 'coder' for full development access
    - Switch to 'reviewer' for code review and bug analysis

    This will pause and ask the user to confirm the switch.
    """
    # Validate agent name
    if agent_name not in AGENT_CONFIGS:
        available = ", ".join(AGENT_CONFIGS.keys())
        return f"Error: Unknown agent '{agent_name}'. Available agents: {available}"
    
    config = AGENT_CONFIGS[agent_name]
    
    # Use interrupt to signal agent switch and get user confirmation
    response = interrupt({
        "type": "agent_switch_request",
        "new_agent": agent_name,
        "new_agent_description": config.description,
        "reason": reason,
        "message": f"Requesting switch to '{agent_name}' agent. {config.description}. Approve?",
    })
    
    if response.get("approved", False):
        # Signal successful switch (the CLI will need to handle this)
        return (
            f"# Switched to {agent_name} agent.\n"
            f"Description: {config.description}\n"
            f"Tools available: {len(config.tools)}\n"
            f"Max steps: {config.max_steps}"
        )
    else:
        return f"# Agent switch to '{agent_name}' was rejected by user."

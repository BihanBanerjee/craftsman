"""
LangGraph builder for the coding agent.

Supports:
- SQLite persistence
- Multi-agent modes (coder, researcher, planner, reviewer)
- OpenRouter for all models
"""

import os
from pathlib import Path

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from craftsman.agents.config import get_agent_config, AGENT_CONFIGS
from craftsman.llm import get_llm


# Default paths
DEFAULT_DB_DIR = Path.home() / ".craftsman"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "sessions.db"


def get_model(model_name: str | None = None):
    """Get the LLM model via OpenRouter.
    
    Args:
        model_name: Model alias (sonnet, opus, haiku, gpt4o, gpt4o-mini)
                    or full OpenRouter model ID
    
    Returns:
        ChatOpenAI instance configured for OpenRouter
    """
    return get_llm(model_name)

def get_checkpointer(
        db_path: str | Path | None = None,
        in_memory: bool = False,
):
    """Get a checkpointer for session persistence.
    
    Args:
        db_path: Path to SQLite database (default: ~/.craftsman/sessions.db)
        in_memory: If True, use MemorySaver (no persistence)
    
    Returns:
        LangGraph checkpointer
    """

    if in_memory:
        return MemorySaver()
    
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return SqliteSaver.from_conn_string(str(db_path))

def build_agent(
    agent_name: str = "coder",
    model_name: str | None = None,
    checkpointer = None,
    db_path: str | Path | None = None,
    in_memory: bool = False
):
    """Build a coding agent graph.

    Args:
        agent_name: Agent mode ("coder", "researcher", "planner")
        model_name: Optional model name override
        checkpointer: Optional pre-configured checkpointer
        db_path: Path to SQLite database for persistence
        in_memory: If True, disable persistence

    Returns:
        Compiled LangGraph agent
    """
    # Get agent configuration
    agent_config = get_agent_config(agent_name)

    # Get model
    model = get_model(model_name)

    # Get or create checkpointer
    if checkpointer is None:
        checkpointer = get_checkpointer(db_path, in_memory)
    
    # Build agent with agent-specific tools and prompt
    agent = create_react_agent(
        model,
        agent_config.tools,
        state_modifier=agent_config.system_prompt,
        checkpointer=checkpointer,
    )

    return agent


def list_available_agents() -> list[str]:
    """List available agent modes."""
    return list(AGENT_CONFIGS.keys())


def build_advanced_agent():
    """Build an advanced agent with 2 features.
    
    """
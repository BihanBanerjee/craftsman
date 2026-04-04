"""Subagent tools for multi-agent orchestration.

Creates tools that delegate to subagent graphs (researcher, planner, reviewer).
This implements the OpenCode pattern where the main coder agent
can invoke specialized subagents with step limits.
"""

from pathlib import Path
from typing import Any
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from craftsman.agents.config import get_agent_config


# Cache for subagent instances.
# Keyed by "{session_id}:{agent_name}" so each session gets its own
# subagent graph instance with the correct persistent thread.
_subagent_cache: dict[str, Any] = {}


def _get_or_create_subagent(
    agent_name: str,
    model,
    cwd: str | None = None,
    session_id: str = "default",
    in_memory: bool = False,
    db_path: Path | None = None,
):
    """Get or create a subagent instance for a given session.

    Each subagent is scoped to a (session_id, agent_name) pair so that
    delegations within the same session accumulate context across turns,
    while different sessions remain isolated.
    """
    cache_key = f"{session_id}:{agent_name}"
    if cache_key not in _subagent_cache:
        config = get_agent_config(agent_name)

        if in_memory:
            checkpointer = MemorySaver()
        else:
            # Re-use the same database as the main agent so all conversation
            # history (parent + subagents) lives in one place.
            from craftsman.graph.builder import DEFAULT_DB_PATH
            resolved_db = db_path or DEFAULT_DB_PATH
            resolved_db = Path(resolved_db)
            resolved_db.parent.mkdir(parents=True, exist_ok=True)
            checkpointer = SqliteSaver.from_conn_string(str(resolved_db))

        subagent = create_react_agent(
            model,
            config.tools,
            state_modifier=config.with_dynamic_context(cwd),
            checkpointer=checkpointer,
        )
        _subagent_cache[cache_key] = (subagent, config.max_steps)
    return _subagent_cache[cache_key]


class DelegateToResearcherInput(BaseModel):
    """Input for delegate_to_researcher tool."""
    question: str = Field(
        description="The research question or exploration task for the researcher agent"
    )


class DelegateToPlannerInput(BaseModel):
    """Input for delegate_to_planner tool."""
    task: str = Field(
        description="The task to create an implementation plan for"
    )


def create_subagent_tools(
    model,
    cwd: str | None = None,
    session_id: str = "default",
    in_memory: bool = False,
    db_path: Path | None = None,
):
    """Create tools for delegating to subagents.

    Args:
        model: The LLM model to use for subagents
        cwd: Working directory to pass to subagent prompts
        session_id: Parent session ID; subagent thread IDs are derived from
                    this so each session has isolated, persistent subagent state
        in_memory: If True, use MemorySaver (mirrors parent agent persistence setting)
        db_path: Path to SQLite database; defaults to DEFAULT_DB_PATH

    Returns:
        List of delegation tools
    """

    @tool(args_schema=DelegateToResearcherInput)
    def delegate_to_researcher(question: str) -> str:
        """Delegate a research task to the researcher agent.

        The researcher agent can READ files, search with grep, and find files.
        It CANNOT write or edit files. Use this for:
        - Exploring unfamiliar codebases
        - Finding specific implementations
        - Understanding how something works
        """
        subagent, max_steps = _get_or_create_subagent(
            "researcher", model, cwd, session_id, in_memory, db_path
        )
        result = subagent.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={
                # Stable thread ID: same session always continues the same
                # researcher conversation rather than starting fresh.
                "configurable": {"thread_id": f"{session_id}-researcher"},
                "recursion_limit": max_steps,
            },
        )
        last_message = result["messages"][-1]
        return f"[Researcher Agent Report (max {max_steps} steps)]\n\n{last_message.content}"

    @tool(args_schema=DelegateToPlannerInput)
    def delegate_to_planner(task: str) -> str:
        """Delegate to the planner agent to create an implementation plan.

        The planner agent can READ files and WRITE markdown plan files.
        It cannot edit existing code. Use this for:
        - Creating step-by-step implementation plans
        - Breaking down complex tasks
        - Documenting approach before coding
        """
        subagent, max_steps = _get_or_create_subagent(
            "planner", model, cwd, session_id, in_memory, db_path
        )
        result = subagent.invoke(
            {"messages": [HumanMessage(content=f"Create an implementation plan for: {task}")]},
            config={
                "configurable": {"thread_id": f"{session_id}-planner"},
                "recursion_limit": max_steps,
            },
        )
        last_message = result["messages"][-1]
        return f"[Planner Agent Report (max {max_steps} steps)]\n\n{last_message.content}"

    @tool
    def delegate_to_reviewer(code_or_file: str) -> str:
        """Delegate to the reviewer agent for code review.

        The reviewer agent can READ files and search code, but CANNOT modify anything.
        Use this for:
        - Getting feedback on code changes before committing
        - Finding bugs, security issues, and code smells
        - Getting improvement suggestions

        Args:
            code_or_file: Either a file path to review, or describe what to review
        """
        subagent, max_steps = _get_or_create_subagent(
            "reviewer", model, cwd, session_id, in_memory, db_path
        )
        prompt = f"""Please review the following code/file and provide feedback:

{code_or_file}

Look for bugs, security issues, code smells, and improvement opportunities.
Prioritize issues by severity (Critical > Warning > Suggestion)."""

        result = subagent.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={
                "configurable": {"thread_id": f"{session_id}-reviewer"},
                "recursion_limit": max_steps,
            },
        )
        last_message = result["messages"][-1]
        return f"[Code Review Report (max {max_steps} steps)]\n\n{last_message.content}"

    return [delegate_to_researcher, delegate_to_planner, delegate_to_reviewer]


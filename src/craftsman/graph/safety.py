"""Safety utilities for the agent.

Includes doom loop detection and other safety checks.
"""

from typing import Any


DOOM_LOOP_THRESHOLD = 3



def check_doom_loop(recent_tool_calls: list[dict[str, Any]]) -> bool:
    """Check if we're in a doom loop (same tool called repeatedly with same args).

    A doom loop occurs when the agent calls the same tool 3+ times
    with identical arguments, indicating it's stuck.

    Args:
        recent_tool_calls: List of recent tool calls, each with 'tool' and 'args' keys
    Returns:
        True if doom loop detected, False otherwise
    """
    if len(recent_tool_calls) < DOOM_LOOP_THRESHOLD:
        return False

    last_n = recent_tool_calls[-DOOM_LOOP_THRESHOLD:] 
    first_call = last_n[0]

    return all(
        call.get("tool") == first_call.get("tool") and
        call.get("args") == first_call.get("args")
        for call in last_n
    )

def format_doom_loop_warning(tool_name: str, args: dict) -> str:
    """Format a warning message for doom loop detection."""
    return (
        f"# Doom loop detected: Tool '{tool_name}' called {DOOM_LOOP_THRESHOLD} times "
        f"with identical arguments. This might indicate the agent is stuck.\n"
        f"Arguments: {args}"
    )
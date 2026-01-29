"""Safety utilities for the agent.

Includes doom loop detection and other safety checks.
"""

from typing import Any


DOOM_LOOP_THRESHOLD = 3



def check_doom_loop(recent_tool_calls) -> bool:
    pass
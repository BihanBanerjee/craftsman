"""Subagent tools for multi-agent orchestration.

Creates tools that delegate to subagent graphs (researcher, planner, reviewer)
This implements the OpenCode pattern where the main coder agent
can invoke specialized subagents with step limits.
"""
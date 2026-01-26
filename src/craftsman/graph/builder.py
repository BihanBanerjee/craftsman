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



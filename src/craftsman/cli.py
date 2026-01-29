"""CLI entry point for the Craftsman coding agent.

Features:
- Interactive chat with streaming output
- Multi-agent modes (coder, researcher, planner, reviewer)
- SQLite session persistence
- Session listing and resumption
- Checkpoint management (/checkpoints, /restore)
"""
import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from langchain_core.messages import HumanMessage

from craftsman.graph.builder import (
    build_agent,
    list_available_agents,
    DEFAULT_DB_PATH,
)

from 
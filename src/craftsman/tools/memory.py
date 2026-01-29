"""Memory tool for persistent key-value storage.

Allows the agent to remember user preferences, notes, and context
across sessions. Stores data in ~/.agent-cli/memory.json.
"""

import json
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field


def _get_memory_path() -> Path:
    """Get the path to the memory file."""
    data_dir = Path.home() / ".agent-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "memory.json"


def _load_memory() -> dict:
    """Load memory from file."""
    path = _get_memory_path()
    if not path.exists():
        return {"entries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}}


def _save_memory(memory: dict) -> None:
    """Save memory to file."""
    path = _get_memory_path()
    path.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")


class MemoryInput(BaseModel):
    """Input for memory tool."""
    action: str = Field(
        description="Action to perform: 'set', 'get', 'delete', 'list', or 'clear'"
    )
    key: str | None = Field(
        default=None,
        description="Memory key (required for set, get, delete)"
    )
    value: str | None = Field(
        default=None,
        description="Value to store (required for set)"
    )


@tool(args_schema=MemoryInput)
def memory(action: str, key: str | None = None, value: str | None = None) -> str:
    """Store and retrieve persistent memory.
    
    Use this to remember user preferences, important context, or notes.
    Memory persists across sessions.
    
    Actions:
    - set: Store a key-value pair (requires key and value)
    - get: Retrieve a value by key (requires key)
    - delete: Remove a key (requires key)
    - list: Show all stored memories
    - clear: Remove all memories
    """
    action = action.lower()
    
    if action == "set":
        if not key or not value:
            return "Error: 'key' and 'value' are required for 'set' action"
        mem = _load_memory()
        mem["entries"][key] = value
        _save_memory(mem)
        return f"✅ Stored memory: {key} = {value}"
    
    elif action == "get":
        if not key:
            return "Error: 'key' is required for 'get' action"
        mem = _load_memory()
        if key not in mem.get("entries", {}):
            return f"Memory not found: {key}"
        return f"Memory: {key} = {mem['entries'][key]}"
    
    elif action == "delete":
        if not key:
            return "Error: 'key' is required for 'delete' action"
        mem = _load_memory()
        if key not in mem.get("entries", {}):
            return f"Memory not found: {key}"
        del mem["entries"][key]
        _save_memory(mem)
        return f"✅ Deleted memory: {key}"
    
    elif action == "list":
        mem = _load_memory()
        entries = mem.get("entries", {})
        if not entries:
            return "No memories stored"
        lines = ["Stored memories:"]
        for k, v in sorted(entries.items()):
            lines.append(f"  • {k}: {v}")
        return "\n".join(lines)
    
    elif action == "clear":
        mem = _load_memory()
        count = len(mem.get("entries", {}))
        mem["entries"] = {}
        _save_memory(mem)
        return f"✅ Cleared {count} memory entries"
    
    else:
        return f"Error: Unknown action '{action}'. Use: set, get, delete, list, clear"

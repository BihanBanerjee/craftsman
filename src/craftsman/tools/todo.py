"""Todo tool for task tracking.

Allows the agent to manage a persistent task list for tracking
multi-step tasks across sessions. Stores data in ~/.craftsman/todos.json.
"""

import json
import uuid
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field


def _get_todos_path() -> Path:
    """Get the path to the todos file."""
    data_dir = Path.home() / ".agent-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "todos.json"


def _load_todos() -> dict:
    """Load todos from file."""
    path = _get_todos_path()
    if not path.exists():
        return {"items": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}}


def _save_todos(todos: dict) -> None:
    """Save todos to file."""
    path = _get_todos_path()
    path.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")


class TodoInput(BaseModel):
    """Input for todo tool."""
    action: str = Field(
        description="Action: 'add', 'complete', 'list', or 'clear'"
    )
    id: str | None = Field(
        default=None,
        description="Todo ID (required for complete)"
    )
    content: str | None = Field(
        default=None,
        description="Todo content (required for add)"
    )


@tool(args_schema=TodoInput)
def todo(action: str, id: str | None = None, content: str | None = None) -> str:
    """Manage a task list for tracking multi-step work.
    
    Use this to track progress on complex tasks that span multiple steps.
    Todos persist across sessions.
    
    Actions:
    - add: Add a new todo (requires content)
    - complete: Mark a todo as complete (requires id)
    - list: Show all pending todos
    - clear: Remove all todos
    """
    action = action.lower()
    
    if action == "add":
        if not content:
            return "Error: 'content' is required for 'add' action"
        todo_id = str(uuid.uuid4())[:8]
        todos = _load_todos()
        todos["items"][todo_id] = {"content": content, "completed": False}
        _save_todos(todos)
        return f"# Added todo [{todo_id}]: {content}"
    
    elif action == "complete":
        if not id:
            return "Error: 'id' is required for 'complete' action"
        todos = _load_todos()
        if id not in todos.get("items", {}):
            return f"Todo not found: {id}"
        item = todos["items"].pop(id)
        _save_todos(todos)
        return f"# Completed todo [{id}]: {item['content']}"
    
    elif action == "list":
        todos = _load_todos()
        items = todos.get("items", {})
        if not items:
            return "📋 No pending todos"
        lines = ["# Pending todos:"]
        for todo_id, item in items.items():
            lines.append(f"  [{todo_id}] {item['content']}")
        return "\n".join(lines)
    
    elif action == "clear":
        todos = _load_todos()
        count = len(todos.get("items", {}))
        todos["items"] = {}
        _save_todos(todos)
        return f"# Cleared {count} todos"
    
    else:
        return f"Error: Unknown action '{action}'. Use: add, complete, list, clear"

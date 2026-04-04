# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Craftsman** is a CLI coding agent built on LangChain and LangGraph. It supports multi-agent orchestration (coder, researcher, planner, reviewer), a per-tool permission system with human-in-the-loop approvals, SQLite session persistence, context compaction, doom loop detection, and a custom hook system for automation.

All LLM access is unified through OpenRouter (`OPENROUTER_API_KEY` required). `EXA_API_KEY` is optional — falls back to DuckDuckGo for web search.

## Commands

```bash
# Install dependencies
uv sync

# Run interactive chat (coder mode, basic)
uv run craftsman chat

# Run with advanced features (permissions, hooks, doom loop detection)
uv run craftsman chat --advanced

# Run with specific model and trust policy
uv run craftsman chat --model opus --advanced --policy yolo

# Named session (persistent)
uv run craftsman chat --session my-project

# Single-shot command
uv run craftsman run "Read main.py and explain"

# List available agent modes
uv run craftsman agents

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_core.py -v

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

## Architecture

### Graph Control Flow (`src/craftsman/graph/`)

The core is a custom LangGraph `StateGraph` in `custom_agent.py`. Nodes:

1. `call_model` → invokes LLM with bound tools
2. `check_permissions` → evaluates each tool call against permission rules; uses `interrupt()` for ASK-policy tools
3. `execute_tools` → runs approved tools, tracks recent calls
4. `doom_loop` → triggered when same tool is called 3× with identical args; prompts user to continue or abort
5. `check_compaction` → summarizes old messages when approaching 85% of the model's context limit

Routing: `should_continue` → `after_permission_check` → `after_tool_execution` → `after_compaction`

`builder.py` provides two entrypoints: `build_agent()` (simple react_agent) and `build_advanced_agent()` (full custom graph). The CLI uses `build_advanced_agent()` when `--advanced` is passed.

### Permission System (`src/craftsman/permission/rules.py`)

- Actions: `ALLOW`, `DENY`, `ASK` — evaluated last-match-wins against a list of rules
- Policies: `ask` (default), `auto` (approve all ASK), `yolo` (approve all), `never` (deny all)
- Per-session approval memory: `remember_approval(tool, pattern, action)` lets users skip future prompts for the same tool/path pattern
- Agent-specific overrides: researcher denies `write_file`/`edit_file`; planner allows `*.md` writes

### Agent Modes (`src/craftsman/agents/`)

- **coder**: All tools + subagent delegation, 100 steps
- **researcher**: Read-only (`read_file`, `grep`, `glob_files`), 30 steps
- **planner**: Read + write `.md` files, 20 steps
- **reviewer**: Read-only, 20 steps

System prompts live in `src/craftsman/agents/prompts/{name}.md`. The coder agent gets delegation tools from `subagents.py` to spawn the other agents with `MemorySaver` (in-memory, not persisted).

### Tools (`src/craftsman/tools/`)

- `core.py`: `read_file`, `write_file`, `edit_file`, `run_bash` (60s timeout), `grep`, `glob_files`
- `memory.py`: Persistent key-value store at `~/.agent-cli/memory.json`
- `todo.py`: Task tracker at `~/.agent-cli/todos.json`
- `web_search.py`: Exa (semantic) → DuckDuckGo fallback
- `web_fetch.py`: httpx + BeautifulSoup, truncated to 10k chars
- `switch_agent.py`: Uses `interrupt()` to request agent switch with user confirmation

### Hooks (`src/craftsman/hooks/hook_system.py`)

Hook triggers: `before_agent`, `after_agent`, `before_tool`, `after_tool`, `on_error`. Hooks run as async shell commands/scripts with a 30s timeout. Errors are swallowed — hooks must not crash the agent. The hook environment receives `AI_AGENT_*` variables.

### Persistence

- **SQLite** at `~/.craftsman/sessions.db` via LangGraph's `SqliteSaver`
- Checkpoint management in `graph/checkpoints.py`: list, export to markdown, session stats
- User config at `~/.craftsman/config.yaml` (managed by `config/user_config.py`)

### Terminal UI (`src/craftsman/ui/tui.py`)

Rich-based TUI with a singleton `get_tui()`. Displays tool calls/results in panels with syntax highlighting, unified diffs for edits, and streaming LLM output.

## Key Design Patterns

- **Last-match-wins** for permission rules — later rules override earlier ones
- **`interrupt()`** from LangGraph used for human-in-the-loop at permission checks and agent switches
- **Subagents use `MemorySaver`** (in-memory, not persisted) and are cached in `_subagent_cache`
- **Context compaction** prunes old tool outputs and summarizes messages; thresholds are per-model (200k for Claude, 128k for GPT)
- All tests use `pytest-asyncio`; test file is `tests/test_core.py`

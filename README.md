# Craftsman

<div align="center">

![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)
![LangChain](https://img.shields.io/badge/LangChain-0.3+-green.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0+-purple.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**A CLI coding agent with multi-agent orchestration, permission system, and extensible hooks.**

[Features](#features) •
[Installation](#installation) •
[Quick Start](#quick-start) •
[Configuration](#configuration) •
[Architecture](#architecture)

</div>

---

## Features

### Multi-Agent System
- **Coder** - Full-access development agent with all tools
- **Researcher** - Read-only codebase exploration
- **Planner** - Creates implementation plans (markdown only)
- **Reviewer** - Code review specialist with detailed feedback

### Permission System
- Agent-specific permission rules (researcher can't write, planner limited to .md)
- Configurable approval policies: `ask`, `auto`, `yolo`, `never`
- Session memory for "remember this decision" feature
- Interactive approval prompts with LangGraph interrupts

### Hooks System
- Run custom scripts at 5 trigger points
- Automate backups, testing, notifications, git commits
- Configure via `~/.craftsman/config.yaml`

### 10+ Built-in Tools
| Core | Extended |
|------|----------|
| `read_file`, `write_file`, `edit_file` | `memory` (persistent key-value store) |
| `run_bash`, `grep`, `glob_files` | `web_search`, `web_fetch` |
| | `todo` (task tracking), `switch_agent` |

### Persistence & Safety
- SQLite-backed session persistence
- Checkpoint save/restore (`/checkpoints`, `/restore`)
- Doom loop detection (prevents repetitive tool calls)
- Context compaction (manages token limits)

### Rich Terminal UI
- Syntax-highlighted code blocks
- Color-coded tool execution panels
- Streaming responses with real-time output

---

## Installation

### Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Install

```bash
# Clone the repository
git clone https://github.com/yourusername/craftsman.git
cd craftsman

# Install dependencies
uv sync

# Set your OpenRouter API key (all models accessed via OpenRouter)
export OPENROUTER_API_KEY="your-key-here"
# Get your key at: https://openrouter.ai/keys
```

---

## Quick Start

### Interactive Chat

```bash
# Start with defaults (Claude Sonnet via OpenRouter, coder mode)
uv run craftsman chat

# Use a different model
uv run craftsman chat --model opus
uv run craftsman chat --model gemini
uv run craftsman chat --model deepseek

# Or pass any full OpenRouter model ID directly
uv run craftsman chat --model x-ai/grok-4

# Full trust mode (no permission prompts)
uv run craftsman chat --advanced --policy yolo

# Named session for persistence
uv run craftsman chat --session my-project
```

### Single Command

```bash
uv run craftsman run "Read main.py and explain what it does"
```

### List Available Agents

```bash
uv run craftsman agents
```

---

## Configuration

### Config File

Create `~/.craftsman/config.yaml`:

```yaml
# Model Settings (all models via OpenRouter)
model: sonnet                # sonnet, opus, haiku, gpt4o, gpt4o-mini

# Agent Settings
agent: coder                 # coder, researcher, planner, reviewer
policy: ask                  # ask, auto, yolo, never
advanced: true               # enable permissions & hooks

# Session
session: default
no_persist: false

# Hooks (optional)
hooks:
  before_agent:
    - echo "Agent starting..." >> ~/.craftsman/agent.log
  after_tool:
    - |
      if [ "$AI_AGENT_TOOL_NAME" = "write_file" ]; then
        git add . && git commit -m "Auto-commit" || true
      fi
```

### Interactive Configuration

```bash
# View current config
/config

# Set a value
/config set model=opus
/config set agent=researcher
/config set advanced=true

# Show config file path
/config path
```

---

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `craftsman chat` | Start interactive chat session |
| `craftsman run "<prompt>"` | Run single command and exit |
| `craftsman agents` | List available agents |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--model`, `-m` | `sonnet` | Model alias or full OpenRouter ID (see Models section) |
| `--session`, `-s` | `default` | Session ID for persistence |
| `--agent`, `-a` | `coder` | Agent mode |
| `--policy` | `ask` | Approval policy |
| `--advanced/--no-advanced` | `true` | Full agent (permissions, hooks, doom loop). Use --no-advanced for simple mode |
| `--no-persist` | `false` | Disable session persistence |

### Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/config` | Show current configuration |
| `/config set key=value` | Set and save config value |
| `/checkpoints` | List session checkpoints |
| `/restore <#>` | Restore to checkpoint |
| `/sessions` | List all sessions |
| `/export [name]` | Export session to markdown |
| `/approvals` | Show remembered approvals |
| `/clear` | Clear approval memory |
| `exit`, `quit` | End session |

---

## Models

All models are accessed via [OpenRouter](https://openrouter.ai). Use a short alias or pass any full OpenRouter model ID directly.

| Alias | Model | Context |
|-------|-------|---------|
| `sonnet` | anthropic/claude-sonnet-4.6 | 1M |
| `opus` | anthropic/claude-opus-4.6 | 1M |
| `haiku` | anthropic/claude-haiku-4.5 | 200k |
| `gemini` | google/gemini-2.5-pro | 1M |
| `flash` | google/gemini-2.5-flash | 1M |
| `gpt4o` | openai/gpt-4o | 128k |
| `gpt4o-mini` | openai/gpt-4o-mini | 128k |
| `gpt5` | openai/gpt-5.4 | 1M |

Context limits are fetched live from the OpenRouter API at startup, so newly released models are automatically supported even without a code update.

---

## Agents

| Agent | Permissions | Use Case |
|-------|-------------|----------|
| **coder** | Full access (all tools) | Development work |
| **researcher** | Read-only (read, grep, glob) | Codebase exploration |
| **planner** | Read + write .md files | Implementation plans |
| **reviewer** | Read-only | Code review & feedback |

### Subagent Delegation

The coder agent can delegate tasks to specialized subagents:

```
"Please have the researcher explore the authentication module"
-> Spawns researcher subagent with step limit

"Create an implementation plan for adding OAuth support"
-> Spawns planner subagent

"Review the changes I made to auth.py"
-> Spawns reviewer subagent with code review format
```

---

## Approval Policies

| Policy | Behavior |
|--------|----------|
| `ask` | Prompt for each dangerous action (default) |
| `auto` | Auto-approve with guardrails |
| `yolo` | Auto-approve everything (full trust) |
| `never` | Deny all dangerous actions (read-only) |

---

## Hooks System

Hooks run custom scripts at trigger points:

| Trigger | When | Use Cases |
|---------|------|-----------|
| `before_agent` | Before LLM processes | Logging, timers |
| `after_agent` | After LLM responds | Notifications |
| `before_tool` | Before tool runs | Backups |
| `after_tool` | After tool completes | Tests, git commits |
| `on_error` | On error | Alerts |

### Environment Variables

Hooks receive context via environment variables:

| Variable | Description |
|----------|-------------|
| `AI_AGENT_TRIGGER` | Trigger type |
| `AI_AGENT_TOOL_NAME` | Tool being executed |
| `AI_AGENT_TOOL_PARAMS` | Tool parameters (JSON) |
| `AI_AGENT_USER_MESSAGE` | User's input |
| `AI_AGENT_CWD` | Working directory |

### Example: Auto-backup before writes

```yaml
hooks:
  before_tool:
    - |
      if [ "$AI_AGENT_TOOL_NAME" = "write_file" ]; then
        FILE=$(echo $AI_AGENT_TOOL_PARAMS | jq -r '.file_path')
        [ -f "$FILE" ] && cp "$FILE" "$FILE.bak"
      fi
```

---

## Architecture

```
+------------------------------------------------------------+
|                        CLI Layer                            |
|   chat command | run command | slash commands (/config)    |
+---------------------------+--------------------------------+
                            |
+---------------------------v--------------------------------+
|                     Agent Builder                           |
|   build_agent() ---- simple mode                           |
|   build_advanced_agent() ---- permissions + hooks + safety |
+---------------------------+--------------------------------+
                            |
+---------------------------v--------------------------------+
|                  LangGraph StateGraph                       |
|   +----------+    +-------------+    +--------------+     |
|   |call_model|    |check_perms  |    |execute_tools |     |
|   +----------+    +-------------+    +--------------+     |
|        |                |                    |             |
|        v                v                    v             |
|   BEFORE_AGENT    BEFORE_TOOL          AFTER_TOOL         |
|   AFTER_AGENT     (interrupt)          (hooks)            |
+------------------------------------------------------------+
```

---

## Project Structure

```
src/craftsman/
├── cli.py                  # Typer CLI entry point
├── llm.py                  # LLM configuration (OpenRouter)
├── graph/
│   ├── builder.py          # Agent builder (simple + advanced)
│   ├── custom_agent.py     # StateGraph with permissions & hooks
│   ├── checkpoints.py      # Session checkpoint management
│   ├── compaction.py       # Context window management
│   └── safety.py           # Doom loop detection
├── tools/
│   ├── core.py             # Core tools (read, write, edit, bash)
│   ├── memory.py           # Persistent memory
│   ├── web_search.py       # Web search (Exa or DuckDuckGo)
│   ├── web_fetch.py        # URL fetching
│   ├── todo.py             # Task list
│   └── switch_agent.py     # Agent switching
├── agents/
│   ├── config.py           # Agent configurations & prompts
│   ├── subagents.py        # Subagent delegation tools
│   └── prompts/            # Agent system prompts
├── permission/
│   └── rules.py            # Permission rules & policies
├── hooks/
│   └── hook_system.py      # Hook triggers & execution
├── config/
│   └── user_config.py      # User configuration management
└── ui/
    └── tui.py              # Rich terminal UI
```

---

## Data Storage

All data stored in `~/.craftsman/`:

| File | Purpose |
|------|---------|
| `config.yaml` | User configuration |
| `sessions.db` | SQLite session storage |
| `memory.json` | Persistent memory store |
| `todos.json` | Todo list data |

---

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Lint
uv run ruff check src/
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with [LangChain](https://langchain.com) & [LangGraph](https://github.com/langchain-ai/langgraph)**

</div>

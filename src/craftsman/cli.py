"""CLI entry point for Craftsman.

Usage:
    craftsman [PATH]           Start session in PATH (default: current dir)
    craftsman --resume         Pick and resume a previous session
    craftsman -p "prompt"      Single-shot non-interactive mode
    craftsman agents           List available agent modes
    craftsman run "prompt"     Alias for -p (kept for back-compat)
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from langchain_core.messages import HumanMessage

from craftsman.graph.builder import (
    build_agent,
    build_advanced_agent,
    list_available_agents,
    DEFAULT_DB_PATH,
)
from craftsman.graph.checkpoints import (
    list_checkpoints,
    format_checkpoint_table,
    get_session_count,
)
from craftsman.hooks import HookSystem, HookConfig, HookTrigger
from craftsman.hooks.hook_system import HookSystemConfig
from craftsman.permission.rules import clear_session_approvals

app = typer.Typer(
    name="craftsman",
    help="A CLI coding agent powered by LangChain and LangGraph",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()

from craftsman.ui.tui import TUI, get_tui


# ---------------------------------------------------------------------------
# Session picker for --resume
# ---------------------------------------------------------------------------

def _pick_session() -> str | None:
    """Show an interactive session picker. Returns chosen thread_id or None."""
    sessions = get_session_count(DEFAULT_DB_PATH)
    if not sessions:
        console.print("[yellow]No previous sessions found.[/yellow]")
        return None

    table = Table(title="Previous Sessions", box=box.ROUNDED, border_style="grey35")
    table.add_column("#", style="muted", justify="right", width=4)
    table.add_column("Session ID", style="cyan")
    table.add_column("Checkpoints", style="dim", justify="right")

    session_list = list(sessions.items())
    for i, (tid, count) in enumerate(session_list):
        table.add_row(str(i + 1), tid, str(count))

    console.print(table)

    try:
        raw = console.input("\n[bold]Pick a session (# or ID, Enter to cancel):[/bold] ").strip()
    except (KeyboardInterrupt, EOFError):
        return None

    if not raw:
        return None

    # Try numeric index first
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(session_list):
            return session_list[idx][0]
        console.print("[red]Invalid number.[/red]")
        return None
    except ValueError:
        pass

    # Try direct match / prefix match
    for tid, _ in session_list:
        if tid == raw or tid.startswith(raw):
            return tid

    console.print(f"[red]Session not found: {raw}[/red]")
    return None


# ---------------------------------------------------------------------------
# Slash-command handler
# ---------------------------------------------------------------------------

def _handle_slash_command(
    command: str,
    session: str,
    no_persist: bool,
    console: Console,
) -> None:
    """Handle slash commands in the chat loop."""
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None

    if cmd == "/help":
        console.print(Panel(
            "[bold]Available Commands:[/bold]\n\n"
            "/help               - Show this help message\n"
            "/config             - Show current configuration\n"
            "/config set <k>=<v> - Set a config value\n"
            "/config path        - Show config file location\n"
            "/checkpoints        - List checkpoints for current session\n"
            "/restore <#>        - Restore to a checkpoint (by index or ID)\n"
            "/sessions           - List all sessions\n"
            "/export [name]      - Export session to markdown file\n"
            "/approvals          - Show remembered approval decisions\n"
            "/clear              - Clear remembered approvals\n"
            "exit, quit          - End the session",
            border_style="blue",
        ))

    elif cmd == "/checkpoints":
        if no_persist:
            console.print("[yellow]Checkpoints disabled (no persistence)[/yellow]")
            return
        checkpoints = list_checkpoints(DEFAULT_DB_PATH, session, limit=10)
        console.print(format_checkpoint_table(checkpoints))

    elif cmd == "/restore":
        if no_persist:
            console.print("[yellow]Restore disabled (no persistence)[/yellow]")
            return
        if not arg:
            console.print("[yellow]Usage: /restore <checkpoint_index or id>[/yellow]")
            return

        checkpoints = list_checkpoints(DEFAULT_DB_PATH, session)
        if not checkpoints:
            console.print("[yellow]No checkpoints available[/yellow]")
            return

        target_id = None
        try:
            idx = int(arg)
            if 0 <= idx < len(checkpoints):
                target_id = checkpoints[idx].checkpoint_id
        except ValueError:
            for cp in checkpoints:
                if cp.checkpoint_id.startswith(arg):
                    target_id = cp.checkpoint_id
                    break

        if target_id:
            console.print(f"[green]Restored to checkpoint: {target_id[:36]}...[/green]")
            console.print("[dim]Note: Next message will resume from this checkpoint.[/dim]")
        else:
            console.print(f"[red]Checkpoint not found: {arg}[/red]")

    elif cmd == "/sessions":
        sessions = get_session_count(DEFAULT_DB_PATH)
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        console.print("[bold]Sessions:[/bold]")
        for tid, count in sessions.items():
            marker = " [current]" if tid == session else ""
            console.print(f"  {tid}: {count} checkpoints{marker}")

    elif cmd == "/export":
        from craftsman.graph.checkpoints import export_session

        if no_persist:
            console.print("[yellow]Export disabled (no persistence)[/yellow]")
            return

        output_name = arg.strip() if arg else None
        output_path = Path(f"{output_name}.md") if output_name else None

        success, result = export_session(DEFAULT_DB_PATH, session, output_path=output_path)
        if success:
            console.print(f"[green]Session exported to: {result}[/green]")
        else:
            console.print(f"[red]{result}[/red]")

    elif cmd == "/approvals":
        from craftsman.permission.rules import list_session_approvals, PermissionAction
        approvals = list_session_approvals()
        if not approvals:
            console.print("[dim]No remembered approvals in this session[/dim]")
        else:
            console.print("[bold]Remembered Approvals:[/bold]")
            for key, action in approvals.items():
                icon = "allow" if action == PermissionAction.ALLOW else "deny"
                console.print(f"  [{icon}] {key}: {action.value}")

    elif cmd == "/clear":
        clear_session_approvals()
        console.print("[green]Cleared all remembered approvals[/green]")

    elif cmd == "/config":
        from craftsman.config.user_config import UserConfig, CONFIG_FILE
        config = UserConfig.load()

        if not arg:
            console.print("[bold]Current Configuration:[/bold]")
            for key, value in config.to_display_dict().items():
                console.print(f"  [cyan]{key}[/cyan]: {value}")
            console.print(f"\n[dim]Config file: {CONFIG_FILE}[/dim]")

        elif arg == "path":
            console.print(f"[bold]Config file:[/bold] {CONFIG_FILE}")
            if CONFIG_FILE.exists():
                console.print("[green]File exists[/green]")
            else:
                console.print("[yellow]File does not exist (using defaults)[/yellow]")

        elif arg.startswith("set "):
            set_arg = arg[4:].strip()
            if "=" not in set_arg:
                console.print("[yellow]Usage: /config set key=value[/yellow]")
                console.print("[dim]Examples: /config set model=opus, /config set agent=researcher[/dim]")
                return

            key, value = set_arg.split("=", 1)
            key = key.strip()
            value = value.strip()

            success, message = config.set_value(key, value)
            if success:
                if config.save():
                    console.print(f"[green]{message} (saved)[/green]")
                else:
                    console.print(f"[yellow]{message} (could not save — PyYAML missing?)[/yellow]")
            else:
                console.print(f"[red]{message}[/red]")

        else:
            console.print(f"[yellow]Unknown config subcommand: {arg}[/yellow]")
            console.print("[dim]Usage: /config, /config set key=value, /config path[/dim]")

    else:
        console.print(f"[yellow]Unknown command: {cmd}. Type /help for available commands.[/yellow]")


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

async def _stream_response(agent, user_input: str, config: dict):
    """Stream agent response with real-time output using Rich TUI."""
    tui = get_tui()
    current_tool_id = None
    current_tool_name = None

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=user_input)]},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                tui.stream_text(chunk.content)

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            run_id = event.get("run_id", "unknown")[:8]
            data = event.get("data", {})
            tool_input = data.get("input", {})

            current_tool_id = run_id
            current_tool_name = tool_name

            tui.tool_start(tool_name, run_id, tool_input)

        elif kind == "on_tool_end":
            tool_name = event.get("name", "unknown")
            run_id = event.get("run_id", "unknown")[:8]
            data = event.get("data", {})
            output = data.get("output", "")

            if hasattr(output, "content"):
                output = output.content
            elif not isinstance(output, str):
                output = str(output)

            tui.tool_end(tool_name, run_id, output, success=True)
            current_tool_id = None
            current_tool_name = None

    tui.end_response()


# ---------------------------------------------------------------------------
# Core session runner (shared by interactive and --print modes)
# ---------------------------------------------------------------------------

def _build_hook_system(user_config):
    """Build a HookSystem from user config, or return None."""
    if not user_config.hooks:
        return None

    hooks_list = []
    for trigger_name, commands in user_config.hooks.items():
        try:
            trigger = HookTrigger(trigger_name)
            for cmd in commands:
                hooks_list.append(HookConfig(trigger=trigger, command=cmd, enabled=True))
        except ValueError:
            console.print(f"[yellow]Warning: Unknown hook trigger '{trigger_name}'[/yellow]")

    if not hooks_list:
        return None

    hook_config = HookSystemConfig(enabled=True, hooks=hooks_list)
    hook_system = HookSystem(hook_config)
    console.print(f"[dim]Loaded {len(hooks_list)} hook(s)[/dim]")
    return hook_system


def _build_graph(agent, model, session, no_persist, advanced, policy, hook_system, work_dir):
    """Construct the LangGraph agent graph."""
    cwd = str(work_dir)
    if advanced:
        return build_advanced_agent(
            agent_name=agent,
            model_name=model,
            in_memory=no_persist,
            approval_policy=policy,
            hook_system=hook_system,
            session_id=session,
            cwd=cwd,
        )
    return build_agent(
        agent_name=agent,
        model_name=model,
        in_memory=no_persist,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# Default command: craftsman [PATH]
# ---------------------------------------------------------------------------

@app.command(name="chat")
def chat(
    path: Optional[Path] = typer.Argument(None, help="Directory to work in (default: current dir)"),
    model: str = typer.Option(None, "--model", "-m", help="Model alias or full OpenRouter ID"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID for persistence"),
    agent: str = typer.Option(None, "--agent", "-a", help="Agent mode (coder/researcher/planner/reviewer)"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume a previous session (interactive picker)"),
    print_mode: bool = typer.Option(False, "--print", "-p", help="Single-shot mode: run prompt then exit"),
    prompt: Optional[str] = typer.Option(None, "--prompt", hidden=True, help="Prompt for --print mode"),
    no_persist: bool = typer.Option(False, "--no-persist", help="Disable session persistence"),
    advanced: bool = typer.Option(True, "--advanced/--no-advanced", help="Full agent (permissions, hooks, doom loop)"),
    policy: str = typer.Option(None, "--policy", help="Approval policy: ask, auto, yolo, never"),
):
    """Start a session in the given directory (default: current directory)."""

    # ---- Load user config and apply defaults ----
    from craftsman.config import get_config
    user_config = get_config()

    model = model or user_config.model
    agent = agent or user_config.agent
    policy = policy or user_config.policy
    advanced = advanced or user_config.advanced
    no_persist = no_persist or user_config.no_persist

    # ---- Resolve working directory ----
    if path is not None:
        work_dir = path.resolve()
        if not work_dir.is_dir():
            console.print(f"[red]Not a directory: {work_dir}[/red]")
            raise typer.Exit(1)
        os.chdir(work_dir)
    else:
        work_dir = Path.cwd()

    # ---- Validate agent ----
    available_agents = list_available_agents()
    if agent not in available_agents:
        console.print(f"[red]Unknown agent '{agent}'. Available: {', '.join(available_agents)}[/red]")
        raise typer.Exit(1)

    # ---- Session resolution ----
    if resume:
        chosen = _pick_session()
        if chosen is None:
            # User cancelled or no sessions — start fresh
            session = session or user_config.session
        else:
            session = chosen
            console.print(f"[dim]Resuming session: {session}[/dim]")
    else:
        session = session or user_config.session

    # ---- Print mode (single-shot) ----
    if print_mode:
        # Prompt comes from --prompt option or is read from the command line
        if prompt is None:
            try:
                prompt = console.input("[bold green]>[/bold green] ").strip()
            except (KeyboardInterrupt, EOFError):
                raise typer.Exit(0)
        if not prompt:
            raise typer.Exit(0)

        agent_graph = _build_graph(agent, model, session, no_persist=True, advanced=advanced,
                                    policy=policy, hook_system=None, work_dir=work_dir)
        cfg = {"configurable": {"thread_id": session}}
        try:
            asyncio.run(_stream_response(agent_graph, prompt, cfg))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        return

    # ---- Interactive session ----
    tui = get_tui()
    tui.print_welcome(
        agent_mode=agent,
        session=session,
        policy=policy if advanced else "n/a",
        persistence="disabled" if no_persist else "enabled",
        cwd=str(work_dir),
    )

    hook_system = _build_hook_system(user_config)
    agent_graph = _build_graph(agent, model, session, no_persist, advanced, policy, hook_system, work_dir)
    cfg = {"configurable": {"thread_id": session}}

    while True:
        try:
            user_input = console.input("\n[bold green]>[/bold green] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Goodbye![/yellow]")
            break

        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]Goodbye![/yellow]")
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            _handle_slash_command(user_input, session, no_persist, console)
            continue

        try:
            asyncio.run(_stream_response(agent_graph, user_input, cfg))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@app.command()
def run(
    prompt: str = typer.Argument(..., help="The task for the agent to perform"),
    model: str = typer.Option(None, "--model", "-m", help="Model name override"),
    agent: str = typer.Option("coder", "--agent", "-a", help="Agent mode"),
):
    """Run a single prompt and exit (alias for -p)."""
    agent_graph = build_agent(
        agent_name=agent,
        model_name=model,
        in_memory=True,
        cwd=str(Path.cwd()),
    )
    cfg = {"configurable": {"thread_id": "oneshot"}}

    console.print(f"[dim]Running ({agent}): {prompt}[/dim]\n")
    try:
        asyncio.run(_stream_response(agent_graph, prompt, cfg))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def agents():
    """List available agent modes."""
    from craftsman.agents.config import AGENT_CONFIGS

    table = Table(title="Available Agents", box=box.ROUNDED, border_style="grey35")
    table.add_column("Name", style="cyan")
    table.add_column("Mode", style="green")
    table.add_column("Description")

    for name, config in AGENT_CONFIGS.items():
        table.add_row(name, config.mode, config.description)

    console.print(table)


def main():
    """Main entry point.

    Defaults to `chat` when no subcommand is supplied so that:
      craftsman              → craftsman chat
      craftsman .            → craftsman chat .
      craftsman /path        → craftsman chat /path
      craftsman --resume     → craftsman chat --resume
      craftsman -p "prompt"  → craftsman chat -p "prompt"
    Explicit subcommands (run, agents) are passed through unchanged.
    """
    import sys

    _known_subcommands = {"chat", "run", "agents"}
    _global_flags = {"--help", "-h", "--version"}
    # Inject "chat" only when the first arg is not a known subcommand or global flag.
    # This makes `craftsman .`, `craftsman --resume`, etc. all route to `chat`.
    # `craftsman --help` is left unchanged so it shows the full command listing.
    first = sys.argv[1] if len(sys.argv) >= 2 else None
    if first is None or (first not in _known_subcommands and first not in _global_flags):
        sys.argv.insert(1, "chat")

    app()


if __name__ == "__main__":
    main()

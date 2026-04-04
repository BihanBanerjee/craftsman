"""CLI entry point for the coding agent.

Features:
- Interactive chat with streaming output
- Multi-agent modes (coder, researcher, planner)
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
    build_advanced_agent,
    list_available_agents,
    DEFAULT_DB_PATH,
)
from craftsman.graph.checkpoints import (
    list_checkpoints,
    format_checkpoint_table,
)
from craftsman.hooks import HookSystem, HookConfig, HookTrigger
from craftsman.hooks.hook_system import HookSystemConfig
from craftsman.permission.rules import clear_session_approvals

app = typer.Typer(
    name="craftsman",
    help="A CLI coding agent powered by LangChain and LangGraph",
    add_completion=False,
)
console = Console()

# Import TUI for rich output
from craftsman.ui.tui import TUI, get_tui


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
            "/help             - Show this help message\n"
            "/config           - Show current configuration\n"
            "/config set <k>=<v> - Set a config value\n"
            "/config path      - Show config file location\n"
            "/checkpoints      - List checkpoints for current session\n"
            "/restore <#>      - Restore to a checkpoint (by index or ID)\n"
            "/sessions         - List all sessions\n"
            "/export [name]    - Export session to markdown file\n"
            "/approvals        - Show remembered approval decisions\n"
            "/clear            - Clear remembered approvals\n"
            "exit, quit        - End the session",
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
        
        # Try to find checkpoint by index or ID
        target_id = None
        try:
            idx = int(arg)
            if 0 <= idx < len(checkpoints):
                target_id = checkpoints[idx].checkpoint_id
        except ValueError:
            # Try to match by partial ID
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
        from craftsman.graph.checkpoints import get_session_count
        sessions = get_session_count(DEFAULT_DB_PATH)
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        console.print("[bold]Sessions:[/bold]")
        for tid, count in sessions.items():
            marker = " [current]" if tid == session else ""
            console.print(f"  • {tid}: {count} checkpoints{marker}")
    
    elif cmd == "/export":
        from craftsman.graph.checkpoints import export_session
        from pathlib import Path
        
        if no_persist:
            console.print("[yellow]Export disabled (no persistence)[/yellow]")
            return
        
        output_name = arg.strip() if arg else None
        output_path = Path(f"{output_name}.md") if output_name else None
        
        success, result = export_session(
            DEFAULT_DB_PATH,
            session,
            output_path=output_path,
        )
        
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
        console.print("[green]✓ Cleared all remembered approvals[/green]")
    
    elif cmd == "/config":
        from craftsman.config.user_config import UserConfig, CONFIG_FILE
        config = UserConfig.load()
        
        if not arg:
            # Show current config
            console.print("[bold]Current Configuration:[/bold]")
            for key, value in config.to_display_dict().items():
                console.print(f"  [cyan]{key}[/cyan]: {value}")
            console.print(f"\n[dim]Config file: {CONFIG_FILE}[/dim]")
        
        elif arg == "path":
            console.print(f"[bold]Config file:[/bold] {CONFIG_FILE}")
            if CONFIG_FILE.exists():
                console.print("[green]✓ File exists[/green]")
            else:
                console.print("[yellow]File does not exist (using defaults)[/yellow]")
        
        elif arg.startswith("set "):
            # Parse key=value
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
                    console.print(f"[green]✓ {message} (saved to config file)[/green]")
                else:
                    console.print(f"[yellow]✓ {message} (could not save - PyYAML not installed?)[/yellow]")
            else:
                console.print(f"[red]✗ {message}[/red]")
        
        else:
            console.print(f"[yellow]Unknown config subcommand: {arg}[/yellow]")
            console.print("[dim]Usage: /config, /config set key=value, /config path[/dim]")
    
    else:
        console.print(f"[yellow]Unknown command: {cmd}. Type /help for available commands.[/yellow]")


@app.command()
def chat(
    model: str = typer.Option(None, "--model", "-m", help="Model name override"),
    session: str = typer.Option("default", "--session", "-s", help="Session ID for conversation persistence"),
    agent: str = typer.Option("coder", "--agent", "-a", help="Agent mode (coder/researcher/planner)"),
    no_persist: bool = typer.Option(False, "--no-persist", help="Disable session persistence"),
    advanced: bool = typer.Option(False, "--advanced", help="Use advanced agent with permissions & doom loop detection"),
    policy: str = typer.Option("ask", "--policy", help="Approval policy: ask, auto, yolo, never"),
):
    """Start an interactive chat session with the coding agent."""
    # Load user config and merge with CLI args
    from craftsman.config import get_config
    user_config = get_config()

    # CLI args override config file (use config if CLI has default values)
    model = model or user_config.model
    agent = agent if agent != "coder" else user_config.agent
    policy = policy if policy != "ask" else user_config.policy
    advanced = advanced or user_config.advanced
    session = session if session != "default" else user_config.session
    no_persist = no_persist or user_config.no_persist
    
    # Validate agent
    available_agents = list_available_agents()
    if agent not in available_agents:
        console.print(f"[red]Error: Unknown agent '{agent}'. Available: {', '.join(available_agents)}[/red]")
        raise typer.Exit(1)
    
    mode_label = f"{agent} mode" + (" [advanced]" if advanced else "")
    policy_label = policy if advanced else "n/a"
    
    # Use rich TUI for welcome
    tui = get_tui()
    tui.print_welcome(
        agent_mode=mode_label,
        session=session,
        policy=policy_label,
        persistence="disabled" if no_persist else "enabled",
    )
    
    # Initialize hooks system from config
    hook_system = None
    if user_config.hooks:
        hooks_list = []
        for trigger_name, commands in user_config.hooks.items():
            try:
                trigger = HookTrigger(trigger_name)
                for cmd in commands:
                    hooks_list.append(HookConfig(
                        trigger=trigger,
                        command=cmd,
                        enabled=True,
                    ))
            except ValueError:
                console.print(f"[yellow]Warning: Unknown hook trigger '{trigger_name}'[/yellow]")
        
        if hooks_list:
            hook_config = HookSystemConfig(enabled=True, hooks=hooks_list)
            hook_system = HookSystem(hook_config)
            console.print(f"[dim]Loaded {len(hooks_list)} hook(s)[/dim]")
    
    # Choose agent builder based on --advanced flag
    if advanced:
        agent_graph = build_advanced_agent(
            agent_name=agent,
            model_name=model,
            in_memory=no_persist,
            approval_policy=policy,
            hook_system=hook_system,
        )
    else:
        agent_graph = build_agent(
            agent_name=agent,
            model_name=model,
            in_memory=no_persist,
        )
    config = {"configurable": {"thread_id": session}}
    
    while True:
        try:
            user_input = console.input("\n[bold green]You:[/bold green] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        
        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]Goodbye![/yellow]")
            break
        
        if not user_input.strip():
            continue
        
        # Handle slash commands
        if user_input.startswith("/"):
            _handle_slash_command(user_input, session, no_persist, console)
            continue
        
        console.print("\n[bold blue]Agent:[/bold blue]")
        
        try:
            # Run with streaming
            asyncio.run(_stream_response(agent_graph, user_input, config))
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def _stream_response(agent, user_input: str, config: dict):
    """Stream agent response with real-time output using Rich TUI."""
    tui = get_tui()
    current_tool_id = None
    current_tool_name = None
    
    tui.begin_assistant()
    
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
            
            # Handle different output types
            if hasattr(output, "content"):
                output = output.content
            elif not isinstance(output, str):
                output = str(output)
            
            tui.tool_end(tool_name, run_id, output, success=True)
            current_tool_id = None
            current_tool_name = None
    
    tui.end_response()


@app.command()
def run(
    prompt: str = typer.Argument(..., help="The task for the agent to perform"),
    model: str = typer.Option(None, "--model", "-m", help="Model name override"),
    agent: str = typer.Option("coder", "--agent", "-a", help="Agent mode"),
):
    """Run a single prompt and exit."""
    agent_graph = build_agent(
        agent_name=agent,
        model_name=model,
        in_memory=True,  # No persistence for one-shot
    )
    config = {"configurable": {"thread_id": "oneshot"}}
    
    console.print(f"[dim]Running ({agent} mode): {prompt}[/dim]\n")
    
    try:
        asyncio.run(_stream_response(agent_graph, prompt, config))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def agents():
    """List available agent modes."""
    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Mode", style="green")
    table.add_column("Description")
    
    from craftsman.agents.config import AGENT_CONFIGS
    
    for name, config in AGENT_CONFIGS.items():
        table.add_row(name, config.mode, config.description)
    
    console.print(table)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
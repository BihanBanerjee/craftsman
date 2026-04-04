"""Rich TUI for craftsman.

Provides beautiful terminal output with:
- Custom theme with color-coded styles
- Tool call panels with syntax highlighting
- Diff rendering for file edits
- Language detection from file extensions
"""

from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.syntax import Syntax


# Custom theme for the agent
AGENT_THEME = Theme({
    # General
    "info": "cyan",
    "warning": "yellow",
    "error": "bright_red bold",
    "success": "green",
    "dim": "dim",
    "muted": "grey50",
    "border": "grey35",
    "highlight": "bold cyan",
    # Roles
    "user": "bright_blue bold",
    "assistant": "bright_white",
    # Tools
    "tool": "bright_magenta bold",
    "tool.read": "cyan",
    "tool.write": "yellow",
    "tool.shell": "magenta",
    "tool.search": "bright_blue",
    "tool.memory": "green",
    # Code
    "code": "white",
})


# Language detection from file extension
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".css": "css",
    ".html": "html",
    ".xml": "xml",
    ".sql": "sql",
    ".rb": "ruby",
    ".php": "php",
}


def guess_language(path: str | None) -> str:
    """Guess programming language from file path."""
    if not path:
        return "text"
    suffix = Path(path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, "text")


def get_tool_kind(tool_name: str) -> str:
    """Get the tool kind for styling."""
    if tool_name in ("read_file", "grep", "glob_files"):
        return "read"
    elif tool_name in ("write_file", "edit_file"):
        return "write"
    elif tool_name in ("run_bash",):
        return "shell"
    elif tool_name in ("web_search", "web_fetch"):
        return "search"
    elif tool_name in ("memory", "todo"):
        return "memory"
    return "read"


class TUI:
    """Rich Terminal UI for craftsman."""
    
    def __init__(self, console: Console | None = None):
        self.console = console or Console(theme=AGENT_THEME, highlight=False)
        self._tool_args: dict[str, dict[str, Any]] = {}
        self._max_output_lines = 50
    
    def print_welcome(
        self,
        agent_mode: str,
        session: str,
        policy: str,
        persistence: str,
    ) -> None:
        """Print welcome banner."""
        self.console.print(Panel(
            Text.assemble(
                ("Craftsman", "highlight"),
                f" ({agent_mode} mode)\n\n",
                ("Session: ", "muted"), (session, "info"), "\n",
                ("Policy: ", "muted"), (policy, "info"), "\n",
                ("Persistence: ", "muted"), (persistence, "info"), "\n\n",
                ("Type ", "muted"), ("/help", "highlight"), (" for commands or ", "muted"),
                ("exit", "highlight"), (" to quit.", "muted"),
            ),
            title=Text("Welcome", style="highlight"),
            title_align="left",
            border_style="border",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
    
    def print_user_prompt(self) -> str:
        """Print user prompt and get input."""
        self.console.print()
        return self.console.input("[user]You:[/user] ")
    
    def begin_assistant(self) -> None:
        """Begin assistant response section."""
        self.console.print()
        self.console.print(Rule(Text("Assistant", style="assistant")))
    
    def stream_text(self, text: str) -> None:
        """Stream text output (no newline)."""
        self.console.print(text, end="", markup=False)
    
    def end_response(self) -> None:
        """End response with newline."""
        self.console.print()
    
    def tool_start(self, tool_name: str, call_id: str, args: dict[str, Any]) -> None:
        """Display tool call start panel."""
        self._tool_args[call_id] = args
        kind = get_tool_kind(tool_name)
        border_style = f"tool.{kind}"
        
        # Build title
        title = Text.assemble(
            ("⏺ ", "muted"),
            (tool_name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )
        
        # Build args table
        if args:
            table = Table.grid(padding=(0, 1))
            table.add_column(style="muted", justify="right", no_wrap=True)
            table.add_column(style="code", overflow="fold")
            
            for key, value in args.items():
                # Truncate long values
                if isinstance(value, str) and len(value) > 100:
                    value = f"<{len(value)} chars>"
                table.add_row(key, str(value))
            
            content = table
        else:
            content = Text("(no args)", style="muted")
        
        panel = Panel(
            content,
            title=title,
            title_align="left",
            subtitle=Text("running", style="muted"),
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)
    
    def tool_end(
        self,
        tool_name: str,
        call_id: str,
        output: str,
        success: bool = True,
    ) -> None:
        """Display tool call result panel."""
        kind = get_tool_kind(tool_name)
        border_style = f"tool.{kind}"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"
        
        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (tool_name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )
        
        # Get args for context
        args = self._tool_args.get(call_id, {})
        
        # Build output blocks
        blocks = []
        
        # Detect file path for syntax highlighting
        file_path = args.get("file_path", args.get("path"))
        
        if tool_name == "read_file" and success and file_path:
            # Syntax highlight file content
            lang = guess_language(file_path)
            lines = output.split("\n")
            if len(lines) > self._max_output_lines:
                output = "\n".join(lines[:self._max_output_lines])
                output += f"\n... ({len(lines) - self._max_output_lines} more lines)"
            
            blocks.append(Text(f"{file_path}", style="muted"))
            blocks.append(Syntax(
                output,
                lang,
                theme="monokai",
                line_numbers=True,
                word_wrap=False,
            ))
        
        elif tool_name in ("write_file", "edit_file") and success:
            # Check if output contains a diff block
            if "```diff" in output:
                # Extract and render the diff
                parts = output.split("```diff")
                message = parts[0].strip()
                if message:
                    blocks.append(Text(message, style="success"))
                
                if len(parts) > 1:
                    diff_content = parts[1].split("```")[0].strip()
                    blocks.append(Syntax(
                        diff_content,
                        "diff",
                        theme="monokai",
                        word_wrap=True,
                    ))
            else:
                blocks.append(Text(output, style="success"))
        
        elif tool_name == "run_bash":
            # Show command and output
            command = args.get("command", "")
            if command:
                blocks.append(Text(f"$ {command}", style="muted"))
            blocks.append(Syntax(
                output[:2000] if len(output) > 2000 else output,
                "text",
                theme="monokai",
                word_wrap=True,
            ))
        
        else:
            # Generic output
            if output.strip():
                lines = output.split("\n")
                if len(lines) > self._max_output_lines:
                    output = "\n".join(lines[:self._max_output_lines])
                    output += f"\n... ({len(lines) - self._max_output_lines} more lines)"
                blocks.append(Syntax(
                    output,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                ))
            else:
                blocks.append(Text("(no output)", style="muted"))
        
        panel = Panel(
            Group(*blocks) if blocks else Text("(no output)", style="muted"),
            title=title,
            title_align="left",
            subtitle=Text("done" if success else "failed", style=status_style),
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)
    
    def print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(f"[error]{message}[/error]")
    
    def print_warning(self, message: str) -> None:
        """Print warning message."""
        self.console.print(f"[warning]{message}[/warning]")
    
    def print_success(self, message: str) -> None:
        """Print success message."""
        self.console.print(f"[success]{message}[/success]")
    
    def print_info(self, message: str) -> None:
        """Print info message."""
        self.console.print(f"[info]{message}[/info]")


# Global TUI instance
_tui: TUI | None = None


def get_tui() -> TUI:
    """Get or create the global TUI instance."""
    global _tui
    if _tui is None:
        _tui = TUI()
    return _tui

"""Core tools for the coding agent."""

from pathlib import Path
import subprocess
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class ReadFileInput(BaseModel):
    """Input schema for read_file tool."""
    file_path: str = Field(description="Absolute path to the file to read")
    start_line: int | None = Field(default=None, description="Start line (1-indexed, optional)")
    end_line: int | None = Field(default=None, description="End line (1-indexed, optional)")


class WriteFileInput(BaseModel):
    """Input schema for write_file tool."""
    file_path: str = Field(description="Path to the file to create/overwrite")
    content: str = Field(description="Content to write to the file")

class EditFileInput(BaseModel):
    """Input schema for edit_file tool."""
    file_path: str = Field(description="Path to the file to edit")
    old_content: str = Field(description="Exact text to replace (must match exactly)")
    new_content: str = Field(description="New text to replace with")

class BashInput(BaseModel):
    """Input schema for run_bash tool."""
    command: str = Field(description="Shell command to execute")
    working_dir: str = Field(default=".", description="Working directory for the command")

class GrepInput(BaseModel):
    """Input schema for grep tool."""
    pattern: str = Field(description="Pattern to search for")
    path: str = Field(description="File or directory path to search in")
    case_insensitive: bool = Field(default=False, description="Case insensitive search")

class GlobInput(BaseModel):
    """Input schema for glob tool."""
    pattern: str = Field(description="Glob pattern (e.g., '**/*.py')")
    path: str = Field(default=".", description="Base directory to search from")


@tool(args_schema=ReadFileInput)
def read_file(file_path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read the contents of a file. Optionally specify line range."""
    try:
        content = Path(file_path).read_text()
        lines = content.splitlines()
        
        if start_line is not None and end_line is not None:
            lines = lines[start_line - 1:end_line]
        elif start_line is not None:
            lines = lines[start_line - 1:]
        
        return "\n".join(lines)
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error reading file: {e}"


@tool(args_schema=WriteFileInput)
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(args_schema=EditFileInput)
def edit_file(file_path: str, old_content: str, new_content: str) -> str:
    """Edit a file by replacing exact text. The old_content must match exactly.
    
    Returns a unified diff showing the changes made.
    """
    import difflib
    
    try:
        path = Path(file_path)
        content = path.read_text()
        
        if old_content not in content:
            return f"Error: Could not find the specified text to replace in {file_path}"
        
        if content.count(old_content) > 1:
            return f"Error: Found multiple occurrences of the text. Please be more specific."
        
        new_file_content = content.replace(old_content, new_content, 1)
        path.write_text(new_file_content)
        
        # Generate unified diff
        old_lines = content.splitlines(keepends=True)
        new_lines = new_file_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            lineterm="",
        )
        diff_text = "".join(diff)
        
        if diff_text:
            return f"Successfully edited {file_path}\n\n```diff\n{diff_text}\n```"
        else:
            return f"Successfully edited {file_path} (no visible changes)"
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error editing file: {e}"


@tool(args_schema=BashInput)
def run_bash(command: str, working_dir: str = ".") -> str:
    """Execute a bash command and return the output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        return f"Exit code: {result.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds"
    except Exception as e:
        return f"Error executing command: {e}"

@tool(args_schema=GrepInput)
def grep(pattern: str, path: str, case_insensitive: bool = False) -> str:
    """
    Search for a pattern in files using grep.
    """
    try:
        flags = "-rn"
        if case_insensitive:
            flags += "i"
        result = subprocess.run(
            f"grep {flags} '{pattern}' {path}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return result.stdout
        elif result.returncode == 1:
            return "No matches found"
        else:
            return f"Error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Search timed out"
    except Exception as e:
        return f"Error during search: {e}"

@tool(args_schema=GlobInput)
def glob_files(pattern: str, path:str = ".") -> str:
    """Find files matching a glob pattern."""
    try:
        base_path = Path(path)
        matches = list(base_path.glob(pattern))

        if not matches:
            return "No files found matching pattern"
        
        return "\n".join(str(m) for m in sorted(matches)[:50]) # Limit to 50
    except Exception as e:
        return f"Error during glob: {e}"

# Export core tools (web tools are added by agent builder for lazy loading)
TOOLS = [read_file, write_file, edit_file, run_bash, grep, glob_files]


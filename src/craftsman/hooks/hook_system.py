"""Hook system for executing scripts at trigger points.

Allows users to run custom scripts before/after agent runs or tool calls.
Inpired by Claude Code Hooks.
"""

import asyncio
import json
import os
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class HookTrigger(Enum):
    """When to trigger a hook."""
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"




@dataclass
class HookConfig:
    """Configuration for a single hook."""
    trigger: HookTrigger
    command: str | None = None # Shell command to run
    script: str | None = None # Inline script content
    timeout_sec: float = 30.0
    enabled: bool = True


@dataclass
class HookSystemConfig:
    """Global hooks configuration."""
    enabled: bool = True
    hooks: list[HookConfig] = field(default_factory=list)
    cwd: Path = field(default_factory=Path.cwd)


class HookSystem:
    """System for managing and executing hooks.

    Hooks can be triggered at various points:
    - BEFORE_AGENT: Before the agent processes a message
    - AFTER_AGENT: After the agent completes a response
    - BEFORE_TOOL: Before a tool is executed
    - AFTER_TOOL: After a tool completes
    - ON_ERROR: When an error occurs

    Environment variables passed to hooks:
    - AI_AGENT_TRIGGER: The trigger type
    - AI_AGENT_CWD: Working directory
    - AI_AGENT_TOOL_NAME: Tool name (for tool triggers)
    - AI_AGENT_TOOL_PARAMS: Tool parameters as JSON
    - AI_AGENT_USER_MESSAGE: User's message
    - AI_AGENT_RESPONSE: Agent's response
    - AI_AGENT_ERROR: Error message (for error trigger)
    """

    def __init__(self, config: HookSystemConfig | None = None):
        self.config = config or HookSystemConfig()
        self.hooks:list[HookConfig] = []
        if self.config.enabled:
            self.hooks = [h for h in self.config.hooks if h.enabled]
    
    async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
        """Run a single hook."""
        try:
            if hook.command:
                await self._run_command(hook.command, hook.timeout_sec, env)
            elif hook.script:
                # Write script to temp file and execute
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False
                ) as f:
                    f.write("#!/bin/bash\n")
                    f.write(hook.script)
                    script_path = f.name
                
                try:
                    os.chmod(script_path, 0o755)
                    await self._run_command(script_path, hook.timeout_sec, env)
                finally:
                    os.unlink(script_path)
        
        except Exception as e:
            # Hooks should not crash the agent
            print(f"[Hook error] {e}")
        
    
    async def _run_command(
        self,
        command: str,
        timeout: float,
        env: dict[str, str],
    ) -> None:
        """Run a command with timeout."""
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # stdout=asyncio.subprocess.PIPE – Captures the command's standard output (normal output) into a pipe that Python can read
            # stderr=asyncio.subprocess.PIPE – Captures the command's standard error (error messages) into a pipe that Python can read
            # What PIPE means: Instead of letting the output print to the terminal, it's redirected into a buffer that the parent process can access via process.communicate().
            cwd=str(self.config.cwd),
            env=env,
            start_new_session=True,
        )

        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # Kill the process group on timeout
            if sys.platform != "win32":
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            await process.wait()
    

    def _build_env(
            self,
            trigger: HookTrigger,
            tool_name: str | None = None,
            tool_params: dict[str, Any] | None = None,
            user_message: str | None = None,
            agent_response: str | None = None,
            error: Exception | None = None,

    ) -> dict[str, str]:
        """Build environment variables from hook execution."""
        env = os.environ.copy()
        env["AI_AGENT_TRIGGER"] = trigger.value
        env["AI_AGENT_CWD"] = str(self.config.cwd)


        if tool_name:
            env["AI_AGENT_TOOL_NAME"] = tool_name
        if tool_params:
            env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        if user_message:
            env["AI_AGENT_USER_MESSAGE"] = user_message
        if agent_response:
            env["AI_AGENT_RESPONSE"] = agent_response
        if error:
            env["AI_AGENT_ERROR"] = str(error)
        
        return env
    
    async def trigger_before_agent(self, user_message: str) -> None:
        """Trigger hooks before agent processes a message."""
        env = self._build_env(HookTrigger.BEFORE_AGENT, user_message=user_message)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook, env) 

    async def trigger_after_agent(self, user_message: str, agent_response: str) -> None:
        """Trigger hooks after agent completes a response."""
        env = self._build_env(
            HookTrigger.AFTER_AGENT,
            user_message=user_message,
            agent_response=agent_response,
        )
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT:
                await self._run_hook(hook, env)
    
    async def trigger_before_tool(self, tool_name: str, tool_params: dict[str, Any]) -> None:
        """Trigger hooks before a tool is executed."""
        env = self._build_env(
            HookTrigger.BEFORE_TOOL,
            tool_name=tool_name,
            tool_params=tool_params,
        )
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL:
                await self._run_hook(hook, env)

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: str,
    ) -> None:
        """Trigger hooks after a tool completes."""
        env = self._build_env(
            HookTrigger.AFTER_TOOL,
            tool_name=tool_name,
            tool_params=tool_params,
        )
        env["AI_AGENT_TOOL_RESULT"] = tool_result
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL:
                await self._run_hook(hook, env)
    
    async def trigger_on_error(self, error: Exception) -> None:
        """Trigger hooks when an error occurs."""
        env = self._build_env(HookTrigger.ON_ERROR, error=error)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._run_hook(hook, env)
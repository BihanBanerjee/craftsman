"""Tests for craftsman core functionality."""

import pytest
from pathlib import Path


class TestToolsCore:
    """Tests for core tools."""
    
    def test_tools_import(self):
        """Test that core tools can be imported."""
        from craftsman.tools.core import TOOLS, read_file, write_file, edit_file, run_bash, grep, glob_files
        
        assert len(TOOLS) == 6
        assert read_file is not None
        assert write_file is not None
    
    def test_tools_have_names(self):
        """Test that all tools have names."""
        from craftsman.tools.core import TOOLS
        
        tool_names = [t.name for t in TOOLS]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names
        assert "run_bash" in tool_names
        assert "grep" in tool_names
        assert "glob_files" in tool_names


class TestAgentConfig:
    """Tests for agent configuration."""
    
    def test_agent_configs_exist(self):
        """Test that agent configs are defined."""
        from craftsman.agents.config import AGENT_CONFIGS
        
        assert "coder" in AGENT_CONFIGS
        assert "researcher" in AGENT_CONFIGS
        assert "planner" in AGENT_CONFIGS
        assert "reviewer" in AGENT_CONFIGS
    
    def test_get_agent_config(self):
        """Test getting agent config by name."""
        from craftsman.agents.config import get_agent_config
        
        coder = get_agent_config("coder")
        assert coder.name == "coder"
        assert coder.mode == "primary"
        assert len(coder.tools) == 6
    
    def test_get_agent_config_invalid(self):
        """Test that invalid agent name raises error."""
        from craftsman.agents.config import get_agent_config
        
        with pytest.raises(ValueError):
            get_agent_config("nonexistent")
    
    def test_reviewer_is_readonly(self):
        """Test that reviewer agent only has read-only tools."""
        from craftsman.agents.config import get_agent_config
        
        reviewer = get_agent_config("reviewer")
        tool_names = [t.name for t in reviewer.tools]
        
        assert "read_file" in tool_names
        assert "grep" in tool_names
        assert "write_file" not in tool_names
        assert "run_bash" not in tool_names


class TestPermissionSystem:
    """Tests for permission system."""
    
    def test_permission_action_enum(self):
        """Test PermissionAction enum values."""
        from craftsman.permission import PermissionAction
        
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.DENY.value == "deny"
        assert PermissionAction.ASK.value == "ask"
    
    def test_approval_policy_enum(self):
        """Test ApprovalPolicy enum values."""
        from craftsman.permission import ApprovalPolicy
        
        assert ApprovalPolicy.ASK.value == "ask"
        assert ApprovalPolicy.AUTO.value == "auto"
        assert ApprovalPolicy.YOLO.value == "yolo"
        assert ApprovalPolicy.NEVER.value == "never"
    
    def test_apply_policy_yolo(self):
        """Test that YOLO policy auto-approves ASK actions."""
        from craftsman.permission import apply_policy, PermissionAction, ApprovalPolicy
        
        result = apply_policy(PermissionAction.ASK, ApprovalPolicy.YOLO)
        assert result == PermissionAction.ALLOW
    
    def test_apply_policy_never(self):
        """Test that NEVER policy denies ASK actions."""
        from craftsman.permission import apply_policy, PermissionAction, ApprovalPolicy
        
        result = apply_policy(PermissionAction.ASK, ApprovalPolicy.NEVER)
        assert result == PermissionAction.DENY
    
    def test_apply_policy_deny_always_respected(self):
        """Test that DENY is always respected regardless of policy."""
        from craftsman.permission import apply_policy, PermissionAction, ApprovalPolicy
        
        result = apply_policy(PermissionAction.DENY, ApprovalPolicy.YOLO)
        assert result == PermissionAction.DENY


class TestHooksSystem:
    """Tests for hooks system."""
    
    def test_hook_trigger_enum(self):
        """Test HookTrigger enum values."""
        from craftsman.hooks import HookTrigger
        
        assert HookTrigger.BEFORE_TOOL.value == "before_tool"
        assert HookTrigger.AFTER_TOOL.value == "after_tool"
        assert HookTrigger.BEFORE_AGENT.value == "before_agent"
        assert HookTrigger.AFTER_AGENT.value == "after_agent"
        assert HookTrigger.ON_ERROR.value == "on_error"
    
    def test_hook_system_instance(self):
        """Test HookSystem can be instantiated."""
        from craftsman.hooks import HookSystem
        
        hooks = HookSystem()
        assert hooks is not None


class TestTUI:
    """Tests for Rich TUI."""
    
    def test_tui_import(self):
        """Test TUI can be imported."""
        from craftsman.ui import TUI, get_tui, AGENT_THEME
        
        assert TUI is not None
        assert AGENT_THEME is not None
    
    def test_tui_singleton(self):
        """Test get_tui returns same instance."""
        from craftsman.ui import get_tui
        
        tui1 = get_tui()
        tui2 = get_tui()
        assert tui1 is tui2
    
    def test_language_detection(self):
        """Test language detection from file path."""
        from craftsman.ui.tui import guess_language
        
        assert guess_language("test.py") == "python"
        assert guess_language("test.js") == "javascript"
        assert guess_language("test.ts") == "typescript"
        assert guess_language("test.unknown") == "text"
        assert guess_language(None) == "text"


class TestMemoryTool:
    """Tests for memory tool."""
    
    def test_memory_import(self):
        """Test memory tool can be imported."""
        from craftsman.tools.memory import memory
        
        assert memory is not None
        assert memory.name == "memory"


class TestTodoTool:
    """Tests for todo tool."""
    
    def test_todo_import(self):
        """Test todo tool can be imported."""
        from craftsman.tools.todo import todo
        
        assert todo is not None
        assert todo.name == "todo"


class TestCheckpoints:
    """Tests for checkpoint system."""
    
    def test_checkpoint_functions_import(self):
        """Test checkpoint functions can be imported."""
        from craftsman.graph.checkpoints import list_checkpoints, format_checkpoint_table, get_session_count
        
        assert list_checkpoints is not None
        assert format_checkpoint_table is not None
        assert get_session_count is not None
    
    def test_format_empty_checkpoints(self):
        """Test formatting empty checkpoint list."""
        from craftsman.graph.checkpoints import format_checkpoint_table
        
        result = format_checkpoint_table([])
        assert "No checkpoints found" in result

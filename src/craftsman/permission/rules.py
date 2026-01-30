"""Permission rules for tool execution.

Implements OpenCode-style permission system with allow/deny/ask actions.
Includes session-level approval memory for "remember this decision" feature.
Supports approval policies: ask, auto, yolo, never.
"""

from enum import Enum
from dataclasses import dataclass
from fnmatch import fnmatch

class PermissionAction(Enum):
    """Action to take for a permission check."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class ApprovalPolicy(Enum):
    """Approval policy for the session.

    - ask: Prompt user for each dangerous action (default)
    - auto: Auto-approve safe actions, ask for dangerous
    - yolo: Auto-approve everything (full trust mode)
    - never: Deny all dangerous actions (read-only mode)
    """
    ASK = "ask"
    AUTO = "auto"
    YOLO = "yolo"
    NEVER = "never"


def apply_policy(action: PermissionAction, policy: ApprovalPolicy) -> PermissionAction:
    """Apply approval policy to modify the permission action.

    Args:
        action: The original permission action from rules
        policy: The session's approval policy
    
    Returns:
        Modified action based on policy
    """

    if action == PermissionAction.DENY:
        # DENY is always respected regardless of policy
        return PermissionAction.DENY
    
    if action == PermissionAction.ALLOW:
        # ALLOW is respected unless policy is NEVER
        if policy == ApprovalPolicy.NEVER:
            return PermissionAction.DENY
        return PermissionAction.ALLOW
    
    # action == PermissionAction.ASK
    if policy == ApprovalPolicy.YOLO:
        return PermissionAction.ALLOW
    elif policy == ApprovalPolicy.AUTO:
        return PermissionAction.ALLOW  # Auto-approve in AUTO mode
    elif policy == ApprovalPolicy.NEVER:
        return PermissionAction.DENY
    else:  # ASK policy
        return PermissionAction.ASK
    

@dataclass
class PermissionRule:
    """A permission rule that matches tools and patterns.

    Attributes:
        permission: Tool name or category (e.g., "bash", "edit", "*")
        pattern: Glob pattern for matching args (e.g., "*.py", "*")
        action: What to do when matched
    """
    permission: str
    pattern: str
    action: PermissionAction


# Default permission rules (order matters - last match wins)
DEFAULT_RULES: list[PermissionRule] = [
    # Allow everything by default
    PermissionRule("*", "*", PermissionAction.ALLOW),


    # Ask before destructive operations
    PermissionRule("write", "*", PermissionAction.ASK),
    PermissionRule("edit", "*", PermissionAction.ASK),
    PermissionRule("bash", "*", PermissionAction.ASK),


    # Deny reading sensitive files
    PermissionRule("read", "*.env", PermissionAction.DENY),
    PermissionRule("read", "*.env.*", PermissionAction.DENY),
    PermissionRule("read", "*.env.example", PermissionAction.ALLOW),
]


# ============================================================================
# Session-level approval memory
# ============================================================================

# Cache for session-scoped approvals (cleared on new session)
_session_approvals: dict[str, PermissionAction] = {}

def _make_approval_key(tool: str, pattern: str) -> str:
    """Create a unique key for tool+pattern combo."""
    return f"{tool}:{pattern}"


def remember_approval(tool: str, pattern: str, action: PermissionAction) -> None:
    """Remember an approval decision for this session.
    
    Args:
        tool: Tool name that was approved/denied
        pattern: Pattern (e.g., file path) that was approved/denied
        action: The action to remember (ALLOW or DENY)
    """
    key = _make_approval_key(tool, pattern)
    _session_approvals[key] = action


def get_remembered_approval(tool: str, pattern: str) -> PermissionAction | None:
    """Check if we already have a remembered approval for this tool+pattern.
    
    Args:
        tool: Tool name to check
        pattern: Pattern to check
    
    Returns:
        The remembered action, or None if not found
    """
    key = _make_approval_key(tool, pattern)
    return _session_approvals.get(key)

def clear_session_approvals() -> None:
    """Clear all remembered approvals (call when starting new session)."""
    _session_approvals.clear()


def list_session_approvals() -> dict[str, PermissionAction]:
    """List all current session approvals (for debugging/UI)."""
    return dict(_session_approvals)



# ============================================================================
# Permission evaluation
# ============================================================================


def evaluate_permission(
        tool_name: str,
        pattern: str = "*",
        rules: list[PermissionRule] | None = None,
        check_memory: bool = True,
) -> PermissionAction:
    """Evaluate permission for a tool call.
    
    Uses "last match wins" semantics like OpenCode.
    Checks session memory first for remembered approvals.
    
    Args:
        tool_name: Name of the tool being called
        pattern: Pattern to match against (e.g., file path)
        rules: Permission rules to evaluate (defaults to DEFAULT_RULES)
        check_memory: Whether to check session memory first
    
    Returns:
        PermissionAction indicating what to do
    """
    # Check session memory first (if enabled)
    if check_memory:
        remembered = get_remembered_approval(tool_name, pattern)
        if remembered is not None:
            return remembered
    
    if rules is None:
        rules = DEFAULT_RULES
    
    result = PermissionAction.ASK   # Default to ask if no rules match

    for rule in rules:
        # Check if tool matches
        if fnmatch(tool_name, rule.permission) or fnmatch(rule.permission, tool_name):
            # Check if pattern matches
            if fnmatch(pattern, rule.pattern) or rule.pattern == "*":
                result = rule.action
    
    return result


def merge_rules(*rulesets: list[PermissionRule]) -> list[PermissionRule]:
    """Merge multiple rulesets. Later rules override earlier ones."""
    merged = []
    for ruleset in rulesets:
        merged.extend(ruleset)
    return merged

# "last match wins" combined with merge_rules.


# Agent-specific permission overrides
AGENT_PERMISSIONS: dict[str, list[PermissionRule]] = {
    "coder": [
        # Coder has full access
    ],
    "researcher": [
        # Researcher is read-only
        PermissionRule("write", "*", PermissionAction.DENY),
        PermissionRule("edit", "*", PermissionAction.DENY),
        PermissionRule("bash", "*", PermissionAction.ASK),  # Ask for bash
    ],
    "planner": [
        # Planner can only write to plan files
        PermissionRule("write", "*", PermissionAction.DENY),
        PermissionRule("write", "*.md", PermissionAction.ALLOW),
        PermissionRule("write", "*plan*", PermissionAction.ALLOW),
        PermissionRule("edit", "*", PermissionAction.DENY),
    ],
}


def get_agent_rules(agent_name: str) -> list[PermissionRule]:
    """Get permission rules for a specific agent."""
    base_rules = DEFAULT_RULES.copy()
    agent_rules = AGENT_PERMISSIONS.get(agent_name, [])
    return merge_rules(base_rules, agent_rules)













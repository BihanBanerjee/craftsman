"""User configuration management.

Loads user preferences from ~/.craftsman/config.yaml and provides
defaults that can be overridden by CLI arguments.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

CONFIG_DIR = Path.home() / ".craftsman"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class UserConfig:
    """User configuration with defaults."""
    model: str | None = None
    agent: str = "coder"
    policy: str = "ask"
    advanced: bool = False
    session: str = "default"
    no_persist: bool = False

    # Hooks configuration
    hooks: dict[str, list[str]] = field(default_factory=dict)
    
    @classmethod
    def load(cls) -> "UserConfig":
        """Load config from file, falling back to defaults."""
        if not CONFIG_FILE.exists():
            return cls()
        
        try:
            with open(CONFIG_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
            
            return cls(
                model=data.get("model"),
                agent=data.get("agent", "coder"),
                policy=data.get("policy", "ask"),
                advanced=data.get("advanced", False),
                session=data.get("session", "default"),
                no_persist=data.get("no_persist", False),
                hooks=data.get("hooks", {}),
            )
        except Exception:
            # If config is malformed, use defaults
            return cls()
    
    def save(self) -> bool:
        """Save current config to file.
        
        Returns:
            True if saved successfully, False otherwise.
        """
        
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            
            data: dict[str, Any] = {
                "agent": self.agent,
                "policy": self.policy,
                "advanced": self.advanced,
            }
            
            # Only save non-default values
            if self.model:
                data["model"] = self.model
            if self.session != "default":
                data["session"] = self.session
            if self.no_persist:
                data["no_persist"] = self.no_persist
            if self.hooks:
                data["hooks"] = self.hooks
            
            with open(CONFIG_FILE, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            
            return True
        except Exception:
            return False
    
    def set_value(self, key: str, value: str) -> tuple[bool, str]:
        """Set a configuration value.

        Args:
            key: Configuration key (model, agent, policy, advanced, session, no_persist)
            value: New value as string

        Returns:
            Tuple of (success, message)
        """
        valid_keys = {
            "agent": ["coder", "researcher", "planner", "reviewer"],
            "policy": ["ask", "auto", "yolo", "never"],
            "advanced": ["true", "false"],
            "model": None,  # Any string allowed
            "session": None,
            "no_persist": ["true", "false"],
        }

        if key not in valid_keys:
            return False, f"Unknown key: {key}. Valid keys: {', '.join(valid_keys.keys())}"

        allowed = valid_keys[key]
        if allowed and value.lower() not in allowed:
            return False, f"Invalid value for {key}. Allowed: {', '.join(allowed)}"

        # Set the value
        if key == "model":
            self.model = value if value else None
        elif key == "agent":
            self.agent = value.lower()
        elif key == "policy":
            self.policy = value.lower()
        elif key == "advanced":
            self.advanced = value.lower() == "true"
        elif key == "session":
            self.session = value
        elif key == "no_persist":
            self.no_persist = value.lower() == "true"

        return True, f"Set {key} = {value}"
    
    def to_display_dict(self) -> dict[str, str]:
        """Get config as dictionary for display."""
        return {
            "model": self.model or "(default: sonnet)",
            "agent": self.agent,
            "policy": self.policy,
            "advanced": str(self.advanced).lower(),
            "session": self.session,
            "no_persist": str(self.no_persist).lower(),
            "hooks": f"{len(self.hooks)} trigger(s)" if self.hooks else "(none)",
        }


def get_config() -> UserConfig:
    """Get the current user configuration."""
    return UserConfig.load()
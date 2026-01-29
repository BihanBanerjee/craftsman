"""Context compaction for managing long conversations.

Summarizes old messages when approaching token limits.
Based on OpenCode's compaction approach.
"""

from typing import Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage


# Model-specific context limits
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Aliases (what users pass via --model)
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt4o": 128_000,
    "gpt4o-mini": 128_000,

    # OpenRouter IDs (what llm.py resolves to)
    "anthropic/claude-sonnet-4.5": 200_000,
    "anthropic/claude-opus-4.5": 200_000,
    "anthropic/claude-haiku-4.5": 200_000,
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,
}

# Token limits
DEFAULT_CONTEXT_LIMIT = 200_000  # Default fallback
OUTPUT_RESERVE = 32_000  # Reserve for output
COMPACTION_THRESHOLD = 0.85  # Trigger at 85% usage
RECENT_MESSAGES_TO_KEEP = 10  # Keep last N messages

# Tool output pruning settings
TOOL_OUTPUT_MAX_TOKENS = 4_000  # Max tokens per old tool output
PROTECTED_RECENT_OUTPUTS = 3  # Don't prune last N tool outputs

# Summary prompt for compaction
SUMMARY_PROMPT = (
    "You are summarizing a coding assistant conversation to save context space. "
    "Create a concise summary (max 500 words) that preserves critical context:\n\n"
    "1. **Current Task**: What is the user trying to accomplish?\n"
    "2. **Files Modified**: List files created, edited, or deleted (with brief changes)\n"
    "3. **Files Read**: Key files examined for context\n"
    "4. **Commands Run**: Important shell commands and their outcomes\n"
    "5. **Decisions Made**: Key technical decisions or user preferences\n"
    "6. **Current State**: What's working, what's broken, any blockers\n"
    "7. **Next Steps**: What was planned but not yet done\n\n"
    "Omit pleasantries, redundant exchanges, and tool output details. "
    "Preserve file paths, function names, error messages, and technical specifics."
)

def get_context_limit(model_name: str) -> str:
    """Get context limit for a specific model.

    Args:
        model_name: Name of the model

    Returns:
        Context limit in tokens
    """
    return MODEL_CONTEXT_LIMITS.get(model_name, DEFAULT_CONTEXT_LIMIT)

def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return len(text) // 4


def estimate_message_tokens(message: BaseMessage) -> int:
    """Estimate tokens in a message."""
    content = message.content if isinstance(message.content, str) else str(message.content)
    return estimate_tokens(content) + 10 # +10 for role overhead

def estimate_total_tokens(messages: list[BaseMessage]) -> int:
    """Estimate total tokens in message list."""
    return sum(estimate_message_tokens(m) for m in messages)

def should_compact(
        messages: list[BaseMessage],
        model_name: str | None = None,
        context_limit: int | None = None,
) -> bool:
    """Check if we should compact the conversation.
    
    Args:
        messages: Current conversation messages
        model_name: Model name to get context limit for (optional)
        context_limit: Override context limit (optional)
    
    Returns:
        True if compaction is recommended
    """
    # Determine context limit
    if context_limit is None:
        if model_name:
            context_limit = get_context_limit(model_name)
        else:
            context_limit = DEFAULT_CONTEXT_LIMIT

    usable_limit = context_limit - OUTPUT_RESERVE
    threshold = int(usable_limit * COMPACTION_THRESHOLD)
    current_tokens = estimate_total_tokens(messages)
    return current_tokens > threshold


def prune_tool_outputs(
        messages: list[BaseMessage],
        max_token_per_output: int = TOOL_OUTPUT_MAX_TOKENS,
        protected_count: int = PROTECTED_RECENT_OUTPUTS
) -> list[BaseMessage]:
    """Prune old tool outputs while keeping recent ones intact.
    
    OpenCode's approach: truncate tool outputs older than the protected
    threshold to save context space while preserving recent results.
    
    Args:
        messages: Message history
        max_tokens_per_output: Max tokens to keep per old tool output
        protected_count: Number of recent tool outputs to keep intact
    
    Returns:
        Messages with old tool outputs truncated
    """
    # Count tool messages from the end to identify protected ones
    tool_message_indices = []
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            tool_message_indices.append(i)
    
    # Determine which indices are protected (last N tool messages)
    protected_indices = set(tool_message_indices[-protected_count:]) if tool_message_indices else set()

    # Process messages
    pruned_messages = []
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage) and i not in protected_indices:
            # This is an old tool output - check if it needs truncation
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            token_estimate = estimate_tokens(content)

            if token_estimate > max_token_per_output:
                # Truncate the output 
                max_chars = max_token_per_output * 4 # ~4 chars per token
                truncated_content = content[:max_chars]

                # Create truncated message
                pruned_msg = ToolMessage(
                    content=f"{truncated_content}\n\n[OUTPUT TRUNCATED - {token_estimate - max_token_per_output} tokens removed]",
                    tool_call_id=msg.tool_call_id,
                )
                pruned_messages.append(pruned_msg)
            else:
                pruned_messages.append(msg)
        else:
            pruned_messages.append(msg)
    
    return pruned_messages









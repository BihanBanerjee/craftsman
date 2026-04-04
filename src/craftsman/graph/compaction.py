"""Context compaction for managing long conversations.

Summarizes old messages when approaching token limits.
Based on OpenCode's compaction approach.
"""

import os
from typing import Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage


# Fallback context limits — used when the live OpenRouter lookup fails.
# Keyed by both short alias and full OpenRouter model ID.
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Anthropic Claude
    "sonnet": 1_000_000,
    "opus": 1_000_000,
    "haiku": 200_000,
    "anthropic/claude-sonnet-4.6": 1_000_000,
    "anthropic/claude-opus-4.6": 1_000_000,
    "anthropic/claude-haiku-4.5": 200_000,

    # Google Gemini
    "gemini": 1_000_000,
    "flash": 1_000_000,
    "google/gemini-2.5-pro": 1_000_000,
    "google/gemini-2.5-flash": 1_000_000,

    # OpenAI
    "gpt4o": 128_000,
    "gpt4o-mini": 128_000,
    "gpt5": 1_000_000,
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,
    "openai/gpt-5.4": 1_000_000,

    # DeepSeek
    "deepseek": 64_000,
    "deepseek/deepseek-chat": 64_000,

    # Mistral
    "mistral": 128_000,
    "mistralai/devstral-small-2503": 128_000,
}

# Token limits
DEFAULT_CONTEXT_LIMIT = 200_000  # Conservative fallback when model is unknown
OUTPUT_RESERVE = 32_000          # Reserve for model output tokens
COMPACTION_THRESHOLD = 0.85      # Trigger compaction at 85% usage
RECENT_MESSAGES_TO_KEEP = 10     # Keep last N messages intact after compaction

# Tool output pruning settings
TOOL_OUTPUT_MAX_TOKENS = 4_000   # Max tokens per old tool output
PROTECTED_RECENT_OUTPUTS = 3     # Don't prune last N tool outputs

# Runtime cache for live OpenRouter context limits.
# Populated on first use per model; never re-queried in the same process.
_live_context_cache: dict[str, int] = {}


def _fetch_live_context_limit(model_id: str) -> int | None:
    """Query OpenRouter for the actual context window of a model.

    Called at most once per model per process — result is cached in
    _live_context_cache. Returns None on any network or parse failure
    so callers can fall back to the hardcoded dict.

    Args:
        model_id: Full OpenRouter model ID (e.g. "anthropic/claude-sonnet-4.6")

    Returns:
        Context window size in tokens, or None if unavailable.
    """
    if model_id in _live_context_cache:
        return _live_context_cache[model_id]

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code != 200:
                return None

            for model in response.json().get("data", []):
                if model.get("id") == model_id:
                    limit = model.get("context_length")
                    if isinstance(limit, int) and limit > 0:
                        _live_context_cache[model_id] = limit
                        return limit
    except Exception:
        pass

    return None

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

def get_context_limit(model_name: str) -> int:
    """Get the context window size for a model.

    Resolution order:
    1. Hardcoded alias (e.g. "sonnet") — instant, no I/O
    2. Live OpenRouter API lookup using the resolved full model ID
    3. Hardcoded full model ID (e.g. "anthropic/claude-sonnet-4.6")
    4. DEFAULT_CONTEXT_LIMIT as a safe conservative fallback

    The live lookup fires at most once per model per process. If it
    succeeds, the result overrides the hardcoded dict so newly released
    models or updated context windows are automatically picked up.

    Args:
        model_name: Short alias (e.g. "sonnet") or full OpenRouter ID

    Returns:
        Context window size in tokens
    """
    # 1. Alias in hardcoded dict — no network needed for known shortcuts
    if model_name in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model_name]

    # 2. Resolve alias to full model ID via llm.py MODELS table
    try:
        from craftsman.llm import MODELS
        model_id = MODELS.get(model_name, model_name)
    except ImportError:
        model_id = model_name

    # 3. Live lookup from OpenRouter (cached after first call)
    live_limit = _fetch_live_context_limit(model_id)
    if live_limit is not None:
        return live_limit

    # 4. Hardcoded full ID fallback
    if model_id in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model_id]

    # 5. Conservative default — unknown model, don't risk overflowing
    return DEFAULT_CONTEXT_LIMIT

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









"""LLM configuration for OpenRouter.

All models are accessed through OpenRouter's unified API.
Users only need a single OPENROUTER_API_KEY.
"""

import os
from langchain_openai import ChatOpenAI


# Available models via OpenRouter.
# Users can also pass any full OpenRouter model ID directly (e.g. --model x-ai/grok-4).
MODELS = {
    # Anthropic Claude
    "sonnet": "anthropic/claude-sonnet-4.6",
    "opus": "anthropic/claude-opus-4.6",
    "haiku": "anthropic/claude-haiku-4.5",  # Update when 4.6 haiku ships

    # Google Gemini
    "gemini": "google/gemini-2.5-pro",
    "flash": "google/gemini-2.5-flash",

    # OpenAI
    "gpt4o": "openai/gpt-4o",
    "gpt4o-mini": "openai/gpt-4o-mini",
    "gpt5": "openai/gpt-5.4",

}

DEFAULT_MODEL = "sonnet"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_llm(model_name: str | None = None) -> ChatOpenAI:
    """Get an LLM instance via OpenRouter.
    
    Args:
        model_name: Model alias (sonnet, opus, haiku, gpt4o, gpt4o-mini)
                    or full OpenRouter model ID
    
    Returns:
        ChatOpenAI instance configured for OpenRouter
    
    Raises:
        ValueError: If OPENROUTER_API_KEY is not set
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required.\n"
            "Get your API key at: https://openrouter.ai/keys"
        )
    
    # Resolve model alias to full ID
    model_id = MODELS.get(model_name or DEFAULT_MODEL, model_name or MODELS[DEFAULT_MODEL])
    
    return ChatOpenAI(
        model=model_id,
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/agent-cli",  # Optional: for tracking
            "X-Title": "Agent CLI",  # Optional: shows in OpenRouter dashboard
        },
    )


def list_models() -> dict[str, str]:
    """Return available model aliases and their IDs."""
    return MODELS.copy()


def get_model_info(model_name: str) -> dict:
    """Get info about a model."""
    model_id = MODELS.get(model_name, model_name)
    return {
        "alias": model_name,
        "id": model_id,
        "provider": model_id.split("/")[0] if "/" in model_id else "unknown",
    }

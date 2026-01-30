"""Web search tool with Exa (preferred) and DuckDuckGo (fallback).

Uses Exa for semantic search if EXA_API_KEY is set, otherwise falls back
to DuckDuckGo which requires no API key.
"""

import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from exa_py import Exa
from duckduckgo_search import DDGS

class WebSearchInput(BaseModel):
    """Input for web_search tool."""
    query: str = Field(description="Search query")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum results to return (default: 5, max: 10)"
    )


def _search_with_exa(query: str, max_results: int, api_key: str) -> tuple[str, bool]:
    """Search using Exa (semantic search optimized for AI).

    Returns:
        Tuple of (result_string, success_bool)
    """

    try:
        exa = Exa(api_key=api_key)
        results = exa.search(
            query,
            num_results=max_results,
            use_autoprompt=True,
        )

        if not results.results:
            return (f"No results found for: {query}", True)

        output_lines = [f" Search results for: {query} (via Exa)\n"]
        for i, result in enumerate(results.results, start=1):
            output_lines.append(f"{i}. **{result.title}**")
            output_lines.append(f"   {result.url}")
            if hasattr(result, 'text') and result.text:
                snippet = result.text[:200] + "..." if len(result.text) > 200 else result.text
                output_lines.append(f"   {snippet}")
            output_lines.append("")

        return ("\n".join(output_lines), True)

    except Exception:
        return ("", False)  # Signal to fall back to DuckDuckGo
    

def _search_with_duckduckgo(query: str, max_results: int) -> str:
    """Search using DuckDuckGo (no API key required.)"""

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                max_results=max_results,
            ))
    except Exception as e:
        return f"DuckDuckGo search failed: {e}"
    
    if not results:
        return f"No results found for: {query}"
    
    output_lines = [f"Search results for: {query} (via DuckDuckGo)\n"]

    for i, result in enumerate(results, start=1):
        title = result.get("title", "No title")
        url = result.get("href", result.get("link", "No URL"))
        snippet = result.get("body", "No description")

        output_lines.append(f"{i}. **{title}**")
        output_lines.append(f"   {url}")
        output_lines.append(f"   {snippet}")
        output_lines.append("")

    return "\n".join(output_lines)


@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information.

    Uses Exa (semantic search) if EXA_API_KEY is set, otherwise
    falls back to DuckDuckGo (no API key required).

    Returns search results with titles, URLs, and snippets.
    """
    # Try Exa first if API key is available
    exa_key = os.environ.get("EXA_API_KEY")
    if exa_key:
        result, success = _search_with_exa(query, max_results, exa_key)
        if success:
            return result
        # Exa failed, fall back to DuckDuckGo

    # Fall back to DuckDuckGo (no API key needed)
    return _search_with_duckduckgo(query, max_results)

    

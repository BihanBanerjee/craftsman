"""Web fetch tool for retrieveing URL content.

Allows the agent to fetch and read web page content.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

import httpx
from bs4 import BeautifulSoup

class WebFetchInput(BaseModel):
    """Input for web_fetch tool."""
    url: str = Field(description="URL to fetch")
    max_chars: int = Field(
        default=10000,
        ge=1000,
        le=50000,
        description="Maximum characters to return (default: 10000)"
    )

@tool(args_schema=WebFetchInput)
def web_fetch(url: str, max_chars: int = 10000) -> str:
    """Fetch and read content from a URL.
    
    Retrieves the web page and extracts readable text content.
    Useful for reading documentation, articles, or examples.
    """
    try:
        # Fetch the page
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; agent-cli/1.0)"
        }
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "")
        
        # Handle different content types
        if "application/json" in content_type:
            return f"# JSON from {url}:\n\n{response.text[:max_chars]}"
        
        if "text/plain" in content_type:
            return f"# Text from {url}:\n\n{response.text[:max_chars]}"
        
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        
        # Get title
        title = soup.title.string if soup.title else "No title"
        
        # Get main content (try common content containers)
        main_content = None
        for selector in ["main", "article", '[role="main"]', ".content", "#content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.body or soup
        
        # Extract text
        text = main_content.get_text(separator="\n", strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)
        
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Content truncated...]"
        
        return f" **{title}**\n{url}\n\n{text}"
    
    except httpx.HTTPStatusError as e:
        return f"HTTP error: {e.response.status_code} for {url}"
    except httpx.RequestError as e:
        return f"Request failed: {e}"
    except Exception as e:
        return f"Error fetching URL: {e}"
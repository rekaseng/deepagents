"""calculator / echo / web_fetch — ports of src/tools/{calculator,echo,webFetch}.ts"""

import re

import httpx
from langchain_core.tools import tool

_EXPR_RE = re.compile(r"^[\d\s+\-*/().]+$")


@tool
def calculator(expression: str) -> dict:
    """Evaluate a mathematical expression. Returns numeric result."""
    if not _EXPR_RE.match(expression):
        return {"success": False, "error": "Invalid expression"}
    try:
        result = eval(compile(expression, "<calc>", "eval"), {"__builtins__": {}}, {})
        return {"success": True, "output": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def echo(message: str) -> dict:
    """Echo the input message back. Used for testing."""
    return {"success": True, "output": message}


@tool
def web_fetch(url: str) -> dict:
    """Fetch the text content of a URL. Returns raw text (truncated to 8000 chars)."""
    try:
        res = httpx.get(url, timeout=10, headers={"User-Agent": "DeepAgent/1.0"}, follow_redirects=True)
        return {"success": True, "output": res.text[:8000]}
    except Exception as e:
        return {"success": False, "error": str(e)}

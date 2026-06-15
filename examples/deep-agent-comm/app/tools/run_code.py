"""run_code — execute LLM-written Python in the L4 sandbox. Available ONLY to
sub-agents (least privilege), never the main agent."""

from langchain_core.tools import tool

from ..sandbox.runner import run_in_sandbox


@tool
def run_code(code: str, input_files: list[str] | None = None) -> dict:
    """Run Python code in an isolated sandbox. Working directory is a private job dir; input files you list are copied into it first. Use print() for output; write any produced files to the working directory. Returns stdout, stderr, and paths of files created."""
    try:
        result = run_in_sandbox(code, input_files or [])
        out = {
            "success": result.success,
            "output": {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "filesCreated": result.files,
            },
        }
        if not result.success:
            out["error"] = f"exit non-zero. stderr: {result.stderr[:500]}"
        return out
    except Exception as e:
        return {"success": False, "error": str(e)}

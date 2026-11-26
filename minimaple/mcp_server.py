"""stdio MCP-server voor mini-Maple: `python -m minimaple.mcp_server`."""
import base64
from mcp.server.mcpserver import MCPServer
from mcp.types import ImageContent, TextContent
from .sessions import SessionManager, commands, help_for

mcp = MCPServer("minimaple")
_mgr = SessionManager()


@mcp.tool()
def maple_eval(code: str, session: str = "default") -> list:
    """Evaluate Maple-syntax code in a persistent named session (variables and procs persist).
    Returns per statement the Maple-style text output and LaTeX; plots come back as PNG images.
    A statement ending in ':' is evaluated silently. Times out after 60 s (session then resets)."""
    results = _mgr.eval(code, session)
    out = []
    for i, r in enumerate(results, 1):
        lines = [f"[{i}] {r['stmt']}"]
        if r.get("error"):
            lines.append(f"error: {r['error']}")
        elif r.get("show", True):
            lines.append(f"text: {r.get('text', '')}")
            if r.get("latex"):
                lines.append(f"latex: {r['latex']}")
        else:
            lines.append("(suppressed)")
        out.append(TextContent(type="text", text="\n".join(lines)))
        for png in r.get("plots") or []:
            out.append(ImageContent(type="image", data=base64.b64encode(png).decode(), mimeType="image/png"))
    return out


@mcp.tool()
def maple_reset(session: str = "default") -> str:
    """Forget all definitions of a session (kills its worker process)."""
    _mgr.reset(session)
    return f"session '{session}' reset"


@mcp.tool()
def maple_commands() -> str:
    """List the supported commands (builtins, and per package)."""
    b, pk = commands()
    s = "Commands: " + ", ".join(b)
    for p, ns in sorted(pk.items()):
        s += f"\n{p}: " + ", ".join(ns)
    return s


@mcp.tool()
def maple_help(name: str) -> str:
    """Short help for one command."""
    h = help_for(name)
    return h if h else f"unknown command '{name}'. Use maple_commands() for the list."


if __name__ == "__main__":
    mcp.run()

import asyncio, sys, pathlib
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


async def _session_test():
    params = StdioServerParameters(command=sys.executable, args=["-m", "minimaple.mcp_server"], cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            assert {"maple_eval", "maple_reset", "maple_commands", "maple_help"} <= tools
            res = await s.call_tool("maple_eval", {"code": "a := 5; a:", "session": "t"})
            txt = "".join(c.text for c in res.content if c.type == "text")
            assert "a" in txt
            res = await s.call_tool("maple_eval", {"code": "a;", "session": "t"})
            assert "5" in "".join(c.text for c in res.content if c.type == "text")
            await s.call_tool("maple_reset", {"session": "t"})
            assert (await s.call_tool("maple_commands", {})).content
            assert (await s.call_tool("maple_help", {"name": "nonexistent"})).content


def test_mcp_stdio():
    _run(_session_test())


def test_timeout():
    from minimaple import sessions
    m = sessions.SessionManager()
    r = m.eval("while true do end do", "s", timeout=4)
    m.close()
    assert "Time limit" in r[0]["error"]

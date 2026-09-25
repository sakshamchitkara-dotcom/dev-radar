import json

from mcp import Client

from dev_radar.servers.system_health import mcp


async def test_snapshot_fields_and_warning_threshold():
    async with Client(mcp) as c:
        r = await c.call_tool("snapshot", {"warn_percent": 0.001})
    snap = r.structured_content
    assert 0 <= snap["memory_percent"] <= 100 and snap["cpu_count"] >= 1
    # Memory use is always above 0.001%, so at least one warning must fire.
    assert any(w.startswith("memory") for w in snap["warnings"])


async def test_snapshot_rejects_missing_path():
    async with Client(mcp) as c:
        r = await c.call_tool("snapshot", {"disk_path": "/definitely/not/here"})
    assert r.is_error


async def test_top_processes_sorted_and_validated():
    async with Client(mcp) as c:
        r = await c.call_tool("top_processes", {"sort_by": "memory", "limit": 3})
        bad = await c.call_tool("top_processes", {"sort_by": "disk"})
    procs = r.structured_content["result"]
    assert 1 <= len(procs) <= 3
    assert [p["memory_mib"] for p in procs] == sorted((p["memory_mib"] for p in procs), reverse=True)
    assert bad.is_error


async def test_snapshot_resource():
    async with Client(mcp) as c:
        r = await c.read_resource("system://snapshot")
    assert "disk_percent" in json.loads(r.contents[0].text)

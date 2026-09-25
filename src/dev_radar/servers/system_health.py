"""system-health MCP server: CPU, memory, disk and process stats via psutil."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Annotated, Literal

import psutil
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("system-health")

GIB = 1024**3


class Snapshot(BaseModel):
    cpu_percent: float
    cpu_count: int
    load_avg_1m: float
    memory_percent: float
    memory_used_gib: float
    memory_total_gib: float
    disk_path: str
    disk_percent: float
    disk_free_gib: float
    uptime_hours: float
    warnings: list[str]


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_mib: float


@mcp.tool()
def snapshot(
    disk_path: Annotated[str, Field(min_length=1, max_length=4096, description="Mount point / path to report disk usage for")] = "/",
    warn_percent: Annotated[float, Field(gt=0, le=100, description="Flag CPU, memory or disk usage at or above this percent")] = 90,
) -> Snapshot:
    """Point-in-time CPU, memory, disk and uptime, with warnings over a threshold."""
    path = Path(disk_path).expanduser()
    if not path.exists():
        raise ToolError(f"Path does not exist: {path}")
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(path))
    warnings = [
        f"{label} at {value:.0f}%"
        for label, value in (("CPU", cpu), ("memory", mem.percent), (f"disk {path}", disk.percent))
        if value >= warn_percent
    ]
    return Snapshot(
        cpu_percent=cpu,
        cpu_count=psutil.cpu_count() or 1,
        load_avg_1m=round(os.getloadavg()[0], 2),
        memory_percent=mem.percent,
        memory_used_gib=round((mem.total - mem.available) / GIB, 2),
        memory_total_gib=round(mem.total / GIB, 2),
        disk_path=str(path),
        disk_percent=disk.percent,
        disk_free_gib=round(disk.free / GIB, 2),
        uptime_hours=round((time.time() - psutil.boot_time()) / 3600, 1),
        warnings=warnings,
    )


@mcp.tool()
def top_processes(
    sort_by: Literal["cpu", "memory"] = "memory",
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum processes to return")] = 5,
) -> list[ProcessInfo]:
    """Heaviest processes by CPU or resident memory."""
    procs = list(psutil.process_iter(["pid", "name", "memory_info"]))
    if sort_by == "cpu":
        # cpu_percent needs two samples; prime every process, wait, then read.
        for p in procs:
            try:
                p.cpu_percent(None)
            except psutil.Error:
                pass
        time.sleep(0.3)
    rows = []
    for p in procs:
        try:
            cpu = p.cpu_percent(None) if sort_by == "cpu" else 0.0
            rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
        except psutil.Error:
            continue  # process exited or is off-limits
        rows.append(ProcessInfo(pid=p.info["pid"], name=p.info["name"] or "?", cpu_percent=cpu, memory_mib=round(rss / 1024**2, 1)))
    key = (lambda r: r.cpu_percent) if sort_by == "cpu" else (lambda r: r.memory_mib)
    return sorted(rows, key=key, reverse=True)[:limit]


@mcp.resource("system://snapshot", mime_type="application/json")
def snapshot_resource() -> str:
    """Current system snapshot for the root filesystem as JSON."""
    return snapshot().model_dump_json()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

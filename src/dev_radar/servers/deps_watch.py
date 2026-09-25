"""deps-watch MCP server: outdated dependencies and known vulnerabilities for a local project.

Reads pinned versions from uv.lock / poetry.lock / requirements*.txt (PyPI) and
package-lock.json (npm). Latest versions come from the PyPI and npm registries;
vulnerabilities from OSV.dev. The project defaults to $DEV_RADAR_REPO or cwd.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tomllib
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from dev_radar.servers import serve

OSV_API = os.environ.get("OSV_API_BASE", "https://api.osv.dev/v1")
PYPI_API = os.environ.get("PYPI_API_BASE", "https://pypi.org/pypi")
NPM_API = os.environ.get("NPM_API_BASE", "https://registry.npmjs.org")

mcp = MCPServer("deps-watch")
logging.getLogger("httpx").setLevel(logging.WARNING)

ProjectPath = Annotated[str | None, Field(description="Project directory; defaults to $DEV_RADAR_REPO or cwd")]
Ecosystem = Literal["PyPI", "npm"]
PIN_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")


class Dependency(BaseModel):
    name: str
    version: str
    ecosystem: Ecosystem
    direct: bool
    source: str  # lockfile it came from


class Outdated(BaseModel):
    name: str
    ecosystem: Ecosystem
    current: str
    latest: str


class Vulnerability(BaseModel):
    id: str
    package: str
    version: str
    ecosystem: Ecosystem
    summary: str
    severity: str | None
    fixed_in: list[str]
    url: str


class OutdatedReport(BaseModel):
    checked: int
    outdated: list[Outdated]
    errors: list[str]


class VulnReport(BaseModel):
    checked: int
    vulnerabilities: list[Vulnerability]


def _project(project: str | None) -> Path:
    path = Path(project or os.environ.get("DEV_RADAR_REPO") or os.getcwd()).expanduser().resolve()
    if not path.is_dir():
        raise ToolError(f"Not a directory: {path}")
    return path


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()  # PEP 503


def _from_toml_lock(path: Path) -> list[Dependency]:
    """uv.lock and poetry.lock share the [[package]] name/version shape."""
    data = tomllib.loads(path.read_text())
    packages = data.get("package", [])
    roots = [p for p in packages if isinstance(p.get("source"), dict) and ({"editable", "virtual"} & set(p["source"]))]
    direct = {_norm(d["name"]) for r in roots for d in r.get("dependencies", [])}
    if path.name == "poetry.lock":  # poetry.lock has no root entry; direct deps live in pyproject.toml
        pyproject = path.parent / "pyproject.toml"
        if pyproject.exists():
            tool = tomllib.loads(pyproject.read_text()).get("tool", {}).get("poetry", {})
            direct = {_norm(n) for n in tool.get("dependencies", {}) if n != "python"}
    return [
        Dependency(name=p["name"], version=p["version"], ecosystem="PyPI", direct=_norm(p["name"]) in direct, source=path.name)
        for p in packages if p not in roots and "version" in p
    ]


def _from_requirements(path: Path) -> list[Dependency]:
    return [
        Dependency(name=m[1], version=m[2], ecosystem="PyPI", direct=True, source=path.name)
        for line in path.read_text().splitlines() if (m := PIN_RE.match(line))
    ]


def _from_package_lock(path: Path) -> list[Dependency]:
    packages = json.loads(path.read_text()).get("packages", {})  # lockfileVersion 2/3
    root = packages.get("", {})
    direct = set(root.get("dependencies", {})) | set(root.get("devDependencies", {}))
    deps = {}
    for key, meta in packages.items():
        if not key or "version" not in meta or meta.get("link"):
            continue
        name = meta.get("name") or key.rsplit("node_modules/", 1)[-1]
        top_level = key == f"node_modules/{name}"
        deps[(name, meta["version"])] = Dependency(
            name=name, version=meta["version"], ecosystem="npm", direct=top_level and name in direct, source=path.name)
    return list(deps.values())


def scan(project: Path) -> list[Dependency]:
    try:
        return _scan(project)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        raise ToolError(f"Could not parse a lockfile in {project}: {type(e).__name__}: {e}") from e


def _scan(project: Path) -> list[Dependency]:
    deps: list[Dependency] = []
    for name in ("uv.lock", "poetry.lock"):
        if (project / name).exists():
            deps += _from_toml_lock(project / name)
            break
    else:
        for req in sorted(project.glob("requirements*.txt")):
            deps += _from_requirements(req)
    if (project / "package-lock.json").exists():
        deps += _from_package_lock(project / "package-lock.json")
    return deps


def is_newer(latest: str, current: str) -> bool:
    """PEP 440 ordering (also parses npm semver like 1.0.0-beta.1); unparseable versions count if they differ."""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


@mcp.tool()
def list_dependencies(project: ProjectPath = None, direct_only: bool = False) -> list[Dependency]:
    """Pinned dependencies found in the project's lockfiles."""
    deps = scan(_project(project))
    return [d for d in deps if d.direct] if direct_only else deps


async def _latest(client: httpx.AsyncClient, dep: Dependency) -> str:
    if dep.ecosystem == "PyPI":
        resp = await client.get(f"{PYPI_API}/{dep.name}/json")
        resp.raise_for_status()
        return resp.json()["info"]["version"]
    resp = await client.get(f"{NPM_API}/{dep.name.replace('/', '%2F')}/latest")
    resp.raise_for_status()
    return resp.json()["version"]


@mcp.tool()
async def outdated(
    project: ProjectPath = None,
    direct_only: bool = True,
    limit: Annotated[int, Field(ge=1, le=500, description="Maximum packages to check against the registry")] = 100,
) -> OutdatedReport:
    """Dependencies whose pinned version is behind the registry's latest release."""
    deps = [d for d in scan(_project(project)) if d.direct or not direct_only][:limit]
    async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=16)) as client:
        latest = await asyncio.gather(*(_latest(client, d) for d in deps), return_exceptions=True)
    rows, errors = [], []
    for d, v in zip(deps, latest):
        if isinstance(v, BaseException):
            errors.append(f"{d.ecosystem}/{d.name}: {v}")
        elif is_newer(v, d.version):
            rows.append(Outdated(name=d.name, ecosystem=d.ecosystem, current=d.version, latest=v))
    return OutdatedReport(checked=len(deps), outdated=rows, errors=errors)


def _to_vuln(dep: Dependency, v: dict[str, Any]) -> Vulnerability:
    fixed = sorted({
        e["fixed"]
        for a in v.get("affected", []) if _norm(a.get("package", {}).get("name", "")) == _norm(dep.name)
        for r in a.get("ranges", []) for e in r.get("events", []) if "fixed" in e
    })
    return Vulnerability(
        id=v["id"], package=dep.name, version=dep.version, ecosystem=dep.ecosystem,
        summary=v.get("summary") or v.get("details", "")[:200], severity=(v.get("database_specific") or {}).get("severity"),
        fixed_in=fixed, url=f"https://osv.dev/vulnerability/{v['id']}",
    )


async def check_vulns(deps: list[Dependency]) -> list[Vulnerability]:
    try:
        async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=16)) as client:
            hits: list[tuple[Dependency, str]] = []
            for i in range(0, len(deps), 1000):  # querybatch accepts up to 1000 queries
                chunk = deps[i:i + 1000]
                queries = [{"package": {"name": d.name, "ecosystem": d.ecosystem}, "version": d.version} for d in chunk]
                resp = await client.post(f"{OSV_API}/querybatch", json={"queries": queries})
                resp.raise_for_status()
                for d, res in zip(chunk, resp.json()["results"]):
                    hits += [(d, v["id"]) for v in res.get("vulns", [])]

            async def detail(vid: str) -> dict[str, Any]:
                r = await client.get(f"{OSV_API}/vulns/{vid}")
                r.raise_for_status()
                return r.json()

            details = await asyncio.gather(*(detail(vid) for _, vid in hits))
    except httpx.HTTPError as e:
        raise ToolError(f"OSV.dev unavailable: {e}") from e
    return [_to_vuln(d, v) for (d, _), v in zip(hits, details)]


@mcp.tool()
async def vulnerabilities(ctx: Context, project: ProjectPath = None) -> VulnReport:
    """Known vulnerabilities (OSV.dev) affecting every pinned dependency, direct and transitive.

    The result is also published as the `deps://vulnerabilities` resource; subscribers are
    notified when the set of vulnerability IDs for the project changes.
    """
    root = _project(project)
    deps = scan(root)
    report = VulnReport(checked=len(deps), vulnerabilities=await check_vulns(deps) if deps else [])
    previous = _last_report.get(str(root))
    _last_report[str(root)] = report
    if previous is None or {v.id for v in previous.vulnerabilities} != {v.id for v in report.vulnerabilities}:
        await ctx.notify_resource_updated(REPORT_URI)
    return report


REPORT_URI = "deps://vulnerabilities"
_last_report: dict[str, VulnReport] = {}  # project path -> last scan, per server process


@mcp.resource(REPORT_URI, mime_type="application/json")
def last_vulnerability_report() -> str:
    """The most recent vulnerability scan per project (run the `vulnerabilities` tool to refresh). Subscribable."""
    return json.dumps({path: r.model_dump() for path, r in _last_report.items()})


@mcp.prompt(title="Dependency triage")
def triage_dependencies(project: str = "") -> str:
    """Ask the model to turn vulnerability and outdated reports into an upgrade plan."""
    target = project.strip() or "the default project"
    return (
        f"Audit the dependencies of {target}.\n"
        "1. Call vulnerabilities, then outdated.\n"
        "2. Group vulnerabilities by package; for each, give the minimum fixed version and severity.\n"
        "3. Propose an upgrade order: security fixes first, then major-version jumps with release-note links "
        "to check, then routine bumps.\n"
        "Only cite versions and IDs that appear in tool results."
    )


def main() -> None:
    serve(mcp)


if __name__ == "__main__":
    main()

import json

import httpx
import pytest
from mcp import Client

from dev_radar.servers import deps_watch
from dev_radar.servers.deps_watch import is_newer, mcp

UV_LOCK = """
version = 1
[[package]]
name = "app"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "Jinja2" }]

[[package]]
name = "jinja2"
version = "2.10"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "markupsafe"
version = "1.0"
source = { registry = "https://pypi.org/simple" }
"""
PACKAGE_LOCK = {"lockfileVersion": 3, "packages": {
    "": {"dependencies": {"lodash": "^4"}},
    "node_modules/lodash": {"version": "4.17.15"},
    "node_modules/a/node_modules/lodash": {"version": "3.0.0"},
    "node_modules/minimist": {"version": "1.2.0"},
    "node_modules/linked": {"version": "1.0.0", "link": True},
}}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "uv.lock").write_text(UV_LOCK)
    (tmp_path / "package-lock.json").write_text(json.dumps(PACKAGE_LOCK))
    return tmp_path


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://pypi.org/pypi/jinja2/json":
        return httpx.Response(200, json={"info": {"version": "3.1.6"}})
    if url == "https://registry.npmjs.org/lodash/latest":
        return httpx.Response(200, json={"version": "4.17.15"})
    if url.endswith("/querybatch"):
        queries = json.loads(request.content)["queries"]
        return httpx.Response(200, json={"results": [
            {"vulns": [{"id": "GHSA-1"}]} if q["package"]["name"] == "jinja2" else {} for q in queries]})
    if url.endswith("/vulns/GHSA-1"):
        return httpx.Response(200, json={"id": "GHSA-1", "summary": "sandbox escape", "database_specific": {"severity": "HIGH"},
                                         "affected": [{"package": {"name": "Jinja2"}, "ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.10.1"}]}]}]})
    return httpx.Response(500)


@pytest.fixture
def fake_http(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(deps_watch.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))


async def test_list_dependencies_parses_locks(project):
    async with Client(mcp) as c:
        r = await c.call_tool("list_dependencies", {"project": str(project)})
        direct = await c.call_tool("list_dependencies", {"project": str(project), "direct_only": True})
    deps = {(d["ecosystem"], d["name"], d["version"]): d["direct"] for d in r.structured_content["result"]}
    assert deps == {
        ("PyPI", "jinja2", "2.10"): True, ("PyPI", "markupsafe", "1.0"): False,
        ("npm", "lodash", "4.17.15"): True, ("npm", "lodash", "3.0.0"): False, ("npm", "minimist", "1.2.0"): False,
    }
    assert {d["name"] for d in direct.structured_content["result"]} == {"jinja2", "lodash"}


def test_requirements_pins_only(tmp_path):
    (tmp_path / "requirements.txt").write_text("jinja2==2.10\nrequests[socks]==2.19.0 ; python_version>'3'\nflask>=2\n# x==1\n")
    assert [(d.name, d.version) for d in deps_watch.scan(tmp_path)] == [("jinja2", "2.10"), ("requests", "2.19.0")]


async def test_outdated_and_vulnerabilities(project, fake_http):
    async with Client(mcp) as c:
        out = await c.call_tool("outdated", {"project": str(project)})
        vul = await c.call_tool("vulnerabilities", {"project": str(project)})
    assert out.structured_content == {"checked": 2, "errors": [],
                                      "outdated": [{"name": "jinja2", "ecosystem": "PyPI", "current": "2.10", "latest": "3.1.6"}]}
    v = vul.structured_content
    assert v["checked"] == 5
    assert v["vulnerabilities"] == [{"id": "GHSA-1", "package": "jinja2", "version": "2.10", "ecosystem": "PyPI",
                                     "summary": "sandbox escape", "severity": "HIGH", "fixed_in": ["2.10.1"],
                                     "url": "https://osv.dev/vulnerability/GHSA-1"}]


async def test_osv_down_is_tool_error(project, monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(deps_watch.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    async with Client(mcp) as c:
        r = await c.call_tool("vulnerabilities", {"project": str(project)})
        missing = await c.call_tool("outdated", {"project": str(project / "nope")})
    assert r.is_error and "OSV.dev unavailable" in r.content[0].text
    assert missing.is_error


def test_is_newer():
    assert is_newer("3.1.6", "2.10") and is_newer("2.10.1", "2.10")
    assert not is_newer("2.10", "2.10") and not is_newer("1.9", "1.10")
    assert is_newer("2.0.0", "2.0rc1") and not is_newer("2.0rc1", "2.0.0")  # pre-releases sort before the release
    assert not is_newer("2.0.0", "2.0")  # trailing zeros are equal, not "outdated"
    assert is_newer("1.0.post1", "1.0") and is_newer("1.0.0", "1.0.0-beta.1")  # post-release, npm semver pre-release
    assert is_newer("git-abc", "git-def") and not is_newer("x", "x")  # unparseable: any difference counts

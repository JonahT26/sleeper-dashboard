"""The pins agree with each other and with what is actually installed, so GitHub Actions runs what runs locally.

These run both locally and in GitHub Actions: locally they catch a virtual environment that has
drifted from the lock file; in Actions they confirm the install matched it.
"""

import re
import sys
import tomllib
from importlib import metadata

from packaging.markers import default_environment
from packaging.requirements import Requirement

from sleeper_dash.config import PROJECT_ROOT

PIN = re.compile(r"^([A-Za-z0-9_.-]+)==(\S+)$")
UPDATE = "see docs/CODEBASE.md, 'Dependencies'"


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(lines):
    found = {}
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            match = PIN.match(line)
            assert match, f"not an exact pin: {line!r}"
            found[canonical(match[1])] = match[2]
    return found


def project():
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def lock():
    return pins((PROJECT_ROOT / "requirements-ci.txt").read_text(encoding="utf-8").splitlines())


def test_every_pyproject_dependency_is_an_exact_pin():
    meta = project()
    pins(meta["dependencies"] + meta["optional-dependencies"]["dev"])


def test_ci_lock_file_has_pyproject_versions_and_pytest():
    meta = project()
    wanted = pins(meta["dependencies"])
    wanted["pytest"] = pins(meta["optional-dependencies"]["dev"])["pytest"]
    assert {name: lock().get(name) for name in wanted} == wanted
    assert "jupyterlab" not in lock()  # local tool only; keeps the Actions install light


def test_every_locked_package_is_installed_at_its_locked_version():
    installed = {canonical(d.metadata["Name"]): d.version for d in metadata.distributions()}
    wrong = {name: installed.get(name, "not installed") for name, version in lock().items() if installed.get(name) != version}
    assert not wrong, f"installed versions differ from requirements-ci.txt: {wrong}; {UPDATE}"


def test_lock_file_is_complete():
    # Everything the locked packages need (on this platform) is itself locked, so pip has nothing to choose.
    locked, env = lock(), default_environment()
    missing = set()
    for name in locked:
        for spec in metadata.requires(name) or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate({**env, "extra": ""}):
                if canonical(req.name) not in locked:
                    missing.add(f"{req.name} (needed by {name})")
    assert not missing, f"requirements-ci.txt is missing {sorted(missing)}; {UPDATE}"


def test_python_is_the_pinned_version():
    pinned = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    running = ".".join(map(str, sys.version_info[:3]))
    assert running == pinned, (
        f"Python {running} is running, but .python-version (what GitHub Actions uses) says {pinned}; {UPDATE}"
    )
    requires = project()["requires-python"]
    assert requires == f">={pinned.rsplit('.', 1)[0]}", "requires-python should name the same minor version"

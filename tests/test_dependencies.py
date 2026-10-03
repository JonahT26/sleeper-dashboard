"""The two dependency lists agree: everything GitHub Actions installs is pinned, at pyproject.toml's versions."""

import re
import tomllib

from sleeper_dash.config import PROJECT_ROOT

PIN = re.compile(r"^([A-Za-z0-9_.-]+)==(\S+)$")


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


def test_every_pyproject_dependency_is_an_exact_pin():
    meta = project()
    pins(meta["dependencies"] + meta["optional-dependencies"]["dev"])


def test_ci_lock_file_has_pyproject_versions_and_pytest():
    meta = project()
    lock = pins((PROJECT_ROOT / "requirements-ci.txt").read_text(encoding="utf-8").splitlines())
    wanted = pins(meta["dependencies"])
    wanted["pytest"] = pins(meta["optional-dependencies"]["dev"])["pytest"]
    assert {name: lock.get(name) for name in wanted} == wanted
    assert "jupyterlab" not in lock  # local tool only; keeps the Actions install light

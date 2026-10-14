"""Verify that the final Linux image retained all locked runtime packages."""
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import sys


def main():
    lock = Path(__file__).resolve().parents[1] / "requirements-linux.lock"
    expected = dict(re.findall(
        r"^([A-Za-z0-9._-]+)==([^\s\\]+)",
        lock.read_text(encoding="utf-8"), re.MULTILINE,
    ))
    if not expected:
        raise RuntimeError("Runtime package lock is empty")
    mismatches = []
    for name, version in expected.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed != version:
            mismatches.append({"package": name, "expected": version,
                               "installed": installed})
    installers = [name for name in ("pip", "setuptools", "wheel", "ensurepip")
                  if importlib.util.find_spec(name) is not None]
    print(json.dumps({"locked_packages_checked": len(expected),
                      "mismatches": mismatches,
                      "runtime_installation_tools": installers}))
    return 1 if mismatches or installers else 0


if __name__ == "__main__":
    sys.exit(main())

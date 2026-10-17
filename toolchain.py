"""
toolchain.py - locate (and put on PATH) the OSS CAD Suite and this repo's Python environment.

Shared by setup.py (installs things) and ttfpga.py (uses them). Standard library only.
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
LOCAL_DIR = os.path.join(ROOT, ".oss-cad-suite")        # where setup.py extracts the suite
REQUIRED = ("yosys", "nextpnr-ice40", "icepack")
IS_WIN = os.name == "nt"


def venv_python():
    return os.path.join(VENV, "Scripts", "python.exe") if IS_WIN else os.path.join(VENV, "bin", "python")


def in_venv():
    return os.path.normcase(os.path.abspath(sys.prefix)) == os.path.normcase(os.path.abspath(VENV))


def _has_tools(bin_dir):
    exe = ".exe" if IS_WIN else ""
    return all(os.path.isfile(os.path.join(bin_dir, t + exe)) for t in REQUIRED)


def candidates():
    """Folders that may hold an OSS CAD Suite, best first."""
    env = os.environ.get("OSS_CAD_SUITE")
    if env:
        yield env
    yield os.path.join(LOCAL_DIR, "oss-cad-suite")
    home = os.path.expanduser("~")
    yield os.path.join(home, "oss-cad-suite")
    if IS_WIN:
        yield r"C:\oss-cad-suite"
    else:
        yield "/opt/oss-cad-suite"


def find_suite():
    """Root folder of an OSS CAD Suite that has yosys, nextpnr-ice40 and icepack, or None."""
    for root in candidates():
        if _has_tools(os.path.join(root, "bin")):
            return root
    return None


def activate():
    """Put the suite on PATH. Returns a description of where the tools come from, or None if missing."""
    root = find_suite()
    if root:
        os.environ["PATH"] = os.pathsep.join(
            [os.path.join(root, "bin"), os.path.join(root, "lib"), os.environ.get("PATH", "")]
        )
        return root
    if all(shutil.which(t) for t in REQUIRED):
        return "PATH"
    return None


def suite_version(root):
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "unknown"

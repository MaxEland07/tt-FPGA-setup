#!/usr/bin/env python3
"""
setup.py - one-command setup for the TT FPGA workflow (Windows, Linux, macOS).

    python setup.py              # install everything that is missing, then run a build smoke test
    python setup.py --check      # only report what is installed
    python setup.py --latest     # use the newest OSS CAD Suite instead of the pinned, tested one
    python setup.py --force      # re-download the OSS CAD Suite even if one is found
    python setup.py --skip-test  # skip the smoke-test build

What it sets up (all inside this folder, no admin rights needed):

    .venv/             Python virtual environment with mpremote + pyserial (requirements.txt)
    .oss-cad-suite/    OSS CAD Suite (yosys, nextpnr-ice40, icepack), downloaded from GitHub and
                       checked against the SHA-256 published with the release

An OSS CAD Suite you already have (OSS_CAD_SUITE, ~/oss-cad-suite, C:\\oss-cad-suite, /opt/oss-cad-suite,
or the tools already on PATH) is reused instead of downloading another ~2 GB.

Needs only Python 3.8+ and git. Standard library only, so it can run before anything is installed.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

import toolchain as tc

# The suite version the repo was tested with. `--latest` ignores it.
PINNED_TAG = "2026-10-17"
RELEASES = "https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases"
DOWNLOAD = "https://github.com/YosysHQ/oss-cad-suite-build/releases/download"
UA = {"User-Agent": "tt-fpga-setup"}
CACHE = os.path.join(tc.ROOT, ".cache")


def step(msg):
    print(f"\n=== {msg}", flush=True)


def info(msg):
    print(f"  {msg}", flush=True)


def die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- prerequisites


def check_prereqs():
    step("Checking prerequisites")
    if sys.version_info < (3, 8):
        die(f"Python 3.8 or newer is required (this is {platform.python_version()}).")
    info(f"Python {platform.python_version()}")
    if not shutil.which("git"):
        hint = {"win32": "winget install --id Git.Git -e", "darwin": "xcode-select --install"}.get(
            sys.platform, "sudo apt install git   (or your distro's equivalent)")
        die(f"git not found. Install it ({hint}) and run setup again.")
    info("git found")


# ---------------------------------------------------------------- python environment


def setup_venv():
    step("Python environment (.venv)")
    py = tc.venv_python()
    if not os.path.exists(py):
        info("creating .venv")
        r = subprocess.run([sys.executable, "-m", "venv", tc.VENV])
        if r.returncode != 0:
            shutil.rmtree(tc.VENV, ignore_errors=True)
            hint = "  On Debian/Ubuntu: sudo apt install python3-venv" if sys.platform.startswith("linux") else ""
            die("could not create the virtual environment." + ("\n" + hint if hint else ""))
    req = os.path.join(tc.ROOT, "requirements.txt")
    r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", req])
    if r.returncode != 0:
        die("pip install failed (no internet connection?)")
    out = subprocess.run([py, "-m", "pip", "list", "--disable-pip-version-check", "--format=freeze"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.split("==")[0].lower() in ("mpremote", "pyserial"):
            info(line)


# ---------------------------------------------------------------- OSS CAD Suite


def suite_platform():
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "win32":
        return "windows-x64"        # the only Windows build; Windows on ARM runs it under emulation
    if sys.platform == "darwin":
        return "darwin-arm64" if arm else "darwin-x64"
    if sys.platform.startswith("linux"):
        if arm:
            return "linux-arm64"
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
    die(f"No OSS CAD Suite build for {sys.platform}/{machine}. Install yosys, nextpnr-ice40 and icepack "
        "yourself (they just need to be on PATH) and run setup again.")


def api_json(url):
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def resolve_asset(latest):
    """Return (tag, file name, url, size, sha256). size/sha256 are None if the API is unavailable."""
    plat = suite_platform()
    tag = None if latest else PINNED_TAG
    rel = None
    try:
        rel = api_json(f"{RELEASES}/latest" if latest else f"{RELEASES}/tags/{tag}")
    except urllib.error.HTTPError as e:
        if e.code == 404 and not latest:
            info(f"release {PINNED_TAG} is no longer available, using the latest one instead")
            try:
                rel = api_json(f"{RELEASES}/latest")
            except (urllib.error.URLError, OSError):
                rel = None
        elif e.code == 403:
            info("GitHub API rate limit reached; downloading without a published checksum")
    except (urllib.error.URLError, OSError, ValueError):
        pass
    if rel:
        for a in rel.get("assets", []):
            if a["name"].startswith(f"oss-cad-suite-{plat}-") and a["name"].endswith(".tgz"):
                digest = a.get("digest") or ""
                sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
                return rel["tag_name"], a["name"], a["browser_download_url"], a.get("size"), sha
        die(f"release {rel.get('tag_name')} has no {plat} build")
    if latest:
        die("could not reach api.github.com to find the latest release")
    name = f"oss-cad-suite-{plat}-{PINNED_TAG.replace('-', '')}.tgz"
    return PINNED_TAG, name, f"{DOWNLOAD}/{PINNED_TAG}/{name}", None, None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, dest, size):
    """Download url to dest, resuming a partial download and retrying on network errors."""
    part = dest + ".part"
    for attempt in range(1, 6):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = dict(UA)
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                if have and r.status != 206:     # server ignored the range: start again
                    have = 0
                total = have + int(r.headers.get("Content-Length") or 0) or size or 0
                last = 0.0
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        block = r.read(1 << 20)
                        if not block:
                            break
                        f.write(block)
                        have += len(block)
                        if time.time() - last > 0.5:
                            last = time.time()
                            pct = f" of {total >> 20} MB ({have * 100 // total}%)" if total else ""
                            print(f"\r  {have >> 20} MB{pct}   ", end="", flush=True)
            print(flush=True)
            if size and os.path.getsize(part) != size:
                raise OSError("download ended early")
            os.replace(part, dest)
            return
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:           # already have the whole file
                os.replace(part, dest)
                return
            if e.code == 404:
                print(flush=True)
                raise
            err = e
        except (urllib.error.URLError, OSError) as e:
            err = e
        print(flush=True)
        info(f"download interrupted ({err}); retry {attempt}/5 in 3 s")
        time.sleep(3)
    die("download failed. Check your internet connection and run setup again (it resumes).")


def extract(archive, dest_parent):
    """Extract the suite into dest_parent/oss-cad-suite, atomically (no half-installed folder on failure)."""
    final = os.path.join(dest_parent, "oss-cad-suite")
    tmp = os.path.join(dest_parent, f".extracting-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    kw = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}   # Python 3.12+: refuse unsafe paths
    try:
        with tarfile.open(archive, "r:gz") as tf:
            n = 0
            for member in tf:
                tf.extract(member, tmp, **kw)
                n += 1
                if n % 2000 == 0:
                    print(f"\r  {n} files   ", end="", flush=True)
            print(f"\r  {n} files   ", flush=True)
        if not os.path.isdir(os.path.join(tmp, "oss-cad-suite")):
            die("unexpected archive layout (no oss-cad-suite folder inside)")
        shutil.rmtree(final, ignore_errors=True)
        os.replace(os.path.join(tmp, "oss-cad-suite"), final)
    except (tarfile.TarError, OSError) as e:
        die(f"extraction failed: {e}\n  On Windows, very long folder paths can cause this: "
            "clone the repo closer to the drive root, e.g. C:\\tt-fpga.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return final


def setup_suite(latest, force):
    step("OSS CAD Suite (yosys, nextpnr-ice40, icepack)")
    found = None if force else tc.activate()
    if found:
        where = "already on PATH" if found == "PATH" else f"{found} (version {tc.suite_version(found)})"
        info(f"found: {where}; not downloading another copy (use --force to override)")
        return
    tag, name, url, size, sha = resolve_asset(latest)
    info(f"installing release {tag}: {name}" + (f" ({size >> 20} MB download, about 2 GB installed)" if size else ""))
    free = shutil.disk_usage(tc.ROOT).free
    if free < 4 << 30:
        die(f"only {free >> 30} GB free on this drive; the suite needs about 4 GB while installing.")
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(tc.LOCAL_DIR, exist_ok=True)
    archive = os.path.join(CACHE, name)
    if not os.path.exists(archive):
        step("Downloading")
        try:
            download(url, archive, size)
        except urllib.error.HTTPError as e:
            die(f"download failed: HTTP {e.code} for {url}")
    if sha:
        info("verifying SHA-256")
        if sha256_of(archive).lower() != sha.lower():
            os.remove(archive)
            die("checksum mismatch: the download is corrupt. Deleted it, run setup again.")
    else:
        info("WARNING: no published checksum available, skipping verification")
    step("Extracting (a few minutes)")
    root = extract(archive, tc.LOCAL_DIR)
    os.remove(archive)
    info(f"installed to {root}")
    if tc.activate() is None:
        die("installation finished but yosys / nextpnr-ice40 / icepack were not found in it")


# ---------------------------------------------------------------- verification


def show_tool_versions():
    for tool, flag in (("yosys", "-V"), ("nextpnr-ice40", "--version"), ("icepack", "--help")):
        try:
            r = subprocess.run([tool, flag], capture_output=True, text=True, timeout=60)
            out = (r.stdout + r.stderr).strip().splitlines()
            info(f"{tool}: {out[0] if out else 'ok'}")
        except (OSError, subprocess.TimeoutExpired) as e:
            info(f"{tool}: FAILED to run ({e})")


def smoke_test():
    step("Smoke test: building the Tiny Tapeout factory test (no board needed)")
    r = subprocess.run([tc.venv_python(), os.path.join(tc.ROOT, "ttfpga.py"), "factory-test", "--no-upload"])
    if r.returncode != 0:
        die("the test build failed; see the output above.")


def check_board():
    step("Board")
    code = ("import serial.tools.list_ports as lp\n"
            "for p in lp.comports():\n"
            "    if p.vid == 0x2E8A: print(p.device)\n")
    out = subprocess.run([tc.venv_python(), "-c", code], capture_output=True, text=True).stdout.split()
    if out:
        info(f"TT demoboard found on {out[0]}")
    else:
        info("No board detected. That is fine for building; plug it in over USB before uploading.")
    if sys.platform.startswith("linux"):
        import grp
        try:
            groups = {grp.getgrgid(g).gr_name for g in os.getgroups()}
        except KeyError:
            groups = set()
        if not groups & {"dialout", "uucp", "plugdev"}:
            info("Linux: you may need serial-port access. Run: sudo usermod -aG dialout $USER   "
                 "then log out and back in.")


def report():
    """--check: say what is installed, change nothing."""
    ok = True
    step("Status")
    venv_ok = os.path.exists(tc.venv_python())
    info(f".venv:  {'ok' if venv_ok else 'MISSING'}")
    ok &= venv_ok
    found = tc.activate()
    info(f"OSS CAD Suite: {('on PATH' if found == 'PATH' else found) if found else 'MISSING'}")
    ok &= bool(found)
    if found:
        show_tool_versions()
    if venv_ok:
        check_board()
    print("\nEverything is installed." if ok else "\nSomething is missing: run  python setup.py", flush=True)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Set up the TT FPGA toolchain in this folder")
    ap.add_argument("--check", action="store_true", help="report what is installed, change nothing")
    ap.add_argument("--latest", action="store_true", help="use the newest OSS CAD Suite instead of the pinned one")
    ap.add_argument("--force", action="store_true", help="download the OSS CAD Suite even if one is found")
    ap.add_argument("--skip-test", action="store_true", help="skip the smoke-test build")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    if args.check:
        sys.exit(report())
    check_prereqs()
    setup_venv()
    setup_suite(args.latest, args.force)
    show_tool_versions()
    if not args.skip_test:
        smoke_test()
    check_board()
    print("\nSetup complete. Build a project and load it onto the board with:\n"
          "    python ttfpga.py https://github.com/<user>/<tt-project>.git\n"
          "See README.md for options.", flush=True)


if __name__ == "__main__":
    main()

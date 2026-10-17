#!/usr/bin/env python3
"""
ttfpga.py - clone, harden and load a Tiny Tapeout project onto the TT FPGA breakout.

    python ttfpga.py https://github.com/user/tt-my-project.git
    python ttfpga.py projects\\tt-my-project                 # already cloned
    python ttfpga.py <repo-or-dir> --clock-hz 2000000      # override the clock rate
    python ttfpga.py <repo-or-dir> --no-upload             # build the .bin only

What it does (the same steps as tools/tt_fpga.py harden + configure, without its Python
dependencies, using the OSS CAD Suite tools):

    1. git clone (or git pull) into projects/<repo name>
    2. read info.yaml (top module, source files, clock)
    3. yosys -> nextpnr-ice40 -> icepack  =>  <project>/build/<top_module>.bin
    4. copy the .bin to the board over USB (mpremote), make it the default project,
       set its clock rate in config.ini, restart the board and show the boot log

Needs: Python 3, git, OSS CAD Suite (C:\\oss-cad-suite, or set OSS_CAD_SUITE), `pip install mpremote`.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

import toolchain

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_FPGA = os.path.join(HERE, "fpga")
PROJECTS = os.path.join(HERE, "projects")
SHIM_DIR = os.path.join(HERE, "fpga_shim")
PCF = {"fabricfox": "tt_fpga_fabricfoxv2.pcf", "classic": "tt_fpga_top.pcf"}
ALIASES = {"factory-test": "https://github.com/TinyTapeout/ttsky25b-factory-test.git"}


def die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def step(msg):
    print(f"\n=== {msg}")


def run(cmd, **kw):
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, **kw)


# ---------------------------------------------------------------- tools


def use_repo_python():
    """Re-run under the .venv that setup.py created, so mpremote and pyserial are found."""
    if toolchain.in_venv() or os.environ.get("TTFPGA_NO_VENV") or not os.path.exists(toolchain.venv_python()):
        return
    raise SystemExit(subprocess.call([toolchain.venv_python(), os.path.abspath(__file__), *sys.argv[1:]]))


def setup_oss_cad():
    if toolchain.activate() is None:
        die("yosys / nextpnr-ice40 / icepack not found. Run:  python setup.py")


# ---------------------------------------------------------------- project


def get_project(target):
    """Return the project directory, cloning/updating from GitHub if target is a URL."""
    target = ALIASES.get(target, target)
    if re.match(r"^(https?://|git@|ssh://)", target) or target.endswith(".git"):
        name = re.sub(r"\.git$", "", target.rstrip("/").split("/")[-1])
        dest = os.path.join(PROJECTS, name)
        os.makedirs(PROJECTS, exist_ok=True)
        if os.path.isdir(os.path.join(dest, ".git")):
            step(f"Updating {dest}")
            run(["git", "-C", dest, "pull", "--ff-only"])
        else:
            step(f"Cloning {target}")
            if run(["git", "clone", target, dest]).returncode != 0:
                die("git clone failed")
        return dest
    if not os.path.isdir(target):
        die(f"{target} is not a directory or a git URL")
    return os.path.abspath(target)


def read_info(project):
    path = os.path.join(project, "info.yaml")
    if not os.path.exists(path):
        die(f"No info.yaml in {project}")
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"(?m)^\s*#.*$", "", text)  # whole-line comments

    def scalar(key):
        m = re.search(rf"(?m)^\s*{key}:\s*[\"']?([^\"'#\r\n]*)", text)
        return m.group(1).strip() if m else ""

    sources = []
    m = re.search(r"(?ms)^\s*source_files:\s*\n((?:\s*-\s*.*\n?)+)", text)
    if m:
        sources = [re.sub(r"[\"']", "", s).split("#")[0].strip()
                   for s in re.findall(r"-\s*(.+)", m.group(1))]
    info = {
        "top": scalar("top_module"),
        "title": scalar("title"),
        "language": scalar("language") or "Verilog",
        "clock_hz": int(float(scalar("clock_hz") or 0)),
        "sources": [s for s in sources if s],
    }
    if not info["top"] or not info["sources"]:
        die("info.yaml needs top_module and source_files")
    if info["language"].lower() not in ("verilog", "systemverilog"):
        die(f"Language '{info['language']}' is not supported by this script (Verilog/SystemVerilog only). "
            "Generate Verilog first, then list those files in info.yaml.")
    return info


# ---------------------------------------------------------------- harden


def harden(project, info, target, seed, freq_mhz):
    top, name = info["top"], info["top"]
    src = os.path.join(project, "src")
    build = os.path.join(project, "build")
    os.makedirs(build, exist_ok=True)

    sources = [os.path.join(src, s) for s in info["sources"]]
    for s in sources:
        if not os.path.exists(s):
            die(f"Source file listed in info.yaml not found: {s}")

    # wrapper that maps the TT interface onto the breakout's pins
    template = open(os.path.join(TOOLS_FPGA, "tt_fpga_top.v"), encoding="utf-8").read()
    wrapper = os.path.join(build, "_tt_fpga_top.v")
    open(wrapper, "w", encoding="utf-8").write(template.replace("__tt_um_placeholder", top))

    # designs that instantiate Sky130 cells by name (ring oscillators, delay chains) need FPGA stand-ins
    if any("sky130_fd_sc_" in open(f, errors="replace").read() for f in sources):
        shim = os.path.join(SHIM_DIR, "sky130_cells.v")
        sources.append(shim)
        print(f"  Note: design uses Sky130 cells, adding FPGA stand-ins from {shim}")

    json_f, asc_f, bin_f = (os.path.join(build, f"{name}.{e}") for e in ("json", "asc", "bin"))

    step("Synthesis (yosys)")
    ys = f"read_verilog -sv {wrapper} {' '.join(sources)}; synth_ice40 -top tt_fpga_top -json {json_f}"
    ys = ys.replace("\\", "/")
    if run(["yosys", "-q", "-l", os.path.join(build, "01-synth.log"), "-DSYNTH", "-p", ys]).returncode != 0:
        die(f"synthesis failed, see {os.path.join(build, '01-synth.log')}")

    step(f"Place and route (nextpnr-ice40, target {freq_mhz:g} MHz)")
    nextpnr = ["nextpnr-ice40", "-q", "-l", os.path.join(build, "02-nextpnr.log"),
               "--pcf-allow-unconstrained", "--seed", str(seed), "--freq", f"{freq_mhz:g}",
               "--package", "sg48", "--up5k", "--asc", asc_f,
               "--pcf", os.path.join(TOOLS_FPGA, PCF[target]), "--json", json_f]
    if run(nextpnr).returncode != 0:
        log = open(os.path.join(build, "02-nextpnr.log"), errors="replace").read()
        extra = []
        if "combinational loops" in log:
            print("  Note: the design has combinational loops (ring oscillators?); timing is not checked through them.")
            extra.append("--ignore-loops")
        if extra and run(nextpnr + extra).returncode == 0:
            pass
        else:
            log = open(os.path.join(build, "02-nextpnr.log"), errors="replace").read()
            slow = "Max frequency" in log and "FAIL" in log
            hold = "time violation" in log
            if slow or hold:
                if slow:
                    print("  WARNING: design does not meet timing at the target clock; building anyway.")
                if hold:
                    print("  WARNING: hold-time violations reported; building anyway. In a design with ring "
                          "oscillators these are paths inside the rings and can be ignored.")
                if run(nextpnr + extra + ["--timing-allow-fail"]).returncode != 0:
                    die("placement failed")
            else:
                die(f"placement failed, see {os.path.join(build, '02-nextpnr.log')}")

    log = open(os.path.join(build, "02-nextpnr.log"), errors="replace").read()
    lines = re.findall(r"Info: Max frequency.*", log)
    main = [l for l in lines if "clk$SB_IO_IN" in l]    # the project clock, not a divided clock inside the design
    for line in (main or lines)[-1:]:
        print("  " + re.sub(r"\s+", " ", line))

    step("Bitstream (icepack)")
    if run(["icepack", asc_f, bin_f]).returncode != 0:
        die("icepack failed")
    print(f"  {bin_f} ({os.path.getsize(bin_f)} bytes)")
    return bin_f


# ---------------------------------------------------------------- board


def find_port(wanted):
    if wanted:
        return wanted
    try:
        import serial.tools.list_ports as lp
        for p in lp.comports():
            if p.vid == 0x2E8A:  # Raspberry Pi (RP2040 / RP2350)
                return p.device
    except ImportError:
        pass
    die("Could not find the board. Plug it in or pass --port (COM5, /dev/ttyACM0, ...).")


def mp(port, *args, capture=False):
    cmd = [sys.executable, "-m", "mpremote", "connect", port, *args]
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        die(f"mpremote failed: {' '.join(args)}\n{r.stderr or ''}")
    return r.stdout


def edit_config(text, top, clock_hz):
    """Make `top` the default project and give it a [top] section with the clock rate."""
    text = re.sub(r"(?m)^(project\s*=\s*)[^\r\n]*", lambda m: m.group(1) + top, text, count=1)
    exists = re.search(rf"(?m)^\[{re.escape(top)}\]", text)
    if exists and not clock_hz:
        return text  # no clock requested: keep whatever is already configured for this project
    # drop any previous section for this project
    text = re.sub(rf"(?ms)^\[{re.escape(top)}\][^\[]*", "", text)
    nl = "\r\n" if "\r\n" in text else "\n"
    # a project without a clock in info.yaml still gets a slow default so you can see it run
    section = f"[{top}]{nl}start_in_reset = no{nl}clock_frequency = {clock_hz or 10}{nl}"
    return text.rstrip() + nl + nl + section + nl


def upload(bin_f, info, port, clock_hz):
    top = info["top"]
    port = find_port(port)
    step(f"Uploading to the board on {port}")
    mp(port, "fs", "cp", bin_f, f":/bitstreams/{top}.bin")

    tmp = os.path.join(tempfile.gettempdir(), "tt_config.ini")
    mp(port, "fs", "cp", ":config.ini", tmp)
    old = open(tmp, encoding="utf-8", newline="").read()
    new = edit_config(old, top, clock_hz)
    if new != old:
        open(tmp, "w", encoding="utf-8", newline="").write(new)
        mp(port, "fs", "cp", tmp, ":config.ini")
    print(f"  default project = {top}, clock = {clock_hz or 'not set'} Hz")

    step("Restarting the board")
    mp(port, "reset")
    show_boot(port)


def show_boot(port):
    try:
        import serial
    except ImportError:
        return
    # the COM port disappears and comes back while the board reboots, so keep reconnecting
    buf, ser, end = "", None, time.time() + 25
    while time.time() < end and "boot done" not in buf:
        try:
            if ser is None:
                ser = serial.Serial(port, 115200, timeout=0.3)
            buf += ser.read(4096).decode(errors="replace")
        except Exception:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            time.sleep(0.3)
    if ser is not None:
        ser.close()
    if "boot done" not in buf:
        print("  (did not see the boot log; the board is probably fine, check the display)")
    buf = re.sub(r"\x1b\[[0-9;]*m", "", buf)
    keys = ("Detected", "FPGA", "Transmission complete", "Enable design", "Clocking at", "<DemoBoard", "rror")
    for line in buf.splitlines():
        if any(k in line for k in keys):
            print("  " + line.strip())


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Clone, harden and load a Tiny Tapeout project on the TT FPGA breakout")
    ap.add_argument("target", help="GitHub URL or path to a project folder ('factory-test' = the Tiny Tapeout factory test)")
    ap.add_argument("--port", help="board COM port (default: auto-detect)")
    ap.add_argument("--clock-hz", type=int, help="project clock in Hz (default: clock_hz from info.yaml)")
    ap.add_argument("--breakout-target", choices=list(PCF), default="fabricfox",
                    help="fabricfox = current TT FPGA breakout (default), classic = original TT ASIC Sim board")
    ap.add_argument("--seed", type=int, default=int(os.environ.get("TT_FPGA_SEED", "10")), help="nextpnr seed")
    ap.add_argument("--no-upload", action="store_true", help="only build the .bin")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    use_repo_python()
    setup_oss_cad()
    project = get_project(args.target)
    info = read_info(project)
    clock_hz = args.clock_hz if args.clock_hz is not None else info["clock_hz"]
    print(f"\nProject: {info['title'] or info['top']}  ({info['top']}, {len(info['sources'])} source files, clock {clock_hz} Hz)")

    freq_mhz = clock_hz / 1e6 if clock_hz else float(os.environ.get("TT_FPGA_FREQ", "12"))
    bin_f = harden(project, info, args.breakout_target, args.seed, freq_mhz)
    if args.no_upload:
        print(f"\nDone. Bitstream: {bin_f}")
        return
    upload(bin_f, info, args.port, clock_hz)
    print("\nDone.")


if __name__ == "__main__":
    main()

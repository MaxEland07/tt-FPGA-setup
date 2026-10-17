# TT FPGA: build a Tiny Tapeout project and run it on the board

One command takes a GitHub repo (or a local project folder), builds it for the TT FPGA breakout, and loads it onto the board. A second command, once per computer, installs everything needed.

## Setup (once per computer)

```bash
git clone https://github.com/MaxEland07/tt-FPGA-setup.git tt-fpga
cd tt-fpga
```

then, depending on your system:

| System | Command |
|--------|---------|
| Windows | `.\setup.cmd` |
| Linux / macOS | `sh setup.sh` |
| Anywhere with Python 3.8+ | `python setup.py` |

Setup needs only **Python 3.8+ and git** (on Windows it offers to install Python through winget). It installs into this folder, with no admin rights:

- `.venv/`: Python environment with `mpremote` and `pyserial` (from `requirements.txt`)
- `.oss-cad-suite/`: the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) (yosys, nextpnr-ice40, icepack) for your OS and CPU. About 600 MB to download and 2 GB on disk. The download is verified against the SHA-256 published with the release, and it resumes if interrupted.

If you already have an OSS CAD Suite (`OSS_CAD_SUITE`, `~/oss-cad-suite`, `C:\oss-cad-suite`, `/opt/oss-cad-suite`, or on `PATH`), it is reused. Setup finishes by building the Tiny Tapeout factory test as a smoke test and checking for a connected board.

| Option | What it does |
|--------|--------------|
| `--check` | report what is installed, change nothing |
| `--latest` | use the newest OSS CAD Suite instead of the pinned one the repo was tested with |
| `--force` | download the suite even if one is found |
| `--skip-test` | skip the smoke-test build |

**Linux:** for serial access add yourself to the `dialout` group (`sudo usermod -aG dialout $USER`, then log out and in).
**Windows:** if extraction fails with a path-too-long error, clone the repo closer to the drive root, for example `C:\tt-fpga`.

## Use it

```bash
python ttfpga.py https://github.com/MaxEland07/tt-game-paddle-and-ball.git
```

It clones into `projects/<repo>` (or runs `git pull` if it's already there), then:

1. reads `info.yaml` (top module, source files, clock)
2. builds the bitstream with yosys, nextpnr-ice40 and icepack into `projects/<repo>/build/<top_module>.bin`
3. copies it to the board over USB, makes it the default project, sets its clock, and restarts the board

After that, the board loads and clocks the project by itself on every power-up. You can run `python ttfpga.py` from any Python; it switches to the repo's `.venv` on its own.

| Command | What it does |
|---------|--------------|
| `python ttfpga.py <url-or-folder>` | clone, build, upload |
| `python ttfpga.py <url-or-folder> --no-upload` | build only |
| `python ttfpga.py <url-or-folder> --clock-hz 2000000` | override the clock (default: `clock_hz` from `info.yaml`) |
| `python ttfpga.py <url-or-folder> --port COM7` | pick the board's serial port, e.g. `COM7` or `/dev/ttyACM0` (default: auto-detect) |
| `python ttfpga.py <url-or-folder> --breakout-target classic` | pinout for the original "TT ASIC Sim" board (default: `fabricfox`) |
| `python ttfpga.py factory-test` | switch back to the Tiny Tapeout factory test |

## Using it with Claude Code

This repo carries its own Claude Code configuration, so anyone who opens it in [Claude Code](https://claude.com/claude-code) gets the same assistant: [CLAUDE.md](CLAUDE.md) explains the project and its pitfalls, and the `tt-fpga` skill in `.claude/skills/` covers building, loading and troubleshooting. Ask it things like "load https://github.com/.../tt-my-project onto the board". Nothing personal (accounts, credentials, memory) is stored in the repo.

## Things to know

- **Verilog and SystemVerilog only.** For other languages (Amaranth, VHDL, ...) generate Verilog and list those files in `info.yaml`.
- **Designs that use Sky130 cells** (ring oscillators, delay chains that instantiate `sky130_fd_sc_hd__...` by name) have no equivalent on the FPGA. The script adds stand-ins from `fpga_shim/sky130_cells.v`, one lookup table per cell, kept as written. Cells that aren't in that file still fail with "not part of the design"; add them to the shim.
- **Combinational loops.** nextpnr can't analyse timing through a loop, so the script retries with `--ignore-loops`, and it builds anyway if only ring-internal hold violations remain, with a warning.
- **Timing is checked at the project's clock.** The build prints nextpnr's max frequency and warns if the design is too slow for `clock_hz`.
- **Clock accuracy.** The board rounds to the nearest clock it can make. The VGA game asks for 25.175 MHz and gets 25.25 MHz.
- **Inputs.** With the FPGA breakout the board is in "manual inputs" mode, so the DIP switches and buttons on the board drive `ui_in`.
- **Existing board settings.** The script only edits the `project =` default and the `[<top_module>]` section of the board's `config.ini`. If a project has `clock_hz: 0`, it keeps any clock you set earlier, or uses 10 Hz.
- **Testing by hand.** Don't enable a project with a bare `mpremote exec`. That skips the boot-time FPGA detection and loads the wrong shuttle. Press reset and let the board boot normally.

## Layout

| Path | What |
|------|------|
| `setup.py`, `setup.sh`, `setup.ps1`, `setup.cmd` | the setup command |
| `ttfpga.py` | build and upload |
| `toolchain.py` | finds the OSS CAD Suite and the `.venv` |
| `fpga/` | Tiny Tapeout pin files and the top-level wrapper, copied from [tt-support-tools](https://github.com/TinyTapeout/tt-support-tools) (Apache-2.0, see `fpga/LICENSE`) |
| `fpga_shim/` | FPGA stand-ins for Sky130 cells |
| `CLAUDE.md`, `.claude/` | Claude Code configuration |
| `projects/`, `.venv/`, `.oss-cad-suite/`, `.cache/` | generated, not committed |

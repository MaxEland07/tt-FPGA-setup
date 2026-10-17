# TT FPGA

This repo builds Tiny Tapeout (TT) projects for the iCE40 UP5K FPGA on the TT FPGA breakout and loads them onto the TT demoboard (RP2040/RP2350, MicroPython) over USB. The whole flow is `ttfpga.py`.

## First thing in a fresh clone

Run `python setup.py --check`. If anything is missing, run `python setup.py` (Windows: `.\setup.cmd`, Linux/macOS: `sh setup.sh`). It creates `.venv/` (mpremote, pyserial) and downloads the OSS CAD Suite into `.oss-cad-suite/`, then does a test build. Never `pip install` into the system Python for this repo.

## Everyday command

```
python ttfpga.py <github-url | project-folder | factory-test> [--no-upload] [--clock-hz N] [--port PORT] [--breakout-target fabricfox|classic]
```

It clones into `projects/<repo>` (or `git pull`s), reads `info.yaml`, runs yosys, nextpnr-ice40 and icepack into `projects/<repo>/build/<top>.bin`, then uploads it, makes it the default project, sets the clock and restarts the board. It re-runs itself under `.venv` automatically, so plain `python` works.

If the user only wants to check a design builds, use `--no-upload`. Uploading changes which project the board boots into, so say what you are about to load when the board holds something the user may care about.

## Facts that are easy to get wrong

- Verilog/SystemVerilog only. Other languages must be generated to Verilog and listed in `info.yaml`.
- Designs instantiating `sky130_fd_sc_hd__*` cells get FPGA stand-ins from `fpga_shim/sky130_cells.v` (one LUT per cell). If the build fails with a missing sky130 cell, add that cell to the shim with the right `LUT_INIT`.
- Combinational loops: `ttfpga.py` retries nextpnr with `--ignore-loops`, and builds anyway (with a warning) if only ring-internal hold violations remain.
- Never enable a project with a bare `mpremote exec`. It skips the boot-time FPGA detection and loads the wrong shuttle. Reset the board and let it boot normally.
- Only the `project =` line and the `[<top_module>]` section of the board's `config.ini` are edited. Do not rewrite the rest.
- The board rounds the clock to what it can make (25.175 MHz becomes 25.25 MHz). That is expected.
- `.bin` files are specific to a pinout: `fabricfox` (current breakout, default) vs `classic` (original TT ASIC Sim board).

## Layout

- `ttfpga.py`: build + upload. `toolchain.py`: finds the OSS CAD Suite / venv. `setup.py`, `setup.sh`, `setup.ps1`, `setup.cmd`: installation.
- `fpga/`: TT pin files (`*.pcf`) and `tt_fpga_top.v` wrapper, vendored from TinyTapeout/tt-support-tools (Apache-2.0).
- `fpga_shim/`: Sky130 stand-ins. `projects/`, `.venv/`, `.oss-cad-suite/`, `.cache/`: generated, git-ignored.

For troubleshooting a failed build or board problem, use the `tt-fpga` skill.

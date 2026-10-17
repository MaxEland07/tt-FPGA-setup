---
name: tt-fpga
description: Build a Tiny Tapeout project for the TT FPGA breakout (iCE40 UP5K) and load it onto the TT demoboard, or troubleshoot setup, synthesis, place-and-route, upload and boot problems in this repo. Use when the user gives a GitHub URL for a tt-* project, asks to put a design on the board, or hits an error from ttfpga.py or setup.py.
---

# TT FPGA workflow

## 1. Make sure the toolchain exists

```
python setup.py --check
```

Missing pieces: run `python setup.py` (Windows `.\setup.cmd`, Linux/macOS `sh setup.sh`). It downloads about 600 MB and installs about 2 GB into `.oss-cad-suite/`, so tell the user before starting it.

## 2. Build and load

```
python ttfpga.py <github-url-or-folder>            # clone, build, upload
python ttfpga.py <github-url-or-folder> --no-upload  # build only
```

Add `--clock-hz N` to override `clock_hz` from `info.yaml`, `--port` if auto-detect picks the wrong serial port, `--breakout-target classic` for the original TT ASIC Sim board.

After a successful upload the output shows the board's boot log (`Detected`, `Enable design`, `Clocking at`). Report the max frequency nextpnr printed and any warnings.

## 3. Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `yosys / nextpnr-ice40 / icepack not found` | Toolchain not installed: `python setup.py`. A custom location: set `OSS_CAD_SUITE` to the suite folder. |
| `No module named mpremote` / `serial` | Not running in `.venv`. Use `python ttfpga.py` from the repo root (it re-execs into `.venv`), or re-run `python setup.py`. |
| `Could not find the board` | Plug in USB; pass `--port COMx` or `--port /dev/ttyACM0`. Linux: `sudo usermod -aG dialout $USER`, then log out and in. |
| `Language 'X' is not supported` | Project is not Verilog/SystemVerilog. Generate Verilog and list those files under `source_files` in `info.yaml`. |
| `Source file listed in info.yaml not found` | Paths in `source_files` are relative to the project's `src/`. |
| yosys error about an unknown `sky130_fd_sc_hd__*` module | Add the cell to `fpga_shim/sky130_cells.v` (one `SB_LUT4` with the right `LUT_INIT`, bit n is the output for `{I3,I2,I1,I0}=n`, keep the `(* keep *)`). |
| nextpnr "combinational loops" | Handled automatically with `--ignore-loops`; expected for ring oscillators. |
| `design does not meet timing` warning | The design is slower than `clock_hz` on this FPGA. It still builds; lower the clock with `--clock-hz` or fix the critical path in the log (`projects/<repo>/build/02-nextpnr.log`). |
| nextpnr placement fails | Try another seed: `--seed 3` (or `TT_FPGA_SEED`). Read `build/02-nextpnr.log`. |
| Board boots the wrong design or "Shuttle unknown" | Someone enabled a project with a bare `mpremote exec`. Press the board's reset button (or `python -m mpremote connect <port> reset`) and let it boot normally. |
| Download in `setup.py` fails midway | Run it again; it resumes the partial download and verifies the SHA-256. |
| Windows extraction errors (path too long) | Clone the repo near the drive root, e.g. `C:\tt-fpga`. |

## 4. Rules

- Build logs and outputs are in `projects/<repo>/build/`. Read the log before guessing.
- Do not edit the board's `config.ini` beyond what `ttfpga.py` does.
- Do not commit `projects/`, `.venv/`, `.oss-cad-suite/` or `.cache/`.

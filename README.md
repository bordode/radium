# Radium

Hobby OS.

## Memory Map

| Begin       | End (incl.) | Purpose
| ----------- | ----------- | -------
| `0000_0000` | `0000_0fff` | Null page. Not mapped in.
| `0000_1000` | `000f_ffff` | Low memory. Untouched.
| `0010_0000` | *???*       | The kernel is loaded here by GRUB.
| *???*       | `0fbf_ffff` | Kernel dynamic allocation area.
| `0fc0_0000` | `0fc0_0fff` | Kernel stack guard page. Not mapped in.
| `0fc0_1000` | `0fff_ffff` | Kernel stack.
| `1000_0000` | `ffbf_ffff` | User address space.
| `ffc0_0000` | `ffff_efff` | Recursively mapped page tables
| `ffff_f000` | `ffff_ffff` | Recursively mapped page directory

## Cloud9 Little Red Dot Investigation

This repo also includes a dependency-free Python Cloud9 Assembly helper for triaging JWST “little red dot” candidates as early black-hole growth systems. The tool reads a candidate CSV, estimates the cosmic age at each redshift, calculates a simple Eddington-growth seed-mass diagnostic, scores compact/X-ray-obscured candidates, and renders a Markdown report.

Run the sample investigation with:

```sh
make cloud9-lrd
```

The default catalogue lives at `data/little_red_dots/sample_candidates.csv`, the generated report is written to `docs/cloud9_lrd_investigation.md`, and the Python entry point is `tools/cloud9_lrd_investigator.py`.

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

## Cloud9 / Colab Assembly Analysis

A Colab-ready analyzer is available at `tools/cloud9_assembly_analysis_colab.py`. It can be pasted into Google Colab or run locally to generate a static-analysis report for the assembly and C portions of the project, including source inventory CSVs, assembly instruction/register frequency tables, label and call-target listings, optional build-artifact inspection, and charts when `matplotlib` is installed.

Run it locally from the repository root with:

```sh
RADIUM_ANALYZER_OUTPUT=./radium_analysis_report python tools/cloud9_assembly_analysis_colab.py
```

To inspect compiled artifacts as part of the report, install the project build tools and run with `RADIUM_ANALYZER_RUN_BUILD=1`.

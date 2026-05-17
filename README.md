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

## Cloud9 Assembly Investigation

Run the dependency-free Python investigation utility to classify hypothetical
negative-mass binary systems from a Cloud9-style shell:

```sh
python3 tools/cloud9_assembly.py
```

The utility prints ordinary chirp, anti-chirp, repulsive, runaway, and
equivalence-principle-breaking dipole-candidate regimes.  Custom cases can be
provided with a CSV containing `name,m1g,m1i,m2g,m2i[,separation]` columns:

```sh
python3 tools/cloud9_assembly.py --csv cases.csv --separation 10
```

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

## Investigation Tools

Run the Avi Loeb article toy investigation script with Python 3:

```sh
python3 tools/loeb_investigation.py
```

The script assembles quick, dependency-free checks for positive/negative-mass
binary sign logic, early-universe temperature estimates, and Galactic-center
orbital scales. Its output is intended as an investigation checklist rather than
a substitute for numerical relativity, stellar-evolution, or hydrodynamic
simulations.

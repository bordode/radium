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
## Cloud9 Negative-Mass Assembly Probe

The `tools/cloud9_negative_mass_assembly.py` helper is a stdlib-only Python
probe for assembling quick diagnostics around signed-mass binary scenarios,
including ordinary chirps, mixed-sign anti-chirps, zero-total-mass runaway
cases, negative-total-mass repulsion, and equivalence-principle mismatch flags
for dipole radiation. It is designed to run in lightweight Cloud9-style shells:

```sh
python3 tools/cloud9_negative_mass_assembly.py --m1 30 --m2 -10 --separation 1e9
```

Run its checks with:

```sh
python3 -m unittest tools/test_cloud9_negative_mass_assembly.py
```


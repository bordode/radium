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

## Syscall Investigation

Use `tools/syscall_audit.py --check` when changing syscalls or the `sysenter`
assembly path. The dependency-free Python audit cross-checks the public syscall
numbers in `api/radium.h`, the kernel dispatch table in `kernel/src/syscall.c`,
the user-space wrappers in `user/crt1.c`, and the assembly exports/register
layout used by `user/crt0.asm` and `kernel/src/syscall_entry.asm`.


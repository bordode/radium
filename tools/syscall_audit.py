#!/usr/bin/env python3
"""Audit Radium syscall declarations, dispatch wiring, and assembly entrypoints.

The script is intentionally dependency-free so it can run in lightweight IDE
shells such as AWS Cloud9 as well as local development environments.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_HEADER = ROOT / "api" / "radium.h"
SYSCALL_C = ROOT / "kernel" / "src" / "syscall.c"
KERNEL_ENTRY_ASM = ROOT / "kernel" / "src" / "syscall_entry.asm"
USER_CRT_C = ROOT / "user" / "crt1.c"
USER_CRT_ASM = ROOT / "user" / "crt0.asm"


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


DEFINE_RE = re.compile(r"^\s*#define\s+(SYS_[A-Z0-9_]+)\s+(\d+)\b", re.MULTILINE)
TABLE_RE = re.compile(r"\[\s*(SYS_[A-Z0-9_]+)\s*\]\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)")
WRAPPER_RE = re.compile(r"(_syscall[0-3])\s*\(\s*(SYS_[A-Z0-9_]+)")
GLOBAL_RE = re.compile(r"^\s*global\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: could not read {path.relative_to(ROOT)}: {exc}") from exc


def parse_syscall_numbers() -> dict[str, int]:
    return {name: int(value) for name, value in DEFINE_RE.findall(read(API_HEADER))}


def parse_dispatch_table() -> dict[str, str]:
    return {name: handler for name, handler in TABLE_RE.findall(read(SYSCALL_C))}


def parse_user_wrappers() -> dict[str, set[str]]:
    wrappers: dict[str, set[str]] = {}
    for wrapper, name in WRAPPER_RE.findall(read(USER_CRT_C)):
        wrappers.setdefault(name, set()).add(wrapper)
    return wrappers


def assembly_exports(path: Path) -> set[str]:
    return set(GLOBAL_RE.findall(read(path)))


def audit() -> list[Finding]:
    findings: list[Finding] = []
    numbers = parse_syscall_numbers()
    table = parse_dispatch_table()
    wrappers = parse_user_wrappers()
    syscall_c = read(SYSCALL_C)
    kernel_asm = read(KERNEL_ENTRY_ASM)
    user_asm = read(USER_CRT_ASM)
    user_exports = assembly_exports(USER_CRT_ASM)
    kernel_exports = assembly_exports(KERNEL_ENTRY_ASM)

    duplicate_values: dict[int, list[str]] = {}
    for name, number in numbers.items():
        duplicate_values.setdefault(number, []).append(name)
    for number, names in sorted(duplicate_values.items()):
        if len(names) > 1:
            findings.append(Finding("ERROR", f"syscall number {number} is shared by {', '.join(sorted(names))}"))

    for name in sorted(numbers, key=numbers.get):
        if name not in table:
            findings.append(Finding("ERROR", f"{name} is declared in api/radium.h but missing from syscall_table"))
        if name not in wrappers:
            findings.append(Finding("WARN", f"{name} has no user-space wrapper usage in user/crt1.c"))

    for name in sorted(table):
        if name not in numbers:
            findings.append(Finding("ERROR", f"{name} is wired in syscall_table but not declared in api/radium.h"))

    expected_user_exports = {"__syscall0", "__syscall1", "__syscall2", "__syscall3"}
    missing_user_exports = sorted(expected_user_exports - user_exports)
    if missing_user_exports:
        findings.append(Finding("ERROR", f"user/crt0.asm is missing exports: {', '.join(missing_user_exports)}"))

    expected_kernel_exports = {"syscall_entry", "syscall_init"}
    missing_kernel_exports = sorted(expected_kernel_exports - kernel_exports)
    if missing_kernel_exports:
        findings.append(Finding("ERROR", f"kernel/src/syscall_entry.asm is missing exports: {', '.join(missing_kernel_exports)}"))

    required_kernel_tokens = ["wrmsr", "sysexit", "call syscall_dispatch"]
    for token in required_kernel_tokens:
        if token not in kernel_asm:
            findings.append(Finding("ERROR", f"kernel syscall assembly does not contain expected token: {token}"))

    if "sysenter" not in user_asm:
        findings.append(Finding("ERROR", "user syscall assembly does not contain expected token: sysenter"))

    if "REG_VECTOR(regs) >= countof(syscall_table)" not in syscall_c:
        findings.append(Finding("ERROR", "syscall_dispatch must reject vectors >= countof(syscall_table) before indexing"))

    return findings


def print_report(findings: list[Finding]) -> None:
    numbers = parse_syscall_numbers()
    table = parse_dispatch_table()
    wrappers = parse_user_wrappers()

    print("Radium syscall/assembly audit")
    print("=============================\n")
    print("Syscall ABI:")
    for name, number in sorted(numbers.items(), key=lambda item: item[1]):
        handler = table.get(name, "<missing>")
        wrapper_list = ", ".join(sorted(wrappers.get(name, []))) or "<none>"
        print(f"  {number:2d}  {name:<18} handler={handler:<20} wrappers={wrapper_list}")

    print("\nAssembly entrypoints:")
    print(f"  kernel: {', '.join(sorted(assembly_exports(KERNEL_ENTRY_ASM)))}")
    print(f"  user:   {', '.join(sorted(assembly_exports(USER_CRT_ASM)))}")

    if findings:
        print("\nFindings:")
        for finding in findings:
            print(f"  {finding.level}: {finding.message}")
    else:
        print("\nFindings: no blocking issues found")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only print findings")
    args = parser.parse_args(argv)

    findings = audit()
    if args.quiet:
        for finding in findings:
            print(f"{finding.level}: {finding.message}")
    else:
        print_report(findings)

    return 1 if any(finding.level == "ERROR" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

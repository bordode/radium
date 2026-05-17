#!/usr/bin/env python3
"""Inspect Radium syscall declarations, kernel dispatch entries, and assembly ABI.

The script is intentionally dependency-free so it can be run from a local shell,
CI job, or a browser IDE terminal such as Cloud9. It performs lightweight static
checks that keep the syscall number definitions, dispatch table, C runtime
wrappers, and SYSENTER assembly register convention in sync.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
API_HEADER = ROOT / "api" / "radium.h"
KERNEL_SYSCALL = ROOT / "kernel" / "src" / "syscall.c"
USER_CRT = ROOT / "user" / "crt1.c"
USER_ASM = ROOT / "user" / "crt0.asm"

DEFINE_RE = re.compile(r"^#define\s+(SYS_[A-Z0-9_]+)\s+(\d+)\b", re.MULTILINE)
TABLE_ENTRY_RE = re.compile(r"\[(SYS_[A-Z0-9_]+)\]\s*=\s*(syscall_[a-z0-9_]+)")
USER_WRAPPER_RE = re.compile(r"\b_syscall(?P<argc>[0-3])\s*\(\s*(?P<number>SYS_[A-Z0-9_]+)")
KERNEL_ARG_RE = re.compile(r"#define\s+REG_ARG(?P<index>[123])\(regs\)\s+\(\(regs\)->(?P<reg>[a-z]{3})\)")
ASM_ARG_RE = re.compile(r"mov\s+(?P<reg>ebx|edi|esi),\s*\[esp\+[^\n]+", re.IGNORECASE)
BOUNDS_RE = re.compile(r"REG_VECTOR\(regs\)\s*(?P<op>>=?|<|<=|==)\s*countof\(syscall_table\)")

EXPECTED_ARG_REGISTERS = ("ebx", "edi", "esi")


@dataclasses.dataclass(frozen=True)
class Finding:
    level: str
    message: str


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_defines(text: str) -> dict[str, int]:
    return {name: int(number) for name, number in DEFINE_RE.findall(text)}


def parse_table(text: str) -> dict[str, str]:
    return dict(TABLE_ENTRY_RE.findall(text))


def parse_user_wrappers(text: str) -> dict[str, int]:
    return {match.group("number"): int(match.group("argc")) for match in USER_WRAPPER_RE.finditer(text)}


def parse_kernel_arg_registers(text: str) -> tuple[str, ...]:
    registers: dict[int, str] = {}
    for match in KERNEL_ARG_RE.finditer(text):
        registers[int(match.group("index"))] = match.group("reg")
    return tuple(registers[index] for index in sorted(registers))


def parse_asm_arg_registers(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for match in ASM_ARG_RE.finditer(text):
        reg = match.group("reg").lower()
        if reg not in seen:
            seen.append(reg)
    return tuple(seen)


def investigate() -> list[Finding]:
    api_text = read(API_HEADER)
    kernel_text = read(KERNEL_SYSCALL)
    user_text = read(USER_CRT)
    asm_text = read(USER_ASM)

    defines = parse_defines(api_text)
    table = parse_table(kernel_text)
    wrappers = parse_user_wrappers(user_text)
    kernel_arg_registers = parse_kernel_arg_registers(kernel_text)
    asm_arg_registers = parse_asm_arg_registers(asm_text)

    findings: list[Finding] = []

    if not defines:
        findings.append(Finding("ERROR", f"No SYS_* definitions found in {API_HEADER.relative_to(ROOT)}"))
        return findings

    duplicate_numbers = sorted({number for number in defines.values() if list(defines.values()).count(number) > 1})
    for number in duplicate_numbers:
        names = sorted(name for name, value in defines.items() if value == number)
        findings.append(Finding("ERROR", f"Syscall number {number} is shared by {', '.join(names)}"))

    for expected, name in enumerate(sorted(defines, key=defines.get)):
        actual = defines[name]
        if actual != expected:
            findings.append(Finding("WARN", f"{name} is {actual}, leaving a gap before expected number {expected}"))

    for name in sorted(defines, key=defines.get):
        if name not in table:
            findings.append(Finding("ERROR", f"{name} is defined but missing from syscall_table"))

    for name in sorted(table):
        if name not in defines:
            findings.append(Finding("ERROR", f"{name} appears in syscall_table but is not defined in api/radium.h"))

    for name in sorted(wrappers):
        if name not in defines:
            findings.append(Finding("ERROR", f"User wrapper calls undefined {name}"))
        elif name not in table:
            findings.append(Finding("ERROR", f"User wrapper calls {name}, but it is not dispatched by the kernel"))

    for name in sorted(set(defines) - set(wrappers)):
        # SYS_EXIT is still reachable through exit(), and all current syscalls have wrappers.
        findings.append(Finding("WARN", f"{name} has no user-space wrapper detected in user/crt1.c"))

    if kernel_arg_registers != EXPECTED_ARG_REGISTERS:
        findings.append(
            Finding(
                "ERROR",
                "Kernel syscall argument registers are "
                f"{kernel_arg_registers}, expected {EXPECTED_ARG_REGISTERS}",
            )
        )

    if asm_arg_registers != EXPECTED_ARG_REGISTERS:
        findings.append(
            Finding(
                "ERROR",
                "User assembly syscall argument registers are "
                f"{asm_arg_registers}, expected {EXPECTED_ARG_REGISTERS}",
            )
        )

    bounds_match = BOUNDS_RE.search(kernel_text)
    if not bounds_match:
        findings.append(Finding("WARN", "Could not find syscall_table bounds check"))
    elif bounds_match.group("op") != ">=":
        findings.append(
            Finding(
                "ERROR",
                "syscall_table bounds check should reject REG_VECTOR(regs) >= countof(syscall_table)",
            )
        )

    if not findings:
        findings.append(Finding("OK", f"{len(defines)} syscalls are defined, dispatched, and ABI-consistent"))

    return findings


def print_report(findings: Iterable[Finding]) -> None:
    for finding in findings:
        print(f"{finding.level}: {finding.message}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures in addition to errors.",
    )
    args = parser.parse_args(argv)

    findings = investigate()
    print_report(findings)

    failure_levels = {"ERROR"}
    if args.strict:
        failure_levels.add("WARN")

    return 1 if any(finding.level in failure_levels for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

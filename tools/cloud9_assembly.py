#!/usr/bin/env python3
"""Cloud9 Assembly investigation checks for Radium's syscall path.

This intentionally uses only the Python standard library so it can run in a
minimal Cloud9-style development image.  It cross-checks the public syscall
numbers, the kernel dispatch table, the libc-style wrappers, and the x86
assembly bridge used by SYSENTER.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

SYSCALL_DEFINE_RE = re.compile(r"^\s*#define\s+(SYS_[A-Z0-9_]+)\s+(\d+)\b", re.MULTILINE)
TABLE_ENTRY_RE = re.compile(r"\[\s*(SYS_[A-Z0-9_]+)\s*\]\s*=\s*(syscall_[a-z0-9_]+)")
WRAPPER_RE = re.compile(r"\b_syscall(?P<argc>[0-3])\s*\(\s*(?P<name>SYS_[A-Z0-9_]+)\b")
GLOBAL_RE = re.compile(r"^\s*global\s+(__syscall[0-3]|syscall_entry|syscall_init)\b", re.MULTILINE)

EXPECTED_USER_ARG_REGISTERS = {
    1: ("ebx",),
    2: ("ebx", "edi"),
    3: ("ebx", "edi", "esi"),
}
EXPECTED_KERNEL_ARG_MACROS = {
    "REG_ARG1": "ebx",
    "REG_ARG2": "edi",
    "REG_ARG3": "esi",
}


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def read(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


def syscall_definitions(header: str) -> dict[str, int]:
    return {name: int(value) for name, value in SYSCALL_DEFINE_RE.findall(header)}


def dispatch_table(syscall_c: str) -> dict[str, str]:
    return {name: func for name, func in TABLE_ENTRY_RE.findall(syscall_c)}


def wrapper_arities(crt1_c: str) -> dict[str, int]:
    wrappers: dict[str, int] = {}
    for match in WRAPPER_RE.finditer(crt1_c):
        wrappers[match.group("name")] = int(match.group("argc"))
    return wrappers


def assembly_exports(*sources: str) -> set[str]:
    exports: set[str] = set()
    for source in sources:
        exports.update(GLOBAL_RE.findall(source))
    return exports


def line_contains(source: str, *needles: str) -> bool:
    return any(all(needle in line for needle in needles) for line in source.splitlines())


def investigate() -> tuple[list[str], list[Finding]]:
    api = read("api/radium.h")
    syscall_c = read("kernel/src/syscall.c")
    crt1_c = read("user/crt1.c")
    crt0_asm = read("user/crt0.asm")
    syscall_entry_asm = read("kernel/src/syscall_entry.asm")

    syscalls = syscall_definitions(api)
    table = dispatch_table(syscall_c)
    wrappers = wrapper_arities(crt1_c)
    exports = assembly_exports(crt0_asm, syscall_entry_asm)

    findings: list[Finding] = []
    lines: list[str] = []

    lines.append("Cloud9 Assembly syscall investigation")
    lines.append("=====================================")
    lines.append(f"Repository: {ROOT}")
    lines.append("")
    lines.append("Syscall inventory:")
    for name, number in sorted(syscalls.items(), key=lambda item: item[1]):
        handler = table.get(name, "<missing>")
        wrapper = wrappers.get(name)
        wrapper_text = f"_syscall{wrapper}" if wrapper is not None else "<kernel-only/no wrapper>"
        lines.append(f"  {number:>2}  {name:<16} handler={handler:<20} wrapper={wrapper_text}")

    if not syscalls:
        findings.append(Finding("error", "No SYS_* definitions found in api/radium.h."))

    duplicate_numbers = sorted({value for value in syscalls.values() if list(syscalls.values()).count(value) > 1})
    for number in duplicate_numbers:
        names = sorted(name for name, value in syscalls.items() if value == number)
        findings.append(Finding("error", f"Duplicate syscall number {number}: {', '.join(names)}."))

    expected_numbers = list(range(len(syscalls)))
    actual_numbers = sorted(syscalls.values())
    if actual_numbers != expected_numbers:
        findings.append(
            Finding(
                "warning",
                f"Syscall numbers are not contiguous from zero: expected {expected_numbers}, got {actual_numbers}.",
            )
        )

    for name in sorted(syscalls):
        if name not in table:
            findings.append(Finding("error", f"{name} is defined publicly but missing from syscall_table."))

    for name in sorted(table):
        if name not in syscalls:
            findings.append(Finding("error", f"{name} appears in syscall_table but is not defined in api/radium.h."))

    if "REG_VECTOR(regs) >= countof(syscall_table)" not in syscall_c:
        findings.append(Finding("error", "syscall_dispatch must reject vectors with >= countof(syscall_table)."))

    for macro, register in EXPECTED_KERNEL_ARG_MACROS.items():
        if f"#define {macro}(regs) ((regs)->{register})" not in syscall_c:
            findings.append(Finding("error", f"Kernel macro {macro} should read {register}."))

    for argc, registers in EXPECTED_USER_ARG_REGISTERS.items():
        label = f"__syscall{argc}:"
        start = crt0_asm.find(label)
        end = crt0_asm.find(f"__syscall{argc + 1}:", start) if argc < 3 else len(crt0_asm)
        block = crt0_asm[start:end] if start >= 0 else ""
        for register in registers:
            if not re.search(rf"\bmov\s+{register}\s*,\s*\[esp[+]", block):
                findings.append(Finding("error", f"{label} does not load argument register {register}."))

    for symbol in ("__syscall0", "__syscall1", "__syscall2", "__syscall3", "syscall_entry", "syscall_init"):
        if symbol not in exports:
            findings.append(Finding("error", f"Assembly symbol {symbol} is not exported."))

    for required in (
        ("sysenter",),
        ("push", "ecx"),
        ("push", "edx"),
        ("pop", "edx"),
        ("pop", "ecx"),
    ):
        if not line_contains(crt0_asm, *required):
            findings.append(Finding("error", f"user/crt0.asm is missing expected instruction pattern: {' '.join(required)}."))

    for required in (
        ("wrmsr",),
        ("pusha",),
        ("call", "syscall_dispatch"),
        ("sysexit",),
    ):
        if not line_contains(syscall_entry_asm, *required):
            findings.append(
                Finding("error", f"kernel/src/syscall_entry.asm is missing expected instruction pattern: {' '.join(required)}.")
            )

    return lines, findings


def print_findings(findings: Iterable[Finding]) -> int:
    exit_code = 0
    findings = list(findings)
    if findings:
        print("\nFindings:")
    else:
        print("\nFindings: none")

    for finding in findings:
        print(f"  [{finding.level}] {finding.message}")
        if finding.level == "error":
            exit_code = 1

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Investigate Radium syscall assembly wiring.")
    parser.add_argument("--quiet", action="store_true", help="Only print findings.")
    args = parser.parse_args(argv)

    report, findings = investigate()
    if not args.quiet:
        print("\n".join(report))
    return print_findings(findings)


if __name__ == "__main__":
    sys.exit(main())

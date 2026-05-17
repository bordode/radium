#!/usr/bin/env python3
"""Audit Radium's syscall ABI across C headers, kernel dispatch, and assembly.

The script is intentionally dependency-free so it can run in a small Cloud9,
Vagrant, or local shell while investigating syscall/assembly changes.
"""
from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys
from collections.abc import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
API_HEADER = ROOT / "api" / "radium.h"
KERNEL_SYSCALL = ROOT / "kernel" / "src" / "syscall.c"
KERNEL_REGS = ROOT / "kernel" / "inc" / "syscall.h"
USER_CRT = ROOT / "user" / "crt1.c"
USER_ASM = ROOT / "user" / "crt0.asm"
KERNEL_ASM = ROOT / "kernel" / "src" / "syscall_entry.asm"

DEFINE_RE = re.compile(r"^#define\s+(SYS_[A-Z0-9_]+)\s+(\d+)\b", re.MULTILINE)
TABLE_RE = re.compile(r"\[(SYS_[A-Z0-9_]+)\]\s*=\s*(syscall_[a-z0-9_]+)")
WRAPPER_RE = re.compile(
    r"(?P<return>\w+)\s*\n(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\([^)]*\)\n\{(?P<body>.*?)\n\}",
    re.DOTALL,
)
CALL_RE = re.compile(r"_syscall(?P<argc>[0-3])\((?P<symbol>SYS_[A-Z0-9_]+)")
REG_STRUCT_RE = re.compile(r"typedef\s+struct\s*\{(?P<body>.*?)\}\s*registers_t", re.DOTALL)
FIELD_RE = re.compile(r"uint32_t\s+([a-z0-9_]+)\s*;")
ASM_GLOBAL_RE = re.compile(r"^global\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
ASM_DEFINE_RE = re.compile(r"^%define\s+([A-Za-z0-9_]+)\s+([^\n]+)", re.MULTILINE)
DISPATCH_BOUND_RE = re.compile(r"if\s*\(\s*REG_VECTOR\(regs\)\s*>=\s*countof\(syscall_table\)\s*\)")

EXPECTED_REGS = ["edi", "esi", "ebp", "esp", "ebx", "edx", "ecx", "eax"]
EXPECTED_ARG_REGS = {
    "number": "eax",
    "arg1": "ebx",
    "arg2": "edi",
    "arg3": "esi",
    "return": "eax",
}


@dataclasses.dataclass(frozen=True)
class Syscall:
    symbol: str
    number: int
    handler: str | None = None
    wrapper: str | None = None
    argc: int | None = None


def read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc


def parse_syscall_numbers(text: str) -> dict[str, int]:
    return {symbol: int(number) for symbol, number in DEFINE_RE.findall(text)}


def parse_table(text: str) -> dict[str, str]:
    return {symbol: handler for symbol, handler in TABLE_RE.findall(text)}


def parse_wrappers(text: str) -> dict[str, tuple[str, int]]:
    wrappers: dict[str, tuple[str, int]] = {}
    for match in WRAPPER_RE.finditer(text):
        call = CALL_RE.search(match.group("body"))
        if call:
            wrappers[call.group("symbol")] = (match.group("name"), int(call.group("argc")))
    return wrappers


def parse_registers(text: str) -> list[str]:
    match = REG_STRUCT_RE.search(text)
    if not match:
        return []
    return FIELD_RE.findall(match.group("body"))


def parse_asm_exports(text: str) -> list[str]:
    return ASM_GLOBAL_RE.findall(text)


def parse_asm_defines(text: str) -> dict[str, str]:
    return {name: value.strip() for name, value in ASM_DEFINE_RE.findall(text)}


def build_inventory() -> list[Syscall]:
    numbers = parse_syscall_numbers(read(API_HEADER))
    table = parse_table(read(KERNEL_SYSCALL))
    wrappers = parse_wrappers(read(USER_CRT))

    inventory: list[Syscall] = []
    for symbol, number in sorted(numbers.items(), key=lambda item: item[1]):
        wrapper = wrappers.get(symbol)
        inventory.append(
            Syscall(
                symbol=symbol,
                number=number,
                handler=table.get(symbol),
                wrapper=wrapper[0] if wrapper else None,
                argc=wrapper[1] if wrapper else None,
            )
        )
    return inventory


def report(inventory: Iterable[Syscall]) -> str:
    lines = [
        "Radium syscall investigation",
        "=============================",
        "",
        "ABI summary:",
        f"  syscall number: {EXPECTED_ARG_REGS['number']}",
        f"  arg1/arg2/arg3: {EXPECTED_ARG_REGS['arg1']}/{EXPECTED_ARG_REGS['arg2']}/{EXPECTED_ARG_REGS['arg3']}",
        f"  return value:   {EXPECTED_ARG_REGS['return']}",
        "",
        "Syscall table:",
    ]
    for call in inventory:
        argc = "-" if call.argc is None else str(call.argc)
        wrapper = call.wrapper or "<missing>"
        handler = call.handler or "<missing>"
        lines.append(f"  {call.number:2d} {call.symbol:<16} wrapper={wrapper:<12} argc={argc} handler={handler}")
    return "\n".join(lines)


def validate(inventory: list[Syscall]) -> list[str]:
    errors: list[str] = []

    numbers = [call.number for call in inventory]
    if numbers != list(range(len(numbers))):
        errors.append(f"syscall numbers must be contiguous from 0; found {numbers}")

    for call in inventory:
        if call.handler is None:
            errors.append(f"{call.symbol} is declared in api/radium.h but missing from syscall_table")
        if call.wrapper is None:
            errors.append(f"{call.symbol} is declared in api/radium.h but has no user wrapper in user/crt1.c")

    kernel_text = read(KERNEL_SYSCALL)
    if not DISPATCH_BOUND_RE.search(kernel_text):
        errors.append("syscall_dispatch must reject REG_VECTOR(regs) >= countof(syscall_table)")

    table_symbols = set(parse_table(kernel_text))
    header_symbols = {call.symbol for call in inventory}
    for symbol in sorted(table_symbols - header_symbols):
        errors.append(f"{symbol} is in syscall_table but not declared in api/radium.h")

    registers = parse_registers(read(KERNEL_REGS))
    if registers != EXPECTED_REGS:
        errors.append(f"registers_t order must match pusha order {EXPECTED_REGS}; found {registers}")

    user_exports = set(parse_asm_exports(read(USER_ASM)))
    for name in ["__syscall0", "__syscall1", "__syscall2", "__syscall3"]:
        if name not in user_exports:
            errors.append(f"user/crt0.asm does not export {name}")

    kernel_exports = set(parse_asm_exports(read(KERNEL_ASM)))
    for name in ["syscall_entry", "syscall_init"]:
        if name not in kernel_exports:
            errors.append(f"kernel/src/syscall_entry.asm does not export {name}")

    msrs = parse_asm_defines(read(KERNEL_ASM))
    for name in ["IA32_SYSENTER_CS", "IA32_SYSENTER_ESP", "IA32_SYSENTER_EIP"]:
        if name not in msrs:
            errors.append(f"kernel/src/syscall_entry.asm missing {name} MSR definition")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero if the syscall ABI audit finds a mismatch")
    args = parser.parse_args(argv)

    inventory = build_inventory()
    print(report(inventory))

    errors = validate(inventory)
    if errors:
        print("\nFindings:")
        for error in errors:
            print(f"  ERROR: {error}")
    elif args.check:
        print("\nCheck passed: syscall declarations, wrappers, dispatch table, and assembly exports agree.")

    return 1 if args.check and errors else 0


if __name__ == "__main__":
    sys.exit(main())

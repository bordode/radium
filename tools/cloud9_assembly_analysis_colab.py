# -*- coding: utf-8 -*-
"""Cloud9 / Google Colab assembly-project analyzer for Radium.

This file is intentionally written as a Colab-friendly Python script: upload it to
Google Colab, paste it into a notebook cell, or open it with Colab's "Open
notebook from GitHub" flow after converting cells with jupytext if desired.

What it analyzes:
  * Assembly source inventory and instruction-frequency tables.
  * Label definitions, external symbol references, and a best-effort call graph.
  * Kernel/user C source inventory, syscall references, and memory-map constants.
  * Makefile/build metadata.
  * Optional build-artifact inspection with readelf, nm, size, and objdump when a
    compiled kernel/radium.bin or user/init.bin exists.
  * Optional charts and downloadable CSV/JSON reports.

Quick Colab use:
  1. Runtime -> Run all.
  2. Set REPO_SOURCE below to one of:
       "upload"  - upload a zip/tar of this repository,
       "clone"   - clone from REPO_URL,
       "mounted" - use an already-mounted Google Drive path,
       "local"   - use the current runtime path.
  3. Read the generated report under /content/radium_analysis_report.

The analyzer avoids modifying the Radium source tree. It writes reports to
OUTPUT_DIR only.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# %% [markdown]
# # Cloud9 Assembly Project Analyzer
#
# This notebook-style script produces a static-analysis report for the Radium
# hobby OS assembly/C codebase. It is designed for Google Colab and also runs in
# Cloud9 or a local Python 3 environment.

# %% Configuration
REPO_SOURCE = os.environ.get("RADIUM_ANALYZER_SOURCE", "local")
REPO_URL = os.environ.get("RADIUM_ANALYZER_REPO_URL", "")
MOUNTED_REPO_PATH = os.environ.get("RADIUM_ANALYZER_MOUNTED_PATH", "/content/radium")
LOCAL_REPO_PATH = os.environ.get("RADIUM_ANALYZER_LOCAL_PATH", ".")
OUTPUT_DIR = Path(os.environ.get("RADIUM_ANALYZER_OUTPUT", "/content/radium_analysis_report"))
RUN_BUILD = os.environ.get("RADIUM_ANALYZER_RUN_BUILD", "0") == "1"
MAX_SOURCE_SNIPPET_LINES = int(os.environ.get("RADIUM_ANALYZER_SNIPPET_LINES", "8"))

ASM_EXTENSIONS = {".asm", ".s", ".S"}
C_EXTENSIONS = {".c", ".h"}
IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "build",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

ASM_REGISTER_PATTERN = re.compile(
    r"\b(?:e?[abcd]x|e?[sd]i|e?[sb]p|eip|esp|cs|ds|es|fs|gs|ss|cr[0-4]|dr[0-7])\b",
    re.IGNORECASE,
)
ASM_LABEL_PATTERN = re.compile(r"^\s*([A-Za-z_.$?][\w.$?]*):")
ASM_GLOBAL_PATTERN = re.compile(r"^\s*(?:global|extern)\s+(.+)$", re.IGNORECASE)
ASM_INSTRUCTION_PATTERN = re.compile(r"^\s*(?![;%#])(?:[A-Za-z_.$?][\w.$?]*:\s*)?([A-Za-z][A-Za-z0-9_.]*)\b")
ASM_CALL_PATTERN = re.compile(r"\bcall\s+([^;#]+)", re.IGNORECASE)
C_FUNCTION_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*\([^;]*\)\s*\{")
C_FUNCTION_SIGNATURE_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*\([^;]*\)\s*$")
C_CONTROL_KEYWORDS = {"if", "for", "while", "switch"}
SYSCALL_PATTERN = re.compile(r"\b(?:syscall|int\s+0x80|int\s+80h|SYSCALL_[A-Z0-9_]+)\b", re.IGNORECASE)
HEX_NUMBER_PATTERN = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]+h\b")
MAKE_TARGET_PATTERN = re.compile(r"^([A-Za-z0-9_./%-]+)\s*:(?!=)")


@dataclasses.dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclasses.dataclass(frozen=True)
class SourceFileStats:
    path: str
    language: str
    lines: int
    nonblank_lines: int
    comment_lines: int
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class AssemblyFileAnalysis:
    path: str
    labels: List[str]
    globals: List[str]
    externs: List[str]
    instructions: Mapping[str, int]
    calls: List[str]
    registers: Mapping[str, int]
    hex_literals: List[str]


def is_colab() -> bool:
    """Return True when running inside Google Colab."""
    return "google.colab" in sys.modules or Path("/content").exists()


def run_command(command: Sequence[str], cwd: Optional[Path] = None, timeout: int = 120) -> CommandResult:
    """Run a command and capture stdout/stderr without raising on failure."""
    printable = " ".join(shlex.quote(part) for part in command)
    try:
        proc = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CommandResult(printable, proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CommandResult(printable, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(printable, 124, stdout, stderr + "\nTimed out")


def print_command_result(result: CommandResult, max_chars: int = 4000) -> None:
    status = "PASS" if result.returncode == 0 else "WARN"
    print(f"[{status}] {result.command} -> {result.returncode}")
    body = (result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else "")).strip()
    if body:
        print(body[:max_chars])
        if len(body) > max_chars:
            print(f"... truncated {len(body) - max_chars} chars ...")


def resolve_repo() -> Path:
    """Resolve the repository path from Colab/local configuration."""
    if REPO_SOURCE == "clone":
        if not REPO_URL:
            raise ValueError("Set REPO_URL or RADIUM_ANALYZER_REPO_URL when REPO_SOURCE='clone'.")
        target = Path("/content/radium") if is_colab() else Path("radium-clone")
        if target.exists():
            shutil.rmtree(target)
        print_command_result(run_command(["git", "clone", REPO_URL, str(target)], timeout=300))
        return target.resolve()

    if REPO_SOURCE == "upload":
        if not is_colab():
            raise RuntimeError("REPO_SOURCE='upload' requires Google Colab.")
        from google.colab import files  # type: ignore

        uploaded = files.upload()
        if not uploaded:
            raise RuntimeError("No repository archive uploaded.")
        archive = Path(next(iter(uploaded)))
        extract_dir = Path("/content/radium_upload")
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_dir)
        else:
            shutil.unpack_archive(str(archive), str(extract_dir))
        candidates = [p for p in extract_dir.rglob("Makefile") if (p.parent / "kernel").exists()]
        return (candidates[0].parent if candidates else extract_dir).resolve()

    if REPO_SOURCE == "mounted":
        return Path(MOUNTED_REPO_PATH).expanduser().resolve()

    return Path(LOCAL_REPO_PATH).expanduser().resolve()


def iter_source_files(repo: Path) -> Iterable[Path]:
    """Yield source and metadata files that are useful for this analysis."""
    useful_names = {"Makefile", "README.md", "linker.ld", "menu.lst", "mtoolsrc", "Vagrantfile"}
    for path in sorted(repo.rglob("*")):
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix in ASM_EXTENSIONS | C_EXTENSIONS or path.name in useful_names:
            yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def classify_language(path: Path) -> str:
    if path.suffix in ASM_EXTENSIONS:
        return "assembly"
    if path.suffix == ".c":
        return "c"
    if path.suffix == ".h":
        return "header"
    if path.name == "Makefile":
        return "makefile"
    if path.suffix == ".ld":
        return "linker_script"
    return "metadata"


def source_stats(repo: Path, path: Path) -> SourceFileStats:
    text = read_text(path)
    lines = text.splitlines()
    language = classify_language(path)
    comment_prefixes = (";", "#") if language == "assembly" else ("//", "/*", "*", "#")
    comment_lines = sum(1 for line in lines if line.strip().startswith(comment_prefixes))
    return SourceFileStats(
        path=str(path.relative_to(repo)),
        language=language,
        lines=len(lines),
        nonblank_lines=sum(1 for line in lines if line.strip()),
        comment_lines=comment_lines,
        size_bytes=path.stat().st_size,
    )


def strip_asm_comment(line: str) -> str:
    """Strip common NASM/GAS comment suffixes without trying to parse strings."""
    return re.split(r"[;#]", line, maxsplit=1)[0]


def split_symbol_list(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,\s]+", text) if item.strip()]


def analyze_assembly_file(repo: Path, path: Path) -> AssemblyFileAnalysis:
    labels: List[str] = []
    globals_: List[str] = []
    externs: List[str] = []
    instructions: collections.Counter[str] = collections.Counter()
    calls: List[str] = []
    registers: collections.Counter[str] = collections.Counter()
    hex_literals: List[str] = []

    for raw_line in read_text(path).splitlines():
        code = strip_asm_comment(raw_line).strip()
        if not code:
            continue

        label_match = ASM_LABEL_PATTERN.match(code)
        if label_match:
            labels.append(label_match.group(1))

        global_match = ASM_GLOBAL_PATTERN.match(code)
        if global_match:
            directive = code.split(None, 1)[0].lower()
            symbols = split_symbol_list(global_match.group(1))
            if directive == "global":
                globals_.extend(symbols)
            elif directive == "extern":
                externs.extend(symbols)

        instruction_match = ASM_INSTRUCTION_PATTERN.match(code)
        if instruction_match:
            mnemonic = instruction_match.group(1).lower()
            if mnemonic not in {"global", "extern", "section", "bits", "align", "struc", "endstruc"}:
                instructions[mnemonic] += 1

        for call_match in ASM_CALL_PATTERN.finditer(code):
            target = call_match.group(1).strip().split()[0].strip(",")
            calls.append(target)

        registers.update(register.lower() for register in ASM_REGISTER_PATTERN.findall(code))
        hex_literals.extend(HEX_NUMBER_PATTERN.findall(code))

    return AssemblyFileAnalysis(
        path=str(path.relative_to(repo)),
        labels=sorted(set(labels)),
        globals=sorted(set(globals_)),
        externs=sorted(set(externs)),
        instructions=dict(sorted(instructions.items())),
        calls=calls,
        registers=dict(sorted(registers.items())),
        hex_literals=sorted(set(hex_literals)),
    )


def analyze_makefiles(repo: Path) -> Dict[str, List[str]]:
    targets: Dict[str, List[str]] = {}
    for makefile in sorted(repo.rglob("Makefile")):
        if any(part in IGNORED_DIR_NAMES for part in makefile.parts):
            continue
        rel = str(makefile.relative_to(repo))
        file_targets: List[str] = []
        for line in read_text(makefile).splitlines():
            match = MAKE_TARGET_PATTERN.match(line)
            if match and not match.group(1).startswith("."):
                file_targets.append(match.group(1))
        targets[rel] = file_targets
    return targets


def analyze_c_sources(repo: Path) -> Dict[str, object]:
    functions: Dict[str, List[str]] = {}
    syscall_lines: Dict[str, List[str]] = {}
    include_graph: Dict[str, List[str]] = {}
    constants: Dict[str, List[str]] = {}

    for path in sorted(repo.rglob("*")):
        if any(part in IGNORED_DIR_NAMES for part in path.parts) or path.suffix not in C_EXTENSIONS:
            continue
        rel = str(path.relative_to(repo))
        text = read_text(path)
        function_names: List[str] = []
        previous_code_line = ""
        for line in text.splitlines():
            stripped = line.strip()
            match = C_FUNCTION_PATTERN.match(line)
            if not match and stripped == "{":
                match = C_FUNCTION_SIGNATURE_PATTERN.match(previous_code_line)
            if match and match.group(1) not in C_CONTROL_KEYWORDS:
                function_names.append(match.group(1))
            if stripped and not stripped.startswith(("//", "/*", "*")):
                previous_code_line = line
        functions[rel] = function_names
        syscall_hits: List[str] = []
        literal_hits: List[str] = []
        includes: List[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            if SYSCALL_PATTERN.search(line):
                syscall_hits.append(f"{line_no}: {line.strip()}")
            if "0x" in line or re.search(r"\b[0-9a-fA-F]+h\b", line):
                literal_hits.extend(HEX_NUMBER_PATTERN.findall(line))
            include_match = re.match(r"\s*#\s*include\s+[<\"]([^>\"]+)[>\"]", line)
            if include_match:
                includes.append(include_match.group(1))
        if syscall_hits:
            syscall_lines[rel] = syscall_hits
        include_graph[rel] = includes
        if literal_hits:
            constants[rel] = sorted(set(literal_hits))

    return {
        "functions": functions,
        "syscall_lines": syscall_lines,
        "include_graph": include_graph,
        "hex_constants": constants,
    }


def inspect_build_artifacts(repo: Path) -> Dict[str, object]:
    artifacts = [repo / "kernel" / "radium.bin", repo / "user" / "init.bin"]
    report: Dict[str, object] = {}
    for artifact in artifacts:
        rel = str(artifact.relative_to(repo))
        if not artifact.exists():
            report[rel] = {"exists": False}
            continue
        commands = {
            "file": ["file", str(artifact)],
            "size": ["size", str(artifact)],
            "nm_top": ["sh", "-lc", f"nm -n {shlex.quote(str(artifact))} | head -80"],
            "readelf_headers": ["readelf", "-h", str(artifact)],
            "objdump_disassembly_head": ["sh", "-lc", f"objdump -d -Mintel {shlex.quote(str(artifact))} | head -220"],
        }
        report[rel] = {
            "exists": True,
            "size_bytes": artifact.stat().st_size,
            "commands": {name: dataclasses.asdict(run_command(command, cwd=repo)) for name, command in commands.items()},
        }
    return report


def maybe_build(repo: Path) -> List[Dict[str, object]]:
    if not RUN_BUILD:
        return []
    build_commands = [["make", "clean"], ["make"]]
    return [dataclasses.asdict(run_command(command, cwd=repo, timeout=600)) for command in build_commands]


def top_counter(counter: Mapping[str, int], limit: int = 25) -> List[Tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]


def write_csv(path: Path, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    import csv

    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(headers)
        writer.writerows(rows)


def create_charts(output_dir: Path, stats: Sequence[SourceFileStats], instruction_totals: Mapping[str, int]) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - optional Colab dependency
        print(f"Skipping charts because matplotlib is unavailable: {exc}")
        return

    by_language: collections.Counter[str] = collections.Counter()
    for item in stats:
        by_language[item.language] += item.nonblank_lines

    plt.figure(figsize=(9, 5))
    plt.bar(by_language.keys(), by_language.values())
    plt.title("Nonblank source lines by language/file type")
    plt.ylabel("Lines")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "lines_by_language.png", dpi=160)
    plt.close()

    top_instructions = top_counter(instruction_totals, 20)
    if top_instructions:
        names, counts = zip(*top_instructions)
        plt.figure(figsize=(10, 6))
        plt.barh(list(reversed(names)), list(reversed(counts)))
        plt.title("Top assembly mnemonics")
        plt.xlabel("Count")
        plt.tight_layout()
        plt.savefig(output_dir / "top_assembly_instructions.png", dpi=160)
        plt.close()


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def fmt(value: object) -> str:
        return str(value).replace("|", "\\|")

    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(fmt(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def source_snippet(repo: Path, rel_path: str, limit: int = MAX_SOURCE_SNIPPET_LINES) -> str:
    path = repo / rel_path
    lines = read_text(path).splitlines()[:limit]
    numbered = [f"{idx + 1:>4}: {line}" for idx, line in enumerate(lines)]
    return "\n".join(numbered)


def generate_report(repo: Path) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_files = list(iter_source_files(repo))
    stats = [source_stats(repo, path) for path in source_files]
    asm_files = [path for path in source_files if path.suffix in ASM_EXTENSIONS]
    asm_analysis = [analyze_assembly_file(repo, path) for path in asm_files]

    instruction_totals: collections.Counter[str] = collections.Counter()
    register_totals: collections.Counter[str] = collections.Counter()
    calls: List[Tuple[str, str]] = []
    all_labels: Dict[str, List[str]] = {}
    for item in asm_analysis:
        instruction_totals.update(item.instructions)
        register_totals.update(item.registers)
        calls.extend((item.path, target) for target in item.calls)
        for label in item.labels:
            all_labels.setdefault(label, []).append(item.path)

    c_report = analyze_c_sources(repo)
    makefile_report = analyze_makefiles(repo)
    build_results = maybe_build(repo)
    artifact_report = inspect_build_artifacts(repo)

    write_csv(
        OUTPUT_DIR / "source_inventory.csv",
        ["path", "language", "lines", "nonblank_lines", "comment_lines", "size_bytes"],
        ([s.path, s.language, s.lines, s.nonblank_lines, s.comment_lines, s.size_bytes] for s in stats),
    )
    write_csv(OUTPUT_DIR / "assembly_instruction_frequency.csv", ["mnemonic", "count"], top_counter(instruction_totals, 10_000))
    write_csv(OUTPUT_DIR / "assembly_register_frequency.csv", ["register", "count"], top_counter(register_totals, 10_000))
    write_csv(OUTPUT_DIR / "assembly_calls.csv", ["source_file", "target"], calls)
    write_csv(
        OUTPUT_DIR / "assembly_labels.csv",
        ["label", "defined_in"],
        ([label, "; ".join(paths)] for label, paths in sorted(all_labels.items())),
    )

    full_report = {
        "repo": str(repo),
        "source_inventory": [dataclasses.asdict(s) for s in stats],
        "assembly_files": [dataclasses.asdict(a) for a in asm_analysis],
        "assembly_instruction_totals": dict(instruction_totals),
        "assembly_register_totals": dict(register_totals),
        "c_report": c_report,
        "makefile_targets": makefile_report,
        "build_results": build_results,
        "artifacts": artifact_report,
    }
    (OUTPUT_DIR / "full_report.json").write_text(json.dumps(full_report, indent=2, sort_keys=True), encoding="utf-8")
    create_charts(OUTPUT_DIR, stats, instruction_totals)

    language_rows = []
    by_language: Dict[str, List[SourceFileStats]] = collections.defaultdict(list)
    for item in stats:
        by_language[item.language].append(item)
    for language, items in sorted(by_language.items()):
        language_rows.append((language, len(items), sum(item.nonblank_lines for item in items), sum(item.size_bytes for item in items)))

    top_file_rows = [
        (item.path, item.language, item.nonblank_lines, item.size_bytes)
        for item in sorted(stats, key=lambda s: (-s.nonblank_lines, s.path))[:20]
    ]
    top_instruction_rows = top_counter(instruction_totals, 20)
    top_register_rows = top_counter(register_totals, 20)

    asm_summary_rows = [
        (
            item.path,
            len(item.labels),
            len(item.globals),
            len(item.externs),
            sum(item.instructions.values()),
            len(item.calls),
        )
        for item in asm_analysis
    ]

    unresolved_calls = sorted({target for _, target in calls if target not in all_labels and not target.startswith("[")})
    syscall_files = c_report.get("syscall_lines", {})
    function_counts = sorted(
        ((path, len(names)) for path, names in c_report.get("functions", {}).items()),
        key=lambda item: (-item[1], item[0]),
    )[:20]

    report_md = f"""# Radium Cloud9 Assembly Analysis Report

Repository: `{repo}`

## Executive summary

* Source files analyzed: **{len(stats)}**
* Assembly files analyzed: **{len(asm_analysis)}**
* Assembly labels discovered: **{len(all_labels)}**
* Assembly call instructions discovered: **{len(calls)}**
* Distinct assembly mnemonics: **{len(instruction_totals)}**
* Report directory: `{OUTPUT_DIR}`

## Source inventory by language/file type

{markdown_table(["Language", "Files", "Nonblank lines", "Bytes"], language_rows)}

## Largest source files

{markdown_table(["Path", "Type", "Nonblank lines", "Bytes"], top_file_rows)}

## Assembly file summary

{markdown_table(["Path", "Labels", "Globals", "Externs", "Instructions", "Calls"], asm_summary_rows)}

## Top assembly mnemonics

{markdown_table(["Mnemonic", "Count"], top_instruction_rows)}

## Top registers referenced in assembly

{markdown_table(["Register", "Count"], top_register_rows)}

## Potential external or indirect call targets

These targets appear in `call` instructions but were not found as local labels by this static analyzer.
Some are expected externs or indirect operands.

{markdown_table(["Target"], [(target,) for target in unresolved_calls[:60]]) if unresolved_calls else "No unresolved direct call targets found."}

## C function counts

{markdown_table(["Path", "Function-like definitions"], function_counts)}

## Syscall-related lines

```json
{json.dumps(syscall_files, indent=2)}
```

## Makefile targets

```json
{json.dumps(makefile_report, indent=2)}
```

## Build artifacts

```json
{json.dumps({key: {'exists': value.get('exists'), 'size_bytes': value.get('size_bytes')} for key, value in artifact_report.items()}, indent=2)}
```

## Useful next steps for a Cloud9 assembly presentation

1. Explain how the boot loader transfers control to the kernel entry assembly.
2. Walk through GDT/IDT setup and identify which assembly files provide CPU transition glue.
3. Use `assembly_instruction_frequency.csv` to discuss common low-level operations.
4. Use `assembly_calls.csv` and `assembly_labels.csv` to draw a manual control-flow diagram.
5. If build tools are installed, set `RADIUM_ANALYZER_RUN_BUILD=1` before running to inspect ELF headers and disassembly.

## Generated files

* `source_inventory.csv`
* `assembly_instruction_frequency.csv`
* `assembly_register_frequency.csv`
* `assembly_calls.csv`
* `assembly_labels.csv`
* `full_report.json`
* `lines_by_language.png` when matplotlib is available
* `top_assembly_instructions.png` when matplotlib is available
""".strip()

    (OUTPUT_DIR / "README.md").write_text(report_md + "\n", encoding="utf-8")
    return OUTPUT_DIR / "README.md"


def maybe_download_report(output_dir: Path) -> None:
    """Zip and download report when running in Colab."""
    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    print(f"Report archive created: {archive}")
    if is_colab():
        try:
            from google.colab import files  # type: ignore

            files.download(archive)
        except Exception as exc:  # pragma: no cover - Colab-only convenience
            print(f"Could not trigger Colab download automatically: {exc}")


def main() -> None:
    repo = resolve_repo()
    if not repo.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")
    print(f"Analyzing repository: {repo}")
    report_path = generate_report(repo)
    print(f"\nReport written to: {report_path}")
    print("\nPreview:\n")
    print(read_text(report_path)[:5000])
    maybe_download_report(OUTPUT_DIR)


if __name__ == "__main__":
    main()

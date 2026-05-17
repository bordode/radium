#!/usr/bin/env python3
"""Cloud9 Assembly: lightweight investigation notes for astronomy essays.

The tool turns short article excerpts or claim notes into a structured,
plain-text investigation report.  It is intentionally dependency-free so it can
run inside the minimal Radium development environment.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import Iterable


@dataclasses.dataclass(frozen=True)
class InvestigationSeed:
    title: str
    focus: str
    claims: tuple[str, ...]
    checks: tuple[str, ...]


DEFAULT_SEEDS: tuple[InvestigationSeed, ...] = (
    InvestigationSeed(
        title="A Tale of Three Gas Clouds Orbiting Sagittarius A*",
        focus=(
            "Compares stellar-source and wind-source explanations for the "
            "compact Galactic-center gas clouds G1, G2, and G3."
        ),
        claims=(
            "Sagittarius A* is the Milky Way's central supermassive black hole.",
            "G1, G2, and G3 follow unusually similar orbits near Sagittarius A*.",
            "A proto-planetary disk around a young star could produce a compact gas cloud when tidally disturbed.",
            "A massive binary wind model must explain how diffuse gas becomes compact dense clumps.",
            "A disrupted young triple-star system is an alternative source model.",
        ),
        checks=(
            "Compare published orbital elements for G1, G2, and G3, including uncertainties and pericenter epochs.",
            "Estimate the chance alignment rate for unrelated young stars on similar Galactic-center orbits.",
            "Model whether IRS 16SW-like winds can cool and compress into observed cloud masses before shear disperses them.",
            "Search for faint stellar counterparts or dust excesses that would favor embedded-star models.",
        ),
    ),
    InvestigationSeed(
        title="The Cosmic Shells that Seeded Life",
        focus=(
            "Connects first-star nucleosynthesis, pair-instability supernovae, "
            "and the later availability of carbon and oxygen for life."
        ),
        claims=(
            "Big Bang nucleosynthesis produced negligible carbon and oxygen compared with hydrogen and helium.",
            "The first stars likely formed roughly 100 million years after the Big Bang.",
            "Very massive first stars can end as pair-instability supernovae that disperse heavy elements.",
            "A universe-wide room-temperature epoch occurred before abundant oxygen was available.",
            "Older technological civilizations, if they exist, could have sent artifacts into interstellar space.",
        ),
        checks=(
            "Cross-check first-star formation times against current Population III simulations and JWST constraints.",
            "Identify which stellar mass ranges trigger pair-instability supernovae and which collapse to black holes.",
            "Separate well-established nucleosynthesis claims from speculative technosignature implications.",
            "Quantify lunar impact survival and detectability for hypothetical interstellar artifacts.",
        ),
    ),
)

KEYWORDS = (
    "Sagittarius A*",
    "G1",
    "G2",
    "G3",
    "IRS 16SW",
    "proto-planetary",
    "triple",
    "Big Bang",
    "carbon",
    "oxygen",
    "pair-instability",
    "first stars",
    "technological civilizations",
    "Moon",
)

RISK_PATTERNS = (
    (re.compile(r"\bunknown\b|\bprobability\b|\blikelihood\b", re.I), "uncertainty / likelihood claim"),
    (re.compile(r"\bsuggest\w*\b|\bmight\b|\bcould\b|\bpossible\b", re.I), "hypothesis or model"),
    (re.compile(r"\bfirst\b|\bonly\b|\bfully understood\b|\ball\b", re.I), "broad or exclusivity claim"),
    (re.compile(r"\bshould\b|\bneed to\b|\bpriority\b", re.I), "recommendation"),
)


def wrap(text: str, width: int = 88, indent: str = "") -> str:
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]


def interesting_sentences(text: str, limit: int = 12) -> list[str]:
    sentences = split_sentences(text)
    ranked: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        score = sum(2 for keyword in KEYWORDS if keyword.lower() in sentence.lower())
        score += sum(1 for pattern, _ in RISK_PATTERNS if pattern.search(sentence))
        if score:
            ranked.append((-score, index, sentence))
    ranked.sort()
    return [sentence for _, _, sentence in ranked[:limit]]


def classify_sentence(sentence: str) -> list[str]:
    labels = [label for pattern, label in RISK_PATTERNS if pattern.search(sentence)]
    return labels or ["descriptive claim"]


def keyword_counts(texts: Iterable[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    joined = "\n".join(texts)
    for keyword in KEYWORDS:
        counts[keyword] = len(re.findall(re.escape(keyword), joined, flags=re.I))
    return counts


def render_seed(seed: InvestigationSeed) -> str:
    lines = [f"## {seed.title}", "", wrap(seed.focus), "", "### Claims to test"]
    lines.extend(f"- {claim}" for claim in seed.claims)
    lines.extend(["", "### Suggested checks"])
    lines.extend(f"- {check}" for check in seed.checks)
    return "\n".join(lines)


def render_custom(title: str, text: str) -> str:
    lines = [f"## {title}", "", "### Extracted high-signal sentences"]
    sentences = interesting_sentences(text)
    if not sentences:
        lines.append("- No astronomy investigation signals were detected in the provided text.")
    for sentence in sentences:
        labels = ", ".join(classify_sentence(sentence))
        lines.append(f"- [{labels}] {sentence}")

    counts = keyword_counts([text])
    seen = [(keyword, count) for keyword, count in counts.items() if count]
    if seen:
        lines.extend(["", "### Keyword hits"])
        lines.extend(f"- {keyword}: {count}" for keyword, count in seen)

    lines.extend(
        [
            "",
            "### Next investigation steps",
            "- Resolve article links to primary papers and record DOI/arXiv identifiers.",
            "- Split observational claims from interpretations and speculative implications.",
            "- Reproduce any quantitative probability, timescale, or mass estimates in a notebook.",
            "- Capture contrary models and note what observation would falsify each model.",
        ]
    )
    return "\n".join(lines)


def read_inputs(paths: list[Path]) -> list[tuple[str, str]]:
    if paths:
        return [(path.name, path.read_text(encoding="utf-8")) for path in paths]

    if sys.stdin.isatty():
        return []

    data = sys.stdin.read()
    return [("stdin investigation", data)] if data.strip() else []


def build_report(inputs: list[tuple[str, str]]) -> str:
    lines = ["# Cloud9 Assembly Investigation Report", ""]
    lines.append(
        wrap(
            "Purpose: organize the supplied astronomy article material into "
            "claims, risk labels, and concrete verification tasks for Radium's "
            "development system."
        )
    )
    lines.append("")

    if inputs:
        for title, text in inputs:
            lines.append(render_custom(title, text))
            lines.append("")
    else:
        for seed in DEFAULT_SEEDS:
            lines.append(render_seed(seed))
            lines.append("")

        counts = keyword_counts(claim for seed in DEFAULT_SEEDS for claim in (*seed.claims, *seed.checks))
        lines.extend(["## Cross-article keyword map", ""])
        lines.extend(f"- {keyword}: {count}" for keyword, count in counts.items() if count)
        lines.append("")

    lines.extend(
        [
            "## Output discipline",
            "",
            "- Treat this report as a triage artifact, not as a fact-check by itself.",
            "- Prefer primary papers, observatory data releases, and reproducible calculations for final conclusions.",
            "- Keep copyrighted article text outside the repository; feed excerpts through stdin or local files when needed.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble an investigation report for supplied astronomy article excerpts."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional UTF-8 text files to investigate. With no files and no stdin, built-in claim seeds are used.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the report to this path instead of stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    inputs = read_inputs(args.paths)
    report = build_report(inputs)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

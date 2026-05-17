#!/usr/bin/env python3
"""Cloud9 Assembly investigator for JWST little red dot candidates.

This dependency-free tool turns a small candidate catalogue into an evidence
ledger for early-universe black-hole hypotheses. It is intentionally conservative:
it does not declare a source to be a black hole, but it highlights the growth and
observational tensions that make compact red JWST sources interesting.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# Flat Lambda-CDM defaults close to Planck 2018 values. These constants are kept
# local so the tool remains runnable from a fresh Cloud9/dev-shell environment.
H0_KM_S_MPC = 67.4
OMEGA_M = 0.315
OMEGA_LAMBDA = 0.685
UNIVERSE_AGE_GYR = 13.8
SALPETER_TIME_MYR = 45.0  # e-folding time for epsilon ~= 0.1 at Eddington.


@dataclass(frozen=True)
class Candidate:
    """Minimal catalogue row for a little-red-dot candidate."""

    name: str
    redshift: float
    bh_mass_msun: float
    stellar_mass_msun: float
    radius_pc: float
    xray_status: str
    notes: str = ""


@dataclass(frozen=True)
class Investigation:
    """Derived diagnostics for one candidate."""

    candidate: Candidate
    cosmic_age_myr: float
    lookback_gyr: float
    bh_to_stellar_ratio: float
    eddington_seed_100myr_msun: float
    compactness_msun_pc2: float
    cloud9_score: int
    flags: tuple[str, ...]


def _as_float(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except KeyError as exc:
        raise ValueError(f"missing required column: {field}") from exc
    except ValueError as exc:
        raise ValueError(f"invalid numeric value for {field}: {row.get(field)!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"non-finite numeric value for {field}: {value!r}")
    return value


def load_candidates(path: Path) -> list[Candidate]:
    """Load candidates from a CSV file."""

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        candidates: list[Candidate] = []
        for line_number, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            if not name:
                raise ValueError(f"line {line_number}: missing candidate name")
            candidates.append(
                Candidate(
                    name=name,
                    redshift=_as_float(row, "redshift"),
                    bh_mass_msun=_as_float(row, "bh_mass_msun"),
                    stellar_mass_msun=_as_float(row, "stellar_mass_msun"),
                    radius_pc=_as_float(row, "radius_pc"),
                    xray_status=(row.get("xray_status") or "unknown").strip().lower(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return candidates


def cosmic_age_myr(redshift: float, *, steps: int = 4096) -> float:
    """Approximate cosmic age at redshift by numerical integration.

    The integral uses the analytic Hubble time scale and Simpson's rule over the
    scale factor. Accuracy is more than sufficient for triage/reporting.
    """

    if redshift < 0:
        raise ValueError("redshift must be non-negative")
    if steps % 2:
        steps += 1

    scale_factor = 1.0 / (1.0 + redshift)
    h0_s = H0_KM_S_MPC / 3.0856775814913673e19
    hubble_time_gyr = 1.0 / h0_s / (60 * 60 * 24 * 365.25 * 1e9)

    def integrand(a: float) -> float:
        return 1.0 / (a * math.sqrt(OMEGA_M / a**3 + OMEGA_LAMBDA))

    delta = scale_factor / steps
    total = integrand(1e-12) + integrand(scale_factor)
    for index in range(1, steps):
        coefficient = 4 if index % 2 else 2
        total += coefficient * integrand(index * delta)
    return hubble_time_gyr * delta * total / 3.0 * 1000.0


def seed_mass_for_growth(final_mass_msun: float, available_myr: float) -> float:
    """Return the Eddington-limited seed mass needed for a final mass."""

    if final_mass_msun <= 0:
        raise ValueError("final black-hole mass must be positive")
    if available_myr <= 0:
        return final_mass_msun
    return final_mass_msun / math.exp(available_myr / SALPETER_TIME_MYR)


def investigate(candidate: Candidate, *, seed_start_myr: float = 100.0) -> Investigation:
    age_myr = cosmic_age_myr(candidate.redshift)
    growth_window = max(age_myr - seed_start_myr, 0.0)
    ratio = candidate.bh_mass_msun / candidate.stellar_mass_msun if candidate.stellar_mass_msun else math.inf
    compactness = candidate.stellar_mass_msun / (math.pi * candidate.radius_pc**2)

    flags: list[str] = []
    score = 0
    if age_myr < 1000:
        flags.append("first-gyr object")
        score += 2
    if ratio >= 0.01:
        flags.append("overmassive BH/stellar ratio")
        score += 2
    if candidate.radius_pc <= 300:
        flags.append("compact source")
        score += 1
    if candidate.xray_status in {"weak", "hidden", "undetected", "absorbed"}:
        flags.append("X-ray weak/obscured")
        score += 1
    if seed_mass_for_growth(candidate.bh_mass_msun, growth_window) >= 1_000:
        flags.append("requires massive seed or super-Eddington growth")
        score += 2

    return Investigation(
        candidate=candidate,
        cosmic_age_myr=age_myr,
        lookback_gyr=UNIVERSE_AGE_GYR - age_myr / 1000.0,
        bh_to_stellar_ratio=ratio,
        eddington_seed_100myr_msun=seed_mass_for_growth(candidate.bh_mass_msun, growth_window),
        compactness_msun_pc2=compactness,
        cloud9_score=score,
        flags=tuple(flags),
    )


def render_markdown(investigations: Sequence[Investigation]) -> str:
    """Render a compact Markdown report."""

    lines = [
        "# Cloud9 Little Red Dot Investigation",
        "",
        "Cloud9 Assembly scores JWST little-red-dot candidates by combining cosmic age, compactness, black-hole-to-stellar mass ratio, and X-ray obscuration clues.",
        "",
        "| Candidate | z | Age (Myr) | Lookback (Gyr) | BH mass (M☉) | BH/stellar | Seed needed from 100 Myr (M☉) | Cloud9 | Flags |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in sorted(investigations, key=lambda result: result.cloud9_score, reverse=True):
        c = item.candidate
        flags = ", ".join(item.flags) or "baseline"
        lines.append(
            "| {name} | {z:.3g} | {age:.0f} | {lookback:.2f} | {bh:.2e} | {ratio:.2%} | {seed:.2e} | {score}/8 | {flags} |".format(
                name=c.name,
                z=c.redshift,
                age=item.cosmic_age_myr,
                lookback=item.lookback_gyr,
                bh=c.bh_mass_msun,
                ratio=item.bh_to_stellar_ratio,
                seed=item.eddington_seed_100myr_msun,
                score=item.cloud9_score,
                flags=flags,
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "* A high Cloud9 score is a triage signal, not a discovery claim.",
            "* The seed-mass column assumes continuous Eddington-limited accretion with a 45 Myr Salpeter time after a 100 Myr seed epoch.",
            "* X-ray weak candidates remain ambiguous: dense cocoons, viewing angle, source variability, or non-AGN stellar populations can mimic parts of the signature.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_self_test() -> None:
    """Small deterministic checks for CI and fresh workspaces."""

    age_z7 = cosmic_age_myr(7.0)
    if not 700 <= age_z7 <= 850:
        raise AssertionError(f"expected z=7 age near 0.75 Gyr, got {age_z7:.1f} Myr")
    candidate = Candidate("test", 7.0, 10_000_000, 100_000_000, 100, "weak")
    result = investigate(candidate)
    if result.cloud9_score < 6:
        raise AssertionError(f"expected high score for compact overmassive candidate, got {result.cloud9_score}")
    if "overmassive BH/stellar ratio" not in result.flags:
        raise AssertionError("expected overmassive ratio flag")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investigate JWST little red dot candidates with Cloud9 Assembly diagnostics.")
    parser.add_argument("catalog", nargs="?", default="data/little_red_dots/sample_candidates.csv", type=Path, help="CSV catalogue to investigate")
    parser.add_argument("--output", "-o", type=Path, help="write Markdown report to this path instead of stdout")
    parser.add_argument("--self-test", action="store_true", help="run deterministic internal checks")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        run_self_test()
        return 0

    candidates = load_candidates(args.catalog)
    report = render_markdown([investigate(candidate) for candidate in candidates])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

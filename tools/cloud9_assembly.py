#!/usr/bin/env python3
"""Cloud9 Assembly negative-mass binary investigator.

This utility is intentionally dependency-free so it can be run from a fresh
Cloud9-style shell beside the Radium OS sources.  It does not claim that
negative mass exists; it gives a small Newtonian/gravitational-wave proxy for
sorting hypothetical binaries into the three regimes discussed in current
negative-mass-binary proposals:

* negative total mass: no bound circular binary
* positive total mass with a mixed-sign pair: anti-chirp expansion
* zero total mass: runaway limit

Masses are in arbitrary units.  Set gravitational and inertial masses
separately to probe equivalence-principle-breaking cases.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from typing import Iterable, TextIO

G = 1.0
C = 1.0
EPSILON = 1.0e-12


@dataclass(frozen=True)
class Body:
    """One member of a binary system."""

    gravitational_mass: float
    inertial_mass: float

    @property
    def charge_to_inertia(self) -> float:
        """Ratio controlling response to a gravitational field."""

        return self.gravitational_mass / self.inertial_mass


@dataclass(frozen=True)
class BinaryCase:
    """A compact classification of one two-body configuration."""

    name: str
    primary: Body
    secondary: Body
    separation: float

    @property
    def total_gravitational_mass(self) -> float:
        return self.primary.gravitational_mass + self.secondary.gravitational_mass

    @property
    def product_gravitational_mass(self) -> float:
        return self.primary.gravitational_mass * self.secondary.gravitational_mass

    @property
    def dipole_contrast(self) -> float:
        return abs(self.primary.charge_to_inertia - self.secondary.charge_to_inertia)


def classify(binary: BinaryCase) -> str:
    """Return the qualitative orbital/gravitational-wave regime."""

    total_mass = binary.total_gravitational_mass
    mass_product = binary.product_gravitational_mass

    if math.isclose(total_mass, 0.0, abs_tol=EPSILON):
        return "runaway: zero total gravitational mass"
    if total_mass < 0.0:
        return "repulsive: negative total gravitational mass"
    if mass_product < 0.0:
        return "anti-chirp: mixed signs expand while radiating"
    return "chirp: ordinary inspiral proxy"


def orbital_frequency(binary: BinaryCase) -> float:
    """Circular-orbit frequency proxy for positive-total-mass cases."""

    total_mass = binary.total_gravitational_mass
    if total_mass <= 0.0:
        return float("nan")
    angular_frequency = math.sqrt(G * total_mass / binary.separation**3)
    return angular_frequency / (2.0 * math.pi)


def gw_separation_rate(binary: BinaryCase) -> float:
    """Quadrupole-inspired da/dt sign proxy.

    With all constants normalized to one, the standard expression has the sign
    of -m1*m2*(m1+m2).  A mixed-sign pair with positive total mass therefore
    expands instead of inspiraling.
    """

    total_mass = binary.total_gravitational_mass
    mass_product = binary.product_gravitational_mass
    return -(64.0 / 5.0) * G**3 * mass_product * total_mass / (C**5 * binary.separation**3)


def frequency_slope(binary: BinaryCase) -> float:
    """df/dt proxy obtained by differentiating f proportional to a^-3/2."""

    frequency = orbital_frequency(binary)
    if math.isnan(frequency):
        return float("nan")
    return -1.5 * frequency * gw_separation_rate(binary) / binary.separation


def default_cases(separation: float) -> list[BinaryCase]:
    """Representative cases covering the expected negative-mass regimes."""

    return [
        BinaryCase(
            "ordinary_positive_binary",
            Body(gravitational_mass=1.0, inertial_mass=1.0),
            Body(gravitational_mass=0.6, inertial_mass=0.6),
            separation,
        ),
        BinaryCase(
            "positive_total_mixed_sign",
            Body(gravitational_mass=1.0, inertial_mass=1.0),
            Body(gravitational_mass=-0.4, inertial_mass=-0.4),
            separation,
        ),
        BinaryCase(
            "negative_total_mixed_sign",
            Body(gravitational_mass=0.4, inertial_mass=0.4),
            Body(gravitational_mass=-1.0, inertial_mass=-1.0),
            separation,
        ),
        BinaryCase(
            "zero_total_runaway",
            Body(gravitational_mass=1.0, inertial_mass=1.0),
            Body(gravitational_mass=-1.0, inertial_mass=-1.0),
            separation,
        ),
        BinaryCase(
            "equivalence_breaking_dipole_candidate",
            Body(gravitational_mass=1.0, inertial_mass=1.0),
            Body(gravitational_mass=-0.4, inertial_mass=0.8),
            separation,
        ),
    ]


def load_cases(path: str, separation: float) -> list[BinaryCase]:
    """Load cases from CSV columns: name,m1g,m1i,m2g,m2i[,separation]."""

    cases: list[BinaryCase] = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                case_separation = float(row.get("separation") or separation)
                case = BinaryCase(
                    row.get("name") or f"case_{row_number}",
                    Body(float(row["m1g"]), float(row["m1i"])),
                    Body(float(row["m2g"]), float(row["m2i"])),
                    case_separation,
                )
            except KeyError as error:
                raise SystemExit(f"missing CSV column: {error}") from error
            except ValueError as error:
                raise SystemExit(f"invalid numeric value on CSV row {row_number}: {error}") from error
            validate(case)
            cases.append(case)
    return cases


def validate(binary: BinaryCase) -> None:
    if math.isclose(binary.primary.inertial_mass, 0.0, abs_tol=EPSILON):
        raise SystemExit(f"{binary.name}: primary inertial mass must be nonzero")
    if math.isclose(binary.secondary.inertial_mass, 0.0, abs_tol=EPSILON):
        raise SystemExit(f"{binary.name}: secondary inertial mass must be nonzero")
    if binary.separation <= 0.0:
        raise SystemExit(f"{binary.name}: separation must be positive")


def format_float(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:.6g}"


def render(cases: Iterable[BinaryCase], output: TextIO) -> None:
    headers = [
        "case",
        "m_total",
        "dipole_contrast",
        "f_orbit",
        "da_dt_proxy",
        "df_dt_proxy",
        "classification",
    ]
    rows = []
    for case in cases:
        rows.append(
            [
                case.name,
                format_float(case.total_gravitational_mass),
                format_float(case.dipole_contrast),
                format_float(orbital_frequency(case)),
                format_float(gw_separation_rate(case)),
                format_float(frequency_slope(case)),
                classify(case),
            ]
        )

    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]

    output.write("Cloud9 Assembly: negative-mass binary investigation\n")
    output.write("=" * 56 + "\n")
    output.write("  ".join(header.ljust(width) for header, width in zip(headers, widths)) + "\n")
    output.write("  ".join("-" * width for width in widths) + "\n")
    for row in rows:
        output.write("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Investigate hypothetical negative-mass binary regimes."
    )
    parser.add_argument(
        "--separation",
        type=float,
        default=10.0,
        help="default binary separation for generated or CSV cases",
    )
    parser.add_argument(
        "--csv",
        help="optional CSV with name,m1g,m1i,m2g,m2i[,separation] columns",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.separation <= 0.0:
        raise SystemExit("--separation must be positive")

    cases = load_cases(args.csv, args.separation) if args.csv else default_cases(args.separation)
    for case in cases:
        validate(case)
    render(cases, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

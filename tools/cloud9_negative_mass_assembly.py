#!/usr/bin/env python3
"""Cloud9-friendly negative-mass binary investigation tool.

This script assembles a small Newtonian diagnostic report for binary systems
that contain positive and/or negative gravitational masses. It is intentionally
stdlib-only so it can run in lightweight Cloud9-style development shells.

The model is a probe, not a detector pipeline: it classifies qualitative regimes
that are useful when looking for the gravitational-wave signatures discussed in
recent negative-mass-binary proposals.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import sys
from typing import Iterable, Optional

G = 6.67430e-11
C = 299_792_458.0
SOLAR_MASS = 1.98847e30


@dataclasses.dataclass(frozen=True)
class BinaryScenario:
    """Input parameters for a signed-mass binary investigation."""

    primary_solar_masses: float
    secondary_solar_masses: float
    separation_m: float
    primary_grav_to_inertial: float = 1.0
    secondary_grav_to_inertial: float = 1.0

    @property
    def m1(self) -> float:
        return self.primary_solar_masses * SOLAR_MASS

    @property
    def m2(self) -> float:
        return self.secondary_solar_masses * SOLAR_MASS

    @property
    def total_mass(self) -> float:
        return self.m1 + self.m2

    @property
    def mass_product(self) -> float:
        return self.m1 * self.m2


@dataclasses.dataclass(frozen=True)
class Investigation:
    """Computed qualitative and approximate quantitative diagnostics."""

    regime: str
    circular_orbit: bool
    radiation_signature: str
    orbital_frequency_hz: Optional[float]
    gravitational_wave_frequency_hz: Optional[float]
    orbital_energy_j: Optional[float]
    separation_drift_m_per_s: Optional[float]
    chirp_direction: str
    dipole_radiation_expected: bool
    notes: tuple[str, ...]


def _safe_quadrupole_power(scenario: BinaryScenario) -> float:
    """Return a positive quadrupole power scale for bound circular cases."""

    reduced_mass = scenario.mass_product / scenario.total_mass
    return (
        (32.0 / 5.0)
        * G**4
        * reduced_mass**2
        * abs(scenario.total_mass) ** 3
        / (C**5 * scenario.separation_m**5)
    )


def investigate(scenario: BinaryScenario) -> Investigation:
    """Classify a signed-mass binary and estimate its waveform trend."""

    if scenario.separation_m <= 0:
        raise ValueError("separation must be positive")

    notes: list[str] = []
    dipole = not math.isclose(
        scenario.primary_grav_to_inertial,
        scenario.secondary_grav_to_inertial,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
    if dipole:
        notes.append(
            "different gravitational/inertial mass ratios imply dipole radiation in addition to quadrupole terms"
        )

    if math.isclose(scenario.total_mass, 0.0, rel_tol=0.0, abs_tol=1e-9 * SOLAR_MASS):
        return Investigation(
            regime="zero-total-mass runaway",
            circular_orbit=False,
            radiation_signature="runaway acceleration rather than periodic inspiral",
            orbital_frequency_hz=None,
            gravitational_wave_frequency_hz=None,
            orbital_energy_j=None,
            separation_drift_m_per_s=None,
            chirp_direction="none",
            dipole_radiation_expected=dipole,
            notes=tuple(
                notes
                + [
                    "the signed total mass cancels, "
                    "so the Newtonian circular-orbit frequency is undefined"
                ]
            ),
        )

    if scenario.total_mass < 0:
        return Investigation(
            regime="negative-total-mass repulsive",
            circular_orbit=False,
            radiation_signature="short-lived scattering/repulsive system",
            orbital_frequency_hz=None,
            gravitational_wave_frequency_hz=None,
            orbital_energy_j=None,
            separation_drift_m_per_s=None,
            chirp_direction="none",
            dipole_radiation_expected=dipole,
            notes=tuple(notes + ["negative signed total mass prevents a stable Newtonian circular binary"]),
        )

    omega = math.sqrt(G * scenario.total_mass / scenario.separation_m**3)
    orbital_frequency = omega / (2.0 * math.pi)
    gravitational_wave_frequency = 2.0 * orbital_frequency
    energy = -G * scenario.mass_product / (2.0 * scenario.separation_m)
    power = _safe_quadrupole_power(scenario)
    d_energy_d_separation = G * scenario.mass_product / (2.0 * scenario.separation_m**2)
    separation_drift = -power / d_energy_d_separation

    if scenario.mass_product < 0:
        regime = "positive-total mixed-sign expanding binary"
        signature = "anti-chirp: frequency decreases as gravitational radiation carries energy away"
        chirp = "decreasing"
        notes.append("opposite mass signs make the orbital energy positive and drive expansion under energy loss")
    else:
        regime = "ordinary positive-mass inspiral"
        signature = "chirp: frequency increases as the binary inspirals"
        chirp = "increasing"
        notes.append("same-sign positive masses reproduce the familiar inspiral trend")

    return Investigation(
        regime=regime,
        circular_orbit=True,
        radiation_signature=signature,
        orbital_frequency_hz=orbital_frequency,
        gravitational_wave_frequency_hz=gravitational_wave_frequency,
        orbital_energy_j=energy,
        separation_drift_m_per_s=separation_drift,
        chirp_direction=chirp,
        dipole_radiation_expected=dipole,
        notes=tuple(notes),
    )


def format_report(scenario: BinaryScenario, result: Investigation) -> str:
    """Render a compact, terminal-friendly investigation report."""

    def maybe(value: Optional[float], unit: str) -> str:
        if value is None:
            return "n/a"
        return f"{value:.6e} {unit}"

    lines = [
        "Negative-mass binary investigation",
        "===================================",
        f"m1: {scenario.primary_solar_masses:.6g} solar masses",
        f"m2: {scenario.secondary_solar_masses:.6g} solar masses",
        f"separation: {scenario.separation_m:.6e} m",
        f"total signed mass: {scenario.total_mass / SOLAR_MASS:.6g} solar masses",
        "",
        f"regime: {result.regime}",
        f"stable circular orbit in this model: {'yes' if result.circular_orbit else 'no'}",
        f"radiation signature: {result.radiation_signature}",
        f"dipole radiation expected: {'yes' if result.dipole_radiation_expected else 'no'}",
        f"orbital frequency: {maybe(result.orbital_frequency_hz, 'Hz')}",
        f"dominant GW frequency: {maybe(result.gravitational_wave_frequency_hz, 'Hz')}",
        f"orbital energy: {maybe(result.orbital_energy_j, 'J')}",
        f"separation drift: {maybe(result.separation_drift_m_per_s, 'm/s')}",
        f"chirp direction: {result.chirp_direction}",
    ]

    if result.notes:
        lines.extend(["", "notes:"])
        lines.extend(f"- {note}" for note in result.notes)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble Cloud9-friendly diagnostics for signed-mass binaries.",
    )
    parser.add_argument(
        "--m1", type=float, default=30.0, help="primary signed mass in solar masses"
    )
    parser.add_argument(
        "--m2", type=float, default=-10.0, help="secondary signed mass in solar masses"
    )
    parser.add_argument(
        "--separation", type=float, default=1.0e9, help="binary separation in meters"
    )
    parser.add_argument(
        "--m1-grav-to-inertial",
        type=float,
        default=1.0,
        help="primary gravitational/inertial mass ratio for equivalence-principle checks",
    )
    parser.add_argument(
        "--m2-grav-to-inertial",
        type=float,
        default=1.0,
        help="secondary gravitational/inertial mass ratio for equivalence-principle checks",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenario = BinaryScenario(
            primary_solar_masses=args.m1,
            secondary_solar_masses=args.m2,
            separation_m=args.separation,
            primary_grav_to_inertial=args.m1_grav_to_inertial,
            secondary_grav_to_inertial=args.m2_grav_to_inertial,
        )
        result = investigate(scenario)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_report(scenario, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

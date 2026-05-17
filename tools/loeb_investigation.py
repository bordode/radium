#!/usr/bin/env python3
"""Toy investigations for recent Avi Loeb article claims.

This script is intentionally self-contained so it can run in lightweight
Cloud9-style shells or in this repository without third-party packages.  It is
not a numerical-relativity or stellar-evolution solver; it assembles small,
transparent Python calculations that check orders of magnitude and sign logic
for claims discussed in the supplied articles:

* positive/negative-mass binary classifications and gravitational-wave chirps,
* the cosmic microwave background temperature at early cosmic times, and
* simple Galactic-center scales for compact gas clouds near Sagittarius A*.

Use the output as an investigation checklist, not as proof of the papers.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Iterable

G = 6.67430e-11
C = 299_792_458.0
AU = 1.495978707e11
DAY = 86_400.0
YEAR = 365.25 * DAY
SOLAR_MASS = 1.98847e30
EARTH_MASS = 5.9722e24
CMB_TODAY_K = 2.7255
H0_KM_S_MPC = 67.4
OMEGA_M = 0.315
MPC_M = 3.0856775814913673e22


def hubble_si(h0_km_s_mpc: float = H0_KM_S_MPC) -> float:
    return h0_km_s_mpc * 1_000.0 / MPC_M


def matter_era_temperature(age_years: float) -> float:
    """Approximate CMB temperature at a post-recombination matter-era age.

    The approximation uses t = 2 / (3 H0 sqrt(Omega_m)) * (1 + z)^(-3/2),
    which is adequate for quick order-of-magnitude checks around 10--100 Myr.
    """

    age_seconds = age_years * YEAR
    one_plus_z = (
        2.0 / (3.0 * hubble_si() * math.sqrt(OMEGA_M) * age_seconds)
    ) ** (2.0 / 3.0)
    return CMB_TODAY_K * one_plus_z


@dataclass(frozen=True)
class BinaryScenario:
    positive_mass_solar: float
    secondary_mass_solar: float
    separation_au: float

    @property
    def total_mass_solar(self) -> float:
        return self.positive_mass_solar + self.secondary_mass_solar

    def classification(self) -> str:
        total = self.total_mass_solar
        if math.isclose(total, 0.0, rel_tol=0.0, abs_tol=1e-12):
            return "zero-total-mass runaway: no ordinary periodic orbit"
        if total < 0.0:
            return "negative-total-mass repulsive case: stable binaries are not expected"
        if self.secondary_mass_solar < 0.0:
            return "positive-total mixed-sign case: circular orbit can expand into an anti-chirp"
        return "ordinary positive-positive case: energy loss drives inspiral chirp"

    def orbital_frequency_hz(self) -> float | None:
        total = self.total_mass_solar
        if total <= 0.0:
            return None
        total_kg = total * SOLAR_MASS
        radius_m = self.separation_au * AU
        return math.sqrt(G * total_kg / radius_m**3) / (2.0 * math.pi)

    def gw_frequency_hz(self) -> float | None:
        orbital = self.orbital_frequency_hz()
        return None if orbital is None else 2.0 * orbital

    def energy_sign(self) -> str:
        product = self.positive_mass_solar * self.secondary_mass_solar
        if product < 0.0 and self.total_mass_solar > 0.0:
            return (
                "positive orbital-energy sign; losing energy moves the binary "
                "outward toward zero energy"
            )
        if product > 0.0 and self.total_mass_solar > 0.0:
            return "negative orbital-energy sign; losing energy shrinks the binary"
        return "not an ordinary bound Keplerian energy case"


def anti_chirp_table(
    scenario: BinaryScenario, expansion_factors: Iterable[float]
) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for factor in expansion_factors:
        expanded = BinaryScenario(
            scenario.positive_mass_solar,
            scenario.secondary_mass_solar,
            scenario.separation_au * factor,
        )
        gw = expanded.gw_frequency_hz()
        if gw is not None:
            rows.append((expanded.separation_au, gw))
    return rows


def sgr_a_orbital_period_years(
    semi_major_axis_au: float, central_mass_solar: float = 4.0e6
) -> float:
    radius_m = semi_major_axis_au * AU
    mass_kg = central_mass_solar * SOLAR_MASS
    return 2.0 * math.pi * math.sqrt(radius_m**3 / (G * mass_kg)) / YEAR


def schwarzschild_radius_au(mass_solar: float = 4.0e6) -> float:
    return 2.0 * G * mass_solar * SOLAR_MASS / C**2 / AU


def format_hz(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6e} Hz"


def run(args: argparse.Namespace) -> int:
    print("Loeb article investigation toolkit (toy checks)\n")

    scenarios = [
        BinaryScenario(30.0, 20.0, 0.2),
        BinaryScenario(30.0, -10.0, 0.2),
        BinaryScenario(10.0, -30.0, 0.2),
        BinaryScenario(10.0, -10.0, 0.2),
    ]
    print("1) Positive/negative-mass binary sign checks")
    for scenario in scenarios:
        print(
            f"   m+= {scenario.positive_mass_solar:g} Msun, "
            f"m2= {scenario.secondary_mass_solar:g} Msun, "
            f"total= {scenario.total_mass_solar:g} Msun -> {scenario.classification()}"
        )
        print(
            f"      GW frequency estimate at {scenario.separation_au:g} AU: "
            f"{format_hz(scenario.gw_frequency_hz())}"
        )
        print(f"      Energy logic: {scenario.energy_sign()}")

    mixed = BinaryScenario(
        args.positive_mass, -abs(args.negative_mass), args.separation_au
    )
    print("\n   Anti-chirp toy sequence for the requested mixed-sign binary:")
    for separation, gw in anti_chirp_table(mixed, [1, 2, 4, 8, 16]):
        print(f"      separation={separation:8.3f} AU -> f_GW={gw:.6e} Hz")

    print("\n2) Cosmic-shell / first-stars order-of-magnitude checks")
    for age_myr in [15.0, 100.0]:
        temp = matter_era_temperature(age_myr * 1.0e6)
        print(f"   Matter-era CMB temperature at ~{age_myr:g} Myr: {temp:.1f} K")
    print(
        "   Interpretation: the room-temperature claim is an order-of-magnitude "
        "fit, but carbon/oxygen require stellar nucleosynthesis."
    )

    print("\n3) Galactic-center gas-cloud scale checks")
    print(
        "   Sgr A* Schwarzschild radius for 4e6 Msun: "
        f"{schwarzschild_radius_au():.3f} AU"
    )
    for semi_major_axis in [100.0, 1_000.0, 10_000.0]:
        period = sgr_a_orbital_period_years(semi_major_axis)
        print(
            f"   Circular-period scale at {semi_major_axis:7.0f} AU "
            f"around Sgr A*: {period:.3f} years"
        )
    print(
        f"   A few Earth masses is tiny next to Sgr A*: "
        f"3 Mearth / 4e6 Msun = {3 * EARTH_MASS / (4.0e6 * SOLAR_MASS):.3e}"
    )

    print("\nInvestigation checklist")
    print(
        "   * Treat negative masses as speculative unless an observational "
        "population and formation mechanism are demonstrated."
    )
    print(
        "   * Search gravitational-wave catalogs for decreasing-frequency "
        "anti-chirps before claiming detections."
    )
    print(
        "   * Separate established first-star nucleosynthesis from speculative "
        "extraterrestrial-artifact implications."
    )
    print(
        "   * For G1/G2/G3, compare compact-cloud survival against "
        "stellar-source and diffuse-wind models."
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--positive-mass",
        type=float,
        default=30.0,
        help="positive component mass in solar masses",
    )
    parser.add_argument(
        "--negative-mass",
        type=float,
        default=10.0,
        help="absolute value of negative component mass in solar masses",
    )
    parser.add_argument(
        "--separation-au",
        type=float,
        default=0.2,
        help="initial binary separation in AU",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

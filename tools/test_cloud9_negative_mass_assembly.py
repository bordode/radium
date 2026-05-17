#!/usr/bin/env python3
"""Unit checks for the Cloud9 negative-mass assembly probe."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud9_negative_mass_assembly import BinaryScenario, investigate


class NegativeMassAssemblyTests(unittest.TestCase):
    def test_mixed_sign_positive_total_mass_expands_and_anti_chirps(self):
        result = investigate(BinaryScenario(30.0, -10.0, 1.0e9))

        self.assertTrue(result.circular_orbit)
        self.assertIn("mixed-sign", result.regime)
        self.assertEqual(result.chirp_direction, "decreasing")
        self.assertGreater(result.separation_drift_m_per_s, 0.0)

    def test_positive_masses_inspiral_and_chirp(self):
        result = investigate(BinaryScenario(30.0, 10.0, 1.0e9))

        self.assertTrue(result.circular_orbit)
        self.assertIn("ordinary", result.regime)
        self.assertEqual(result.chirp_direction, "increasing")
        self.assertLess(result.separation_drift_m_per_s, 0.0)

    def test_zero_total_mass_is_runaway(self):
        result = investigate(BinaryScenario(10.0, -10.0, 1.0e9))

        self.assertFalse(result.circular_orbit)
        self.assertIn("runaway", result.regime)
        self.assertIsNone(result.orbital_frequency_hz)

    def test_negative_total_mass_is_repulsive(self):
        result = investigate(BinaryScenario(10.0, -30.0, 1.0e9))

        self.assertFalse(result.circular_orbit)
        self.assertIn("repulsive", result.regime)

    def test_grav_to_inertial_mismatch_flags_dipole_radiation(self):
        result = investigate(BinaryScenario(30.0, -10.0, 1.0e9, 1.0, -1.0))

        self.assertTrue(result.dipole_radiation_expected)
        self.assertTrue(any("dipole" in note for note in result.notes))

    def test_non_positive_separation_is_rejected(self):
        with self.assertRaises(ValueError):
            investigate(BinaryScenario(30.0, -10.0, 0.0))


if __name__ == "__main__":
    unittest.main()

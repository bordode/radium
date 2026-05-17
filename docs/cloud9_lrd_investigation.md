# Cloud9 Little Red Dot Investigation

Cloud9 Assembly scores JWST little-red-dot candidates by combining cosmic age, compactness, black-hole-to-stellar mass ratio, and X-ray obscuration clues.

| Candidate | z | Age (Myr) | Lookback (Gyr) | BH mass (M☉) | BH/stellar | Seed needed from 100 Myr (M☉) | Cloud9 | Flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Overmassive-seed-stress-test | 12 | 368 | 13.43 | 5.00e+07 | 16.67% | 1.31e+05 | 8/8 | first-gyr object, overmassive BH/stellar ratio, compact source, X-ray weak/obscured, requires massive seed or super-Eddington growth |
| CANUCS-LRD-z8.6-like | 8.6 | 579 | 13.22 | 1.00e+07 | 5.00% | 2.38e+02 | 6/8 | first-gyr object, overmassive BH/stellar ratio, compact source, X-ray weak/obscured |
| Compact-starburst-control | 5 | 1171 | 12.63 | 1.00e+05 | 0.01% | 4.66e-06 | 2/8 | compact source, X-ray weak/obscured |
| AEGIS-XRD-bridge-like | 3.28 | 1939 | 11.86 | 4.00e+06 | 0.80% | 7.21e-12 | 1/8 | compact source |

## Interpretation guardrails

* A high Cloud9 score is a triage signal, not a discovery claim.
* The seed-mass column assumes continuous Eddington-limited accretion with a 45 Myr Salpeter time after a 100 Myr seed epoch.
* X-ray weak candidates remain ambiguous: dense cocoons, viewing angle, source variability, or non-AGN stellar populations can mimic parts of the signature.

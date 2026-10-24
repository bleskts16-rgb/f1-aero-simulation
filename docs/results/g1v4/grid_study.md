# Grid study `g1v4`

U = 50.0 m/s, half model doubled to the full car, CL*A positive = downforce, mean (and peak-to-peak band) over the last 1000 iterations.

## zmode

| level | h0 [m] | cells | iters | CL*A [m^2] | CD*A [m^2] | FW CL*A | body CL*A | RW CL*A |
|---|---|---|---|---|---|---|---|---|
| L1 | 0.4 | 1,286,706 | 2000 | 1.307 (0.194) | 0.993 (0.080) | 0.891 | 0.138 | 0.652 |
| L2 | 0.3 | 2,390,309 | 2000 | 1.560 (0.148) | 1.004 (0.061) | 0.915 | 0.198 | 0.738 |

- L1 prism layers (mean count / thickness vs target): body 2.18 layers/70%, front_wing 2.47 layers/78%, rear_wing 2.53 layers/80%, wheels_front 1.97 layers/63%, wheels_rear 2.18 layers/70%; mean y+: body 100, front_wing 44, rear_wing 61
- L2 prism layers (mean count / thickness vs target): body 2.42 layers/78%, front_wing 2.60 layers/81%, rear_wing 2.67 layers/84%, wheels_front 2.54 layers/83%, wheels_rear 2.60 layers/86%; mean y+: body 70, front_wing 42, rear_wing 51

## xmode

| level | h0 [m] | cells | iters | CL*A [m^2] | CD*A [m^2] | FW CL*A | body CL*A | RW CL*A |
|---|---|---|---|---|---|---|---|---|
| L1 | 0.4 | 1,289,059 | 2000 | 0.771 (0.153) | 0.831 (0.050) | 0.536 | 0.228 | 0.304 |
| L2 | 0.3 | 2,392,757 | 2000 | 1.001 (0.147) | 0.827 (0.053) | 0.559 | 0.342 | 0.304 |

- L1 prism layers (mean count / thickness vs target): body 2.18 layers/70%, front_wing 2.48 layers/78%, rear_wing 2.54 layers/80%, wheels_front 1.97 layers/63%, wheels_rear 2.18 layers/70%; mean y+: body 100, front_wing 46, rear_wing 61
- L2 prism layers (mean count / thickness vs target): body 2.42 layers/78%, front_wing 2.60 layers/81%, rear_wing 2.68 layers/84%, wheels_front 2.54 layers/83%, wheels_rear 2.60 layers/86%; mean y+: body 71, front_wing 42, rear_wing 50

## Trend check: xmode - zmode

Difference between the two designs at each level, relative to the finest level (L2).

| level | dCL*A | dCD*A | dCL*A vs finest | dCD*A vs finest |
|---|---|---|---|---|
| L1 | -0.536 | -0.162 | +4.2 % | +8.5 % |
| L2 | -0.559 | -0.177 | +0.0 % | +0.0 % |

Coarsest level whose design difference is within 10 % of the finest level (same sign): **L1**

# Grid study `grid1`

U = 50.0 m/s, half model doubled to the full car, CL*A positive = downforce, mean (and peak-to-peak band) over the last 1000 iterations.

## baseline

| level | h0 [m] | cells | iters | CL*A [m^2] | CD*A [m^2] | FW CL*A | body CL*A | RW CL*A |
|---|---|---|---|---|---|---|---|---|
| L1 | 0.4 | 772,822 | 3000 | 1.352 (0.437) | 1.158 (0.092) | 1.016 | -0.025 | 0.703 |
| L2 | 0.3 | 1,449,566 | 3000 | 1.518 (0.207) | 1.167 (0.057) | 1.326 | -0.171 | 0.732 |
| L3 | 0.225 | 2,880,455 | 3000 | 1.601 (0.193) | 1.147 (0.045) | 1.349 | -0.143 | 0.763 |
| L4 | 0.1688 | 5,714,795 | 3000 | 1.443 (0.391) | 1.129 (0.102) | 1.257 | -0.135 | 0.669 |
| L5 | 0.1266 | 11,004,229 | 3000 | 1.875 (0.240) | 1.081 (0.043) | 1.152 | 0.161 | 0.791 |

- CL*A: grids L5, L4, L3 not in the asymptotic range (non-monotonic; order p=4.78 outside 0.5-3) -> no Richardson extrapolation / GCI. Spread over these grids 26.3 %, statistical error of each mean <= 0.014 m^2
- CD*A: grids L5, L4, L3 not in the asymptotic range (order p=4.56 outside 0.5-3) -> no Richardson extrapolation / GCI. Spread over these grids 5.9 %, statistical error of each mean <= 0.005 m^2
- L1 prism layers (mean count / thickness vs target): body 2.56 layers/70%, front_wing 2.65 layers/83%, rear_wing 2.49 layers/73%, wheels_front 2.53 layers/78%, wheels_rear 2.52 layers/72%; mean y+: body 218, front_wing 118, rear_wing 113
- L2 prism layers (mean count / thickness vs target): body 2.64 layers/76%, front_wing 2.74 layers/85%, rear_wing 2.61 layers/78%, wheels_front 2.90 layers/94%, wheels_rear 2.90 layers/88%; mean y+: body 190, front_wing 90, rear_wing 101
- L3 prism layers (mean count / thickness vs target): body 2.71 layers/80%, front_wing 2.79 layers/87%, rear_wing 2.68 layers/82%, wheels_front 2.96 layers/96%, wheels_rear 2.98 layers/96%; mean y+: body 143, front_wing 69, rear_wing 82
- L4 prism layers (mean count / thickness vs target): body 2.78 layers/85%, front_wing 2.84 layers/89%, rear_wing 2.71 layers/81%, wheels_front 2.94 layers/96%, wheels_rear 2.98 layers/97%; mean y+: body 110, front_wing 58, rear_wing 74
- L5 prism layers (mean count / thickness vs target): body 2.80 layers/85%, front_wing 2.77 layers/85%, rear_wing 2.74 layers/83%, wheels_front 2.97 layers/97%, wheels_rear 2.99 layers/98%; mean y+: body 88, front_wing 61, rear_wing 52

## low_drag

| level | h0 [m] | cells | iters | CL*A [m^2] | CD*A [m^2] | FW CL*A | body CL*A | RW CL*A |
|---|---|---|---|---|---|---|---|---|
| L1 | 0.4 | 776,421 | 3000 | 1.066 (0.440) | 0.940 (0.069) | 0.981 | -0.064 | 0.523 |
| L2 | 0.3 | 1,456,124 | 3000 | 1.293 (0.176) | 0.970 (0.027) | 1.276 | -0.152 | 0.504 |
| L3 | 0.225 | 2,910,419 | 3000 | 1.143 (0.107) | 0.937 (0.023) | 1.293 | -0.191 | 0.399 |
| L4 | 0.1688 | 5,788,714 | 3000 | 0.964 (0.314) | 0.947 (0.078) | 1.258 | -0.295 | 0.350 |
| L5 | 0.1266 | 11,096,879 | 3000 | 1.340 (0.294) | 0.897 (0.072) | 1.215 | -0.037 | 0.407 |

- CL*A: grids L5, L4, L3 not in the asymptotic range (non-monotonic; order p=3.56 outside 0.5-3) -> no Richardson extrapolation / GCI. Spread over these grids 32.7 %, statistical error of each mean <= 0.017 m^2
- CD*A: grids L5, L4, L3 not in the asymptotic range (non-monotonic; order p=7.78 outside 0.5-3) -> no Richardson extrapolation / GCI. Spread over these grids 5.4 %, statistical error of each mean <= 0.004 m^2
- L1 prism layers (mean count / thickness vs target): body 2.56 layers/70%, front_wing 2.66 layers/83%, rear_wing 2.51 layers/75%, wheels_front 2.53 layers/78%, wheels_rear 2.52 layers/73%; mean y+: body 228, front_wing 114, rear_wing 103
- L2 prism layers (mean count / thickness vs target): body 2.64 layers/76%, front_wing 2.74 layers/85%, rear_wing 2.62 layers/79%, wheels_front 2.90 layers/94%, wheels_rear 2.89 layers/88%; mean y+: body 187, front_wing 89, rear_wing 87
- L3 prism layers (mean count / thickness vs target): body 2.71 layers/80%, front_wing 2.81 layers/87%, rear_wing 2.71 layers/83%, wheels_front 2.96 layers/96%, wheels_rear 2.98 layers/96%; mean y+: body 142, front_wing 70, rear_wing 78
- L4 prism layers (mean count / thickness vs target): body 2.78 layers/85%, front_wing 2.84 layers/88%, rear_wing 2.73 layers/82%, wheels_front 2.95 layers/96%, wheels_rear 2.98 layers/97%; mean y+: body 110, front_wing 59, rear_wing 70
- L5 prism layers (mean count / thickness vs target): body 2.80 layers/85%, front_wing 2.78 layers/86%, rear_wing 2.76 layers/85%, wheels_front 2.97 layers/97%, wheels_rear 2.99 layers/98%; mean y+: body 90, front_wing 59, rear_wing 59

## Trend check: low_drag - baseline

Difference between the two designs at each level, relative to the finest level (L5).

| level | dCL*A | dCD*A | dCL*A vs finest | dCD*A vs finest |
|---|---|---|---|---|
| L1 | -0.286 | -0.218 | +46.6 % | -18.4 % |
| L2 | -0.226 | -0.197 | +57.9 % | -6.7 % |
| L3 | -0.458 | -0.210 | +14.5 % | -13.8 % |
| L4 | -0.480 | -0.181 | +10.5 % | +1.8 % |
| L5 | -0.536 | -0.184 | +0.0 % | +0.0 % |

Coarsest level whose design difference is within 10 % of the finest level (same sign): **none**
